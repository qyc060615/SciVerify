"""Explicit M3A HTTP projection: no internal locator, bytes or parser objects."""
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.researchguard.domain import CitationCallout, ManuscriptDiagnostic, Paragraph, ParsedManuscript, Reference


class ManuscriptDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str | None = None
    content_hash: str | None = None


class ParsedManuscriptDTO(BaseModel):
    manuscript: ManuscriptDTO
    paragraphs: tuple[Paragraph, ...]
    references: tuple[Reference, ...]
    citation_callouts: tuple[CitationCallout, ...]
    citation_contexts: tuple = ()


class ManuscriptParseResponse(BaseModel):
    schema_version: Literal[1] = 1
    scope: Literal["body_prose"] = "body_prose"
    offset_unit: Literal["python_unicode_code_point"] = "python_unicode_code_point"
    status: Literal["completed", "partial"]
    parsed: ParsedManuscriptDTO
    diagnostics: tuple[ManuscriptDiagnostic, ...]

    @classmethod
    def from_domain(cls, parsed: ParsedManuscript):
        return cls(
            status="partial" if any(d.severity == "warning" for d in parsed.diagnostics) else "completed",
            parsed=ParsedManuscriptDTO(
                manuscript=ManuscriptDTO(id=parsed.manuscript.id, title=parsed.manuscript.title,
                                         content_hash=parsed.manuscript.content_hash),
                paragraphs=parsed.paragraphs, references=parsed.references,
                citation_callouts=parsed.citation_callouts,
            ), diagnostics=parsed.diagnostics,
        )
