"""Exact grounding and conservative clause-local attribution, never verification."""
import hashlib
import json
import re
from dataclasses import dataclass

from app.researchguard.domain import AtomicClaim, AttributionStatus, CitationResolutionStatus, TextSpan
from app.services.citation_context import diagnostic, groups

ATTRIBUTION_POLICY_VERSION = "exact-clause-guard-v1"
_STRONG = re.compile(r";|\b(?:while|whereas|but)\b", re.IGNORECASE)
_MODIFIERS = re.compile(r"\b(?:not|no|never|neither|without|may|might|could|can|must|should|"
                        r"suggests?|appears?|possibly|probably|likely|unlikely|potentially)\b", re.IGNORECASE)
_RESTRICTION = re.compile(r"\b(?:only|if|unless|when|provided|compared|relative|versus|vs|during|"
                          r"among|within|in patients|on small|in small)\b.*", re.IGNORECASE)
_TOKENS = re.compile(r"\w+(?:['’]\w+)*|[%±<>=/+−-]", re.UNICODE)
_QUANTITIES = re.compile(
    r"\d+(?:[.,]\d+)*(?:\s*(?:%|percent\b|mg\b|kg\b|g\b|ml\b|mm\b|cm\b|ms\b|"
    r"seconds?\b|minutes?\b|hours?\b|days?\b|years?\b))?", re.IGNORECASE)


class ProposalRejected(ValueError):
    def __init__(self, code):
        super().__init__("An extraction proposal did not satisfy grounding or attribution policy.")
        self.code = code


@dataclass(frozen=True)
class ValidatedClaim:
    claim: AtomicClaim
    diagnostics: tuple = ()


def exact_span(text, quote, focal):
    matches, offset = [], focal.start
    while offset < focal.end:
        position = text.find(quote.quote, offset, focal.end)
        if position < 0:
            break
        end = position + len(quote.quote)
        if ((quote.left_anchor is None or text[max(focal.start, position - len(quote.left_anchor)):position] == quote.left_anchor)
                and (quote.right_anchor is None or text[end:min(focal.end, end + len(quote.right_anchor))] == quote.right_anchor)):
            matches.append(TextSpan(start=position, end=end))
        offset = position + 1  # Enumerate every occurrence, including overlapping matches.
    if not matches:
        raise ProposalRejected("QUOTE_NOT_FOUND")
    if len(matches) != 1:
        raise ProposalRejected("QUOTE_AMBIGUOUS")
    return matches[0]


def _without_markers(text, start, end, callouts):
    chars = list(text[start:end])
    for c in callouts:
        for i in range(max(start, c.span.start), min(end, c.span.end)):
            chars[i - start] = " "
    return "".join(chars)


def _scopes(text, focal, callouts, paragraph_fallback=False):
    cuts = {focal.start, focal.end}
    for match in _STRONG.finditer(text, focal.start, focal.end):
        cuts.add(match.start())
        cuts.add(match.end())
    if paragraph_fallback:
        # A conservative attribution barrier, not inferred sentence spans. Without
        # trusted boundaries, never associate across explicit terminal punctuation.
        # Decimal points are exempt; abbreviations may intentionally cause abstention.
        for match in re.finditer(r"(?<!\d)[.!?]|[.!?](?!\d)", text[focal.start:focal.end]):
            cuts.add(focal.start + match.end())
    # A marker followed by a comma and substantive prose is an explicit new clause.
    # Commas between adjacent refs never form this boundary.
    for group in groups(text, callouts):
        end = group[-1].span.end
        match = re.match(r"\s*,\s*", text[end:focal.end])
        if match and not any(c.span.start == end + match.end() for c in callouts):
            cuts.add(end + match.end())
    ordered = sorted(cuts)
    return [(a, b) for a, b in zip(ordered, ordered[1:])
            if _without_markers(text, a, b, callouts).strip(" ,;.!?")]


