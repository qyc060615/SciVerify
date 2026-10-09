"""Deterministic, callout-driven focal construction; no NLP or external I/O."""
import hashlib
import json
import re
from dataclasses import dataclass

from app.researchguard.domain import (
    CitationContext, CitationResolutionStatus, ManuscriptDiagnostic,
    ParsedManuscript, TextSpan,
)

CONTEXT_POLICY_VERSION = "citation-sentence-boundary-v2-quality-v1"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_TEXT = 200000
MAX_CONTEXTS = 64
MAX_FOCAL = 2000
MAX_WINDOW = 3000

# These are structural clues, not a vocabulary of paper/journal names.
_ABBREVIATIONS = frozenset({"al", "cf", "dr", "eq", "fig", "jr", "mr", "mrs", "ms",
                            "no", "prof", "sr", "st", "vs"})
_CONTINUATION_SUFFIX = re.compile(r"^(?:tion|sion|ment|ness|ance|ence)\s+[a-z]{2,}\b")
_TERMINAL = re.compile(r"[!?]|\.(?!\d)")


def _text_quality_code(parsed, paragraph, focal, local):
    """Bounded abstention only: do not infer grammar, repair words or merge prose.

    Mask markers before inspecting text; ownership and canonical offsets stay intact.
    A nearby broken token plus a bare morphological suffix is evidence of an
    incomplete target, not evidence sufficient to join two paragraphs.
    """
    chars = list(paragraph.text[focal.start:focal.end])
    for call in local:
        a, b = max(focal.start, call.span.start), min(focal.end, call.span.end)
        chars[a - focal.start:b - focal.start] = " " * (b - a)
    prose = "".join(chars).strip()
    opening = prose.lstrip("\"'“‘(")
    if (re.search(r"\b[\w.-]+\.(?:org|com|edu|net)\b", opening[:180], re.IGNORECASE)
            and re.search(r"\b(?:[A-Za-z]\s+){3,}", opening[:180])):
        return "SKIPPED_UNRELIABLE_TEXT"
    if re.match(r"(?:copyright\s*(?:©|\(c\))?\s*\d{4}|all rights reserved\b|"
                r"downloaded from\s+\S+\s+at\b)", opening, re.IGNORECASE):
        return "SKIPPED_UNRELIABLE_TEXT"
    if focal.start == 0 and _CONTINUATION_SUFFIX.match(opening):
        nearby = parsed.paragraphs[max(0, paragraph.order - 8):paragraph.order]
        if any(p.section == paragraph.section and re.search(r"[a-z]{3,}-$", p.text)
               for p in nearby):
            return "SKIPPED_INCOMPLETE_TEXT"
    if re.search(r"[a-z]{3,}-$", prose):
        return "SKIPPED_INCOMPLETE_TEXT"
    # Detect only clear additional prose after terminal punctuation. Abbreviations,
    # initials and decimals are exempt; ambiguous cases are not re-tokenized.
    for match in _TERMINAL.finditer(prose):
        before = re.search(r"([A-Za-z]+)$", prose[:match.start()])
        if match.group() == "." and before:
            word = before.group(1)
            if word.lower() in _ABBREVIATIONS or len(word) == 1:
                continue
        if re.match(r"\s*[\"'“‘(]?(?:[A-Z][\w-]*|\d+(?:[.,]\d+)?%?)\s+[A-Za-z]{2,}\b",
                    prose[match.end():]):
            return "SKIPPED_UNRELIABLE_TEXT"
    return None


class ExtractionInputError(ValueError):
    def __init__(self, code="INVALID_MANUSCRIPT_STRUCTURE", status_code=422):
        super().__init__("The submitted manuscript structure is invalid or exceeds extraction limits.")
        self.code = code
        self.status_code = status_code


def diagnostic(code, entity_id=None, severity="warning"):
    return ManuscriptDiagnostic(code=code, severity=severity, entity_id=entity_id,
                               safe_message="The extraction policy requires review of this structure.")


