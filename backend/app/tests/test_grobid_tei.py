from pathlib import Path

import pytest
from pydantic import ValidationError

from app.researchguard.adapters.grobid_tei import MAX_DEPTH, parse_tei
from app.researchguard.domain import Manuscript, ParsedManuscript, TextSpan
from app.services.manuscript_errors import ManuscriptParseError

FIXTURE = Path(__file__).parent / "fixtures/manuscript.tei.xml"
MANUSCRIPT = Manuscript(id="m1", content_locator="memory:m1", content_hash="sha256:test")


def tei(body, back=""):
    return ('<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>' + body +
            '</body><back>' + back + '</back></text></TEI>').encode()


def bibliography(*entries):
    return "<listBibl>" + "".join('<biblStruct xml:id="' + identifier + '"><monogr><title>' + title +
        '</title></monogr></biblStruct>' for identifier, title in entries) + "</listBibl>"


def codes(parsed):
    return {d.code for d in parsed.diagnostics}


def test_namespace_document_order_nested_sections_exclusions_and_mixed_text():
    parsed = parse_tei(FIXTURE.read_bytes(), MANUSCRIPT)
    assert [p.order for p in parsed.paragraphs] == [0, 1, 2]
    assert [p.section for p in parsed.paragraphs] == ["Introduction", "Prior work", "Introduction"]
    assert parsed.paragraphs[0].text == "A & B 😊 improve accuracy [3]. B reduces latency [3]."
    assert parsed.paragraphs[1].text == "Joint evidence [3–5] is cited."
    assert parsed.paragraphs[2].text == "Unsegmented prose with Fig. 1."
    assert parsed.manuscript.title == "Offline manuscript fixture"
    assert len(parsed.citation_callouts) == 3
    assert parsed.citation_contexts == ()


def test_metadata_raw_reference_monogr_fallback_duplicate_doi_identity():
    parsed = parse_tei(FIXTURE.read_bytes(), MANUSCRIPT)
    first, second = parsed.references
    assert first.title == "Accuracy study"
    assert first.authors == ("Ada Lovelace",)
    assert first.year == 2020 and first.journal == "Example Journal"
    assert first.doi == second.doi == "10.1234/shared"
    assert first.id != second.id
    assert first.raw_text == "Lovelace A. Accuracy study. Example Journal. 2020."
    assert second.title == "Latency book" and second.authors == ("Grace Hopper",)
    assert second.year == 2021 and second.journal is None
    assert any(d.code == "RECONSTRUCTED_REFERENCE_TEXT" and d.entity_id == second.id for d in parsed.diagnostics)


def test_repeat_markers_unicode_sentence_spans_and_exact_slices():
    parsed = parse_tei(FIXTURE.read_bytes(), MANUSCRIPT)
    p = parsed.paragraphs[0]
    first, second = parsed.citation_callouts[:2]
    assert (first.span.start, first.span.end) == (25, 28)
    assert (second.span.start, second.span.end) == (48, 51)
    assert first.span != second.span and first.text == second.text == "[3]"
    assert [p.text[s.start:s.end] for s in p.sentence_spans] == [
        "A & B 😊 improve accuracy [3].", "B reduces latency [3]."]
    for callout in parsed.citation_callouts:
        paragraph = next(p for p in parsed.paragraphs if p.id == callout.paragraph_id)
        assert paragraph.text[callout.span.start:callout.span.end] == callout.text


def test_multiple_targets_explicit_range_mapping_and_adjacent_ref():
    xml = tei('<p>Evidence <ref type="bibr" target="#b12 #b13 #b12">[3–5]</ref>, '
              '<ref type="bibr" target="#b13">[5]</ref>.</p>', bibliography(("b12", "One"), ("b13", "Two")))
    parsed = parse_tei(xml, MANUSCRIPT)
    assert len(parsed.references) == 2 and len(parsed.citation_callouts) == 2
    assert parsed.citation_callouts[0].reference_ids == tuple(r.id for r in parsed.references)
    assert parsed.citation_callouts[1].reference_ids == (parsed.references[1].id,)
    assert all(c.resolution_status == "resolved" for c in parsed.citation_callouts)


@pytest.mark.parametrize("target,expected,code", [
    ("", "unresolved", "UNRESOLVED_REFERENCE_TARGET"),
    ('target="#unknown"', "unresolved", "UNRESOLVED_REFERENCE_TARGET"),
    ('target="#b1 #unknown"', "partial", "PARTIAL_REFERENCE_TARGET"),
    ('target="https://untrusted.invalid/#b1"', "unresolved", "UNRESOLVED_REFERENCE_TARGET"),
])
def test_missing_unknown_partial_external_targets(target, expected, code):
    parsed = parse_tei(tei('<p>Claim <ref type="bibr" ' + target + '>[1]</ref>.</p>', bibliography(("b1", "Title"))), MANUSCRIPT)
    callout = parsed.citation_callouts[0]
    assert callout.resolution_status == expected and code in codes(parsed)
    assert len(callout.reference_ids) == (1 if expected == "partial" else 0)
    assert len(parsed.references) == 1


def test_duplicate_parser_target_is_ambiguous_not_last_write_wins():
    parsed = parse_tei(tei('<p>Claim <ref type="bibr" target="#same">[1]</ref>.</p>',
                          bibliography(("same", "One"), ("same", "Two"))), MANUSCRIPT)
    assert len(parsed.references) == 2 and parsed.references[0].id != parsed.references[1].id
    assert parsed.citation_callouts[0].reference_ids == ()
    assert "DUPLICATE_REFERENCE_TARGET" in codes(parsed)


