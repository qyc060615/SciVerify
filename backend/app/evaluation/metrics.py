from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.schemas.verification import (
    ClaimSegmentStatus,
    ClaimTraceability,
    Verdict,
    VerificationResponse,
)
from app.utils.evidence_text import normalize_evidence_text

HIGH_CONFIDENCE_THRESHOLD = 0.75
LOW_EVIDENCE_COVERAGE_THRESHOLD = 0.4
LINKED_SEGMENT_STATUSES = {
    ClaimSegmentStatus.SUPPORTED,
    ClaimSegmentStatus.CONTRADICTED,
}


@dataclass(frozen=True)
class CaseMetrics:
    case_id: str
    expected_verdict: Verdict
    actual_verdict: Verdict | None
    verdict_correct: bool
    evidence_count: int
    duplicate_rate: float
    average_relevance: float
    average_claim_overlap: float
    traceability_present: bool
    segment_count: int
    supported_segments: int
    partially_supported_segments: int
    unsupported_segments: int
    contradicted_segments: int
    overall_coverage: float | None
    evidence_coverage_rate: float
    traceability_link_rate: float
    confidence_risk: bool
    unsupported_claim_detected: bool | None
    adjudicator_verdict: Verdict | None
    verdict_changed: bool
    confidence_before_validation: float | None
    confidence_after_validation: float | None
    validation_warning_count: int
    agent_agreement: bool | None
    confidence: float | None
    confidence_error: float | None


@dataclass
class AggregateMetrics:
    case_count: int = 0
    verdict_correct_count: int = 0
    confusion_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    per_verdict_totals: Counter[str] = field(default_factory=Counter)
    per_verdict_correct: Counter[str] = field(default_factory=Counter)
    evidence_counts: list[int] = field(default_factory=list)
    duplicate_rates: list[float] = field(default_factory=list)
    average_relevances: list[float] = field(default_factory=list)
    average_claim_overlaps: list[float] = field(default_factory=list)
    traceability_case_count: int = 0
    segment_totals: Counter[str] = field(default_factory=Counter)
    overall_coverages: list[float] = field(default_factory=list)
    evidence_coverage_rates: list[float] = field(default_factory=list)
    traceability_link_rates: list[float] = field(default_factory=list)
    confidence_risk_count: int = 0
    unsupported_claim_cases: int = 0
    unsupported_claim_detected_count: int = 0
    validation_override_count: int = 0
    validation_warning_case_count: int = 0
    agent_agreement_true_count: int = 0
    agent_agreement_false_count: int = 0
    agent_agreement_missing_count: int = 0
    confidences: list[float] = field(default_factory=list)
    correct_confidences: list[float] = field(default_factory=list)
    incorrect_confidences: list[float] = field(default_factory=list)
    confidence_errors: list[float] = field(default_factory=list)
    incorrect_case_ids: list[str] = field(default_factory=list)

    @property
    def verdict_accuracy(self) -> float:
        if self.case_count == 0:
            return 0.0
        return self.verdict_correct_count / self.case_count

    @property
    def per_verdict_accuracy(self) -> dict[str, float]:
        return {
            verdict: self.per_verdict_correct[verdict] / total
            for verdict, total in self.per_verdict_totals.items()
            if total > 0
        }

    @property
    def average_evidence_count(self) -> float:
        return _mean(self.evidence_counts)

    @property
    def average_duplicate_rate(self) -> float:
        return _mean(self.duplicate_rates)

    @property
    def average_relevance(self) -> float:
        return _mean(self.average_relevances)

    @property
    def average_claim_overlap(self) -> float:
        return _mean(self.average_claim_overlaps)

    @property
    def traceability_completeness(self) -> float:
        if self.case_count == 0:
            return 0.0
        return self.traceability_case_count / self.case_count

    @property
    def average_overall_coverage(self) -> float:
        return _mean(self.overall_coverages)

    @property
    def average_evidence_coverage_rate(self) -> float:
        return _mean(self.evidence_coverage_rates)

    @property
    def average_traceability_link_rate(self) -> float:
        return _mean(self.traceability_link_rates)

    @property
    def confidence_risk_rate(self) -> float:
        if self.case_count == 0:
            return 0.0
        return self.confidence_risk_count / self.case_count

    @property
    def unsupported_claim_detection_rate(self) -> float | None:
        if self.unsupported_claim_cases == 0:
            return None
        return self.unsupported_claim_detected_count / self.unsupported_claim_cases

    @property
    def validation_override_rate(self) -> float:
        if self.case_count == 0:
            return 0.0
        return self.validation_override_count / self.case_count

    @property
    def validation_warning_rate(self) -> float:
        if self.case_count == 0:
            return 0.0
        return self.validation_warning_case_count / self.case_count

    @property
    def agent_agreement_rate(self) -> float | None:
        known = self.agent_agreement_true_count + self.agent_agreement_false_count
        if known == 0:
            return None
        return self.agent_agreement_true_count / known

    @property
    def average_confidence(self) -> float | None:
        return _mean(self.confidences) if self.confidences else None

    @property
    def average_correct_confidence(self) -> float | None:
        return _mean(self.correct_confidences) if self.correct_confidences else None

    @property
    def average_incorrect_confidence(self) -> float | None:
        return _mean(self.incorrect_confidences) if self.incorrect_confidences else None

    @property
    def minimum_confidence(self) -> float | None:
        return min(self.confidences) if self.confidences else None

    @property
    def maximum_confidence(self) -> float | None:
        return max(self.confidences) if self.confidences else None

    @property
    def average_confidence_error(self) -> float | None:
        return _mean(self.confidence_errors) if self.confidence_errors else None

    def segment_percentage(self, status: str) -> float:
        total = sum(self.segment_totals.values())
        if total == 0:
            return 0.0
        return self.segment_totals[status] / total


