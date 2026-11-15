"""M3A upload validation and application boundary; no source or LLM pipeline."""
from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Callable

from anyio import to_thread
from pypdf import PdfReader

from app.config import manuscript_max_size
from app.researchguard.domain import Manuscript, ParsedManuscript
from app.researchguard.ports import ManuscriptParser
from app.services.manuscript_errors import ManuscriptParseError

ParserFactory = Callable[[bytes, Manuscript], ManuscriptParser]


def create_parser(content: bytes, manuscript: Manuscript) -> ManuscriptParser:
    from app.researchguard.adapters.grobid import GrobidAdapter
    return GrobidAdapter(content, manuscript.content_locator)


def get_manuscript_limit() -> int:
    try:
        return manuscript_max_size()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ManuscriptParseError("GROBID_CONFIGURATION_ERROR", "Manuscript upload configuration is invalid.", 503) from exc


def validate_pdf(content: bytes, limit: int):
    if len(content) > limit:
        raise ManuscriptParseError("MANUSCRIPT_TOO_LARGE", "The manuscript PDF exceeds the upload size limit.", 413)
    if not content.startswith(b"%PDF-"):
        raise ManuscriptParseError("INVALID_MANUSCRIPT_PDF", "Upload a non-empty, valid PDF manuscript.", 400)
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted or not reader.pages:
            raise ValueError("Empty or encrypted PDF")
        # Basic structure preflight only; do not extract/normalize manuscript prose here.
        _ = reader.pages[0].mediabox
    except Exception as exc:
        raise ManuscriptParseError("INVALID_MANUSCRIPT_PDF", "The manuscript PDF could not be read or is encrypted.", 400) from exc


async def parse_manuscript(content: bytes, *, parser_factory: ParserFactory = create_parser,
                           limit: int | None = None) -> ParsedManuscript:
    await to_thread.run_sync(validate_pdf, content, limit if limit is not None else get_manuscript_limit())
    digest = hashlib.sha256(content).hexdigest()
    manuscript = Manuscript(id="manuscript:" + digest, content_hash="sha256:" + digest,
                            content_locator="memory:manuscript:" + digest)
    parser = parser_factory(content, manuscript)
    parsed = await parser.parse(manuscript)
    if (parsed.manuscript.id != manuscript.id or parsed.manuscript.content_hash != manuscript.content_hash
            or parsed.manuscript.content_locator != manuscript.content_locator or parsed.citation_contexts):
        raise ManuscriptParseError("MANUSCRIPT_PARSE_FAILED", "The parser returned inconsistent manuscript structure.")
    return parsed
