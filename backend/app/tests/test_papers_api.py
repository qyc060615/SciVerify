from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.paper import (
    PaperMetadata,
    PaperRetrievalStatus,
    PaperSource,
    RetrievePaperResponse,
)
from app.services.paper_retriever import (
    DocumentRetrievalFailure,
    FullTextUnavailableError,
    PaperNotFoundError,
    PaperProviderError,
)


class TestPapersApi:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    @patch("app.api.routes.papers.retrieve_paper")
    def test_successful_retrieval(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.return_value = RetrievePaperResponse(
            status=PaperRetrievalStatus.SUCCESS,
            paper=PaperMetadata(
                paper_id="10.1038/s41586-020-2649-2",
                doi="10.1038/s41586-020-2649-2",
                title="Example Paper",
                full_text_available=True,
                full_text_format="pdf",
            ),
            sections=[],
            chunks=[],
            source=PaperSource(url="https://example.org/paper.pdf", provider="openalex"),
        )

        response = self.client.post(
            "/api/papers/retrieve",
            json={"doi": "10.1038/s41586-020-2649-2"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["paper"]["full_text_available"] is True

    @patch("app.api.routes.papers.retrieve_paper")
    def test_metadata_only_response(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.return_value = RetrievePaperResponse(
            status=PaperRetrievalStatus.METADATA_ONLY,
            paper=PaperMetadata(
                paper_id="10.1038/s41586-020-2649-2",
                doi="10.1038/s41586-020-2649-2",
                title="Example Paper",
                full_text_available=False,
            ),
            sections=[],
            chunks=[],
            source=PaperSource(url="https://openalex.org/W123", provider="openalex"),
        )

        response = self.client.post(
            "/api/papers/retrieve",
            json={"doi": "10.1038/s41586-020-2649-2"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "metadata_only"

    @patch("app.api.routes.papers.retrieve_paper")
    def test_full_text_unavailable(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.return_value = RetrievePaperResponse(
            status=PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE,
            paper=PaperMetadata(
                paper_id="10.1038/s41586-020-2649-2",
                doi="10.1038/s41586-020-2649-2",
                title="Example Paper",
                full_text_available=False,
            ),
            sections=[],
            chunks=[],
            source=PaperSource(url="https://openalex.org/W123", provider="openalex"),
        )

        response = self.client.post(
            "/api/papers/retrieve",
            json={"doi": "10.1038/s41586-020-2649-2"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "full_text_unavailable"

    def test_invalid_doi(self) -> None:
        response = self.client.post(
            "/api/papers/retrieve",
            json={"doi": "invalid-doi"},
        )
        assert response.status_code == 400

    @patch("app.api.routes.papers.retrieve_paper")
    def test_paper_not_found(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.side_effect = PaperNotFoundError("Paper not found.")

        response = self.client.post(
            "/api/papers/retrieve",
            json={"doi": "10.1038/not-found"},
        )
        assert response.status_code == 404

    @patch("app.api.routes.papers.retrieve_paper")
    def test_provider_failure(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.side_effect = PaperProviderError("OpenAlex unavailable.")

        response = self.client.post(
            "/api/papers/retrieve",
            json={"doi": "10.1038/s41586-020-2649-2"},
        )
        assert response.status_code == 503

    @patch("app.api.routes.papers.retrieve_paper")
    def test_document_retrieval_failure(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.side_effect = DocumentRetrievalFailure("Document request timed out.")

        response = self.client.post(
            "/api/papers/retrieve",
            json={"doi": "10.1038/s41586-020-2649-2"},
        )
        assert response.status_code == 503

    @patch("app.api.routes.papers.retrieve_paper")
    def test_parsing_failure_returns_http_200(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.return_value = RetrievePaperResponse(
            status=PaperRetrievalStatus.PARSING_FAILURE,
            paper=PaperMetadata(
                paper_id="10.1038/s41586-020-2649-2",
                doi="10.1038/s41586-020-2649-2",
                title="Array programming with NumPy",
                full_text_available=True,
                full_text_format="pdf",
                full_text_url="https://www.nature.com/articles/s41586-020-2649-2.pdf",
            ),
            sections=[],
            chunks=[],
            source=PaperSource(
                url="https://www.nature.com/articles/s41586-020-2649-2.pdf",
                provider="openalex",
            ),
            detail="PDF document contains no extractable text.",
        )

        response = self.client.post(
            "/api/papers/retrieve",
            json={"doi": "10.1038/s41586-020-2649-2"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "parsing_failure"
        assert body["paper"]["full_text_available"] is True
        assert body["paper"]["full_text_format"] == "pdf"
        assert body["sections"] == []
        assert body["chunks"] == []
        assert body["detail"] == "PDF document contains no extractable text."

    @patch("app.api.routes.papers.retrieve_paper")
    def test_full_text_unavailable_error(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.side_effect = FullTextUnavailableError("Full text unavailable from sources.")

        response = self.client.post(
            "/api/papers/retrieve",
            json={"doi": "10.1038/s41586-020-2649-2"},
        )
        assert response.status_code == 503
        assert "Full text unavailable" in response.json()["detail"]
