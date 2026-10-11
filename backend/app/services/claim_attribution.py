"""Exact grounding and conservative clause-local attribution, never verification."""
import hashlib
import json
import re
from dataclasses import dataclass

from app.researchguard.domain import AtomicClaim, AttributionStatus, CitationResolutionStatus, TextSpan
from app.services.citation_context import diagnostic, groups
from app.services.citation_labels import local_label_index, visible_labels

ATTRIBUTION_POLICY_VERSION = "exact-evidence-visible-labels-v4"
_STRONG = re.compile(r";|\b(?:while|whereas|but)\b", re.IGNORECASE)


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
        position = text.find(quote, offset, focal.end)
        if position < 0:
            break
        end = position + len(quote)
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


def validate_proposal(parsed, context, proposal) -> ValidatedClaim:
    paragraph = next(p for p in parsed.paragraphs if p.id == context.paragraph_id)
    calls = {c.id: c for c in parsed.citation_callouts}
    local = [calls[cid] for cid in context.citation_callout_ids]
    labels = local_label_index(local)
    if (len(set(proposal.citation_labels)) != len(proposal.citation_labels)
            or not set(proposal.citation_labels) <= labels.keys()):
        raise ProposalRejected("UNKNOWN_CITATION_CALLOUT")
    if any(len(labels[label]) != 1 for label in proposal.citation_labels):
        raise ProposalRejected("AMBIGUOUS_CITATION_LABEL")
    span = exact_span(paragraph.text, proposal.evidence_quote, context.focal_span)
    if not _without_markers(paragraph.text, span.start, span.end, local).strip(" ,;.!?()[]"):
        raise ProposalRejected("CITATION_MARKER_AS_SOURCE")
    spans = (span,)
    scopes = _scopes(paragraph.text, context.focal_span, local,
                     context.scope_kind == "paragraph_fallback")
    # Evidence may contain markers or a full sentence. Only substantive evidence
    # must fit one ownership region; citation positions never disambiguate quotes.
    scope = next(((a, b) for a, b in scopes
                  if not _without_markers(paragraph.text, span.start, min(span.end, a), local).strip(" ,;.!?")
                  and not _without_markers(paragraph.text, max(span.start, b), span.end, local).strip(" ,;.!?")), None)
    selected_ids = {labels[x][0].id for x in proposal.citation_labels}
    selected = [c for c in local if c.id in selected_ids]
    code, status = None, AttributionStatus.RESOLVED
    candidates = []
    if scope:
        candidates = [g for g in groups(paragraph.text, local)
                      if scope[0] <= g[0].span.start and g[-1].span.end <= scope[1]]
    if context.scope_kind == "trailing_marker" and scope:
        # Explicit attachment is the only supported citation-after-sentence exception.
        candidates = groups(paragraph.text, local)
    if (len(candidates) == 1
            and any(c.id not in {c.id for c in candidates[0]} for c in selected)):
        raise ProposalRejected("WRONG_CITATION_SCOPE")
    if (not scope or len(candidates) != 1
            or {c.id for c in candidates[0]} != {c.id for c in selected}
            or any(not set(visible_labels(c.text)) <= set(proposal.citation_labels) for c in selected)):
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
        if claim.paragraph_id != context.paragraph_id or claim.manuscript_id != parsed.manuscript.id:
            raise ValueError("Claim must belong to its context and manuscript")
        p = paragraphs[claim.paragraph_id]
        if (len(claim.source_spans) != 1
                or any(not context.focal_span.start <= s.start < s.end <= context.focal_span.end <= len(p.text)
                       for s in claim.source_spans)):
            raise ValueError("Claim evidence must be one exact focal span")
        selected = [calls[cid] for cid in claim.citation_callout_ids]
        expected = tuple(dict.fromkeys(r for c in selected for r in c.reference_ids))
        if claim.reference_ids != expected:
            raise ValueError("References must be derived from selected occurrences")
        if claim.attribution_status == AttributionStatus.RESOLVED and (not selected or any(c.resolution_status != CitationResolutionStatus.RESOLVED for c in selected)):
            raise ValueError("Incomplete targets cannot form resolved attribution")
    return result
