import pytest
import time
import httpx
from app.services.llm.provider import OpenAICompatibleLLMProvider, LLMProviderError

class MockResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.headers = {}
        self.text = text
    def json(self):
        # Return a minimal valid JSON response for success case
        return {"choices": [{"message": {"content": "{\"result\": \"ok\"}"}}]}

def test_quota_exhaustion_no_retry(monkeypatch):
    """When the provider returns a 429 with daily quota information, it should raise immediately without sleeping."""
    def mock_post(self, url, headers=None, json=None):
        return MockResponse(429, "tokens per day (TPD): Limit 100000 Used 99999 Requested 4081")
    monkeypatch.setattr(httpx.Client, "post", mock_post)
    def fake_sleep(seconds):
        raise AssertionError("sleep should not be called on quota exhaustion")
    monkeypatch.setattr(time, "sleep", fake_sleep)
    provider = OpenAICompatibleLLMProvider(
        api_key="dummy",
        model="dummy-model",
        base_url="http://example.com",
        max_rate_limit_retries=3,
    )
    with pytest.raises(LLMProviderError) as exc:
        provider.generate("test prompt")
    assert "quota exhausted" in str(exc.value).lower()

def test_transient_429_retries(monkeypatch):
    """A normal transient 429 (without quota info) should trigger retries and eventual success."""
    call_counter = {"count": 0}
    def mock_post(self, url, headers=None, json=None):
        if call_counter["count"] < 2:
            call_counter["count"] += 1
            return MockResponse(429, "rate limit, try again later")
        return MockResponse(200, "")
    monkeypatch.setattr(httpx.Client, "post", mock_post)
    sleep_calls = []
    def fake_sleep(seconds):
        sleep_calls.append(seconds)
    monkeypatch.setattr(time, "sleep", fake_sleep)
    provider = OpenAICompatibleLLMProvider(
        api_key="dummy",
        model="dummy-model",
        base_url="http://example.com",
        max_rate_limit_retries=3,
    )
    result = provider.generate("test prompt")
    assert len(sleep_calls) == 2
    assert result == "{\"result\": \"ok\"}"
