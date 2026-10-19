from __future__ import annotations

from app.schemas.evidence import EvidenceItem
from app.schemas.verification import (
    AdjudicatorAnalysis,
    DefenderAnalysis,
    ProsecutorAnalysis,
    Verdict,
)
from app.services.verification_validator import validate_verification_result


def _evidence(
    chunk_id: str,
    *,
    relevance: float,
    overlap: float,
    text: str = "Supporting evidence text.",
) -> EvidenceItem:
    return EvidenceItem(
        chunk_id=chunk_id,
        section="Results",
        chunk_index=0,
        text=text,
        relevance_score=relevance,
        claim_overlap=overlap,
        numeric_overlap=0.0,
    )


def _strong_evidence(chunk_id: str = "c1", text: str = "Direct supporting statement.") -> EvidenceItem:
    return _evidence(chunk_id, relevance=0.82, overlap=0.76, text=text)


def _weak_evidence(chunk_id: str = "c1") -> EvidenceItem:
    return _evidence(
        chunk_id,
        relevance=0.05,
        overlap=0.04,
        text="Unrelated background information.",
    )


def _prosecutor(**overrides: object) -> ProsecutorAnalysis:
    payload = {
        "agent": "prosecutor",
        "analysis": "Prosecutor analysis.",
        "stance": "neutral",
        "key_points": [],
        "supporting_evidence": [],
        "contradicting_evidence": [],
        "confidence": 0.6,
    }
    payload.update(overrides)
    return ProsecutorAnalysis(**payload)


def _defender(**overrides: object) -> DefenderAnalysis:
    payload = {
        "agent": "defender",
        "analysis": "Defender analysis.",
        "stance": "supportive",
        "key_points": [],
        "supporting_evidence": ["c1"],
        "contradicting_evidence": [],
        "confidence": 0.7,
    }
    payload.update(overrides)
    return DefenderAnalysis(**payload)


def _adjudicator(**overrides: object) -> AdjudicatorAnalysis:
    payload = {
        "agent": "adjudicator",
        "analysis": "Final analysis.",
        "verdict": Verdict.SUPPORTS,
        "confidence": 0.85,
        "reasoning": "Reasoning.",
        "supporting_evidence": ["c1"],
        "contradicting_evidence": [],
        "suggested_correction": None,
    }
    payload.update(overrides)
    return AdjudicatorAnalysis(**payload)


