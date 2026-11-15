from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from app.schemas.verification import (
    AdjudicatorAnalysis,
    DefenderAnalysis,
    ProsecutorAnalysis,
    Verdict,
)
from app.services.llm.provider import (
    LLMProviderError,
    LLMResponseError,
    LLMUnavailableError,
    OpenAICompatibleLLMProvider,
    UnavailableLLMProvider,
    _extract_json_content,
    _normalize_structured_payload,
    get_llm_provider,
)


def _mock_llm_response(content: str) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.text = json.dumps(
        {"choices": [{"message": {"content": content}}]}
    )
    response.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return response


def _mock_llm_client(content: str) -> MagicMock:
    client = MagicMock(spec=httpx.Client)
    client.post.return_value = _mock_llm_response(content)
    return client


class TestLLMProvider:
    def test_unavailable_when_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "none")
        monkeypatch.setenv("LLM_API_KEY", "")

        provider = get_llm_provider()
        assert isinstance(provider, UnavailableLLMProvider)

        with pytest.raises(LLMUnavailableError):
            provider.generate("test prompt")

    def test_unsupported_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "unknown-provider")
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        with pytest.raises(LLMUnavailableError):
            get_llm_provider()

    def test_parses_valid_prosecutor_response(self) -> None:
        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=_mock_llm_client(
                json.dumps(
                    {
                        "agent": "prosecutor",
                        "analysis": "Numeric mismatch.",
                        "stance": "skeptical",
                        "key_points": ["12% vs 40%"],
                        "supporting_evidence": [],
                        "contradicting_evidence": ["c1"],
                        "confidence": 0.72,
                    }
                )
            ),
        )

        result = provider.generate(
            "prompt",
            response_model=ProsecutorAnalysis,
        )

        assert isinstance(result, ProsecutorAnalysis)
        assert result.agent == "prosecutor"
        assert result.contradicting_evidence == ["c1"]

    def test_normalizes_capitalized_agent_literal(self) -> None:
        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=_mock_llm_client(
                json.dumps(
                    {
                        "agent": "Prosecutor",
                        "analysis": "Numeric mismatch.",
                        "stance": "skeptical",
                        "key_points": [],
                        "supporting_evidence": [],
                        "contradicting_evidence": ["c1"],
                        "confidence": 0.72,
                    }
                )
            ),
        )

        result = provider.generate(
            "prompt",
            response_model=ProsecutorAnalysis,
        )

        assert isinstance(result, ProsecutorAnalysis)
        assert result.agent == "prosecutor"

    def test_normalizes_evidence_objects_to_chunk_ids(self) -> None:
        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=_mock_llm_client(
                json.dumps(
                    {
                        "agent": "Defender",
                        "analysis": "Evidence supports direction.",
                        "stance": "supportive",
                        "key_points": [],
                        "supporting_evidence": [
                            {"chunk_id": "c1", "text": "Improvement observed."}
                        ],
                        "contradicting_evidence": [],
                        "confidence": 0.68,
                    }
                )
            ),
        )

        result = provider.generate(
            "prompt",
            response_model=DefenderAnalysis,
        )

        assert isinstance(result, DefenderAnalysis)
        assert result.agent == "defender"
        assert result.supporting_evidence == ["c1"]

    def test_parses_adjudicator_with_object_evidence_references(self) -> None:
        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=_mock_llm_client(
                json.dumps(
                    {
                        "agent": "adjudicator",
                        "analysis": "Magnitude overstated.",
                        "verdict": "OVERSTATED",
                        "confidence": 0.9,
                        "reasoning": "Evidence reports 12%, not 40%.",
                        "supporting_evidence": [
                            {"chunk_id": "c1", "text": "12% improvement."}
                        ],
                        "contradicting_evidence": [],
                        "suggested_correction": "The method improves accuracy by 12%.",
                    }
                )
            ),
        )

        result = provider.generate(
            "prompt",
            response_model=AdjudicatorAnalysis,
        )

        assert isinstance(result, AdjudicatorAnalysis)
        assert result.verdict == Verdict.OVERSTATED
        assert result.supporting_evidence == ["c1"]

    def test_strips_markdown_json_fences(self) -> None:
        content = """```json
{
  "agent": "prosecutor",
  "analysis": "Numeric mismatch.",
  "stance": "skeptical",
  "key_points": [],
  "supporting_evidence": [],
  "contradicting_evidence": ["c1"],
  "confidence": 0.72
}
```"""
        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=_mock_llm_client(content),
        )

        result = provider.generate(
            "prompt",
            response_model=ProsecutorAnalysis,
        )

        assert isinstance(result, ProsecutorAnalysis)
        assert result.agent == "prosecutor"

    def test_json_decode_error_includes_details(self) -> None:
        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=_mock_llm_client("not-json"),
        )

        with pytest.raises(LLMResponseError, match="invalid JSON"):
            provider.generate("prompt", response_model=ProsecutorAnalysis)

    def test_validation_error_includes_details(self) -> None:
        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=_mock_llm_client(
                json.dumps(
                    {
                        "agent": "prosecutor",
                        "analysis": "Missing required fields.",
                    }
                )
            ),
        )

        with pytest.raises(LLMResponseError, match="invalid structured output"):
            provider.generate("prompt", response_model=ProsecutorAnalysis)

    def test_response_format_unsupported_returns_clear_error(self) -> None:
        client = MagicMock(spec=httpx.Client)
        response = MagicMock(spec=httpx.Response)
        response.status_code = 400
        response.text = '{"error":{"message":"response_format is not supported"}}'
        response.headers = {}
        client.post.return_value = response

        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=client,
        )

        with pytest.raises(
            LLMProviderError,
            match="does not support structured JSON output",
        ):
            provider.generate("prompt", response_model=ProsecutorAnalysis)

    def test_request_error_includes_exception_details(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.side_effect = httpx.ConnectError("Connection refused")

        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=client,
        )

        with pytest.raises(LLMProviderError, match="ConnectError"):
            provider.generate("prompt", response_model=ProsecutorAnalysis)

    def test_rate_limit_retries_and_succeeds(self) -> None:
        client = MagicMock(spec=httpx.Client)
        rate_limited = MagicMock(spec=httpx.Response)
        rate_limited.status_code = 429
        rate_limited.text = (
            '{"error":{"message":"Rate limit reached. Please try again in 100ms."}}'
        )
        rate_limited.headers = {}

        success = _mock_llm_response(
            json.dumps(
                {
                    "agent": "prosecutor",
                    "analysis": "Test.",
                    "stance": "skeptical",
                    "key_points": [],
                    "supporting_evidence": [],
                    "contradicting_evidence": [],
                    "confidence": 0.5,
                }
            )
        )
        client.post.side_effect = [rate_limited, success]

        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=client,
            max_rate_limit_retries=2,
        )

        result = provider.generate("prompt", response_model=ProsecutorAnalysis)

        assert isinstance(result, ProsecutorAnalysis)
        assert client.post.call_count == 2

    def test_rate_limit_exhausted_returns_clear_error(self) -> None:
        client = MagicMock(spec=httpx.Client)
        rate_limited = MagicMock(spec=httpx.Response)
        rate_limited.status_code = 429
        rate_limited.text = '{"error":{"message":"Rate limit reached."}}'
        rate_limited.headers = {}
        client.post.return_value = rate_limited

        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=client,
            max_rate_limit_retries=1,
        )

        with pytest.raises(LLMProviderError, match="rate limit exceeded"):
            provider.generate("prompt", response_model=ProsecutorAnalysis)

        assert client.post.call_count == 2

    def test_rate_limit_retries_with_seconds_delay(self) -> None:
        client = MagicMock(spec=httpx.Client)
        rate_limited = MagicMock(spec=httpx.Response)
        rate_limited.status_code = 429
        rate_limited.text = (
            '{"error":{"message":"Rate limit reached. Please try again in 0.2s."}}'
        )
        rate_limited.headers = {}

        success = _mock_llm_response(
            json.dumps(
                {
                    "agent": "prosecutor",
                    "analysis": "Test.",
                    "stance": "skeptical",
                    "key_points": [],
                    "supporting_evidence": [],
                    "contradicting_evidence": [],
                    "confidence": 0.5,
                }
            )
        )
        client.post.side_effect = [rate_limited, success]

        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
            client=client,
            max_rate_limit_retries=2,
        )

        result = provider.generate("prompt", response_model=ProsecutorAnalysis)

        assert isinstance(result, ProsecutorAnalysis)
        assert client.post.call_count == 2

    def test_groq_compatible_provider_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "groq-compatible")
        monkeypatch.setenv("LLM_API_KEY", "test-key-long-enough-1234")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        monkeypatch.setenv("LLM_MODEL", "llama-3.3-70b-versatile")

        provider = get_llm_provider()

        assert isinstance(provider, OpenAICompatibleLLMProvider)
        assert provider.base_url == "https://api.groq.com/openai/v1"
        assert provider.model == "llama-3.3-70b-versatile"

    def test_daily_token_quota_exhausted_includes_provider_message(self) -> None:
        client = MagicMock(spec=httpx.Client)
        quota_resp = MagicMock(spec=httpx.Response)
        quota_resp.status_code = 429
        quota_resp.text = (
            '{"error":{"message":"Rate limit reached for model `llama-3.3-70b-versatile` on tokens per day (TPD): Limit 100000, Used 99206, Requested 2332. Please try again in 22m8.832s."}}'
        )
        quota_resp.json.return_value = {
            "error": {
                "message": "Rate limit reached for model `llama-3.3-70b-versatile` on tokens per day (TPD): Limit 100000, Used 99206, Requested 2332. Please try again in 22m8.832s."
            }
        }
        quota_resp.headers = {}
        client.post.return_value = quota_resp

        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1",
            client=client,
            max_rate_limit_retries=2,
        )

        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate("prompt", response_model=ProsecutorAnalysis)

        msg = str(exc_info.value)
        assert "LLM quota exhausted (daily token limit reached)" in msg
        assert "Limit 100000" in msg
        assert "Used 99206" in msg
        assert "Please try again in 22m8.832s" in msg
        # Should fail immediately without retrying
        assert client.post.call_count == 1

    def test_daily_token_quota_exhausted_plain_text_fallback(self) -> None:
        client = MagicMock(spec=httpx.Client)
        quota_resp = MagicMock(spec=httpx.Response)
        quota_resp.status_code = 429
        quota_resp.text = "Error: tokens per day exceeded"
        quota_resp.json.side_effect = ValueError("not json")
        quota_resp.headers = {}
        client.post.return_value = quota_resp

        provider = OpenAICompatibleLLMProvider(
            api_key="test-key",
            model="llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1",
            client=client,
            max_rate_limit_retries=2,
        )

        with pytest.raises(LLMProviderError, match="LLM quota exhausted"):
            provider.generate("prompt", response_model=ProsecutorAnalysis)

        assert client.post.call_count == 1


class TestStructuredPayloadNormalization:
    def test_extract_json_content_strips_fences(self) -> None:
        content = '```json\n{"agent": "prosecutor"}\n```'
        assert _extract_json_content(content) == '{"agent": "prosecutor"}'

    def test_normalize_structured_payload_lowercases_agent(self) -> None:
        normalized = _normalize_structured_payload({"agent": "Prosecutor"})
        assert normalized == {"agent": "prosecutor"}

    def test_normalize_structured_payload_coerces_evidence_objects(self) -> None:
        normalized = _normalize_structured_payload(
            {
                "supporting_evidence": [{"chunk_id": "c1", "text": "example"}],
            }
        )
        assert normalized == {"supporting_evidence": ["c1"]}
