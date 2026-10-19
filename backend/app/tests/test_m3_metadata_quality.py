"""Structural metadata policies; real TEI replay needs no PDF or public API."""
import json
from pathlib import Path

import pytest

from app.researchguard.adapters.grobid_tei import parse_tei
from app.researchguard.domain import ParsedManuscript
from app.services.citation_context import validate_input
from app.tests.test_grobid_tei import MANUSCRIPT, codes, tei
from app.utils.doi import normalize_doi

LIVE = Path(__file__).resolve().parents[3] / "docs/e2e-main-20261019-live"


def document(header):
    return ('<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc>'
            + header + '</fileDesc></teiHeader><text><body><p>Body prose.</p></body></text></TEI>').encode()


def title_metadata(candidate, article=None, container=None, level="a"):
    return (f'<titleStmt><title level="{level}" type="main">{candidate}</title></titleStmt>'
            '<sourceDesc><biblStruct><analytic>'
            + (f'<title level="a">{article}</title>' if article else '')
            + '</analytic><monogr>'
            + (f'<title level="j">{container}</title>' if container else '')
            + '</monogr></biblStruct></sourceDesc>')


def test_reliable_article_title_kept_and_subtitle_not_mistaken_for_conflict():
    xml = document(title_metadata("A reliable study", "A reliable study", "A journal").replace(
        '</titleStmt>', '<title type="sub">A subtitle</title></titleStmt>'))
    parsed = parse_tei(xml, MANUSCRIPT)
    assert parsed.manuscript.title == "A reliable study"
    assert not any(d.code.startswith("MANUSCRIPT_TITLE_") for d in parsed.diagnostics)


@pytest.mark.parametrize("container", ["A Journal", "a journal", " A   Journal "])
def test_container_collision_rejected_without_journal_name_list(container):
    parsed = parse_tei(document(title_metadata("A Journal", "A Journal", container)), MANUSCRIPT)
    assert parsed.manuscript.title is None
    assert "MANUSCRIPT_TITLE_CONTAINER_CONFLICT" in codes(parsed)


def test_conflicting_container_candidate_recovers_only_separate_article_title():
    parsed = parse_tei(document(title_metadata("A Journal", "A reliable study", "A Journal")), MANUSCRIPT)
    assert parsed.manuscript.title == "A reliable study"
    assert "MANUSCRIPT_TITLE_CONTAINER_CONFLICT" in codes(parsed)


def test_explicit_container_role_without_replacement_abstains():
    parsed = parse_tei(document(title_metadata("Container", level="j")), MANUSCRIPT)
    assert parsed.manuscript.title is None
    assert "MANUSCRIPT_TITLE_CONTAINER_CONFLICT" in codes(parsed)


def test_two_disagreeing_article_candidates_abstain_instead_of_guessing():
    parsed = parse_tei(document(title_metadata("One article", "Another article", "A journal")), MANUSCRIPT)
    assert parsed.manuscript.title is None
    assert "MANUSCRIPT_TITLE_CONFLICT" in codes(parsed)


def test_incomplete_header_preserves_candidate_but_marks_unverified():
    parsed = parse_tei(document(title_metadata("Unverifiable candidate", "Unverifiable candidate")), MANUSCRIPT)
    assert parsed.manuscript.title == "Unverifiable candidate"
    assert "MANUSCRIPT_TITLE_UNVERIFIED" in codes(parsed)


def parse_identifier(identifier, url=None):
    from xml.sax.saxutils import escape, quoteattr
    entry = ('<listBibl><biblStruct><monogr><title>Source</title></monogr>'
             '<idno type="DOI">' + escape(identifier) + '</idno>'
             + ('<ptr target=' + quoteattr(url) + '/>' if url else '')
             + '</biblStruct></listBibl>')
    return parse_tei(tei('<p>Prose.</p>', entry), MANUSCRIPT)


@pytest.mark.parametrize("suffix", ["asset.pdf", "data.zip", "table.csv", "appendix.docx"])
def test_nested_file_url_path_is_not_accepted_as_identifier(suffix):
    candidate = "10.1234/work/extra/" + suffix
    url = "https://publisher.example/download/" + candidate
    parsed = parse_identifier(candidate, url)
    assert parsed.references[0].doi is None
    assert parsed.references[0].url == url
    assert "REFERENCE_DOI_RESOURCE_PATH" in codes(parsed)
    assert "10.1234/work" != parsed.references[0].doi  # Never infer a parent.


@pytest.mark.parametrize("doi", ["10.1234/a/b.c", "10.1234/suppl_file/item.pdf",
    "10.1234/report.pdf", "10.1234/(sici)001<2:3::aid>4.0.co;2-x"])
def test_valid_complex_bare_identifiers_are_not_blacklisted(doi):
    assert parse_identifier(doi).references[0].doi == normalize_doi(doi)


@pytest.mark.parametrize("identifier,url", [
    ("10.1234/a/b.c", "https://publisher.example/article/10.1234/a/b.c"),
    ("10.1234/report.pdf", "https://publisher.example/article/10.1234/report.pdf"),
    ("10.1234/work", "https://publisher.example/10.1234/work/extra/data.pdf"),
    ("https://doi.org/10.1234/work/data.pdf", "https://publisher.example/10.1234/work/data.pdf"),
    ("10.1234/work/data.pdf", "https://doi.org/10.1234/work/data.pdf"),
])
def test_identifier_is_not_replaced_by_resource_or_resolver_url(identifier, url):
    assert parse_identifier(identifier, url).references[0].doi == normalize_doi(identifier)


def test_publisher_url_mislabelled_as_doi_stays_url_without_parent_identifier():
    url = "https://publisher.example/10.1234/work/assets/item.pdf"
    parsed = parse_identifier(url)
    assert parsed.references[0].doi is None and parsed.references[0].url == url
    assert "MISSING_REFERENCE_METADATA" in codes(parsed)


def test_real_tei_only_metadata_changes_and_graph_offsets_unchanged():
    payload = json.loads((LIVE / "parse-response.json").read_text(encoding="utf-8"))["parsed"]
    payload["manuscript"]["content_locator"] = "replay:committed-parse-response"
    saved = ParsedManuscript.model_validate(payload)
    parsed = parse_tei((LIVE / "grobid-original.tei.xml").read_bytes(), saved.manuscript)
    validate_input(parsed)
    assert parsed.paragraphs == saved.paragraphs
    assert parsed.citation_callouts == saved.citation_callouts
    assert len(parsed.references) == len(saved.references) == 15
    assert parsed.manuscript.title == saved.manuscript.title  # TEI cannot prove it is a journal.
    assert "MANUSCRIPT_TITLE_UNVERIFIED" in codes(parsed)
    assert "REFERENCE_DOI_RESOURCE_PATH" in codes(parsed)
    for old, new in zip(saved.references, parsed.references):
        assert old.id == new.id and old.raw_text == new.raw_text and old.url == new.url
        if old.id == saved.references[4].id:
            assert new.doi is None and new.url.endswith(".pdf")
        else:
            assert old == new
    assert ParsedManuscript.model_validate_json(parsed.model_dump_json()) == parsed
