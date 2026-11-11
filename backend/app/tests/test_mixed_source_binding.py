"""Resolved DOI plus selected URL must not lose its acquisition identity."""
import pytest

from app.researchguard.domain import ReferenceResolution
from app.researchguard.manuscript_verification import ManuscriptCoreResult, SourceBinding
from app.researchguard.source_locator import SourceLocator
from app.services import manuscript_verification as core
from app.services.citation_context import fingerprint
from app.services.source_locator import reference_locator
from app.schemas.paper import PaperRetrievalStatus
from app.tests.test_manuscript_verification import inputs, FakeRetriever, verifier
from app.tests.test_paperqa2_integration import paper


def mixed_inputs():
    parsed, extraction = inputs()
    ref = parsed.references[0].model_copy(update={
        'raw_text': 'XLNet. https://proceedings. neurips.cc/paper.pdf',
        'resolution': ReferenceResolution(reference_id='r1', status='resolved',
            resolved_doi='10.1234/local', provider='crossref', match_reason='fixture'),
    })
    parsed = parsed.model_copy(update={'references': (ref,)})
    extraction = extraction.model_copy(update={'metadata': extraction.metadata.model_copy(
        update={'input_fingerprint': 'sha256:' + fingerprint(parsed)})})
    assert reference_locator(ref) == SourceLocator(kind='url', value='https://proceedings/')
    return parsed, extraction


@pytest.mark.anyio
@pytest.mark.parametrize('outcome', ['url', 'doi_fallback', 'unavailable', 'foreign', 'url_with_doi'])
async def test_mixed_identity_survives_binding_and_keeps_checks(paper, monkeypatch, outcome):
    parsed, extraction = mixed_inputs()
    before = parsed.model_dump_json(), extraction.model_dump_json()
    chosen = reference_locator(parsed.references[0])
    response = paper.model_copy(deep=True)
    response.source.locator = chosen
    response.paper.doi = None
    if outcome == 'doi_fallback':
        response.source.locator = SourceLocator(kind='doi', value='10.1234/local')
        response.paper.doi = '10.1234/local'
    elif outcome == 'foreign':
        response.source.locator = SourceLocator(kind='doi', value='10.9999/foreign')
        response.paper.doi = '10.9999/foreign'
    elif outcome == 'url_with_doi':
        response.paper.doi = '10.1234/local'
    elif outcome == 'unavailable':
        response.status = PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        response.chunks = []
    acquisitions, queries, verified = [], [], []

    def acquire(reference, **kwargs):
        acquisitions.append(reference.id)
        # Exercise the injection path too: a URL must never be sent as DOI=None.
        assert kwargs['doi_retriever'] is not None
        return response

    def forbidden_doi(doi):
        pytest.fail(f'Unexpected DOI-only retrieval: {doi}')

    async def verify(claim, evidence):
        verified.append(claim)
        return await verifier(claim, evidence)

    monkeypatch.setattr(core, 'retrieve_reference_source', acquire)
    result = await core.verify_manuscript_core(parsed, extraction,
        source_retriever=forbidden_doi,
        evidence_retriever_factory=lambda chunks: FakeRetriever(chunks, queries),
        prepared_verifier=verify)
    pair = result.pairs[0]
    assert acquisitions == ['r1']
    assert pair.binding is not None
    SourceBinding.model_validate(pair.binding.model_dump())
    assert before == (parsed.model_dump_json(), extraction.model_dump_json())
    assert ManuscriptCoreResult.model_validate_json(result.model_dump_json()) == result
    if outcome in {'url', 'doi_fallback'}:
        assert pair.reason_code == 'VERIFIED'
        assert pair.binding.doi == response.paper.doi
        assert pair.binding.locator == response.source.locator
        assert len(queries) == len(verified) == 1
    else:
        assert not queries and not verified
        assert pair.legacy_verdict is None
        assert pair.reason_code == ('SOURCE_REQUIRED_FULL_TEXT_UNAVAILABLE'
            if outcome == 'unavailable' else 'SOURCE_LOCATOR_MISMATCH')
