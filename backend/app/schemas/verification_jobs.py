"""Local job API schemas. Private locators never enter a response."""
from typing import Annotated, Literal

from pydantic import Field

from app.researchguard.domain import (
    DomainModel, ParsedManuscript, ClaimExtractionResult, AtomicClaim, Reference,
    Paragraph, CitationCallout, CitationContext, ClaimExtractionMetadata, ContextExtractionResult,
)
from app.researchguard.manuscript_verification import PairOutcome, AttributionBlockedClaim, SourceBinding
from app.services.verification_job_models import JobId, RawHash, Count, JobState, TaskState, JobCoverage, coverage


class JobCreateRequest(DomainModel):
    parsed: ParsedManuscript
    extraction: ClaimExtractionResult


class JobResumeRequest(DomainModel):
    expected_revision: Count
    reference_ids: Annotated[tuple[str, ...], Field(max_length=2000)] | None = None
    source_hashes: dict[str, RawHash] = Field(default_factory=dict)
    retry_failed: bool = False


class TaskView(DomainModel):
    task_key: str
    claim_id: str
    reference_id: str
    state: TaskState
    reason_code: str | None
    attempt: Count
    source_binding: SourceBinding | None
    source_version: str | None
    expected_raw_hash: RawHash | None
    last_error_code: str | None
    pair_outcome: PairOutcome | None
    resume_available: bool


class JobView(DomainModel):
    job_id: JobId
    status: JobState
    revision: Count
    input_provenance: Literal["client_supplied"] = "client_supplied"
    manuscript_id: str
    paragraphs: tuple[Paragraph, ...]
    claims: tuple[AtomicClaim, ...]
    references: tuple[Reference, ...]
    citation_callouts: tuple[CitationCallout, ...]
    contexts: tuple[CitationContext, ...]
    extraction_metadata: ClaimExtractionMetadata
    context_results: tuple[ContextExtractionResult, ...]
    tasks: tuple[TaskView, ...]
    attribution_blocked: tuple[AttributionBlockedClaim, ...]
    coverage: JobCoverage
    next_sequence: int
    runtime_error_code: str | None = None


def job_view(snapshot, max_attempts, *, runtime_error_code=None):
    from app.services.verification_jobs import RETRYABLE
    tasks = tuple(TaskView(task_key=t.task_key, claim_id=t.claim_id, reference_id=t.reference_id,
        state=t.state, reason_code=t.reason_code, attempt=t.attempt, source_binding=t.source_binding,
        source_version=t.source_version, expected_raw_hash=t.expected_raw_hash,
        last_error_code=t.last_error_code, pair_outcome=t.pair_outcome,
        resume_available=t.attempt < max_attempts and snapshot.state not in {JobState.RUNNING, JobState.FAILED}
            and (t.state in {TaskState.PENDING, TaskState.BLOCKED_SOURCE}
                 or (t.state == TaskState.FAILED and t.reason_code in RETRYABLE))) for t in snapshot.tasks)
    return JobView(job_id=snapshot.job_id, status=snapshot.state, revision=snapshot.revision,
        manuscript_id=snapshot.parsed.manuscript.id, paragraphs=snapshot.parsed.paragraphs,
        claims=snapshot.extraction.claims, references=snapshot.parsed.references,
        citation_callouts=snapshot.parsed.citation_callouts, contexts=snapshot.extraction.contexts,
        extraction_metadata=snapshot.extraction.metadata, context_results=snapshot.extraction.context_results,
        tasks=tasks, attribution_blocked=snapshot.attribution_blocked,
        coverage=coverage(snapshot), next_sequence=snapshot.next_sequence,
        runtime_error_code=runtime_error_code)
