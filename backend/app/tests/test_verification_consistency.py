"""Regression tests for verification result consistency.

These tests validate the deterministic rules in the verification pipeline
that must remain stable regardless of which LLM is in use.  No external
network or LLM calls are made.

Covered invariants
------------------
1. _agents_agree -- normal adversarial pattern with low-confidence defender -> agree
2. _agents_agree -- true disagreement (both high-confidence opposing) is detected
3. Verdict normalizer -- lowercase LLM output is accepted by AdjudicatorAnalysis
4. suggested_correction stripped for SUPPORTS by validator
5. suggested_correction stripped for INSUFFICIENT by validator
6. VerificationResponse.confidence is always calibrated, not raw LLM value
7. original_confidence holds the raw LLM value for auditing
8. Calibrated confidence is always in [0.0, 1.0]
9. Zero evidence yields zero confidence
10. SUPPORTS verdict not overridden by partial coverage warning
11. SUPPORTS without strong evidence caps confidence at 0.5
12. Verdict normalizer handles whitespace and mixed case
13. Invalid verdict raises ValidationError
"""

from __future__ import annotations

import pytest

from app.schemas.evidence import EvidenceItem
from app.schemas.verification import (
    AdjudicatorAnalysis,
    DefenderAnalysis,
    ProsecutorAnalysis,
    Verdict,
)
from app.services.verification_validator import validate_verification_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evidence(
    chunk_id: str = "c1",
    *,
    relevance: float = 0.8,
    overlap: float = 0.7,
    text: str = "Direct supporting statement.",
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


def _strong_evidence(chunk_id: str = "c1") -> EvidenceItem:
    return _evidence(chunk_id, relevance=0.82, overlap=0.76)


def _weak_evidence(chunk_id: str = "c1") -> EvidenceItem:
    return _evidence(
        chunk_id,
        relevance=0.05,
        overlap=0.04,
        text="Unrelated background information.",
    )


def _prosecutor(**overrides: object) -> ProsecutorAnalysis:
    payload: dict[str, object] = {
        "agent": "prosecutor",
        "analysis": "Prosecutor analysis.",
        "stance": "skeptical",
        "key_points": [],
        "supporting_evidence": [],
        "contradicting_evidence": ["c1"],
        "confidence": 0.7,
    }
    payload.update(overrides)
    return ProsecutorAnalysis(**payload)


def _defender(**overrides: object) -> DefenderAnalysis:
    payload: dict[str, object] = {
        "agent": "defender",
        "analysis": "Defender analysis.",
        "stance": "supportive",
        "key_points": [],
        "supporting_evidence": ["c1"],
        "contradicting_evidence": [],
        "confidence": 0.72,
    }
    payload.update(overrides)
    return DefenderAnalysis(**payload)


def _adjudicator(**overrides: object) -> AdjudicatorAnalysis:
    payload: dict[str, object] = {
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


# ---------------------------------------------------------------------------
# Agent agreement logic
# ---------------------------------------------------------------------------

class TestAgentAgreementLogic:
    def test_one_low_confidence_agent_does_not_trigger_disagreement(self) -> None:
        """Prosecutor challenges strongly but defender has low confidence (<0.5).
        This must NOT be detected as disagreement."""
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="skeptical",
                contradicting_evidence=["c1"],
                supporting_evidence=[],
                confidence=0.8,
            ),
            defender=_defender(
                stance="supportive",
                supporting_evidence=["c1"],
                contradicting_evidence=[],
                confidence=0.3,  # below 0.5 threshold
            ),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS),
        )
        assert result.agent_agreement is True

    def test_both_high_confidence_opposing_is_disagreement(self) -> None:
        """Both agents are strongly committed (>=0.5) to opposing conclusions.
        This must be detected as genuine disagreement."""
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="skeptical",
                contradicting_evidence=["c1"],
                supporting_evidence=[],
                confidence=0.85,
            ),
            defender=_defender(
                stance="supportive",
                supporting_evidence=["c1"],
                contradicting_evidence=[],
                confidence=0.9,
            ),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS),
        )
        assert result.agent_agreement is False

    def test_prosecutor_low_confidence_does_not_trigger_disagreement(self) -> None:
        """Prosecutor below threshold, defender strongly supports -> agree."""
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="skeptical",
                contradicting_evidence=["c1"],
                confidence=0.35,  # below 0.5
            ),
            defender=_defender(
                stance="supportive",
                supporting_evidence=["c1"],
                confidence=0.9,
            ),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS),
        )
        assert result.agent_agreement is True

    def test_neutral_prosecutor_is_agreement(self) -> None:
        """A neutral/non-challenging prosecutor should always produce agreement."""
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="neutral",
                contradicting_evidence=[],
                supporting_evidence=["c1"],
                confidence=0.6,
            ),
            defender=_defender(
                stance="supportive",
                supporting_evidence=["c1"],
                confidence=0.75,
            ),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS),
        )
        assert result.agent_agreement is True

    def test_at_threshold_boundary_is_disagreement(self) -> None:
        """Confidence exactly at 0.5 (>= threshold) must count as strongly committed."""
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="skeptical",
                contradicting_evidence=["c1"],
                confidence=0.5,  # exactly at boundary
            ),
            defender=_defender(
                stance="supportive",
                supporting_evidence=["c1"],
                confidence=0.5,  # exactly at boundary
            ),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS),
        )
        assert result.agent_agreement is False

    def test_below_threshold_boundary_is_agreement(self) -> None:
        """Confidence just below 0.5 must NOT count as strongly committed."""
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="skeptical",
                contradicting_evidence=["c1"],
                confidence=0.49,  # just below boundary
            ),
            defender=_defender(
                stance="supportive",
                supporting_evidence=["c1"],
                confidence=0.9,  # high but prosecutor is low
            ),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS),
        )
        assert result.agent_agreement is True


