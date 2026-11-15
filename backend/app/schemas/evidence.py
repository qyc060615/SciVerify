from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EvidenceRetrievalStatus(str, Enum):
    SUCCESS = "success"
    NO_CHUNKS = "no_chunks"
    NO_RELEVANT_EVIDENCE = "no_relevant_evidence"
    FULL_TEXT_UNAVAILABLE = "full_text_unavailable"
    METADATA_ONLY = "metadata_only"
    PARSING_FAILURE = "parsing_failure"
    NOT_FOUND = "not_found"
    PROVIDER_ERROR = "provider_error"


class EvidenceRetrievalRequest(BaseModel):
    claim: str
    doi: str


class EvidencePaperSummary(BaseModel):
    paper_id: str
    doi: str | None = None
    title: str | None = None


class EvidenceItem(BaseModel):
    chunk_id: str
    section: str
    chunk_index: int
    text: str
    relevance_score: float
    claim_overlap: float
    numeric_overlap: float
    claim_numbers: list[str] = Field(default_factory=list)
    evidence_numbers: list[str] = Field(default_factory=list)
    source_url: str | None = None
    page: int | None = None


class EvidenceRetrievalResponse(BaseModel):
    status: EvidenceRetrievalStatus
    claim: str
    paper: EvidencePaperSummary
    evidence: list[EvidenceItem] = Field(default_factory=list)
    total_chunks_considered: int = 0
    detail: str | None = None
