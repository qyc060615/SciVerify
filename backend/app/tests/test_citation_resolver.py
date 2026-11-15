from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.citation_resolver import (
    CitationNotFoundError,
    CitationResolverError,
    _map_crossref_message,
    _map_openalex_work,
    resolve_doi,
)
from app.utils.doi import InvalidDOIError, normalize_doi


class TestNormalizeDoi:
    def test_raw_doi(self) -> None:
        assert normalize_doi("10.1038/s41586-020-2649-2") == "10.1038/s41586-020-2649-2"

    def test_doi_org_https_url(self) -> None:
        assert (
            normalize_doi("https://doi.org/10.1038/s41586-020-2649-2")
            == "10.1038/s41586-020-2649-2"
        )

    def test_doi_org_http_url(self) -> None:
        assert (
            normalize_doi("http://doi.org/10.1038/s41586-020-2649-2")
            == "10.1038/s41586-020-2649-2"
        )

    def test_doi_prefix(self) -> None:
        assert normalize_doi("doi:10.1038/s41586-020-2649-2") == "10.1038/s41586-020-2649-2"

    def test_whitespace(self) -> None:
        assert (
            normalize_doi("  10.1038/s41586-020-2649-2  ")
            == "10.1038/s41586-020-2649-2"
        )

    def test_invalid_doi(self) -> None:
        with pytest.raises(InvalidDOIError):
            normalize_doi("not-a-doi")


CROSSREF_MESSAGE = {
    "DOI": "10.1038/s41586-020-2649-2",
    "title": ["Example Paper Title"],
    "author": [
        {"given": "Ada", "family": "Lovelace"},
        {"given": "Alan", "family": "Turing"},
    ],
    "container-title": ["Nature"],
    "publisher": "Nature Publishing Group",
    "published-print": {"date-parts": [[2020, 5, 28]]},
    "URL": "https://doi.org/10.1038/s41586-020-2649-2",
    "type": "journal-article",
}

OPENALEX_WORK = {
    "id": "https://openalex.org/W123",
    "doi": "https://doi.org/10.1038/s41586-020-2649-2",
    "display_name": "Fallback Paper Title",
    "authorships": [
        {"author": {"display_name": "Grace Hopper"}},
    ],
    "primary_location": {
        "source": {
            "display_name": "OpenAlex Journal",
            "host_organization_name": "OpenAlex Publisher",
        }
    },
    "publication_year": 2021,
    "type": "article",
}


def _mock_response(status_code: int, json_data: dict | None = None) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    if json_data is None:
        response.json.side_effect = ValueError("invalid json")
    else:
        response.json.return_value = json_data
    return response


class TestCrossrefParsing:
    @patch("app.services.citation_resolver._resolve_from_openalex")
    @patch("app.services.citation_resolver._resolve_from_crossref")
    def test_complete_metadata(
        self,
        mock_crossref: MagicMock,
        mock_openalex: MagicMock,
    ) -> None:
        mock_crossref.return_value = _map_crossref_message(
            CROSSREF_MESSAGE,
            "10.1038/s41586-020-2649-2",
        )

        result = resolve_doi("10.1038/s41586-020-2649-2", client=MagicMock())

        assert result.source == "crossref"
        assert result.title == "Example Paper Title"
        assert result.authors == ["Ada Lovelace", "Alan Turing"]
        assert result.journal == "Nature"
        assert result.publisher == "Nature Publishing Group"
        assert result.year == 2020
        mock_openalex.assert_not_called()

    def test_missing_optional_fields(self) -> None:
        message = {
            "DOI": "10.1000/minimal",
            "title": ["Minimal Title"],
        }
        result = _map_crossref_message(message, "10.1000/minimal")
        assert result is not None
        assert result.title == "Minimal Title"
        assert result.authors == []
        assert result.journal is None


