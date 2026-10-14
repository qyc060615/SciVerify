"""Real HTTP stage bridge with injected parser/provider/verifier; never live E2E."""
import json
from pathlib import Path

import httpx
import pytest

from app.main import app
from app.api.routes.manuscripts import get_parser_factory, get_extraction_provider_factory
from app.schemas.claim_extraction import ClaimExtractionRequest
from app.services.citation_context import from_request
from app.services.manuscript_verification import validate_combined_input
from app.researchguard.domain import ClaimExtractionResult, ParsedManuscript
from app.tests.test_claim_extractor import FakeProvider
from app.tests.test_manuscript_verification import paper
from app.tests.test_verification_jobs import harness


FIXTURE = Path(__file__).resolve().parents[3] / 'frontend/tests/fixtures/manuscript.json'


@pytest.mark.anyio
async def test_parse_extract_job_bridge_unicode_ids_and_diagnostics(harness, monkeypatch):
    data = json.loads(FIXTURE.read_text(encoding='utf-8'))
    public = data['parse_response']
    internal = from_request(ClaimExtractionRequest.model_validate(data['extraction_request']))
    assert internal.diagnostics == () and public['diagnostics']
    assert internal.manuscript.content_locator == 'submitted:client-structure'
    assert internal.paragraphs[0].text.startswith('研究🧪')
    class Parser:
        async def parse(self, manuscript):
            # Keep the true upload identity; all relationships follow it.
            payload = internal.model_dump()
            old = payload['manuscript']['id']
            payload['manuscript'] = manuscript.model_dump()
            for collection in ('paragraphs', 'references', 'citation_callouts'):
                for item in payload[collection]:
                    assert item['manuscript_id'] == old
                    item['manuscript_id'] = manuscript.id
            payload['diagnostics'] = public['diagnostics']
            return ParsedManuscript.model_validate(payload)
    h = harness()
    monkeypatch.setenv('RESEARCHGUARD_JOBS_ENABLED', '1')
    monkeypatch.setattr(app.state, 'verification_jobs', h.runtime, raising=False)
    app.dependency_overrides[get_parser_factory] = lambda: lambda *_: Parser()
    app.dependency_overrides[get_extraction_provider_factory] = lambda: lambda: FakeProvider()
    try:
        pdf = (Path(__file__).parent / 'fixtures/manuscript.pdf').read_bytes()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1234)), base_url='http://test') as client:
            parsed_response = await client.post('/api/manuscripts/parse', files={'file': ('paper.pdf', pdf, 'application/pdf')})
            assert parsed_response.status_code == 200
            parsed = parsed_response.json()['parsed']
            extraction_request = {k: parsed_response.json()[k] for k in ('schema_version', 'scope', 'offset_unit', 'parsed')}
            extracted = await client.post('/api/manuscripts/extract-claims', json=extraction_request)
            assert extracted.status_code == 200
            extraction = ClaimExtractionResult.model_validate(extracted.json())
            job_parsed = {**parsed, 'manuscript': {**parsed['manuscript'], 'content_locator': 'submitted:client-structure'}, 'diagnostics': []}
            validated, _ = validate_combined_input(ParsedManuscript.model_validate(job_parsed), extraction)
            assert validated == from_request(ClaimExtractionRequest.model_validate(extraction_request))
            created = await client.post('/api/verification/jobs', json={'parsed': job_parsed, 'extraction': extracted.json()})
            assert created.status_code == 202
            result = await h.runtime.wait(created.json()['job_id'])
            assert [p.id for p in result.parsed.paragraphs] == [p['id'] for p in parsed['paragraphs']]
            assert result.extraction == extraction
            assert any(r.doi is None for r in result.parsed.references)
    finally:
        app.dependency_overrides.pop(get_parser_factory, None)
        app.dependency_overrides.pop(get_extraction_provider_factory, None)


def test_frontend_golden_job_payload_matches_m3b_reconstruction():
    data = json.loads(FIXTURE.read_text(encoding='utf-8'))
    rebuilt = from_request(ClaimExtractionRequest.model_validate(data['extraction_request']))
    submitted = ParsedManuscript.model_validate(data['job_request']['parsed'])
    extraction = ClaimExtractionResult.model_validate(data['job_request']['extraction'])
    assert rebuilt == submitted
    validate_combined_input(submitted, extraction)


@pytest.mark.anyio
async def test_ambiguous_citation_bridge_does_not_invent_pairs(harness):
    from app.tests.test_citation_context import manuscript
    from app.services.claim_extractor import extract_claims
    from app.schemas.manuscript import ManuscriptParseResponse
    original = manuscript('A improves accuracy [3], while B reduces latency [4].')
    public = ManuscriptParseResponse.from_domain(original).model_dump(mode='json')
    request = {k: public[k] for k in ('schema_version', 'scope', 'offset_unit', 'parsed')}
    rebuilt = from_request(ClaimExtractionRequest.model_validate(request))
    # A globally cited proposal spanning both clauses must keep ambiguous attribution.
    provider = FakeProvider(handler=lambda p: {'claims': [{'text': 'A improves accuracy and B reduces latency',
        'evidence_quote': p['focal_text'], 'citation_labels': ['3', '4']}]})
    extraction = await extract_claims(rebuilt, provider_factory=lambda: provider)
    assert extraction.claims and extraction.claims[0].attribution_status == 'ambiguous'
    validate_combined_input(rebuilt, extraction)
    h = harness()
    job = await h.runtime.create(rebuilt, extraction)
    final = await h.runtime.wait(job.job_id)
    assert final.tasks == () and final.attribution_blocked
    assert not h.sources and not h.verified


def test_upload_limits_are_actual_runtime_settings(monkeypatch):
    from app.api.routes.manuscripts import upload_limits
    monkeypatch.setenv('RESEARCHGUARD_MANUSCRIPT_MAX_SIZE', '1234')
    monkeypatch.setenv('RESEARCHGUARD_SOURCE_MAX_SIZE', '5678')
    assert upload_limits() == {'manuscript_max_bytes': 1234, 'source_max_bytes': 5678}
