from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.schemas.evidence import (
    EvidenceItem,
    EvidencePaperSummary,
    EvidenceRetrievalResponse,
    EvidenceRetrievalStatus,
)
from app.schemas.verification import (
    AdjudicatorAnalysis,
    DefenderAnalysis,
    ProsecutorAnalysis,
    VerificationStatus,
    Verdict,
)
from app.services.llm.provider import LLMResponseError, LLMUnavailableError, UnavailableLLMProvider
from app.services.verification_service import analyze_verification
from app.tests.test_agents import MockLLMProvider


PAPER = EvidencePaperSummary(
    paper_id="10.1000/test",
    doi="10.1000/test",
    title="Example Paper",
)

EVIDENCE = [
    EvidenceItem(
        chunk_id="c1",
        section="Results",
        chunk_index=0,
        text="The proposed method improves accuracy by 12%.",
        relevance_score=0.8,
        claim_overlap=0.7,
        numeric_overlap=0.5,
    )
]

SUCCESS_EVIDENCE = EvidenceRetrievalResponse(
    status=EvidenceRetrievalStatus.SUCCESS,
    claim="The method improves accuracy by 40%.",
    paper=PAPER,
    evidence=EVIDENCE,
    total_chunks_considered=1,
)


class TestVerificationService:
    @patch("app.services.verification_service.retrieve_evidence_for_claim")
    def test_end_to_end_mocked_verification(self, mock_evidence: MagicMock) -> None:
        mock_evidence.return_value = SUCCESS_EVIDENCE
        llm = MockLLMProvider(
            [
                ProsecutorAnalysis(
                    agent="prosecutor",
                    analysis="Magnitude mismatch.",
                    stance="skeptical",
                    key_points=["12% vs 40%"],
                    supporting_evidence=[],
                    contradicting_evidence=["c1"],
                    confidence=0.7,
                ),
                DefenderAnalysis(
                    agent="defender",
                    analysis="Direction supported.",
                    stance="supportive",
                    key_points=["Accuracy improved"],
                    supporting_evidence=["c1"],
                    contradicting_evidence=[],
                    confidence=0.65,
                ),
                AdjudicatorAnalysis(
                    agent="adjudicator",
                    analysis="Claim is directionally supported but overstated.",
                    verdict=Verdict.OVERSTATED,
                    confidence=0.78,
                    reasoning="Evidence reports 12%, not 40%.",
                    supporting_evidence=["c1"],
                    contradicting_evidence=["c1"],
                    suggested_correction="The method improves accuracy by about 12%.",
                ),
            ]
        )

        result = analyze_verification(
            "The method improves accuracy by 40%.",
            "10.1000/test",
            llm=llm,
        )

        assert result.status == VerificationStatus.SUCCESS
        assert result.verdict == Verdict.OVERSTATED
        assert result.prosecutor is not None
        assert result.defender is not None
        assert result.adjudicator is not None
        assert result.evidence[0].chunk_id == "c1"
        assert len(llm.prompts) == 3

    @patch("app.services.verification_service.retrieve_evidence_for_claim")
    def test_missing_source_requires_recovery_without_agents(self, mock_evidence: MagicMock) -> None:
        mock_evidence.return_value = EvidenceRetrievalResponse(
            status=EvidenceRetrievalStatus.FULL_TEXT_UNAVAILABLE,
            claim="The method improves accuracy by 40%.",
            paper=PAPER,
            evidence=[],
            detail="Full text unavailable.",
        )

        result = analyze_verification("The method improves accuracy by 40%.", "10.1000/test")

        assert result.status == VerificationStatus.SOURCE_REQUIRED
        assert result.verdict is None and result.confidence is None
        assert result.source_recovery.required
        assert result.prosecutor is None

    @patch("app.services.verification_service.retrieve_evidence_for_claim")
    def test_llm_unavailable(self, mock_evidence: MagicMock) -> None:
        mock_evidence.return_value = SUCCESS_EVIDENCE

        result = analyze_verification(
            "The method improves accuracy by 40%.",
            "10.1000/test",
            llm=UnavailableLLMProvider(),
        )

        assert result.status == VerificationStatus.LLM_UNAVAILABLE
        assert result.verdict is None

    @patch("app.services.verification_service.retrieve_evidence_for_claim")
    def test_malformed_agent_output(self, mock_evidence: MagicMock) -> None:
        mock_evidence.return_value = SUCCESS_EVIDENCE

        class BrokenLLM(UnavailableLLMProvider):
            def generate(self, prompt, *, system=None, response_model=None):
                raise LLMResponseError("Invalid structured output.")

        result = analyze_verification(
            "The method improves accuracy by 40%.",
            "10.1000/test",
            llm=BrokenLLM(),
        )

        assert result.status == VerificationStatus.VERIFICATION_FAILED
        assert "Invalid structured output" in (result.detail or "")

    @patch("app.services.verification_service.retrieve_evidence_for_claim")
    def test_no_relevant_evidence(self, mock_evidence: MagicMock) -> None:
        mock_evidence.return_value = EvidenceRetrievalResponse(
            status=EvidenceRetrievalStatus.NO_RELEVANT_EVIDENCE,
            claim="The method improves accuracy by 40%.",
            paper=PAPER,
            evidence=[],
            total_chunks_considered=3,
            detail="No relevant evidence.",
        )

        result = analyze_verification("The method improves accuracy by 40%.", "10.1000/test")

        assert result.status == VerificationStatus.INSUFFICIENT_EVIDENCE

    @patch("app.services.verification_service.retrieve_evidence_for_claim")
    def test_llm_rate_limit_429_returns_verification_failed(self, mock_evidence: MagicMock) -> None:
        from app.services.llm.provider import LLMRateLimitError

        mock_evidence.return_value = SUCCESS_EVIDENCE

        class RateLimitedLLM(UnavailableLLMProvider):
            def generate(self, prompt, *, system=None, response_model=None):
                raise LLMRateLimitError("LLM provider rate limit exceeded (HTTP 429). Please retry shortly.")

        result = analyze_verification(
            "The method improves accuracy by 40%.",
            "10.1000/test",
            llm=RateLimitedLLM(),
        )

        assert result.status == VerificationStatus.VERIFICATION_FAILED
        assert result.verdict is None
        assert result.confidence is None
        assert result.prosecutor is None
        assert result.defender is None
        assert result.adjudicator is None
        assert "429" in (result.detail or "")

    def test_invalid_claim(self) -> None:
        from app.utils.claim_preprocessor import InvalidClaimError

        with pytest.raises(InvalidClaimError):
            analyze_verification("   ", "10.1000/test")
