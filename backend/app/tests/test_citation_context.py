"""M3B deterministic input/context fixtures; no PDF, provider or tokenizer."""
import re

import pytest
from pydantic import ValidationError

from app.researchguard.domain import CitationCallout, Manuscript, Paragraph, ParsedManuscript, Reference, TextSpan
from app.schemas.claim_extraction import ClaimExtractionRequest
from app.services.citation_context import ExtractionInputError, build_contexts, from_request, validate_input


def manuscript(text="A improves accuracy [3].", sentences=None, targets=None, statuses=None):
    markers = list(re.finditer(r"\[\d+(?:[,–-]\d+)*\]", text))
    calls, ids = [], []
    for i, m in enumerate(markers):
        refs = tuple((targets or {}).get(m.group(), ["r" + n for n in re.findall(r"\d+", m.group())]))
        status = (statuses or {}).get(i, "resolved")
        if status == "unresolved":
            refs = ()
        ids.extend(refs)
        calls.append(CitationCallout(id=f"callout:{i}", manuscript_id="m", paragraph_id="p",
            text=m.group(), reference_ids=refs, span=TextSpan(start=m.start(), end=m.end()), order=i,
            resolution_status=status))
    spans = (TextSpan(start=0, end=len(text)),) if sentences is None else tuple(TextSpan(start=a, end=b) for a, b in sentences)
    return ParsedManuscript(manuscript=Manuscript(id="m", content_locator="test:memory"),
        paragraphs=(Paragraph(id="p", manuscript_id="m", text=text, order=0, sentence_spans=spans),),
        references=tuple(Reference(id=i, manuscript_id="m", raw_text=f"Fixture {i}") for i in dict.fromkeys(ids)),
        citation_callouts=tuple(calls))


def request_payload(parsed):
    body = parsed.model_dump(mode="json")
    body["manuscript"].pop("content_locator")
    body.pop("diagnostics")
    return {"schema_version": 1, "scope": "body_prose", "offset_unit": "python_unicode_code_point", "parsed": body}


def test_one_sentence_one_context_many_occurrences_stable():
    p = manuscript("A improves accuracy [3], while B reduces latency [4].")
    plans = build_contexts(p)
    assert len(plans) == 1 and plans == build_contexts(p)
    assert plans[0].context.citation_callout_ids == ("callout:0", "callout:1")
    assert plans[0].skip_code is None


def test_neighbors_read_only_and_contexts_in_document_order():
    first = "A improves accuracy [3]."
    text = first + " B reduces latency [4]."
    p = manuscript(text, [(0, len(first)), (len(first) + 1, len(text))])
    plans = build_contexts(p)
    assert len(plans) == 2
    assert [x.context.citation_callout_ids for x in plans] == [("callout:0",), ("callout:1",)]
    assert all(x.context.text == text for x in plans)
    assert plans[0].context.focal_span.end == len(first)


@pytest.mark.parametrize("text", ["Copyright 2020.", "Downloaded from journal.", "Cumulative Incidence (%)"])
def test_citation_free_noise_no_context(text):
    assert build_contexts(manuscript(text)) == ()


def test_single_group_paragraph_fallback():
    p = manuscript("A improves accuracy [3][4].", sentences=[])
    plan = build_contexts(p)[0]
    assert plan.context.scope_kind == "paragraph_fallback" and plan.skip_code is None


def test_multiple_group_fallback_abstains():
    plan = build_contexts(manuscript("A improves accuracy [3]. B reduces latency [4].", sentences=[]))[0]
    assert plan.skip_code == "UNRELIABLE_SENTENCE_SCOPE"


@pytest.mark.parametrize("segmented_tail", [True, False])
def test_explicit_trailing_marker(segmented_tail):
    text = "A improves accuracy. [3]"
    sentence = (0, 20)
    spans = [sentence, (21, len(text))] if segmented_tail else [sentence]
    plan = build_contexts(manuscript(text, spans))[0]
    assert plan.context.scope_kind == "trailing_marker" and plan.skip_code is None
    assert plan.context.focal_span == TextSpan(start=0, end=len(text))


def test_marker_attachment_with_prior_citation_abstains():
    first = "A improves accuracy [3]."
    text = first + " [4]"
    plans = build_contexts(manuscript(text, [(0, len(first)), (len(first) + 1, len(text))]))
    assert plans[1].skip_code == "UNRELIABLE_SENTENCE_SCOPE"


@pytest.mark.parametrize("status,code", [("unresolved", "SKIPPED_UNRESOLVED_CITATION"), ("partial", "SKIPPED_PARTIAL_CITATION")])
def test_ineligible_context_retained(status, code):
    plan = build_contexts(manuscript(statuses={0: status}))[0]
    assert plan.skip_code == code and plan.context.citation_callout_ids


