"""Untrusted DTO, bounded requests and injected providers; no retrieval side effects."""
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.routes.manuscripts import get_extraction_provider_factory
from app.services.llm.provider import LLMUnavailableError, LLMResponseError
from app.tests.test_citation_context import manuscript, request_payload
from app.tests.test_claim_extractor import FakeProvider


@pytest.fixture
def api(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("Forbidden production entry called"))
    monkeypatch.setattr("app.services.llm.provider.get_llm_provider", forbidden)
    monkeypatch.setattr("app.services.paper_retriever.retrieve_paper", forbidden)
    monkeypatch.setattr("app.researchguard.adapters.paperqa2.PaperQA2EvidenceRetriever", forbidden)
    monkeypatch.setattr("app.services.manuscript_parser.create_parser", forbidden)
    provider = FakeProvider()
    app.dependency_overrides[get_extraction_provider_factory] = lambda: lambda: provider
    with TestClient(app) as client:
        yield client, provider
    app.dependency_overrides.pop(get_extraction_provider_factory, None)
    forbidden.assert_not_called()


def test_api_success_contract_no_verdict_or_source_readiness(api):
    client, provider = api
    r = client.post("/api/manuscripts/extract-claims", json=request_payload(manuscript()))
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert r.json()["claims"][0]["reference_ids"] == ["r3"] and len(provider.prompts) == 1
    for key in ["verdict", "content_locator", "VerificationCandidate", "ReferenceBinding", "confidence"]:
        assert key not in r.text


@pytest.mark.parametrize("field,value", [("provider", "secret-key"), ("model", "secret-key"), ("prompt", "secret-key"), ("source_url", "secret-key"), ("schema_version", True), ("offset_unit", "byte"), ("scope", "whole_paper")])
def test_api_rejects_client_controls_without_echo(api, field, value):
    client, provider = api
    data = request_payload(manuscript())
    data[field] = value
    r = client.post("/api/manuscripts/extract-claims", json=data)
    assert r.status_code == 422 and "secret-key" not in r.text and not provider.prompts


@pytest.mark.parametrize("corruption", ["unknown_reference", "locator", "prebuilt_context", "duplicate", "order", "text", "missing_span", "reference_ids_null", "paragraphs_null"])
def test_api_graph_invalid_no_provider(api, corruption):
    client, provider = api
    data = request_payload(manuscript())
    parsed = data["parsed"]
    if corruption == "unknown_reference":
        parsed["citation_callouts"][0]["reference_ids"] = ["unknown"]
    elif corruption == "locator":
        parsed["manuscript"]["content_locator"] = "secret-key"
    elif corruption == "prebuilt_context":
        parsed["citation_contexts"] = [{"text": "secret-key"}]
    elif corruption == "duplicate":
        parsed["references"] *= 2
    elif corruption == "order":
        parsed["paragraphs"][0]["order"] = 5
    elif corruption == "text":
        parsed["citation_callouts"][0]["text"] = "[9]"
    elif corruption == "missing_span":
        del parsed["citation_callouts"][0]["span"]
    elif corruption == "reference_ids_null":
        parsed["citation_callouts"][0]["reference_ids"] = None
    else:
        parsed["paragraphs"] = None
    r = client.post("/api/manuscripts/extract-claims", json=data)
    assert r.status_code == 422 and "secret-key" not in r.text and not provider.prompts


def test_request_byte_limit_and_malformed_json(api):
    client, provider = api
    r = client.post("/api/manuscripts/extract-claims", content=b" " * (2 * 1024 * 1024 + 1))
    assert r.status_code == 413 and not provider.prompts
    r = client.post("/api/manuscripts/extract-claims", content=b'{"secret-key":')
    assert r.status_code == 422 and "secret-key" not in r.text


@pytest.mark.parametrize("exception,status", [(LLMUnavailableError("PRIVATE_BODY secret-key"), 503), (LLMResponseError("PRIVATE_BODY secret-key"), 502), (TimeoutError("PRIVATE_BODY secret-key"), 504)])
def test_provider_failure_safe_http_response(api, exception, status, caplog):
    client, provider = api
    def fail(p):
        raise exception
    provider.handler = fail
    r = client.post("/api/manuscripts/extract-claims", json=request_payload(manuscript()))
    assert r.status_code == status and r.json()["status"] == "failed"
    assert "secret-key" not in r.text + caplog.text and "PRIVATE_BODY" not in r.text + caplog.text


def test_no_claims_success_skipped_not_failure(api):
    client, provider = api
    provider.handler = lambda p: {"claims": []}
    r = client.post("/api/manuscripts/extract-claims", json=request_payload(manuscript()))
    assert r.status_code == 200 and r.json()["status"] == "completed" and not r.json()["claims"]
    provider.prompts.clear()
    r = client.post("/api/manuscripts/extract-claims", json=request_payload(manuscript(statuses={0: "unresolved"})))
    assert r.status_code == 200 and r.json()["status"] == "skipped" and not provider.prompts


def test_context_limit_before_any_provider_call(api):
    client, provider = api
    pieces = [f"Method improves accuracy [{i}]." for i in range(65)]
    text = " ".join(pieces)
    bounds, start = [], 0
    for s in pieces:
        bounds.append((start, start + len(s)))
        start += len(s) + 1
    r = client.post("/api/manuscripts/extract-claims", json=request_payload(manuscript(text, bounds)))
    assert r.status_code == 413 and r.json()["detail"]["code"] == "EXTRACTION_CONTEXT_LIMIT"
    assert not provider.prompts


def test_total_text_limit_before_provider(api):
    client, provider = api
    data = request_payload(manuscript("x" * 100001))
    paragraph = {**data["parsed"]["paragraphs"][0], "id": "p2", "order": 1}
    data["parsed"]["paragraphs"].append(paragraph)
    r = client.post("/api/manuscripts/extract-claims", json=data)
    assert r.status_code == 413 and not provider.prompts


@pytest.mark.parametrize("collection,limit", [("paragraphs", 1000), ("references", 2000), ("citation_callouts", 2000)])
def test_collection_limits(api, collection, limit):
    client, provider = api
    data = request_payload(manuscript())
    data["parsed"][collection] = data["parsed"][collection] * (limit + 1)
    r = client.post("/api/manuscripts/extract-claims", json=data)
    assert r.status_code == 422 and not provider.prompts


def test_actual_m3a_projection_roundtrip(api):
    from pathlib import Path
    from app.researchguard.adapters.grobid_tei import parse_tei
    from app.researchguard.domain import Manuscript
    from app.schemas.manuscript import ManuscriptParseResponse
    client, provider = api
    parsed = parse_tei((Path(__file__).parent / "fixtures" / "manuscript.tei.xml").read_bytes(),
                       Manuscript(id="m", content_locator="memory:test"))
    response = ManuscriptParseResponse.from_domain(parsed).model_dump(mode="json")
    data = {k: response[k] for k in ("schema_version", "scope", "offset_unit", "parsed")}
    provider.handler = lambda p: {"claims": []}
    r = client.post("/api/manuscripts/extract-claims", json=data)
    assert r.status_code == 200 and r.json()["status"] in {"partial", "completed"}
    assert provider.prompts  # Existing TEI fixture, no GROBID or fixture edits.


def test_invalid_unicode_input_safe_422(api):
    import json
    client, provider = api
    data = request_payload(manuscript())
    data["parsed"]["manuscript"]["title"] = "\ud800"
    r = client.post("/api/manuscripts/extract-claims", content=json.dumps(data, ensure_ascii=True),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and not provider.prompts
