"""Offline HTTP-to-durable-job contracts; real parsing/stores, no paid models."""
import asyncio
from dataclasses import replace
import hashlib
from io import BytesIO
import json
import socket

import httpcore
import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from app.researchguard.domain import Reference, ReferenceResolution, ReferenceCandidate
from app.researchguard.manuscript_verification import SourceBinding
from app.researchguard.source_locator import SourceLocator
from app.services.source_locator import reference_locator
from app.researchguard.adapters.sciverify import accepted_source_to_domain, standalone_claim_to_domain
from app.services.source_acquisition import retrieve_url_source, retrieve_reference_source
from app.services.source_store import LocalSourceStore, verify_source_durability
from app.services.public_http import resolve_public, PublicNetworkBackend, fetch_public, UnsafeSourceURL
from app.services.source_versions import probable_candidate, review_version
from app.services.document_retriever import retrieve_document, DocumentRetrievalError
from app.services.document_parser import parse_document
from app.services.full_text_qualifier import is_full_text_document
from app.services.verification_job_store import LocalJobStore, JobError
from app.services.verification_jobs import VerificationJobRuntime
from app.services.citation_context import fingerprint
from app.tests.test_manuscript_verification import inputs, verifier
from app.tests.test_paperqa2_integration import LocalEmbedding, LocalSummary, config
from app.researchguard.adapters.paperqa2 import PaperQA2EvidenceRetriever
from app.tests.test_source_lifecycle import pdf_bytes, artifact, DOI

TITLE = 'Guidance for emergency treatment risk reduction in adult patients'
URL = 'https://www.fda.gov/media/12345/download'
PROSE = ('This document provides detailed recommendations for evaluation of emergency treatment in adult patients. '
         'The clinical evidence must address relevant risks and benefits, study population and appropriate follow up. '
         'Regulatory assessment includes careful review of safety outcomes and transparent reporting of the results. ')
HTML = ('<html><head><title>' + TITLE + '</title></head><body><main><h1>' + TITLE + '</h1>' + ''.join(
    '<h2>' + heading + '</h2><p>' + PROSE * 3 + '</p>'
    for heading in ['Purpose', 'Background', 'Regulatory Considerations', 'Recommendations']) + '</main></body></html>').encode()


def ref(url=URL, title=TITLE):
    return Reference(id='r1', manuscript_id='m', raw_text=title + ' (2020)', title=title, year=2020, url=url)


def client_for(content=HTML, content_type='text/html', seen=None):
    def handler(request):
        if seen is not None:
            seen.append(str(request.url))
        return httpx.Response(200, headers={'content-type': content_type}, content=content)
    return httpx.Client(transport=httpx.MockTransport(handler))


def url_inputs(links=(('r1',),)):
    parsed, extraction = inputs(links, dois={'r1': None})
    parsed = parsed.model_copy(update={'references': (ref(),)})
    extraction = extraction.model_copy(update={'metadata': extraction.metadata.model_copy(
        update={'input_fingerprint': 'sha256:' + fingerprint(parsed)})})
    return parsed, extraction


def evidence_factory(config):
    return lambda chunks: PaperQA2EvidenceRetriever(chunks, config,
        embedding_model=LocalEmbedding(), summary_model=LocalSummary())


def test_url_html_real_parse_bind_store_cache_and_history(tmp_path):
    seen = []
    store = LocalSourceStore(tmp_path)
    with client_for(seen=seen) as client:
        result = retrieve_url_source(ref(), client=client, store=store)
        again = retrieve_url_source(ref(), client=client, store=store)
    assert result.status == 'success' and result.paper.doi is None and result.chunks
    assert result.source.identity_status == 'confirmed'
    assert again.source.cache_hit and len(seen) == 1
    assert again.source.provenance == result.source.provenance
    assert 'HISTORICAL_VERSION_UNCONFIRMED' in result.source.provenance.warnings
    assert result.source.provenance.retrieved_at and result.source.provenance.final_url == URL
    assert result.source.provenance.retrieved_title == TITLE
    assert result.source.provenance.retrieved_version == 'sha256:' + hashlib.sha256(HTML).hexdigest()
    verify_source_durability(result, store)
    source, chunks = accepted_source_to_domain(result)
    assert source.doi is None and source.content_hash == result.source.provenance.retrieved_version
    assert chunks[0].metadata['source_provenance']['warnings'] == ['HISTORICAL_VERSION_UNCONFIRMED']
    assert store.get_locator(reference_locator(ref())).source_locator.kind == 'url'


