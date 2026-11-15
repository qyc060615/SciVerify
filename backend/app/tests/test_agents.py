from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.schemas.evidence import EvidenceItem
from app.schemas.verification import (
    AdjudicatorAnalysis,
    DefenderAnalysis,
    ProsecutorAnalysis,
    Verdict,
)
from app.services.agents import run_adjudicator, run_defender, run_prosecutor
from app.services.llm.provider import LLMProvider

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(LLMProvider):
    def __init__(self, responses: list[BaseModel]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_model: type[T] | None = None,
    ) -> T | str:
        self.prompts.append(prompt)
        result = self.responses.pop(0)
        if response_model is not None and not isinstance(result, response_model):
            return response_model.model_validate(result.model_dump())
        return result


EVIDENCE = [
    EvidenceItem(
        chunk_id="c1",
        section="Results",
        chunk_index=0,
        text="The proposed method improves accuracy by 12% on software tasks.",
        relevance_score=0.8,
        claim_overlap=0.7,
        numeric_overlap=0.5,
        claim_numbers=["40%"],
        evidence_numbers=["12%"],
    )
]

CLAIM = "The method improves accuracy by 40%."


class TestAgents:
    def test_prosecutor_receives_claim_and_evidence(self) -> None:
        llm = MockLLMProvider(
            [
                ProsecutorAnalysis(
                    agent="prosecutor",
                    analysis="The evidence reports 12%, not 40%.",
                    stance="skeptical",
                    key_points=["Numeric mismatch"],
                    supporting_evidence=[],
                    contradicting_evidence=["c1", "missing"],
                    confidence=0.72,
                )
            ]
        )

        result = run_prosecutor(CLAIM, EVIDENCE, llm)

        assert CLAIM in llm.prompts[0]
        assert "c1" in llm.prompts[0]
        assert result.contradicting_evidence == ["c1"]

    def test_defender_receives_claim_and_evidence(self) -> None:
        llm = MockLLMProvider(
            [
                DefenderAnalysis(
                    agent="defender",
                    analysis="The evidence supports improved accuracy.",
                    stance="supportive",
                    key_points=["Direction supported"],
                    supporting_evidence=["c1"],
                    contradicting_evidence=[],
                    confidence=0.68,
                )
            ]
        )

        result = run_defender(CLAIM, EVIDENCE, llm)

        assert CLAIM in llm.prompts[0]
        assert result.supporting_evidence == ["c1"]

    def test_adjudicator_receives_both_analyses(self) -> None:
        prosecutor = ProsecutorAnalysis(
            agent="prosecutor",
            analysis="Overstated magnitude.",
            stance="skeptical",
            key_points=["12% vs 40%"],
            supporting_evidence=[],
            contradicting_evidence=["c1"],
            confidence=0.7,
        )
        defender = DefenderAnalysis(
            agent="defender",
            analysis="Direction supported.",
            stance="supportive",
            key_points=["Accuracy improved"],
            supporting_evidence=["c1"],
            contradicting_evidence=[],
            confidence=0.65,
        )
        llm = MockLLMProvider(
            [
                AdjudicatorAnalysis(
                    agent="adjudicator",
                    analysis="Claim direction is supported but magnitude is overstated.",
                    verdict=Verdict.OVERSTATED,
                    confidence=0.78,
                    reasoning="Evidence reports 12%, not 40%.",
                    supporting_evidence=["c1"],
                    contradicting_evidence=["c1"],
                    suggested_correction="The method improves accuracy by about 12%.",
                )
            ]
        )

        result = run_adjudicator(CLAIM, EVIDENCE, prosecutor, defender, llm)

        assert "Prosecutor analysis" in llm.prompts[0]
        assert "Defender analysis" in llm.prompts[0]
        assert result.verdict == Verdict.OVERSTATED


class TestVerdictOutputs:
    def _adjudicator(self, verdict: Verdict) -> AdjudicatorAnalysis:
        return AdjudicatorAnalysis(
            agent="adjudicator",
            analysis=f"Verdict {verdict.value}",
            verdict=verdict,
            confidence=0.7,
            reasoning="Test reasoning.",
            supporting_evidence=["c1"],
            contradicting_evidence=[],
        )

    def test_supports_verdict(self) -> None:
        result = self._adjudicator(Verdict.SUPPORTS)
        assert result.verdict == Verdict.SUPPORTS

    def test_overstated_verdict(self) -> None:
        result = self._adjudicator(Verdict.OVERSTATED)
        assert result.verdict == Verdict.OVERSTATED

    def test_contradicts_verdict(self) -> None:
        result = self._adjudicator(Verdict.CONTRADICTS)
        assert result.verdict == Verdict.CONTRADICTS

    def test_insufficient_verdict(self) -> None:
        result = self._adjudicator(Verdict.INSUFFICIENT)
        assert result.verdict == Verdict.INSUFFICIENT

    def test_fabricated_verdict(self) -> None:
        result = self._adjudicator(Verdict.FABRICATED)
        assert result.verdict == Verdict.FABRICATED
