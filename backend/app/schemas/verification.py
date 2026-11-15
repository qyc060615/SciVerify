from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.evidence import EvidenceItem, EvidencePaperSummary


class Verdict(str, Enum):
    SUPPORTS = "SUPPORTS"
    OVERSTATED = "OVERSTATED"
    CONTRADICTS = "CONTRADICTS"
    INSUFFICIENT = "INSUFFICIENT"
    FABRICATED = "FABRICATED"


class VerificationStatus(str, Enum):
    SOURCE_REQUIRED = "source_required"
    SUCCESS = "success"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    LLM_UNAVAILABLE = "llm_unavailable"
    VERIFICATION_FAILED = "verification_failed"
    NOT_FOUND = "not_found"
    PROVIDER_ERROR = "provider_error"


class LiveFailureCategory(str, Enum):
    DOI_NOT_FOUND = "doi_not_found"
    FULL_TEXT_UNAVAILABLE = "full_text_unavailable"
    ANTI_BOT_BLOCKED = "anti_bot_blocked"
    PAYWALLED = "paywalled"
    HTTP_403 = "http_403"
    HTTP_404 = "http_404"
    RATE_LIMITED = "rate_limited"
    INVALID_DOCUMENT = "invalid_document"
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_ERROR = "network_error"
    LLM_FAILURE = "llm_failure"
    LLM_QUOTA_EXCEEDED = "llm_quota_exceeded"
    LLM_TIMEOUT = "llm_timeout"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN_FAILURE = "unknown_failure"


class VerificationAnalyzeRequest(BaseModel):
    claim: str
    doi: str


class AgentEvidenceReference(BaseModel):
    chunk_id: str
    rationale: str | None = None


class ProsecutorAnalysis(BaseModel):
    agent: Literal["prosecutor"] = "prosecutor"
    analysis: str
    stance: str
    key_points: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    confidence: float

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, value))


class DefenderAnalysis(BaseModel):
    agent: Literal["defender"] = "defender"
    analysis: str
    stance: str
    key_points: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    confidence: float

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, value))


class AdjudicatorAnalysis(BaseModel):
    agent: Literal["adjudicator"] = "adjudicator"
    analysis: str
    verdict: Verdict
    confidence: float
    reasoning: str
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    suggested_correction: str | None = None

    @field_validator("verdict", mode="before")
    @classmethod
    def normalize_verdict(cls, value: object) -> object:
        """Normalize LLM-returned verdict strings to uppercase before enum parsing.

        Some LLMs return lowercase (e.g. "supports") or mixed-case (e.g.
        "Supports") values.  Uppercasing before Pydantic resolves the enum
        prevents a validation error that would otherwise crash the pipeline.
        """
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, value))


class ClaimSegmentStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"


class ClaimSegmentTrace(BaseModel):
    id: str
    text: str
    status: ClaimSegmentStatus
    coverage_score: float
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("coverage_score")
    @classmethod
    def clamp_coverage(cls, value: float) -> float:
        return max(0.0, min(1.0, value))


class ClaimTraceability(BaseModel):
    segments: list[ClaimSegmentTrace] = Field(default_factory=list)
    overall_coverage: float = 0.0
    warnings: list[str] = Field(default_factory=list)

    @field_validator("overall_coverage")
    @classmethod
    def clamp_overall_coverage(cls, value: float) -> float:
        return max(0.0, min(1.0, value))


class SourceRecovery(BaseModel):
    required: Literal[True] = True
    reason: Literal["full_text_unavailable", "metadata_only", "parsing_failure"]
    accepts_manual_pdf: Literal[True] = True
    max_size_bytes: int


class VerificationResponse(BaseModel):
    source_recovery: SourceRecovery | None = None
    status: VerificationStatus
    claim: str
    verdict: Verdict | None = None
    confidence: float | None = None
    summary: str | None = None
    reasoning: str | None = None
    paper: EvidencePaperSummary
    evidence: list[EvidenceItem] = Field(default_factory=list)
    prosecutor: ProsecutorAnalysis | None = None
    defender: DefenderAnalysis | None = None
    adjudicator: AdjudicatorAnalysis | None = None
    suggested_correction: str | None = None
    agent_agreement: bool | None = None
    validation_warnings: list[str] | None = None
    claim_traceability: ClaimTraceability | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def validate_source_recovery(self):
        if self.status == VerificationStatus.SOURCE_REQUIRED:
            if (self.source_recovery is None or self.verdict is not None
                    or self.confidence is not None or self.adjudicator is not None
                    or self.prosecutor is not None or self.defender is not None
                    or self.claim_traceability is not None or self.evidence):
                raise ValueError("Source recovery cannot carry a semantic assessment")
        elif self.source_recovery is not None:
            raise ValueError("Source recovery requires source_required status")
        return self
