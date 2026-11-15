from __future__ import annotations

import pytest

from app.evaluation.live_diagnostics import (
    classify_exception,
    classify_http_status,
    classify_paper_retrieval_status,
    DETERMINISTIC_FAILURE_CATEGORIES,
    MAX_RETRIES,
    RETRYABLE_CATEGORIES,
    RETRIEVAL_FAILURE_CATEGORIES,
    should_retry,
    VERIFICATION_FAILURE_CATEGORIES,
)
import httpx
from app.services.document_parser import DocumentParseError
from app.schemas.paper import PaperRetrievalStatus
from app.schemas.verification import LiveFailureCategory
from app.services.document_retriever import (
    DocumentRetrievalError,
    InterstitialPageError,
    PaywallError,
)
from app.services.llm.provider import (
    LLMProviderError,
    LLMResponseError,
    LLMUnavailableError,
)
from app.services.paper_retriever import (
    FullTextUnavailableError,
    PaperNotFoundError,
    PaperProviderError,
)


class TestClassifyException:
    def test_paper_not_found(self) -> None:
        exc = PaperNotFoundError("Paper not found")
        assert classify_exception(exc) == LiveFailureCategory.DOI_NOT_FOUND

    def test_full_text_unavailable(self) -> None:
        exc = FullTextUnavailableError("Full text unavailable")
        assert classify_exception(exc) == LiveFailureCategory.FULL_TEXT_UNAVAILABLE

    def test_interstitial_page(self) -> None:
        exc = InterstitialPageError("Browser challenge detected")
        assert classify_exception(exc) == LiveFailureCategory.ANTI_BOT_BLOCKED

    def test_paywall_error(self) -> None:
        exc = PaywallError("Content is behind a paywall")
        assert classify_exception(exc) == LiveFailureCategory.PAYWALLED

    def test_document_retrieval_403(self) -> None:
        exc = DocumentRetrievalError("Access denied (403)")
        assert classify_exception(exc) == LiveFailureCategory.HTTP_403

    def test_document_retrieval_404(self) -> None:
        exc = DocumentRetrievalError("Not found (404)")
        assert classify_exception(exc) == LiveFailureCategory.HTTP_404

    def test_document_retrieval_timeout(self) -> None:
        exc = DocumentRetrievalError("Request timed out")
        assert classify_exception(exc) == LiveFailureCategory.NETWORK_TIMEOUT

    def test_paper_provider_timeout(self) -> None:
        exc = PaperProviderError("OpenAlex request timed out")
        assert classify_exception(exc) == LiveFailureCategory.NETWORK_TIMEOUT

    def test_paper_provider_rate_limit(self) -> None:
        exc = PaperProviderError("Rate limit exceeded")
        assert classify_exception(exc) == LiveFailureCategory.RATE_LIMITED

    def test_paper_provider_unavailable(self) -> None:
        exc = PaperProviderError("Service unavailable")
        assert classify_exception(exc) == LiveFailureCategory.NETWORK_ERROR

    def test_llm_quota_exceeded(self) -> None:
        exc = LLMProviderError("LLM provider rate limit exceeded (HTTP 429)")
        assert classify_exception(exc) == LiveFailureCategory.LLM_QUOTA_EXCEEDED

    def test_llm_timeout(self) -> None:
        exc = LLMProviderError("LLM request timed out: TimeoutException")
        assert classify_exception(exc) == LiveFailureCategory.LLM_TIMEOUT

    def test_llm_provider_error(self) -> None:
        exc = LLMProviderError("LLM provider error")
        assert classify_exception(exc) == LiveFailureCategory.LLM_FAILURE

    def test_llm_response_error(self) -> None:
        exc = LLMResponseError("Invalid LLM response")
        assert classify_exception(exc) == LiveFailureCategory.LLM_FAILURE

    def test_llm_unavailable(self) -> None:
        exc = LLMUnavailableError("LLM unavailable")
        assert classify_exception(exc) == LiveFailureCategory.LLM_FAILURE

    def test_document_parse_error(self) -> None:
        exc = DocumentParseError("Failed to parse document")
        assert classify_exception(exc) == LiveFailureCategory.INVALID_DOCUMENT

    def test_httpx_status_error(self) -> None:
        req = httpx.Request("GET", "https://example.com")
        res = httpx.Response(403, request=req)
        exc = httpx.HTTPStatusError("403 Forbidden", request=req, response=res)
        assert classify_exception(exc) == LiveFailureCategory.HTTP_403

    def test_unknown_exception(self) -> None:
        exc = ValueError("Unknown error")
        assert classify_exception(exc) == LiveFailureCategory.UNKNOWN_FAILURE


class TestClassifyHttpStatus:
    def test_403(self) -> None:
        assert classify_http_status(403) == LiveFailureCategory.HTTP_403

    def test_404(self) -> None:
        assert classify_http_status(404) == LiveFailureCategory.HTTP_404

    def test_429(self) -> None:
        assert classify_http_status(429) == LiveFailureCategory.RATE_LIMITED

    def test_500(self) -> None:
        assert classify_http_status(500) == LiveFailureCategory.NETWORK_ERROR

    def test_400(self) -> None:
        assert classify_http_status(400) == LiveFailureCategory.INVALID_RESPONSE

    def test_200(self) -> None:
        assert classify_http_status(200) == LiveFailureCategory.UNKNOWN_FAILURE