def test_url_pdf_real_parse_and_identity(tmp_path):
    text = pdf_bytes(lines=[TITLE, 'October 2020', 'Purpose', PROSE * 15, 'Background', PROSE * 15],
                     metadata={'/Title': TITLE})
    writer = PdfWriter(); writer.clone_document_from_reader(PdfReader(BytesIO(text)))
    writer.add_blank_page(width=612, height=792)
    output = BytesIO(); writer.write(output)
    with client_for(output.getvalue(), 'application/pdf') as client:
        result = retrieve_url_source(ref(), client=client, store=LocalSourceStore(tmp_path))
    assert result.status == 'success' and result.paper.full_text_format == 'pdf' and result.chunks
    assert result.source.provenance.publication_date == 'October 2020'


@pytest.mark.parametrize('body,code', [
    (b'<html><body><main><h1>' + TITLE.encode() + b'</h1><p>Abstract only.</p><a href="/">Download</a></main></body></html>', 'LANDING_PAGE'),
    (b'<html><body><main><h1>' + TITLE.encode() + b'</h1><div class="abstract">' + PROSE.encode() * 30 + b'</div></main></body></html>', 'ABSTRACT_ONLY'),
    (HTML.replace(TITLE.encode(), b'Unrelated childhood nutrition policy'), 'SOURCE_IDENTITY_CONFLICT'),
    (HTML.replace(b'<main>', b'<div>').replace(b'</main>', b'</div>'), 'LANDING_PAGE'),
])
def test_url_rejects_landing_abstract_wrong_identity_and_no_body(tmp_path, body, code):
    with client_for(body) as client:
        result = retrieve_url_source(ref(), client=client, store=LocalSourceStore(tmp_path))
    assert result.status == 'full_text_unavailable' and not result.chunks and result.detail == code
    assert LocalSourceStore(tmp_path).get_locator(reference_locator(ref())) is None


def test_public_body_on_nonofficial_redirect_not_accepted(tmp_path):
    def handler(request):
        if request.url.host == 'www.fda.gov':
            return httpx.Response(302, headers={'location': 'https://unrelated.example/document'})
        return httpx.Response(200, headers={'content-type': 'text/html'}, content=HTML)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = retrieve_url_source(ref(), client=client, store=LocalSourceStore(tmp_path))
    assert result.status != 'success' and not result.chunks


def test_url_content_change_creates_new_version_preserves_old_bytes(tmp_path):
    store = LocalSourceStore(tmp_path)
    with client_for() as client:
        first = retrieve_url_source(ref(), client=client, store=store)
    changed = HTML.replace(b'adult patients', b'adult patients and older adults')
    with client_for(changed) as client:
        second = retrieve_url_source(ref(), client=client, store=store, refresh=True)
    assert first.source.locator == second.source.locator
    assert first.source.raw_content_sha256 != second.source.raw_content_sha256
    assert (tmp_path / first.source.raw_content_sha256 / 'source.html').read_bytes() == HTML
    assert store.get_locator(first.source.locator).raw_content_sha256 == second.source.raw_content_sha256
    with pytest.raises(ValueError, match='SOURCE_DURABILITY_MISMATCH'):
        verify_source_durability(first, store)


def test_url_cache_cannot_bypass_reference_identity_review(tmp_path):
    store = LocalSourceStore(tmp_path)
    with client_for() as client:
        first = retrieve_url_source(ref(), client=client, store=store)
        wrong = retrieve_url_source(ref(title='Unrelated childhood nutrition policy'), client=client, store=store)
    assert first.status == 'success' and wrong.status != 'success' and not wrong.chunks
    assert wrong.source.provenance.identity == 'IDENTITY_CONFLICT'


