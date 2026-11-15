from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from app.evaluation.metrics import CaseMetrics
from app.schemas.verification import Verdict, VerificationResponse

HIGH_CONFIDENCE_THRESHOLD = 0.75
LOW_EVIDENCE_COVERAGE_THRESHOLD = 0.4
WEAK_RELEVANCE_THRESHOLD = 0.4
WEAK_OVERLAP_THRESHOLD = 0.35
POOR_TRACEABILITY_COVERAGE_THRESHOLD = 0.4


class FailureCategory(str, Enum):
    WRONG_VERDICT = "WRONG_VERDICT"
    WEAK_EVIDENCE = "WEAK_EVIDENCE"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    POOR_TRACEABILITY = "POOR_TRACEABILITY"
    OVERCONFIDENT = "OVERCONFIDENT"
    AGENT_DISAGREEMENT = "AGENT_DISAGREEMENT"
    INVALID_EVIDENCE_REFERENCE = "INVALID_EVIDENCE_REFERENCE"
    INSUFFICIENT_EVIDENCE_NOT_DETECTED = "INSUFFICIENT_EVIDENCE_NOT_DETECTED"


@dataclass(frozen=True)
class CaseFailureAnalysis:
    case_id: str
    categories: tuple[FailureCategory, ...]
    is_failure: bool


@dataclass
class FailureAnalysisSummary:
    category_counts: Counter[str] = field(default_factory=Counter)
    failed_cases: list[CaseFailureAnalysis] = field(default_factory=list)
    worst_cases: list[dict] = field(default_factory=list)

    @property
    def total_failures(self) -> int:
        return len(self.failed_cases)


def classify_case_failure(
    metrics: CaseMetrics,
    response: VerificationResponse,
) -> CaseFailureAnalysis:
    categories: list[FailureCategory] = []

    if not metrics.verdict_correct:
        categories.append(FailureCategory.WRONG_VERDICT)

    if metrics.evidence_count == 0 and metrics.expected_verdict in {
        Verdict.SUPPORTS,
        Verdict.OVERSTATED,
        Verdict.CONTRADICTS,
    }:
        categories.append(FailureCategory.MISSING_EVIDENCE)
    elif (
        metrics.evidence_count > 0
        and (
            metrics.average_relevance < WEAK_RELEVANCE_THRESHOLD
            or metrics.average_claim_overlap < WEAK_OVERLAP_THRESHOLD
        )
    ):
        categories.append(FailureCategory.WEAK_EVIDENCE)

    if metrics.traceability_present:
        if metrics.overall_coverage is not None and metrics.overall_coverage < POOR_TRACEABILITY_COVERAGE_THRESHOLD:
            categories.append(FailureCategory.POOR_TRACEABILITY)
        elif metrics.unsupported_segments > metrics.supported_segments + metrics.contradicted_segments:
            categories.append(FailureCategory.POOR_TRACEABILITY)
    elif metrics.segment_count == 0 and metrics.expected_verdict != Verdict.SUPPORTS:
        categories.append(FailureCategory.POOR_TRACEABILITY)

    if metrics.confidence is not None and metrics.confidence >= HIGH_CONFIDENCE_THRESHOLD:
        low_coverage = metrics.evidence_coverage_rate < LOW_EVIDENCE_COVERAGE_THRESHOLD
        if not metrics.verdict_correct or low_coverage:
            categories.append(FailureCategory.OVERCONFIDENT)

    if metrics.agent_agreement is False:
        categories.append(FailureCategory.AGENT_DISAGREEMENT)

    if _has_invalid_evidence_references(response):
        categories.append(FailureCategory.INVALID_EVIDENCE_REFERENCE)

    if metrics.expected_verdict in {Verdict.INSUFFICIENT, Verdict.FABRICATED}:
        if metrics.actual_verdict in {Verdict.SUPPORTS, Verdict.OVERSTATED}:
            categories.append(FailureCategory.INSUFFICIENT_EVIDENCE_NOT_DETECTED)

    unique = tuple(dict.fromkeys(categories))
    return CaseFailureAnalysis(
        case_id=metrics.case_id,
        categories=unique,
        is_failure=len(unique) > 0,
    )


def analyze_failures(
    cases: list[CaseMetrics],
    responses_by_id: dict[str, VerificationResponse],
) -> FailureAnalysisSummary:
    summary = FailureAnalysisSummary()

    for metrics in cases:
        response = responses_by_id[metrics.case_id]
        analysis = classify_case_failure(metrics, response)
        if not analysis.is_failure:
            continue

        summary.failed_cases.append(analysis)
        for category in analysis.categories:
            summary.category_counts[category.value] += 1

        summary.worst_cases.append(
            build_worst_case_entry(metrics, analysis),
        )

    summary.worst_cases.sort(
        key=lambda entry: (
            0 if FailureCategory.WRONG_VERDICT.value in entry["failure_categories"] else 1,
            -(entry.get("confidence") or 0.0),
            entry["case_id"],
        )
    )
    return summary


def build_worst_case_entry(
    metrics: CaseMetrics,
    analysis: CaseFailureAnalysis,
) -> dict:
    return {
        "case_id": metrics.case_id,
        "expected_verdict": metrics.expected_verdict.value,
        "actual_verdict": metrics.actual_verdict.value if metrics.actual_verdict else None,
        "confidence": metrics.confidence,
        "evidence_coverage": metrics.evidence_coverage_rate,
        "traceability_coverage": metrics.overall_coverage,
        "failure_categories": [category.value for category in analysis.categories],
    }


def _has_invalid_evidence_references(response: VerificationResponse) -> bool:
    valid_ids = {item.chunk_id for item in response.evidence}
    referenced: set[str] = set()

    for agent in (response.prosecutor, response.defender, response.adjudicator):
        if agent is None:
            continue
        referenced.update(agent.supporting_evidence)
        referenced.update(agent.contradicting_evidence)

    if response.claim_traceability is not None:
        for segment in response.claim_traceability.segments:
            referenced.update(segment.evidence_ids)

    invalid = referenced - valid_ids
    return bool(invalid)
