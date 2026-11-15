from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.dataset_loader import BenchmarkCase
from app.evaluation.evaluator import EvaluationResult
from app.evaluation.live_diagnostics import (
    classify_exception,
    DETERMINISTIC_FAILURE_CATEGORIES,
    evaluate_live_case,
    LiveCaseResult,
    LiveEvaluationMetrics,
    MAX_RETRIES,
)
from app.schemas.verification import LiveFailureCategory, Verdict
from app.services.paper_retriever import PaperNotFoundError


class TestEvaluateLiveCase:
    def test_successful_evaluation(self) -> None:
        """Test that a successful evaluation returns correct status and metrics."""
        case = BenchmarkCase(
            id="test-001",
            claim="Test claim",
            doi="10.1000/test.2024.001",
            expected_verdict=Verdict.SUPPORTS,
            description="Test case",
            live_evaluable=True,
        )

        mock_response = MagicMock()
        mock_response.status = "success"
        mock_response.verdict = Verdict.SUPPORTS
        mock_response.confidence = 0.95
        mock_response.evidence = []
        mock_response.paper = MagicMock()
        mock_response.paper.paper_id = "test-doi"
        mock_response.claim_traceability = MagicMock()
        mock_response.claim_traceability.segments = []
        mock_response.claim_traceability.overall_coverage = 0.0
        mock_response.validation_warnings = None
        mock_response.agent_agreement = True

        with patch("app.evaluation.live_diagnostics.analyze_verification", return_value=mock_response):
            live_result, response = evaluate_live_case(case, max_retries=MAX_RETRIES)

        assert live_result.status == "evaluated"
        assert live_result.case_id == "test-001"
        assert live_result.expected_verdict == Verdict.SUPPORTS
        assert live_result.actual_verdict == Verdict.SUPPORTS
        assert live_result.confidence == 0.95
        assert live_result.failure_category is None
        assert live_result.failure_reason is None
        assert live_result.retrieval_attempts == 1
        assert live_result.elapsed_seconds >= 0
        assert response is not None

    def test_retrieval_failure_classification(self) -> None:
        """Test that retrieval failures are correctly classified and tracked."""
        case = BenchmarkCase(
            id="test-002",
            claim="Test claim",
            doi="10.1000/nonexistent.2024.001",
            expected_verdict=Verdict.SUPPORTS,
            description="Test case with bad DOI",
            live_evaluable=True,
        )

        with patch("app.evaluation.live_diagnostics.analyze_verification", side_effect=PaperNotFoundError("Paper not found")):
            live_result, response = evaluate_live_case(case, max_retries=MAX_RETRIES)

        assert live_result.status == "skipped"
        assert live_result.case_id == "test-002"
        assert live_result.failure_category == LiveFailureCategory.DOI_NOT_FOUND
        assert live_result.failure_reason == "Paper not found"
        assert live_result.retrieval_attempts == 1  # Deterministic failures have 1 attempt
        assert response is None

    def test_llm_failure_classification(self) -> None:
        """Test that LLM failures are correctly classified."""
        from app.services.llm.provider import LLMProviderError

        case = BenchmarkCase(
            id="test-003",
            claim="Test claim",
            doi="10.1000/test.2024.002",
            expected_verdict=Verdict.SUPPORTS,
            description="Test case",
            live_evaluable=True,
        )

        with patch("app.evaluation.live_diagnostics.analyze_verification", side_effect=LLMProviderError("LLM provider error")):
            live_result, response = evaluate_live_case(case, max_retries=MAX_RETRIES)

        assert live_result.status == "failed"
        assert live_result.failure_category == LiveFailureCategory.LLM_FAILURE
        assert live_result.failure_reason == "LLM provider error"
        assert live_result.retrieval_attempts == MAX_RETRIES + 1  # Verification failures retry
        assert response is None

    def test_insufficient_evidence_response_status(self) -> None:
        """Test that analyze_verification returning INSUFFICIENT_EVIDENCE is marked as skipped."""
        from app.schemas.verification import VerificationStatus

        case = BenchmarkCase(
            id="test-003b",
            claim="Test claim",
            doi="10.1000/test.2024.002",
            expected_verdict=Verdict.SUPPORTS,
            description="Test case",
            live_evaluable=True,
        )

        mock_response = MagicMock()
        mock_response.status = VerificationStatus.INSUFFICIENT_EVIDENCE
        mock_response.reasoning = "Full text is unavailable"
        mock_response.detail = None

        with patch("app.evaluation.live_diagnostics.analyze_verification", return_value=mock_response):
            live_result, response = evaluate_live_case(case, max_retries=MAX_RETRIES)

        assert live_result.status == "skipped"
        assert live_result.failure_category == LiveFailureCategory.FULL_TEXT_UNAVAILABLE
        assert live_result.actual_verdict is None
        assert response is None

    def test_llm_unavailable_response_status(self) -> None:
        """Test that analyze_verification returning LLM_UNAVAILABLE is marked as failed."""
        from app.schemas.verification import VerificationStatus

        case = BenchmarkCase(
            id="test-003c",
            claim="Test claim",
            doi="10.1000/test.2024.002",
            expected_verdict=Verdict.SUPPORTS,
            description="Test case",
            live_evaluable=True,
        )

        mock_response = MagicMock()
        mock_response.status = VerificationStatus.LLM_UNAVAILABLE
        mock_response.detail = "LLM provider not configured"

        with patch("app.evaluation.live_diagnostics.analyze_verification", return_value=mock_response):
            live_result, response = evaluate_live_case(case, max_retries=MAX_RETRIES)

        assert live_result.status == "failed"
        assert live_result.failure_category == LiveFailureCategory.LLM_FAILURE
        assert live_result.actual_verdict is None
        assert response is None

    def test_infrastructure_vs_verification_failure_separation(self) -> None:
        """Test that infrastructure failures are separated from verification failures."""
        # Infrastructure failure (DOI not found)
        case1 = BenchmarkCase(
            id="test-004",
            claim="Test claim",
            doi="10.1000/nonexistent.2024.001",
            expected_verdict=Verdict.SUPPORTS,
            description="Infrastructure failure case",
            live_evaluable=True,
        )

        with patch("app.evaluation.live_diagnostics.analyze_verification", side_effect=PaperNotFoundError("Paper not found")):
            live_result1, _ = evaluate_live_case(case1, max_retries=MAX_RETRIES)

        # This should be classified as an infrastructure failure (DOI_NOT_FOUND)
        assert live_result1.failure_category == LiveFailureCategory.DOI_NOT_FOUND
        assert live_result1.failure_category != LiveFailureCategory.LLM_FAILURE
        assert live_result1.retrieval_attempts == 1  # Deterministic failure

    def test_retry_logic_with_retryable_error(self) -> None:
        """Test that retryable errors trigger retries."""
        from app.services.paper_retriever import PaperProviderError

        case = BenchmarkCase(
            id="test-005",
            claim="Test claim",
            doi="10.1000/test.2024.003",
            expected_verdict=Verdict.SUPPORTS,
            description="Test case",
            live_evaluable=True,
        )

        # First two attempts fail, third succeeds
        mock_response = MagicMock()
        mock_response.status = "success"
        mock_response.verdict = Verdict.SUPPORTS
        mock_response.confidence = 0.95
        mock_response.evidence = []
        mock_response.paper = MagicMock()
        mock_response.paper.paper_id = "test-doi"
        mock_response.claim_traceability = MagicMock()
        mock_response.claim_traceability.segments = []
        mock_response.claim_traceability.overall_coverage = 0.0
        mock_response.validation_warnings = None
        mock_response.agent_agreement = True

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise PaperProviderError("Rate limit exceeded")
            return mock_response

        with patch("app.evaluation.live_diagnostics.analyze_verification", side_effect=side_effect):
            live_result, response = evaluate_live_case(case, max_retries=MAX_RETRIES)

        # Should have retried and succeeded
        assert live_result.status == "evaluated"
        assert live_result.retrieval_attempts == 2
        assert response is not None

    def test_retry_logic_with_non_retryable_error(self) -> None:
        """Test that non-retryable errors do not trigger retries."""
        case = BenchmarkCase(
            id="test-006",
            claim="Test claim",
            doi="10.1000/nonexistent.2024.001",
            expected_verdict=Verdict.SUPPORTS,
            description="Test case",
            live_evaluable=True,
        )

        with patch("app.evaluation.live_diagnostics.analyze_verification", side_effect=PaperNotFoundError("Paper not found")):
            live_result, response = evaluate_live_case(case, max_retries=MAX_RETRIES)

        # DOI_NOT_FOUND is deterministic (non-retryable retrieval failure), should skip immediately with 1 attempt
        assert live_result.status == "skipped"
        assert live_result.retrieval_attempts == 1  # Deterministic failures have 1 attempt
        assert response is None

    def test_deterministic_failure_not_retried(self) -> None:
        """Test that deterministic failures fail immediately with 1 attempt."""
        case = BenchmarkCase(
            id="test-007",
            claim="Test claim",
            doi="10.1000/nonexistent.2024.002",
            expected_verdict=Verdict.SUPPORTS,
            description="Test case",
            live_evaluable=True,
        )

        with patch("app.evaluation.live_diagnostics.analyze_verification", side_effect=PaperNotFoundError("Paper not found")):
            live_result, response = evaluate_live_case(case, max_retries=MAX_RETRIES)

        assert live_result.status == "skipped"
        assert live_result.failure_category == LiveFailureCategory.DOI_NOT_FOUND
        assert live_result.retrieval_attempts == 1  # Should be exactly 1 for deterministic failures
        assert response is None

    def test_transient_failure_is_retried(self) -> None:
        """Test that transient failures trigger retries."""
        from app.services.paper_retriever import PaperProviderError

        case = BenchmarkCase(
            id="test-008",
            claim="Test claim",
            doi="10.1000/test.2024.004",
            expected_verdict=Verdict.SUPPORTS,
            description="Test case",
            live_evaluable=True,
        )

        mock_response = MagicMock()
        mock_response.status = "success"
        mock_response.verdict = Verdict.SUPPORTS
        mock_response.confidence = 0.95
        mock_response.evidence = []
        mock_response.paper = MagicMock()
        mock_response.paper.paper_id = "test-doi"
        mock_response.claim_traceability = MagicMock()
        mock_response.claim_traceability.segments = []
        mock_response.claim_traceability.overall_coverage = 0.0
        mock_response.validation_warnings = None
        mock_response.agent_agreement = True

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise PaperProviderError("Rate limit exceeded")
            return mock_response

        with patch("app.evaluation.live_diagnostics.analyze_verification", side_effect=side_effect):
            live_result, response = evaluate_live_case(case, max_retries=MAX_RETRIES)

        # Should have retried and succeeded
        assert live_result.status == "evaluated"
        assert live_result.retrieval_attempts == 2
        assert response is not None


