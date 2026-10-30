"""Provider outages must not disconnect verified local documents from references."""
from dataclasses import replace
from unittest.mock import Mock

import httpx
import pytest

from app.researchguard.domain import Reference
from app.researchguard.source_locator import SourceLocator, SourceProvenance
from app.schemas.paper import PaperMetadata
from app.services.local_reference_recovery import recover_local_reference
from app.services.reference_resolver import resolve_reference, resolve_references
from app.services.source_preparation import prepare_reference
from app.services.source_store import AcceptedSourceArtifact, LocalSourceStore
from app.tests.test_source_lifecycle import pdf_bytes
from app.tests.test_manuscript_verification import inputs, verifier

TITLE = 'Reliable attention models for structured language inference'
AUTHORS = ('Alice Smith', 'Bob Jones')


def reference(**updates):
    return Reference(id='r1', manuscript_id='m', title=TITLE, authors=AUTHORS,
        year=2020, raw_text='Alice Smith, Bob Jones. ' + TITLE + '. 2020.').model_copy(update=updates)


def save(doi='10.1234/local-recovery', *, locator=None, content=None, **updates):
    content = content or pdf_bytes([TITLE, 'Alice Smith Bob Jones 2020',
        'Abstract', 'This study examines reliable attention models.',
        'Introduction', 'Structured language inference uses attention over the input.',
        'Results', 'Treatment reduces risk by 12% in a controlled study.'])
    locator = locator or SourceLocator(kind='doi', value=doi)
    paper = PaperMetadata(paper_id=locator.key if locator.kind == 'url' else doi,
        doi=doi if locator.kind == 'doi' else None, title=TITLE, authors=list(AUTHORS),
        year=2020, full_text_available=True, full_text_format='pdf')
    artifact = AcceptedSourceArtifact.create(doi=paper.doi, locator=locator, content=content,
        format='pdf', source_url='https://example.org/paper.pdf', provider='fixture', origin='remote', paper=paper,
        provenance=SourceProvenance(identity='EXACT_IDENTITY', document_kind='ARTICLE_FULL_TEXT',
            original_citation=reference().raw_text, match_evidence=('DOCUMENT_TITLE_DIRECT_MATCH',)))
    artifact = replace(artifact, **updates)
    LocalSourceStore().put(artifact)
    return artifact


def no_network(monkeypatch):
    forbidden = Mock(side_effect=AssertionError('A local hit must never contact a provider or download'))
    monkeypatch.setattr('app.services.paper_retriever.resolve_doi', forbidden)
    monkeypatch.setattr('app.services.source_acquisition.retrieve_document', forbidden)
    return forbidden


@pytest.mark.anyio
async def test_unique_verified_local_hit_skips_unavailable_providers_and_populates_real_reference(monkeypatch):
    artifact = save()
    forbidden = no_network(monkeypatch)
    parsed, _ = inputs()
    parsed = parsed.model_copy(update={'references': (reference(),)})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail('Providers are offline'))) as client:
        enriched = await resolve_references(parsed, client=client)
    restored = enriched.references[0]
    assert restored.doi == artifact.doi and restored.resolution.provider == 'local_cache'
    assert restored.raw_text == reference().raw_text
    status = prepare_reference(restored, retrieve=True)
    assert status['state'] == 'available' and status['raw_content_sha256'] == artifact.raw_content_sha256
    assert status['source']['cache_hit']
    forbidden.assert_not_called()


@pytest.mark.anyio
async def test_completely_unavailable_providers_without_a_cache_leave_reference_unresolved():
    def offline(request):
        raise httpx.ConnectError('offline', request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(offline)) as client:
        result = await resolve_reference(reference(), client=client)
    assert result.status == 'provider_error' and result.resolved_doi is None