def test_url_doi_index_isolation_and_legacy_store(tmp_path):
    store = LocalSourceStore(tmp_path); old = artifact(); store.put(old)
    before = store._lookup_path(DOI).read_bytes()
    with client_for() as client:
        result = retrieve_url_source(ref(), client=client, store=store)
    assert store.get(DOI) == old and store._lookup_path(DOI).read_bytes() == before
    assert store.get_locator(result.source.locator).doi is None
    assert (tmp_path / 'doi').is_dir() and (tmp_path / 'url').is_dir()


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'http://127.0.0.1/a', 'http://169.254.169.254/latest/meta-data',
    'http://[::1]/a', 'http://localhost/a', 'http://user:pass@example.com/a', 'https://example.com:8000/a'])
def test_locator_rejects_unsafe_urls_before_contact(url):
    with pytest.raises(ValueError):
        SourceLocator(kind='url', value=url)


@pytest.mark.parametrize('addresses', [['127.0.0.1'], ['169.254.169.254'], ['10.0.0.1'],
    ['93.184.216.34', '192.168.1.1'], ['::ffff:127.0.0.1']])
def test_dns_answers_must_all_be_public(monkeypatch, addresses):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', (ip, 443)) for ip in addresses])
    with pytest.raises(UnsafeSourceURL, match='SOURCE_ADDRESS_BLOCKED'):
        resolve_public('rebind.example', 443)


def test_dns_pins_numeric_connect_without_resolving_host_again(monkeypatch):
    import app.services.public_http as network
    seen = []
    monkeypatch.setattr(network, 'resolve_public', lambda *args: ['93.184.216.34'])
    sentinel = object()
    def connect(self, host, *args):
        seen.append(host); return sentinel
    monkeypatch.setattr(httpcore.SyncBackend, 'connect_tcp', connect)
    assert PublicNetworkBackend().connect_tcp('rebind.example', 443, timeout=5) is sentinel
    assert seen == ['93.184.216.34']


def test_redirect_to_private_address_never_contacted():
    seen = []
    def handler(request):
        seen.append(str(request.url)); return httpx.Response(302, headers={'location': 'http://169.254.169.254/latest'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            fetch_public(client, URL, headers={}, max_bytes=1024)
    assert seen == [URL]


def test_redirect_limit_and_streamed_size_limit():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={'location': '/next'}))) as client:
        with pytest.raises(UnsafeSourceURL, match='SOURCE_REDIRECT_LIMIT'):
            fetch_public(client, URL, headers={}, max_bytes=1024, max_redirects=2)
    class Body(httpx.SyncByteStream):
        def __iter__(self):
            yield b'x' * 8; yield b'y' * 8
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=Body()))) as client:
        with pytest.raises(UnsafeSourceURL, match='SOURCE_RESPONSE_TOO_LARGE'):
            fetch_public(client, URL, headers={}, max_bytes=10)


@pytest.mark.parametrize('kind,body', [('application/pdf', HTML), ('text/html', b'%PDF not html'), ('application/json', b'{}')])
def test_url_mime_and_bytes_must_agree(kind, body):
    with client_for(body, kind) as client:
        with pytest.raises(DocumentRetrievalError):
            retrieve_document(URL, client=client, public_only=True)


def test_old_binding_serializes_identically():
    old = {'reference_id': 'r1', 'doi': '10.1234/local', 'source_document_id': None, 'source_version': None}
    assert SourceBinding.model_validate(old).model_dump(mode='json') == old
    with pytest.raises(ValueError):
        SourceBinding(reference_id='r1', doi='10.1234/local', locator=SourceLocator(kind='url', value=URL))


def test_preprint_pdf_adjacent_doi_label_is_not_a_different_identifier():
    from app.services.source_identity import qualify_source_identity
    from app.schemas.paper import PaperMetadata
    doi = '10.1101/2020.12.09.20245175'
    content = pdf_bytes(lines=[TITLE, doi + 'doi:', 'Abstract', PROSE], metadata={'/Title': TITLE})
    paper = PaperMetadata(paper_id=doi, doi=doi, title=TITLE)
    # A second page makes this a manuscript, rather than a single-page abstract.
    writer = PdfWriter(); writer.clone_document_from_reader(PdfReader(BytesIO(content)))
    writer.add_blank_page(width=612, height=792); out = BytesIO(); writer.write(out)
    assert qualify_source_identity(out.getvalue(), 'pdf', paper).status == 'confirmed'
    paper.doi = '10.1101/2020.12.09.99999999'
    assert qualify_source_identity(out.getvalue(), 'pdf', paper).status == 'conflict'


