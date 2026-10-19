from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.schemas.evidence import EvidenceItem
from app.schemas.verification import (
    AdjudicatorAnalysis,
    DefenderAnalysis,
    ProsecutorAnalysis,
    Verdict,
)
from app.services.evidence_validation import (
    available_chunk_ids,
    sanitize_adjudicator_analysis,
    sanitize_defender_analysis,
    sanitize_prosecutor_analysis,
)

logger = logging.getLogger(__name__)

WEAK_RELEVANCE_THRESHOLD = 0.15
WEAK_OVERLAP_THRESHOLD = 0.15
STRONG_RELEVANCE_THRESHOLD = 0.35
STRONG_OVERLAP_THRESHOLD = 0.25

CHALLENGE_STANCE_KEYWORDS = (
    "challenge",
    "skeptic",
    "contradict",
    "oppose",
    "weaken",
    "dispute",
    "reject",
    "uncertain",
)
SUPPORT_STANCE_KEYWORDS = (
    "support",
    "defend",
    "confirm",
    "uphold",
    "substantiat",
    "align",
)


@dataclass(frozen=True)
class EvidenceStrength:
    count: int
    avg_relevance: float
    avg_overlap: float
    max_relevance: float
    max_overlap: float
    strong_count: int
    weak_only: bool


@dataclass(frozen=True)
class ValidatedVerification:
    verdict: Verdict
    confidence: float
    suggested_correction: str | None
    agent_agreement: bool
    validation_warnings: list[str]
    original_verdict: Verdict
    original_confidence: float


def validate_verification_result(
    *,
    claim: str,
    evidence: list[EvidenceItem],
    prosecutor: ProsecutorAnalysis,
    defender: DefenderAnalysis,
    adjudicator: AdjudicatorAnalysis,
) -> ValidatedVerification:
    """Apply deterministic checks to the adjudicator result."""
    _ = claim  # Reserved for future claim-aware checks without domain keywords.
    valid_ids = available_chunk_ids(evidence)
    warnings = _invalid_reference_warnings(prosecutor, defender, adjudicator, valid_ids)
    prosecutor = sanitize_prosecutor_analysis(prosecutor, valid_ids)
    defender = sanitize_defender_analysis(defender, valid_ids)
    adjudicator = sanitize_adjudicator_analysis(adjudicator, valid_ids)

    # Calibrate against evidence the adjudicator actually used for this verdict.
    cited = (adjudicator.supporting_evidence if adjudicator.verdict == Verdict.SUPPORTS
             else adjudicator.contradicting_evidence if adjudicator.verdict in {Verdict.CONTRADICTS, Verdict.FABRICATED}
             else adjudicator.supporting_evidence + adjudicator.contradicting_evidence)
    strength = _compute_evidence_strength([item for item in evidence if item.chunk_id in cited])
    agent_agreement = _agents_agree(prosecutor, defender)

    verdict, verdict_warnings = _validate_verdict(
        adjudicator,
        prosecutor,
        defender,
        strength,
        evidence,
    )
    warnings.extend(verdict_warnings)

    correction, correction_warnings = _normalize_suggested_correction(
        verdict,
        adjudicator.suggested_correction,
    )
    warnings.extend(correction_warnings)

    original_confidence = adjudicator.confidence
    confidence = _calibrate_confidence(
        original_confidence,
        verdict=verdict,
        strength=strength,
        agent_agreement=agent_agreement,
        warnings=warnings,
        verdict_changed=verdict != adjudicator.verdict,
    )

    logger.info(
        "Verification validation: original_verdict=%s validated_verdict=%s "
        "evidence_count=%s supporting_count=%s contradicting_count=%s "
        "agent_agreement=%s confidence_before=%s confidence_after=%s warnings=%s",
        adjudicator.verdict.value,
        verdict.value,
        strength.count,
        len(adjudicator.supporting_evidence),
        len(adjudicator.contradicting_evidence),
        agent_agreement,
        original_confidence,
        confidence,
        len(warnings),
    )

    return ValidatedVerification(
        verdict=verdict,
        confidence=confidence,
        suggested_correction=correction,
        agent_agreement=agent_agreement,
        validation_warnings=warnings,
        original_verdict=adjudicator.verdict,
        original_confidence=original_confidence,
    )


