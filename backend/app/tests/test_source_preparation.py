"""Stage 2 HTTP → real source bytes → Stage 4 cache/evidence/verifier, offline."""
import hashlib
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from app.main import app
from app.schemas.citation import CitationMetadata
from app.services import paper_retriever as retrieval, source_acquisition
from app.services.document_retriever import RetrievedDocument, DocumentRetrievalError
from app.services.source_store import LocalSourceStore
from app.tests.test_source_lifecycle import pdf_bytes, TITLE
from app.tests.test_unified_source import ref, HTML, URL, PROSE, TITLE as URL_TITLE, url_inputs
from app.tests.test_verification_jobs import harness  # noqa: F401
from app.tests.test_manuscript_verification import inputs, paper  # noqa: F401

DOI = '10.1234/local'


def doi_setup(monkeypatch):
    content = pdf_bytes([TITLE, 'Ada Lovelace 2020', 'doi: ' + DOI, 'Results', 'Treatment reduces risk by 12% in patients.'])
    monkeypatch.setattr(retrieval, 'resolve_doi', lambda *a, **k: CitationMetadata(
        doi=DOI, title=TITLE, authors=['Ada Lovelace'], year=2020, source='crossref', type='journal-article'))
    monkeypatch.setattr(retrieval, '_fetch_openalex_work', lambda *a: None)
    monkeypatch.setattr(retrieval, '_discover_europe_pmc_candidates', lambda *a: [retrieval.FullTextCandidate('https://example.org/paper.pdf', 'pdf', 'fixture')])
    for name in ('_discover_unpaywall_candidates', '_discover_semantic_scholar_candidates'):
        monkeypatch.setattr(retrieval, name, lambda *a: [])
    return content


def transport(monkeypatch, content, content_type='text/html', redirect=None):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={'location': redirect}) if redirect else httpx.Response(
            200, content=content, headers={'content-type': content_type})
    monkeypatch.setattr('app.services.public_http.source_client', lambda *a, **k: httpx.Client(transport=httpx.MockTransport(handler)))
    return seen


def check(client, reference, retrieve=False):
    response = client.post('/api/sources/prepare', json={'reference': reference.model_dump(mode='json'), 'retrieve': retrieve})
    assert response.status_code == 200, response.text
    return response.json()


def test_doi_fetch_persistence_real_hash_and_local_check(monkeypatch):
    parsed, _ = inputs()
    reference = parsed.references[0]
    content = doi_setup(monkeypatch)
    seen = transport(monkeypatch, content, 'application/pdf')
    client = TestClient(app)
    assert check(client, reference)['state'] == 'not_cached'
    assert seen == []
    response = client.post('/api/papers/retrieve', json={'doi': DOI})
    assert response.json()['status'] == 'success'
    saved = check(client, reference)
    assert saved['state'] == 'available'
    assert saved['raw_content_sha256'] == hashlib.sha256(content).hexdigest()
    assert saved['source']['cache_hit'] is True
    assert len(seen) == 1
    assert check(client, reference)['state'] == 'available'
    assert len(seen) == 1


def test_retrieval_success_without_disk_persistence_is_not_available(monkeypatch):
    content = doi_setup(monkeypatch)
    transport(monkeypatch, content, 'application/pdf')
    def fail(*a):
        raise OSError('private server path must not escape')
    monkeypatch.setattr(LocalSourceStore, 'put', fail)
    client = TestClient(app)
    assert client.post('/api/papers/retrieve', json={'doi': DOI}).json()['status'] == 'success'
    parsed, _ = inputs()
    result = check(client, parsed.references[0])
    assert result['state'] != 'available' and result['raw_content_sha256'] is None
    result = check(client, ref(), retrieve=True)
    assert result['state'] != 'available' and 'private server path' not in str(result)


def test_url_preparation_persists_exact_locator_without_job(monkeypatch):
    seen = transport(monkeypatch, HTML)
    client = TestClient(app)
    assert check(client, ref())['state'] == 'not_cached' and not seen
    result = check(client, ref(), retrieve=True)
    assert result['state'] == 'available'
    assert result['source']['locator'] == {'kind': 'url', 'value': URL}
    assert result['raw_content_sha256'] == hashlib.sha256(HTML).hexdigest()
    assert check(client, ref())['state'] == 'available' and len(seen) == 1


