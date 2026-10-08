from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class PaperRetrievalStatus(str, Enum):
    SUCCESS = "success"
    METADATA_ONLY = "metadata_only"
    FULL_TEXT_UNAVAILABLE = "full_text_unavailable"
    NOT_FOUND = "not_found"
    PROVIDER_ERROR = "provider_error"
    PARSING_FAILURE = "parsing_failure"


class PaperMetadata(BaseModel):
    paper_id: str
    doi: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    journal: str | None = None
    publisher: str | None = None
    publication_date: str | None = None
    year: int | None = None
    url: str | None = None
    source_url: str | None = None
    open_access: bool | None = None
    full_text_available: bool = False
    full_text_format: Literal["pdf", "html"] | None = None
    full_text_url: str | None = None


class DocumentSection(BaseModel):
    section_name: str
    text: str
    order: int


class EvidenceChunk(BaseModel):
    chunk_id: str
    paper_id: str
    section: str
    chunk_index: int
    text: str
    source_url: str | None = None
    page: int | None = None
    metadata: dict[str, Any] | None = None


class PaperSource(BaseModel):
    raw_content_sha256: str | None = None
    origin: Literal["remote", "manual"] = "remote"
    cache_hit: bool = False
    url: str | None = None
    provider: str


class RetrievePaperRequest(BaseModel):
    doi: str


class RetrievePaperResponse(BaseModel):
    status: PaperRetrievalStatus
    paper: PaperMetadata
    sections: list[DocumentSection] = Field(default_factory=list)
    chunks: list[EvidenceChunk] = Field(default_factory=list)
    source: PaperSource
    detail: str | None = None
