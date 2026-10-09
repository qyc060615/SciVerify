"""Internal data contracts. No HTTP schemas or integration-specific objects.

IDs are opaque, nonblank strings. Pages are one-based; paragraph order is
zero-based. Adapters allocate IDs and normalize metadata before construction.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Page = Annotated[int, Field(strict=True, ge=1)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Verdict(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    OVERSTATED = "OVERSTATED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CITATION_UNRESOLVED = "citation_unresolved"
    SOURCE_UNAVAILABLE = "source_unavailable"
    SOURCE_MISMATCH = "source_mismatch"
    FAILED = "failed"


class RetrievalStatus(str, Enum):
    PENDING = "pending"
    AVAILABLE = "available"
    METADATA_ONLY = "metadata_only"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class SourceType(str, Enum):
    REMOTE = "remote"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class Manuscript(DomainModel):
    id: Identifier
    content_locator: Text
    title: str | None = None
    content_hash: str | None = None


class TextSpan(DomainModel):
    """Half-open Unicode code-point offsets into canonical Paragraph.text."""

    start: Annotated[int, Field(strict=True, ge=0)]
    end: Annotated[int, Field(strict=True, ge=0)]

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.end <= self.start:
            raise ValueError("TextSpan end must exceed start")
        return self


class CitationResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"


class ManuscriptDiagnostic(DomainModel):
    code: Identifier
    severity: Annotated[str, StringConstraints(pattern=r"^(info|warning)$")]
    entity_id: Identifier | None = None
    safe_message: Text


class Paragraph(DomainModel):
    id: Identifier
    manuscript_id: Identifier
    text: Text
    order: Annotated[int, Field(strict=True, ge=0)]
    page: Page | None = None
    section: str | None = None
    sentence_spans: tuple[TextSpan, ...] = ()

    @model_validator(mode="after")
    def validate_sentences(self) -> Self:
        previous_end = 0
        for span in self.sentence_spans:
            if span.end > len(self.text) or span.start < previous_end:
                raise ValueError("Sentence spans must be ordered, disjoint and inside paragraph")
            previous_end = span.end
        return self


class CitationCallout(DomainModel):
    id: Identifier
    manuscript_id: Identifier
    paragraph_id: Identifier
    text: Text
    # Empty means unresolved, never a fabricated reference ID.
    reference_ids: tuple[Identifier, ...] = ()
    page: Page | None = None
    # None only for backward-compatible M0/M1 fixtures, not M3 parser output.
    span: TextSpan | None = None
    order: Annotated[int, Field(strict=True, ge=0)] | None = None
    resolution_status: CitationResolutionStatus = CitationResolutionStatus.UNRESOLVED

    @model_validator(mode="before")
    @classmethod
    def default_resolution(cls, value):
        if isinstance(value, dict) and "resolution_status" not in value:
            value = {**value, "resolution_status": "resolved" if value.get("reference_ids") else "unresolved"}
        return value

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if len(set(self.reference_ids)) != len(self.reference_ids):
            raise ValueError("Duplicate callout reference IDs")
        if (self.resolution_status == CitationResolutionStatus.UNRESOLVED) != (not self.reference_ids):
            raise ValueError("Callout resolution status disagrees with reference links")
        return self


class Reference(DomainModel):
    id: Identifier
    manuscript_id: Identifier
    raw_text: Text
    doi: str | None = None
    title: str | None = None
    authors: tuple[str, ...] = ()
    year: int | None = None
    journal: str | None = None


class CitationContext(DomainModel):
    id: Identifier
    manuscript_id: Identifier
    paragraph_id: Identifier
    text: Text
    citation_callout_ids: tuple[Identifier, ...] = ()
    page: Page | None = None


class ParsedManuscript(DomainModel):
    """Parser output; validate identity links without prescribing TEI structure."""

    manuscript: Manuscript
    paragraphs: tuple[Paragraph, ...] = ()
    references: tuple[Reference, ...] = ()
    citation_callouts: tuple[CitationCallout, ...] = ()
    citation_contexts: tuple[CitationContext, ...] = ()
    diagnostics: tuple[ManuscriptDiagnostic, ...] = ()

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        collections = (self.paragraphs, self.references, self.citation_callouts, self.citation_contexts)
        for items in collections:
            if len({item.id for item in items}) != len(items):
                raise ValueError("Duplicate IDs within a manuscript collection")
            if any(item.manuscript_id != self.manuscript.id for item in items):
                raise ValueError("Manuscript identity mismatch")
        paragraphs = {item.id for item in self.paragraphs}
        paragraph_map = {item.id: item for item in self.paragraphs}
        if [item.order for item in self.paragraphs] != list(range(len(self.paragraphs))):
            raise ValueError("Paragraph order must match document sequence")
        references = {item.id for item in self.references}
        callouts = {item.id: item for item in self.citation_callouts}
        for callout in self.citation_callouts:
            if callout.paragraph_id not in paragraphs:
                raise ValueError("Callout references an unknown paragraph")
            if not set(callout.reference_ids) <= references:
                raise ValueError("Callout references an unknown reference")
            if callout.span is not None:
                text = paragraph_map[callout.paragraph_id].text
                if callout.span.end > len(text) or text[callout.span.start:callout.span.end] != callout.text:
                    raise ValueError("Callout span must exactly slice paragraph text")
        for context in self.citation_contexts:
            if context.paragraph_id not in paragraphs:
                raise ValueError("Context references an unknown paragraph")
            for callout_id in context.citation_callout_ids:
                callout = callouts.get(callout_id)
                if callout is None or callout.paragraph_id != context.paragraph_id:
                    raise ValueError("Context callout must belong to the same paragraph")
        return self


class AtomicClaim(DomainModel):
    id: Identifier
    manuscript_id: Identifier
    text: Text
    paragraph_id: Identifier
    context_id: Identifier
    citation_callout_ids: tuple[Identifier, ...] = ()
    reference_ids: tuple[Identifier, ...] = ()
    page: Page | None = None


class SourceDocument(DomainModel):
    id: Identifier
    reference_id: Identifier
    doi: str | None = None
    title: str | None = None
    authors: tuple[str, ...] = ()
    year: int | None = None
    # A local path, URI, or application storage key; this model performs no I/O.
    content_locator: Text | None = None
    content_hash: str | None = None
    source_type: SourceType = SourceType.UNKNOWN
    provider: str | None = None
    source_url: str | None = None
    retrieval_status: RetrievalStatus = RetrievalStatus.PENDING


class EvidenceChunk(DomainModel):
    id: Identifier
    source_document_id: Identifier
    text: Text
    page: Page | None = None
    section: str | None = None
    retrieval_score: Annotated[float, Field(allow_inf_nan=False)] | None = None
    source_url: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class VerificationTraceability(DomainModel):
    """Evidence links plus JSON metadata for engine-specific diagnostics.

    Provider objects must be normalized to JSON at the adapter boundary.
    """

    evidence_ids: tuple[Identifier, ...] = ()
    method: str | None = None
    warnings: tuple[str, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class VerificationResult(DomainModel):
    claim_id: Identifier
    processing_status: ProcessingStatus
    verdict: Verdict | None = None
    confidence: Probability | None = None
    evidence_chunks: tuple[EvidenceChunk, ...] = ()
    explanation: str | None = None
    traceability: VerificationTraceability = Field(default_factory=VerificationTraceability)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.processing_status == ProcessingStatus.COMPLETED:
            if self.verdict is None:
                raise ValueError("Completed verification requires a semantic verdict")
        elif self.verdict is not None or self.confidence is not None:
            raise ValueError("Incomplete processing cannot carry a semantic verdict or confidence")
        ids = {chunk.id for chunk in self.evidence_chunks}
        if len(ids) != len(self.evidence_chunks):
            raise ValueError("Duplicate evidence chunk IDs")
        if not set(self.traceability.evidence_ids) <= ids:
            raise ValueError("Traceability references evidence absent from the result")
        return self


class Job(DomainModel):
    """Job identity and state only; no queue or persistence implementation."""

    id: Identifier
    manuscript_id: Identifier
    status: ProcessingStatus = ProcessingStatus.PENDING
    detail: str | None = None


class JobEvent(DomainModel):
    job_id: Identifier
    sequence: Annotated[int, Field(strict=True, ge=0)]
    event_type: Text
    status: ProcessingStatus
    claim_id: Identifier | None = None
    detail: str | None = None
