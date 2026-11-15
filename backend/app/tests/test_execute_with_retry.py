import pytest
from app.evaluation.live_diagnostics import (
    execute_with_retry,
    classify_exception,
    LiveFailureCategory,
    DETERMINISTIC_FAILURE_CATEGORIES,
    RETRYABLE_CATEGORIES,
)
from app.services.document_retriever import PaywallError
from app.services.paper_retriever import PaperNotFoundError, FullTextUnavailableError
from app.services.llm.provider import LLMProviderError

class DummyError(Exception):
    pass


def test_execute_with_retry_deterministic(monkeypatch):
    # Simulate a deterministic failure (paywall) which should not be retried
    call_count = {'c': 0}
    def fn():
        call_count['c'] += 1
        raise PaywallError("paywall encountered")
    with pytest.raises(PaywallError):
        execute_with_retry(fn, case_id="case1")
    assert call_count['c'] == 1


def test_execute_with_retry_retryable(monkeypatch):
    attempts = []
    # Simulate a transient failure that becomes retryable via classification
    def fn():
        attempts.append(1)
        if len(attempts) < 3:
            raise DummyError("transient")
        return "ok"
    # Patch classification to mark DummyError as a retryable category
    monkeypatch.setattr('app.evaluation.live_diagnostics.classify_exception', lambda exc: LiveFailureCategory.NETWORK_TIMEOUT)
    result, category, reason, attempt_count = execute_with_retry(fn, case_id="case2")
    assert result == "ok"
    assert attempt_count == 3
    assert category is None
    assert reason is None