def test_multiple_reliable_local_files_are_ambiguous():
    save()
    save('10.1234/another', content=pdf_bytes([TITLE, 'Alice Smith Bob Jones 2020',
        'Abstract', 'Another matching version.', 'Results', 'Different persisted content.']))
    result = recover_local_reference(reference())
    assert result.status == 'ambiguous' and result.resolved_doi is None
    assert result.match_reason == 'LOCAL_CACHE_MULTIPLE_IDENTITIES'


def test_same_bytes_with_conflicting_doi_aliases_are_not_arbitrarily_bound():
    artifact = save()
    save('10.1234/another', content=artifact.content)
    assert recover_local_reference(reference()).status == 'ambiguous'


def test_verified_historical_citation_disambiguates_a_publication_and_unassociated_preprint():
    formal = save()
    save('10.1234/preprint', content=pdf_bytes([TITLE, 'Alice Smith Bob Jones 2020',
        'Abstract', 'Alternative preprint.', 'Results', 'Earlier version.']),
        provenance=SourceProvenance(identity='EXACT_IDENTITY', document_kind='ARTICLE_FULL_TEXT'))
    result = recover_local_reference(reference())
    assert result.resolved_doi == formal.doi
    assert 'LOCAL_HISTORICAL_CITATION_MATCH' in result.diagnostics


def test_an_arxiv_identifier_in_metadata_is_not_used_as_the_document_title():
    from pypdf import PdfReader, PdfWriter
    from io import BytesIO
    text = pdf_bytes([TITLE, 'Alice Smith Bob Jones 2020', 'Abstract',
        'Introduction', 'Structured language inference. ' * 180, 'Results', 'Reliable attention results. ' * 180])
    writer = PdfWriter(); writer.clone_document_from_reader(PdfReader(BytesIO(text)))
    writer.add_blank_page(width=612, height=792)
    output = BytesIO(); writer.write(output)
    locator = SourceLocator(kind='url', value='https://example.org/source.pdf')
    paper = PaperMetadata(paper_id=locator.key, title='arXiv:2001.00001v2 [cs.CL] 1 Jan 2020',
        authors=list(AUTHORS), year=2020, full_text_available=True, full_text_format='pdf')
    artifact = AcceptedSourceArtifact.create(locator=locator, content=output.getvalue(), format='pdf',
        source_url=locator.value, provider='fixture', origin='remote', paper=paper)
    LocalSourceStore().put(artifact)
    result = recover_local_reference(reference())
    assert result.source_url == locator.value


def test_local_resolution_is_disabled_for_remote_api_callers():
    from starlette.requests import Request
    from app.api.routes.manuscripts import get_reference_resolver
    remote = Request({'type': 'http', 'client': ('203.0.113.2', 80)})
    local = Request({'type': 'http', 'client': ('127.0.0.1', 80)})
    assert get_reference_resolver(remote).keywords['local_cache'] is False
    assert get_reference_resolver(local).keywords['local_cache'] is True


@pytest.mark.parametrize('case', ['corrupt', 'wrong_document', 'wrong_authors', 'body_only', 'doi_conflict', 'known_conflict', 'wrong_year', 'malformed'])
def test_wrong_or_unreliable_cache_is_not_recovered(case):
    content = None
    if case == 'wrong_document':
        content = pdf_bytes(['A completely different paper', 'Carol White Dan Brown', 'Abstract', TITLE, 'Results', 'Other work'])
    if case == 'wrong_authors':
        content = pdf_bytes([TITLE, 'Carol White Dan Brown', 'Abstract', 'Results from other authors.'])
    if case == 'body_only':
        content = pdf_bytes(['Unrelated research report', 'Abstract', TITLE, 'Alice Smith Bob Jones', 'Results', 'Body mentions the requested paper.'])
    if case == 'doi_conflict':
        content = pdf_bytes([TITLE, 'Alice Smith Bob Jones 2020', 'doi: 10.1234/wrong', 'Abstract', 'Body text', 'Results', 'Other DOI'])
    if case == 'malformed':
        content = b'%PDF-not-a-readable-document'
    updates = {'provenance': SourceProvenance(identity='IDENTITY_CONFLICT', document_kind='ARTICLE_FULL_TEXT')} if case == 'known_conflict' else {}
    artifact = save(content=content, **updates)
    if case == 'corrupt':
        (LocalSourceStore().root / artifact.raw_content_sha256 / 'source.pdf').write_bytes(b'corrupt')
    ref = reference(year=2015, raw_text='Different historical citation. 2015.') if case == 'wrong_year' else reference()
    assert recover_local_reference(ref) is None


