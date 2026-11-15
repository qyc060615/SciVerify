from __future__ import annotations

from app.evaluation.metrics import AggregateMetrics, CaseMetrics, aggregate_case_metrics
from app.evaluation.regression import (
    RegressionThresholds,
    aggregate_to_baseline_payload,
    compare_to_baseline,
)
from app.schemas.verification import Verdict


def _aggregate(**overrides: float) -> AggregateMetrics:
    case = CaseMetrics(
        case_id="sample",
        expected_verdict=Verdict.SUPPORTS,
        actual_verdict=Verdict.SUPPORTS,
        verdict_correct=True,
        evidence_count=2,
        duplicate_rate=0.0,
        average_relevance=0.8,
        average_claim_overlap=0.75,
        traceability_present=True,
        segment_count=1,
        supported_segments=1,
        partially_supported_segments=0,
        unsupported_segments=0,
        contradicted_segments=0,
        overall_coverage=0.9,
        evidence_coverage_rate=1.0,
        traceability_link_rate=1.0,
        confidence_risk=False,
        unsupported_claim_detected=None,
        adjudicator_verdict=Verdict.SUPPORTS,
        verdict_changed=False,
        confidence_before_validation=0.8,
        confidence_after_validation=0.8,
        validation_warning_count=0,
        agent_agreement=True,
        confidence=0.8,
        confidence_error=0.2,
    )
    aggregate = aggregate_case_metrics([case])
    for key, value in overrides.items():
        setattr(aggregate, key, value)
    return aggregate


class TestRegressionComparison:
    def test_passes_when_within_tolerance(self) -> None:
        baseline = aggregate_to_baseline_payload(_aggregate())
        current = _aggregate()
        comparison = compare_to_baseline(
            current,
            baseline,
            thresholds=RegressionThresholds(),
        )
        assert comparison.passed is True
        assert comparison.findings == []

    def test_verdict_accuracy_regression(self) -> None:
        baseline = {"verdict_accuracy": 0.95}
        current = _aggregate()
        current.verdict_correct_count = 0
        current.case_count = 10
        comparison = compare_to_baseline(
            current,
            baseline,
            thresholds=RegressionThresholds(verdict_accuracy=0.02),
        )
        assert comparison.passed is False
        assert comparison.findings[0].metric == "verdict_accuracy"

    def test_duplicate_rate_regression(self) -> None:
        baseline = {"average_duplicate_rate": 0.0}
        current = _aggregate()
        current.duplicate_rates = [0.05]
        comparison = compare_to_baseline(
            current,
            baseline,
            thresholds=RegressionThresholds(duplicate_rate=0.01),
        )
        assert comparison.passed is False
        assert comparison.findings[0].metric == "average_duplicate_rate"

    def test_floating_point_tolerance_allows_small_drift(self) -> None:
        baseline = {"average_relevance": 0.80}
        current = _aggregate()
        current.average_relevances = [0.785]
        comparison = compare_to_baseline(
            current,
            baseline,
            thresholds=RegressionThresholds(average_relevance=0.03),
        )
        assert comparison.passed is True

    def test_traceability_completeness_regression(self) -> None:
        baseline = {"traceability_completeness": 1.0}
        current = _aggregate()
        current.traceability_case_count = 0
        current.case_count = 1
        comparison = compare_to_baseline(
            current,
            baseline,
            thresholds=RegressionThresholds(traceability_completeness=0.03),
        )
        assert comparison.passed is False
        assert comparison.findings[0].metric == "traceability_completeness"

    def test_baseline_payload_roundtrip(self) -> None:
        aggregate = _aggregate()
        payload = aggregate_to_baseline_payload(aggregate)
        assert payload["case_count"] == 1
        assert payload["verdict_accuracy"] == 1.0
        assert payload["average_overall_coverage"] == 0.9
        assert "average_evidence_coverage_rate" in payload

    def test_min_verdict_accuracy_threshold(self) -> None:
        baseline = {"verdict_accuracy": 1.0}
        current = _aggregate()
        current.verdict_correct_count = 7
        current.case_count = 10
        comparison = compare_to_baseline(
            current,
            baseline,
            thresholds=RegressionThresholds(min_verdict_accuracy=0.80),
        )
        assert comparison.passed is False
        assert any(finding.metric == "verdict_accuracy" for finding in comparison.findings)

    def test_confidence_regression_threshold(self) -> None:
        baseline = {"average_confidence_error": 0.20}
        current = _aggregate()
        current.confidence_errors = [0.35]
        comparison = compare_to_baseline(
            current,
            baseline,
            thresholds=RegressionThresholds(max_confidence_regression=0.10),
        )
        assert comparison.passed is False
        assert comparison.findings[0].metric == "average_confidence_error"

    def test_evidence_coverage_regression_threshold(self) -> None:
        baseline = {"average_evidence_coverage_rate": 0.90}
        current = _aggregate()
        current.evidence_coverage_rates = [0.70]
        comparison = compare_to_baseline(
            current,
            baseline,
            thresholds=RegressionThresholds(max_evidence_regression=0.10),
        )
        assert comparison.passed is False
        assert comparison.findings[0].metric == "average_evidence_coverage_rate"