def evaluate_case(case_id: str, expected_verdict: Verdict, response: VerificationResponse) -> CaseMetrics:
    actual_verdict = response.verdict
    verdict_correct = actual_verdict == expected_verdict

    evidence = response.evidence
    evidence_count = len(evidence)
    duplicate_rate = _duplicate_rate(evidence)
    average_relevance = _mean([item.relevance_score for item in evidence]) if evidence else 0.0
    average_claim_overlap = _mean([item.claim_overlap for item in evidence]) if evidence else 0.0

    traceability = response.claim_traceability
    traceability_metrics = _traceability_metrics(traceability)
    evidence_coverage_rate = _evidence_coverage_rate(traceability)
    traceability_link_rate = _traceability_link_rate(traceability)

    adjudicator_verdict = response.adjudicator.verdict if response.adjudicator else None
    confidence_before = response.adjudicator.confidence if response.adjudicator else None
    confidence_after = response.confidence
    verdict_changed = (
        adjudicator_verdict is not None
        and actual_verdict is not None
        and adjudicator_verdict != actual_verdict
    )

    validation_warning_count = len(response.validation_warnings or [])
    agent_agreement = response.agent_agreement
    confidence = response.confidence
    confidence_error = None
    if confidence is not None:
        correctness = 1.0 if verdict_correct else 0.0
        confidence_error = abs(confidence - correctness)

    confidence_risk = False
    # Ensure confidence is numeric before comparison to avoid TypeError with MagicMock in tests
    if confidence is not None and isinstance(confidence, (int, float)) and confidence >= HIGH_CONFIDENCE_THRESHOLD:
        if not verdict_correct or evidence_coverage_rate < LOW_EVIDENCE_COVERAGE_THRESHOLD:
            confidence_risk = True

    unsupported_claim_detected = None
    if expected_verdict in {Verdict.INSUFFICIENT, Verdict.FABRICATED}:
        unsupported_claim_detected = actual_verdict in {Verdict.INSUFFICIENT, Verdict.FABRICATED}

    return CaseMetrics(
        case_id=case_id,
        expected_verdict=expected_verdict,
        actual_verdict=actual_verdict,
        verdict_correct=verdict_correct,
        evidence_count=evidence_count,
        duplicate_rate=duplicate_rate,
        average_relevance=average_relevance,
        average_claim_overlap=average_claim_overlap,
        traceability_present=traceability is not None,
        segment_count=traceability_metrics["segment_count"],
        supported_segments=traceability_metrics["supported_segments"],
        partially_supported_segments=traceability_metrics["partially_supported_segments"],
        unsupported_segments=traceability_metrics["unsupported_segments"],
        contradicted_segments=traceability_metrics["contradicted_segments"],
        overall_coverage=traceability_metrics["overall_coverage"],
        evidence_coverage_rate=evidence_coverage_rate,
        traceability_link_rate=traceability_link_rate,
        confidence_risk=confidence_risk,
        unsupported_claim_detected=unsupported_claim_detected,
        adjudicator_verdict=adjudicator_verdict,
        verdict_changed=verdict_changed,
        confidence_before_validation=confidence_before,
        confidence_after_validation=confidence_after,
        validation_warning_count=validation_warning_count,
        agent_agreement=agent_agreement,
        confidence=confidence,
        confidence_error=confidence_error,
    )


