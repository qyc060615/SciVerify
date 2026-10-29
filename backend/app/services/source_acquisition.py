"""Unified DOI/URL acquisition; no claims, LLM, embedding or job scheduling."""
from datetime import datetime, timezone
from io import BytesIO
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.researchguard.source_locator import SourceLocator, SourceProvenance
from app.services.source_locator import reference_locator, reference_candidates, citation_title, MAX_REFERENCE_ATTEMPTS
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
):
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
    attempts = []
    def attempt_record(url):
        existing = next((a for a in attempts if a['url'] == url), None)
        if existing is None:
            existing = dict(url=url, provider='official_url', attempted=False, state='candidate_found',
                reason='NOT_ATTEMPTED', full_text_obtained=False, raw_content_sha256=None)
            attempts.append(existing)
        return existing
    attempt_record(locator.value)
    kind, identity, title, date, final_url = 'UNAVAILABLE', 'IDENTITY_UNCERTAIN', None, None, None
    for _ in range(4):
        if not pending:
            break
        url, fmt = pending.pop(0)
        if url in seen:
            continue
        seen.add(url)
        attempt = attempt_record(url)
        attempt.update(attempted=True, state="unavailable")
        try:
            doc = retrieve_document(url, expected_format=fmt, client=client, public_only=True)
            final_url = doc.source_url
            sections = parse_document(doc.content, doc.format, doc.text)
            kind, identity, title, date = inspect_institutional(doc, reference, locator)
            if kind in {'LANDING_PAGE', 'ABSTRACT_ONLY'}:
                if url == locator.value:
                    links = discover_direct_full_text_links(doc.content, doc.source_url)
                    pending.extend((link.url, link.format) for link in links)
                    for link in links:
                        attempt_record(link.url)
                last = kind
                attempt.update(reason=last)
                continue
            if identity == 'IDENTITY_CONFLICT':
                last = 'SOURCE_' + identity
                attempt.update(state='conflict', reason=last)
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
            attempt.update(state='accepted', reason='SOURCE_PERSISTED', full_text_obtained=True, raw_content_sha256=artifact.raw_content_sha256)
            result.candidates = attempts
            return result
        except (DocumentRetrievalError, DocumentParseError, ValueError) as exc:
            last = str(exc)[:1000] if isinstance(exc, DocumentRetrievalError) else str(exc) if re.fullmatch(r'[A-Z_]+', str(exc)) else type(exc).__name__
            attempt.update(reason=last)
    return RetrievePaperResponse(status=PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE, paper=paper,
        source=PaperSource(url=locator.value, provider='official_url', locator=locator,
            identity_status='conflict' if identity == 'IDENTITY_CONFLICT' else 'uncertain',
            provenance=SourceProvenance(original_citation=reference.raw_text,
                source_url=locator.value, final_url=final_url, retrieved_title=title, publication_date=date,
                retrieved_at=datetime.now(timezone.utc).isoformat(), identity=identity,
                document_kind=kind, match_evidence=(last,), warnings=('HISTORICAL_VERSION_UNCONFIRMED',))), detail=last, candidates=attempts)


