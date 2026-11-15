from __future__ import annotations

from unittest.mock import MagicMock, patch


from app.tests.full_text_fixtures import FULL_TEXT_HTML

import httpx
import pytest

from app.schemas.citation import CitationMetadata
from app.schemas.paper import PaperRetrievalStatus
from app.services.document_retriever import InterstitialPageError
from app.services.paper_retriever import (
    PaperNotFoundError,
    PaperProviderError,
    discover_full_text,
    discover_full_text_candidates,
    retrieve_paper,
)

CITATION = CitationMetadata(
    doi="10.1038/s41586-020-2649-2",
    title="Example Paper",
    authors=["Ada Lovelace"],
    journal="Nature",
    publisher="Nature Publishing Group",
    year=2020,
    url="https://doi.org/10.1038/s41586-020-2649-2",
    source="crossref",
    type="journal-article",
)

OPENALEX_WITH_PDF = {
    "id": "https://openalex.org/W123",
    "abstract_inverted_index": {
        "Example": [0],
        "abstract": [1],
        "text.": [2],
    },
    "publication_date": "2020-05-28",
    "open_access": {"is_oa": True},
    "best_oa_location": {
        "pdf_url": "https://example.org/paper.pdf",
        "oa_url": "https://example.org/paper.html",
    },
    "primary_location": {
        "landing_page_url": "https://example.org/landing",
    },
    "locations": [],
}

OPENALEX_NO_FULL_TEXT = {
    "id": "https://openalex.org/W456",
    "abstract_inverted_index": {"Metadata": [0], "only.": [1]},
    "publication_date": "2020-01-01",
    "open_access": {"is_oa": False},
    "best_oa_location": None,
    "primary_location": {"landing_page_url": "https://example.org/landing"},
    "locations": [],
}

OPENALEX_PMC_OA_LANDING = {
    "id": "https://openalex.org/W999",
    "abstract_inverted_index": {"Cas9": [0], "RNA": [1], "guide.": [2]},
    "publication_date": "2012-08-17",
    "open_access": {
        "is_oa": True,
        "oa_url": "https://www.ncbi.nlm.nih.gov/pmc/articles/6286148",
    },
    "best_oa_location": {
        "pdf_url": None,
        "oa_url": None,
        "landing_page_url": "https://www.ncbi.nlm.nih.gov/pmc/articles/6286148",
        "is_oa": True,
    },
    "primary_location": {
        "landing_page_url": "https://doi.org/10.1126/science.1225829",
        "is_oa": False,
    },
    "locations": [
        {
            "landing_page_url": "https://doi.org/10.1126/science.1225829",
            "is_oa": False,
        },
        {
            "landing_page_url": "https://www.ncbi.nlm.nih.gov/pmc/articles/6286148",
            "is_oa": True,
        },
    ],
}


class TestDiscoverFullText:
    def test_public_pdf_available(self) -> None:
        candidate = discover_full_text(OPENALEX_WITH_PDF)
        assert candidate is not None
        assert candidate.format == "pdf"
        assert candidate.url == "https://example.org/paper.pdf"

    def test_public_html_available(self) -> None:
        work = {
            **OPENALEX_NO_FULL_TEXT,
            "best_oa_location": {"oa_url": "https://example.org/paper.html"},
        }
        candidate = discover_full_text(work)
        assert candidate is not None
        assert candidate.format == "html"

    def test_no_full_text_available(self) -> None:
        assert discover_full_text(OPENALEX_NO_FULL_TEXT) is None

    def test_oa_landing_page_without_pdf_or_oa_url(self) -> None:
        candidate = discover_full_text(OPENALEX_PMC_OA_LANDING)
        assert candidate is not None
        assert candidate.url == "https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/pdf/"
        assert candidate.format == "pdf"
        assert candidate.provider == "pmc"

    def test_ignores_non_oa_publisher_landing_page(self) -> None:
        work = {
            **OPENALEX_NO_FULL_TEXT,
            "primary_location": {
                "landing_page_url": "https://doi.org/10.1126/science.1225829",
                "is_oa": False,
            },
        }
        assert discover_full_text(work) is None

    def test_pmc_candidates_include_pdf_and_europe_pmc_mirrors(self) -> None:
        candidates = discover_full_text_candidates(OPENALEX_PMC_OA_LANDING)
        urls = [candidate.url for candidate in candidates]

        assert "https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/pdf/" in urls
        assert "https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/" in urls
        assert "https://europepmc.org/articles/PMC6286148" in urls
        assert candidates[0].format == "pdf"


