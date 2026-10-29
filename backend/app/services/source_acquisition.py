"""Unified DOI/URL acquisition; no claims, LLM, embedding or job scheduling."""
from datetime import datetime, timezone
from io import BytesIO
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.researchguard.source_locator import SourceLocator, SourceProvenance
from app.services.source_locator import reference_locator
from app.schemas.paper import PaperMetadata, PaperSource, PaperRetrievalStatus, RetrievePaperResponse
from app.services.document_retriever import retrieve_document, DocumentRetrievalError, RetrievedDocument
from app.services.document_parser import parse_document, DocumentParseError
from app.services.evidence_chunker import chunk_sections
from app.services.full_text_qualifier import discover_direct_full_text_links
from app.services.source_identity import _words, _title_relation
from app.services.source_versions import identity_conflict
from app.services.source_store import AcceptedSourceArtifact, LocalSourceStore
from app.services.source_versions import review_version, document_version_date, document_title
from app.services.source_requests import single_source


def _official(url):
    host = urlsplit(url).hostname or ''
    return any(host == d or host.endswith('.' + d) for d in ('cdc.gov', 'fda.gov', 'who.int', 'jhu.edu'))


def inspect_institutional(document, reference, locator):
    """A main document with title/body evidence, not a long navigation page."""
    target = reference.title or ''
    title = ''; date = None
    if document.format == 'pdf':
        reader = PdfReader(BytesIO(document.content))
        pages = [page.extract_text() or '' for page in reader.pages]
        header = pages[0][:6000] if pages else ''
        metadata_title = str((reader.metadata or {}).get('/Title', ''))
        body = '\n'.join(pages)
        title = metadata_title if len(metadata_title) > 15 else ' '.join(header.splitlines()[:8])[:500]
        title_region = metadata_title + ' ' + header
        date_match = re.search(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+(?:\d{1,2},?\s+)?20\d{2}\b', header)
        date = date_match.group() if date_match else None
        structural = len(pages) >= 2 and len(body.split()) >= 500
        abstract_only = bool(re.search(r'(?im)^\s*abstract\b', body)) and len(body.split()) < 500
    else:
        soup = BeautifulSoup(document.content, 'html.parser')
        title_node = soup.select_one('main h1, article h1, h1')
        title = title_node.get_text(' ', strip=True) if title_node else ''
        date_node = soup.select_one('meta[property="article:modified_time"], meta[name="dcterms.modified"], time[datetime]')
        date = (date_node.get('content') or date_node.get('datetime')) if date_node else None
        main = soup.select_one('main, [role="main"], article')
        if main is None:
            return 'LANDING_PAGE', 'IDENTITY_UNCERTAIN', title, date
        had_abstract = bool(main.select_one('.abstract, #abstract'))
        for node in main.select('nav, header, footer, aside, form, script, style, .abstract, #abstract'):
            node.decompose()
        paragraphs = [n.get_text(' ', strip=True) for n in main.select('p') if len(n.get_text(' ', strip=True)) >= 80]
        body = '\n'.join(paragraphs)
        links = sum(len(a.get_text(' ', strip=True)) for a in main.select('a'))
        headings = [n.get_text(' ', strip=True).casefold() for n in main.select('h2,h3')]
        structures = len({h for h in headings if len(h) >= 3 and not re.match(r'abstract|references|contents|related|links', h)})
        structural = len(paragraphs) >= 4 and len(body.split()) >= 250 and structures >= 2 and links < len(body) * .5
        abstract_only = had_abstract and not structural
        title_region = title
    if abstract_only:
        return 'ABSTRACT_ONLY', 'IDENTITY_UNCERTAIN', title, date
    if not structural:
        return 'LANDING_PAGE', 'IDENTITY_UNCERTAIN', title, date
    expected = _words(target)
    actual = _words(title_region)
    match = len(expected.split()) >= 3 and (expected in actual or _title_relation(target, title) == 'match')
    conflict = identity_conflict(target, title)
    if conflict or (not match and _title_relation(target, title) == 'conflict'):
        return 'INSTITUTIONAL_DOCUMENT', 'IDENTITY_CONFLICT', title, date
    # A cited URL is direct association evidence, but a present title still needs
    # corroboration. Unknown host names affect confidence, never eligibility.
    title_terms = set(expected.split())
    body_terms = set(_words(body).split())
    related = match or (len(title_terms) >= 3 and len(title_terms & body_terms) / len(title_terms) >= .65)
    if not related and target:
        return 'INSTITUTIONAL_DOCUMENT', 'IDENTITY_UNCERTAIN', title, date
    trusted = _official(locator.value) and _official(document.source_url)
    return 'INSTITUTIONAL_DOCUMENT', 'EXACT_IDENTITY' if match and trusted else 'IDENTITY_UNCERTAIN', title, date


def _url_association(reference, title, sections):
    if not reference.title:
        return True  # Explicit cited URL, complete body, missing citation title.
    terms = set(_words(reference.title).split())
    actual = set(_words(title + ' ' + ' '.join(s.text for s in sections)).split())
    return _title_relation(reference.title, title) == 'match' or (
        len(terms) >= 3 and len(terms & actual) / len(terms) >= .65)


def _url_provenance(reference, locator, final_url, identity, title, date, digest, retrieved_at):
    warnings = ['HISTORICAL_VERSION_UNCONFIRMED']
    evidence = ['EXPLICIT_CITED_URL', 'SUBSTANTIVE_DOCUMENT_BODY']
    if _official(locator.value) and _official(final_url):
        evidence.insert(0, 'OFFICIAL_ORIGIN')
    else:
        warnings.append('UNRECOGNIZED_INSTITUTION')
    if _title_relation(reference.title, title) == 'match':
        evidence.append('DOCUMENT_TITLE_MATCH')
    else:
        evidence.append('REFERENCE_TERMS_IN_DOCUMENT' if reference.title else 'CITATION_TITLE_MISSING')
        warnings.append('DOCUMENT_TITLE_UNCONFIRMED')
    if identity == 'IDENTITY_UNCERTAIN':
        warnings.append('SOURCE_IDENTITY_UNCERTAIN')
    return SourceProvenance(original_citation=reference.raw_text, source_url=locator.value,
        final_url=final_url, retrieved_at=retrieved_at, retrieved_title=title, publication_date=date,
        identity=identity, document_kind='INSTITUTIONAL_DOCUMENT', match_evidence=tuple(evidence),
        warnings=tuple(warnings), retrieved_version='sha256:' + digest)



@single_source(lambda reference, locator=None, **kwargs: getattr(locator or reference_locator(reference), 'key', 'unresolved:' + reference.id))
def retrieve_url_source(reference, locator=None, *, client=None, store=None, refresh=False, local_only=False):
    locator = locator or reference_locator(reference)
    if locator is None or locator.kind != 'url':
        raise ValueError('URL_SOURCE_LOCATOR_REQUIRED')
    store = store or LocalSourceStore()
    artifact = store.get_locator(locator)
    if artifact and (not artifact.paper.full_text_available or artifact.paper.full_text_format != artifact.format):
        artifact = None
    if artifact and not refresh:
        cached = RetrievedDocument(artifact.content, None, artifact.format,
            'application/pdf' if artifact.format == 'pdf' else 'text/html', artifact.source_url or locator.value)
        try:
            kind, identity, title, date = inspect_institutional(cached, reference, locator)
            sections = parse_document(artifact.content, artifact.format)
        except Exception:
            # Invalid cached content gets the normal bounded acquisition fallback.
            return retrieve_url_source(reference, locator, client=client, store=store,
                                       refresh=True, local_only=local_only)
        if (identity == 'IDENTITY_CONFLICT' or kind in {'LANDING_PAGE', 'ABSTRACT_ONLY'}
                or not _url_association(reference, title, sections)):
            if not local_only:
                return retrieve_url_source(reference, locator, client=client, store=store, refresh=True)
            return RetrievePaperResponse(status=PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE,
                paper=artifact.paper, source=PaperSource(provider='official_url', locator=locator,
                provenance=SourceProvenance(original_citation=reference.raw_text,
                    identity=identity, document_kind=kind, retrieved_title=title,
                    source_url=locator.value, final_url=artifact.source_url,
                    warnings=('HISTORICAL_VERSION_UNCONFIRMED',))), detail='SOURCE_' + identity)
        chunks = chunk_sections(sections, artifact.paper.paper_id, artifact.source_url)
        result = artifact.response(cache_hit=True, sections=sections, chunks=chunks)
        if artifact.origin == 'manual':
            result.source.provenance = artifact.provenance
            result.source.identity_status = 'confirmed' if artifact.provenance and artifact.provenance.identity == 'EXACT_IDENTITY' else 'uncertain'
        else:
            result.source.provenance = _url_provenance(reference, locator, artifact.source_url or locator.value,
                identity, title, date, artifact.raw_content_sha256,
                artifact.provenance.retrieved_at if artifact.provenance else None)
            result.source.identity_status = 'confirmed' if identity == 'EXACT_IDENTITY' else 'uncertain'
        return result
    if local_only:
        return RetrievePaperResponse(status=PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE,
            paper=PaperMetadata(paper_id=locator.key, url=locator.value),
            source=PaperSource(provider='local_cache', locator=locator), detail='SOURCE_NOT_CACHED')
    paper = PaperMetadata(paper_id=locator.key, doi=None, title=reference.title, authors=list(reference.authors),
                          year=reference.year, url=locator.value)
    pending = [(locator.value, None)]; seen = set(); last = 'SOURCE_UNAVAILABLE'
    kind, identity, title, date, final_url = 'UNAVAILABLE', 'IDENTITY_UNCERTAIN', None, None, None
    for _ in range(4):
        if not pending:
            break
        url, fmt = pending.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            doc = retrieve_document(url, expected_format=fmt, client=client, public_only=True)
            final_url = doc.source_url
            sections = parse_document(doc.content, doc.format, doc.text)
            kind, identity, title, date = inspect_institutional(doc, reference, locator)
            if kind in {'LANDING_PAGE', 'ABSTRACT_ONLY'}:
                if url == locator.value:
                    pending.extend((link.url, link.format) for link in discover_direct_full_text_links(doc.content, doc.source_url))
                last = kind
                continue
            if identity == 'IDENTITY_CONFLICT' or not _url_association(reference, title, sections):
                last = 'SOURCE_' + identity
                continue
            chunks = chunk_sections(sections, locator.key, doc.source_url)
            if not chunks:
                last = 'SOURCE_PARSING_FAILURE'
                continue
            paper.title = title; paper.publication_date = date
            paper.full_text_available = True; paper.full_text_format = doc.format; paper.full_text_url = doc.source_url
            import hashlib
            provenance = _url_provenance(reference, locator, doc.source_url, identity, title, date,
                hashlib.sha256(doc.content).hexdigest(), datetime.now(timezone.utc).isoformat())
            artifact = AcceptedSourceArtifact.create(locator=locator, content=doc.content, format=doc.format,
                source_url=doc.source_url, provider='official_url', origin='remote', paper=paper, provenance=provenance)
            # Actual bytes, never title/date, pin the version that RAG will consume.
            provenance = provenance.model_copy(update={'retrieved_version': 'sha256:' + artifact.raw_content_sha256})
            from dataclasses import replace
            artifact = replace(artifact, provenance=provenance)
            store.put(artifact)
            result = artifact.response(sections=sections, chunks=chunks)
            result.source.identity_status = 'confirmed' if identity == 'EXACT_IDENTITY' else 'uncertain'
            return result
        except (DocumentRetrievalError, DocumentParseError, ValueError) as exc:
            last = str(exc) if re.fullmatch(r'[A-Z_]+', str(exc)) else type(exc).__name__
    return RetrievePaperResponse(status=PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE, paper=paper,
        source=PaperSource(url=locator.value, provider='official_url', locator=locator,
            identity_status='conflict' if identity == 'IDENTITY_CONFLICT' else 'uncertain',
            provenance=SourceProvenance(original_citation=reference.raw_text,
                source_url=locator.value, final_url=final_url, retrieved_title=title, publication_date=date,
                retrieved_at=datetime.now(timezone.utc).isoformat(), identity=identity,
                document_kind=kind, match_evidence=(last,), warnings=('HISTORICAL_VERSION_UNCONFIRMED',))), detail=last)


def retrieve_reference_source(reference, *, doi_retriever=None, client=None, candidate_urls=(),
                              citing_publication_date=None, local_only=False):
    locator = reference_locator(reference)
    if locator is None:
        raise ValueError('SOURCE_LOCATOR_MISSING')
    if locator.kind == 'url':
        result = retrieve_url_source(reference, locator, client=client, **({'local_only': True} if local_only else {}))
        if result.source.provenance:
            result.source.provenance = result.source.provenance.model_copy(update={'original_citation': reference.raw_text})
        return result
    if doi_retriever is None:
        from app.services.paper_retriever import retrieve_paper
        from functools import partial
        hints = tuple(dict.fromkeys((*candidate_urls, *((reference.url,) if reference.url else ()))))[:3]
        doi_retriever = partial(retrieve_paper, candidate_urls=hints, **({'cache_only': True} if local_only else {}))
    response = doi_retriever(locator.value)
    if response.status != PaperRetrievalStatus.SUCCESS:
        return response
    response = response.model_copy(deep=True)
    conflict = identity_conflict(reference.title or '', response.paper.title or '')
    if conflict or _title_relation(reference.title, response.paper.title) == 'conflict':
        response.status = PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        response.chunks = []
        response.detail = 'SOURCE_IDENTITY_CONFLICT'
        response.source.identity_status = 'conflict'
        if response.source.provenance:
            response.source.provenance = response.source.provenance.model_copy(update={
                'identity': 'IDENTITY_CONFLICT', 'original_citation': reference.raw_text,
                'match_evidence': (conflict or 'CITATION_TITLE_CONFLICT',)})
        return response
    if response.source.provenance:
        response.source.provenance = response.source.provenance.model_copy(update={'original_citation': reference.raw_text})
    date_warning = ()
    artifact = LocalSourceStore().get_locator(locator)
    if artifact:
        actual_date = document_version_date(artifact.content, artifact.format)
        if actual_date and actual_date != response.paper.publication_date:
            date_warning = ('PROVIDER_DATE_DIFFERS_FROM_RETRIEVED_VERSION',)
            response.paper.publication_date = actual_date
        if response.source.provenance:
            title = document_title(artifact.content, artifact.format, response.paper.title)
            warnings = list(response.source.provenance.warnings)
            warnings.append('ORIGINAL_CITATION_VERSION_UNCONFIRMED')
            if not title:
                warnings.append('RETRIEVED_TITLE_UNCONFIRMED')
            if response.source.identity_status != 'confirmed':
                warnings.append('VERSION_RELATIONSHIP_UNCONFIRMED')
            response.source.provenance = response.source.provenance.model_copy(update={
                'retrieved_title': title, 'publication_date': response.paper.publication_date,
                'warnings': tuple(dict.fromkeys((*warnings, *date_warning)))})
    review = review_version(reference, response, citing_publication_date=citing_publication_date) if not reference.doi else None
    if not reference.doi and review is None:
        rejected = response.model_copy(deep=True)
        rejected.status = PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        rejected.chunks = []
        rejected.detail = 'SOURCE_REFERENCE_ASSOCIATION_UNCONFIRMED'
        rejected.source.identity_status = 'uncertain'
        if rejected.source.provenance:
            rejected.source.provenance = rejected.source.provenance.model_copy(update={
                'identity': 'IDENTITY_UNCERTAIN', 'original_citation': reference.raw_text,
                'warnings': rejected.source.provenance.warnings + ('SOURCE_VERSION_UNCONFIRMED',)})
        return rejected
    if review and review['identity'] == 'IDENTITY_CONFLICT':
        response.status = PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        response.chunks = []
        response.detail = 'SOURCE_IDENTITY_CONFLICT'
        response.source.identity_status = 'conflict'
    if review:
        review['warnings'] = review['warnings'] + date_warning + ('ORIGINAL_CITATION_VERSION_UNCONFIRMED',)
        response = response.model_copy(deep=True)
        response.source.locator = locator
        response.source.identity_status = 'conflict' if review['identity'] == 'IDENTITY_CONFLICT' else 'uncertain'
        response.source.provenance = SourceProvenance(original_citation=reference.raw_text,
            matched_doi=response.paper.doi, source_url=response.paper.url,
            final_url=response.source.url,
            retrieved_title=response.source.provenance.retrieved_title if response.source.provenance else None,
            retrieved_at=response.source.provenance.retrieved_at if response.source.provenance else None,
            publication_date=response.paper.publication_date, document_kind='ARTICLE_FULL_TEXT',
            retrieved_version='sha256:' + response.source.raw_content_sha256, **review)
    return response
