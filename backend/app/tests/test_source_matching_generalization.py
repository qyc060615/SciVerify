"""Source indexing acceptance, independent of claims, RAG and scientific verdicts."""
import hashlib
from io import BytesIO

import httpx
import pytest
from pypdf import PdfReader, PdfWriter

from app.researchguard.domain import Reference, ReferenceCandidate, ReferenceResolution
from app.researchguard.adapters.sciverify import accepted_source_to_domain
from app.schemas.paper import PaperMetadata, PaperSource, RetrievePaperResponse, DocumentSection
from app.services.source_acquisition import retrieve_url_source, retrieve_reference_source
from app.services.source_versions import probable_candidate, review_version, identity_conflict, document_title
from app.services.source_locator import reference_locator
from app.services.source_store import LocalSourceStore, verify_source_durability
from app.services.reference_resolver import resolve_reference
from app.tests.test_source_lifecycle import pdf_bytes

TITLE = 'Efficient compression of sparse matrices with QX42 operators'
CANDIDATE = 'Sparse matrix compression with efficient QX42 operators'
PROSE = ('Efficient compression of sparse matrices with QX42 operators reduces storage requirements. '
         'The evaluation compares reconstruction errors across a range of sparse matrix dimensions. '
         'Numerical experiments describe reproducible measurements and the complete implementation. ')
URL = 'https://laboratory.example/publications/report'


def version_reference(title=CANDIDATE, authors=('Ada Lovelace', 'Grace Hopper'), year=2020):
    c = ReferenceCandidate(doi='10.1234/revised', title=title, authors=authors, years=(2020,),
        publication_type='preprint', provider='crossref', rejection_reason='TITLE_MISMATCH', match_confidence=.85)
    return Reference(id='r1', manuscript_id='m', raw_text=TITLE + '. preprint.', title=TITLE,
        authors=authors, year=year, resolution=ReferenceResolution(reference_id='r1', status='ambiguous',
            match_reason='VERSION_UNCERTAIN', candidates=(c,)))


def response_for(r, status='confirmed', authors=None):
    c = r.resolution.candidates[0]
    return RetrievePaperResponse(status='success', paper=PaperMetadata(paper_id=c.doi, doi=c.doi,
        title=c.title, authors=list(c.authors if authors is None else authors), year=2020,
        publication_date='2020-12-11'),
        sections=[DocumentSection(section_name='Body', text=PROSE * 20, order=0)],
        source=PaperSource(provider='fixture', identity_status=status, raw_content_sha256='a'*64))


def html(title=TITLE, headings=('Storage layout', 'Numerical evaluation', 'Implementation details', 'Reproducibility')):
    return ('<html><body><main><h1>' + title + '</h1>' + ''.join(
        '<h2>' + h + '</h2><p>' + PROSE * 3 + '</p>' for h in headings) + '</main></body></html>').encode()


def url_reference(title=TITLE):
    return Reference(id='r1', manuscript_id='m', raw_text=(title or 'Laboratory report') + ' (' + URL + ')',
        title=title, url=URL)


def client(body, status=200, mime='text/html'):
    return httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(status, content=body, headers={'content-type': mime})))


@pytest.mark.parametrize('year', [2020, None])
def test_nonmedical_retitled_preprint_has_no_clinical_requirements(year):
    r = version_reference(year=year)
    assert probable_candidate(r)
    review = review_version(r, response_for(r))
    assert review['identity'] == 'PROBABLE_SAME_WORK'
    assert {'RETITLED_PREPRINT', 'VERSION_RELATIONSHIP_UNCONFIRMED'} <= set(review['warnings'])
    if year is None:
        assert 'ORIGINAL_CITATION_DATE_UNKNOWN' in review['warnings']


def test_missing_authors_with_key_identifier_is_uncertain_not_conflict():
    r = version_reference(authors=())
    assert probable_candidate(r)
    review = review_version(r, response_for(r))
    assert review['identity'] == 'IDENTITY_UNCERTAIN'
    assert {'AUTHORS_UNCONFIRMED', 'SOURCE_IDENTITY_UNCERTAIN'} <= set(review['warnings'])