class TestLiveCaseResult:
    def test_live_case_result_structure(self) -> None:
        """Test that LiveCaseResult has all required fields."""
        result = LiveCaseResult(
            case_id="test-001",
            status="evaluated",
            expected_verdict=Verdict.SUPPORTS,
            actual_verdict=Verdict.SUPPORTS,
            confidence=0.95,
            failure_category=None,
            failure_reason=None,
            retrieval_attempts=1,
            elapsed_seconds=1.5,
        )

        assert result.case_id == "test-001"
        assert result.status == "evaluated"
        assert result.expected_verdict == Verdict.SUPPORTS
        assert result.actual_verdict == Verdict.SUPPORTS
        assert result.confidence == 0.95
        assert result.failure_category is None
        assert result.failure_reason is None
        assert result.retrieval_attempts == 1
        assert result.elapsed_seconds == 1.5

    def test_live_case_result_with_failure(self) -> None:
        """Test LiveCaseResult with failure information."""
        result = LiveCaseResult(
            case_id="test-002",
            status="failed",
            expected_verdict=Verdict.SUPPORTS,
            actual_verdict=None,
            confidence=None,
            failure_category=LiveFailureCategory.DOI_NOT_FOUND,
            failure_reason="Paper not found",
            retrieval_attempts=4,
            elapsed_seconds=2.5,
        )

        assert result.status == "failed"
        assert result.failure_category == LiveFailureCategory.DOI_NOT_FOUND
        assert result.failure_reason == "Paper not found"
        assert result.retrieval_attempts == 4


