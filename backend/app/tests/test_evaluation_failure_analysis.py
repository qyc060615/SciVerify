from __future__ import annotations

from app.evaluation.failure_analysis import (
    FailureCategory,
    analyze_failures,
    classify_case_failure,
)
from app.evaluation.fixture_factory import build_fixture
from app.evaluation.metrics import evaluate_case
from app.schemas.verification import Verdict


class TestFailureClassification:
    def test_wrong_verdict_classification(self) -> None:
        response = build_fixture("cas9_supports_001")
        metrics = evaluate_case("cas9_supports_001", Verdict.CONTRADICTS, response)
        analysis = classify_case_failure(metrics, response)
        assert FailureCategory.WRONG_VERDICT in analysis.categories
        assert analysis.is_failure is True

    def test_weak_evidence_classification(self) -> None:
        response = build_fixture("weak_insufficient_001")
        metrics = evaluate_case("weak_insufficient_001", Verdict.INSUFFICIENT, response)
        analysis = classify_case_failure(metrics, response)
        assert FailureCategory.WEAK_EVIDENCE in analysis.categories

    def test_missing_evidence_classification(self) -> None:
        response = build_fixture("fabricated_claim_001")
        metrics = evaluate_case("fabricated_claim_001", Verdict.SUPPORTS, response)
        analysis = classify_case_failure(metrics, response)
        assert FailureCategory.MISSING_EVIDENCE in analysis.categories
        assert FailureCategory.WRONG_VERDICT in analysis.categories

    def test_poor_traceability_classification(self) -> None:
        response = build_fixture("not_in_paper_003")
        metrics = evaluate_case("not_in_paper_003", Verdict.FABRICATED, response)
        analysis = classify_case_failure(metrics, response)
        assert FailureCategory.POOR_TRACEABILITY in analysis.categories

    def test_overconfident_classification(self) -> None:
        response = build_fixture("cas9_supports_001")
        metrics = evaluate_case("cas9_supports_001", Verdict.CONTRADICTS, response)
        analysis = classify_case_failure(metrics, response)
        assert FailureCategory.OVERCONFIDENT in analysis.categories

    def test_agent_disagreement_classification(self) -> None:
        response = build_fixture("accuracy_overstated_001")
        metrics = evaluate_case("accuracy_overstated_001", Verdict.OVERSTATED, response)
        analysis = classify_case_failure(metrics, response)
        assert FailureCategory.AGENT_DISAGREEMENT in analysis.categories

    def test_insufficient_not_detected_classification(self) -> None:
        response = build_fixture("insufficient_evidence_001").model_copy(
            update={"verdict": Verdict.SUPPORTS}
        )
        metrics = evaluate_case("insufficient_evidence_001", Verdict.INSUFFICIENT, response)
        analysis = classify_case_failure(metrics, response)
        assert FailureCategory.INSUFFICIENT_EVIDENCE_NOT_DETECTED in analysis.categories
        assert FailureCategory.WRONG_VERDICT in analysis.categories

    def test_correct_case_has_no_wrong_verdict(self) -> None:
        response = build_fixture("numeric_supports_001")
        metrics = evaluate_case("numeric_supports_001", Verdict.SUPPORTS, response)
        analysis = classify_case_failure(metrics, response)
        assert FailureCategory.WRONG_VERDICT not in analysis.categories


class TestFailureAnalysisSummary:
    def test_analyze_failures_builds_worst_cases(self) -> None:
        wrong_response = build_fixture("cas9_supports_001")
        weak_response = build_fixture("weak_insufficient_001")
        cases = [
            evaluate_case("cas9_supports_001", Verdict.CONTRADICTS, wrong_response),
            evaluate_case("weak_insufficient_001", Verdict.INSUFFICIENT, weak_response),
            evaluate_case("numeric_supports_001", Verdict.SUPPORTS, build_fixture("numeric_supports_001")),
        ]
        responses = {
            "cas9_supports_001": wrong_response,
            "weak_insufficient_001": weak_response,
            "numeric_supports_001": build_fixture("numeric_supports_001"),
        }
        summary = analyze_failures(cases, responses)
        assert summary.total_failures >= 2
        assert summary.category_counts[FailureCategory.WRONG_VERDICT.value] >= 1
        assert summary.worst_cases[0]["case_id"] == "cas9_supports_001"
        assert "failure_categories" in summary.worst_cases[0]

    def test_worst_case_entry_fields(self) -> None:
        response = build_fixture("mortality_contradicts_001")
        metrics = evaluate_case("mortality_contradicts_001", Verdict.SUPPORTS, response)
        summary = analyze_failures([metrics], {"mortality_contradicts_001": response})
        entry = summary.worst_cases[0]
        assert entry["expected_verdict"] == "SUPPORTS"
        assert entry["actual_verdict"] == "CONTRADICTS"
        assert entry["confidence"] is not None
        assert "evidence_coverage" in entry
