"""Work identity confirmation from real title pages; no provider/model calls."""
import hashlib
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from app.main import app
from app.researchguard.domain import Reference, ReferenceResolution, ReferenceCandidate
from app.services.source_confirmation import inspect_confirmation
from app.services.source_store import AcceptedSourceArtifact, LocalSourceStore
from app.researchguard.source_locator import SourceLocator
from app.schemas.paper import PaperMetadata
from app.schemas.citation import CitationMetadata
from app.tests.test_source_lifecycle import pdf_bytes, TITLE
from app.tests.test_source_preparation import doi_setup, transport, check, DOI
from app.tests.test_lenient_acquisition import reference, candidate


def test_typesetting_spaces_and_missing_authors_confirm_actual_title():
    title = 'A Structured Self-Attentive Sentence Embedding'
    ref = Reference(id='r', manuscript_id='m', raw_text=title, title=title)
    content = pdf_bytes(['A S TRUCTURED SELF -ATTENTIVE', 'SENTENCE EMBEDDING', 'Abstract', 'Body text'])
    proof = inspect_confirmation(content, 'pdf', ref)
    assert proof['status'] == 'confirmed' and proof['reason'] == 'DOCUMENT_TITLE_DIRECT_MATCH'


def test_short_citation_title_requires_document_author_corroboration():
    ref = Reference(id='r', manuscript_id='m', raw_text='A decomposable attention model',
        title='A decomposable attention model', authors=('Ankur Parikh', 'Oscar Tackstrom'))
    content = pdf_bytes(['A Decomposable Attention Model for Natural Language Inference',
        'Ankur Parikh Oscar Tackstrom', 'Abstract', 'Body text'])
    proof = inspect_confirmation(content, 'pdf', ref)
    assert proof['status'] == 'confirmed' and proof['reason'] == 'DOCUMENT_TITLE_AND_AUTHORS_MATCH'


def test_search_keywords_and_body_title_mentions_stay_possible():
    ref = Reference(id='r', manuscript_id='m', raw_text=TITLE, title=TITLE)
    content = pdf_bytes(['Research report', 'Abstract', TITLE, 'Results', 'Risk treatment patient analysis'])
    assert inspect_confirmation(content, 'pdf', ref)['status'] == 'uncertain'


def test_explicit_arxiv_confirms_without_a_recognized_title():
    ref = Reference(id='r', manuscript_id='m', raw_text='Author. arXiv:1703.03130.', title=None)
    content = pdf_bytes(['A technical manuscript', 'Abstract', 'Full text'])
    proof = inspect_confirmation(content, 'pdf', ref, 'https://arxiv.org/pdf/1703.03130')
    assert proof['status'] == 'confirmed' and proof['reason'] == 'EXPLICIT_CITED_ARXIV_MATCH'


def test_printed_arxiv_conflict_cannot_be_overridden_by_title():
    ref = Reference(id='r', manuscript_id='m', raw_text=TITLE + '. arXiv:1703.03130.', title=TITLE)
    content = pdf_bytes(['arXiv:1703.99999', TITLE, 'Abstract', 'Full text'])
    assert inspect_confirmation(content, 'pdf', ref, 'https://arxiv.org/pdf/1703.03130')['status'] == 'conflict'


def test_empty_metadata_foreign_thesis_cover_is_rejected_and_bytes_preserved():
    from unittest.mock import patch
    ref = Reference(id='r', manuscript_id='m', raw_text='Kaiming He. Deep residual learning for image recognition. 2016.',
        title='Deep residual learning for image recognition', authors=('Kaiming He',), year=2016)
    cover = '''Propuesta metodologica para procesamiento de senales y videos

Diego Hernando Orozco Gomez

Universidad Nacional de Colombia
2022
'''
    # Exercise the cover parser separately from PDF font/layout generation.
    reader = type('Reader', (), {'pages': [type('Page', (), {'extract_text': lambda self: cover})()], 'metadata': {}})()
    with patch('app.services.source_confirmation.PdfReader', return_value=reader):
        proof = inspect_confirmation(b'unchanged bytes', 'pdf', ref)
    assert proof['status'] == 'conflict' and proof['reason'] == 'DOCUMENT_COVER_TITLE_CONFLICT'