class TestEvaluationResultWithLiveResults:
    def test_evaluation_result_with_live_case_results(self) -> None:
        """Test that EvaluationResult can contain live case results."""
        live_results = [
            LiveCaseResult(
                case_id="test-001",
                status="evaluated",
                expected_verdict=Verdict.SUPPORTS,
                actual_verdict=Verdict.SUPPORTS,
                confidence=0.95,
                failure_category=None,
                failure_reason=None,
                retrieval_attempts=1,
                elapsed_seconds=1.5,
            ),
            LiveCaseResult(
                case_id="test-002",
                status="failed",
                expected_verdict=Verdict.SUPPORTS,
                actual_verdict=None,
                confidence=None,
                failure_category=LiveFailureCategory.DOI_NOT_FOUND,
                failure_reason="Paper not found",
                retrieval_attempts=1,  # Deterministic failure
                elapsed_seconds=2.5,
            ),
        ]

        result = EvaluationResult(
            dataset_path=MagicMock(),
            cases=[],
            aggregate=MagicMock(),
            skipped_case_ids=["test-002"],
            responses_by_id={},
            live_case_results=live_results,
        )

        assert len(result.live_case_results) == 2
        assert result.live_case_results[0].case_id == "test-001"
        assert result.live_case_results[1].case_id == "test-002"

    def test_evaluation_result_without_live_case_results(self) -> None:
        """Test that EvaluationResult works without live case results (offline evaluation)."""
        result = EvaluationResult(
            dataset_path=MagicMock(),
            cases=[],
            aggregate=MagicMock(),
            skipped_case_ids=[],
            responses_by_id={},
        )

        assert result.live_case_results == []


