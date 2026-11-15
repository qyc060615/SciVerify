from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Literal, TypeVar

import httpx

from app.evaluation.dataset_loader import BenchmarkCase
from app.schemas.paper import PaperRetrievalStatus
from app.schemas.verification import (
    LiveFailureCategory,
    Verdict,
    VerificationResponse,
    VerificationStatus,
)
from app.services.document_parser import DocumentParseError
from app.services.document_retriever import InterstitialPageError, PaywallError
from app.services.llm.provider import (
    LLMProviderError,
    LLMResponseError,
    LLMUnavailableError,
)
from app.services.paper_retriever import (
    DocumentRetrievalError,
    FullTextUnavailableError,
    PaperNotFoundError,
    PaperProviderError,
)
from app.services.verification_service import analyze_verification

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRYABLE_CATEGORIES = {
    LiveFailureCategory.NETWORK_TIMEOUT,
    LiveFailureCategory.NETWORK_ERROR,
    LiveFailureCategory.RATE_LIMITED,
    LiveFailureCategory.HTTP_403,
}

# Deterministic failures that should not be retried
DETERMINISTIC_FAILURE_CATEGORIES = {
    LiveFailureCategory.DOI_NOT_FOUND,
    LiveFailureCategory.FULL_TEXT_UNAVAILABLE,
    LiveFailureCategory.ANTI_BOT_BLOCKED,
    LiveFailureCategory.PAYWALLED,
    LiveFailureCategory.INVALID_DOCUMENT,
    LiveFailureCategory.HTTP_404,
    LiveFailureCategory.INVALID_RESPONSE,
}

# Retrieval/infrastructure failure categories that skip evaluation
RETRIEVAL_FAILURE_CATEGORIES = {
    LiveFailureCategory.DOI_NOT_FOUND,
    LiveFailureCategory.FULL_TEXT_UNAVAILABLE,
    LiveFailureCategory.ANTI_BOT_BLOCKED,
    LiveFailureCategory.PAYWALLED,
    LiveFailureCategory.HTTP_403,
    LiveFailureCategory.HTTP_404,
    LiveFailureCategory.RATE_LIMITED,
    LiveFailureCategory.INVALID_DOCUMENT,
    LiveFailureCategory.NETWORK_TIMEOUT,
    LiveFailureCategory.NETWORK_ERROR,
}

# Verification failure categories that represent actual system failures
VERIFICATION_FAILURE_CATEGORIES = {
    LiveFailureCategory.LLM_FAILURE,
    LiveFailureCategory.LLM_QUOTA_EXCEEDED,
    LiveFailureCategory.LLM_TIMEOUT,
    LiveFailureCategory.INVALID_RESPONSE,
    LiveFailureCategory.UNKNOWN_FAILURE,
}

T = TypeVar("T")


@dataclass(frozen=True)
class LiveCaseResult:
    case_id: str
    status: Literal["evaluated", "skipped", "failed"]
    expected_verdict: Verdict
    actual_verdict: Verdict | None
    confidence: float | None
    failure_category: LiveFailureCategory | None
    failure_reason: str | None
    retrieval_attempts: int
    elapsed_seconds: float
    candidate_urls: list[str] = field(default_factory=list)
    retrieval_elapsed_ms: int | None = None


@dataclass
class LiveEvaluationMetrics:
    """Metrics for live evaluation, separating retrieval failures from verification failures."""
    live_eligible_count: int = 0
    successfully_evaluated_count: int = 0
    retrieval_failure_count: int = 0
    verification_failure_count: int = 0
    failure_category_counts: Counter = field(default_factory=Counter)
    total_retrieval_attempts: int = 0
    total_elapsed_seconds: float = 0.0

    @property
    def retrieval_success_rate(self) -> float:
        if self.live_eligible_count == 0:
            return 0.0
        return self.successfully_evaluated_count / self.live_eligible_count

    @property
    def retrieval_failure_rate(self) -> float:
        if self.live_eligible_count == 0:
            return 0.0
        return self.retrieval_failure_count / self.live_eligible_count

    @property
    def average_attempts_per_case(self) -> float:
        if self.live_eligible_count == 0:
            return 0.0
        return self.total_retrieval_attempts / self.live_eligible_count


