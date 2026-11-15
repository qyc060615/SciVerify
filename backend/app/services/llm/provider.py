from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import LLM_BASE_URL, LLM_MODEL, LLM_REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE_PATTERN = re.compile(
    r"^\s*(?:```(?:json)?\s*\n?)?(.*?)(?:\n?\s*```)?\s*$",
    re.DOTALL | re.IGNORECASE,
)
_RETRY_AFTER_PATTERN = re.compile(
    r"try again in (\d+(?:\.\d+)?)(ms|s)",
    re.IGNORECASE,
)
_DEFAULT_RATE_LIMIT_RETRIES = 5
_DEFAULT_RATE_LIMIT_DELAY_SECONDS = 1.0


class LLMProviderError(Exception):
    """Raised when an LLM provider fails."""


class LLMRateLimitError(LLMProviderError):
    """Raised when an LLM provider hits rate limits or quota exhaustion."""


class LLMUnavailableError(LLMProviderError):
    """Raised when no LLM provider is configured or available."""


class LLMResponseError(LLMProviderError):
    """Raised when an LLM response cannot be parsed or validated."""


class LLMProvider(ABC):
    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_model: type[T] | None = None,
    ) -> T | str:
        """Generate a response from the configured LLM provider."""


class UnavailableLLMProvider(LLMProvider):
    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_model: type[T] | None = None,
    ) -> T | str:
        raise LLMUnavailableError(
            "LLM provider is not configured. Set LLM_PROVIDER and LLM_API_KEY to enable verification agents."
        )


def _extract_json_content(content: str) -> str:
    """Strip optional Markdown code fences from LLM JSON output."""
    match = _JSON_FENCE_PATTERN.match(content)
    if match is None:
        return content.strip()
    return match.group(1).strip()


def _normalize_evidence_id_list(value: Any) -> Any:
    """Coerce provider-specific evidence references to chunk_id strings."""
    if not isinstance(value, list):
        return value

    normalized: list[Any] = []
    for item in value:
        if isinstance(item, str):
            normalized.append(item)
            continue
        if isinstance(item, dict):
            chunk_id = item.get("chunk_id")
            if isinstance(chunk_id, str):
                normalized.append(chunk_id)
                continue
        normalized.append(item)
    return normalized


def _normalize_structured_payload(parsed: Any) -> Any:
    """Apply provider-specific compatibility fixes before Pydantic validation."""
    if not isinstance(parsed, dict):
        return parsed

    normalized = dict(parsed)

    agent = normalized.get("agent")
    if isinstance(agent, str):
        normalized["agent"] = agent.strip().lower()

    verdict = normalized.get("verdict")
    if isinstance(verdict, str):
        normalized["verdict"] = verdict.strip().upper()

    for key in ("supporting_evidence", "contradicting_evidence"):
        if key in normalized:
            normalized[key] = _normalize_evidence_id_list(normalized[key])

    return normalized


def _build_timeout(timeout: float) -> httpx.Timeout:
    return httpx.Timeout(timeout=timeout, connect=min(10.0, timeout))


def _parse_rate_limit_delay(response: httpx.Response) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return max(float(retry_after), 0.1)
        except ValueError:
            pass

    match = _RETRY_AFTER_PATTERN.search(response.text)
    if match:
        value = float(match.group(1))
        unit = match.group(2).lower()
        if unit == "ms":
            return max(value / 1000.0, 0.1)
        return max(value, 0.1)

    return _DEFAULT_RATE_LIMIT_DELAY_SECONDS


def _safe_provider_error_body(response: httpx.Response) -> str:
    return response.text[:1000]


def _provider_error_message(response: httpx.Response) -> str:
    status = response.status_code
    body = _safe_provider_error_body(response)

    if status == 429:
        return "LLM provider rate limit exceeded (HTTP 429). Please retry shortly."

    if status == 401:
        return "LLM provider rejected the request: invalid API key (HTTP 401)."

    if status == 403:
        return "LLM provider rejected the request: access denied (HTTP 403)."

    if (
        status == 400
        and "response_format" in body.lower()
    ):
        return (
            "LLM provider or model does not support structured JSON output "
            "(response_format)."
        )

    if body:
        return f"LLM provider rejected the request (HTTP {status}): {body}"

    return f"LLM provider rejected the request (HTTP {status})."


class OpenAICompatibleLLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = LLM_REQUEST_TIMEOUT,
        max_rate_limit_retries: int = _DEFAULT_RATE_LIMIT_RETRIES,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_rate_limit_retries = max_rate_limit_retries
        self._client = client

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        response_model: type[T] | None = None,
    ) -> T | str:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=_build_timeout(self.timeout))

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }
        if response_model is not None:
            payload["response_format"] = {"type": "json_object"}

        request_url = f"{self.base_url}/chat/completions"
        logger.info(
            "LLM request prepared: url=%s model=%s api_key_configured=%s payload_keys=%s message_count=%s response_format=%s",
            request_url,
            self.model,
            bool(self.api_key),
            sorted(payload.keys()),
            len(messages),
            response_model is not None,
        )

        try:
            response = self._post_chat_completion(
                client,
                request_url,
                payload,
            )
        except httpx.TimeoutException as exc:
            logger.error(
                "LLM request timed out: exception=%s url=%s model=%s",
                type(exc).__name__,
                request_url,
                self.model,
            )
            raise LLMProviderError(
                f"LLM request timed out: {type(exc).__name__}."
            ) from exc
        except httpx.RequestError as exc:
            logger.error(
                "LLM request failed: exception=%s url=%s model=%s",
                type(exc).__name__,
                request_url,
                self.model,
            )
            raise LLMProviderError(
                f"LLM request failed: {type(exc).__name__}."
            ) from exc
        finally:
            if owns_client:
                client.close()

        if response.status_code >= 500:
            logger.error(
                "LLM provider unavailable: status=%s url=%s model=%s",
                response.status_code,
                request_url,
                self.model,
            )
            raise LLMProviderError(
                f"LLM provider is unavailable (HTTP {response.status_code})."
            )

        if response.status_code == 429:
            logger.error(
                "LLM provider rate limited (HTTP 429): status=%s url=%s model=%s",
                response.status_code,
                request_url,
                self.model,
            )
            raise LLMRateLimitError(_provider_error_message(response))

        if response.status_code >= 400:
            logger.error(
                "LLM provider rejected the request: status=%s url=%s model=%s",
                response.status_code,
                request_url,
                self.model,
            )
            raise LLMProviderError(_provider_error_message(response))

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("LLM returned an unexpected response format.") from exc

        if response_model is None:
            return content

        content = _extract_json_content(content)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("LLM JSON decode error")
            raise LLMResponseError("LLM returned invalid JSON.") from exc

        try:
            normalized = _normalize_structured_payload(parsed)
            return response_model.model_validate(normalized)
        except ValidationError as exc:
            logger.error("LLM validation error")
            raise LLMResponseError(
                "LLM returned invalid structured output."
            ) from exc

    def _post_chat_completion(
        self,
        client: httpx.Client,
        request_url: str,
        payload: dict[str, Any],
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(self.max_rate_limit_retries + 1):
            response = client.post(request_url, headers=headers, json=payload)

            if response.status_code != 429:
                return response

            # Detect permanent daily quota exhaustion
            lower_text = response.text.lower()
            if "tokens per day" in lower_text or "tpd" in lower_text:
                error_msg = None
                try:
                    err_json = response.json()
                    error_msg = err_json.get("error", {}).get("message")
                except Exception:
                    pass
                if error_msg:
                    raise LLMRateLimitError(
                        f"LLM quota exhausted (daily token limit reached): {error_msg}"
                    )
                raise LLMRateLimitError(
                    "LLM quota exhausted (daily token limit reached)."
                )

            if attempt >= self.max_rate_limit_retries:
                return response

            delay = _parse_rate_limit_delay(response)
            logger.warning(
                "LLM rate limited (HTTP 429): url=%s model=%s attempt=%s/%s retry_in=%.2fs",
                request_url,
                self.model,
                attempt + 1,
                self.max_rate_limit_retries,
                delay,
            )
            time.sleep(delay)

        return response


def get_llm_provider() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "none").strip().lower()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", LLM_MODEL).strip()
    base_url = os.getenv("LLM_BASE_URL", LLM_BASE_URL).strip().rstrip("/")
    max_rate_limit_retries = int(
        os.getenv("LLM_MAX_RETRIES", str(_DEFAULT_RATE_LIMIT_RETRIES))
    )

    logger.info(
        "LLM provider config: provider=%s model=%s base_url=%s api_key_configured=%s max_rate_limit_retries=%s",
        provider,
        model,
        base_url,
        bool(api_key),
        max_rate_limit_retries,
    )

    if provider in {"", "none", "disabled"} or not api_key:
        return UnavailableLLMProvider()

    if provider in {
        "openai",
        "openai-compatible",
        "compatible",
        "groq",
        "groq-compatible",
    }:
        return OpenAICompatibleLLMProvider(
            api_key=api_key,
            model=model,
            base_url=base_url,
            max_rate_limit_retries=max_rate_limit_retries,
        )

    raise LLMUnavailableError(f"Unsupported LLM provider: {provider}")