def test_title_only_is_not_identity_evidence():
    save()
    assert recover_local_reference(reference(authors=())) is None
    assert recover_local_reference(reference(authors=('Carol White', 'Dan Brown'))) is None


@pytest.mark.anyio
async def test_explicit_original_doi_or_url_is_never_replaced_by_a_cache_match():
    save()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail('No provider needed'))) as client:
        result = await resolve_reference(reference(doi='10.1234/explicit-other'), client=client)
    assert result.resolved_doi == '10.1234/explicit-other' and result.provider == 'original'


@pytest.mark.anyio
async def test_verified_url_locator_is_written_to_actual_reference(monkeypatch):
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter
    locator = SourceLocator(kind='url', value='https://example.org/paper.pdf')
    text = pdf_bytes([TITLE, 'Alice Smith Bob Jones 2020', 'Abstract',
        'Introduction', 'Reliable language inference and attention. ' * 120,
        'Results', 'Structured inference results are reproducible. ' * 120])
    writer = PdfWriter(); writer.clone_document_from_reader(PdfReader(BytesIO(text)))
    writer.add_blank_page(width=612, height=792)
    output = BytesIO(); writer.write(output)
    save(locator=locator, content=output.getvalue())
    parsed, _ = inputs()
    parsed = parsed.model_copy(update={'references': (reference(),)})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail('No provider needed'))) as client:
        enriched = await resolve_references(parsed, client=client)
    ref = enriched.references[0]
    assert ref.doi is None and ref.url == locator.value and ref.resolution.source_url == locator.value
    assert prepare_reference(ref)['state'] == 'available'


@pytest.mark.anyio
async def test_remote_resolution_cannot_search_the_local_store():
    save()
    parsed, _ = inputs()
    parsed = parsed.model_copy(update={'references': (reference(),)})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        enriched = await resolve_references(parsed, client=client, local_cache=False)
    assert enriched.references[0].doi is None


@pytest.mark.anyio
async def test_step2_and_step4_reuse_the_same_bytes_without_models_or_download(monkeypatch):
    from app.services.manuscript_verification import verify_manuscript_core
    from app.services.citation_context import fingerprint
    from app.tests.test_manuscript_verification import FakeRetriever
    from app.services.source_store import verify_source_durability

    artifact = save()
    forbidden = no_network(monkeypatch)
    parsed, extraction = inputs()
    parsed = parsed.model_copy(update={'references': (reference(),)})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail('No provider needed'))) as client:
        enriched = await resolve_references(parsed, client=client)
    step2 = prepare_reference(enriched.references[0])
    assert step2['state'] == 'available'
    extraction = extraction.model_copy(update={'metadata': extraction.metadata.model_copy(update={'input_fingerprint': 'sha256:' + fingerprint(enriched)})})
    queries = []
    result = await verify_manuscript_core(enriched, extraction,
        evidence_retriever_factory=lambda chunks: FakeRetriever(chunks, queries, 'ok'),
        prepared_verifier=verifier, source_durability_check=lambda response: verify_source_durability(response, LocalSourceStore()))
    pair = result.pairs[0]
    assert queries and pair.processing_status.value == 'completed'
    assert pair.binding.source_version == 'sha256:' + step2['raw_content_sha256']
    forbidden.assert_not_called()