class TestLiveEvaluationMetrics:
    def test_live_metrics_initialization(self) -> None:
        """Test that LiveEvaluationMetrics initializes correctly."""
        metrics = LiveEvaluationMetrics()
        assert metrics.live_eligible_count == 0
        assert metrics.successfully_evaluated_count == 0
        assert metrics.retrieval_failure_count == 0
        assert metrics.verification_failure_count == 0
        assert metrics.total_retrieval_attempts == 0
        assert metrics.total_elapsed_seconds == 0.0

    def test_retrieval_success_rate(self) -> None:
        """Test retrieval success rate calculation."""
        metrics = LiveEvaluationMetrics()
        metrics.live_eligible_count = 30
        metrics.successfully_evaluated_count = 19
        assert metrics.retrieval_success_rate == 19 / 30

    def test_retrieval_failure_rate(self) -> None:
        """Test retrieval failure rate calculation."""
        metrics = LiveEvaluationMetrics()
        metrics.live_eligible_count = 30
        metrics.retrieval_failure_count = 11
        assert metrics.retrieval_failure_rate == 11 / 30

    def test_average_attempts_per_case(self) -> None:
        """Test average attempts per case calculation."""
        metrics = LiveEvaluationMetrics()
        metrics.live_eligible_count = 30
        metrics.total_retrieval_attempts = 63
        assert metrics.average_attempts_per_case == 63 / 30

    def test_zero_division_protection(self) -> None:
        """Test that division by zero is handled gracefully."""
        metrics = LiveEvaluationMetrics()
        assert metrics.retrieval_success_rate == 0.0
        assert metrics.retrieval_failure_rate == 0.0
        assert metrics.average_attempts_per_case == 0.0

    def test_deterministic_failures_counted_as_retrieval_failures(self) -> None:
        """Test that deterministic failures are counted as retrieval failures."""
        from collections import Counter

        metrics = LiveEvaluationMetrics()
        metrics.live_eligible_count = 30
        metrics.retrieval_failure_count = 11
        metrics.failure_category_counts = Counter({"doi_not_found": 11})

        assert metrics.retrieval_failure_count == 11
        assert metrics.failure_category_counts["doi_not_found"] == 11
