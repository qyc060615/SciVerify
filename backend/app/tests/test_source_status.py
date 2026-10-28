"""Real file/cache checks and a pre-upload → durable job integration; no paid APIs."""
import hashlib
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.citation import CitationMetadata
from app.services.source_store import LocalSourceStore
from app.services import paper_retriever
from app.tests.test_source_lifecycle import pdf_bytes, DOI, TITLE, CITATION
from app.tests.test_verification_jobs import harness  # noqa: F401
from app.tests.test_manuscript_verification import paper, inputs  # noqa: F401


def test_status_requires_real_current_pointer_and_valid_file(monkeypatch):
    monkeypatch.setattr('app.services.manual_source.resolve_doi', lambda _: CITATION)
    client = TestClient(app)
    locator = {'kind': 'doi', 'value': DOI}
    assert client.post('/api/sources/status', json=locator).json()['availability'] == 'not_cached'
    content = pdf_bytes()
    uploaded = client.post('/api/sources/manual', data={'doi': DOI}, files={'file': ('ref.pdf', content, 'application/pdf')})
    digest = uploaded.json()['raw_content_sha256']
    response = client.post('/api/sources/status', json=locator)
    assert response.headers['cache-control'] == 'no-store'
    assert response.json() == {'availability': 'available', 'remote_status': 'not_checked', 'raw_content_sha256': digest, 'format': 'pdf'}
    assert digest == hashlib.sha256(content).hexdigest()
    raw = LocalSourceStore().root / digest / 'source.pdf'
    raw.write_bytes(b'corrupt')
    assert client.post('/api/sources/status', json=locator).json()['availability'] == 'not_cached'
    raw.unlink()
    assert client.post('/api/sources/status', json=locator).json()['raw_content_sha256'] is None


def test_status_rejects_remote_and_invalid_locators():
    client = TestClient(app, client=('198.51.100.1', 1234))
    assert client.post('/api/sources/status', json={'kind': 'doi', 'value': DOI}).status_code == 403
    assert TestClient(app).post('/api/sources/status', json={'kind': 'doi', 'value': '../../fake'}).status_code == 422


@pytest.mark.anyio
async def test_preuploaded_pdf_is_read_by_later_job_without_remote_retrieval(harness, monkeypatch):
    h = harness(blocked=['10.1234/local'])
    monkeypatch.setenv('RESEARCHGUARD_JOBS_ENABLED', '1')
    monkeypatch.setenv('RESEARCHGUARD_SOURCE_CACHE_DIR', str(h.source_store.root))
    monkeypatch.setattr(app.state, 'verification_jobs', h.runtime, raising=False)
    doi = '10.1234/local'
    monkeypatch.setattr('app.services.manual_source.resolve_doi', lambda _: CitationMetadata(
        doi=doi, title=TITLE, authors=['Ada Lovelace'], year=2020, source='crossref', type='journal-article'))
    def no_network(*_, **__):
        raise AssertionError('A preuploaded source must be reused before remote retrieval')
    monkeypatch.setattr(paper_retriever, 'resolve_doi', no_network)
    retrieved = []
    def cached_retrieval(value):
        response = paper_retriever.retrieve_paper(value)
        retrieved.append(response)
        return response
    h.runtime.core_dependencies['source_retriever'] = cached_retrieval
    await h.runtime.start()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1234)), base_url='http://local') as client:
        content = pdf_bytes([TITLE, 'Ada Lovelace 2020', 'doi: ' + doi, 'Results', 'Treatment reduces risk by 12% in patients.'])
        uploaded = await client.post('/api/sources/manual', data={'doi': doi}, files={'file': ('ref.pdf', content, 'application/pdf')})
        assert uploaded.status_code == 200
        digest = uploaded.json()['raw_content_sha256']
        checked = await client.post('/api/sources/status', json={'kind': 'doi', 'value': doi})
        assert checked.json()['raw_content_sha256'] == digest
        parsed, extraction = inputs()
        created = await client.post('/api/verification/jobs', json={'parsed': parsed.model_dump(mode='json'), 'extraction': extraction.model_dump(mode='json')})
        assert created.status_code == 202
        final = await h.runtime.wait(created.json()['job_id'])
        assert final.state.value == 'completed'
        assert final.tasks[0].source_version == 'sha256:' + digest
        assert retrieved[0].source.cache_hit
        assert retrieved[0].source.raw_content_sha256 == digest
        assert len(h.verified) == 1
        assert h.source_store.get(doi).content == content