def _compute_evidence_strength(evidence: list[EvidenceItem]) -> EvidenceStrength:
    if not evidence:
        return EvidenceStrength(
            count=0,
            avg_relevance=0.0,
            avg_overlap=0.0,
            max_relevance=0.0,
            max_overlap=0.0,
            strong_count=0,
            weak_only=True,
        )

    relevances = [item.relevance_score for item in evidence]
    overlaps = [item.claim_overlap for item in evidence]
    strong_count = sum(
        1
        for item in evidence
        if item.relevance_score >= STRONG_RELEVANCE_THRESHOLD
    )
    weak_only = all(
        item.relevance_score < WEAK_RELEVANCE_THRESHOLD
        and item.claim_overlap < WEAK_OVERLAP_THRESHOLD
        for item in evidence
    )

    return EvidenceStrength(
        count=len(evidence),
        avg_relevance=sum(relevances) / len(relevances),
        avg_overlap=sum(overlaps) / len(overlaps),
        max_relevance=max(relevances),
        max_overlap=max(overlaps),
        strong_count=strong_count,
        weak_only=weak_only,
    )


def _stance_indicates_challenge(stance: str) -> bool:
    normalized = stance.lower()
    return any(keyword in normalized for keyword in CHALLENGE_STANCE_KEYWORDS)


def _stance_indicates_support(stance: str) -> bool:
    normalized = stance.lower()
    return any(keyword in normalized for keyword in SUPPORT_STANCE_KEYWORDS)


_DISAGREEMENT_CONFIDENCE_THRESHOLD = 0.5


def _agents_agree(
    prosecutor: ProsecutorAnalysis,
    defender: DefenderAnalysis,
) -> bool:
    """Return True when agents do not strongly oppose each other.

    The prosecutor is designed to challenge and the defender to support, so
    having contradicting/supporting evidence respectively is their normal
    adversarial role.  We only declare *disagreement* when **both** agents are
    simultaneously highly confident (≥ 0.5) in opposing conclusions — i.e.
    the prosecutor strongly challenges while the defender strongly supports, or
    vice versa.  Low-confidence opposition is expected and does not constitute
    true disagreement.
    """
    prosecutor_challenging = bool(prosecutor.contradicting_evidence) or _stance_indicates_challenge(
        prosecutor.stance
    )
    defender_supporting = bool(defender.supporting_evidence) or _stance_indicates_support(
        defender.stance
    )
    defender_challenging = bool(defender.contradicting_evidence) or _stance_indicates_challenge(
        defender.stance
    )
    prosecutor_supporting = bool(prosecutor.supporting_evidence) or _stance_indicates_support(
        prosecutor.stance
    )

    # Disagree only when both are *strongly* committed to opposite conclusions.
    if (
        prosecutor_challenging
        and defender_supporting
        and prosecutor.confidence >= _DISAGREEMENT_CONFIDENCE_THRESHOLD
        and defender.confidence >= _DISAGREEMENT_CONFIDENCE_THRESHOLD
    ):
        return False
    if (
        defender_challenging
        and prosecutor_supporting
        and defender.confidence >= _DISAGREEMENT_CONFIDENCE_THRESHOLD
        and prosecutor.confidence >= _DISAGREEMENT_CONFIDENCE_THRESHOLD
    ):
        return False
    return True


def _invalid_reference_warnings(
    prosecutor: ProsecutorAnalysis,
    defender: DefenderAnalysis,
    adjudicator: AdjudicatorAnalysis,
    valid_ids: set[str],
) -> list[str]:
    referenced: set[str] = set()
    for analysis in (prosecutor, defender, adjudicator):
        referenced.update(analysis.supporting_evidence)
        referenced.update(analysis.contradicting_evidence)

    invalid = [chunk_id for chunk_id in referenced if chunk_id not in valid_ids]
    if invalid:
        return ["Agent referenced evidence IDs that are not in retrieved evidence."]
    return []