def _shared_subject(text, focal, quote, span, main_start):
    # Limited named-subject recovery, not arbitrary coreference or trusting role tags.
    match = re.match(r"(?:Although\s+)?([A-Z][\w-]*(?:\s+[A-Z][\w-]*)*)\b", text[focal.start:focal.end])
    return bool(match and quote.quote == match.group(1)
                and span.start == focal.start + match.start(1) and span.end <= main_start)


def _semantic_guard(proposal, parts, scope_text):
    joined = " ".join(p.quote for p in parts)
    if _TOKENS.findall(proposal.text) != _TOKENS.findall(joined):
        raise ProposalRejected("SEMANTIC_TEXT_DRIFT")
    if len(re.findall(r"\w+", proposal.text)) < 3:
        raise ProposalRejected("INVALID_ATOMIC_PROPOSITION")
    words = {t.lower() for t in _TOKENS.findall(joined)}
    if any(m.group().lower() not in words for m in _MODIFIERS.finditer(scope_text)):
        raise ProposalRejected("SEMANTIC_MODIFIER_DRIFT")
    source_numbers = re.findall(r"\d+(?:[.,]\d+)*", scope_text)
    claim_numbers = re.findall(r"\d+(?:[.,]\d+)*", joined)
    if any(n not in claim_numbers for n in source_numbers):
        raise ProposalRejected("SEMANTIC_NUMERIC_DRIFT")
    quantities = [_TOKENS.findall(m.group()) for m in _QUANTITIES.finditer(joined)]
    if any(_TOKENS.findall(m.group()) not in quantities for m in _QUANTITIES.finditer(scope_text)):
        raise ProposalRejected("SEMANTIC_NUMERIC_DRIFT")
    restriction = _RESTRICTION.search(scope_text)
    if restriction:
        required = _TOKENS.findall(restriction.group())
        # No broad paraphrase allowance for conditions/populations/comparisons.
        available = _TOKENS.findall(joined)
        if any(t not in available for t in required):
            raise ProposalRejected("SEMANTIC_SCOPE_DRIFT")