def aggregate_case_metrics(cases: list[CaseMetrics]) -> AggregateMetrics:
    aggregate = AggregateMetrics(case_count=len(cases))

    for case in cases:
        expected_key = case.expected_verdict.value
        actual_key = case.actual_verdict.value if case.actual_verdict else "NONE"
        aggregate.confusion_matrix.setdefault(expected_key, defaultdict(int))
        aggregate.confusion_matrix[expected_key][actual_key] += 1
        aggregate.per_verdict_totals[expected_key] += 1
        if case.verdict_correct:
            aggregate.verdict_correct_count += 1
            aggregate.per_verdict_correct[expected_key] += 1
        else:
            aggregate.incorrect_case_ids.append(case.case_id)

        aggregate.evidence_counts.append(case.evidence_count)
        aggregate.duplicate_rates.append(case.duplicate_rate)
        aggregate.average_relevances.append(case.average_relevance)
        aggregate.average_claim_overlaps.append(case.average_claim_overlap)
        aggregate.evidence_coverage_rates.append(case.evidence_coverage_rate)
        aggregate.traceability_link_rates.append(case.traceability_link_rate)

        if case.confidence_risk:
            aggregate.confidence_risk_count += 1

        if case.unsupported_claim_detected is not None:
            aggregate.unsupported_claim_cases += 1
            if case.unsupported_claim_detected:
                aggregate.unsupported_claim_detected_count += 1

        if case.traceability_present:
            aggregate.traceability_case_count += 1
            if case.overall_coverage is not None:
                aggregate.overall_coverages.append(case.overall_coverage)
            aggregate.segment_totals["SUPPORTED"] += case.supported_segments
            aggregate.segment_totals["PARTIALLY_SUPPORTED"] += case.partially_supported_segments
            aggregate.segment_totals["UNSUPPORTED"] += case.unsupported_segments
            aggregate.segment_totals["CONTRADICTED"] += case.contradicted_segments

        if case.verdict_changed:
            aggregate.validation_override_count += 1
        if case.validation_warning_count > 0:
            aggregate.validation_warning_case_count += 1

        if case.agent_agreement is True:
            aggregate.agent_agreement_true_count += 1
        elif case.agent_agreement is False:
            aggregate.agent_agreement_false_count += 1
        else:
            aggregate.agent_agreement_missing_count += 1

        if case.confidence is not None:
            aggregate.confidences.append(case.confidence)
            if case.verdict_correct:
                aggregate.correct_confidences.append(case.confidence)
            else:
                aggregate.incorrect_confidences.append(case.confidence)
        if case.confidence_error is not None:
            aggregate.confidence_errors.append(case.confidence_error)

    aggregate.confusion_matrix = {
        expected: dict(actuals) for expected, actuals in aggregate.confusion_matrix.items()
    }
    return aggregate


def _duplicate_rate(evidence: list) -> float:
    if not evidence:
        return 0.0
    normalized = [normalize_evidence_text(item.text) for item in evidence]
    normalized = [value for value in normalized if value]
    if not normalized:
        return 0.0
    duplicates = len(normalized) - len(set(normalized))
    return duplicates / len(normalized)


def _traceability_metrics(traceability: ClaimTraceability | None) -> dict[str, float | int | None]:
    if traceability is None:
        return {
            "segment_count": 0,
            "supported_segments": 0,
            "partially_supported_segments": 0,
            "unsupported_segments": 0,
            "contradicted_segments": 0,
            "overall_coverage": None,
        }

    counts = Counter(segment.status.value for segment in traceability.segments)
    return {
        "segment_count": len(traceability.segments),
        "supported_segments": counts[ClaimSegmentStatus.SUPPORTED.value],
        "partially_supported_segments": counts[ClaimSegmentStatus.PARTIALLY_SUPPORTED.value],
        "unsupported_segments": counts[ClaimSegmentStatus.UNSUPPORTED.value],
        "contradicted_segments": counts[ClaimSegmentStatus.CONTRADICTED.value],
        "overall_coverage": traceability.overall_coverage,
    }


def _evidence_coverage_rate(traceability: ClaimTraceability | None) -> float:
    # Safeguard against empty or non-iterable segments (e.g., MagicMock in tests)
    if traceability is None:
        return 0.0
    segments = getattr(traceability, "segments", None)
    if not segments:
        return 0.0
    # Ensure we have a length to avoid ZeroDivisionError
    try:
        total = len(segments)
    except Exception:
        # Fallback: treat as empty
        return 0.0
    if total == 0:
        return 0.0
    covered = sum(1 for segment in segments if getattr(segment, "evidence_ids", None))
    return covered / total


def _traceability_link_rate(traceability: ClaimTraceability | None) -> float:
    # Safeguard against empty or non-iterable segments (e.g., MagicMock in tests)
    if traceability is None:
        return 0.0
    segments = getattr(traceability, "segments", None)
    if not segments:
        return 0.0
    try:
        total = len(segments)
    except Exception:
        return 0.0
    if total == 0:
        return 0.0
    linked = sum(
        1
        for segment in segments
        if getattr(segment, "evidence_ids", None) and getattr(segment, "status", None) in LINKED_SEGMENT_STATUSES
    )
    return linked / total


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
