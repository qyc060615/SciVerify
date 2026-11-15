from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.evidence import EvidencePaperSummary
from app.schemas.verification import (
    VerificationResponse,
    VerificationStatus,
    Verdict,
)
from app.services.paper_retriever import (
    DocumentRetrievalFailure,
    FullTextUnavailableError,
    PaperNotFoundError,
    PaperProviderError,
)


class TestVerificationApi:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    @patch("app.api.routes.verification.analyze_verification")
    def test_successful_request(self, mock_analyze: MagicMock) -> None:
        mock_analyze.return_value = VerificationResponse(
            status=VerificationStatus.SUCCESS,
            claim="The method improves accuracy by 40%.",
            verdict=Verdict.OVERSTATED,
            confidence=0.78,
            summary="Claim is directionally supported but overstated.",
            reasoning="Evidence reports 12%, not 40%.",
            paper=EvidencePaperSummary(
                paper_id="10.1000/test",
                doi="10.1000/test",
                title="Example Paper",
            ),
            evidence=[],
        )

        response = self.client.post(
            "/api/verification/analyze",
            json={
                "claim": "The method improves accuracy by 40%.",
                "doi": "10.1000/test",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["verdict"] == "OVERSTATED"

    def test_empty_claim(self) -> None:
        response = self.client.post(
            "/api/verification/analyze",
            json={"claim": "   ", "doi": "10.1000/test"},
        )
        assert response.status_code == 400

    def test_invalid_doi(self) -> None:
        response = self.client.post(
            "/api/verification/analyze",
            json={"claim": "accuracy improved", "doi": "invalid-doi"},
        )
        assert response.status_code == 400

    @patch("app.api.routes.verification.analyze_verification")
    def test_citation_failure(self, mock_analyze: MagicMock) -> None:
        mock_analyze.side_effect = PaperNotFoundError("Paper not found.")

        response = self.client.post(
            "/api/verification/analyze",
            json={"claim": "accuracy improved", "doi": "10.1000/missing"},
        )
        assert response.status_code == 404

    @patch("app.api.routes.verification.analyze_verification")
    def test_provider_failure(self, mock_analyze: MagicMock) -> None:
        mock_analyze.side_effect = PaperProviderError("OpenAlex unavailable.")

        response = self.client.post(
            "/api/verification/analyze",
            json={"claim": "accuracy improved", "doi": "10.1000/test"},
        )
        assert response.status_code == 503

    @patch("app.api.routes.verification.analyze_verification")
    def test_document_retrieval_failure(self, mock_analyze: MagicMock) -> None:
        mock_analyze.side_effect = DocumentRetrievalFailure("Document request timed out.")

        response = self.client.post(
            "/api/verification/analyze",
            json={"claim": "accuracy improved", "doi": "10.1000/test"},
        )
        assert response.status_code == 503

    @patch("app.api.routes.verification.analyze_verification")
    def test_insufficient_evidence(self, mock_analyze: MagicMock) -> None:
        mock_analyze.return_value = VerificationResponse(
            status=VerificationStatus.INSUFFICIENT_EVIDENCE,
            claim="accuracy improved",
            verdict=Verdict.INSUFFICIENT,
            confidence=0.0,
            summary="Insufficient evidence available.",
            reasoning="No usable evidence chunks.",
            paper=EvidencePaperSummary(
                paper_id="10.1000/test",
                doi="10.1000/test",
                title="Example Paper",
            ),
            evidence=[],
            detail="Full text unavailable.",
        )

        response = self.client.post(
            "/api/verification/analyze",
            json={"claim": "accuracy improved", "doi": "10.1000/test"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "insufficient_evidence"

    @patch("app.api.routes.verification.analyze_verification")
    def test_llm_unavailable(self, mock_analyze: MagicMock) -> None:
        mock_analyze.return_value = VerificationResponse(
            status=VerificationStatus.LLM_UNAVAILABLE,
            claim="accuracy improved",
            paper=EvidencePaperSummary(
                paper_id="10.1000/test",
                doi="10.1000/test",
                title="Example Paper",
            ),
            evidence=[],
            detail="LLM provider is not configured.",
        )

        response = self.client.post(
            "/api/verification/analyze",
            json={"claim": "accuracy improved", "doi": "10.1000/test"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "llm_unavailable"

    @patch("app.api.routes.verification.analyze_verification")
    def test_successful_response_schema(self, mock_analyze: MagicMock) -> None:
        mock_analyze.return_value = VerificationResponse(
            status=VerificationStatus.SUCCESS,
            claim="accuracy improved",
            verdict=Verdict.SUPPORTS,
            confidence=0.9,
            summary="Supported.",
            reasoning="Direct support in Results.",
            paper=EvidencePaperSummary(
                paper_id="10.1000/test",
                doi="10.1000/test",
                title="Example Paper",
            ),
            evidence=[],
        )

        response = self.client.post(
            "/api/verification/analyze",
            json={"claim": "accuracy improved", "doi": "10.1000/test"},
        )

        assert response.status_code == 200
        VerificationResponse.model_validate(response.json())

    @patch("app.api.routes.verification.analyze_verification")
    def test_full_text_unavailable_failure(self, mock_analyze: MagicMock) -> None:
        mock_analyze.side_effect = FullTextUnavailableError("Full text could not be found.")

        response = self.client.post(
            "/api/verification/analyze",
            json={"claim": "accuracy improved", "doi": "10.1000/test"},
        )
        assert response.status_code == 503
        assert "Full text could not be found." in response.json()["detail"]

    @patch("app.api.routes.verification.analyze_verification")
    def test_rate_limit_failed_status_response(self, mock_analyze: MagicMock) -> None:
        mock_analyze.return_value = VerificationResponse(
            status=VerificationStatus.VERIFICATION_FAILED,
            claim="accuracy improved",
            paper=EvidencePaperSummary(
                paper_id="10.1000/test",
                doi="10.1000/test",
                title="Example Paper",
            ),
            evidence=[],
            detail="LLM provider rate limit exceeded (HTTP 429). Please retry shortly.",
        )

        response = self.client.post(
            "/api/verification/analyze",
            json={"claim": "accuracy improved", "doi": "10.1000/test"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "verification_failed"
        assert "429" in data["detail"]
        assert data["verdict"] is None

    def test_health_endpoints(self) -> None:
        for path in ["/health", "/api/health"]:
            response = self.client.get(path)
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "service": "sciverify-backend"}

    def test_cors_headers(self) -> None:
        response = self.client.options(
            "/api/verification/analyze",
            headers={
                "Origin": "https://sciverify.vercel.app",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        assert (
            response.headers.get("access-control-allow-origin")
            == "https://sciverify.vercel.app"
        )


