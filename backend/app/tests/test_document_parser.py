from __future__ import annotations

import pytest

from app.services.document_parser import DocumentParseError, parse_document, parse_html
from app.utils.text_cleaner import clean_text


SAMPLE_HTML = """
<html>
  <body>
    <h1>Abstract</h1>
    <p>This study reports a 42.5% increase in sample size (n=120).</p>
    <h2>Introduction</h2>
    <p>Background information about the topic.</p>
    <h2>Custom Section</h2>
    <p>Unknown but useful section content.</p>
  </body>
</html>
"""

SAMPLE_PMC_HTML = """
<html>
  <head><meta name="ncbi_db" content="pmc"></head>
  <body>
    <div id="ncbi-header">Search NCBI Primary site navigation</div>
    <div id="mc">
      <h2>Abstract</h2>
      <p>Cas9 can be directed by RNA to cleave double-stranded DNA target sequences.</p>
      <h2>PERMALINK</h2>
      <p>Permalink page controls should be ignored.</p>
      <h2>Results</h2>
      <p>Cas9 can be directed by RNA to cleave double-stranded DNA target sequences.</p>
      <div><p>Cas9 can be directed by RNA to cleave double-stranded DNA target sequences.</p></div>
    </div>
  </body>
</html>
"""


class TestDocumentParser:
    def test_simple_html_sections(self) -> None:
        sections = parse_html(SAMPLE_HTML)

        assert len(sections) >= 3
        assert sections[0].section_name.lower() == "abstract"
        assert "42.5%" in sections[0].text
        assert any(section.section_name == "Custom Section" for section in sections)

    def test_malformed_html_fallback(self) -> None:
        sections = parse_html("<html><body><p>Only paragraph</p></body>")
        assert len(sections) == 1
        assert "Only paragraph" in sections[0].text

    def test_missing_sections(self) -> None:
        html = "<html><body><p>Solo paragraph without headings.</p></body></html>"
        sections = parse_html(html)
        assert len(sections) == 1
        assert sections[0].section_name == "Body"

    def test_pdf_without_extractable_text(self) -> None:
        with pytest.raises(DocumentParseError) as exc_info:
            parse_document(b"not-a-pdf", "pdf")
        assert exc_info.value.reason == "pdf_read_error"

    def test_pdf_empty_content(self) -> None:
        with pytest.raises(DocumentParseError) as exc_info:
            parse_document(b"", "pdf")
        assert exc_info.value.reason == "pdf_empty"

    def test_pdf_no_text_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakePage:
            def extract_text(self) -> str:
                return "   "

        class FakeReader:
            def __init__(self, _stream: object) -> None:
                self.pages = [FakePage()]

        monkeypatch.setattr("app.services.document_parser.PdfReader", FakeReader)

        with pytest.raises(DocumentParseError) as exc_info:
            parse_document(b"%PDF-1.4", "pdf")
        assert exc_info.value.reason == "pdf_no_text"
        assert "no extractable text" in exc_info.value.message

    def test_unsupported_format(self) -> None:
        with pytest.raises(DocumentParseError) as exc_info:
            parse_document(b"abc", "xml")  # type: ignore[arg-type]
        assert exc_info.value.reason == "unsupported_format"

    def test_html_empty_content(self) -> None:
        with pytest.raises(DocumentParseError) as exc_info:
            parse_html("   ")
        assert exc_info.value.reason == "html_empty"

    def test_pmc_html_excludes_navigation_and_permalink(self) -> None:
        sections = parse_html(SAMPLE_PMC_HTML)

        combined = "\n".join(section.text for section in sections)
        assert "Cas9 can be directed by RNA" in combined
        assert "Search NCBI" not in combined
        assert "Permalink page controls" not in combined
        assert all(section.section_name != "PERMALINK" for section in sections)

    def test_pmc_html_deduplicates_repeated_article_text(self) -> None:
        sections = parse_html(SAMPLE_PMC_HTML)
        abstract_sections = [section for section in sections if section.section_name == "Abstract"]
        results_sections = [section for section in sections if section.section_name == "Results"]

        assert len(abstract_sections) == 1
        assert len(results_sections) == 1


class TestTextCleaning:
    def test_excessive_whitespace(self) -> None:
        cleaned = clean_text("Line 1\n\n\n\nLine 2")
        assert cleaned == "Line 1\n\nLine 2"

    def test_preserve_scientific_numbers(self) -> None:
        cleaned = clean_text("The value was 3.14 mg/L at 25°C.")
        assert "3.14 mg/L" in cleaned
        assert "25°C" in cleaned

    def test_repeated_line_breaks(self) -> None:
        cleaned = clean_text("Alpha\n\n\nBeta")
        assert cleaned == "Alpha\n\nBeta"

    def test_preserved_paragraphs(self) -> None:
        cleaned = clean_text("First paragraph.\n\nSecond paragraph.")
        assert "First paragraph." in cleaned
        assert "Second paragraph." in cleaned


class TestPdfParsingWithMock:
    def test_simple_pdf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakePage:
            def extract_text(self) -> str:
                return "Abstract\nFindings show a 10% effect.\n\nIntroduction\nMore text."

        class FakeReader:
            def __init__(self, _stream: object) -> None:
                self.pages = [FakePage()]

        monkeypatch.setattr("app.services.document_parser.PdfReader", FakeReader)

        sections = parse_document(b"%PDF", "pdf")
        assert len(sections) >= 1
        assert any("10%" in section.text for section in sections)
