"""Async integration ports; external I/O is awaited by application services."""
from typing import Protocol

from .domain import AtomicClaim, EvidenceChunk, Manuscript, ParsedManuscript, SourceDocument


class EvidenceRetriever(Protocol):
    async def retrieve(
        self, claim: AtomicClaim, source_document: SourceDocument, top_k: int
    ) -> list[EvidenceChunk]:
        """Return at most top_k ranked chunks from this source; top_k must be positive.

        The adapter loads content through the source locator, keeps chunk IDs
        stable, and sets source_document_id on every returned chunk. Empty
        results mean no relevant evidence, not a source-resolution failure.
        Translate external failures to application errors; do not invent verdicts.
        """
        ...


class ManuscriptParser(Protocol):
    async def parse(self, manuscript: Manuscript) -> ParsedManuscript:
        """Read the locator and return structure preserving manuscript identity.

        Paragraph order is zero-based and pages are one-based when known.
        Keep unresolved callouts with empty reference_ids. No TEI nodes or
        external parser schema may escape this boundary.
        """
        ...