@pytest.mark.parametrize('content', [b'<main><h1>Abstract</h1><p>Only an abstract.</p></main>', b'<html>Error</html>'])
def test_url_abstract_and_error_are_not_fulltext(monkeypatch, content):
    transport(monkeypatch, content)
    result = check(TestClient(app), ref(), retrieve=True)
    assert result['state'] == 'unavailable' and result['raw_content_sha256'] is None


@pytest.mark.parametrize('url', ['http://127.0.0.1/a', 'http://169.254.169.254/latest/meta-data', 'file:///tmp/a', 'http://localhost/a', 'http://[::1]/a'])
def test_unsafe_url_is_rejected_before_contact(monkeypatch, url):
    seen = transport(monkeypatch, HTML)
    result = check(TestClient(app), ref(url=url), retrieve=True)
    assert result['state'] == 'needs_attention' and not seen


def test_url_redirect_to_metadata_is_not_contacted(monkeypatch):
    seen = transport(monkeypatch, HTML, redirect='http://169.254.169.254/latest/meta-data')
    result = check(TestClient(app), ref(), retrieve=True)
    assert result['state'] != 'available'
    assert seen == [URL]


def test_ambiguous_reference_with_explicit_url_downloads_and_verifies_bytes(monkeypatch):
    from app.researchguard.domain import ReferenceResolution
    reference = ref().model_copy(update={'resolution': ReferenceResolution(reference_id='r1', status='ambiguous', match_reason='MULTIPLE_IDENTITIES')})
    seen = transport(monkeypatch, HTML)
    result = check(TestClient(app), reference, retrieve=True)
    assert result['state'] == 'available'
    assert result['raw_content_sha256'] == hashlib.sha256(HTML).hexdigest()
    assert seen == [URL]
    assert result['candidates'][0]['attempted'] is True


def test_url_manual_pdf_preserves_manual_origin_and_accepts_unconfirmed_identity():
    text = pdf_bytes([URL_TITLE, 'October 2020', 'Purpose', PROSE * 15, 'Background', PROSE * 15], metadata={'/Title': URL_TITLE})
    writer = PdfWriter(); writer.clone_document_from_reader(PdfReader(BytesIO(text))); writer.add_blank_page(width=612, height=792)
    output = BytesIO(); writer.write(output); content = output.getvalue()
    client = TestClient(app)
    response = client.post('/api/sources/manual-reference', data={'reference': ref().model_dump_json()}, files={'file': ('source.pdf', content, 'application/pdf')})
    assert response.status_code == 200, response.text
    result = check(client, ref())
    assert result['state'] == 'available' and result['source']['origin'] == 'manual'
    assert result['source']['url'] is None and result['source']['provenance']['final_url'] is None
    assert result['raw_content_sha256'] == hashlib.sha256(content).hexdigest()
    wrong = client.post('/api/sources/manual-reference', data={'reference': ref(title='Unrelated childhood nutrition policy and food safety guidance').model_dump_json()}, files={'file': ('wrong.pdf', content, 'application/pdf')})
    assert wrong.status_code == 200 and wrong.json()['identity_match'] == 'uncertain'
    uncertain = check(client, ref(title='Unrelated childhood nutrition policy and food safety guidance'))
    assert uncertain['state'] == 'available' and uncertain['identity'] == 'UNCERTAIN'


def test_prepare_is_loopback_only():
    assert TestClient(app, client=('198.51.100.1', 1234)).post('/api/sources/prepare', json={'reference': ref().model_dump(mode='json')}).status_code == 403


def test_simultaneous_doi_downloads_share_persisted_source(monkeypatch):
    content = doi_setup(monkeypatch)
    entered, release = Event(), Event()
    calls = []
    def download(*a, **k):
        calls.append(1); entered.set(); assert release.wait(5)
        return RetrievedDocument(content, None, 'pdf', 'application/pdf', 'https://example.org/paper.pdf')
    monkeypatch.setattr(retrieval, 'retrieve_document', download)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(retrieval.retrieve_paper, DOI)
        assert entered.wait(5)
        second = executor.submit(retrieval.retrieve_paper, DOI)
        release.set()
        a, b = first.result(), second.result()
    assert len(calls) == 1 and a.source.raw_content_sha256 == b.source.raw_content_sha256
    assert b.source.cache_hit