def test_year_and_missing_authors_are_warnings_not_downgrades(monkeypatch):
    content = doi_setup(monkeypatch)
    transport(monkeypatch, content, 'application/pdf')
    ref = reference().model_copy(update={'authors': (), 'year': 2019})
    result = check(TestClient(app), ref, retrieve=True)
    assert result['identity'] == 'CONFIRMED' and result['full_text_obtained']
    assert {'AUTHORS_UNCONFIRMED', 'VERSION_DATE_DIFFERS'} <= set(result['source']['provenance']['warnings'])


def test_unrecognized_host_with_actual_title_can_confirm(monkeypatch):
    from app.tests.test_source_matching_generalization import html, url_reference
    transport(monkeypatch, html())
    result = check(TestClient(app), url_reference(), retrieve=True)
    assert result['identity'] == 'CONFIRMED'
    assert 'UNRECOGNIZED_INSTITUTION' in result['source']['provenance']['warnings']
    assert result['source']['provenance']['identity'] == 'EXACT_IDENTITY'


def test_conflict_can_upload_explicit_matching_candidate_and_recheck(monkeypatch):
    content = doi_setup(monkeypatch)
    monkeypatch.setattr('app.services.manual_source.resolve_doi', lambda *a, **k:
        CitationMetadata(doi=DOI, title=TITLE, authors=['Ada Lovelace'], year=2020, source='crossref'))
    ref = reference()
    client = TestClient(app)
    response = client.post('/api/sources/manual-reference', data={'reference': ref.model_dump_json(),
        'locator': SourceLocator(kind='doi', value=DOI).model_dump_json()}, files={'file': ('source.pdf', content, 'application/pdf')})
    assert response.status_code == 200, response.text
    assert response.json()['reference_id'] == ref.id
    saved = check(client, ref)
    assert saved['identity'] == 'CONFIRMED' and saved['source']['origin'] == 'manual'
    assert saved['raw_content_sha256'] == hashlib.sha256(content).hexdigest()
    assert saved['source']['url'] is None


def test_upload_cannot_choose_foreign_candidate_or_accept_wrong_pdf():
    ref = reference()
    client = TestClient(app)
    response = client.post('/api/sources/manual-reference', data={'reference': ref.model_dump_json(),
        'locator': SourceLocator(kind='doi', value='10.1234/foreign').model_dump_json()}, files={'file': ('source.pdf', pdf_bytes(), 'application/pdf')})
    assert response.status_code == 400 and response.json()['detail']['code'] == 'SOURCE_NOT_CITED'
    wrong = pdf_bytes(['Unrelated laboratory optical absorption measurements', 'Results', 'Full text'])
    response = client.post('/api/sources/manual-reference', data={'reference': ref.model_dump_json(),
        'locator': SourceLocator(kind='doi', value=DOI).model_dump_json()}, files={'file': ('source.pdf', wrong, 'application/pdf')})
    assert response.status_code == 400 and response.json()['detail']['code'] == 'SOURCE_MISMATCH'
    assert LocalSourceStore().get(DOI) is None



def test_stage4_reader_and_evidence_keep_confirmation_without_new_download(monkeypatch):
    from app.services.source_acquisition import retrieve_reference_source
    from app.researchguard.adapters.sciverify import accepted_source_to_domain
    content = doi_setup(monkeypatch)
    seen = transport(monkeypatch, content, 'application/pdf')
    ref = reference().model_copy(update={'authors': (), 'year': 2019})
    ready = check(TestClient(app), ref, retrieve=True)
    assert ready['identity'] == 'CONFIRMED'
    count = len(seen)
    result = retrieve_reference_source(ref, local_only=True)
    source, chunks = accepted_source_to_domain(result)
    assert len(seen) == count and result.source.cache_hit
    assert source.content_hash == 'sha256:' + ready['raw_content_sha256']
    assert chunks and all(c.metadata['source_identity_status'] == 'confirmed' for c in chunks)
    assert all('HISTORICAL_VERSION_UNCONFIRMED' in c.metadata['source_provenance']['warnings'] for c in chunks)



