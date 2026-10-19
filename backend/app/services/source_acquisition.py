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
from app.services.full_text_qualifier import is_full_text_document, discover_direct_full_text_links
from app.services.source_identity import _words, _title_relation
from app.services.source_store import AcceptedSourceArtifact, LocalSourceStore
from app.services.source_versions import review_version, document_version_date


def _official(url):
    host = urlsplit(url).hostname or ''
    return any(host == d or host.endswith('.' + d) for d in ('cdc.gov', 'fda.gov', 'who.int', 'jhu.edu'))


def inspect_institutional(document, reference, locator):
    """A main document with title/body evidence, not a long navigation page."""
    target = re.sub(r'^(?:.*?guidance for industry\s*:\s*)', '', reference.title or '', flags=re.I)
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
        abstract_only = len(pages) == 1 and re.search(r'(?im)^\s*abstract\b', body)
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
        structures = sum(bool(re.search(r'purpose|background|recommendations?|considerations?|guidance|scope|symptoms|prevention|treatment|protect', h)) for h in headings)
        structural = len(paragraphs) >= 4 and len(body.split()) >= 250 and structures >= 2 and links < len(body) * .5
        abstract_only = had_abstract and not structural
        title_region = title
    if abstract_only:
        return 'ABSTRACT_ONLY', 'IDENTITY_UNCERTAIN', title, date
    if not structural:
        return 'LANDING_PAGE', 'IDENTITY_UNCERTAIN', title, date
    expected = _words(target)
    actual = _words(title_region)
    match = len(expected.split()) >= 4 and (expected in actual or _title_relation(target, title) == 'match')
    if not match:
        return 'INSTITUTIONAL_DOCUMENT', ('IDENTITY_CONFLICT' if _title_relation(target, title) == 'conflict'
                                          else 'IDENTITY_UNCERTAIN'), title, date
    # Public official hosting corroborates title identity; it does not prove history.
    trusted = _official(locator.value) and _official(document.source_url)
    return 'INSTITUTIONAL_DOCUMENT', 'EXACT_IDENTITY' if trusted else 'IDENTITY_UNCERTAIN', title, date


def retrieve_url_source(reference, locator=None, *, client=None, store=None, refresh=False):
    locator = locator or reference_locator(reference)
    if locator is None or locator.kind != 'url':
        raise ValueError('URL_SOURCE_LOCATOR_REQUIRED')
    store = store or LocalSourceStore()
    artifact = store.get_locator(locator)
    if artifact and not refresh:
        cached = RetrievedDocument(artifact.content, None, artifact.format,
            'application/pdf' if artifact.format == 'pdf' else 'text/html', artifact.source_url or locator.value)
        kind, identity, title, date = inspect_institutional(cached, reference, locator)
        if identity != 'EXACT_IDENTITY':
            return RetrievePaperResponse(status=PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE,
                paper=artifact.paper, source=PaperSource(provider='official_url', locator=locator,
                provenance=SourceProvenance(original_citation=reference.raw_text,
                    identity=identity, document_kind=kind, retrieved_title=title,
                    source_url=locator.value, final_url=artifact.source_url,
                    warnings=('HISTORICAL_VERSION_UNCONFIRMED',))), detail='SOURCE_' + identity)
        sections = parse_document(artifact.content, artifact.format)
        chunks = chunk_sections(sections, artifact.paper.paper_id, artifact.source_url)
        return artifact.response(cache_hit=True, sections=sections, chunks=chunks)
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
            if identity != 'EXACT_IDENTITY':
                last = 'SOURCE_' + identity
                continue
            chunks = chunk_sections(sections, locator.key, doc.source_url)
            if not chunks:
                last = 'SOURCE_PARSING_FAILURE'
                continue
            paper.title = title; paper.publication_date = date
            paper.full_text_available = True; paper.full_text_format = doc.format; paper.full_text_url = doc.source_url
            provenance = SourceProvenance(original_citation=reference.raw_text, source_url=locator.value,
                final_url=doc.source_url, retrieved_at=datetime.now(timezone.utc).isoformat(),
                retrieved_title=title, publication_date=date, identity=identity, document_kind=kind,
                match_evidence=('OFFICIAL_ORIGIN', 'DOCUMENT_TITLE_MATCH', 'SUBSTANTIVE_DOCUMENT_BODY'),
                warnings=('HISTORICAL_VERSION_UNCONFIRMED',))
            artifact = AcceptedSourceArtifact.create(locator=locator, content=doc.content, format=doc.format,
                source_url=doc.source_url, provider='official_url', origin='remote', paper=paper, provenance=provenance)
            # Actual bytes, never title/date, pin the version that RAG will consume.
            provenance = provenance.model_copy(update={'retrieved_version': 'sha256:' + artifact.raw_content_sha256})
            from dataclasses import replace
            artifact = replace(artifact, provenance=provenance)
            store.put(artifact)
            result = artifact.response(sections=sections, chunks=chunks)
            result.source.identity_status = 'confirmed'
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


def retrieve_reference_source(reference, *, doi_retriever=None, client=None, candidate_urls=()):
    locator = reference_locator(reference)
    if locator is None:
        raise ValueError('SOURCE_LOCATOR_MISSING')
    if locator.kind == 'url':
        result = retrieve_url_source(reference, locator, client=client)
        if result.source.provenance:
            result.source.provenance = result.source.provenance.model_copy(update={'original_citation': reference.raw_text})
        return result
    if doi_retriever is None:
        from app.services.paper_retriever import retrieve_paper
        from functools import partial
        hints = tuple(dict.fromkeys((*candidate_urls, *((reference.url,) if reference.url else ()))))[:3]
        doi_retriever = partial(retrieve_paper, candidate_urls=hints)
    response = doi_retriever(locator.value)
    if response.status != PaperRetrievalStatus.SUCCESS:
        return response
    date_warning = ()
    if not reference.doi:
        artifact = LocalSourceStore().get_locator(locator)
        if artifact:
            actual_date = document_version_date(artifact.content, artifact.format)
            if actual_date and actual_date != response.paper.publication_date:
                date_warning = ('PROVIDER_DATE_DIFFERS_FROM_RETRIEVED_VERSION',)
                response = response.model_copy(deep=True)
                response.paper.publication_date = actual_date
    review = review_version(reference, response) if not reference.doi else None
    if not reference.doi and review is None:
        rejected = response.model_copy(deep=True)
        rejected.status = PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        rejected.chunks = []
        rejected.detail = 'SOURCE_VERSION_UNCONFIRMED'
        rejected.source.identity_status = 'uncertain'
        if rejected.source.provenance:
            rejected.source.provenance = rejected.source.provenance.model_copy(update={
                'identity': 'IDENTITY_UNCERTAIN', 'original_citation': reference.raw_text,
                'warnings': rejected.source.provenance.warnings + ('SOURCE_VERSION_UNCONFIRMED',)})
        return rejected
    if review:
        review['warnings'] = review['warnings'] + date_warning
        response = response.model_copy(deep=True)
        response.source.locator = locator
        response.source.identity_status = 'uncertain'
        response.source.provenance = SourceProvenance(original_citation=reference.raw_text,
            matched_doi=response.paper.doi, source_url=response.paper.url,
            final_url=response.source.url, retrieved_title=response.paper.title,
            retrieved_at=response.source.provenance.retrieved_at if response.source.provenance else None,
            publication_date=response.paper.publication_date, document_kind='ARTICLE_FULL_TEXT',
            retrieved_version='sha256:' + response.source.raw_content_sha256, **review)
    return response