def test_retrieved_preprint_date_is_not_merged_journal_publication_date():
    from app.schemas.citation import CitationMetadata
    from app.services.paper_retriever import _build_paper_metadata
    from app.services.source_versions import document_version_date
    cited = CitationMetadata(doi='10.1101/2020.12.09.20245175', title=TITLE, source='crossref', year=2020)
    merged = {'doi': 'https://doi.org/10.1234/journal', 'publication_date': '2021-05-27'}
    assert _build_paper_metadata(cited, merged).publication_date is None
    pdf = pdf_bytes(lines=[TITLE, 'this version posted December 11, 2020.', PROSE])
    assert document_version_date(pdf, 'pdf') == '2020-12-11'


def test_actual_prior_snapshot_roundtrip_contract_when_fixture_available():
    # Static repository fixtures are authoritative in CI; no developer live data is read.
    from app.services.verification_job_models import JobSnapshot
    from app.services.verification_jobs import timestamp
    from app.services.verification_job_models import EventRecord, TaskRecord, task_key
    parsed, extraction = inputs(); jid = 'job_' + 'a' * 32; now = timestamp()
    data = JobSnapshot(job_id=jid, input_fingerprint=extraction.metadata.input_fingerprint,
        parsed=parsed, extraction=extraction, tasks=(TaskRecord(task_key=task_key(jid, extraction.metadata.input_fingerprint, 'claim0', 'r1'), claim_id='claim0', reference_id='r1'),),
        attribution_blocked=(), events=(EventRecord(job_id=jid, sequence=1, event_type='job_created', status='pending', timestamp=now),),
        next_sequence=2, created_at=now, updated_at=now).model_dump(mode='json')
    assert JobSnapshot.model_validate(data).model_dump(mode='json') == data
    assert data['input_fingerprint'] == 'sha256:' + fingerprint(parsed)


def version_ref(title=None):
    original = 'BNT162b2 elicits SARS-CoV-2 neutralising antibodies and TH1 T cells in humans'
    candidate = ReferenceCandidate(doi='10.1101/2020.12.09.20245175',
        title=title or 'BNT162b2 induces SARS-CoV-2-neutralising antibodies and T cells in humans',
        authors=('Ugur Sahin', 'Alexander Muik', 'Isabel Vogler'), years=(2020,),
        publication_type='preprint', provider='crossref', rejection_reason='TITLE_MISMATCH', match_confidence=.88)
    return Reference(id='r1', manuscript_id='m', raw_text=original + '. preprint.', title=original,
        authors=('Ugur Sahin', 'Alexander Muik', 'Evelyna Derhovanessian'),
        resolution=ReferenceResolution(reference_id='r1', status='ambiguous', match_reason='VERSION_UNCERTAIN', candidates=(candidate,)))


def test_retitled_preprint_metadata_is_acquisition_permission_not_exact_identity():
    r = version_ref(); c = probable_candidate(r)
    assert c and reference_locator(r).value == c.doi and r.doi is None
    assert r.resolution.status == 'ambiguous'


@pytest.mark.parametrize('title', ['BNT162b1 induces SARS-CoV-2-neutralising antibodies and T cells in humans',
    'BNT162b2 induces SARS-CoV-2-neutralising antibodies and T cells in mice'])
def test_wrong_vaccine_or_population_cannot_become_probable(title):
    assert probable_candidate(version_ref(title)) is None