class TestVerificationValidator:
    def test_supports_with_strong_supporting_evidence(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(stance="neutral"),
            defender=_defender(supporting_evidence=["c1"]),
            adjudicator=_adjudicator(
                verdict=Verdict.SUPPORTS,
                confidence=0.88,
                supporting_evidence=["c1"],
            ),
        )

        assert result.verdict == Verdict.SUPPORTS
        assert result.confidence >= 0.74
        assert result.agent_agreement is True

    def test_supports_with_weak_irrelevant_evidence_is_downgraded(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_weak_evidence()],
            prosecutor=_prosecutor(stance="skeptical"),
            defender=_defender(
                stance="neutral",
                supporting_evidence=[],
                contradicting_evidence=[],
            ),
            adjudicator=_adjudicator(
                verdict=Verdict.SUPPORTS,
                confidence=0.9,
                supporting_evidence=[],
            ),
        )

        assert result.verdict == Verdict.INSUFFICIENT
        assert result.confidence <= 0.5
        assert any("INSUFFICIENT" in warning for warning in result.validation_warnings)

    def test_overstated_with_strong_evidence_is_preserved(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy by 40%.",
            evidence=[_strong_evidence(text="The method improves accuracy by 12%.")],
            prosecutor=_prosecutor(contradicting_evidence=["c1"]),
            defender=_defender(supporting_evidence=["c1"]),
            adjudicator=_adjudicator(
                verdict=Verdict.OVERSTATED,
                confidence=0.8,
                supporting_evidence=["c1"],
                suggested_correction="The method improves accuracy by about 12%.",
            ),
        )

        assert result.verdict == Verdict.OVERSTATED
        assert result.suggested_correction == "The method improves accuracy by about 12%."

    def test_contradicts_with_strong_contradictory_evidence(self) -> None:
        result = validate_verification_result(
            claim="The treatment reduces mortality.",
            evidence=[_strong_evidence(text="No mortality reduction was observed.")],
            prosecutor=_prosecutor(contradicting_evidence=["c1"], stance="skeptical"),
            defender=_defender(supporting_evidence=[], stance="neutral"),
            adjudicator=_adjudicator(
                verdict=Verdict.CONTRADICTS,
                confidence=0.82,
                reasoning='The same mortality endpoint says "No mortality reduction was observed."; this conflicts with the claimed reduction.',
                supporting_evidence=[],
                contradicting_evidence=["c1"],
            ),
        )

        assert result.verdict == Verdict.CONTRADICTS
        assert result.original_verdict == Verdict.CONTRADICTS

    def test_insufficient_with_no_useful_evidence(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_weak_evidence()],
            prosecutor=_prosecutor(stance="skeptical"),
            defender=_defender(stance="neutral", supporting_evidence=[]),
            adjudicator=_adjudicator(
                verdict=Verdict.INSUFFICIENT,
                confidence=0.4,
                supporting_evidence=[],
            ),
        )

        assert result.verdict == Verdict.INSUFFICIENT
        assert result.suggested_correction is None

    def test_fabricated_with_related_evidence_is_downgraded(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(),
            defender=_defender(),
            adjudicator=_adjudicator(
                verdict=Verdict.FABRICATED,
                confidence=0.7,
                supporting_evidence=["c1"],
            ),
        )

        assert result.verdict == Verdict.INSUFFICIENT
        assert any("FABRICATED" in warning for warning in result.validation_warnings)

    def test_adjudicator_supports_without_supporting_evidence_is_flagged(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(),
            defender=_defender(supporting_evidence=["c1"]),
            adjudicator=_adjudicator(
                verdict=Verdict.SUPPORTS,
                confidence=0.86,
                supporting_evidence=[],
            ),
        )

        assert result.verdict == Verdict.INSUFFICIENT
        assert any("without supporting evidence" in warning for warning in result.validation_warnings)

    def test_adjudicator_contradicts_without_contradicting_evidence_is_adjusted(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence(text="The method improves accuracy in experiments.")],
            prosecutor=_prosecutor(supporting_evidence=["c1"], contradicting_evidence=[]),
            defender=_defender(supporting_evidence=["c1"]),
            adjudicator=_adjudicator(
                verdict=Verdict.CONTRADICTS,
                confidence=0.8,
                supporting_evidence=["c1"],
                contradicting_evidence=[],
            ),
        )

        assert result.verdict == Verdict.INSUFFICIENT
        assert any("CONTRADICTS" in warning for warning in result.validation_warnings)

    def test_prosecutor_defender_disagreement_is_detected(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="skeptical",
                contradicting_evidence=["c1"],
                supporting_evidence=[],
            ),
            defender=_defender(
                stance="supportive",
                supporting_evidence=["c1"],
                contradicting_evidence=[],
            ),
            adjudicator=_adjudicator(verdict=Verdict.OVERSTATED, suggested_correction="Reduced claim."),
        )

        assert result.agent_agreement is False

    def test_high_confidence_with_weak_evidence_is_reduced(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_weak_evidence()],
            prosecutor=_prosecutor(),
            defender=_defender(supporting_evidence=[], stance="neutral"),
            adjudicator=_adjudicator(
                verdict=Verdict.INSUFFICIENT,
                confidence=0.95,
                supporting_evidence=[],
            ),
        )

        assert result.confidence < 0.95
        assert result.confidence <= 0.45

    def test_overstated_warns_when_correction_missing(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy by 40%.",
            evidence=[_strong_evidence(text="The method improves accuracy by 12%.")],
            prosecutor=_prosecutor(contradicting_evidence=["c1"]),
            defender=_defender(supporting_evidence=["c1"]),
            adjudicator=_adjudicator(
                verdict=Verdict.OVERSTATED,
                suggested_correction=None,
                supporting_evidence=["c1"],
            ),
        )

        assert result.verdict == Verdict.OVERSTATED
        assert result.suggested_correction is None
        assert any("lacks a suggested correction" in warning for warning in result.validation_warnings)

    def test_supports_removes_suggested_correction(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(),
            defender=_defender(),
            adjudicator=_adjudicator(
                verdict=Verdict.SUPPORTS,
                suggested_correction="Unnecessary correction.",
                supporting_evidence=["c1"],
            ),
        )

        assert result.suggested_correction is None
        assert any("Suggested correction removed" in warning for warning in result.validation_warnings)

    def test_insufficient_removes_fabricated_correction(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_weak_evidence()],
            prosecutor=_prosecutor(),
            defender=_defender(supporting_evidence=[], stance="neutral"),
            adjudicator=_adjudicator(
                verdict=Verdict.INSUFFICIENT,
                suggested_correction="Invented corrected claim.",
                supporting_evidence=[],
            ),
        )

        assert result.suggested_correction is None
        assert any("Suggested correction removed" in warning for warning in result.validation_warnings)

    def test_agent_evidence_ids_must_exist_in_retrieved_evidence(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence("c1")],
            prosecutor=_prosecutor(supporting_evidence=["missing"]),
            defender=_defender(supporting_evidence=["ghost"]),
            adjudicator=_adjudicator(
                supporting_evidence=["c1", "missing"],
                contradicting_evidence=["ghost"],
            ),
        )

        assert any(
            "not in retrieved evidence" in warning for warning in result.validation_warnings
        )