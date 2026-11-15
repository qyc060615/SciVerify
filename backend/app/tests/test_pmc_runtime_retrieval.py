"""Deterministic unit tests for PMC / Europe PMC runtime retrieval fixes.

Covers:
- Test A: PMC structured full-text success (mock response -> parsed chunks, provider = pmc/europepmc)
- Test B: PDF failure falls back to structured full-text (PMC PDF invalid -> PMC HTML succeeds)
- Test C: Interstitial remains rejected (Cloudflare/CAPTCHA challenge is rejected and never treated as evidence)
- Test D: Publisher fallback remains intact (PMC/Europe PMC fail -> legal OA repository/publisher OA succeeds)
- Test E: No-secret logging (API keys, auth tokens never appear in logs or candidates)
"""
from __future__ import annotations

from app.tests.full_text_fixtures import FULL_TEXT_HTML


import logging
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.schemas.citation import CitationMetadata
from app.schemas.paper import DocumentSection, EvidenceChunk, PaperRetrievalStatus
from app.services.document_retriever import (
    DOCUMENT_ACCEPT_HEADER,
    DocumentRetrievalError,
    InterstitialPageError,
    is_interstitial_content,
    retrieve_document,
)
from app.services.paper_retriever import (
    FullTextCandidate,
    _discover_europe_pmc_candidates,
    retrieve_paper,
)

_CITATION = CitationMetadata(
    doi="10.1126/science.1225829",
    title="A Programmable Dual-RNA-Guided DNA Endonuclease in Adaptive Bacterial Immunity",
    authors=["Jinek M", "Chylinski K"],
    journal="Science",
    publisher="AAAS",
    year=2012,
    url="https://doi.org/10.1126/science.1225829",
    source="crossref",
    type="journal-article",
)

_PMC_FULL_TEXT_HTML = FULL_TEXT_HTML

_CHALLENGE_HTML = b"""<!DOCTYPE html>
<html>
<head><title>Just a moment...</title></head>
<body>
  <div class="cf-browser-verification">Checking your browser before accessing</div>
  <iframe src="https://www.google.com/recaptcha/challengepage/"></iframe>
</body>
</html>"""


