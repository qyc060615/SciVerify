from __future__ import annotations

from app.evaluation.fixture_factory import build_fixture
from app.evaluation.metrics import aggregate_case_metrics, evaluate_case
from app.evaluation.report import build_report_payload, render_markdown_report
from app.evaluation.evaluator import EvaluationResult
from app.schemas.verification import Verdict
from pathlib import Path


class TestRobustnessMetrics:
    def test_evidence_coverage_rate(self) -> None:
        response = build_fixture("compound_unsupported_detail_003")
        metrics = evaluate_case("compound_unsupported_detail_003", Verdict.OVERSTATED, response)
        assert metrics.evidence_coverage_rate == 0.5

    def test_traceability_link_rate(self) -> None:
        response = build_fixture("compound_unsupported_detail_003")
        metrics = evaluate_case("compound_unsupported_detail_003", Verdict.OVERSTATED, response)
        assert metrics.traceability_link_rate == 0.5

    def test_confidence_risk_on_wrong_verdict(self) -> None:
        response = build_fixture("cas9_supports_001")
        metrics = evaluate_case("cas9_supports_001", Verdict.CONTRADICTS, response)
        assert metrics.confidence_risk is True

    def test_unsupported_claim_detected(self) -> None:
        response = build_fixture("not_in_paper_003")
        metrics = evaluate_case("not_in_paper_003", Verdict.FABRICATED, response)
        assert metrics.unsupported_claim_detected is True

    def test_unsupported_claim_not_applicable_for_supports(self) -> None:
        response = build_fixture("cas9_supports_001")
        metrics = evaluate_case("cas9_supports_001", Verdict.SUPPORTS, response)
        assert metrics.unsupported_claim_detected is None

    def test_aggregate_robustness_metrics(self) -> None:
        cases = [
            evaluate_case("not_in_paper_003", Verdict.FABRICATED, build_fixture("not_in_paper_003")),
            evaluate_case("weak_insufficient_001", Verdict.INSUFFICIENT, build_fixture("weak_insufficient_001")),
            evaluate_case("cas9_supports_001", Verdict.SUPPORTS, build_fixture("cas9_supports_001")),
        ]
        aggregate = aggregate_case_metrics(cases)
        assert aggregate.average_evidence_coverage_rate > 0.0
        assert aggregate.unsupported_claim_detection_rate == 1.0
        assert aggregate.per_verdict_accuracy["FABRICATED"] == 1.0


class TestExpandedReport:
    def test_report_includes_failure_analysis(self) -> None:
        from app.evaluation.evaluator import load_and_evaluate_offline

        result = load_and_evaluate_offline()
        payload = build_report_payload(result)
        markdown = render_markdown_report(result)

        assert "failure_analysis" in payload
        assert "robustness" in payload
        assert "per_verdict_accuracy" in payload
        assert "Failure analysis:" in markdown
        assert "Worst-performing cases:" in markdown
        assert "Per-Verdict Accuracy:" in markdown

    def test_report_with_synthetic_failure(self) -> None:
        response = build_fixture("cas9_supports_001")
        metrics = evaluate_case("cas9_supports_001", Verdict.CONTRADICTS, response)
        result = EvaluationResult(
            dataset_path=Path("evaluation/dataset.json"),
            cases=[metrics],
            aggregate=aggregate_case_metrics([metrics]),
            skipped_case_ids=[],
            responses_by_id={"cas9_supports_001": response},
        )
        payload = build_report_payload(result)
        assert payload["failure_analysis"]["total_failures"] >= 1
        assert payload["failure_analysis"]["worst_cases"]
