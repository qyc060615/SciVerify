"""Small, serializable M4 outcomes; original entities use the existing domain."""
from typing import Literal

from pydantic import model_validator, model_serializer
from .source_locator import SourceLocator, SourceProvenance

from .domain import (
    DomainModel, Identifier, ParsedManuscript, ClaimExtractionResult,
    ProcessingStatus, SourceDocument, VerificationResult,
)


class SourceBinding(DomainModel):
    reference_id: Identifier
    doi: Identifier | None = None
    source_document_id: Identifier | None = None
    source_version: str | None = None
    locator: SourceLocator | None = None
    provenance: SourceProvenance | None = None

    @model_serializer(mode='wrap')
    def legacy_projection(self, handler):
        data = handler(self)
        for key in ('locator', 'provenance'):
            if data.get(key) is None:
                data.pop(key, None)
        return data

    @model_validator(mode='after')
    def validate_locator(self):
        if self.locator is None:
            if not self.doi:
                raise ValueError('Source binding needs a DOI or locator')
        elif self.doi != (self.locator.value if self.locator.kind == 'doi' else None):
            raise ValueError('Source binding DOI and locator disagree')
        return self


class PairOutcome(DomainModel):
    reference_id: Identifier
    citation_callout_ids: tuple[Identifier, ...]
    reason_code: Identifier
    binding: SourceBinding | None = None
    verification: VerificationResult
    # Raw engine provenance, deliberately independent of legacy HTTP schemas.
    legacy_verdict: Literal["SUPPORTS", "OVERSTATED", "CONTRADICTS", "INSUFFICIENT", "FABRICATED"] | None = None

    @model_validator(mode="after")
    def validate_pair(self):
        if self.binding is not None:
            if self.binding.reference_id != self.reference_id:
                raise ValueError("Pair binding references another manuscript reference")
            if any(c.source_document_id != self.binding.source_document_id for c in self.verification.evidence_chunks):
                raise ValueError("Pair evidence must belong to its bound source")
        if (self.verification.processing_status == ProcessingStatus.COMPLETED) != (self.legacy_verdict is not None):
            raise ValueError("Only completed pairs carry a legacy semantic verdict")
        return self

    @property
    def claim_id(self):
        return self.verification.claim_id

    @property
    def processing_status(self):
        return self.verification.processing_status


class AttributionBlockedClaim(DomainModel):
    claim_id: Identifier
    processing_status: ProcessingStatus = ProcessingStatus.CITATION_UNRESOLVED
    reason_code: Identifier


class CoreCoverage(DomainModel):
    claims: int
    references: int
    pairs: int
    completed: int
    blocked: int
    failed: int
    unresolved_claims: int
    ambiguous_claims: int
    failed_contexts: int
    skipped_contexts: int
    coverage_complete: bool


class ManuscriptCoreResult(DomainModel):
    parsed: ParsedManuscript
    extraction: ClaimExtractionResult
    sources: tuple[SourceDocument, ...]
    pairs: tuple[PairOutcome, ...]
    attribution_blocked: tuple[AttributionBlockedClaim, ...]
    coverage: CoreCoverage
