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


def boundary_manuscript(first, second, markers=("8",), gap=" "):
    """Explicit occurrences, including bare superscript-like numeric surfaces."""
    text = first + gap + second if first else second
    spans = [(0, len(first)), (len(first) + len(gap), len(text))] if first else [(0, len(text))]
    calls, cursor = [], 0
    for i, marker in enumerate(markers):
        if marker.isdecimal():
            match = re.search(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", text[cursor:])
            assert match is not None
            start = cursor + match.start()
        else:
            start = text.index(marker, cursor)
        cursor = start + len(marker)
        calls.append(CitationCallout(id=f"callout:{i}", manuscript_id="m", paragraph_id="p", text=marker,
            span=TextSpan(start=start, end=cursor), order=i, resolution_status="resolved", reference_ids=(f"r{i}",)))
    return ParsedManuscript(manuscript=Manuscript(id="m", content_locator="test:memory"),
        paragraphs=(Paragraph(id="p", manuscript_id="m", text=text, order=0,
                              sentence_spans=tuple(TextSpan(start=a, end=b) for a, b in spans)),),
        references=tuple(Reference(id=f"r{i}", manuscript_id="m", raw_text=f"Fixture {marker}") for i, marker in enumerate(markers)),
        citation_callouts=tuple(calls))


@pytest.mark.parametrize("gap", ["", " ", "\n"])
def test_b1_leading_bare_marker_owned_by_previous_statement(gap):
    p = boundary_manuscript("A supports T-cell responses.", "8 B shows higher titers.", gap=gap)
    original = p.model_dump_json()
    plans = build_contexts(p)
    assert len(plans) == 1 and plans[0].skip_code is None
    c = plans[0].context
    assert c.scope_kind == "trailing_marker" and c.citation_callout_ids == ("callout:0",)
    assert c.focal_span == TextSpan(start=0, end=p.citation_callouts[0].span.end)
    assert "B shows" not in p.paragraphs[0].text[c.focal_span.start:c.focal_span.end]
    assert p.model_dump_json() == original


def test_b2_current_own_citation_and_trimmed_focal():
    p = boundary_manuscript("A supports T-cell responses.", "8 B shows higher titers [9].", ("8", "[9]"))
    plans = build_contexts(p)
    assert [x.context.citation_callout_ids for x in plans] == [("callout:0",), ("callout:1",)]
    assert plans[0].context.scope_kind == "trailing_marker" and plans[1].context.scope_kind == "sentence"
    c = plans[1].context
    assert p.paragraphs[0].text[c.focal_span.start:c.focal_span.end] == "B shows higher titers [9]."
    assert c.focal_span.start > p.citation_callouts[0].span.end


@pytest.mark.parametrize("surface", ["8,9", "8 9", "8, 9"])
def test_b3_leading_group_is_one_ownership_unit(surface):
    p = boundary_manuscript("A supports T-cell responses.", surface + " B shows higher titers.", ("8", "9"))
    plans = build_contexts(p)
    assert len(plans) == 1 and plans[0].context.citation_callout_ids == ("callout:0", "callout:1")
    assert plans[0].context.focal_span.end == p.citation_callouts[1].span.end


def test_b4_standalone_trailing_attachment_still_exact():
    p = boundary_manuscript("A improves accuracy.", "[3]", ("[3]",))
    plan = build_contexts(p)[0]
    assert plan.skip_code is None and plan.context.scope_kind == "trailing_marker"
    assert plan.context.focal_span == TextSpan(start=0, end=len(p.paragraphs[0].text))


@pytest.mark.parametrize("marker", ["8", "[8]"])
def test_b5_prefix_without_previous_never_creates_previous(marker):
    p = boundary_manuscript("", marker + " A improves accuracy.", (marker,))
    plans = build_contexts(p)
    assert len(plans) == 1 and plans[0].context.scope_kind == "sentence"
    assert plans[0].context.focal_span.start == 0


@pytest.mark.parametrize("first,marker", [("Background sentence.", "8"), ("Background provides useful context.", "[8]")])
def test_b6_ambiguous_prefix_abstains(first, marker):
    p = boundary_manuscript(first, marker + " A improves accuracy.", (marker,))
    plan = build_contexts(p)[0]
    assert plan.skip_code == "AMBIGUOUS_BOUNDARY_CITATION"
    assert plan.context.scope_kind == "sentence" and plan.context.focal_span.start == len(first) + 1


def test_b7_terminal_citation_conflict_does_not_union():
    p = boundary_manuscript("A improves accuracy [3].", "8 B reduces latency.", ("[3]", "8"))
    plans = build_contexts(p)
    assert [x.context.citation_callout_ids for x in plans] == [("callout:0",), ("callout:1",)]
    assert plans[0].skip_code is None and plans[1].skip_code == "AMBIGUOUS_BOUNDARY_CITATION"
    assert all(len(x.context.citation_callout_ids) == 1 for x in plans)


def test_b8_ownership_unique_and_order_stable_when_merging_inline_context():
    p = boundary_manuscript("Smith [3] reports improved accuracy.", "8 B shows higher titers [9].", ("[3]", "8", "[9]"))
    plans = build_contexts(p)
    assert plans == build_contexts(p)
    assert [x.context.citation_callout_ids for x in plans] == [("callout:0", "callout:1"), ("callout:2",)]
    memberships = [cid for plan in plans for cid in plan.context.citation_callout_ids]
    assert len(memberships) == len(set(memberships)) == len(p.citation_callouts)
    assert plans[0].context.focal_span.end <= plans[1].context.focal_span.start


def test_b10_nejm_boundary_literals_move_seven_and_eight_together():
    first = "The spike is locked in the prefusion conformation."
    second = "7 Findings elicited robust CD8+ and Th1-type CD4+ T-cell responses."
    third = "8 The 50% neutralizing geometric mean titers exceeded the comparison panel."
    p = boundary_manuscript(first, second + " " + third, ("7", "8"))
    text = p.paragraphs[0].text
    a, b = len(first) + 1, len(first) + 1 + len(second)
    paragraph = p.paragraphs[0].model_copy(update={"sentence_spans": (TextSpan(start=0, end=len(first)), TextSpan(start=a, end=b), TextSpan(start=b+1, end=len(text)))})
    p = p.model_copy(update={"paragraphs": (paragraph,)})
    plans = build_contexts(p)
    assert len(plans) == 2
    assert [plan.context.citation_callout_ids for plan in plans] == [("callout:0",), ("callout:1",)]
    assert all(plan.context.scope_kind == "trailing_marker" for plan in plans)
    assert plans[1].context.focal_span.start > p.citation_callouts[0].span.end
    assert "The 50%" not in text[plans[1].context.focal_span.start:plans[1].context.focal_span.end]


@pytest.mark.parametrize("first,second", [("An introductory label:", "8 A improves accuracy."), ("A supports T-cell responses.", "8,A improves accuracy.")])
def test_weak_boundary_evidence_never_attaches(first, second):
    plan = build_contexts(boundary_manuscript(first, second))[0]
    assert plan.skip_code == "AMBIGUOUS_BOUNDARY_CITATION"