def test_preprint_requires_confirmed_full_text_and_preserves_uncertainty():
    from app.schemas.paper import PaperMetadata, PaperSource, RetrievePaperResponse, DocumentSection
    r = version_ref(); c = probable_candidate(r)
    body = 'Healthy adult participants in this clinical trial showed neutralising antibodies and T cells responses in humans after BNT162b2 SARS CoV 2 vaccination. ' * 40
    response = RetrievePaperResponse(status='success', paper=PaperMetadata(paper_id=c.doi, doi=c.doi,
        title=c.title, authors=list(c.authors), year=2020, publication_date='2020-12-11'),
        sections=[DocumentSection(section_name='Results', text=body, order=0)],
        source=PaperSource(provider='fixture', identity_status='confirmed'))
    review = review_version(r, response)
    assert review['identity'] == 'PROBABLE_SAME_WORK'
    assert 'VERSION_RELATIONSHIP_UNCONFIRMED' in review['warnings']
    response.source.identity_status = 'uncertain'
    assert review_version(r, response) is None
    response.source.identity_status = 'confirmed'; response.sections = []
    assert review_version(r, response) is None


@pytest.mark.anyio
async def test_url_identity_conflict_is_distinct_from_missing_full_text(tmp_path, config, monkeypatch):
    import app.services.source_acquisition as acquisition
    actual = acquisition.retrieve_document
    wrong = HTML.replace(TITLE.encode(), b'Unrelated childhood nutrition policy')
    with client_for(wrong) as client:
        monkeypatch.setattr(acquisition, 'retrieve_document', lambda *a, **k: actual(*a, **{**k, 'client': client}))
        runtime = VerificationJobRuntime(LocalJobStore(tmp_path/'jobs'), core_dependencies={
            'evidence_retriever_factory': evidence_factory(config), 'prepared_verifier': verifier})
        created = await runtime.create(*url_inputs()); saved = await runtime.wait(created.job_id)
    task = saved.tasks[0]
    assert task.reason_code == 'SOURCE_IDENTITY_CONFLICT' and task.state == 'blocked_source'
    assert task.pair_outcome.verification.verdict is None
    assert task.source_binding.provenance.identity == 'IDENTITY_CONFLICT'
    await runtime.shutdown(0)


@pytest.mark.anyio
async def test_url_http_to_real_paperqa_contract_durable_job_and_completed_immutability(tmp_path, config):
    import app.services.source_acquisition as acquisition
    from unittest.mock import patch
    with client_for() as client:
        actual = acquisition.retrieve_document
        def download(*args, **kwargs):
            return actual(*args, **{**kwargs, 'client': client})
        with patch.object(acquisition, 'retrieve_document', download):
            runtime = VerificationJobRuntime(LocalJobStore(tmp_path/'jobs'),
                core_dependencies={'evidence_retriever_factory': evidence_factory(config), 'prepared_verifier': verifier})
            first = await runtime.create(*url_inputs((('r1',), ('r1',))))
            saved = await runtime.wait(first.job_id)
    assert saved.state == 'completed' and all(t.state == 'completed' for t in saved.tasks)
    assert saved.tasks[0].source_binding.doi is None
    assert saved.tasks[0].source_binding.locator.kind == 'url'
    assert all(t.expected_raw_hash and t.source_version == 'sha256:' + t.expected_raw_hash for t in saved.tasks)
    assert saved.tasks[0].pair_outcome.verification.evidence_chunks[0].metadata['paperqa_version']
    unchanged = await runtime.resume(saved.job_id, expected_revision=saved.revision)
    assert unchanged == saved
    assert [e.sequence for e in saved.events] == list(range(1, saved.next_sequence))
    assert runtime.store.load(saved.job_id).input_fingerprint == first.input_fingerprint
    await runtime.shutdown(0)


