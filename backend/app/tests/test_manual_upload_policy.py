"""Manual choice is a binding, not identity evidence; all checks run offline."""
import hashlib
from dataclasses import replace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.researchguard.domain import Reference
from app.services.citation_resolver import CitationResolverError
from app.services.manual_source import accept_manual_pdf, match_pdf_identity
from app.services.source_acquisition import retrieve_reference_source
from app.services.source_preparation import prepare_reference
from app.services.source_store import LocalSourceStore, verify_source_durability
from app.tests.test_source_lifecycle import DOI, TITLE, CITATION, artifact, pdf_bytes


def reference():
    return Reference(id='r1', manuscript_id='m', doi=DOI, title=TITLE,
        raw_text=TITLE, authors=('Ada Lovelace',), year=2020)


@pytest.mark.parametrize('header,expected', [
    (TITLE.upper().replace(' ', '-'), 'title'),
    (TITLE, 'title'),
    ('An incomplete cover', 'uncertain'),
    ('Unrelated optical measurements and laboratory methods\nGrace Hopper', None),
    ('Unrelated optical measurements and laboratory methods\nAda Lovelace', 'uncertain'),
    (TITLE + '\ndoi: 10.1234/wrong', None),
    (TITLE + '\ndoi: 10.48550/arxiv.1234.5678', 'uncertain'),
    ('References\n' + DOI, 'uncertain'),
])
def test_positive_match_missing_identity_and_definite_conflicts(header, expected):
    assert match_pdf_identity(DOI, CITATION, header, {}) == expected


@pytest.mark.parametrize('title_known', [False, True])
def test_provider_failure_accepts_pdf_without_faking_pdf_doi(monkeypatch, title_known):
    resolver = Mock(side_effect=CitationResolverError('offline'))
    monkeypatch.setattr('app.services.manual_source.resolve_doi', resolver)
    content = pdf_bytes([TITLE if title_known else 'Incomplete cover', 'Results',
        'Treatment reduces risk in actual patients.'])
    receipt = accept_manual_pdf(DOI, content, reference=reference())
    resolver.assert_not_called()
    assert receipt['identity_match'] == ('title' if title_known else 'uncertain')
    saved = LocalSourceStore().get(DOI)
    assert saved.provenance.matched_doi is None
    assert not any(e.startswith('PDF_DOI:') for e in saved.provenance.match_evidence)
    assert 'USER_SELECTED_DOI_LOCATOR' in saved.provenance.match_evidence
    assert saved.raw_content_sha256 == hashlib.sha256(content).hexdigest()
    ready = prepare_reference(reference())
    assert ready['state'] == 'available'
    assert ready['identity'] == ('CONFIRMED' if title_known else 'UNCERTAIN')
    if not title_known:
        assert 'SOURCE_IDENTITY_UNCERTAIN' in ready['source']['provenance']['warnings']
    stage4 = retrieve_reference_source(reference(), local_only=True)
    verify_source_durability(stage4, LocalSourceStore())
    assert stage4.status.value == 'success' and stage4.chunks
    assert stage4.source.raw_content_sha256 == receipt['raw_content_sha256']


def test_legacy_doi_upload_survives_missing_provider_metadata(monkeypatch):
    monkeypatch.setattr('app.services.manual_source.resolve_doi', Mock(side_effect=CitationResolverError('offline')))
    receipt = accept_manual_pdf(DOI, pdf_bytes(['Incomplete cover', 'Results', 'Actual readable source body.']))
    assert receipt['identity_match'] == 'uncertain'
    saved = LocalSourceStore().get(DOI)
    assert saved.origin == 'manual' and saved.provenance.identity == 'IDENTITY_UNCERTAIN'
    assert saved.provenance.matched_doi is None


@pytest.mark.parametrize('same_bytes', [False, True])
def test_manual_upload_rebinds_pointer_and_preserves_old_raw_record(monkeypatch, same_bytes):
    monkeypatch.setattr('app.services.manual_source.resolve_doi', lambda _: CITATION)
    content = pdf_bytes([TITLE, 'Results', 'Treatment reduces risk in actual patients.'])
    original = replace(artifact(content=content if same_bytes else pdf_bytes()), format='pdf',
        paper=artifact().paper.model_copy(update={'full_text_format': 'pdf'}))
    store = LocalSourceStore()
    store.put(original)
    raw = store.root / original.raw_content_sha256 / 'source.pdf'
    old_metadata = (raw.parent / store._lookup_path(DOI).name).read_bytes()
    receipt = accept_manual_pdf(DOI, content, reference=reference())
    saved = store.get(DOI)
    assert saved.origin == 'manual' and saved.content == content
    assert raw.read_bytes() == original.content
    if same_bytes:
        assert (raw.parent / (store._lookup_path(DOI).name + '.previous')).read_bytes() == old_metadata
    else:
        assert (raw.parent / store._lookup_path(DOI).name).read_bytes() == old_metadata
    stage4 = retrieve_reference_source(reference(), local_only=True)
    assert stage4.source.raw_content_sha256 == receipt['raw_content_sha256']
    verify_source_durability(stage4, store)


def test_reference_binding_cannot_select_another_doi():
    response = TestClient(app).post('/api/sources/manual',
        data={'doi': '10.1234/foreign', 'reference': reference().model_dump_json()},
        files={'file': ('source.pdf', pdf_bytes(), 'application/pdf')})
    assert response.status_code == 400 and response.json()['detail']['code'] == 'SOURCE_NOT_CITED'


@pytest.mark.parametrize('cover', [[], [TITLE, 'Ada Lovelace']])
def test_abstract_without_body_is_not_a_valid_manual_full_text(cover):
    response = TestClient(app).post('/api/sources/manual',
        data={'doi': DOI, 'reference': reference().model_dump_json()},
        files={'file': ('abstract.pdf', pdf_bytes([*cover, 'Abstract', 'An abstract without an actual body.']), 'application/pdf')})
    assert response.status_code == 400 and response.json()['detail']['code'] == 'INVALID_PDF'
    assert LocalSourceStore().get(DOI) is None


@pytest.mark.anyio
async def test_step4_core_uses_new_manual_file_and_version(monkeypatch):
    from app.services.citation_context import fingerprint
    from app.services.manuscript_verification import verify_manuscript_core
    from app.tests.test_manuscript_verification import inputs, FakeRetriever, verifier
    monkeypatch.setattr('app.services.manual_source.resolve_doi', lambda _: CITATION)
    LocalSourceStore().put(artifact())
    receipt = accept_manual_pdf(DOI, pdf_bytes([TITLE, 'Results', 'Treatment reduces risk by twelve percent.']), reference=reference())
    parsed, extraction = inputs(dois={'r1': DOI})
    parsed = parsed.model_copy(update={'references': (reference(),)})
    extraction = extraction.model_copy(update={'metadata': extraction.metadata.model_copy(update={
        'input_fingerprint': 'sha256:' + fingerprint(parsed)})})
    queries = []
    result = await verify_manuscript_core(parsed, extraction,
        evidence_retriever_factory=lambda chunks: FakeRetriever(chunks, queries), prepared_verifier=verifier,
        source_durability_check=lambda response: verify_source_durability(response, LocalSourceStore()))
    assert queries and queries[0][1].content_hash == 'sha256:' + receipt['raw_content_sha256']
    assert result.pairs[0].binding.source_version == 'sha256:' + receipt['raw_content_sha256']
