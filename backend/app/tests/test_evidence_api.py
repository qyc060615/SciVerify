from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.evidence import EvidenceRetrievalResponse
from app.schemas.paper import (
    EvidenceChunk,
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


class TestEvidenceApi:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    @patch("app.api.routes.evidence.retrieve_paper")
    def test_successful_retrieval(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.return_value = RetrievePaperResponse(
            status=PaperRetrievalStatus.SUCCESS,
            paper=PaperMetadata(
                paper_id="10.1000/test",
                doi="10.1000/test",
                title="Example Paper",
            ),
            chunks=[
                EvidenceChunk(
                    chunk_id="c1",
                    paper_id="10.1000/test",
                    section="Results",
                    chunk_index=0,
                    text="The method improves accuracy by 12% on software tasks.",
                    source_url="https://example.org/paper.pdf",
                    page=4,
                )
            ],
            source=PaperSource(url="https://example.org/paper.pdf", provider="openalex"),
        )

        response = self.client.post(
            "/api/evidence/retrieve",
            json={
                "claim": "The method improves accuracy by 40%.",
                "doi": "10.1000/test",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["paper"]["doi"] == "10.1000/test"
        assert len(body["evidence"]) >= 1
        assert body["evidence"][0]["relevance_score"] >= 0.0
        assert body["total_chunks_considered"] == 1

    def test_empty_claim(self) -> None:
        response = self.client.post(
            "/api/evidence/retrieve",
            json={"claim": "   ", "doi": "10.1000/test"},
        )
        assert response.status_code == 400

    def test_invalid_doi(self) -> None:
        response = self.client.post(
            "/api/evidence/retrieve",
            json={"claim": "accuracy improved", "doi": "invalid-doi"},
        )
        assert response.status_code == 400

    @patch("app.api.routes.evidence.retrieve_paper")
    def test_missing_paper(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.side_effect = PaperNotFoundError("Paper not found.")

        response = self.client.post(
            "/api/evidence/retrieve",
            json={"claim": "accuracy improved", "doi": "10.1000/missing"},
        )
        assert response.status_code == 404

    @patch("app.api.routes.evidence.retrieve_paper")
    def test_no_full_text(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.return_value = RetrievePaperResponse(
            status=PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE,
            paper=PaperMetadata(paper_id="10.1000/test", doi="10.1000/test", title="Paper"),
            chunks=[],
            source=PaperSource(url="https://openalex.org/W1", provider="openalex"),
        )

        response = self.client.post(
            "/api/evidence/retrieve",
            json={"claim": "accuracy improved", "doi": "10.1000/test"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "full_text_unavailable"
        assert response.json()["evidence"] == []

    @patch("app.api.routes.evidence.retrieve_paper")
    def test_no_chunks(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.return_value = RetrievePaperResponse(
            status=PaperRetrievalStatus.SUCCESS,
            paper=PaperMetadata(paper_id="10.1000/test", doi="10.1000/test", title="Paper"),
            chunks=[],
            source=PaperSource(url="https://example.org/paper.pdf", provider="openalex"),
        )

        response = self.client.post(
            "/api/evidence/retrieve",
            json={"claim": "accuracy improved", "doi": "10.1000/test"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "no_chunks"

    @patch("app.api.routes.evidence.retrieve_paper")
    def test_provider_failure(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.side_effect = PaperProviderError("OpenAlex unavailable.")

        response = self.client.post(
            "/api/evidence/retrieve",
            json={"claim": "accuracy improved", "doi": "10.1000/test"},
        )
        assert response.status_code == 503

    @patch("app.api.routes.evidence.retrieve_paper")
    def test_document_retrieval_failure(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.side_effect = DocumentRetrievalFailure("Document request timed out.")

        response = self.client.post(
            "/api/evidence/retrieve",
            json={"claim": "accuracy improved", "doi": "10.1000/test"},
        )
        assert response.status_code == 503

    @patch("app.api.routes.evidence.retrieve_paper")
    def test_no_relevant_evidence(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.return_value = RetrievePaperResponse(
            status=PaperRetrievalStatus.SUCCESS,
            paper=PaperMetadata(paper_id="10.1000/test", doi="10.1000/test", title="Paper"),
            chunks=[
                EvidenceChunk(
                    chunk_id="c1",
                    paper_id="10.1000/test",
                    section="References",
                    chunk_index=0,
                    text="Completely unrelated bibliography content.",
                )
            ],
            source=PaperSource(url="https://example.org/paper.pdf", provider="openalex"),
        )

        response = self.client.post(
            "/api/evidence/retrieve",
            json={"claim": "quantum chromodynamics plasma viscosity", "doi": "10.1000/test"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"no_relevant_evidence", "success"}

    @patch("app.api.routes.evidence.retrieve_paper")
    def test_successful_response_schema(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.return_value = RetrievePaperResponse(
            status=PaperRetrievalStatus.SUCCESS,
            paper=PaperMetadata(paper_id="10.1000/test", doi="10.1000/test", title="Paper"),
            chunks=[
                EvidenceChunk(
                    chunk_id="c1",
                    paper_id="10.1000/test",
                    section="Results",
                    chunk_index=0,
                    text="accuracy improved by 12%",
                )
            ],
            source=PaperSource(url="https://example.org/paper.pdf", provider="openalex"),
        )

        response = self.client.post(
            "/api/evidence/retrieve",
            json={"claim": "accuracy improved by 40%", "doi": "10.1000/test"},
        )

        assert response.status_code == 200
        EvidenceRetrievalResponse.model_validate(response.json())

    @patch("app.api.routes.evidence.retrieve_paper")
    def test_full_text_unavailable_error(self, mock_retrieve: MagicMock) -> None:
        mock_retrieve.side_effect = FullTextUnavailableError("Full text could not be found.")

        response = self.client.post(
            "/api/evidence/retrieve",
            json={"claim": "accuracy improved by 40%", "doi": "10.1000/test"},
        )
        assert response.status_code == 503
        assert "Full text could not be found." in response.json()["detail"]