def classify_exception(exc: Exception) -> LiveFailureCategory:
    """Classify an exception into a LiveFailureCategory."""
    if isinstance(exc, PaperNotFoundError):
        return LiveFailureCategory.DOI_NOT_FOUND
    if isinstance(exc, FullTextUnavailableError):
        return LiveFailureCategory.FULL_TEXT_UNAVAILABLE
    if isinstance(exc, InterstitialPageError):
        return LiveFailureCategory.ANTI_BOT_BLOCKED
    if isinstance(exc, PaywallError):
        return LiveFailureCategory.PAYWALLED
    if isinstance(exc, DocumentParseError):
        return LiveFailureCategory.INVALID_DOCUMENT
    if isinstance(exc, DocumentRetrievalError):
        # Check if it's an HTTP error
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return LiveFailureCategory.NETWORK_TIMEOUT
        if "403" in msg or "forbidden" in msg:
            return LiveFailureCategory.HTTP_403
        if "404" in msg or "not found" in msg:
            return LiveFailureCategory.HTTP_404
        return LiveFailureCategory.INVALID_DOCUMENT
    if isinstance(exc, PaperProviderError):
        msg = str(exc).lower()
        if "timed out" in msg or "timeout" in msg:
            return LiveFailureCategory.NETWORK_TIMEOUT
        if "rate limit" in msg or "too many requests" in msg:
            return LiveFailureCategory.RATE_LIMITED
        if "unavailable" in msg:
            return LiveFailureCategory.NETWORK_ERROR
        return LiveFailureCategory.NETWORK_ERROR
    if isinstance(exc, httpx.HTTPStatusError):
        return classify_http_status(exc.response.status_code)
    if isinstance(exc, httpx.TimeoutException):
        return LiveFailureCategory.NETWORK_TIMEOUT
    if isinstance(exc, httpx.RequestError):
        return LiveFailureCategory.NETWORK_ERROR
    if isinstance(exc, (LLMProviderError, LLMResponseError)):
        msg = str(exc).lower()
        if "quota" in msg or "limit" in msg:
            return LiveFailureCategory.LLM_QUOTA_EXCEEDED
        if "tokens per day" in msg or "tpd" in msg:
            return LiveFailureCategory.LLM_QUOTA_EXCEEDED
        if "timed out" in msg or "timeout" in msg:
            return LiveFailureCategory.LLM_TIMEOUT
        return LiveFailureCategory.LLM_FAILURE
    if isinstance(exc, LLMUnavailableError):
        return LiveFailureCategory.LLM_FAILURE
    return LiveFailureCategory.UNKNOWN_FAILURE


def classify_http_status(status_code: int) -> LiveFailureCategory:
    """Classify an HTTP status code into a LiveFailureCategory."""
    if status_code == 403:
        return LiveFailureCategory.HTTP_403
    if status_code == 404:
        return LiveFailureCategory.HTTP_404
    if status_code == 429:
        return LiveFailureCategory.RATE_LIMITED
    if 500 <= status_code < 600:
        return LiveFailureCategory.NETWORK_ERROR
    if 400 <= status_code < 500:
        return LiveFailureCategory.INVALID_RESPONSE
    return LiveFailureCategory.UNKNOWN_FAILURE


def classify_paper_retrieval_status(status: PaperRetrievalStatus) -> LiveFailureCategory | None:
    """Classify a PaperRetrievalStatus into a LiveFailureCategory if applicable."""
    if status == PaperRetrievalStatus.NOT_FOUND:
        return LiveFailureCategory.DOI_NOT_FOUND
    if status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE:
        return LiveFailureCategory.FULL_TEXT_UNAVAILABLE
    if status == PaperRetrievalStatus.PARSING_FAILURE:
        return LiveFailureCategory.INVALID_DOCUMENT
    if status == PaperRetrievalStatus.PROVIDER_ERROR:
        return LiveFailureCategory.NETWORK_ERROR
    return None


def should_retry(category: LiveFailureCategory, attempt: int) -> bool:
    """Determine if a failed operation should be retried."""
    if attempt >= MAX_RETRIES:
        return False
    return category in RETRYABLE_CATEGORIES


def execute_with_retry(
    fn: Callable[[], T],
    case_id: str,
) -> tuple[T, LiveFailureCategory | None, str | None, int]:
    """Execute a function with bounded retries and backoff."""
    last_category: LiveFailureCategory | None = None
    last_reason: str | None = None
    attempts = 0

    for attempt in range(MAX_RETRIES + 1):
        attempts += 1
        try:
            result = fn()
            return result, None, None, attempts
        except Exception as exc:
            last_category = classify_exception(exc)
            last_reason = str(exc)

            # Deterministic failures should fail immediately with 1 attempt
            if last_category in DETERMINISTIC_FAILURE_CATEGORIES:
                logger.warning(
                    "Case %s failed with deterministic error (no retry): category=%s reason=%s",
                    case_id,
                    last_category,
                    last_reason,
                )
                # Reset attempts to 1 for deterministic failures
                attempts = 1
                raise

            if not should_retry(last_category, attempt):
                logger.warning(
                    "Case %s failed with non-retryable error: category=%s reason=%s",
                    case_id,
                    last_category,
                    last_reason,
                )
                raise

            backoff = min(2 ** attempt, 10)  # Exponential backoff, max 10s
            logger.info(
                "Case %s attempt %d failed, retrying in %ds: category=%s reason=%s",
                case_id,
                attempt + 1,
                backoff,
                last_category,
                last_reason,
            )
            time.sleep(backoff)

    # This should not be reached, but handle it
    raise RuntimeError(f"Max retries exceeded for case {case_id}")