def validate_proposal(parsed, context, proposal) -> ValidatedClaim:
    paragraph = next(p for p in parsed.paragraphs if p.id == context.paragraph_id)
    local = [c for c in parsed.citation_callouts if c.id in context.citation_callout_ids]
    allowed = {c.id for c in local}
    if (len(set(proposal.citation_callout_ids)) != len(proposal.citation_callout_ids)
            or not set(proposal.citation_callout_ids) <= allowed):
        raise ProposalRejected("UNKNOWN_CITATION_CALLOUT")
    spans = tuple(exact_span(paragraph.text, q, context.focal_span) for q in proposal.source_quotes)
    previous = context.focal_span.start
    for span in spans:
        if span.start < previous:
            raise ProposalRejected("INVALID_SOURCE_SPAN_ORDER")
        previous = span.end
        if any(span.start < c.span.end and c.span.start < span.end for c in local):
            raise ProposalRejected("CITATION_MARKER_AS_SOURCE")
    main = [s for q, s in zip(proposal.source_quotes, spans) if q.role != "shared_subject"]
    if not main or not any(q.role == "predicate" for q in proposal.source_quotes):
        raise ProposalRejected("INVALID_ATOMIC_PROPOSITION")
    shared = [(q, s) for q, s in zip(proposal.source_quotes, spans) if q.role == "shared_subject"]
    if len(shared) > 1 or any(not _shared_subject(paragraph.text, context.focal_span, q, s, main[0].start) for q, s in shared):
        raise ProposalRejected("INVALID_SHARED_SUBJECT")
    scopes = _scopes(paragraph.text, context.focal_span, local,
                     context.scope_kind == "paragraph_fallback")
    scope = next(((a, b) for a, b in scopes if all(a <= s.start and s.end <= b for s in main)), None)
    # Ordinary subjects have no cross-clause recovery permission, even on abstention.
    if scope is None and any(q.role == "subject" for q in proposal.source_quotes):
        raise ProposalRejected("WRONG_CITATION_SCOPE")
    # Text/semantic checks cannot be bypassed by asking the model to abstain.
    if scope:
        _semantic_guard(proposal, proposal.source_quotes,
                        _without_markers(paragraph.text, *scope, local))
    else:
        _semantic_guard(proposal, proposal.source_quotes,
                        " ".join(paragraph.text[s.start:s.end] for s in main))
    selected = [c for c in local if c.id in proposal.citation_callout_ids]
    code, status = None, AttributionStatus.RESOLVED
    candidates = []
    if scope:
        candidates = [g for g in groups(paragraph.text, local)
                      if scope[0] <= g[0].span.start and g[-1].span.end <= scope[1]]
    if context.scope_kind == "trailing_marker" and scope:
        # Explicit attachment is the only supported citation-after-sentence exception.
        candidates = groups(paragraph.text, local)
    if (proposal.association != "abstain" and len(candidates) == 1
            and any(c.id not in {c.id for c in candidates[0]} for c in selected)):
        raise ProposalRejected("WRONG_CITATION_SCOPE")
    if (proposal.association == "abstain" or not scope or len(candidates) != 1
            or {c.id for c in candidates[0]} != {c.id for c in selected}):
        code, status = "AMBIGUOUS_CITATION_SCOPE", AttributionStatus.AMBIGUOUS
        selected = []
    elif any(c.resolution_status != CitationResolutionStatus.RESOLVED for c in selected):
        code, status = "INCOMPLETE_CITATION_TARGET", AttributionStatus.UNRESOLVED
    reference_ids = tuple(dict.fromkeys(r for c in selected for r in c.reference_ids))
    identity = json.dumps([context.id, proposal.text, [(s.start, s.end) for s in spans],
                           [c.id for c in selected], status.value, ATTRIBUTION_POLICY_VERSION])
    claim = AtomicClaim(id="claim:" + hashlib.sha256(identity.encode()).hexdigest(),
        manuscript_id=parsed.manuscript.id, paragraph_id=paragraph.id, context_id=context.id,
        text=proposal.text, page=paragraph.page, source_spans=spans, attribution_status=status,
        citation_callout_ids=tuple(c.id for c in selected), reference_ids=reference_ids)
    return ValidatedClaim(claim, (diagnostic(code, claim.id),) if code else ())


def validate_result(parsed, result):
    paragraphs = {p.id: p for p in parsed.paragraphs}
    calls = {c.id: c for c in parsed.citation_callouts}
    contexts = {c.id: c for c in result.contexts}
    for context in result.contexts:
        p = paragraphs[context.paragraph_id]
        if context.text != p.text[context.span.start:context.span.end]:
            raise ValueError("Context must exactly slice canonical paragraph")
        for cid in context.citation_callout_ids:
            c = calls[cid]
            if c.paragraph_id != p.id or not context.focal_span.start <= c.span.start < c.span.end <= context.focal_span.end:
                raise ValueError("Context occurrence must be inside focal")
    for claim in result.claims:
        context = contexts[claim.context_id]
        if (len(set(claim.citation_callout_ids)) != len(claim.citation_callout_ids)
                or not set(claim.citation_callout_ids) <= set(context.citation_callout_ids)):
            raise ValueError("Claim occurrences must belong to focal context")
        p = paragraphs[claim.paragraph_id]
        if any(s.end > len(p.text) or any(s.start < c.span.end and c.span.start < s.end
                   for c in calls.values() if c.paragraph_id == p.id) for s in claim.source_spans):
            raise ValueError("Claim sources cannot include citation markers")
        selected = [calls[cid] for cid in claim.citation_callout_ids]
        expected = tuple(dict.fromkeys(r for c in selected for r in c.reference_ids))
        if claim.reference_ids != expected:
            raise ValueError("References must be derived from selected occurrences")
        if claim.attribution_status == AttributionStatus.RESOLVED and any(c.resolution_status != CitationResolutionStatus.RESOLVED for c in selected):
            raise ValueError("Incomplete targets cannot form resolved attribution")
    return result
