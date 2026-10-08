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