@pytest.mark.parametrize('title', [
    'Efficient compression of sparse matrices with QX43 operators',
    'Measurement of optical absorption in amorphous carbon films',
])
def test_shared_authors_cannot_override_wrong_model_or_different_work(title):
    assert probable_candidate(version_reference(title=title)) is None


def test_missing_identifier_is_not_a_conflict():
    assert identity_conflict(TITLE, TITLE.replace('QX42 ', '')) is None


def test_generic_pdf_metadata_is_not_reported_as_actual_article_title():
    content = pdf_bytes(lines=[TITLE, PROSE], metadata={'/Title': 'Generic Journal Publishing Platform'})
    assert document_title(content, 'pdf', TITLE) == TITLE
    assert document_title(content, 'pdf', 'A different publication about ceramic coatings') is None


def test_fulltext_identity_uncertainty_remains_indexable_at_reference_boundary():
    r = version_reference()
    review = review_version(r, response_for(r, status='uncertain'))
    assert review['identity'] == 'IDENTITY_UNCERTAIN'
    assert 'RELATED_TERMS_IN_SUBSTANTIVE_FULL_TEXT' in review['match_evidence']
    result = retrieve_reference_source(r, doi_retriever=lambda doi: response_for(r, status='uncertain'))
    assert result.status == 'success'
    assert result.source.provenance.identity == 'IDENTITY_UNCERTAIN'
    assert result.source.provenance.original_citation == r.raw_text


def test_version_review_cannot_use_bibliography_or_abstract_as_body():
    r = version_reference(); response = response_for(r)
    response.sections[0].section_name = 'References'
    assert review_version(r, response) is None
    response.sections[0].section_name = 'Abstract'
    assert review_version(r, response) is None


@pytest.mark.parametrize('status', ['confirmed', 'uncertain'])
def test_cache_response_rechecked_per_reference_without_mutating_artifact(status):
    r = version_reference(); response = response_for(r, status=status)
    direct = r.model_copy(update={'doi': response.paper.doi})
    correct = retrieve_reference_source(direct, doi_retriever=lambda doi: response)
    wrong = direct.model_copy(update={'title': TITLE.replace('QX42', 'QX43')})
    rejected = retrieve_reference_source(wrong, doi_retriever=lambda doi: response)
    assert correct.status == 'success'
    assert rejected.status != 'success' and not rejected.chunks
    assert rejected.source.identity_status == 'conflict'
    assert rejected.source.provenance is None  # Legacy responses remain compatible.
    assert response.source.identity_status == status and response.status == 'success'


def test_probable_source_stays_probable_on_repeat_acquisition():
    r = version_reference(); response = response_for(r)
    first = retrieve_reference_source(r, doi_retriever=lambda doi: response)
    response.source.cache_hit = True
    second = retrieve_reference_source(r, doi_retriever=lambda doi: response)
    assert first.source.provenance == second.source.provenance
    assert second.source.provenance.identity == 'PROBABLE_SAME_WORK'
    assert r.doi is None


def test_actual_version_date_is_compared_with_citing_paper_without_inventing_reference_year():
    r = version_reference(year=None)
    result = retrieve_reference_source(r, doi_retriever=lambda doi: response_for(r),
        citing_publication_date='2020-12-10')
    assert result.source.provenance.identity == 'PROBABLE_SAME_WORK'
    assert 'RETRIEVED_VERSION_POSTDATES_CITING_MANUSCRIPT' in result.source.provenance.warnings
    assert 'ORIGINAL_CITATION_DATE_UNKNOWN' in result.source.provenance.warnings
    assert r.year is None