class TestRetrievePaper:
    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_successful_retrieval(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_retrieve: MagicMock,
        mock_parse: MagicMock,
        mock_chunk: MagicMock,
    ) -> None:
        from app.schemas.paper import EvidenceChunk

        mock_resolve.return_value = CITATION
        mock_openalex.return_value = OPENALEX_WITH_PDF
        mock_retrieve.return_value = MagicMock(
            content=b"%PDF-1.4",
            text=None,
            format="pdf",
            content_type="application/pdf",
            source_url="https://example.org/paper.pdf",
        )
        mock_parse.return_value = []
        mock_chunk.return_value = [
            EvidenceChunk(
                chunk_id="10.1038/s41586-020-2649-2:Abstract:0",
                paper_id=CITATION.doi,
                section="Abstract",
                chunk_index=0,
                text="Example abstract text.",
            )
        ]

        result = retrieve_paper(CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.paper.full_text_available is True
        assert result.paper.abstract == "Example abstract text."

    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_metadata_only_when_openalex_enrichment_fails(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
    ) -> None:
        mock_resolve.return_value = CITATION
        mock_openalex.side_effect = PaperProviderError("OpenAlex unavailable.")

        result = retrieve_paper(CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.METADATA_ONLY
        assert result.paper.full_text_available is False
        assert result.sections == []

    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_full_text_unavailable(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
    ) -> None:
        mock_resolve.return_value = CITATION
        mock_openalex.return_value = OPENALEX_NO_FULL_TEXT

        result = retrieve_paper(CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        assert result.paper.full_text_available is False

    @patch("app.services.paper_retriever.resolve_doi")
    def test_paper_not_found(self, mock_resolve: MagicMock) -> None:
        from app.services.citation_resolver import CitationNotFoundError

        mock_resolve.side_effect = CitationNotFoundError("not found")

        with pytest.raises(PaperNotFoundError):
            retrieve_paper("10.1038/not-found", client=MagicMock())

    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_provider_failure_on_download(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_retrieve: MagicMock,
    ) -> None:
        from app.services.document_retriever import DocumentRetrievalError

        mock_resolve.return_value = CITATION
        mock_openalex.return_value = OPENALEX_WITH_PDF
        mock_retrieve.side_effect = DocumentRetrievalError("timeout")

        result = retrieve_paper(CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        assert result.paper.full_text_available is False
        assert result.detail == "timeout"

    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_parsing_failure(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_retrieve: MagicMock,
        mock_parse: MagicMock,
        mock_chunk: MagicMock,
    ) -> None:
        from app.services.document_parser import DocumentParseError

        mock_resolve.return_value = CITATION
        mock_openalex.return_value = OPENALEX_WITH_PDF
        mock_retrieve.return_value = MagicMock(
            content=b"%PDF-1.4",
            text=None,
            format="pdf",
            content_type="application/pdf",
            source_url="https://example.org/paper.pdf",
        )
        mock_parse.side_effect = DocumentParseError(
            "PDF document contains no extractable text.",
            reason="pdf_no_text",
        )
        mock_chunk.return_value = []

        result = retrieve_paper(CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        assert result.paper.full_text_available is False
        assert result.detail == "PDF document contains no extractable text."
        mock_chunk.assert_not_called()

    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_successful_pdf_parsing(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_retrieve: MagicMock,
        mock_parse: MagicMock,
        mock_chunk: MagicMock,
    ) -> None:
        from app.schemas.paper import DocumentSection, EvidenceChunk

        mock_resolve.return_value = CITATION
        mock_openalex.return_value = OPENALEX_WITH_PDF
        mock_retrieve.return_value = MagicMock(
            content=b"%PDF-1.4",
            text=None,
            format="pdf",
            content_type="application/pdf",
            source_url="https://example.org/paper.pdf",
        )
        mock_parse.return_value = [
            DocumentSection(section_name="Abstract", text="Findings.", order=0),
        ]
        mock_chunk.return_value = [
            EvidenceChunk(
                chunk_id="10.1038/s41586-020-2649-2:Abstract:0",
                paper_id=CITATION.doi,
                section="Abstract",
                chunk_index=0,
                text="Findings.",
            )
        ]

        result = retrieve_paper(CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert len(result.sections) == 1
        assert len(result.chunks) == 1
        assert result.detail is None

    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_successful_html_parsing(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_retrieve: MagicMock,
        mock_parse: MagicMock,
        mock_chunk: MagicMock,
    ) -> None:
        from app.schemas.paper import DocumentSection, EvidenceChunk

        work = {
            **OPENALEX_NO_FULL_TEXT,
            "best_oa_location": {"oa_url": "https://example.org/paper.html"},
        }
        mock_resolve.return_value = CITATION
        mock_openalex.return_value = work
        mock_retrieve.return_value = MagicMock(
            content=FULL_TEXT_HTML,
            text=FULL_TEXT_HTML.decode(),
            format="html",
            content_type="text/html",
            source_url="https://example.org/paper.html",
        )
        mock_parse.return_value = [
            DocumentSection(section_name="Body", text="Content", order=0),
        ]
        mock_chunk.return_value = [
            EvidenceChunk(
                chunk_id="10.1038/s41586-020-2649-2:Body:0",
                paper_id=CITATION.doi,
                section="Body",
                chunk_index=0,
                text="Content",
            )
        ]

        result = retrieve_paper(CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.paper.full_text_format == "html"

    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_successful_pmc_landing_page_retrieval(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_retrieve: MagicMock,
        mock_parse: MagicMock,
        mock_chunk: MagicMock,
    ) -> None:
        from app.schemas.paper import DocumentSection, EvidenceChunk

        mock_resolve.return_value = CitationMetadata(
            doi="10.1126/science.1225829",
            title="A Programmable Dual-RNA-Guided DNA Endonuclease in Adaptive Bacterial Immunity",
            authors=["Jennifer A. Doudna"],
            journal="Science",
            publisher="American Association for the Advancement of Science",
            year=2012,
            url="https://doi.org/10.1126/science.1225829",
            source="crossref",
            type="journal-article",
        )
        mock_openalex.return_value = OPENALEX_PMC_OA_LANDING
        document = MagicMock(
            content=FULL_TEXT_HTML,
            text=FULL_TEXT_HTML.decode(),
            format="html",
            content_type="text/html",
            source_url="https://www.ncbi.nlm.nih.gov/pmc/articles/6286148",
        )
        mock_retrieve.side_effect = [
            InterstitialPageError("interstitial"),
            document,
        ]
        mock_parse.return_value = [
            DocumentSection(section_name="Results", text="Cas9 can be directed by RNA.", order=0),
        ]
        mock_chunk.return_value = [
            EvidenceChunk(
                chunk_id="10.1126/science.1225829:Results:0",
                paper_id="10.1126/science.1225829",
                section="Results",
                chunk_index=0,
                text="Cas9 can be directed by RNA.",
            )
        ]

        result = retrieve_paper("10.1126/science.1225829", client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.paper.full_text_available is True
        assert len(result.chunks) == 1
        assert mock_retrieve.call_count >= 2
        called_urls = [call.args[0] for call in mock_retrieve.call_args_list]
        assert "https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/pdf/" in called_urls

    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_publisher_anti_bot_403_returns_full_text_unavailable(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_retrieve: MagicMock,
    ) -> None:
        from app.services.document_retriever import DocumentRetrievalError

        mock_resolve.return_value = CitationMetadata(
            doi="10.1056/NEJM199103213241202",
            title="Effect of a Short Course of Prednisone in the Prevention of Early Relapse",
            authors=["Kenneth R. Chapman"],
            journal="New England Journal of Medicine",
            publisher="Massachusetts Medical Society",
            year=1991,
            url="https://doi.org/10.1056/nejm199103213241202",
            source="crossref",
            type="journal-article",
        )
        mock_openalex.return_value = {
            "id": "https://openalex.org/W1968945837",
            "open_access": {"is_oa": True, "oa_status": "bronze"},
            "best_oa_location": {
                "pdf_url": "https://www.nejm.org/doi/pdf/10.1056/NEJM199103213241202?articleTools=true",
                "landing_page_url": "https://doi.org/10.1056/nejm199103213241202",
            },
            "primary_location": {
                "landing_page_url": "https://doi.org/10.1056/nejm199103213241202",
            },
            "locations": [],
        }
        # Simulate publisher blocking automated requests with 403 Forbidden / Cloudflare challenge
        mock_retrieve.side_effect = DocumentRetrievalError("Document request failed with status 403.")

        result = retrieve_paper("10.1056/NEJM199103213241202", client=MagicMock())

        assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        assert result.paper.full_text_available is False
        assert len(result.chunks) == 0
        assert len(result.sections) == 0
        assert "403" in (result.detail or "")

    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_pmc_preferred_over_publisher(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_retrieve: MagicMock,
        mock_parse: MagicMock,
        mock_chunk: MagicMock,
    ) -> None:
        from app.schemas.paper import DocumentSection, EvidenceChunk

        mock_resolve.return_value = CITATION
        mock_openalex.return_value = {
            "id": "https://openalex.org/W123",
            "open_access": {"is_oa": True},
            "best_oa_location": {
                "pdf_url": "https://publisher.com/paper.pdf",
                "landing_page_url": "https://doi.org/10.1038/example",
            },
            "locations": [
                {
                    "landing_page_url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8371605",
                    "is_oa": True,
                },
                {
                    "pdf_url": "https://publisher.com/paper.pdf",
                    "is_oa": True,
                },
            ],
        }
        pmc_doc = MagicMock(
            content=b"%PDF-1.4 PMC content",
            text=None,
            format="pdf",
            content_type="application/pdf",
            source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC8371605/pdf/",
        )
        mock_retrieve.return_value = pmc_doc
        mock_parse.return_value = [
            DocumentSection(section_name="Methods", text="PMC extracted evidence.", order=0)
        ]
        mock_chunk.return_value = [
            EvidenceChunk(
                chunk_id="chunk-pmc-1",
                paper_id=CITATION.doi,
                section="Methods",
                chunk_index=0,
                text="PMC extracted evidence.",
            )
        ]

        result = retrieve_paper(CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.source.provider == "pmc"
        assert result.paper.full_text_url == "https://pmc.ncbi.nlm.nih.gov/articles/PMC8371605/pdf/"
        # Ensure PMC was tried on the very first call
        first_call_url = mock_retrieve.call_args_list[0].args[0]
        assert "pmc.ncbi.nlm.nih.gov" in first_call_url

    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_europe_pmc_fallback_when_pmc_fails(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_retrieve: MagicMock,
        mock_parse: MagicMock,
        mock_chunk: MagicMock,
    ) -> None:
        from app.schemas.paper import DocumentSection, EvidenceChunk
        from app.services.document_retriever import DocumentRetrievalError

        mock_resolve.return_value = CITATION
        mock_openalex.return_value = {
            "id": "https://openalex.org/W123",
            "open_access": {"is_oa": True},
            "best_oa_location": {
                "landing_page_url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8371605",
                "is_oa": True,
            },
            "locations": [],
        }
        europe_pmc_doc = MagicMock(
            content=FULL_TEXT_HTML,
            text=FULL_TEXT_HTML.decode(),
            format="html",
            content_type="text/html",
            source_url="https://europepmc.org/articles/PMC8371605",
        )
        # PMC PDF fails, PMC HTML fails, Europe PMC HTML succeeds
        mock_retrieve.side_effect = [
            DocumentRetrievalError("PMC PDF download failed 404"),
            DocumentRetrievalError("PMC HTML download failed 404"),
            europe_pmc_doc,
        ]
        mock_parse.return_value = [
            DocumentSection(section_name="Results", text="Europe PMC evidence.", order=0)
        ]
        mock_chunk.return_value = [
            EvidenceChunk(
                chunk_id="chunk-epmc-1",
                paper_id=CITATION.doi,
                section="Results",
                chunk_index=0,
                text="Europe PMC evidence.",
            )
        ]

        result = retrieve_paper(CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.source.provider == "europepmc"
        assert result.source.url == "https://europepmc.org/articles/PMC8371605"
        assert len(result.chunks) == 1

    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_publisher_fallback_when_pmc_and_europepmc_fail(
        self,
        mock_resolve: MagicMock,
        mock_openalex: MagicMock,
        mock_retrieve: MagicMock,
        mock_parse: MagicMock,
        mock_chunk: MagicMock,
    ) -> None:
        from app.schemas.paper import DocumentSection, EvidenceChunk
        from app.services.document_retriever import DocumentRetrievalError

        mock_resolve.return_value = CITATION
        mock_openalex.return_value = {
            "id": "https://openalex.org/W123",
            "open_access": {"is_oa": True},
            "best_oa_location": {
                "pdf_url": "https://publisher.com/paper.pdf",
                "is_oa": True,
            },
            "locations": [
                {
                    "landing_page_url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8371605",
                    "is_oa": True,
                },
                {
                    "pdf_url": "https://publisher.com/paper.pdf",
                    "is_oa": True,
                },
            ],
        }
        publisher_doc = MagicMock(
            content=b"%PDF-1.4 Publisher OA PDF",
            text=None,
            format="pdf",
            content_type="application/pdf",
            source_url="https://publisher.com/paper.pdf",
        )
        # PMC PDF fails, Europe PMC HTML fails, PMC HTML fails -> publisher PDF succeeds
        mock_retrieve.side_effect = [
            DocumentRetrievalError("PMC PDF failed"),
            DocumentRetrievalError("PMC HTML failed"),
            DocumentRetrievalError("Europe PMC failed"),
            publisher_doc,
        ]
        mock_parse.return_value = [
            DocumentSection(section_name="Main", text="Publisher OA content.", order=0)
        ]
        mock_chunk.return_value = [
            EvidenceChunk(
                chunk_id="chunk-pub-1",
                paper_id=CITATION.doi,
                section="Main",
                chunk_index=0,
                text="Publisher OA content.",
            )
        ]

        result = retrieve_paper(CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.paper.full_text_url == "https://publisher.com/paper.pdf"


class TestOpenAlexFetch:
    @patch("httpx.Client.get")
    def test_malformed_openalex_response(self, mock_get: MagicMock) -> None:
        from app.services.paper_retriever import _fetch_openalex_work

        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.json.return_value = {"unexpected": True}
        mock_get.return_value = response

        with pytest.raises(PaperProviderError):
            _fetch_openalex_work("10.1038/example", httpx.Client())