def test_missing_metadata_no_doi_retained_and_empty_entry_diagnosed():
    parsed = parse_tei(tei('<p>Prose.</p>', '<listBibl><biblStruct xml:id="empty"/>'
        '<biblStruct xml:id="raw"><note type="raw_reference">Unstructured reference.</note></biblStruct></listBibl>'), MANUSCRIPT)
    assert len(parsed.references) == 1
    assert parsed.references[0].doi is None and parsed.references[0].title is None
    assert parsed.references[0].id.endswith(":1")  # Physical bibliography order survives omitted empty entry.
    assert "MISSING_REFERENCE_METADATA" in codes(parsed)


def test_no_reference_or_callout_and_no_sentence_segmentation():
    parsed = parse_tei(tei('<div><p>Plain paragraph.</p></div>'), MANUSCRIPT)
    assert parsed.references == () and parsed.citation_callouts == ()
    assert parsed.paragraphs[0].sentence_spans == ()
    assert {"NO_REFERENCES", "NO_CITATION_CALLOUTS", "MISSING_SENTENCE_BOUNDARIES"} <= codes(parsed)


@pytest.mark.parametrize("body", ['<p><s>First.</s> Unsegmented tail.</p>',
                                   '<p><s>Outer <s>nested.</s></s></p>'])
def test_unreliable_sentence_boundaries_are_empty(body):
    assert parse_tei(tei(body), MANUSCRIPT).paragraphs[0].sentence_spans == ()


def test_leading_trailing_whitespace_marker_and_nested_inline_tail():
    parsed = parse_tei(tei('<p>   <s>Text <hi>with <ref type="bibr"> [1] </ref> tail</hi>.</s>   </p>'), MANUSCRIPT)
    p, c = parsed.paragraphs[0], parsed.citation_callouts[0]
    assert p.text == "Text with [1] tail."
    assert p.text[c.span.start:c.span.end] == c.text == "[1]"
    assert p.sentence_spans[0] == TextSpan(start=0, end=len(p.text))


@pytest.mark.parametrize("xml", [b"<TEI>", b"<html/>", b'<TEI><text><body><p>No namespace</p></body></text></TEI>',
    b'<?xml version="1.0" encoding="unknown-encoding"?><TEI/>',
    b'<!DOCTYPE TEI SYSTEM "http://example.invalid/external"><TEI xmlns="http://www.tei-c.org/ns/1.0"/>',
    b'<!DOCTYPE TEI [<!ENTITY x SYSTEM "file:///secret">]><TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><p>&x;</p></body></text></TEI>',
    b'<!DOCTYPE TEI [<!ENTITY x "expanded">]><TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><p>&x;</p></body></text></TEI>',
])
def test_malformed_unsupported_and_unsafe_xml_are_safe_failures(xml):
    with pytest.raises(ManuscriptParseError) as error:
        parse_tei(xml, MANUSCRIPT)
    assert error.value.code == "MALFORMED_TEI" and error.value.status_code == 502


def test_xml_depth_limit_and_missing_body():
    with pytest.raises(ManuscriptParseError, match="complex"):
        parse_tei(tei("<div>" * MAX_DEPTH + "<p>Prose.</p>" + "</div>" * MAX_DEPTH), MANUSCRIPT)
    with pytest.raises(ManuscriptParseError) as error:
        parse_tei(tei(""), MANUSCRIPT)
    assert error.value.code == "MANUSCRIPT_PARSE_FAILED" and error.value.status_code == 422


@pytest.mark.parametrize("start,end", [(True, 2), (0, False), ("0", 2), (0, 1.5), (-1, 2), (2, 2), (3, 2)])
def test_strict_span(start, end):
    with pytest.raises(ValidationError):
        TextSpan(start=start, end=end)


def test_aggregate_rejects_span_or_resolution_corruption_and_roundtrip_stable_ids():
    parsed = parse_tei(FIXTURE.read_bytes(), MANUSCRIPT)
    assert parse_tei(FIXTURE.read_bytes(), MANUSCRIPT) == parsed
    assert ParsedManuscript.model_validate_json(parsed.model_dump_json()) == parsed
    payload = parsed.model_dump()
    payload["citation_callouts"][0]["span"] = {"start": 0, "end": 3}
    with pytest.raises(ValidationError, match="exactly slice"):
        ParsedManuscript.model_validate(payload)
    payload = parsed.model_dump()
    payload["citation_callouts"][0]["resolution_status"] = "unresolved"
    with pytest.raises(ValidationError, match="resolution status"):
        ParsedManuscript.model_validate(payload)


def test_invalid_doi_preserves_entry_without_fake_identifier():
    xml = tei('<p>Prose.</p>', '<listBibl><biblStruct><monogr><title>Title</title></monogr><idno type="DOI">bad</idno></biblStruct></listBibl>')
    parsed = parse_tei(xml, MANUSCRIPT)
    assert parsed.references[0].doi is None and "MISSING_REFERENCE_METADATA" in codes(parsed)


def test_node_limit_and_inline_non_prose_content_are_handled(monkeypatch):
    from app.researchguard.adapters import grobid_tei
    parsed = parse_tei(tei('<p>Before <note>private footnote<ref type="bibr">[8]</ref></note>'
                           'after <formula>E=mc2</formula> prose.</p>'), MANUSCRIPT)
    assert parsed.paragraphs[0].text == "Before after prose."
    assert parsed.citation_callouts == ()
    monkeypatch.setattr(grobid_tei, "MAX_NODES", 3)
    with pytest.raises(ManuscriptParseError, match="complex"):
        parse_tei(tei('<p>Prose.</p>'), MANUSCRIPT)
