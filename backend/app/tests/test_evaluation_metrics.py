from __future__ import annotations

from app.evaluation.fixture_factory import build_fixture
from app.evaluation.metrics import (
    CaseMetrics,
    aggregate_case_metrics,
    evaluate_case,
)
from app.schemas.evidence import EvidenceItem
from app.schemas.verification import Verdict, VerificationResponse, VerificationStatus


def _duplicate_evidence_response() -> VerificationResponse:
    base = build_fixture("cas9_supports_001")
    duplicate = EvidenceItem(
        chunk_id="c3",
        section="Results",
        chunk_index=1,
        text=base.evidence[0].text,
        relevance_score=0.5,
        claim_overlap=0.5,
        numeric_overlap=0.0,
    )
    return base.model_copy(update={"evidence": [*base.evidence, duplicate]})


class TestEvaluateCase:
    def test_verdict_accuracy_correct_case(self) -> None:
        response = build_fixture("cas9_supports_001")
        metrics = evaluate_case("cas9_supports_001", Verdict.SUPPORTS, response)
        assert metrics.verdict_correct is True

    def test_incorrect_verdict_detection(self) -> None:
        response = build_fixture("cas9_supports_001")
        metrics = evaluate_case("cas9_supports_001", Verdict.CONTRADICTS, response)
        assert metrics.verdict_correct is False
        assert metrics.actual_verdict == Verdict.SUPPORTS

    def test_evidence_count(self) -> None:
        response = build_fixture("cas9_supports_001")
        metrics = evaluate_case("cas9_supports_001", Verdict.SUPPORTS, response)
        assert metrics.evidence_count == 2

    def test_duplicate_rate_zero_for_unique_evidence(self) -> None:
        response = build_fixture("cas9_supports_001")
        metrics = evaluate_case("cas9_supports_001", Verdict.SUPPORTS, response)
        assert metrics.duplicate_rate == 0.0

    def test_duplicate_rate_detects_duplicates(self) -> None:
        response = _duplicate_evidence_response()
        metrics = evaluate_case("cas9_supports_001", Verdict.SUPPORTS, response)
        assert metrics.duplicate_rate > 0.0

    def test_average_relevance_and_overlap(self) -> None:
        response = build_fixture("numeric_supports_001")
        metrics = evaluate_case("numeric_supports_001", Verdict.SUPPORTS, response)
        assert metrics.average_relevance == 0.9
        assert metrics.average_claim_overlap == 0.88

    def test_traceability_metrics(self) -> None:
        response = build_fixture("universal_overstated_001")
        metrics = evaluate_case("universal_overstated_001", Verdict.OVERSTATED, response)
        assert metrics.traceability_present is True
        assert metrics.segment_count == 2
        assert metrics.supported_segments == 0
        assert metrics.partially_supported_segments == 1
        assert metrics.unsupported_segments == 1
        assert metrics.overall_coverage is not None

    def test_missing_traceability_fields(self) -> None:
        response = build_fixture("legacy_no_traceability_001")
        metrics = evaluate_case("legacy_no_traceability_001", Verdict.SUPPORTS, response)
        assert metrics.traceability_present is False
        assert metrics.segment_count == 0
        assert metrics.overall_coverage is None

    def test_validation_override_rate_fields(self) -> None:
        response = build_fixture("accuracy_overstated_001")
        metrics = evaluate_case("accuracy_overstated_001", Verdict.OVERSTATED, response)
        assert metrics.adjudicator_verdict == Verdict.OVERSTATED
        assert metrics.verdict_changed is False
        assert metrics.validation_warning_count == 0

    def test_agent_agreement_missing(self) -> None:
        response = build_fixture("legacy_no_traceability_001")
        metrics = evaluate_case("legacy_no_traceability_001", Verdict.SUPPORTS, response)
        assert metrics.agent_agreement is None

    def test_confidence_error(self) -> None:
        response = build_fixture("cas9_supports_001")
        correct = evaluate_case("cas9_supports_001", Verdict.SUPPORTS, response)
        incorrect = evaluate_case("cas9_supports_001", Verdict.CONTRADICTS, response)
        assert correct.confidence_error == 0.14
        assert incorrect.confidence_error == 0.86


class TestAggregateMetrics:
    def _cases(self) -> list[CaseMetrics]:
        return [
            evaluate_case("cas9_supports_001", Verdict.SUPPORTS, build_fixture("cas9_supports_001")),
            evaluate_case(
                "accuracy_overstated_001",
                Verdict.OVERSTATED,
                build_fixture("accuracy_overstated_001"),
            ),
            evaluate_case(
                "legacy_no_traceability_001",
                Verdict.SUPPORTS,
                build_fixture("legacy_no_traceability_001"),
            ),
        ]

    def test_confusion_matrix(self) -> None:
        aggregate = aggregate_case_metrics(self._cases())
        assert aggregate.confusion_matrix["SUPPORTS"]["SUPPORTS"] == 2
        assert aggregate.confusion_matrix["OVERSTATED"]["OVERSTATED"] == 1

    def test_verdict_accuracy(self) -> None:
        aggregate = aggregate_case_metrics(self._cases())
        assert aggregate.verdict_accuracy == 1.0

    def test_agent_agreement_rate(self) -> None:
        aggregate = aggregate_case_metrics(self._cases())
        assert aggregate.agent_agreement_rate == 0.5

    def test_confidence_metrics(self) -> None:
        aggregate = aggregate_case_metrics(self._cases())
        assert aggregate.average_confidence is not None
        assert aggregate.average_correct_confidence is not None
        assert aggregate.minimum_confidence is not None
        assert aggregate.maximum_confidence is not None
        assert aggregate.average_confidence_error is not None

    def test_empty_dataset_handling(self) -> None:
        aggregate = aggregate_case_metrics([])
        assert aggregate.case_count == 0
        assert aggregate.verdict_accuracy == 0.0
        assert aggregate.traceability_completeness == 0.0
        assert aggregate.agent_agreement_rate is None

    def test_insufficient_evidence_status(self) -> None:
        response = build_fixture("insufficient_evidence_001")
        metrics = evaluate_case("insufficient_evidence_001", Verdict.INSUFFICIENT, response)
        assert metrics.actual_verdict == Verdict.INSUFFICIENT
        assert response.status == VerificationStatus.INSUFFICIENT_EVIDENCE
