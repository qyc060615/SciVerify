"""Injected structured providers only; concurrency, isolation and safe boundaries."""
import asyncio
import json
import threading
import time

import httpx
import pytest

from app.researchguard.adapters.claim_llm import ClaimLLMAdapter, ClaimLLMError
from app.schemas.claim_extraction import ExtractionProposal
from app.services.citation_context import build_contexts
from app.services.claim_extractor import extract_claims, failure_http_status
from app.services.llm.provider import LLMProvider, LLMProviderError, LLMUnavailableError, LLMResponseError, LLMRateLimitError
from app.tests.test_citation_context import manuscript


class FakeProvider(LLMProvider):
    model = "offline-fake"

    def __init__(self, handler=None):
        self.handler = handler
        self.prompts = []
        self.systems = []
        self.lock = threading.Lock()
        self.active = self.maximum = 0

    def generate(self, prompt, *, system=None, response_model=None):
        payload = json.loads(prompt)
        with self.lock:
            self.prompts.append(payload)
            self.systems.append(system)
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        try:
            if self.handler:
                data = self.handler(payload)
            else:
                quote = payload["focal_text"].split(" [")[0].rstrip(".")
                data = {"claims": [{"text": quote, "source_quotes": [{"quote": quote}], "citation_callout_ids": ["c1"]}]}
            return response_model.model_validate(data)
        finally:
            with self.lock:
                self.active -= 1


def run(parsed, **kwargs):
    return asyncio.run(extract_claims(parsed, **kwargs))


def adapter(provider, parsed=None):
    p = parsed or manuscript()
    c = build_contexts(p)[0].context
    return ClaimLLMAdapter(provider).propose(c, p.paragraphs[0], p.citation_callouts)


def test_single_call_per_sentence_prompt_minimal_and_alias_conversion():
    provider = FakeProvider(lambda p: {"claims": []})
    result = run(manuscript("A improves accuracy [3], while B reduces latency [4]."), provider=provider)
    assert len(provider.prompts) == 1 and result.status == "completed" and not result.claims
    data = provider.prompts[0]
    assert [c["id"] for c in data["callouts"]] == ["c1", "c2"]
    assert "Fixture r" not in json.dumps(data) and "reference_ids" not in data
    assert "Neighbors are read-only" in provider.systems[0]
    assert adapter(FakeProvider()).claims[0].citation_callout_ids == ("callout:0",)


def test_success_stable_ids_fingerprint_and_legacy_contracts():
    a, b = run(manuscript(), provider=FakeProvider()), run(manuscript(), provider=FakeProvider())
    assert a == b and a.status == "completed" and a.metadata.input_provenance == "client_supplied"
    assert a.claims[0].reference_ids == ("r3",)
    from app.researchguard.domain import AtomicClaim, CitationContext
    assert AtomicClaim(id="c", manuscript_id="m", paragraph_id="p", context_id="cx", text="A claim").source_spans == ()
    assert CitationContext(id="cx", manuscript_id="m", paragraph_id="p", text="context").focal_span is None


@pytest.mark.parametrize("p", [manuscript("Copyright 2020."), manuscript(statuses={0: "unresolved"}), manuscript(statuses={0: "partial"}), manuscript("A improves accuracy [3]. B reduces latency [4].", sentences=[])])
def test_skipped_never_creates_provider(p):
    def forbidden():
        pytest.fail("Provider factory called for skipped context")
    result = run(p, provider_factory=forbidden)
    assert result.status == "skipped" and not result.claims and failure_http_status(result) == 200


def test_concurrency_two_and_failure_isolation_stable_order():
    sentences = ["A improves accuracy [3].", "B reduces latency [4].", "C improves precision [5].", "D improves recall [6]."]
    text = " ".join(sentences)
    bounds, start = [], 0
    for s in sentences:
        bounds.append((start, start + len(s)))
        start += len(s) + 1
    def handler(p):
        focal = p["focal_text"]
        time.sleep(.04 if focal.startswith("A") else .01)
        if focal.startswith("B"):
            raise LLMProviderError("PRIVATE_BODY secret-key")
        quote = focal.split(" [")[0]
        return {"claims": [{"text": quote, "source_quotes": [{"quote": quote}], "citation_callout_ids": ["c1"], "association": "abstain" if focal.startswith("C") else "proposed"}]}
    provider = FakeProvider(handler)
    r = run(manuscript(text, bounds), provider=provider)
    assert provider.maximum == 2 and len(provider.prompts) == 4
    assert r.status == "partial"
    assert [x.status.value for x in r.context_results] == ["completed", "failed", "partial", "completed"]
    assert [c.text for c in r.claims] == ["A improves accuracy", "C improves precision", "D improves recall"]
    assert r.claims[1].reference_ids == ()


@pytest.mark.parametrize("error,code,status", [
    (LLMUnavailableError("secret-key"), "EXTRACTION_PROVIDER_UNAVAILABLE", 503),
    (LLMRateLimitError("secret-key"), "EXTRACTION_RATE_LIMITED", 503),
    (LLMResponseError("PRIVATE_BODY"), "EXTRACTION_INVALID_RESPONSE", 502),
    (LLMProviderError("PRIVATE_BODY"), "EXTRACTION_PROVIDER_ERROR", 503),
    (httpx.ReadTimeout("secret-key"), "EXTRACTION_TIMEOUT", 504),
    (RuntimeError("timeout string PRIVATE_BODY"), "EXTRACTION_PROVIDER_ERROR", 503),
])
def test_safe_provider_failures_not_empty_success(error, code, status, caplog):
    def handler(p):
        raise error
    with caplog.at_level("INFO"):
        r = run(manuscript(), provider=FakeProvider(handler))
    assert r.status == "failed" and not r.claims and failure_http_status(r) == status
    assert code in {d.code for d in r.diagnostics}
    combined = r.model_dump_json() + caplog.text
    assert "PRIVATE_BODY" not in combined and "secret-key" not in combined
    assert "A improves accuracy" not in caplog.text


