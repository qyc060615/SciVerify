"""Strict M3B input/proposal contracts. Quotes never undergo implicit trimming."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.researchguard.domain import (
    CitationCallout, CitationResolutionStatus, Paragraph, Reference, TextSpan,
)

ExactText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=2000)]
OpaqueID = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=512)]


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceQuote(StrictDTO):
    quote: ExactText
    role: Literal["predicate", "subject", "qualifier", "shared_subject"] = "predicate"
    left_anchor: Annotated[str, StringConstraints(strict=True, max_length=200)] | None = None
    right_anchor: Annotated[str, StringConstraints(strict=True, max_length=200)] | None = None


class ClaimProposal(StrictDTO):
    text: ExactText
    source_quotes: Annotated[tuple[SourceQuote, ...], Field(min_length=1, max_length=8)]
    citation_callout_ids: Annotated[tuple[OpaqueID, ...], Field(max_length=2000)] = ()
    association: Literal["proposed", "abstain"] = "proposed"
    reason_code: Literal["UNCLEAR_SCOPE", "INCOMPLETE_TARGET", "NOT_FACTUAL"] | None = None


class ExtractionProposal(StrictDTO):
    claims: Annotated[tuple[ClaimProposal, ...], Field(max_length=8)]


class ManuscriptInput(StrictDTO):
    id: OpaqueID
    title: Annotated[str, StringConstraints(strict=True, max_length=2000)] | None = None
    content_hash: Annotated[str, StringConstraints(strict=True, max_length=128)] | None = None

    @field_validator("id")
    @classmethod
    def canonical_id(cls, value):
        if value != value.strip():
            raise ValueError("Noncanonical identifier")
        return value


class ParagraphInput(Paragraph):
    text: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200000)]

    @field_validator("text")
    @classmethod
    def canonical_text(cls, value):
        if value != value.strip():
            raise ValueError("Canonical paragraph text must not be trimmed implicitly")
        return value


class CalloutInput(CitationCallout):
    text: ExactText
    span: TextSpan
    order: Annotated[int, Field(strict=True, ge=0)]
    resolution_status: CitationResolutionStatus

    @model_validator(mode="before")
    @classmethod
    def explicit_occurrence(cls, value):
        if not isinstance(value, dict) or not {"span", "order", "resolution_status"} <= value.keys():
            raise ValueError("Explicit occurrence contract is required")
        return value


class ParsedInput(StrictDTO):
    manuscript: ManuscriptInput
    paragraphs: Annotated[tuple[ParagraphInput, ...], Field(max_length=1000)]
    references: Annotated[tuple[Reference, ...], Field(max_length=2000)]
    citation_callouts: Annotated[tuple[CalloutInput, ...], Field(max_length=2000)]
    citation_contexts: Annotated[tuple, Field(max_length=0)] = ()

    @model_validator(mode="before")
    @classmethod
    def unchanged_identifiers(cls, value):
        if isinstance(value, dict):
            for name in ("paragraphs", "references", "citation_callouts"):
                collection = value.get(name, ())
                if not isinstance(collection, (list, tuple)):
                    continue
                for item in collection:
                    if not isinstance(item, dict):
                        continue
                    ids = [item.get(k) for k in ("id", "manuscript_id", "paragraph_id") if k in item]
                    targets = item.get("reference_ids", ())
                    if isinstance(targets, (list, tuple)):
                        ids += list(targets)
                    if any(not isinstance(i, str) or i != i.strip() or not i or len(i) > 512 for i in ids):
                        raise ValueError("Noncanonical identifier")
        return value


class ClaimExtractionRequest(StrictDTO):
    schema_version: Literal[1]
    scope: Literal["body_prose"]
    offset_unit: Literal["python_unicode_code_point"]
    parsed: ParsedInput

    @model_validator(mode="before")
    @classmethod
    def exact_version(cls, value):
        if isinstance(value, dict) and type(value.get("schema_version")) is not int:
            raise ValueError("Schema version must be an integer")
        return value
