from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from app.evaluation.metrics import AggregateMetrics


@dataclass(frozen=True)
class RegressionThresholds:
    verdict_accuracy: float = 0.02
    evidence_coverage: float = 0.03
    duplicate_rate: float = 0.01
    traceability_completeness: float = 0.03
    average_relevance: float = 0.03
    min_verdict_accuracy: float = 0.80
    max_confidence_regression: float = 0.10
    max_traceability_regression: float = 0.10
    max_evidence_regression: float = 0.10


@dataclass
class RegressionFinding:
    metric: str
    baseline: float
    current: float
    tolerance: float
    message: str


@dataclass
class RegressionComparison:
    passed: bool
    findings: list[RegressionFinding] = field(default_factory=list)


def load_thresholds() -> RegressionThresholds:
    return RegressionThresholds(
        verdict_accuracy=float(os.getenv("VERDICT_ACCURACY_TOLERANCE", "0.02")),
        evidence_coverage=float(os.getenv("EVIDENCE_COVERAGE_TOLERANCE", "0.03")),
        duplicate_rate=float(os.getenv("DUPLICATE_RATE_TOLERANCE", "0.01")),
        traceability_completeness=float(
            os.getenv("TRACEABILITY_COMPLETENESS_TOLERANCE", "0.03")
        ),
        average_relevance=float(os.getenv("AVERAGE_RELEVANCE_TOLERANCE", "0.03")),
        min_verdict_accuracy=float(os.getenv("EVAL_MIN_VERDICT_ACCURACY", "0.80")),
        max_confidence_regression=float(os.getenv("EVAL_MAX_CONFIDENCE_REGRESSION", "0.10")),
        max_traceability_regression=float(
            os.getenv("EVAL_MAX_TRACEABILITY_REGRESSION", "0.10")
        ),
        max_evidence_regression=float(os.getenv("EVAL_MAX_EVIDENCE_REGRESSION", "0.10")),
    )


def aggregate_to_baseline_payload(aggregate: AggregateMetrics) -> dict:
    return {
        "case_count": aggregate.case_count,
        "verdict_accuracy": aggregate.verdict_accuracy,
        "per_verdict_accuracy": aggregate.per_verdict_accuracy,
        "average_evidence_count": aggregate.average_evidence_count,
        "average_duplicate_rate": aggregate.average_duplicate_rate,
        "average_relevance": aggregate.average_relevance,
        "average_claim_overlap": aggregate.average_claim_overlap,
        "traceability_completeness": aggregate.traceability_completeness,
        "average_overall_coverage": aggregate.average_overall_coverage,
        "average_evidence_coverage_rate": aggregate.average_evidence_coverage_rate,
        "average_traceability_link_rate": aggregate.average_traceability_link_rate,
        "confidence_risk_rate": aggregate.confidence_risk_rate,
        "unsupported_claim_detection_rate": aggregate.unsupported_claim_detection_rate,
        "validation_override_rate": aggregate.validation_override_rate,
        "validation_warning_rate": aggregate.validation_warning_rate,
        "agent_agreement_rate": aggregate.agent_agreement_rate,
        "average_confidence": aggregate.average_confidence,
        "average_correct_confidence": aggregate.average_correct_confidence,
        "average_incorrect_confidence": aggregate.average_incorrect_confidence,
        "average_confidence_error": aggregate.average_confidence_error,
    }


def load_baseline(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Baseline not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def compare_to_baseline(
    current: AggregateMetrics,
    baseline: dict,
    *,
    thresholds: RegressionThresholds | None = None,
) -> RegressionComparison:
    effective = thresholds or load_thresholds()
    current_payload = aggregate_to_baseline_payload(current)
    findings: list[RegressionFinding] = []

    if current_payload["verdict_accuracy"] < effective.min_verdict_accuracy:
        findings.append(
            RegressionFinding(
                metric="verdict_accuracy",
                baseline=effective.min_verdict_accuracy,
                current=current_payload["verdict_accuracy"],
                tolerance=0.0,
                message="Verdict accuracy below minimum threshold",
            )
        )

    checks = [
        (
            "verdict_accuracy",
            effective.verdict_accuracy,
            lambda baseline_value, current_value: current_value < baseline_value - effective.verdict_accuracy,
            "Verdict accuracy decreased",
        ),
        (
            "average_evidence_coverage_rate",
            effective.max_evidence_regression,
            lambda baseline_value, current_value: current_value < baseline_value - effective.max_evidence_regression,
            "Evidence coverage decreased",
        ),
        (
            "average_overall_coverage",
            effective.evidence_coverage,
            lambda baseline_value, current_value: current_value < baseline_value - effective.evidence_coverage,
            "Traceability coverage decreased",
        ),
        (
            "average_duplicate_rate",
            effective.duplicate_rate,
            lambda baseline_value, current_value: current_value > baseline_value + effective.duplicate_rate,
            "Duplicate rate increased",
        ),
        (
            "traceability_completeness",
            effective.max_traceability_regression,
            lambda baseline_value, current_value: current_value < baseline_value - effective.max_traceability_regression,
            "Traceability completeness decreased",
        ),
        (
            "average_traceability_link_rate",
            effective.max_traceability_regression,
            lambda baseline_value, current_value: current_value < baseline_value - effective.max_traceability_regression,
            "Traceability link rate decreased",
        ),
        (
            "average_relevance",
            effective.average_relevance,
            lambda baseline_value, current_value: current_value < baseline_value - effective.average_relevance,
            "Average evidence relevance decreased",
        ),
        (
            "average_confidence_error",
            effective.max_confidence_regression,
            lambda baseline_value, current_value: current_value > baseline_value + effective.max_confidence_regression,
            "Confidence error increased",
        ),
    ]

    for metric, tolerance, is_regression, message in checks:
        if metric not in baseline:
            continue
        baseline_value = float(baseline[metric])
        current_value = float(current_payload.get(metric) or 0.0)
        if is_regression(baseline_value, current_value):
            findings.append(
                RegressionFinding(
                    metric=metric,
                    baseline=baseline_value,
                    current=current_value,
                    tolerance=tolerance,
                    message=message,
                )
            )

    return RegressionComparison(passed=len(findings) == 0, findings=findings)