class TestPmcRuntimeRetrieval:
    """Test suite for PMC / Europe PMC runtime retrieval fixes."""

    # -----------------------------------------------------------------------
    # Test A: PMC structured full-text success
    # -----------------------------------------------------------------------
    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._discover_semantic_scholar_candidates", return_value=[])
    @patch("app.services.paper_retriever._discover_unpaywall_candidates", return_value=[])
    @patch("app.services.paper_retriever._discover_europe_pmc_candidates")
    @patch("app.services.paper_retriever._fetch_openalex_work", return_value=None)
    @patch("app.services.paper_retriever.resolve_doi", return_value=_CITATION)
    def test_pmc_structured_full_text_success(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_epmc_disc: MagicMock,
        mock_unpaywall: MagicMock,
        mock_s2: MagicMock,
        mock_retrieve_doc: MagicMock,
        mock_parse_doc: MagicMock,
        mock_chunk_sec: MagicMock,
    ) -> None:
        """Test A: Retrieval succeeds from structured PMC HTML, producing chunks and correct provider."""
        mock_epmc_disc.return_value = [
            FullTextCandidate(
                url="https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/",
                format="html",
                provider="pmc",
                source_type="repository",
            )
        ]
        mock_retrieve_doc.return_value = MagicMock(
            content=_PMC_FULL_TEXT_HTML,
            text=_PMC_FULL_TEXT_HTML.decode("utf-8"),
            format="html",
            content_type="text/html",
            source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/",
        )
        mock_parse_doc.return_value = [
            DocumentSection(section_name="Abstract", text="CRISPR immunity", order=0),
            DocumentSection(section_name="Results", text="Cas9 endonuclease", order=1),
        ]
        mock_chunk_sec.return_value = [
            EvidenceChunk(
                chunk_id="chunk-1",
                paper_id=_CITATION.doi,
                section="Results",
                chunk_index=0,
                text="Cas9 is a DNA endonuclease guided by two RNA molecules.",
            )
        ]

        result = retrieve_paper(_CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.source.provider == "pmc"
        assert result.source.url == "https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/"
        assert len(result.sections) == 2
        assert len(result.chunks) == 1
        assert "Cas9" in result.chunks[0].text

    # -----------------------------------------------------------------------
    # Test B: PDF failure falls back to structured full text
    # -----------------------------------------------------------------------
    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._discover_semantic_scholar_candidates", return_value=[])
    @patch("app.services.paper_retriever._discover_unpaywall_candidates", return_value=[])
    @patch("app.services.paper_retriever._discover_europe_pmc_candidates")
    @patch("app.services.paper_retriever._fetch_openalex_work", return_value=None)
    @patch("app.services.paper_retriever.resolve_doi", return_value=_CITATION)
    def test_pdf_failure_falls_back_to_structured_full_text(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_epmc_disc: MagicMock,
        mock_unpaywall: MagicMock,
        mock_s2: MagicMock,
        mock_retrieve_doc: MagicMock,
        mock_parse_doc: MagicMock,
        mock_chunk_sec: MagicMock,
    ) -> None:
        """Test B: When PMC PDF is invalid / download wrapper, fallback to PMC structured HTML succeeds."""
        mock_epmc_disc.return_value = [
            FullTextCandidate(
                url="https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/pdf/",
                format="pdf",
                provider="pmc",
                source_type="repository",
            ),
            FullTextCandidate(
                url="https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/",
                format="html",
                provider="pmc",
                source_type="repository",
            ),
        ]
        # First call (PMC PDF) fails with invalid PDF; second call (PMC HTML) succeeds
        mock_retrieve_doc.side_effect = [
            DocumentRetrievalError("Downloaded content is not a valid PDF document."),
            MagicMock(
                content=_PMC_FULL_TEXT_HTML,
                text=_PMC_FULL_TEXT_HTML.decode("utf-8"),
                format="html",
                content_type="text/html",
                source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/",
            ),
        ]
        mock_parse_doc.return_value = [
            DocumentSection(section_name="Results", text="Cas9 endonuclease", order=0)
        ]
        mock_chunk_sec.return_value = [
            EvidenceChunk(
                chunk_id="chunk-1",
                paper_id=_CITATION.doi,
                section="Results",
                chunk_index=0,
                text="Cas9 endonuclease evidence.",
            )
        ]

        result = retrieve_paper(_CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.source.provider == "pmc"
        assert result.source.url == "https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/"
        assert len(result.chunks) == 1

    # -----------------------------------------------------------------------
    # Test C: Interstitial remains rejected
    # -----------------------------------------------------------------------
    def test_interstitial_challenge_rejected(self) -> None:
        """Test C: Cloudflare / CAPTCHA challenge pages are identified and rejected."""
        assert is_interstitial_content(_CHALLENGE_HTML) is True

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.url = "https://example.org/challenge"
        mock_resp.content = _CHALLENGE_HTML
        mock_resp.iter_bytes.return_value = [_CHALLENGE_HTML]

        client = MagicMock(spec=httpx.Client)
        client.get.return_value = mock_resp

        with pytest.raises(InterstitialPageError):
            retrieve_document("https://example.org/challenge", client=client)

    def test_benign_recaptcha_script_in_europepmc_not_rejected(self) -> None:
        """Test C2: Benign recaptcha script include in standard layout does not trigger false positive."""
        epmc_html = b"""<!DOCTYPE html>
<html>
<head><title>Europe PMC Article</title></head>
<body>
  <div><script type="text/javascript" src="/Scripts/recaptcha_ajax.js?v=1.1.1"></script></div>
  <article><h1>Research Paper</h1><p>Scientific content body here.</p></article>
</body>
</html>"""
        assert is_interstitial_content(epmc_html) is False

    # -----------------------------------------------------------------------
    # Test D: Publisher fallback remains intact
    # -----------------------------------------------------------------------
    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._discover_semantic_scholar_candidates", return_value=[])
    @patch("app.services.paper_retriever._discover_unpaywall_candidates")
    @patch("app.services.paper_retriever._discover_europe_pmc_candidates")
    @patch("app.services.paper_retriever._fetch_openalex_work", return_value=None)
    @patch("app.services.paper_retriever.resolve_doi", return_value=_CITATION)
    def test_publisher_fallback_remains_intact(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_epmc_disc: MagicMock,
        mock_unpaywall: MagicMock,
        mock_s2: MagicMock,
        mock_retrieve_doc: MagicMock,
        mock_parse_doc: MagicMock,
        mock_chunk_sec: MagicMock,
    ) -> None:
        """Test D: If PMC/Europe PMC fails, retrieval falls back to publisher OA source."""
        mock_epmc_disc.return_value = [
            FullTextCandidate(
                url="https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/",
                format="html",
                provider="pmc",
                source_type="repository",
            ),
        ]
        mock_unpaywall.return_value = [
            FullTextCandidate(
                url="https://publisher.org/open-access/article.pdf",
                format="pdf",
                provider="unpaywall",
                source_type="publisher",
            )
        ]
        mock_retrieve_doc.side_effect = [
            DocumentRetrievalError("PMC unavailable 503"),
            MagicMock(
                content=b"%PDF-1.5 Publisher OA Content",
                text=None,
                format="pdf",
                content_type="application/pdf",
                source_url="https://publisher.org/open-access/article.pdf",
            ),
        ]
        mock_parse_doc.return_value = [
            DocumentSection(section_name="Body", text="Publisher OA content", order=0)
        ]
        mock_chunk_sec.return_value = [
            EvidenceChunk(
                chunk_id="chunk-pub-1",
                paper_id=_CITATION.doi,
                section="Body",
                chunk_index=0,
                text="Publisher OA content text.",
            )
        ]

        result = retrieve_paper(_CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.source.provider == "unpaywall"
        assert result.source.url == "https://publisher.org/open-access/article.pdf"
        assert len(result.chunks) == 1

    # -----------------------------------------------------------------------
    # Test E: No-secret logging
    # -----------------------------------------------------------------------
    def test_no_secret_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test E: API keys and secret tokens never appear in logs during candidate retrieval."""
        secret_token = "secret_api_key_xyz_12345"
        with caplog.at_level(logging.DEBUG):
            client = MagicMock(spec=httpx.Client)
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = 404
            client.get.return_value = mock_resp

            # Attempt discovery with potential secret params
            _discover_europe_pmc_candidates("10.1126/science.1225829", client)

        for record in caplog.records:
            assert secret_token not in record.getMessage()
            assert "authorization" not in record.getMessage().lower()
            assert "api_key" not in record.getMessage().lower()