def _has_grounded_counterevidence(
    adjudicator: AdjudicatorAnalysis, evidence: list[EvidenceItem],
) -> bool:
    """Check attribution of a quoted basis, not the scientific truth of a quote.

    Relation/time-frame reasoning remains the agents' responsibility. Merely
    labelling a valid ID as contradicting is no longer sufficient.
    """
    normalize = lambda text: " ".join(text.split())
    quotes = re.findall(r'"([^"\n]+)"|“([^”\n]+)”', adjudicator.reasoning)
    cited = [normalize(item.text) for item in evidence
             if item.chunk_id in adjudicator.contradicting_evidence]
    return any(len(normalize(quote)) >= 12 and normalize(quote) in text
               for pair in quotes for quote in pair if quote for text in cited)


def _validate_verdict(
    adjudicator: AdjudicatorAnalysis,
    prosecutor: ProsecutorAnalysis,
    defender: DefenderAnalysis,
    strength: EvidenceStrength,
    evidence: list[EvidenceItem],
) -> tuple[Verdict, list[str]]:
    verdict = adjudicator.verdict
    warnings: list[str] = []

    if verdict == Verdict.SUPPORTS:
        if not adjudicator.supporting_evidence:
            warnings.append("Adjudicator returned SUPPORTS without supporting evidence IDs.")
        if not adjudicator.supporting_evidence or strength.weak_only or strength.strong_count == 0:
            verdict = Verdict.INSUFFICIENT
            warnings.append(
                "Verdict adjusted from SUPPORTS to INSUFFICIENT because evidence quality is too weak."
            )

    elif verdict in {Verdict.CONTRADICTS, Verdict.FABRICATED}:
        if (not _has_grounded_counterevidence(adjudicator, evidence)
                or strength.weak_only or strength.strong_count == 0):
            warnings.append(
                f"Verdict adjusted from {verdict.value} to INSUFFICIENT: "
                "negative judgment requires relevant adjudicator-cited counterevidence "
                "and a verbatim source excerpt in reasoning; agent stance/IDs alone are insufficient."
            )
            verdict = Verdict.INSUFFICIENT

    elif verdict == Verdict.INSUFFICIENT:
        if strength.strong_count >= 2 and adjudicator.supporting_evidence:
            warnings.append(
                "Adjudicator returned INSUFFICIENT despite multiple strong supporting evidence items."
            )

    elif verdict == Verdict.OVERSTATED:
        if strength.weak_only:
            verdict = Verdict.INSUFFICIENT
            warnings.append(
                "Verdict adjusted from OVERSTATED to INSUFFICIENT because evidence quality is too weak."
            )

    return verdict, warnings


def _normalize_suggested_correction(
    verdict: Verdict,
    suggested_correction: str | None,
) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    correction = (suggested_correction or "").strip() or None

    if verdict in {Verdict.SUPPORTS, Verdict.INSUFFICIENT}:
        if correction is not None:
            warnings.append(
                f"Suggested correction removed because verdict is {verdict.value}."
            )
        return None, warnings

    if verdict == Verdict.OVERSTATED and correction is None:
        warnings.append("OVERSTATED verdict lacks a suggested correction.")

    return correction, warnings


def _calibrate_confidence(
    original_confidence: float,
    *,
    verdict: Verdict,
    strength: EvidenceStrength,
    agent_agreement: bool,
    warnings: list[str],
    verdict_changed: bool,
) -> float:
    confidence = original_confidence

    if strength.count == 0:
        return 0.0

    if strength.count == 1:
        confidence *= 0.85

    if strength.avg_relevance < 0.2:
        confidence *= 0.75

    if strength.avg_overlap < 0.15:
        confidence *= 0.75

    if strength.weak_only:
        confidence = min(confidence, 0.45)

    if verdict == Verdict.SUPPORTS and strength.strong_count == 0:
        confidence = min(confidence, 0.5)

    if not agent_agreement:
        confidence *= 0.88

    if warnings:
        confidence *= max(0.7, 0.95 ** len(warnings))

    if verdict_changed:
        # A withdrawn categorical judgment does not establish a confident new one.
        confidence = min(confidence * 0.85, 0.5)

    return max(0.0, min(1.0, confidence))


__all__ = [
    "EvidenceStrength",
    "ValidatedVerification",
    "validate_verification_result",
]
