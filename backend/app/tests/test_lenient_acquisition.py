"""Offline Mock HTTP through the actual Stage 2 API and Source Store."""
import hashlib
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.researchguard.domain import Reference, ReferenceCandidate, ReferenceResolution
from app.services import paper_retriever as retrieval
from app.services.source_locator import reference_candidates
from app.services.reference_resolver import resolve_reference
from app.services.source_identity import qualify_source_identity
from app.schemas.paper import PaperMetadata
from app.services.source_store import LocalSourceStore
from app.tests.test_source_preparation import doi_setup, transport, check, DOI
from app.tests.test_source_lifecycle import pdf_bytes, TITLE


def candidate(doi=DOI, **updates):
    return ReferenceCandidate(doi=doi, title=TITLE, provider='openalex', authors=('Ada Lovelace',),
        years=(2021,), match_confidence=.8, rejection_reason='YEAR_CONFLICT', **updates)


def reference(status='ambiguous', candidates=None):
    return Reference(id='r1', manuscript_id='m', raw_text='Ada Lovelace. ' + TITLE + '. 2020.',
        title=TITLE, authors=('Ada Lovelace',), year=2020,
        resolution=ReferenceResolution(reference_id='r1', status=status, match_reason='VERSION_UNCERTAIN',
            diagnostics=('CROSSREF_RATE_LIMIT',), candidates=tuple(candidates or (candidate(),))))


@pytest.mark.parametrize('status', ['ambiguous', 'provider_error', 'not_found'])
def test_metadata_diagnostics_do_not_block_real_download(monkeypatch, status):
    content = doi_setup(monkeypatch)
    seen = transport(monkeypatch, content, 'application/pdf')
    ref = reference(status)
    result = check(TestClient(app), ref, retrieve=True)
    assert result['state'] == 'available' and seen
    assert result['raw_content_sha256'] == hashlib.sha256(content).hexdigest()
    assert any(r['attempted'] for r in result['candidates'])
    assert 'CROSSREF_RATE_LIMIT' in result['source']['provenance']['warnings']
    again = check(TestClient(app), ref)
    assert again['state'] == 'available' and again['source']['cache_hit']
    assert len(seen) == 1


@pytest.mark.parametrize('first', ['failed', 'wrong_paper'])
def test_first_candidate_failure_or_wrong_identity_continues(monkeypatch, first):
    from app.schemas.citation import CitationMetadata
    content = doi_setup(monkeypatch)
    monkeypatch.setattr(retrieval, 'resolve_doi', lambda doi, **kw: CitationMetadata(doi=doi,
        title=TITLE, authors=['Ada Lovelace'], year=2020, source='crossref'))
    monkeypatch.setattr(retrieval, '_discover_europe_pmc_candidates', lambda doi, *a: [
        retrieval.FullTextCandidate('https://example.org/' + doi.split('/')[-1] + '.pdf', 'pdf', 'fixture')])
    seen = []
    def handler(request):
        seen.append(str(request.url))
        if request.url.path == '/first.pdf':
            if first == 'failed':
                return httpx.Response(403)
            wrong = pdf_bytes(['Optical absorption in amorphous carbon thin films', 'doi: 10.9999/wrong',
                'Results', 'Unrelated physical measurements.'], metadata={'/Title': 'Optical absorption in amorphous carbon thin films'})
            return httpx.Response(200, content=wrong, headers={'content-type': 'application/pdf'})
        return httpx.Response(200, content=content, headers={'content-type': 'application/pdf'})
    monkeypatch.setattr('app.services.public_http.source_client', lambda *a, **k: httpx.Client(transport=httpx.MockTransport(handler)))
    ref = reference(candidates=(candidate('10.1234/first'), candidate()))
    result = check(TestClient(app), ref, retrieve=True)
    assert result['state'] == 'available'
    assert result['source']['locator']['value'] == DOI
    assert len(seen) == 2
    assert result['candidates'][0]['state'] in {'unavailable', 'conflict'}
    assert result['candidates'][0]['downloads'][0]['reason']
    assert result['candidates'][1]['full_text_obtained']
    assert LocalSourceStore().get('10.1234/first') is None