def test_wrong_cached_paper_waits_for_explicit_upload_and_preserves_history(monkeypatch):
    content = doi_setup(monkeypatch)
    wrong = pdf_bytes(['Optical absorption in amorphous carbon thin films', 'Results', 'Physical laboratory measurements'], metadata={'/Title': 'Optical absorption in amorphous carbon thin films'})
    store = LocalSourceStore()
    artifact = AcceptedSourceArtifact.create(doi=DOI, content=wrong, format='pdf', source_url='https://example.org/wrong.pdf',
        provider='fixture', origin='remote', paper=PaperMetadata(paper_id=DOI, doi=DOI, title=TITLE,
            authors=['Ada Lovelace'], year=2020, full_text_available=True, full_text_format='pdf'))
    store.put(artifact)
    original = store.root / artifact.raw_content_sha256 / 'source.pdf'
    seen = transport(monkeypatch, content, 'application/pdf')
    local = check(TestClient(app), reference())
    assert local['identity'] == 'CONFLICT' and local['state'] != 'available' and not seen
    waiting = check(TestClient(app), reference(), retrieve=True)
    assert waiting['identity'] == 'CONFLICT' and not seen
    monkeypatch.setattr('app.services.manual_source.resolve_doi', lambda *a, **k:
        CitationMetadata(doi=DOI, title=TITLE, authors=['Ada Lovelace'], year=2020, source='crossref'))
    receipt = TestClient(app).post('/api/sources/manual-reference', data={
        'reference': reference().model_dump_json(), 'locator': SourceLocator(kind='doi', value=DOI).model_dump_json()},
        files={'file': ('correct.pdf', content, 'application/pdf')})
    assert receipt.status_code == 200, receipt.text
    recovered = check(TestClient(app), reference())
    assert recovered['identity'] == 'CONFIRMED' and recovered['raw_content_sha256'] == receipt.json()['raw_content_sha256']
    assert not seen and original.read_bytes() == wrong



def test_candidate_discovery_without_full_text_is_not_possible_full_text():
    result = check(TestClient(app), reference())
    assert result['state'] == 'not_cached' and result['identity'] == 'CANDIDATE_FOUND'
    assert result['full_text_obtained'] is False and result['raw_content_sha256'] is None



def test_known_primary_cache_conflict_keeps_evidence_without_remote_recovery(monkeypatch):
    from app.services import paper_retriever as retrieval
    from app.services.document_retriever import DocumentRetrievalError
    doi_setup(monkeypatch)
    wrong = pdf_bytes(['Optical absorption in amorphous carbon thin films', 'Results', 'Physical laboratory measurements'], metadata={'/Title': 'Optical absorption in amorphous carbon thin films'})
    store = LocalSourceStore()
    store.put(AcceptedSourceArtifact.create(doi=DOI, content=wrong, format='pdf', source_url='https://example.org/wrong.pdf',
        provider='fixture', origin='remote', paper=PaperMetadata(paper_id=DOI, doi=DOI, title=TITLE,
            full_text_available=True, full_text_format='pdf')))
    def fail(*args, **kwargs):
        pytest.fail('A known primary cache conflict must wait for upload, not download again.')
    monkeypatch.setattr(retrieval, 'retrieve_document', fail)
    result = check(TestClient(app), reference(), retrieve=True)
    assert result['state'] != 'available' and result['identity'] == 'CONFLICT'
    assert result['candidates'][0]['identity_conflict_observed']
    assert 'SOURCE_IDENTITY_CONFLICT_OBSERVED' in result['candidates'][0]['diagnostics']



def test_rejected_secondary_candidate_is_not_a_conflict_of_the_primary_reference():
    wrong_doi = '10.1234/secondary'
    wrong_title = 'Optical absorption in amorphous carbon thin films'
    wrong = pdf_bytes([wrong_title, 'Results', 'Physical laboratory measurements'], metadata={'/Title': wrong_title})
    LocalSourceStore().put(AcceptedSourceArtifact.create(doi=wrong_doi, content=wrong, format='pdf', source_url='https://example.org/secondary.pdf',
        provider='fixture', origin='remote', paper=PaperMetadata(paper_id=wrong_doi, doi=wrong_doi, title=wrong_title,
            full_text_available=True, full_text_format='pdf')))
    ref = reference(candidates=(ReferenceCandidate(doi=wrong_doi, title=wrong_title, provider='openalex'),)).model_copy(update={'doi': DOI})
    result = check(TestClient(app), ref)
    assert result['state'] == 'not_cached' and result['identity'] == 'CANDIDATE_FOUND'
    assert any(c.get('identity_conflict_observed') for c in result['candidates'])