@pytest.mark.parametrize('title', [TITLE, None])
def test_unknown_institution_non_imrad_html_indexes_with_honest_provenance(tmp_path, title):
    store = LocalSourceStore(tmp_path)
    with client(html()) as http:
        first = retrieve_url_source(url_reference(title), client=http, store=store)
        again = retrieve_url_source(url_reference(title), client=http, store=store)
    assert first.status == 'success' and first.chunks and first.paper.doi is None
    assert first.source.provenance.identity == 'IDENTITY_UNCERTAIN'
    assert {'UNRECOGNIZED_INSTITUTION', 'HISTORICAL_VERSION_UNCONFIRMED', 'SOURCE_IDENTITY_UNCERTAIN'} <= set(first.source.provenance.warnings)
    assert again.source.cache_hit and first.source.provenance == again.source.provenance
    verify_source_durability(first, store)
    source, chunks = accepted_source_to_domain(first)
    assert chunks and all(c.source_document_id == source.id for c in chunks)
    assert all(c.metadata['source_provenance']['identity'] == 'IDENTITY_UNCERTAIN' for c in chunks)
    assert source.content_hash == 'sha256:' + hashlib.sha256(html()).hexdigest()


def test_unknown_institution_pdf_report_without_imrad(tmp_path):
    data = pdf_bytes(lines=[TITLE, 'Storage layout', PROSE * 25], metadata={'/Title': TITLE})
    writer = PdfWriter(); writer.clone_document_from_reader(PdfReader(BytesIO(data)))
    writer.add_blank_page(width=612,height=792); out=BytesIO(); writer.write(out)
    with client(out.getvalue(), mime='application/pdf') as http:
        result = retrieve_url_source(url_reference(), client=http, store=LocalSourceStore(tmp_path))
    assert result.status == 'success' and result.chunks
    assert result.source.provenance.identity == 'IDENTITY_UNCERTAIN'


@pytest.mark.parametrize('body', [
    b'<main><h1>Report directory</h1><a href="/download">Download</a></main>',
    ('<main><h1>'+TITLE+'</h1><div class="abstract">'+PROSE*40+'</div></main>').encode(),
    b'<html>Checking your browser before accessing this site</html>',
    b'<html>Subscription required. Purchase access.</html>',
    html('Measurement of optical absorption in amorphous carbon films'),
])
def test_unknown_institution_still_rejects_nonfulltext_and_wrong_identity(tmp_path, body):
    store = LocalSourceStore(tmp_path)
    with client(body) as http:
        result = retrieve_url_source(url_reference(), client=http, store=store)
    assert result.status != 'success' and not result.chunks
    assert store.get_locator(reference_locator(url_reference())) is None


def test_url_cached_document_does_not_inherit_other_citation_identity(tmp_path):
    store = LocalSourceStore(tmp_path)
    with client(html()) as http:
        first = retrieve_url_source(url_reference(), client=http, store=store)
        partial = url_reference('Compression of sparse matrices')
        second = retrieve_url_source(partial, client=http, store=store)
        wrong = retrieve_url_source(url_reference(TITLE.replace('QX42','QX43')), client=http, store=store)
    assert second.source.cache_hit and second.status == 'success'
    assert second.source.provenance.original_citation == partial.raw_text
    assert second.source.provenance.identity == 'IDENTITY_UNCERTAIN'
    assert wrong.status != 'success' and wrong.source.provenance.identity == 'IDENTITY_CONFLICT'
    assert store.get_locator(reference_locator(partial)).provenance == first.source.provenance


@pytest.mark.anyio
async def test_new_url_resolution_discovers_but_never_claims_downloaded_fulltext():
    with client(html()) as _:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: pytest.fail('No metadata query needed'))) as http:
            result = await resolve_reference(url_reference(), client=http)
    assert result.status == 'non_doi_source' and result.match_reason == 'URL_DISCOVERED'
    assert 'SOURCE_NOT_YET_ACQUIRED' in result.diagnostics
    assert 'URL_ONLY_RETRIEVAL_NOT_SUPPORTED' not in str(result)