def test_uncertain_fulltext_remains_durable_and_visible(monkeypatch):
    doi_setup(monkeypatch)
    # Missing document title/DOI provides no positive or negative identity proof.
    content = pdf_bytes(['Research report', 'Results', 'Treatment reduces risk by 12% in patients.'])
    seen = transport(monkeypatch, content, 'application/pdf')
    result = check(TestClient(app), reference(), retrieve=True)
    assert result['state'] == 'available' and result['identity'] == 'POSSIBLE'
    assert result['source']['identity_status'] == 'uncertain'
    assert result['source']['provenance']['identity'] == 'IDENTITY_UNCERTAIN'
    assert result['raw_content_sha256'] == hashlib.sha256(content).hexdigest()
    assert LocalSourceStore().get(DOI).content == content
    assert seen


def test_all_failures_keep_candidates_urls_and_actual_reasons(monkeypatch):
    doi_setup(monkeypatch)
    seen = []
    def denied(request):
        seen.append(str(request.url))
        return httpx.Response(429)
    monkeypatch.setattr('app.services.public_http.source_client', lambda *a, **k: httpx.Client(transport=httpx.MockTransport(denied)))
    full_url = 'https://example.org/paper.pdf?version=conference&download=true&identifier=complete'
    ref = reference(candidates=(candidate(urls=(full_url,)), candidate('10.1234/second')))
    result = check(TestClient(app), ref, retrieve=True)
    assert result['state'] == 'unavailable' and result['raw_content_sha256'] is None
    assert len(result['candidates']) >= 2
    assert any(r['url'] == full_url or full_url in r['urls'] for r in result['candidates'])
    assert full_url in seen
    assert any('429' in str(r.get('downloads')) for r in result['candidates'])
    assert all(not r['full_text_obtained'] and r['raw_content_sha256'] is None for r in result['candidates'])


