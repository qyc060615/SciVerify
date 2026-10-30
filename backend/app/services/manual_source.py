"""Deterministic cited-PDF recovery using the existing resolver/parser/chunker."""
from __future__ import annotations

import logging
import re
import unicodedata
import hashlib
from io import BytesIO
from types import SimpleNamespace

from pypdf import PdfReader

from app.config import source_max_size
from app.services.citation_resolver import resolve_doi, CitationResolverError, CitationNotFoundError
from app.services.document_parser import parse_document
from app.services.evidence_chunker import chunk_sections
from app.services.paper_retriever import _build_paper_metadata
from app.services.source_store import AcceptedSourceArtifact, LocalSourceStore
from app.researchguard.source_locator import SourceProvenance
from app.schemas.paper import PaperMetadata, PaperRetrievalStatus
from app.utils.doi import normalize_doi

logger = logging.getLogger(__name__)
_DOI = re.compile(r"(?<![\w/])10\.\d{4,9}/[^\s<>\"\u201c\u201d]+", re.I)


class ManualSourceError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code, self.status_code = code, status_code


def _words(text: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def _manual_identity(doi, citation, header, metadata):
    """Only positive contrary evidence rejects a user-selected source."""
    from app.services.source_confirmation import compact
    from app.services.source_identity import _title_relation
    header = re.split(r"(?im)^\s*(?:[/\d.()]+\s*)?(?:abstract|introduction|background|methods|results|discussion|references|bibliography)\b", header)[0][:4000]
    identity_metadata = " ".join(str(metadata.get(key, "")) for key in
                                  ("/DOI", "/doi", "/Subject", "/Keywords"))
    found = set()
    for match in _DOI.finditer(header + '\n' + identity_metadata):
        try:
            found.add(normalize_doi(match.group(0).rstrip(').,;]}')))
        except ValueError:
            pass
    expected = citation.title or ''
    target = compact(expected)
    lines = [line.strip() for line in header.splitlines() if line.strip()]
    actual = str(metadata.get('/Title', '')).strip()
    if not actual or re.search(r'(?i)^arxiv:|microsoft|untitled|\.(?:docx?|dvi)$|^document$', actual):
        actual = next((line for line in lines[:5] if not re.search(r'(?i)^arxiv:|published as|^https?://', line)), '')
    standalone = bool(len(target) >= 10 and any(target == compact(' '.join(lines[start:end]))
        for start in range(min(8, len(lines))) for end in range(start + 1, min(start + 5, len(lines)) + 1)))
    title_match = bool(target and (standalone or _title_relation(expected, actual) == 'match'
        or (len(expected.split()) >= 6 and target in compact(header[:2000]))))
    authors = tuple(citation.authors or ())
    author_region = compact(header + ' ' + str(metadata.get('/Author', '')))
    overlap = any(compact(author) in author_region for author in authors if len(compact(author)) >= 5)
    overlap = overlap or any(compact(author.split()[-1]) in author_region
        for author in authors if author.split() and len(compact(author.split()[-1])) >= 4)
    def named_author(line):
        words = re.findall(r'[^\W\d_]+', line)
        return 2 <= len(words) <= 6 and all(word[0].isupper() for word in words) and not re.search(
            r'(?i)university|universidad|institute|journal|research|abstract|copyright|proceedings|department', line)
    author_evidence = any(named_author(line) for line in [str(metadata.get('/Author', '')), *lines[1:]])
    title_conflict = bool(expected and len(actual.split()) >= 4 and _title_relation(expected, actual) == 'conflict')
    conflict = title_conflict and not title_match and bool(authors) and author_evidence and not overlap
    related_version = bool(doi and title_match and len(found) == 1
        and any(value.startswith(('10.48550/arxiv.', '10.1101/')) for value in [doi, *found])
        and next(iter(found)).split('/')[0] != doi.split('/')[0])
    if found and doi and found != {doi} and not related_version:
        conflict = True
    match = None if conflict else 'doi' if doi and found == {doi} else 'uncertain' if related_version else 'title' if title_match else 'uncertain'
    if match == 'title' and overlap and citation.year and str(citation.year) in re.findall(r'\b\d{4}\b', header):
        match = 'title_author_year'  # Retain the existing receipt for this stronger case.
    return {'match': match, 'title': actual or None, 'dois': found, 'related_version': related_version}


def match_pdf_identity(doi, citation, header, metadata) -> str | None:
    return _manual_identity(doi, citation, header, metadata)['match']


def _read_manual_pdf(content, *, validate_body=True):
    if len(content) > source_max_size():
        raise ManualSourceError('FILE_TOO_LARGE', 'The PDF exceeds the configured upload size limit.', 413)
    try:
        if not content.startswith(b'%PDF-'):
            raise ValueError('Invalid PDF')
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted or not reader.pages:
            raise ValueError('Unsupported PDF')
        sections = parse_document(content, 'pdf') if validate_body else []
        has_abstract = any(section.section_name.casefold() == 'abstract' for section in sections)
        body = [section for index, section in enumerate(sections)
            if not (has_abstract and index == 0 and section.section_name == 'Body')
            and section.section_name.casefold() not in {'abstract', 'references', 'bibliography'}
            and len(_words(section.text).split()) >= 3]
        if validate_body and not body:
            raise ValueError('No usable body')
        return sections, reader.pages[0].extract_text() or '', reader.metadata or {}
    except ManualSourceError:
        raise
    except Exception as exc:
        raise ManualSourceError('INVALID_PDF', 'Upload a readable PDF with extractable full text.') from exc


def _manual_provenance(locator, target, content, review):
    uncertain = review['match'] == 'uncertain'
    warnings = ['HISTORICAL_VERSION_UNCONFIRMED']
    if uncertain:
        warnings.append('SOURCE_IDENTITY_UNCERTAIN')
    if review['related_version']:
        warnings.append('RELATED_VERSION_DOI_UNCONFIRMED')
    return SourceProvenance(original_citation=getattr(target, 'raw_text', None),
        matched_doi=locator.value if review['match'] == 'doi' else None,
        identity='IDENTITY_UNCERTAIN' if uncertain else 'EXACT_IDENTITY', document_kind='ARTICLE_FULL_TEXT',
        retrieved_title=review['title'], retrieved_version='sha256:' + hashlib.sha256(content).hexdigest(),
        match_evidence=('USER_SELECTED_' + locator.kind.upper() + '_LOCATOR',
            'MANUAL_PDF_' + ('IDENTITY_UNCONFIRMED' if uncertain else 'DOI_MATCH' if review['match'] == 'doi' else 'TITLE_MATCH'),
            *('PDF_DOI:' + value for value in sorted(review['dois']))), warnings=tuple(warnings))


def review_manual_source(artifact, target):
    """Recheck persisted manual bytes without promoting the user's Locator into evidence."""
    # The acquisition reader extracts the persisted body/chunks separately.
    _, header, metadata = _read_manual_pdf(artifact.content, validate_body=False)
    locator = artifact.source_locator
    return _manual_identity(locator.value if locator.kind == 'doi' else None, target, header, metadata)


def review_manual_response(reference, response, artifact):
    review = review_manual_source(artifact, reference)
    response = response.model_copy(deep=True)
    if review['match'] is None:
        response.status = PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        response.chunks = []
        response.detail = 'SOURCE_IDENTITY_CONFLICT'
        response.source.identity_status = 'conflict'
    else:
        response.source.identity_status = 'uncertain' if review['match'] == 'uncertain' else 'confirmed'
        response.source.provenance = _manual_provenance(artifact.source_locator, reference, artifact.content, review)
        response.detail = None
    return response


def accept_manual_pdf(doi: str, content: bytes, *, reference=None) -> dict:
    normalized = normalize_doi(doi)
    sections, header, metadata = _read_manual_pdf(content)
    citation = None
    if reference is None:
        try:
            citation = resolve_doi(normalized)
        except (CitationResolverError, CitationNotFoundError):
            pass
    if citation and normalize_doi(citation.doi) != normalized:
        citation = None
    target = reference or citation or SimpleNamespace(title=None, authors=(), year=None)
    review = _manual_identity(normalized, target, header, metadata)
    match = review['match']
    if match is None:
        raise ManualSourceError("SOURCE_MISMATCH", "The uploaded PDF does not appear to match DOI " + normalized + ".")
    paper = _build_paper_metadata(citation, None) if citation else PaperMetadata(paper_id=normalized, doi=normalized,
        title=getattr(target, 'title', None), authors=list(target.authors), year=target.year)
    paper.full_text_available = True
    paper.full_text_format = "pdf"
    # No fabricated remote URL for an uploaded file.
    paper.full_text_url = None
    chunks = chunk_sections(sections, paper.paper_id)
    if not chunks:
        raise ManualSourceError("INVALID_PDF", "The PDF contains no usable source text.")
    from app.researchguard.source_locator import SourceLocator
    locator = SourceLocator(kind='doi', value=normalized)
    artifact = AcceptedSourceArtifact.create(
        doi=normalized, content=content, format="pdf", source_url=None,
        provider="manual_upload", origin="manual", paper=paper, locator=locator,
        provenance=_manual_provenance(locator, target, content, review),
    )
    try:
        store = LocalSourceStore()
        store.put(artifact)
        from app.services.source_store import verify_source_durability
        verify_source_durability(artifact.response(), store)
    except (OSError, ValueError) as exc:
        raise ManualSourceError("SOURCE_STORE_FAILED", "The PDF could not be saved locally. Check the source cache directory.", 503) from exc
    logger.info("manual_source_accepted doi=%s match=%s", normalized, match)
    return {"status": "accepted", "doi": normalized,
            "raw_content_sha256": artifact.raw_content_sha256, "identity_match": match}


def accept_reference_pdf(reference, content: bytes, *, locator=None) -> dict:
    """Keep the user-selected reference binding; reject only positive conflicts."""
    from app.services.source_locator import reference_locator, reference_locators
    explicit = locator is not None
    if explicit and locator not in reference_locators(reference):
        raise ManualSourceError('SOURCE_NOT_CITED', "Choose one of this reference's discovered source targets.")
    locator = locator or reference_locator(reference)
    if locator and locator.kind == 'doi':
        accepted = accept_manual_pdf(locator.value, content, reference=reference)
        return {**accepted, 'reference_id': reference.id, 'locator': locator.model_dump()}
    if locator is None or locator.kind != 'url':
        raise ManualSourceError('SOURCE_URL_REQUIRED', 'A cited public URL is required.')
    sections, header, metadata = _read_manual_pdf(content)
    review = _manual_identity(None, reference, header, metadata)
    if review['match'] is None:
        raise ManualSourceError('SOURCE_MISMATCH', 'The PDF identifies a different paper.')
    paper = PaperMetadata(paper_id=locator.key, title=reference.title, authors=list(reference.authors),
        year=reference.year, url=locator.value,
        full_text_available=True, full_text_format='pdf')
    if not chunk_sections(sections, paper.paper_id):
        raise ManualSourceError('INVALID_PDF', 'The PDF contains no usable full text.')
    provenance = _manual_provenance(locator, reference, content, review)
    artifact = AcceptedSourceArtifact.create(locator=locator, content=content, format='pdf',
        source_url=None, provider='manual_upload', origin='manual', paper=paper, provenance=provenance)
    try:
        store = LocalSourceStore()
        store.put(artifact)
        from app.services.source_store import verify_source_durability
        verify_source_durability(artifact.response(), store)
    except (OSError, ValueError) as exc:
        raise ManualSourceError('SOURCE_STORE_FAILED', 'The matching PDF could not be confirmed in local storage.', 503) from exc
    return {'status': 'accepted', 'reference_id': reference.id, 'locator': locator.model_dump(),
            'raw_content_sha256': artifact.raw_content_sha256, 'identity_match': review['match']}