def fingerprint(parsed):
    payload = parsed.model_dump(mode="json")
    payload["manuscript"].pop("content_locator", None)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_input(parsed: ParsedManuscript):
    # Revalidate even a model_copy payload; it is not a server-authenticated artifact.
    try:
        parsed = ParsedManuscript.model_validate(parsed.model_dump())
        # JSON permits escaped lone surrogates, but prompts/HTTP output require
        # valid UTF-8. Reject safely here rather than failing during serialization.
        json.dumps(parsed.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
    except ValueError:
        raise ExtractionInputError() from None
    if parsed.citation_contexts:
        raise ExtractionInputError()
    if (len(parsed.paragraphs) > 1000 or len(parsed.references) > 2000
            or len(parsed.citation_callouts) > 2000 or sum(len(p.text) for p in parsed.paragraphs) > MAX_TEXT):
        raise ExtractionInputError("EXTRACTION_INPUT_TOO_LARGE", 413)
    paragraphs = {p.id: p for p in parsed.paragraphs}
    expected = sorted(parsed.citation_callouts, key=lambda c: (
        paragraphs[c.paragraph_id].order, c.span.start if c.span else -1))
    if list(parsed.citation_callouts) != expected or [c.order for c in expected] != list(range(len(expected))):
        raise ExtractionInputError()
    previous = {}
    for c in expected:
        if c.span is None or c.span.start < previous.get(c.paragraph_id, 0):
            raise ExtractionInputError()
        previous[c.paragraph_id] = c.span.end
    for collection in (parsed.paragraphs, parsed.references, parsed.citation_callouts):
        for item in collection:
            if len(item.id) > 512 or len(item.manuscript_id) > 512:
                raise ExtractionInputError("EXTRACTION_INPUT_TOO_LARGE", 413)
    return parsed


def from_request(request):
    data = request.parsed.model_dump()
    data["manuscript"]["content_locator"] = "submitted:client-structure"
    try:
        parsed = validate_input(ParsedManuscript.model_validate(data))
    except ExtractionInputError:
        raise
    except ValueError:
        raise ExtractionInputError() from None
    return parsed


def groups(text, callouts):
    result = []
    for c in callouts:
        if result and re.fullmatch(r"[\s,]*", text[result[-1][-1].span.end:c.span.start]):
            result[-1].append(c)
        else:
            result.append([c])
    return result


def marker_only(text, span, callouts):
    position = span.start
    remaining = []
    for c in callouts:
        if span.start <= c.span.start and c.span.end <= span.end:
            remaining.append(text[position:c.span.start])
            position = c.span.end
    remaining.append(text[position:span.end])
    return bool(callouts) and not re.sub(r"[\s.,;:!?()]+", "", "".join(remaining))


def _trim_span(text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return TextSpan(start=start, end=end)


def reliable_sentences(paragraph, callouts):
    spans = []
    for s in paragraph.sentence_spans:
        if not paragraph.text[s.start:s.end].strip():
            return []
        spans.append(_trim_span(paragraph.text, s.start, s.end))
    if not spans:
        return []
    previous = 0
    for s in spans:
        if paragraph.text[previous:s.start].strip():
            return []
        previous = s.end
    if paragraph.text[previous:].strip():
        tail = _trim_span(paragraph.text, previous, len(paragraph.text))
        tail_calls = [c for c in callouts if tail.start <= c.span.start and c.span.end <= tail.end]
        if not marker_only(paragraph.text, tail, tail_calls):
            return []
        spans.append(tail)  # Explicit citation-only segment, never a sentence tokenizer.
    return spans


@dataclass(frozen=True)
class ContextPlan:
    context: CitationContext
    diagnostics: tuple[ManuscriptDiagnostic, ...] = ()
    skip_code: str | None = None


@dataclass
class _SentenceOwner:
    focal: TextSpan
    callouts: list
    index: int
    kind: str = "sentence"
    skip: str | None = None


def _sentence_ownership(paragraph, sentences, calls):
    """Plan ownership without changing canonical sentence/callout offsets.

    Standalone markers retain the explicit trailing rule. For a leading group
    followed by prose, only bare numeric surfaces after a closed prose sentence
    qualify. Bracketed/punctuated prefixes and conflicting terminal groups abstain.
    A three-word minimum excludes short labels/headings; it is not a grammar parser.
    """
    text = paragraph.text
    owners = [_SentenceOwner(s, [c for c in calls if s.start <= c.span.start and c.span.end <= s.end], i)
              for i, s in enumerate(sentences)]
    for i, owner in enumerate(owners):
        if not owner.callouts:
            continue
        local_groups = groups(text, owner.callouts)
        leading = local_groups[0]
        if not re.fullmatch(r"[\s.,;:()\[\]]*", text[owner.focal.start:leading[0].span.start]):
            continue  # Ordinary inline citations, including narrative author names.
        standalone = marker_only(text, owner.focal, owner.callouts)
        if i == 0:
            if standalone:
                owner.skip = "UNRELIABLE_SENTENCE_SCOPE"
            continue  # A real prefix without a previous sentence is never reassigned.
        previous = owners[i - 1]
        previous_text = text[previous.focal.start:previous.focal.end]
        terminal_group = bool(previous.callouts and not text[
            previous.callouts[-1].span.end:previous.focal.end].strip(" \t\r\n.,;:!?()"))
        gap_clear = not text[previous.focal.end:leading[0].span.start].strip()
        bare = all(re.fullmatch(r"[\d\s,–-]+", c.text) for c in leading)
        prose_after = bool(re.match(r"\s+[^\W\d_]", text[leading[-1].span.end:owner.focal.end]))
        closed_prose = (previous_text.endswith((".", "!", "?"))
                        and len(re.findall(r"[^\W\d_]+", previous_text)) >= 3)
        attach = (not previous.skip and gap_clear and not terminal_group
                  and not marker_only(text, previous.focal, calls)
                  and (standalone and len(local_groups) == 1
                       or not standalone and bare and prose_after and closed_prose))
        if not attach:
            owner.skip = "UNRELIABLE_SENTENCE_SCOPE" if standalone else "AMBIGUOUS_BOUNDARY_CITATION"
            continue
        previous.focal = TextSpan(start=previous.focal.start, end=leading[-1].span.end)
        previous.callouts.extend(leading)
        previous.kind = "trailing_marker"
        owner.callouts = owner.callouts[len(leading):]
        if not standalone:
            owner.focal = _trim_span(text, leading[-1].span.end, owner.focal.end)
    return [(o.focal, o.callouts, o.kind, o.skip, o.index) for o in owners if o.callouts]


def build_contexts(parsed: ParsedManuscript) -> tuple[ContextPlan, ...]:
    parsed = validate_input(parsed)
    plans = []
    for p in parsed.paragraphs:
        calls = [c for c in parsed.citation_callouts if c.paragraph_id == p.id]
        if not calls:
            continue
        sentences = reliable_sentences(p, calls)
        focal_groups = []
        if not sentences:
            skip = "UNRELIABLE_SENTENCE_SCOPE" if len(groups(p.text, calls)) != 1 else None
            focal_groups.append((TextSpan(start=0, end=len(p.text)), calls, "paragraph_fallback", skip, None))
        else:
            focal_groups = _sentence_ownership(p, sentences, calls)
            assigned = {c.id for _, local, _, _, _ in focal_groups for c in local}
            unassigned = [c for c in calls if c.id not in assigned]
            if unassigned:
                focal_groups.append((TextSpan(start=0, end=len(p.text)), unassigned,
                                     "paragraph_fallback", "UNRELIABLE_SENTENCE_SCOPE", None))
        for focal, local, kind, skip, index in sorted(focal_groups, key=lambda g: g[0].start):
            start, end = focal.start, focal.end
            if index is not None:
                if index > 0 and sentences[index - 1].start < start:
                    start = sentences[index - 1].start
                following = index + 1
                while following < len(sentences) and sentences[following].end <= focal.end:
                    following += 1  # Skip consumed standalone marker segments.
                if following < len(sentences):
                    end = sentences[following].end
                if end - start > MAX_WINDOW:
                    start = focal.start
                if end - start > MAX_WINDOW:
                    end = focal.end
            identity = json.dumps([parsed.manuscript.id, p.id, focal.start, focal.end,
                                   [c.id for c in local], CONTEXT_POLICY_VERSION])
            context = CitationContext(id="context:" + hashlib.sha256(identity.encode()).hexdigest(),
                manuscript_id=parsed.manuscript.id, paragraph_id=p.id, page=p.page,
                text=p.text[start:end], span=TextSpan(start=start, end=end), focal_span=focal,
                scope_kind=kind, citation_callout_ids=tuple(c.id for c in local))
            if focal.end - focal.start > MAX_FOCAL:
                skip = "CONTEXT_TOO_LARGE"
            if not skip:
                skip = _text_quality_code(parsed, p, focal, local)
            if not skip and not any(c.resolution_status == CitationResolutionStatus.RESOLVED for c in local):
                skip = ("SKIPPED_UNRESOLVED_CITATION" if all(c.resolution_status == CitationResolutionStatus.UNRESOLVED for c in local)
                        else "SKIPPED_PARTIAL_CITATION")
            notes = (diagnostic(skip, context.id),) if skip else ()
            if skip == "SKIPPED_INCOMPLETE_TEXT":
                notes += (diagnostic("LAYOUT_METADATA_INSUFFICIENT", context.id, "info"),)
            if not sentences:
                notes += (diagnostic("MISSING_SENTENCE_BOUNDARIES", context.id, "info"),)
            plans.append(ContextPlan(context, notes, skip))
    if len(plans) > MAX_CONTEXTS:
        raise ExtractionInputError("EXTRACTION_CONTEXT_LIMIT", 413)
    return tuple(plans)