@pytest.mark.anyio
async def test_raw_citation_title_hint_is_searched_without_overwriting_original():
    from app.tests.test_reference_resolver import work, TITLE as SEARCH_TITLE
    ref = Reference(id='r1', manuscript_id='m', raw_text='A Smith. ' + SEARCH_TITLE + '. 2020.',
        authors=('A Smith', 'B Jones'), year=2020, journal='Example Journal')
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={'message': {'items': [work()]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await resolve_reference(ref, client=client)
    assert result.candidates and result.status == 'resolved'
    assert 'TITLE_RECOVERED_SEARCH_HINT' in result.diagnostics and seen
    assert ref.title is None


def test_explicit_arxiv_id_and_complete_url_survive_ambiguity():
    raw = 'A. Author. Title. arXiv:1406.1078v2. (https://example.org/full/path?x=1&y=complete)'
    ref = reference().model_copy(update={'raw_text': raw})
    records = reference_candidates(ref)
    assert any(r['doi'] == '10.48550/arxiv.1406.1078' for r in records)
    assert any(r['url'] == 'https://example.org/full/path?x=1&y=complete' for r in records)
    assert any('https://arxiv.org/pdf/1406.1078v2' in r['urls'] for r in records)


def test_unexplained_authoritative_doi_conflict_still_rejected():
    data = pdf_bytes([TITLE, 'doi: 10.9999/different', 'Results'], metadata={'/Title': TITLE})
    assert qualify_source_identity(data, 'pdf', PaperMetadata(paper_id=DOI, doi=DOI, title=TITLE)).status == 'conflict'


def test_arxiv_formal_version_doi_difference_keeps_warning_not_confirmation():
    data = pdf_bytes([TITLE, 'doi: 10.9999/formal', 'Results'], metadata={'/Title': TITLE})
    identity = qualify_source_identity(data, 'pdf', PaperMetadata(paper_id='x', doi='10.48550/arxiv.1406.1078', title=TITLE))
    assert identity.status == 'uncertain' and identity.reason == 'RELATED_VERSION_DOI_UNCONFIRMED'


from app.tests.test_verification_jobs import harness  # noqa: F401
from app.tests.test_manuscript_verification import inputs, paper  # noqa: F401


@pytest.mark.anyio
async def test_candidate_fallback_stage2_to_stage4_reuses_exact_bytes_and_binding(harness, monkeypatch):
    from app.services.citation_context import fingerprint
    h = harness()
    monkeypatch.setenv('RESEARCHGUARD_SOURCE_CACHE_DIR', str(h.source_store.root))
    h.runtime.core_dependencies['source_retriever'] = retrieval.retrieve_paper
    content = doi_setup(monkeypatch)
    seen = transport(monkeypatch, content, 'application/pdf')
    ref = reference(candidates=(candidate('10.1234/notavailable'), candidate()))
    from app.services.citation_resolver import CitationNotFoundError
    original = retrieval.resolve_doi
    def resolve(doi, **kwargs):
        if doi.endswith('/notavailable'):
            raise CitationNotFoundError('Missing metadata, still attempt discovery')
        return original(doi, **kwargs)
    monkeypatch.setattr(retrieval, 'resolve_doi', resolve)
    # Reject the first candidate's actual authoritative DOI; continue to the next.
    ready = check(TestClient(app), ref, retrieve=True)
    assert ready['state'] == 'available' and ready['source']['locator']['value'] == DOI
    network_calls = len(seen)
    assert network_calls == 2
    parsed, extracted = inputs((('r1',), ('r1',)), dois={'r1': None})
    parsed = parsed.model_copy(update={'references': (ref,)})
    extracted = extracted.model_copy(update={'metadata': extracted.metadata.model_copy(update={
        'input_fingerprint': 'sha256:' + fingerprint(parsed)})})
    def forbidden(*args, **kwargs):
        pytest.fail('Prepared candidates must not redownload or resolve metadata')
    monkeypatch.setattr(retrieval, 'resolve_doi', forbidden)
    monkeypatch.setattr(retrieval, 'retrieve_document', forbidden)
    await h.runtime.start()
    try:
        job = await h.runtime.create(parsed, extracted)
        final = await h.runtime.wait(job.job_id)
        assert final.state.value == 'completed'
        assert len(h.queries) == len(h.verified) == 2
        assert len(seen) == network_calls
        for task in final.tasks:
            assert task.source_binding.locator.value == DOI
            assert task.source_version == 'sha256:' + ready['raw_content_sha256']
        assert h.store.load(job.job_id) == final
        again = await h.runtime.resume(job.job_id, expected_revision=final.revision)
        assert again == final and len(h.verified) == 2
    finally:
        await h.runtime.shutdown(0)


@pytest.mark.parametrize('url', ['https://arxiv.org/pdf/1406.1078', 'https://arxiv.org/pdf/1406.1078v2', 'https://example.org/paper.pdf?version=conference&download=true'])
def test_explicit_pdf_format_does_not_require_url_suffix(url):
    assert retrieval._format_from_url(url) == 'pdf'



def test_document_verified_doi_with_unrelated_canonical_title_is_rejected(monkeypatch):
    from app.schemas.citation import CitationMetadata
    doi_setup(monkeypatch)
    monkeypatch.setattr(retrieval, 'resolve_doi', lambda *a, **k: CitationMetadata(doi=DOI,
        title='Optical absorption in amorphous carbon thin films', authors=['Other Author'], year=2020, source='crossref'))
    content = pdf_bytes(['Research report', 'doi: ' + DOI, 'Results', 'Measurements of optical films.'])
    transport(monkeypatch, content, 'application/pdf')
    result = check(TestClient(app), reference(), retrieve=True)
    assert result['state'] != 'available' and result['raw_content_sha256'] is None
    assert any(c['identity_status'] == 'conflict' for c in result['candidates'] if c.get('identity_status'))


def test_author_difference_is_warning_when_document_directly_confirms_title(monkeypatch):
    from app.schemas.citation import CitationMetadata
    content = doi_setup(monkeypatch)
    monkeypatch.setattr(retrieval, 'resolve_doi', lambda *a, **k: CitationMetadata(doi=DOI,
        title=TITLE, authors=['Different Person'], year=2020, source='crossref'))
    transport(monkeypatch, content, 'application/pdf')
    result = check(TestClient(app), reference(), retrieve=True)
    assert result['state'] == 'available' and result['identity'] == 'CONFIRMED'
    assert 'RETRIEVED_AUTHORS_UNCONFIRMED' in result['source']['provenance']['warnings']



def test_generic_short_title_cannot_bind_to_later_different_work_in_url_cache(monkeypatch):
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter
    from app.researchguard.source_locator import SourceLocator
    from app.services.source_store import AcceptedSourceArtifact
    title = 'Long Short-Term Memory-Networks for Machine Reading'
    url = 'https://arxiv.org/pdf/1601.06733'
    data = pdf_bytes([title, 'Jianpeng Cheng Li Dong Mirella Lapata', 'Introduction',
        ('Machine reading methods describe experimental results and detailed analysis. ' * 70)], metadata={'/Title': title})
    writer = PdfWriter(); writer.clone_document_from_reader(PdfReader(BytesIO(data)))
    writer.add_blank_page(width=612, height=792)
    stream = BytesIO(); writer.write(stream); data = stream.getvalue()
    locator = SourceLocator(kind='url', value=url)
    LocalSourceStore().put(AcceptedSourceArtifact.create(locator=locator, content=data, format='pdf',
        source_url=url, provider='fixture', origin='remote', paper=PaperMetadata(paper_id=locator.key,
            title=title, authors=['Jianpeng Cheng', 'Li Dong', 'Mirella Lapata'], year=2016, full_text_available=True, full_text_format='pdf')))
    ref = Reference(id='r1', manuscript_id='m', raw_text='Hochreiter and Schmidhuber. Long short-term memory. 1997.',
        title='Long short-term memory', authors=('Sepp Hochreiter', 'Jürgen Schmidhuber'), year=1997,
        resolution=ReferenceResolution(reference_id='r1', status='ambiguous', match_reason='MULTIPLE_IDENTITIES',
            candidates=(ReferenceCandidate(doi=None, title=title, authors=('Jianpeng Cheng', 'Li Dong', 'Mirella Lapata'),
                years=(2016,), urls=(url,), provider='openalex'),)))
    result = check(TestClient(app), ref)
    assert result['state'] != 'available' and result['raw_content_sha256'] is None
    assert result['candidates'][0]['state'] == 'conflict'
    # The valid R4 artifact remains in the store, but is not associated with R12.
    assert LocalSourceStore().get_locator(locator).content == data



def test_identical_source_bytes_preserve_existing_artifact_file(monkeypatch):
    content = doi_setup(monkeypatch)
    transport(monkeypatch, content, 'application/pdf')
    result = check(TestClient(app), reference(), retrieve=True)
    store = LocalSourceStore()
    artifact = store.get(DOI)
    raw = store.root / artifact.raw_content_sha256 / 'source.pdf'
    original_time = raw.stat().st_mtime_ns
    store.put(artifact)
    assert raw.read_bytes() == content and raw.stat().st_mtime_ns == original_time
    assert result['raw_content_sha256'] == artifact.raw_content_sha256



def test_provider_discovered_url_is_not_falsely_labelled_explicit_citation(monkeypatch):
    from app.tests.test_unified_source import HTML, TITLE as WEB_TITLE
    url = 'https://www.fda.gov/media/12345/download'
    transport(monkeypatch, HTML)
    ref = Reference(id='r1', manuscript_id='m', raw_text=WEB_TITLE + '. 2020.', title=WEB_TITLE, year=2020,
        resolution=ReferenceResolution(reference_id='r1', status='ambiguous', match_reason='VERSION_UNCERTAIN',
            candidates=(ReferenceCandidate(title=WEB_TITLE, urls=(url,), years=(2021,), provider='openalex'),)))
    result = check(TestClient(app), ref, retrieve=True)
    assert result['state'] == 'available'
    prov = result['source']['provenance']
    assert 'PROVIDER_DISCOVERED_URL' in prov['match_evidence'] and 'EXPLICIT_CITED_URL' not in prov['match_evidence']
    assert 'VERSION_DATE_DIFFERS' in prov['warnings']