# ---------------------------------------------------------------------------
# Verdict normalization
# ---------------------------------------------------------------------------

class TestVerdictNormalization:
    def test_lowercase_verdict_is_accepted(self) -> None:
        adj = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Claim supported.",
            verdict="supports",  # type: ignore[arg-type]
            confidence=0.8,
            reasoning="Evidence is consistent.",
            supporting_evidence=[],
            contradicting_evidence=[],
        )
        assert adj.verdict == Verdict.SUPPORTS

    def test_mixed_case_verdict_is_normalized(self) -> None:
        adj = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Claim contradicts.",
            verdict="Contradicts",  # type: ignore[arg-type]
            confidence=0.75,
            reasoning="Contradicted by evidence.",
            supporting_evidence=[],
            contradicting_evidence=[],
        )
        assert adj.verdict == Verdict.CONTRADICTS

    def test_verdict_with_whitespace_is_normalized(self) -> None:
        adj = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Overstated.",
            verdict="  overstated  ",  # type: ignore[arg-type]
            confidence=0.7,
            reasoning="Magnitude mismatch.",
            supporting_evidence=[],
            contradicting_evidence=[],
        )
        assert adj.verdict == Verdict.OVERSTATED

    def test_uppercase_verdict_is_unchanged(self) -> None:
        adj = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Claim insufficient.",
            verdict="INSUFFICIENT",
            confidence=0.5,
            reasoning="Evidence too weak.",
            supporting_evidence=[],
            contradicting_evidence=[],
        )
        assert adj.verdict == Verdict.INSUFFICIENT

    def test_invalid_verdict_raises(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AdjudicatorAnalysis(
                agent="adjudicator",
                analysis="Bad verdict.",
                verdict="MAYBE",  # type: ignore[arg-type]
                confidence=0.5,
                reasoning="Unknown.",
                supporting_evidence=[],
                contradicting_evidence=[],
            )


# ---------------------------------------------------------------------------
# suggested_correction stripping
# ---------------------------------------------------------------------------

class TestSuggestedCorrectionStripping:
    def test_supports_verdict_strips_suggested_correction(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(contradicting_evidence=[], stance="neutral"),
            defender=_defender(),
            adjudicator=_adjudicator(
                verdict=Verdict.SUPPORTS,
                suggested_correction="Unnecessary correction from LLM.",
                supporting_evidence=["c1"],
            ),
        )
        assert result.suggested_correction is None
        assert any("Suggested correction removed" in w for w in result.validation_warnings)

    def test_insufficient_verdict_strips_suggested_correction(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_weak_evidence()],
            prosecutor=_prosecutor(contradicting_evidence=[], stance="neutral"),
            defender=_defender(supporting_evidence=[], stance="neutral"),
            adjudicator=_adjudicator(
                verdict=Verdict.INSUFFICIENT,
                confidence=0.4,
                suggested_correction="This should be stripped.",
                supporting_evidence=[],
            ),
        )
        assert result.suggested_correction is None
        assert any("Suggested correction removed" in w for w in result.validation_warnings)

    def test_overstated_verdict_preserves_correction(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy by 40%.",
            evidence=[_evidence("c1", relevance=0.82, overlap=0.76, text="The method improves accuracy by 12%.")],
            prosecutor=_prosecutor(contradicting_evidence=["c1"]),
            defender=_defender(supporting_evidence=["c1"]),
            adjudicator=_adjudicator(
                verdict=Verdict.OVERSTATED,
                confidence=0.8,
                supporting_evidence=["c1"],
                suggested_correction="The method improves accuracy by about 12%.",
            ),
        )
        assert result.suggested_correction == "The method improves accuracy by about 12%."