def test_typed_timeout_cause_and_factory_failure_safe():
    error = LLMProviderError("PRIVATE_BODY")
    error.__cause__ = TimeoutError("secret-key")
    def handler(p):
        raise error
    assert failure_http_status(run(manuscript(), provider=FakeProvider(handler))) == 504
    def factory():
        raise RuntimeError("secret-key")
    r = run(manuscript(), provider_factory=factory)
    assert failure_http_status(r) == 503 and "secret-key" not in r.model_dump_json()


@pytest.mark.parametrize("extra", ["reference_ids", "offsets", "verdict"])
def test_invalid_structured_extra_fields(extra):
    def handler(p):
        return {"claims": [{"text": "A improves accuracy", "source_quotes": [{"quote": "A improves accuracy"}], extra: "PRIVATE_BODY"}]}
    with pytest.raises(ClaimLLMError) as e:
        adapter(FakeProvider(handler))
    assert e.value.code == "EXTRACTION_INVALID_RESPONSE" and "PRIVATE_BODY" not in str(e.value)


@pytest.mark.parametrize("raw", ["not JSON PRIVATE_BODY", {}, None])
def test_wrong_provider_return_type(raw):
    class Wrong(FakeProvider):
        def generate(self, *args, **kwargs):
            return raw
    with pytest.raises(ClaimLLMError) as e:
        adapter(Wrong())
    assert e.value.code == "EXTRACTION_INVALID_RESPONSE"


def test_malformed_json_fake_provider_safe():
    class Invalid(FakeProvider):
        def generate(self, prompt, *, response_model=None, **kwargs):
            return response_model.model_validate_json("not JSON PRIVATE_BODY")
    r = run(manuscript(), provider=Invalid())
    assert failure_http_status(r) == 502 and "PRIVATE_BODY" not in r.model_dump_json()


def test_all_invalid_failed_some_valid_partial_and_dedup():
    good = {"text": "A improves accuracy", "source_quotes": [{"quote": "A improves accuracy"}], "citation_callout_ids": ["c1"]}
    bad = {**good, "citation_callout_ids": ["c99"]}
    r = run(manuscript(), provider=FakeProvider(lambda p: {"claims": [bad]}))
    assert r.status == "failed" and failure_http_status(r) == 502
    assert r.context_results[0].rejected_proposals[0].reason_code == "UNKNOWN_CITATION_CALLOUT"
    r = run(manuscript(), provider=FakeProvider(lambda p: {"claims": [good, bad, good]}))
    assert r.status == "partial" and len(r.claims) == 1


@pytest.mark.parametrize("status,body,expected", [
    (400, {"error": {"message": "PRIVATE_BODY secret-key"}}, 503),
    (429, {"error": {"message": "PRIVATE_BODY secret-key"}}, 503),
    (500, {"error": {"message": "PRIVATE_BODY secret-key"}}, 503),
    (200, {"choices": [{"message": {"content": "not JSON PRIVATE_BODY"}}]}, 502),
])
def test_existing_provider_via_injected_mock_transport_safe(status, body, expected, caplog):
    from app.services.llm.provider import OpenAICompatibleLLMProvider
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))) as client:
        provider = OpenAICompatibleLLMProvider(api_key="secret-key", model="offline-fake",
            base_url="https://offline.invalid", max_rate_limit_retries=0, client=client)
        with caplog.at_level("INFO"):
            result = run(manuscript(), provider=provider)
    assert failure_http_status(result) == expected
    combined = result.model_dump_json() + caplog.text
    assert "PRIVATE_BODY" not in combined and "secret-key" not in combined
    assert "A improves accuracy" not in caplog.text


def test_result_revalidates_foreign_links_and_marker_sources():
    from app.researchguard.domain import TextSpan
    from app.services.claim_attribution import validate_result
    parsed = manuscript()
    result = run(parsed, provider=FakeProvider())
    claim = result.claims[0]
    for update in [{"reference_ids": ("invented",)}, {"citation_callout_ids": ("foreign",)},
                   {"source_spans": (TextSpan(start=0, end=len(parsed.paragraphs[0].text)),)}]:
        with pytest.raises(ValueError):
            validate_result(parsed, result.model_copy(update={"claims": (claim.model_copy(update=update),)}))


def test_sentence_boundary_whitespace_keeps_exact_window():
    pieces = ["Background information.", "Further background.", "A improves accuracy [3]."]
    text = " ".join(pieces)
    starts = [0, len(pieces[0]), len(pieces[0]) + 1 + len(pieces[1])]
    bounds = [(starts[0], starts[1]), (starts[1], starts[2]), (starts[2], len(text))]
    result = run(manuscript(text, bounds), provider=FakeProvider())
    context = result.contexts[0]
    assert result.status == "completed"
    assert context.text == text[context.span.start:context.span.end]
