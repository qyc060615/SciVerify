"""Deterministic, callout-driven focal construction; no NLP or external I/O."""
import hashlib
import json
import re
from dataclasses import dataclass

from app.researchguard.domain import (
    CitationContext, CitationResolutionStatus, ManuscriptDiagnostic,
    ParsedManuscript, TextSpan,
)

CONTEXT_POLICY_VERSION = "citation-sentence-v1"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_TEXT = 200000
MAX_CONTEXTS = 64
MAX_FOCAL = 2000
MAX_WINDOW = 3000


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
            assigned = set()
            for i, s in enumerate(sentences):
                local = [c for c in calls if s.start <= c.span.start and c.span.end <= s.end]
                if not local:
                    continue
                assigned.update(c.id for c in local)
                kind, skip, focal = "sentence", None, s
                if marker_only(p.text, s, local):
                    preceding = sentences[i - 1] if i else None
                    preceding_calls = [c for c in calls if preceding and preceding.start <= c.span.start < preceding.end]
                    if (preceding and not preceding_calls and not p.text[preceding.end:s.start].strip()
                            and len(groups(p.text, local)) == 1):
                        focal = TextSpan(start=preceding.start, end=s.end)
                        kind = "trailing_marker"
                    else:
                        skip = "UNRELIABLE_SENTENCE_SCOPE"
                focal_groups.append((focal, local, kind, skip, i))
            unassigned = [c for c in calls if c.id not in assigned]
            if unassigned:
                focal_groups.append((TextSpan(start=0, end=len(p.text)), unassigned,
                                     "paragraph_fallback", "UNRELIABLE_SENTENCE_SCOPE", None))
        for focal, local, kind, skip, index in sorted(focal_groups, key=lambda g: g[0].start):
            start, end = focal.start, focal.end
            if index is not None:
                if index > 0 and sentences[index - 1].start < start:
                    start = sentences[index - 1].start
                if index + 1 < len(sentences):
                    end = sentences[index + 1].end
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
            if not skip and not any(c.resolution_status == CitationResolutionStatus.RESOLVED for c in local):
                skip = ("SKIPPED_UNRESOLVED_CITATION" if all(c.resolution_status == CitationResolutionStatus.UNRESOLVED for c in local)
                        else "SKIPPED_PARTIAL_CITATION")
            notes = (diagnostic(skip, context.id),) if skip else ()
            if not sentences:
                notes += (diagnostic("MISSING_SENTENCE_BOUNDARIES", context.id, "info"),)
            plans.append(ContextPlan(context, notes, skip))
    if len(plans) > MAX_CONTEXTS:
        raise ExtractionInputError("EXTRACTION_CONTEXT_LIMIT", 413)
    return tuple(plans)
