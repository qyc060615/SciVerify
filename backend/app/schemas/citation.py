from typing import Literal

from pydantic import BaseModel, Field


class CitationMetadata(BaseModel):
    doi: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    journal: str | None = None
    publisher: str | None = None
    year: int | None = None
    url: str | None = None
    source: Literal["crossref", "openalex", "semantic_scholar"]
    type: str | None = None


class ResolveCitationRequest(BaseModel):
    doi: str