class TestOpenAlexFallback:
    @patch("app.services.citation_resolver._resolve_from_semantic_scholar")
    @patch("app.services.citation_resolver._resolve_from_openalex")
    @patch("app.services.citation_resolver._resolve_from_crossref")
    def test_openalex_called_when_crossref_not_found(
        self,
        mock_crossref: MagicMock,
        mock_openalex: MagicMock,
        mock_semantic_scholar: MagicMock,
    ) -> None:
        mock_crossref.return_value = None
        mock_openalex.return_value = _map_openalex_work(
            OPENALEX_WORK,
            "10.1038/s41586-020-2649-2",
        )
        mock_semantic_scholar.return_value = None

        result = resolve_doi("10.1038/s41586-020-2649-2", client=MagicMock())

        assert result.source == "openalex"
        assert result.title == "Fallback Paper Title"
        mock_openalex.assert_called_once()


class TestNotFound:
    @patch("app.services.citation_resolver._resolve_from_semantic_scholar")
    @patch("app.services.citation_resolver._resolve_from_openalex")
    @patch("app.services.citation_resolver._resolve_from_crossref")
    def test_both_providers_not_found(
        self,
        mock_crossref: MagicMock,
        mock_openalex: MagicMock,
        mock_semantic_scholar: MagicMock,
    ) -> None:
        mock_crossref.return_value = None
        mock_openalex.return_value = None
        mock_semantic_scholar.return_value = None

        with pytest.raises(CitationNotFoundError):
            resolve_doi("10.1038/not-found-example", client=MagicMock())


class TestResolverErrors:
    @patch("app.services.citation_resolver._resolve_from_semantic_scholar")
    @patch("app.services.citation_resolver._resolve_from_openalex")
    @patch("app.services.citation_resolver._resolve_from_crossref")
    def test_both_providers_fail(
        self,
        mock_crossref: MagicMock,
        mock_openalex: MagicMock,
        mock_semantic_scholar: MagicMock,
    ) -> None:
        mock_crossref.side_effect = CitationResolverError("Crossref request timed out.")
        mock_openalex.side_effect = CitationResolverError("OpenAlex request timed out.")
        mock_semantic_scholar.side_effect = CitationResolverError("Semantic Scholar request timed out.")

        with pytest.raises(CitationResolverError):
            resolve_doi("10.1038/s41586-020-2649-2", client=MagicMock())


class TestCitationApi:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    @patch("app.api.routes.citations.resolve_doi")
    def test_resolve_valid_doi(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = _map_crossref_message(
            CROSSREF_MESSAGE,
            "10.1038/s41586-020-2649-2",
        )

        response = self.client.post(
            "/api/citations/resolve",
            json={"doi": "10.1038/s41586-020-2649-2"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["doi"] == "10.1038/s41586-020-2649-2"
        assert body["source"] == "crossref"

    def test_resolve_invalid_doi(self) -> None:
        response = self.client.post(
            "/api/citations/resolve",
            json={"doi": "invalid-doi"},
        )
        assert response.status_code == 400

    @patch("app.api.routes.citations.resolve_doi")
    def test_resolve_not_found(self, mock_resolve: MagicMock) -> None:
        mock_resolve.side_effect = CitationNotFoundError("Citation not found.")

        response = self.client.post(
            "/api/citations/resolve",
            json={"doi": "10.1038/s41586-020-2649-2"},
        )
        assert response.status_code == 404


class TestHttpClientIntegration:
    @patch("httpx.Client.get")
    def test_crossref_success_via_http(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(200, {"message": CROSSREF_MESSAGE})

        result = resolve_doi("10.1038/s41586-020-2649-2")

        assert result.source == "crossref"
        assert mock_get.call_count == 1

    @patch("httpx.Client.get")
    def test_openalex_fallback_via_http(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = [
            _mock_response(404, {"message": "Resource not found."}),
            _mock_response(200, OPENALEX_WORK),
        ]

        result = resolve_doi("10.1038/s41586-020-2649-2")

        assert result.source == "openalex"
        assert mock_get.call_count == 2

    @patch("httpx.Client.get")
    def test_crossref_timeout(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = httpx.TimeoutException("timeout")

        with pytest.raises(CitationResolverError):
            resolve_doi("10.1038/s41586-020-2649-2")