# ---------------------------------------------------------------------------
# Confidence single source of truth
# ---------------------------------------------------------------------------

class TestConfidenceSingleSourceOfTruth:
    def test_high_llm_confidence_is_reduced_for_weak_evidence(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_weak_evidence()],
            prosecutor=_prosecutor(contradicting_evidence=[], stance="neutral"),
            defender=_defender(supporting_evidence=[], stance="neutral"),
            adjudicator=_adjudicator(
                verdict=Verdict.INSUFFICIENT,
                confidence=0.95,
                supporting_evidence=[],
            ),
        )
        assert result.confidence < 0.95
        assert result.confidence <= 0.45

    def test_original_confidence_preserved_separately(self) -> None:
        raw = 0.88
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(contradicting_evidence=[], stance="neutral"),
            defender=_defender(),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS, confidence=raw),
        )
        assert result.original_confidence == raw

    def test_calibrated_confidence_is_always_in_unit_range(self) -> None:
        for raw in (0.0, 0.01, 0.5, 0.99, 1.0):
            result = validate_verification_result(
                claim="The method improves accuracy.",
                evidence=[_strong_evidence()],
                prosecutor=_prosecutor(contradicting_evidence=[], stance="neutral"),
                defender=_defender(),
                adjudicator=_adjudicator(verdict=Verdict.SUPPORTS, confidence=raw),
            )
            assert 0.0 <= result.confidence <= 1.0, (
                f"Confidence {result.confidence} out of bounds for raw={raw}"
            )

    def test_zero_evidence_yields_zero_confidence(self) -> None:
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[],
            prosecutor=_prosecutor(
                contradicting_evidence=[], supporting_evidence=[], confidence=0.7
            ),
            defender=_defender(supporting_evidence=[], confidence=0.7),
            adjudicator=_adjudicator(
                verdict=Verdict.INSUFFICIENT,
                confidence=0.8,
                supporting_evidence=[],
            ),
        )
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Coverage / verdict alignment
# ---------------------------------------------------------------------------

class TestCoverageVerdictAlignment:
    def test_supports_verdict_is_not_overridden_by_partial_coverage(self) -> None:
        """Coverage warnings must be informational only; they must not change the
        adjudicator verdict."""
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(contradicting_evidence=[], stance="neutral"),
            defender=_defender(),
            adjudicator=_adjudicator(
                verdict=Verdict.SUPPORTS,
                supporting_evidence=["c1"],
            ),
        )
        assert result.verdict == Verdict.SUPPORTS

    def test_supports_without_strong_evidence_caps_confidence(self) -> None:
        """SUPPORTS with no strong evidence items must cap confidence at 0.5."""
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[
                _evidence("c1", relevance=0.2, overlap=0.1)
            ],
            prosecutor=_prosecutor(contradicting_evidence=[], stance="neutral"),
            defender=_defender(),
            adjudicator=_adjudicator(
                verdict=Verdict.SUPPORTS,
                confidence=0.9,
                supporting_evidence=["c1"],
            ),
        )
        assert result.confidence <= 0.5


# ---------------------------------------------------------------------------
# Agent agreement: additional regression tests for real-world patterns
# ---------------------------------------------------------------------------


