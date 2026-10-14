"""Actual HTTP Parse → Resolve → Extract → Job bridge; all providers offline."""
import json
from functools import partial
from pathlib import Path

import httpx
import pytest

from app.main import app
from app.api.routes.manuscripts import get_parser_factory, get_extraction_provider_factory, get_reference_resolver
from app.researchguard.domain import ParsedManuscript, ClaimExtractionResult
from app.schemas.claim_extraction import ClaimExtractionRequest
from app.services.citation_context import from_request, fingerprint
from app.services.manuscript_verification import validate_combined_input
from app.services.reference_resolver import resolve_references
from app.tests.test_claim_extractor import FakeProvider
from app.tests.test_verification_jobs import harness
from app.tests.test_manuscript_verification import paper
from app.tests.test_reference_resolver import TITLE, work

FIXTURE = Path(__file__).resolve().parents[3] / "frontend/tests/fixtures/manuscript.json"


@pytest.mark.anyio
async def test_parse_resolve_extract_create_keeps_enriched_fingerprint_and_unicode(harness, monkeypatch):
    original = from_request(ClaimExtractionRequest.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8"))["extraction_request"]))
    data = original.model_dump()
    data["references"] = list(data["references"])
    original_doi = data["references"][0]["doi"]
    data["references"][1].update(title=TITLE, authors=["A Smith", "B Jones"], year=2020, journal="Example Journal", doi=None)
    second = data["references"][1]
    data["references"].extend([
        {**second,"id":"r-url","title":"WHO speech","raw_text":"World Health Organization (https://www.who.int/speech)","authors":[],"journal":None},
        {**second,"id":"r-ambiguous","title":"Ambiguous identity example","raw_text":"Ambiguous identity example"},
        {**second,"id":"r-unresolved","title":None,"raw_text":"No structured metadata","authors":[],"journal":None},
    ])
    original = ParsedManuscript.model_validate(data)
    class Parser:
        async def parse(self, manuscript):
            payload = original.model_dump()
            payload["manuscript"] = manuscript.model_dump()
            for name in ("paragraphs","references","citation_callouts"):
                for item in payload[name]:
                    item["manuscript_id"] = manuscript.id
            return ParsedManuscript.model_validate(payload)
    def handler(request):
        query = request.url.params.get("query.bibliographic", request.url.params.get("search", ""))
        if "Ambiguous" in query:
            items = [work("10.1234/v1", title=["Ambiguous identity example"]), work("10.1234/v2", title=["Ambiguous identity example"])]
        else:
            items = [work()]
        return httpx.Response(200, json={"message":{"items":items}} if "crossref" in request.url.host else {"results":[]})
    h = harness()
    monkeypatch.setenv("RESEARCHGUARD_JOBS_ENABLED", "1")
    monkeypatch.setattr(app.state,"verification_jobs",h.runtime,raising=False)
    app.dependency_overrides[get_parser_factory] = lambda: lambda *_: Parser()
    app.dependency_overrides[get_extraction_provider_factory] = lambda: lambda: FakeProvider()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as providers:
        app.dependency_overrides[get_reference_resolver] = lambda: partial(resolve_references, client=providers)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=("127.0.0.1",1234)),base_url="http://test") as client:
                pdf = (Path(__file__).parent/"fixtures/manuscript.pdf").read_bytes()
                response = await client.post("/api/manuscripts/parse",files={"file":("paper.pdf",pdf,"application/pdf")})
                assert response.status_code == 200
                request = {k:response.json()[k] for k in ("schema_version","scope","offset_unit","parsed")}
                resolved = await client.post("/api/manuscripts/resolve-references",json=request)
                assert resolved.status_code == 200
                enriched = resolved.json()["parsed"]
                assert enriched["references"][0]["doi"] == original_doi
                assert enriched["references"][1]["doi"] == "10.1234/correct"
                assert [r["resolution"]["status"] for r in enriched["references"]] == ["resolved","resolved","non_doi_source","ambiguous","metadata_insufficient"]
                assert enriched["paragraphs"] == request["parsed"]["paragraphs"]
                assert enriched["citation_callouts"] == request["parsed"]["citation_callouts"]
                assert enriched["paragraphs"][0]["text"].startswith("研究🧪")
                for before,after in zip(request["parsed"]["references"],enriched["references"]):
                    assert before["id"] == after["id"] and before["raw_text"] == after["raw_text"]
                extract_request = {k:resolved.json()[k] for k in ("schema_version","scope","offset_unit","parsed")}
                extracted = await client.post("/api/manuscripts/extract-claims",json=extract_request)
                assert extracted.status_code == 200
                extraction = ClaimExtractionResult.model_validate(extracted.json())
                submitted = {**enriched,"manuscript":{**enriched["manuscript"],"content_locator":"submitted:client-structure"},"diagnostics":[]}
                parsed = ParsedManuscript.model_validate(submitted)
                assert extraction.metadata.input_fingerprint == "sha256:" + fingerprint(parsed)
                validate_combined_input(parsed, extraction)
                old_submission = {**request["parsed"],"manuscript":submitted["manuscript"],"diagnostics":[]}
                bad = await client.post("/api/verification/jobs",json={"parsed":old_submission,"extraction":extracted.json()})
                assert bad.status_code == 422
                created = await client.post("/api/verification/jobs",json={"parsed":submitted,"extraction":extracted.json()})
                assert created.status_code == 202
                final = await h.runtime.wait(created.json()["job_id"])
                assert final.parsed == parsed and final.extraction == extraction
                assert "10.1234/correct" in h.sources
                rerequest = await client.post("/api/manuscripts/resolve-references",json=extract_request)
                assert rerequest.status_code == 422 and rerequest.json()["detail"]["code"] == "REFERENCES_ALREADY_ENRICHED"
        finally:
            for dependency in (get_parser_factory,get_extraction_provider_factory,get_reference_resolver):
                app.dependency_overrides.pop(dependency,None)


@pytest.mark.anyio
async def test_resolution_endpoint_validates_structure_and_size():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        for payload in ({}, {"schema_version":True}, {"url":"http://127.0.0.1/private"}):
            response=await client.post("/api/manuscripts/resolve-references",json=payload)
            assert response.status_code == 422
        response=await client.post("/api/manuscripts/resolve-references",content=b" "*(2*1024*1024+1))
        assert response.status_code == 413
