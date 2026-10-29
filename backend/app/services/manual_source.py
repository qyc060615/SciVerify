"""Deterministic cited-PDF recovery using the existing resolver/parser/chunker."""
from __future__ import annotations

import logging
import re
import unicodedata
from io import BytesIO

from pypdf import PdfReader

from app.config import source_max_size
from app.services.citation_resolver import resolve_doi, CitationResolverError, CitationNotFoundError
from app.services.document_parser import parse_document
from app.services.evidence_chunker import chunk_sections
from app.services.paper_retriever import _build_paper_metadata
from app.services.source_store import AcceptedSourceArtifact, LocalSourceStore
from app.utils.doi import normalize_doi

logger = logging.getLogger(__name__)
_DOI = re.compile(r"(?<![\w/])10\.\d{4,9}/[^\s<>\"\u201c\u201d]+", re.I)


class ManualSourceError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code, self.status_code = code, status_code


def _words(text: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def match_pdf_identity(doi, citation, header, metadata) -> str | None:
    """DOI in first-page header/metadata; fallback exact title plus author AND year.

    Header is restricted to 4000 chars before the first body/reference heading. Conflicting
    DOI evidence blocks fallback. Short/generic titles cannot establish identity.
    """
    header = re.split(r"(?im)^\s*(?:abstract|introduction|background|methods|results|discussion|references|bibliography)\s*:?[ \t]*$", header)[0][:4000]
    identity_metadata = " ".join(str(metadata.get(key, "")) for key in
                                  ("/DOI", "/doi", "/Subject", "/Keywords"))
    found = {normalize_doi(m.group(0).rstrip(").,;]}")) for m in _DOI.finditer(header + "\n" + identity_metadata)}
    if found:
        return "doi" if found == {doi} else None
    title = _words(citation.title or "")
    # A full contiguous title in the title/header region, never anywhere in body.
    title_region = _words(str(metadata.get("/Title", "")) + "\n" + header[:2000])
    if len(title.split()) < 6 or len(title) < 35 or not (" " + title + " ") in (" " + title_region + " "):
        return None
    surnames = [_words(author).split()[-1] for author in citation.authors if _words(author)]
    region = " " + _words(header) + " "
    if not citation.year or not surnames:
        return None
    if (str(citation.year) in re.findall(r"\b\d{4}\b", header)
            and any(len(name) >= 3 and " " + name + " " in region for name in surnames)):
        return "title_author_year"
    return None


def accept_manual_pdf(doi: str, content: bytes) -> dict:
    normalized = normalize_doi(doi)
    if len(content) > source_max_size():
        raise ManualSourceError("FILE_TOO_LARGE", "The PDF exceeds the configured upload size limit.", 413)
    if not content or not content.startswith(b"%PDF-"):
        raise ManualSourceError("INVALID_PDF", "Select a non-empty, valid PDF file.")
    try:
        sections = parse_document(content, "pdf")
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted or not reader.pages:
            raise ValueError("Unsupported PDF")
        header = reader.pages[0].extract_text() or ""
        metadata = reader.metadata or {}
    except Exception as exc:
        raise ManualSourceError("INVALID_PDF", "The PDF could not be read. Upload a PDF with extractable text.") from exc
    try:
        citation = resolve_doi(normalized)
    except (CitationResolverError, CitationNotFoundError) as exc:
        raise ManualSourceError("METADATA_UNAVAILABLE", "The cited paper metadata could not be resolved. Try again later.", 503) from exc
    if normalize_doi(citation.doi) != normalized:
        raise ManualSourceError("METADATA_UNAVAILABLE", "The resolver returned a different paper identity.", 503)
    match = match_pdf_identity(normalized, citation, header, metadata)
    if match is None:
        raise ManualSourceError("SOURCE_MISMATCH", "The uploaded PDF does not appear to match DOI " + normalized + ".")
    paper = _build_paper_metadata(citation, None)
    paper.full_text_available = True
    paper.full_text_format = "pdf"
    # No fabricated remote URL for an uploaded file.
    paper.full_text_url = None
    chunks = chunk_sections(sections, paper.paper_id)
    if not chunks:
        raise ManualSourceError("INVALID_PDF", "The PDF contains no usable source text.")
    artifact = AcceptedSourceArtifact.create(
        doi=normalized, content=content, format="pdf", source_url=None,
        provider="manual_upload", origin="manual", paper=paper,
    )
    try:
        LocalSourceStore().put(artifact)
    except OSError as exc:
        raise ManualSourceError("SOURCE_STORE_FAILED", "The PDF could not be saved locally. Check the source cache directory.", 503) from exc
    logger.info("manual_source_accepted doi=%s match=%s", normalized, match)
    return {"status": "accepted", "doi": normalized,
            "raw_content_sha256": artifact.raw_content_sha256, "identity_match": match}


def accept_reference_pdf(reference, content: bytes) -> dict:
    """URL-only PDF association requires a substantive body and a strong title match."""
    from app.services.source_locator import reference_locator
    from app.services.source_acquisition import inspect_institutional, _url_association
    from app.services.source_identity import _title_relation
    from app.services.document_retriever import RetrievedDocument
    from app.researchguard.source_locator import SourceProvenance
    from app.schemas.paper import PaperMetadata
    locator = reference_locator(reference)
    if locator is None or locator.kind != 'url':
        raise ManualSourceError('SOURCE_URL_REQUIRED', 'A cited public URL is required.')
    if reference.resolution and reference.resolution.status != 'non_doi_source':
        raise ManualSourceError('SOURCE_IDENTITY_UNRESOLVED', 'Resolve the reference identity before uploading.')
    if len(content) > source_max_size():
        raise ManualSourceError('FILE_TOO_LARGE', 'The PDF exceeds the upload limit.', 413)
    try:
        if not content.startswith(b'%PDF-'):
            raise ValueError('Invalid PDF')
        sections = parse_document(content, 'pdf')
        document = RetrievedDocument(content, None, 'pdf', 'application/pdf', '')
        kind, identity, title, date = inspect_institutional(document, reference, locator)
    except Exception as exc:
        raise ManualSourceError('INVALID_PDF', 'Upload a readable PDF with extractable text.') from exc
    expected = _words(reference.title or '')
    if (kind != 'INSTITUTIONAL_DOCUMENT' or identity == 'IDENTITY_CONFLICT'
            or len(expected.split()) < 6 or len(expected) < 35
            or _title_relation(reference.title, title) != 'match'
            or not _url_association(reference, title, sections)):
        raise ManualSourceError('SOURCE_MISMATCH', 'The PDF cannot be reliably matched to this cited reference.')
    paper = PaperMetadata(paper_id=locator.key, title=title, authors=list(reference.authors),
        year=reference.year, publication_date=date, url=locator.value,
        full_text_available=True, full_text_format='pdf')
    if not chunk_sections(sections, paper.paper_id):
        raise ManualSourceError('INVALID_PDF', 'The PDF contains no usable full text.')
    provenance = SourceProvenance(original_citation=reference.raw_text, source_url=locator.value,
        identity='EXACT_IDENTITY', document_kind=kind, retrieved_title=title,
        match_evidence=('MANUAL_PDF_TITLE_MATCH',), warnings=('HISTORICAL_VERSION_UNCONFIRMED',))
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
            'raw_content_sha256': artifact.raw_content_sha256, 'identity_match': 'title'}