class TestAgentAgreementRealWorldPatterns:
    """Additional agent agreement tests for the specific real-world pattern
    observed during live verification (Cas9 DOI run).

    The live run produced:
      - Prosecutor: stance="challenge", contradicting_evidence=["c..."], confidence~0.6
      - Defender:   stance="Supported",  supporting_evidence=["c..."], confidence~0.95
      - Final verdict: SUPPORTS

    With both agents >= 0.5 confidence in opposing roles, agent_agreement=False
    is the CORRECT and expected behavior.  The "Agents disagree" badge is
    accurate even on a SUPPORTS verdict — it indicates the evidence was
    contested before the adjudicator resolved it.
    """

    def test_challenge_stance_plus_high_defender_confidence_is_disagreement(
        self,
    ) -> None:
        """Prosecutor uses 'challenge' stance with contradicting evidence at 0.6
        confidence; Defender strongly supports at 0.95 confidence.
        Both >= 0.5 threshold → agent_agreement must be False."""
        result = validate_verification_result(
            claim="Cas9 can be programmed with guide RNA.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="challenge",
                contradicting_evidence=["c1"],
                supporting_evidence=[],
                confidence=0.6,
            ),
            defender=_defender(
                stance="supported",
                supporting_evidence=["c1"],
                contradicting_evidence=[],
                confidence=0.95,
            ),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS),
        )
        # Both agents are >= 0.5 confidence in opposing roles → disagreement
        assert result.agent_agreement is False

    def test_challenge_stance_below_threshold_is_agreement(
        self,
    ) -> None:
        """Prosecutor uses 'challenge' stance at 0.4 confidence (below 0.5
        threshold); Defender strongly supports at 0.95.
        Only one agent is >= 0.5 → agent_agreement must be True."""
        result = validate_verification_result(
            claim="Cas9 can be programmed with guide RNA.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="challenge",
                contradicting_evidence=["c1"],
                supporting_evidence=[],
                confidence=0.4,  # below threshold
            ),
            defender=_defender(
                stance="supported",
                supporting_evidence=["c1"],
                contradicting_evidence=[],
                confidence=0.95,
            ),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS),
        )
        assert result.agent_agreement is True

    def test_supports_verdict_agent_disagreement_does_not_override_verdict(
        self,
    ) -> None:
        """Even when agents disagree (agent_agreement=False), the final verdict
        SUPPORTS must not be changed — the adjudicator resolves the dispute."""
        result = validate_verification_result(
            claim="Cas9 can be programmed with guide RNA.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="challenge",
                contradicting_evidence=["c1"],
                confidence=0.7,
            ),
            defender=_defender(
                stance="supported",
                supporting_evidence=["c1"],
                confidence=0.9,
            ),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS, supporting_evidence=["c1"]),
        )
        # Verdict must remain SUPPORTS; agent disagreement is informational only
        assert result.verdict == Verdict.SUPPORTS
        # agent_agreement=False is expected (both >= 0.5 in opposing roles)
        assert result.agent_agreement is False

    def test_prosecutor_normal_challenge_with_low_confidence_does_not_disagree(
        self,
    ) -> None:
        """Prosecutor does its normal role (challenges) at low confidence.
        This is expected behavior, not genuine disagreement."""
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="challenge",
                contradicting_evidence=["c1"],
                confidence=0.45,  # just below 0.5
            ),
            defender=_defender(
                stance="supportive",
                supporting_evidence=["c1"],
                confidence=0.8,
            ),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS),
        )
        assert result.agent_agreement is True

    def test_strongly_opposing_both_high_confidence_is_disagreement(
        self,
    ) -> None:
        """Prosecutor strongly challenges AND Defender strongly supports, both
        with high confidence → genuine disagreement."""
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(
                stance="skeptical",
                contradicting_evidence=["c1"],
                confidence=0.85,
            ),
            defender=_defender(
                stance="supportive",
                supporting_evidence=["c1"],
                confidence=0.9,
            ),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS),
        )
        assert result.agent_agreement is False

    def test_confidence_calibration_unchanged_by_traceability_fix(
        self,
    ) -> None:
        """Confidence calibration must be unchanged after the traceability fix.
        This is a smoke-test for the single source of truth invariant."""
        result = validate_verification_result(
            claim="The method improves accuracy.",
            evidence=[_strong_evidence()],
            prosecutor=_prosecutor(contradicting_evidence=[], stance="neutral"),
            defender=_defender(),
            adjudicator=_adjudicator(verdict=Verdict.SUPPORTS, confidence=0.85),
        )
        # Must be in [0.0, 1.0]
        assert 0.0 <= result.confidence <= 1.0
        # Calibrated value should be roughly close to the raw (no major penalties)
        assert result.confidence >= 0.6  # strong evidence, agree, no warnings