@pytest.mark.anyio
@pytest.mark.parametrize('kind', ['doi', 'url'])
@pytest.mark.parametrize('scenario', ['prepared', 'skipped', 'missing', 'corrupt', 'fallback_failed'])
async def test_stage2_to_stage4_real_local_hit_evidence_verification_and_hash(harness, monkeypatch, kind, scenario):
    h = harness()
    monkeypatch.setenv('RESEARCHGUARD_JOBS_ENABLED', '1')
    monkeypatch.setenv('RESEARCHGUARD_SOURCE_CACHE_DIR', str(h.source_store.root))
    monkeypatch.setattr(app.state, 'verification_jobs', h.runtime, raising=False)
    h.runtime.core_dependencies['source_retriever'] = retrieval.retrieve_paper
    parsed, extraction = inputs((('r1',), ('r1',))) if kind == 'doi' else url_inputs((('r1',), ('r1',)))
    content = doi_setup(monkeypatch) if kind == 'doi' else HTML
    seen = transport(monkeypatch, content, 'application/pdf' if kind == 'doi' else 'text/html')
    reference = parsed.references[0]
    await h.runtime.start()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1234)), base_url='http://local') as client:
            assert (await client.post('/api/sources/prepare', json={'reference': reference.model_dump(mode='json')})).json()['state'] == 'not_cached'
            if scenario == 'skipped' or scenario == 'fallback_failed':
                ready = None
            elif kind == 'doi':
                assert (await client.post('/api/papers/retrieve', json={'doi': DOI})).json()['status'] == 'success'
                ready = (await client.post('/api/sources/prepare', json={'reference': reference.model_dump(mode='json')})).json()
            else:
                ready = (await client.post('/api/sources/prepare', json={'reference': reference.model_dump(mode='json'), 'retrieve': True})).json()
            if ready:
                assert ready['state'] == 'available' and len(seen) == 1
            if scenario in {'missing', 'corrupt'}:
                raw = h.source_store.root / ready['raw_content_sha256'] / ('source.' + ready['format'])
                if scenario == 'missing':
                    raw.unlink()
                else:
                    raw.write_bytes(b'corrupt bytes, not the expected source')
            hits = []
            original = source_acquisition.retrieve_reference_source
            def tracked(*a, **k):
                result = original(*a, **k); hits.append(result.source.cache_hit); return result
            monkeypatch.setattr('app.services.manuscript_verification.retrieve_reference_source', tracked)
            def forbidden(*a, **k):
                raise AssertionError('Stage 4 must reuse Stage 2 persisted bytes')
            if scenario == 'prepared':
                monkeypatch.setattr(retrieval, 'resolve_doi', forbidden)
                monkeypatch.setattr(retrieval, 'retrieve_document', forbidden)
                monkeypatch.setattr(source_acquisition, 'retrieve_document', forbidden)
            elif scenario == 'fallback_failed':
                def failed(*a, **k):
                    raise DocumentRetrievalError('Unavailable test source')
                monkeypatch.setattr(retrieval, 'retrieve_document', failed)
                monkeypatch.setattr(source_acquisition, 'retrieve_document', failed)
            created = await client.post('/api/verification/jobs', json={'parsed': parsed.model_dump(mode='json'), 'extraction': extraction.model_dump(mode='json')})
            assert created.status_code == 202
            final = await h.runtime.wait(created.json()['job_id'])
            if scenario == 'fallback_failed':
                assert final.state.value == 'waiting_for_source'
                assert all(task.state.value == 'blocked_source' for task in final.tasks)
                assert not h.queries and not h.verified
                return
            assert final.state.value == 'completed'
            assert hits == [scenario == 'prepared']  # Shared by two independent pairs.
            assert len(h.queries) == len(h.verified) == 2
            assert len(seen) == (2 if scenario in {'missing', 'corrupt'} else 1)
            digest = hashlib.sha256(content).hexdigest()
            for task in final.tasks:
                assert task.source_version == 'sha256:' + digest
                assert task.pair_outcome.verification.verdict is not None
                assert task.pair_outcome.verification.evidence_chunks
    finally:
        await h.runtime.shutdown(0)
