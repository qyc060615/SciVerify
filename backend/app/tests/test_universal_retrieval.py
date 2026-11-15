"""Phase 20 - Universal Legal Retrieval: deterministic unit tests.

Covers:
- Europe PMC / PMC source discovery
- Unpaywall discovery (repository vs publisher, PDF vs landing page)
- Semantic Scholar OA PDF discovery
- Full 6-tier candidate ranking / ordering
- Deduplication across sources
- Fallback through the complete hierarchy
- DOI_NOT_FOUND vs FULL_TEXT_UNAVAILABLE distinction
- Security: no secrets or API keys appear in logged / returned URLs
- Access-control: paywalled, 4xx, anti-bot, non-OA content is rejected
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.schemas.citation import CitationMetadata
from app.schemas.paper import PaperRetrievalStatus
from app.services.document_retriever import (
    DocumentRetrievalError,
    InterstitialPageError,
    PaywallError,
)
from app.services.paper_retriever import (
    FullTextCandidate,
    PaperNotFoundError,
    _candidate_priority,
    _dedupe_candidates,
    _discover_europe_pmc_candidates,
    _discover_semantic_scholar_candidates,
    _discover_unpaywall_candidates,
    _order_candidates,
    retrieve_paper,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

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


def _mock_response(status: int, body: dict | bytes) -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status
    if isinstance(body, dict):
        mock.json.return_value = body
        mock.text = json.dumps(body)
    else:
        mock.content = body
        mock.json.side_effect = ValueError("not json")
    return mock


def _mock_client(responses: list[MagicMock]) -> MagicMock:
    client = MagicMock(spec=httpx.Client)
    client.get.side_effect = responses
    return client


# ---------------------------------------------------------------------------
# 1. Europe PMC / PMC source discovery
# ---------------------------------------------------------------------------


class TestEuropePmcDiscovery:
    def test_returns_pmc_pdf_and_europepmc_html_when_pmcid_found(self) -> None:
        epmc_body = {
            "resultList": {
                "result": [{"pmcid": "PMC6286148", "doi": "10.1126/science.1225829"}]
            }
        }
        client = _mock_client([_mock_response(200, epmc_body)])
        candidates = _discover_europe_pmc_candidates("10.1126/science.1225829", client)

        assert len(candidates) == 3
        pdf_c = next(c for c in candidates if c.format == "pdf")
        html_pmc = next(c for c in candidates if c.format == "html" and c.provider == "pmc")
        html_epmc = next(c for c in candidates if c.format == "html" and c.provider == "europepmc")

        assert "pmc.ncbi.nlm.nih.gov/articles/PMC6286148/pdf/" in pdf_c.url
        assert pdf_c.provider == "pmc"
        assert pdf_c.source_type == "repository"

        assert "pmc.ncbi.nlm.nih.gov/articles/PMC6286148/" in html_pmc.url
        assert html_pmc.provider == "pmc"
        assert html_pmc.source_type == "repository"

        assert "europepmc.org/articles/PMC6286148" in html_epmc.url
        assert html_epmc.provider == "europepmc"
        assert html_epmc.source_type == "repository"

    def test_prepends_pmc_prefix_when_pmcid_is_numeric(self) -> None:
        epmc_body = {
            "resultList": {"result": [{"pmcid": "6286148"}]}
        }
        client = _mock_client([_mock_response(200, epmc_body)])
        candidates = _discover_europe_pmc_candidates("10.1126/science.1225829", client)
        assert any("PMC6286148" in c.url for c in candidates)

    def test_returns_empty_when_no_pmcid(self) -> None:
        epmc_body = {
            "resultList": {"result": [{"doi": "10.1126/science.1225829"}]}
        }
        client = _mock_client([_mock_response(200, epmc_body)])
        candidates = _discover_europe_pmc_candidates("10.1126/science.1225829", client)
        assert candidates == []

    def test_returns_empty_on_non_200(self) -> None:
        client = _mock_client([_mock_response(503, {})])
        candidates = _discover_europe_pmc_candidates("10.1126/science.1225829", client)
        assert candidates == []

    def test_returns_empty_when_results_list_is_empty(self) -> None:
        epmc_body = {"resultList": {"result": []}}
        client = _mock_client([_mock_response(200, epmc_body)])
        candidates = _discover_europe_pmc_candidates("10.1126/science.1225829", client)
        assert candidates == []

    def test_handles_network_error_gracefully(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.side_effect = httpx.RequestError("connection refused")
        candidates = _discover_europe_pmc_candidates("10.1126/science.1225829", client)
        assert candidates == []


# ---------------------------------------------------------------------------
# 2. Unpaywall source discovery
# ---------------------------------------------------------------------------


class TestUnpaywallDiscovery:
    def _oa_response(self, locations: list[dict]) -> dict:
        return {"is_oa": True, "doi": "10.1038/example", "oa_locations": locations}

    def test_returns_repository_pdf_candidate(self) -> None:
        body = self._oa_response([
            {
                "host_type": "repository",
                "url_for_pdf": "https://www.ncbi.nlm.nih.gov/pmc/articles/6286148",
                "url": None,
            }
        ])
        client = _mock_client([_mock_response(200, body)])
        candidates = _discover_unpaywall_candidates("10.1038/example", client)
        assert len(candidates) == 1
        assert candidates[0].format == "pdf"
        assert candidates[0].provider == "unpaywall"
        assert candidates[0].source_type == "repository"

    def test_returns_publisher_pdf_with_publisher_source_type(self) -> None:
        body = self._oa_response([
            {
                "host_type": "publisher",
                "url_for_pdf": "https://publisher.com/paper.pdf",
                "url": None,
            }
        ])
        client = _mock_client([_mock_response(200, body)])
        candidates = _discover_unpaywall_candidates("10.1038/example", client)
        assert len(candidates) == 1
        assert candidates[0].source_type == "publisher"

    def test_returns_repository_html_when_no_pdf_url(self) -> None:
        body = self._oa_response([
            {
                "host_type": "repository",
                "url_for_pdf": None,
                "url": "https://arxiv.org/abs/2108.12345",
            }
        ])
        client = _mock_client([_mock_response(200, body)])
        candidates = _discover_unpaywall_candidates("10.1038/example", client)
        assert len(candidates) == 1
        assert candidates[0].source_type == "repository"

    def test_skips_publisher_landing_page_without_pdf(self) -> None:
        body = self._oa_response([
            {
                "host_type": "publisher",
                "url_for_pdf": None,
                "url": "https://publisherdomain.com/article",
            }
        ])
        client = _mock_client([_mock_response(200, body)])
        candidates = _discover_unpaywall_candidates("10.1038/example", client)
        assert candidates == []

    def test_returns_empty_when_not_oa(self) -> None:
        body = {"is_oa": False, "doi": "10.1038/example", "oa_locations": []}
        client = _mock_client([_mock_response(200, body)])
        candidates = _discover_unpaywall_candidates("10.1038/example", client)
        assert candidates == []

    def test_returns_empty_on_non_200(self) -> None:
        client = _mock_client([_mock_response(404, {})])
        candidates = _discover_unpaywall_candidates("10.1038/example", client)
        assert candidates == []

    def test_returns_empty_on_network_error(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.side_effect = httpx.TimeoutException("timeout")
        candidates = _discover_unpaywall_candidates("10.1038/example", client)
        assert candidates == []

    def test_handles_multiple_oa_locations(self) -> None:
        body = self._oa_response([
            {
                "host_type": "repository",
                "url_for_pdf": "https://arxiv.org/pdf/2108.12345",
                "url": None,
            },
            {
                "host_type": "publisher",
                "url_for_pdf": "https://publisher.com/paper.pdf",
                "url": None,
            },
        ])
        client = _mock_client([_mock_response(200, body)])
        candidates = _discover_unpaywall_candidates("10.1038/example", client)
        assert len(candidates) == 2
        sources = {c.source_type for c in candidates}
        assert "repository" in sources
        assert "publisher" in sources


# ---------------------------------------------------------------------------
# 3. Semantic Scholar source discovery
# ---------------------------------------------------------------------------


class TestSemanticScholarDiscovery:
    def test_returns_oa_pdf_candidate(self) -> None:
        body = {
            "isOpenAccess": True,
            "openAccessPdf": {
                "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/6286148",
                "status": "GREEN",
            },
        }
        client = _mock_client([_mock_response(200, body)])
        candidates = _discover_semantic_scholar_candidates("10.1038/example", client)
        assert len(candidates) == 1
        assert candidates[0].provider == "semanticscholar"
        assert candidates[0].format == "pdf"

    def test_returns_empty_when_not_oa(self) -> None:
        body = {"isOpenAccess": False, "openAccessPdf": None}
        client = _mock_client([_mock_response(200, body)])
        candidates = _discover_semantic_scholar_candidates("10.1038/example", client)
        assert candidates == []

    def test_returns_empty_when_oa_pdf_url_missing(self) -> None:
        body = {"isOpenAccess": True, "openAccessPdf": {"url": None}}
        client = _mock_client([_mock_response(200, body)])
        candidates = _discover_semantic_scholar_candidates("10.1038/example", client)
        assert candidates == []

    def test_returns_empty_on_non_200(self) -> None:
        client = _mock_client([_mock_response(429, {})])
        candidates = _discover_semantic_scholar_candidates("10.1038/example", client)
        assert candidates == []

    def test_returns_empty_on_network_error(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.side_effect = httpx.RequestError("network error")
        candidates = _discover_semantic_scholar_candidates("10.1038/example", client)
        assert candidates == []

    def test_repository_url_classified_as_repository_source_type(self) -> None:
        body = {
            "isOpenAccess": True,
            "openAccessPdf": {"url": "https://arxiv.org/pdf/2108.12345v1"},
        }
        client = _mock_client([_mock_response(200, body)])
        candidates = _discover_semantic_scholar_candidates("10.1038/example", client)
        assert candidates[0].source_type == "repository"

    def test_publisher_url_classified_as_publisher_source_type(self) -> None:
        body = {
            "isOpenAccess": True,
            "openAccessPdf": {"url": "https://www.nature.com/articles/paper.pdf"},
        }
        client = _mock_client([_mock_response(200, body)])
        candidates = _discover_semantic_scholar_candidates("10.1038/example", client)
        assert candidates[0].source_type == "publisher"


# ---------------------------------------------------------------------------
# 4. Candidate ranking (6-tier ordering)
# ---------------------------------------------------------------------------


class TestCandidatePriority:
    def test_pmc_pdf_is_tier_0(self) -> None:
        c = FullTextCandidate(
            url="https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/pdf/",
            format="pdf",
            provider="pmc",
            source_type="repository",
        )
        assert _candidate_priority(c) == (0, 0)

    def test_pmc_html_ranks_above_europepmc_html(self) -> None:
        pmc_html = FullTextCandidate(
            url="https://ncbi.nlm.nih.gov/pmc/articles/PMC6286148",
            format="html",
            provider="pmc",
            source_type="repository",
        )
        epmc_html = FullTextCandidate(
            url="https://europepmc.org/articles/PMC6286148",
            format="html",
            provider="europepmc",
            source_type="repository",
        )
        assert _candidate_priority(pmc_html) < _candidate_priority(epmc_html)

    def test_unpaywall_repository_pdf_is_tier_2(self) -> None:
        c = FullTextCandidate(
            url="https://arxiv.org/pdf/2108.12345v1",
            format="pdf",
            provider="unpaywall",
            source_type="repository",
        )
        tier, _ = _candidate_priority(c)
        assert tier == 2

    def test_semanticscholar_pdf_is_tier_4(self) -> None:
        c = FullTextCandidate(
            url="https://www.nature.com/articles/paper.pdf",
            format="pdf",
            provider="semanticscholar",
            source_type="publisher",
        )
        tier, _ = _candidate_priority(c)
        assert tier == 4

    def test_publisher_pdf_is_tier_5(self) -> None:
        c = FullTextCandidate(
            url="https://publisher.com/paper.pdf",
            format="pdf",
            provider="openalex",
            source_type="publisher",
        )
        tier, _ = _candidate_priority(c)
        assert tier == 5

    def test_publisher_html_is_tier_6(self) -> None:
        c = FullTextCandidate(
            url="https://publisher.com/article",
            format="html",
            provider="openalex",
            source_type="publisher",
        )
        tier, _ = _candidate_priority(c)
        assert tier == 6

    def test_order_candidates_sorts_by_tier(self) -> None:
        publisher_html = FullTextCandidate(
            url="https://publisher.com/article",
            format="html",
            provider="openalex",
            source_type="publisher",
        )
        s2_pdf = FullTextCandidate(
            url="https://www.nature.com/articles/paper.pdf",
            format="pdf",
            provider="semanticscholar",
            source_type="publisher",
        )
        unpaywall_pdf = FullTextCandidate(
            url="https://arxiv.org/pdf/1234.5678",
            format="pdf",
            provider="unpaywall",
            source_type="repository",
        )
        pmc_pdf = FullTextCandidate(
            url="https://pmc.ncbi.nlm.nih.gov/articles/PMC9999/pdf/",
            format="pdf",
            provider="pmc",
            source_type="repository",
        )
        ordered = _order_candidates([publisher_html, s2_pdf, unpaywall_pdf, pmc_pdf])
        assert ordered[0].provider == "pmc"
        assert ordered[1].provider == "unpaywall"
        assert ordered[2].provider == "semanticscholar"
        assert ordered[3].provider == "openalex"


# ---------------------------------------------------------------------------
# 5. Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_duplicate_urls_across_sources_are_removed(self) -> None:
        url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/pdf/"
        a = FullTextCandidate(url=url, format="pdf", provider="pmc", source_type="repository")
        b = FullTextCandidate(url=url, format="pdf", provider="unpaywall", source_type="repository")
        result = _dedupe_candidates([a, b])
        assert len(result) == 1
        assert result[0].provider == "pmc"

    def test_different_urls_are_both_kept(self) -> None:
        a = FullTextCandidate(
            url="https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/pdf/",
            format="pdf",
            provider="pmc",
            source_type="repository",
        )
        b = FullTextCandidate(
            url="https://europepmc.org/articles/PMC6286148",
            format="html",
            provider="europepmc",
            source_type="repository",
        )
        result = _dedupe_candidates([a, b])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# 6. Full retrieval hierarchy fallback
# ---------------------------------------------------------------------------


class TestRetrievalHierarchyFallback:
    @patch("app.services.paper_retriever._discover_semantic_scholar_candidates")
    @patch("app.services.paper_retriever._discover_unpaywall_candidates")
    @patch("app.services.paper_retriever._discover_europe_pmc_candidates")
    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_pmc_pdf_succeeds_on_first_attempt(
        self,
        mock_resolve,
        mock_openalex,
        mock_retrieve,
        mock_parse,
        mock_chunk,
        mock_epmc,
        mock_unpaywall,
        mock_s2,
    ) -> None:
        from app.schemas.paper import DocumentSection, EvidenceChunk

        mock_resolve.return_value = _CITATION
        mock_openalex.return_value = {
            "id": "https://openalex.org/W999",
            "open_access": {"is_oa": True},
            "best_oa_location": None,
            "primary_location": None,
            "locations": [],
        }
        pmc_pdf = FullTextCandidate(
            url="https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/pdf/",
            format="pdf",
            provider="pmc",
            source_type="repository",
        )
        mock_epmc.return_value = [pmc_pdf]
        mock_unpaywall.return_value = []
        mock_s2.return_value = []
        mock_retrieve.return_value = MagicMock(
            content=b"%PDF-1.4",
            text=None,
            format="pdf",
            content_type="application/pdf",
            source_url=pmc_pdf.url,
        )
        mock_parse.return_value = [
            DocumentSection(section_name="Body", text="PMC content.", order=0)
        ]
        mock_chunk.return_value = [
            EvidenceChunk(
                chunk_id="pmc-chunk-0",
                paper_id=_CITATION.doi,
                section="Body",
                chunk_index=0,
                text="PMC content.",
            )
        ]

        result = retrieve_paper(_CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.source.provider == "pmc"
        assert mock_retrieve.call_count == 1

    @patch("app.services.paper_retriever._discover_semantic_scholar_candidates")
    @patch("app.services.paper_retriever._discover_unpaywall_candidates")
    @patch("app.services.paper_retriever._discover_europe_pmc_candidates")
    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_falls_back_to_unpaywall_when_pmc_fails(
        self,
        mock_resolve,
        mock_openalex,
        mock_retrieve,
        mock_parse,
        mock_chunk,
        mock_epmc,
        mock_unpaywall,
        mock_s2,
    ) -> None:
        from app.schemas.paper import DocumentSection, EvidenceChunk

        mock_resolve.return_value = _CITATION
        mock_openalex.return_value = {
            "id": "https://openalex.org/W999",
            "open_access": {"is_oa": True},
            "best_oa_location": None,
            "primary_location": None,
            "locations": [],
        }
        pmc_pdf = FullTextCandidate(
            url="https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/pdf/",
            format="pdf",
            provider="pmc",
            source_type="repository",
        )
        arxiv_pdf = FullTextCandidate(
            url="https://arxiv.org/pdf/2108.12345v1",
            format="pdf",
            provider="unpaywall",
            source_type="repository",
        )
        mock_epmc.return_value = [pmc_pdf]
        mock_unpaywall.return_value = [arxiv_pdf]
        mock_s2.return_value = []

        arxiv_doc = MagicMock(
            content=b"%PDF-1.4",
            text=None,
            format="pdf",
            content_type="application/pdf",
            source_url=arxiv_pdf.url,
        )
        mock_retrieve.side_effect = [
            DocumentRetrievalError("PMC PDF failed"),
            arxiv_doc,
        ]
        mock_parse.return_value = [
            DocumentSection(section_name="Abstract", text="arXiv content.", order=0)
        ]
        mock_chunk.return_value = [
            EvidenceChunk(
                chunk_id="arxiv-chunk-0",
                paper_id=_CITATION.doi,
                section="Abstract",
                chunk_index=0,
                text="arXiv content.",
            )
        ]

        result = retrieve_paper(_CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.source.provider == "unpaywall"

    @patch("app.services.paper_retriever._discover_semantic_scholar_candidates")
    @patch("app.services.paper_retriever._discover_unpaywall_candidates")
    @patch("app.services.paper_retriever._discover_europe_pmc_candidates")
    @patch("app.services.paper_retriever.chunk_sections")
    @patch("app.services.paper_retriever.parse_document")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_falls_back_to_semantic_scholar_when_repo_sources_fail(
        self,
        mock_resolve,
        mock_openalex,
        mock_retrieve,
        mock_parse,
        mock_chunk,
        mock_epmc,
        mock_unpaywall,
        mock_s2,
    ) -> None:
        from app.schemas.paper import DocumentSection, EvidenceChunk

        mock_resolve.return_value = _CITATION
        mock_openalex.return_value = {
            "id": "https://openalex.org/W999",
            "open_access": {"is_oa": True},
            "best_oa_location": None,
            "primary_location": None,
            "locations": [],
        }
        pmc_pdf = FullTextCandidate(
            url="https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/pdf/",
            format="pdf",
            provider="pmc",
            source_type="repository",
        )
        s2_pdf = FullTextCandidate(
            url="https://www.nature.com/articles/paper.pdf",
            format="pdf",
            provider="semanticscholar",
            source_type="publisher",
        )
        mock_epmc.return_value = [pmc_pdf]
        mock_unpaywall.return_value = []
        mock_s2.return_value = [s2_pdf]

        s2_doc = MagicMock(
            content=b"%PDF-1.4",
            text=None,
            format="pdf",
            content_type="application/pdf",
            source_url=s2_pdf.url,
        )
        mock_retrieve.side_effect = [
            DocumentRetrievalError("PMC PDF failed"),
            s2_doc,
        ]
        mock_parse.return_value = [
            DocumentSection(section_name="Abstract", text="Nature OA content.", order=0)
        ]
        mock_chunk.return_value = [
            EvidenceChunk(
                chunk_id="s2-chunk-0",
                paper_id=_CITATION.doi,
                section="Abstract",
                chunk_index=0,
                text="Nature OA content.",
            )
        ]

        result = retrieve_paper(_CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.SUCCESS
        assert result.source.provider == "semanticscholar"

    @patch("app.services.paper_retriever._discover_semantic_scholar_candidates")
    @patch("app.services.paper_retriever._discover_unpaywall_candidates")
    @patch("app.services.paper_retriever._discover_europe_pmc_candidates")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_full_text_unavailable_when_all_sources_fail(
        self,
        mock_resolve,
        mock_openalex,
        mock_epmc,
        mock_unpaywall,
        mock_s2,
    ) -> None:
        mock_resolve.return_value = _CITATION
        mock_openalex.return_value = {
            "id": "https://openalex.org/W999",
            "open_access": {"is_oa": False},
            "best_oa_location": None,
            "primary_location": None,
            "locations": [],
        }
        mock_epmc.return_value = []
        mock_unpaywall.return_value = []
        mock_s2.return_value = []

        result = retrieve_paper(_CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        assert result.paper.doi == _CITATION.doi


# ---------------------------------------------------------------------------
# 7. DOI_NOT_FOUND vs FULL_TEXT_UNAVAILABLE distinction
# ---------------------------------------------------------------------------


class TestDoiNotFoundDistinction:
    @patch("app.services.paper_retriever.resolve_doi")
    def test_raises_paper_not_found_when_doi_resolution_fails(self, mock_resolve) -> None:
        from app.services.citation_resolver import CitationNotFoundError

        mock_resolve.side_effect = CitationNotFoundError("DOI not found")

        with pytest.raises(PaperNotFoundError):
            retrieve_paper("10.9999/nonexistent.doi", client=MagicMock())

    @patch("app.services.paper_retriever._discover_semantic_scholar_candidates")
    @patch("app.services.paper_retriever._discover_unpaywall_candidates")
    @patch("app.services.paper_retriever._discover_europe_pmc_candidates")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_full_text_unavailable_when_doi_resolves_but_no_oa_source(
        self,
        mock_resolve,
        mock_openalex,
        mock_epmc,
        mock_unpaywall,
        mock_s2,
    ) -> None:
        """DOI resolves correctly but has no accessible full text - must NOT raise PaperNotFoundError."""
        mock_resolve.return_value = _CITATION
        mock_openalex.return_value = {
            "id": "https://openalex.org/W999",
            "open_access": {"is_oa": False},
            "best_oa_location": None,
            "primary_location": None,
            "locations": [],
        }
        mock_epmc.return_value = []
        mock_unpaywall.return_value = []
        mock_s2.return_value = []

        result = retrieve_paper(_CITATION.doi, client=MagicMock())

        assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        # Title and DOI metadata must be present even when full text is missing
        assert result.paper.title is not None
        assert result.paper.doi == _CITATION.doi


# ---------------------------------------------------------------------------
# 8. Security: no secrets appear in discovery request URLs
# ---------------------------------------------------------------------------


class TestSecurityNoSecretsInUrls:
    def test_unpaywall_email_is_team_address_not_api_key(self) -> None:
        from app.services.paper_retriever import _UNPAYWALL_EMAIL

        assert "@" in _UNPAYWALL_EMAIL
        assert "key" not in _UNPAYWALL_EMAIL.lower()
        assert "secret" not in _UNPAYWALL_EMAIL.lower()
        assert "token" not in _UNPAYWALL_EMAIL.lower()

    def test_europe_pmc_discovery_url_contains_no_api_keys(self) -> None:
        epmc_body = {"resultList": {"result": []}}
        client = _mock_client([_mock_response(200, epmc_body)])
        _discover_europe_pmc_candidates("10.1038/example", client)

        called_url = str(client.get.call_args[0][0])
        assert "apikey" not in called_url.lower()
        assert "token" not in called_url.lower()
        assert "secret" not in called_url.lower()

    def test_semantic_scholar_discovery_url_contains_no_api_keys(self) -> None:
        body = {"isOpenAccess": False, "openAccessPdf": None}
        client = _mock_client([_mock_response(200, body)])
        _discover_semantic_scholar_candidates("10.1038/example", client)

        called_url = str(client.get.call_args[0][0])
        assert "apikey" not in called_url.lower()
        assert "x-api-key" not in called_url.lower()


# ---------------------------------------------------------------------------
# 9. Access-control: paywall and anti-bot content is rejected
# ---------------------------------------------------------------------------


class TestAccessControlRejection:
    @patch("app.services.paper_retriever._discover_semantic_scholar_candidates")
    @patch("app.services.paper_retriever._discover_unpaywall_candidates")
    @patch("app.services.paper_retriever._discover_europe_pmc_candidates")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_interstitial_candidate_results_in_full_text_unavailable(
        self,
        mock_resolve,
        mock_openalex,
        mock_retrieve,
        mock_epmc,
        mock_unpaywall,
        mock_s2,
    ) -> None:
        mock_resolve.return_value = _CITATION
        mock_openalex.return_value = {
            "id": "https://openalex.org/W999",
            "open_access": {"is_oa": True},
            "best_oa_location": None,
            "primary_location": None,
            "locations": [],
        }
        pmc_pdf = FullTextCandidate(
            url="https://pmc.ncbi.nlm.nih.gov/articles/PMC9999/pdf/",
            format="pdf",
            provider="pmc",
            source_type="repository",
        )
        mock_epmc.return_value = [pmc_pdf]
        mock_unpaywall.return_value = []
        mock_s2.return_value = []
        mock_retrieve.side_effect = InterstitialPageError("Anti-bot challenge detected")

        result = retrieve_paper(_CITATION.doi, client=MagicMock())
        assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE

    @patch("app.services.paper_retriever._discover_semantic_scholar_candidates")
    @patch("app.services.paper_retriever._discover_unpaywall_candidates")
    @patch("app.services.paper_retriever._discover_europe_pmc_candidates")
    @patch("app.services.paper_retriever.retrieve_document")
    @patch("app.services.paper_retriever._fetch_openalex_work")
    @patch("app.services.paper_retriever.resolve_doi")
    def test_paywall_candidate_results_in_full_text_unavailable(
        self,
        mock_resolve,
        mock_openalex,
        mock_retrieve,
        mock_epmc,
        mock_unpaywall,
        mock_s2,
    ) -> None:
        mock_resolve.return_value = _CITATION
        mock_openalex.return_value = {
            "id": "https://openalex.org/W999",
            "open_access": {"is_oa": True},
            "best_oa_location": {"pdf_url": "https://publisher.com/paper.pdf", "is_oa": True},
            "primary_location": None,
            "locations": [],
        }
        mock_epmc.return_value = []
        mock_unpaywall.return_value = []
        mock_s2.return_value = []
        mock_retrieve.side_effect = PaywallError("Subscription required")

        result = retrieve_paper(_CITATION.doi, client=MagicMock())
        assert result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