def _review_reference(reference, response, locator, citing_publication_date=None):
    """Review the acquired document; missing metadata is never a contradiction."""
    response = response.model_copy(deep=True)
    artifact = LocalSourceStore().get_locator(locator)
    title = document_title(artifact.content, artifact.format, response.paper.title) if artifact else response.paper.title
    expected = citation_title(reference)
    # A document-verified DOI can corroborate its canonical metadata even when
    # no document title is extractable. Do not relabel provider text as a PDF title.
    evidence = response.source.provenance.match_evidence if response.source.provenance else ()
    reviewed_title = title or (response.paper.title if 'ARTICLE_DOI_MATCH' in evidence else None)
    conflict = identity_conflict(expected or '', reviewed_title or '')
    if response.source.identity_status == 'conflict' or conflict or _title_relation(expected, reviewed_title) == 'conflict':
        response.status = PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        response.chunks = []
        response.detail = 'SOURCE_IDENTITY_CONFLICT'
        response.source.identity_status = 'conflict'
        return response
    relation = _title_relation(expected, title)
    previous = response.source.provenance
    warnings = list(previous.warnings if previous else ())
    warnings.append('ORIGINAL_CITATION_VERSION_UNCONFIRMED')
    if reference.resolution:
        warnings.extend(reference.resolution.diagnostics)
    uncertain = (response.source.identity_status != 'confirmed' or relation != 'match')
    from app.services.reference_resolver import _surname
    cited_authors = {_surname(a) for a in reference.authors if _surname(a)}
    actual_authors = {_surname(a) for a in response.paper.authors if _surname(a)}
    if cited_authors and actual_authors and not cited_authors & actual_authors:
        warnings.append('RETRIEVED_AUTHORS_UNCONFIRMED')
        uncertain = True
    identity = 'IDENTITY_UNCERTAIN' if uncertain else 'EXACT_IDENTITY'
    if reference.doi and locator.kind == 'doi' and locator.value != reference.doi:
        warnings.append('VERSION_RELATIONSHIP_UNCONFIRMED')
        identity, uncertain = 'PROBABLE_SAME_WORK' if relation == 'match' else 'IDENTITY_UNCERTAIN', True
    if reference.year and response.paper.year and reference.year != response.paper.year:
        warnings.append('VERSION_DATE_DIFFERS')
        identity, uncertain = 'PROBABLE_SAME_WORK' if relation == 'match' else 'IDENTITY_UNCERTAIN', True
    if not reference.authors:
        warnings.append('AUTHORS_UNCONFIRMED')
    if not title or not expected:
        warnings.append('RETRIEVED_TITLE_UNCONFIRMED')
    if uncertain:
        warnings.append('SOURCE_IDENTITY_UNCERTAIN')
    # Preserve stronger existing related-version evidence without claiming exact identity.
    review = review_version(reference, response, citing_publication_date=citing_publication_date) if not reference.doi else None
    if review and review['identity'] == 'IDENTITY_CONFLICT':
        response.status = PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        response.chunks = []
        response.detail = 'SOURCE_IDENTITY_CONFLICT'
        response.source.identity_status = 'conflict'
        return response
    if review:
        identity, uncertain = review['identity'], True
        warnings.extend(review['warnings'])
    response.source.locator = locator
    response.source.identity_status = 'uncertain' if uncertain else 'confirmed'
    response.source.provenance = SourceProvenance(original_citation=reference.raw_text,
        matched_doi=response.paper.doi, source_url=previous.source_url if previous else response.source.url,
        final_url=response.source.url, retrieved_at=previous.retrieved_at if previous else None,
        retrieved_title=title, publication_date=response.paper.publication_date,
        retrieved_version='sha256:' + response.source.raw_content_sha256 if response.source.raw_content_sha256 else None,
        identity=identity, document_kind='ARTICLE_FULL_TEXT',
        match_evidence=tuple(dict.fromkeys((*(previous.match_evidence if previous else ()),
            'DOCUMENT_TITLE_MATCH' if relation == 'match' else 'REFERENCE_IDENTITY_UNCONFIRMED'))),
        warnings=tuple(dict.fromkeys(warnings)))
    return response


def _cross_work_conflict(reference, record, response):
    """Converging document + author + date evidence, not a fuzzy title veto.

    Generic short titles can occur inside unrelated later titles. Provider
    differences alone are insufficient; require that candidate's actual title
    be verified in the downloaded document before rejecting that association.
    """
    from app.services.reference_resolver import _surname, _compact
    expected, proposed = citation_title(reference), record.get('title')
    if not expected or not proposed or _compact(expected) == _compact(proposed):
        return False
    original = {_surname(a) for a in reference.authors if _surname(a)}
    candidate_authors = {_surname(a) for a in record['authors'] if _surname(a)}
    if not original or not candidate_authors or original & candidate_authors:
        return False
    if not reference.year or not record['years'] or min(abs(reference.year - y) for y in record['years']) < 5:
        return False
    locator = SourceLocator.model_validate(record['locator'])
    artifact = LocalSourceStore().get_locator(locator)
    if not artifact:
        return False
    actual = document_title(artifact.content, artifact.format, proposed)
    return bool(actual and _title_relation(proposed, actual) == 'match')