@pytest.mark.anyio
async def test_url_job_blocked_then_explicit_hash_resume_and_version_conflict(tmp_path, config):
    from unittest.mock import patch
    import app.services.source_acquisition as acquisition
    actual = acquisition.retrieve_document
    with client_for(b'<html><body><main><h1>Landing</h1></main></body></html>') as client:
        with patch.object(acquisition, 'retrieve_document', lambda *a, **k: actual(*a, **{**k, 'client': client})):
            runtime = VerificationJobRuntime(LocalJobStore(tmp_path/'jobs'), core_dependencies={
                'evidence_retriever_factory': evidence_factory(config), 'prepared_verifier': verifier})
            created = await runtime.create(*url_inputs()); blocked = await runtime.wait(created.job_id)
    assert blocked.state == 'waiting_for_source' and blocked.tasks[0].pair_outcome.verification.verdict is None
    with client_for() as client:
        result = retrieve_url_source(ref(), client=client)
    digest = result.source.raw_content_sha256
    with pytest.raises(JobError, match='JOB_SOURCE_VERSION_CONFLICT'):
        await runtime.resume(created.job_id, expected_revision=blocked.revision, source_hashes={'r1': '0'*64})
    resumed = await runtime.resume(created.job_id, expected_revision=blocked.revision, source_hashes={'r1': digest})
    done = await runtime.wait(resumed.job_id)
    assert done.state == 'completed' and done.tasks[0].attempt == 2
    assert done.tasks[0].task_key == blocked.tasks[0].task_key
    assert done.tasks[0].expected_raw_hash == digest
    await runtime.shutdown(0)


@pytest.mark.anyio
async def test_asgi_url_acquire_contract_does_not_execute_or_mutate_job_until_resume(tmp_path, config, monkeypatch):
    from app.main import app
    import app.services.source_acquisition as acquisition
    actual = acquisition.retrieve_document
    ready = [False]
    def handler(request):
        content = HTML if ready[0] else b'<html><body><main><h1>Document links</h1></main></body></html>'
        return httpx.Response(200, headers={'content-type': 'text/html'}, content=content)
    calls = []
    async def counted(claim, response):
        calls.append(claim)
        return await verifier(claim, response)
    with httpx.Client(transport=httpx.MockTransport(handler)) as documents:
        monkeypatch.setattr(acquisition, 'retrieve_document', lambda *a, **k: actual(*a, **{**k, 'client': documents}))
        runtime = VerificationJobRuntime(LocalJobStore(tmp_path/'jobs'), core_dependencies={
            'evidence_retriever_factory': evidence_factory(config), 'prepared_verifier': counted})
        monkeypatch.setenv('RESEARCHGUARD_JOBS_ENABLED', '1')
        monkeypatch.setattr(app.state, 'verification_jobs', runtime, raising=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 12345)), base_url='http://testserver') as api:
            parsed, extraction = url_inputs()
            created = await api.post('/api/verification/jobs', json={'parsed': parsed.model_dump(mode='json'), 'extraction': extraction.model_dump(mode='json')})
            assert created.status_code == 202
            jid = created.json()['job_id']; path = '/api/verification/jobs/' + jid
            blocked = await runtime.wait(jid)
            assert blocked.state == 'waiting_for_source' and not calls
            ready[0] = True
            conflict = await api.post(path+'/source', json={'reference_id': 'r1', 'expected_revision': 0})
            assert conflict.status_code == 409
            acquired = await api.post(path+'/source', json={'reference_id': 'r1', 'expected_revision': blocked.revision})
            assert acquired.status_code == 200 and acquired.json()['status'] == 'accepted'
            assert acquired.json()['source']['locator']['kind'] == 'url'
            digest = acquired.json()['raw_content_sha256']
            assert runtime.get(jid) == blocked and not calls
            resumed = await api.post(path+'/resume', json={'expected_revision': blocked.revision, 'reference_ids': ['r1'], 'source_hashes': {'r1': digest}})
            assert resumed.status_code == 202
            done = await runtime.wait(jid)
            assert done.state == 'completed' and len(calls) == 1
            snapshot = (await api.get(path)).json()
            assert snapshot['tasks'][0]['source_binding']['doi'] is None
            assert snapshot['tasks'][0]['source_binding']['provenance']['identity'] == 'EXACT_IDENTITY'
            assert snapshot['tasks'][0]['expected_raw_hash'] == digest
            events = (await api.get(path+'/events')).json()
            assert [e['sequence'] for e in events['events']] == list(range(1, events['next_sequence']))
            again = await api.post(path+'/resume', json={'expected_revision': done.revision})
            assert again.status_code == 202 and len(calls) == 1
    await runtime.shutdown(0)