def test_budget_removes_neighbors_not_focal():
    previous, focal, following = "x" * 1700 + ".", "A improves accuracy [3].", "y" * 1700 + "."
    text = " ".join([previous, focal, following])
    a, b = len(previous) + 1, len(previous) + 1 + len(focal)
    plan = build_contexts(manuscript(text, [(0, len(previous)), (a, b), (b + 1, len(text))]))[0]
    assert plan.context.span.start == a and plan.context.focal_span == TextSpan(start=a, end=b)
    assert focal in plan.context.text and plan.skip_code is None


def test_oversize_focal_skipped_without_truncation():
    p = manuscript("A " + "x" * 2100 + " [3].")
    plan = build_contexts(p)[0]
    assert plan.skip_code == "CONTEXT_TOO_LARGE" and plan.context.text == p.paragraphs[0].text


def test_incomplete_coverage_multigroup_skips():
    first = "A improves accuracy [3]."
    text = first + " B reduces latency [4]."
    assert build_contexts(manuscript(text, [(0, len(first))]))[0].skip_code == "UNRELIABLE_SENTENCE_SCOPE"


def test_callout_crosses_sentence_boundary_skipped():
    p = manuscript(sentences=[(0, 21), (21, 24)])
    assert build_contexts(p)[0].skip_code == "UNRELIABLE_SENTENCE_SCOPE"


@pytest.mark.parametrize("corruption", ["unknown_reference", "overlap", "missing_order", "order_gap", "wrong_slice"])
def test_service_revalidates_copied_graph(corruption):
    p = manuscript("A improves accuracy [3][4].")
    calls = list(p.citation_callouts)
    updates = {"unknown_reference": {"reference_ids": ("unknown",)},
               "overlap": {"span": calls[0].span, "text": calls[0].text},
               "missing_order": {"order": None}, "order_gap": {"order": 9}, "wrong_slice": {"text": "[9]"}}
    calls[1] = calls[1].model_copy(update=updates[corruption])
    with pytest.raises(ExtractionInputError):
        validate_input(p.model_copy(update={"citation_callouts": tuple(calls)}))


@pytest.mark.parametrize("field", ["span", "order", "resolution_status"])
def test_http_input_requires_explicit_occurrence_fields(field):
    data = request_payload(manuscript())
    del data["parsed"]["citation_callouts"][0][field]
    with pytest.raises(ValidationError):
        ClaimExtractionRequest.model_validate(data)


def test_input_roundtrip_graph_validated_and_locator_internal():
    p = from_request(ClaimExtractionRequest.model_validate(request_payload(manuscript())))
    assert p.manuscript.content_locator == "submitted:client-structure"
    data = request_payload(manuscript())
    data["parsed"]["citation_callouts"][0]["reference_ids"] = ["unknown"]
    with pytest.raises(ExtractionInputError):
        from_request(ClaimExtractionRequest.model_validate(data))


@pytest.mark.parametrize("corruption", ["manuscript_id", "paragraph_id", "duplicate_id", "negative_span", "out_of_bounds", "unordered_sentences", "noncanonical_id", "resolution_mismatch"])
def test_additional_untrusted_graph_corruption(corruption):
    data = request_payload(manuscript())
    p = data["parsed"]
    if corruption == "manuscript_id":
        p["references"][0]["manuscript_id"] = "other"
    elif corruption == "paragraph_id":
        p["citation_callouts"][0]["paragraph_id"] = "missing"
    elif corruption == "duplicate_id":
        p["paragraphs"] *= 2
    elif corruption == "negative_span":
        p["citation_callouts"][0]["span"]["start"] = -1
    elif corruption == "out_of_bounds":
        p["paragraphs"][0]["sentence_spans"][0]["end"] = 999
    elif corruption == "unordered_sentences":
        p["paragraphs"][0]["sentence_spans"] = [{"start": 10, "end": 20}, {"start": 0, "end": 5}]
    elif corruption == "noncanonical_id":
        p["references"][0]["id"] = " r3 "
    else:
        p["citation_callouts"][0]["resolution_status"] = "unresolved"
    with pytest.raises((ValidationError, ExtractionInputError)):
        from_request(ClaimExtractionRequest.model_validate(data))


def test_unicode_code_points_not_utf8_bytes():
    text = "方法 😀 improves accuracy [3]."
    p = from_request(ClaimExtractionRequest.model_validate(request_payload(manuscript(text))))
    call = p.citation_callouts[0]
    assert call.span.start == text.index("[3]")
    assert call.span.start != len(text[:call.span.start].encode("utf-8"))
    assert build_contexts(p)[0].context.text == text