def evaluate_live_case(
    case: BenchmarkCase,
    max_retries: int = 3,
) -> tuple[LiveCaseResult, VerificationResponse | None]:
    """Evaluate a single live case with full diagnostics tracking.

    Captures every URL attempted during retrieval via a thin monkey-patch on
    ``retrieve_document`` in the paper_retriever module.  The patch is always
    removed in a ``finally`` block so callers are not affected.

    Returns:
        A tuple of (LiveCaseResult, VerificationResponse | None).
        The response is None if the case failed or was skipped.
    """
    from app.evaluation.evaluator import evaluate_case
    from app.schemas.verification import VerificationStatus

    start_time = time.time()
    retrieval_attempts = 0
    actual_verdict = None
    confidence = None
    failure_category: LiveFailureCategory | None = None
    failure_reason: str | None = None
    status = "failed"
    response: VerificationResponse | None = None

    # ------------------------------------------------------------------
    # URL-tracking: monkey-patch retrieve_document so that every URL
    # actually attempted during this case is recorded in url_history.
    # ------------------------------------------------------------------
    url_history: list[str] = []
    import importlib
    paper_retriever_mod = importlib.import_module("app.services.paper_retriever")
    _original_retrieve_document = getattr(paper_retriever_mod, "retrieve_document")

    def _patched_retrieve_document(url: str, *args, **kwargs):  # type: ignore[misc]
        url_history.append(url)
        return _original_retrieve_document(url, *args, **kwargs)

    setattr(paper_retriever_mod, "retrieve_document", _patched_retrieve_document)
    try:
        # ------------------------------------------------------------------
        # Inner try/except: call the verifier and process its response.
        # ------------------------------------------------------------------
        try:
            def _run_verification() -> VerificationResponse:
                return analyze_verification(case.doi, case.claim)

            response_raw, _cat, _reason, attempts = execute_with_retry(_run_verification, case.id)
            retrieval_attempts = attempts
            response = response_raw

            if response.status == VerificationStatus.INSUFFICIENT_EVIDENCE:
                status = "skipped"
                failure_category = LiveFailureCategory.FULL_TEXT_UNAVAILABLE
                failure_reason = (
                    getattr(response, "reasoning", None)
                    or response.detail
                    or "Insufficient evidence available for verification."
                )
                response = None
            elif response.status in (
                VerificationStatus.LLM_UNAVAILABLE,
                VerificationStatus.VERIFICATION_FAILED,
            ):
                status = "failed"
                failure_reason = response.detail or f"Verification ended with status: {response.status.value}"
                msg = failure_reason.lower()
                if "tokens per day" in msg or "tpd" in msg or "quota" in msg or "daily token limit" in msg:
                    failure_category = LiveFailureCategory.LLM_QUOTA_EXCEEDED
                elif "timed out" in msg or "timeout" in msg:
                    failure_category = LiveFailureCategory.LLM_TIMEOUT
                else:
                    failure_category = LiveFailureCategory.LLM_FAILURE
                response = None
            elif response.status == VerificationStatus.SUCCESS:
                case_metrics = evaluate_case(case.id, case.expected_verdict, response)
                actual_verdict = case_metrics.actual_verdict
                confidence = case_metrics.confidence
                status = "evaluated"
            else:
                status = "failed"
                failure_category = LiveFailureCategory.UNKNOWN_FAILURE
                failure_reason = response.detail or f"Unexpected verification status: {response.status}"
                response = None

        except Exception as exc:
            failure_category = classify_exception(exc)
            failure_reason = str(exc)
            status = "skipped" if failure_category in RETRIEVAL_FAILURE_CATEGORIES else "failed"
            retrieval_attempts = (
                1 if failure_category in DETERMINISTIC_FAILURE_CATEGORIES else max_retries + 1
            )
            logger.error(
                "Case %s %s after %d attempts: category=%s reason=%s",
                case.id,
                status,
                retrieval_attempts,
                failure_category,
                failure_reason,
            )
    finally:
        # Always restore the original function regardless of outcome.
        setattr(paper_retriever_mod, "retrieve_document", _original_retrieve_document)

    elapsed_seconds = time.time() - start_time

    live_result = LiveCaseResult(
        case_id=case.id,
        status=status,
        expected_verdict=case.expected_verdict,
        actual_verdict=actual_verdict,
        confidence=confidence,
        failure_category=failure_category,
        failure_reason=failure_reason,
        retrieval_attempts=retrieval_attempts,
        elapsed_seconds=elapsed_seconds,
        candidate_urls=list(url_history),
        retrieval_elapsed_ms=int(elapsed_seconds * 1000),
    )

    return live_result, response


__all__ = [
    "classify_exception",
    "classify_http_status",
    "classify_paper_retrieval_status",
    "DETERMINISTIC_FAILURE_CATEGORIES",
    "evaluate_live_case",
    "execute_with_retry",
    "LiveCaseResult",
    "LiveEvaluationMetrics",
    "MAX_RETRIES",
    "RETRYABLE_CATEGORIES",
    "RETRIEVAL_FAILURE_CATEGORIES",
    "should_retry",
    "VERIFICATION_FAILURE_CATEGORIES",
]