class TestClassifyPaperRetrievalStatus:
    def test_not_found(self) -> None:
        assert classify_paper_retrieval_status(PaperRetrievalStatus.NOT_FOUND) == LiveFailureCategory.DOI_NOT_FOUND

    def test_full_text_unavailable(self) -> None:
        assert classify_paper_retrieval_status(PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE) == LiveFailureCategory.FULL_TEXT_UNAVAILABLE

    def test_parsing_failure(self) -> None:
        assert classify_paper_retrieval_status(PaperRetrievalStatus.PARSING_FAILURE) == LiveFailureCategory.INVALID_DOCUMENT

    def test_provider_error(self) -> None:
        assert classify_paper_retrieval_status(PaperRetrievalStatus.PROVIDER_ERROR) == LiveFailureCategory.NETWORK_ERROR

    def test_success(self) -> None:
        assert classify_paper_retrieval_status(PaperRetrievalStatus.SUCCESS) is None

    def test_metadata_only(self) -> None:
        assert classify_paper_retrieval_status(PaperRetrievalStatus.METADATA_ONLY) is None


class TestShouldRetry:
    def test_retryable_category_within_limit(self) -> None:
        assert should_retry(LiveFailureCategory.NETWORK_TIMEOUT, 0) is True
        assert should_retry(LiveFailureCategory.NETWORK_ERROR, 1) is True
        assert should_retry(LiveFailureCategory.RATE_LIMITED, 2) is True

    def test_retryable_category_exceeds_limit(self) -> None:
        assert should_retry(LiveFailureCategory.NETWORK_TIMEOUT, MAX_RETRIES) is False
        assert should_retry(LiveFailureCategory.NETWORK_ERROR, MAX_RETRIES + 1) is False

    def test_retryable_categories(self) -> None:
        retryable = [
            LiveFailureCategory.NETWORK_TIMEOUT,
            LiveFailureCategory.NETWORK_ERROR,
            LiveFailureCategory.RATE_LIMITED,
            LiveFailureCategory.HTTP_403,
        ]
        for category in retryable:
            assert should_retry(category, 0) is True
            assert should_retry(category, MAX_RETRIES - 1) is True
            assert should_retry(category, MAX_RETRIES) is False

    def test_non_retryable_categories(self) -> None:
        non_retryable = [
            LiveFailureCategory.DOI_NOT_FOUND,
            LiveFailureCategory.FULL_TEXT_UNAVAILABLE,
            LiveFailureCategory.ANTI_BOT_BLOCKED,
            LiveFailureCategory.INVALID_DOCUMENT,
            LiveFailureCategory.LLM_FAILURE,
            LiveFailureCategory.LLM_QUOTA_EXCEEDED,
            LiveFailureCategory.LLM_TIMEOUT,
            LiveFailureCategory.INVALID_RESPONSE,
            LiveFailureCategory.UNKNOWN_FAILURE,
        ]
        for category in non_retryable:
            assert should_retry(category, 0) is False


class TestDeterministicFailureCategories:
    def test_deterministic_failures_not_retried(self) -> None:
        """Test that deterministic failures are in the DETERMINISTIC_FAILURE_CATEGORIES set."""
        expected_deterministic = {
            LiveFailureCategory.DOI_NOT_FOUND,
            LiveFailureCategory.FULL_TEXT_UNAVAILABLE,
            LiveFailureCategory.ANTI_BOT_BLOCKED,
            LiveFailureCategory.PAYWALLED,
            LiveFailureCategory.INVALID_DOCUMENT,
            LiveFailureCategory.HTTP_404,
            LiveFailureCategory.INVALID_RESPONSE,
        }
        assert DETERMINISTIC_FAILURE_CATEGORIES == expected_deterministic

    def test_deterministic_failures_are_not_retryable(self) -> None:
        """Test that deterministic failures are not in RETRYABLE_CATEGORIES."""
        for category in DETERMINISTIC_FAILURE_CATEGORIES:
            assert category not in RETRYABLE_CATEGORIES


class TestConstants:
    def test_max_retries_positive(self) -> None:
        assert MAX_RETRIES > 0

    def test_retryable_categories_not_empty(self) -> None:
        assert len(RETRYABLE_CATEGORIES) > 0

    def test_retryable_categories_are_valid(self) -> None:
        for category in RETRYABLE_CATEGORIES:
            assert isinstance(category, LiveFailureCategory)

    def test_retrieval_and_verification_categories_partition(self) -> None:
        """Test that retrieval and verification categories partition failure types."""
        assert len(RETRIEVAL_FAILURE_CATEGORIES.intersection(VERIFICATION_FAILURE_CATEGORIES)) == 0
        assert LiveFailureCategory.DOI_NOT_FOUND in RETRIEVAL_FAILURE_CATEGORIES
        assert LiveFailureCategory.ANTI_BOT_BLOCKED in RETRIEVAL_FAILURE_CATEGORIES
        assert LiveFailureCategory.LLM_FAILURE in VERIFICATION_FAILURE_CATEGORIES
        assert LiveFailureCategory.LLM_QUOTA_EXCEEDED in VERIFICATION_FAILURE_CATEGORIES