@single_source(lambda reference, **kwargs: 'reference:' + reference.id)
def retrieve_reference_source(reference, *, doi_retriever=None, client=None, candidate_urls=(),
                              citing_publication_date=None, local_only=False):
    records = reference_candidates(reference)
    valid = [r for r in records if r['locator']]
    if not valid:
        return RetrievePaperResponse(status=PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE,
            paper=PaperMetadata(paper_id=reference.id), source=PaperSource(provider='discovery'),
            candidates=records, detail='SOURCE_LOCATOR_MISSING')

    def acquire(record, cache_only):
        locator = SourceLocator.model_validate(record['locator'])
        if locator.kind == 'url':
            result = retrieve_url_source(reference, locator, client=client, local_only=cache_only)
        else:
            if doi_retriever is not None:
                result = doi_retriever(locator.value)
            else:
                from app.services.paper_retriever import retrieve_paper
                hints = tuple(dict.fromkeys((*record['urls'], *candidate_urls,
                    *((reference.url,) if reference.url else ()))))[:3]
                result = retrieve_paper(locator.value, client=client, candidate_urls=hints, cache_only=cache_only,
                    metadata_hint=PaperMetadata(paper_id=locator.key, doi=locator.value,
                        title=record['title'], authors=record['authors'] or list(reference.authors),
                        year=record['years'][0] if record['years'] else reference.year), max_candidate_visits=8)
            if result.status == PaperRetrievalStatus.SUCCESS:
                result = _review_reference(reference, result, locator, citing_publication_date)
        return result

    last, best, attempts, primary_conflict = None, None, 0, None
    # Read all eligible caches before any network. Cache checks do not consume
    # the four-candidate download budget and never request provider metadata.
    phases = (True,) if local_only else (True, False)
    for cache_only in phases:
        for record in valid:
            if record.get('rejected_work'):
                continue
            if not cache_only and attempts >= MAX_REFERENCE_ATTEMPTS:
                record['reason'] = record['reason'] or 'REFERENCE_DOWNLOAD_BUDGET_EXHAUSTED'
                continue
            if cache_only and doi_retriever is not None:
                continue  # Legacy injected retrievers have no cache-only contract.
            if not cache_only:
                attempts += 1
                record['attempted'] = True
            try:
                result = acquire(record, cache_only)
            except Exception as exc:
                from app.services.paper_retriever import PaperNotFoundError, PaperProviderError
                if not isinstance(exc, (PaperNotFoundError, PaperProviderError, DocumentRetrievalError, DocumentParseError, ValueError, OSError)):
                    raise
                record.update(state='unavailable', reason=type(exc).__name__)
                continue
            if result.status == PaperRetrievalStatus.SUCCESS and _cross_work_conflict(reference, record, result):
                record['rejected_work'] = True
                result = result.model_copy(deep=True)
                result.status = PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
                result.chunks = []
                result.detail = 'SOURCE_IDENTITY_CONFLICT'
                result.source.identity_status = 'conflict'
                if result.source.provenance:
                    result.source.provenance = result.source.provenance.model_copy(update={
                        'identity': 'IDENTITY_CONFLICT',
                        'match_evidence': (*result.source.provenance.match_evidence,
                            'DOCUMENT_VERIFIED_DIFFERENT_WORK_AUTHORS_AND_DATE')})
            from app.services.source_confirmation import apply_confirmation
            result = apply_confirmation(reference, result, SourceLocator.model_validate(record['locator']))
            if result.status == PaperRetrievalStatus.SUCCESS and result.source.provenance:
                from app.services.reference_resolver import discover_url
                original_urls = {discover_url(reference.raw_text), reference.url,
                    reference.resolution.source_url if reference.resolution else None}
                prov = result.source.provenance
                warnings = [*prov.warnings, *record['diagnostics'],
                    *(reference.resolution.diagnostics if reference.resolution else ())]
                if reference.year and record['years'] and reference.year not in record['years']:
                    warnings.append('VERSION_DATE_DIFFERS')
                evidence = prov.match_evidence
                if record['locator']['kind'] == 'url' and record['locator']['value'] not in original_urls:
                    evidence = tuple('PROVIDER_DISCOVERED_URL' if e == 'EXPLICIT_CITED_URL' else e for e in evidence)
                result.source.provenance = prov.model_copy(update={
                    'warnings': tuple(dict.fromkeys(warnings)), 'match_evidence': evidence})
            if (result.source.identity_status == 'conflict'
                    or any(c.get('state') == 'conflict' for c in result.candidates)):
                record['identity_conflict_observed'] = True
                if cache_only and (record['priority'] <= 2 or len(valid) == 1):
                    primary_conflict = result.model_copy(deep=True)
                record['diagnostics'] = list(dict.fromkeys((*record['diagnostics'], 'SOURCE_IDENTITY_CONFLICT_OBSERVED')))
            if not cache_only:
                record['downloads'] = result.candidates
            record.update(reason=result.detail or result.status.value,
                cache_hit=result.source.cache_hit, identity_status=result.source.identity_status)
            if result.status == PaperRetrievalStatus.SUCCESS and result.source.identity_status != 'conflict':
                record.update(state='accepted', full_text_obtained=True,
                    raw_content_sha256=result.source.raw_content_sha256, reason='SOURCE_PERSISTED')
                rank = 2 if result.source.identity_status == 'confirmed' else 1
                if best is None or rank > best[0]:
                    best = (rank, result)
                # Ranked exact identity is sufficient. Uncertain sources remain
                # usable while the remaining bounded candidates are compared.
                if rank == 2:
                    result.candidates = records
                    return result
            else:
                record['state'] = 'conflict' if result.source.identity_status == 'conflict' else 'candidate_found' if cache_only else 'unavailable'
                last = result
        if best:
            best[1].candidates = records
            return best[1]
        if primary_conflict is not None:
            primary_conflict.candidates = records
            primary_conflict.detail = 'SOURCE_IDENTITY_CONFLICT'
            primary_conflict.source.identity_status = 'conflict'
            return primary_conflict  # Known wrong cached work waits for explicit PDF upload.
    if last is None:
        last = RetrievePaperResponse(status=PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE,
            paper=PaperMetadata(paper_id=reference.id), source=PaperSource(provider='discovery'))
    last.candidates = records
    last.detail = 'SOURCE_NOT_CACHED' if local_only else ('SOURCE_IDENTITY_CONFLICT' if last.source.identity_status == 'conflict' else 'SOURCE_CANDIDATES_EXHAUSTED')
    return last
