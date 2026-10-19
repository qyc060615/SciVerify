"""Local job contracts. Runtime state is separate from semantic domain status."""
from enum import Enum
import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from app.researchguard.domain import (
    DomainModel, Identifier, ParsedManuscript, ClaimExtractionResult, ProcessingStatus,
    AttributionStatus, ExtractionStatus,
)
from app.researchguard.manuscript_verification import AttributionBlockedClaim, PairOutcome, SourceBinding
from app.services.manuscript_verification import validate_combined_input, plan_manuscript_pairs
from app.utils.doi import normalize_doi
from app.researchguard.source_locator import SourceLocator
from app.services.source_locator import reference_locator

JobId = Annotated[str, StringConstraints(pattern=r"^job_[0-9a-f]{32}$")]
RawHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Count = Annotated[int, Field(strict=True, ge=0)]


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_SOURCE = "waiting_for_source"
    PARTIALLY_COMPLETED = "partially_completed"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED_SOURCE = "blocked_source"
    COMPLETED = "completed"
    FAILED = "failed"


def task_key(job_id, fingerprint, claim_id, reference_id):
    return "task_" + hashlib.sha256(json.dumps(
        [job_id, fingerprint, claim_id, reference_id], separators=(",", ":")).encode()).hexdigest()


class TaskRecord(DomainModel):
    task_key: Identifier
    claim_id: Identifier
    reference_id: Identifier
    state: TaskState = TaskState.PENDING
    reason_code: Identifier | None = None
    attempt: Count = 0
    expected_raw_hash: RawHash | None = None
    # Retain the pinned version even if a later conflict outcome has only a DOI binding.
    source_binding: SourceBinding | None = None
    pair_outcome: PairOutcome | None = None
    last_error_code: Identifier | None = None

    @property
    def source_version(self):
        return self.source_binding.source_version if self.source_binding else None

    @model_validator(mode="after")
    def validate_outcome(self):
        outcome = self.pair_outcome
        if self.state in {TaskState.COMPLETED, TaskState.BLOCKED_SOURCE, TaskState.FAILED} and outcome is None:
            raise ValueError("Terminal task requires a committed outcome")
        if outcome is not None:
            if outcome.claim_id != self.claim_id or outcome.reference_id != self.reference_id:
                raise ValueError("Task outcome identity mismatch")
            completed = outcome.processing_status == ProcessingStatus.COMPLETED
            if completed != (self.state == TaskState.COMPLETED):
                raise ValueError("Completed outcome cannot be rescheduled")
        if self.state != TaskState.PENDING and self.attempt == 0:
            raise ValueError("Executed task requires an attempt")
        return self


class EventRecord(DomainModel):
    job_id: JobId
    sequence: Annotated[int, Field(strict=True, ge=1)]
    event_type: Literal[
        "job_created", "job_started", "pair_started", "pair_completed", "pair_blocked_source",
        "pair_failed", "job_waiting_for_source", "job_partially_completed", "job_completed",
        "job_interrupted", "job_resumed", "job_failed",
    ]
    task_key: Identifier | None = None
    claim_id: Identifier | None = None
    reference_id: Identifier | None = None
    status: JobState | TaskState
    timestamp: Identifier
    reason_code: Identifier | None = None
    attempt: Count | None = None


class JobSnapshot(DomainModel):
    schema_version: Literal[1] = 1
    job_id: JobId
    revision: Count = 0
    input_fingerprint: Identifier
    parsed: ParsedManuscript
    extraction: ClaimExtractionResult
    state: JobState = JobState.PENDING
    tasks: tuple[TaskRecord, ...]
    attribution_blocked: tuple[AttributionBlockedClaim, ...]
    events: tuple[EventRecord, ...]
    next_sequence: Annotated[int, Field(strict=True, ge=1)]
    created_at: Identifier
    updated_at: Identifier

    @model_validator(mode="after")
    def validate_graph(self):
        validate_combined_input(self.parsed, self.extraction)
        if self.input_fingerprint != self.extraction.metadata.input_fingerprint:
            raise ValueError("Job fingerprint mismatch")
        plan, blocked = plan_manuscript_pairs(self.parsed, self.extraction)
        if [(t.claim_id, t.reference_id) for t in self.tasks] != [(c.id, r.id) for c, r, _ in plan]:
            raise ValueError("Job task plan mismatch")
        if self.attribution_blocked != blocked:
            raise ValueError("Job attribution coverage mismatch")
        keys = {t.task_key: t for t in self.tasks}
        if len(keys) != len(self.tasks):
            raise ValueError("Duplicate task key")
        completed_events = set()
        starts = {t.task_key: [] for t in self.tasks}
        last_pair_events = {}
        for t, (_, reference, calls) in zip(self.tasks, plan):
            if t.task_key != task_key(self.job_id, self.input_fingerprint, t.claim_id, t.reference_id):
                raise ValueError("Unstable task key")
            if t.pair_outcome and t.pair_outcome.citation_callout_ids != calls:
                raise ValueError("Task callout identity mismatch")
            if t.source_binding:
                if (t.source_binding.reference_id != t.reference_id
                        or (t.source_binding.locator or SourceLocator(kind='doi', value=t.source_binding.doi))
                        != reference_locator(reference)):
                    raise ValueError("Task source binding does not match its reference")
                version = t.source_version
                if version is not None and (not version.startswith("sha256:") or len(version) != 71
                        or any(c not in "0123456789abcdef" for c in version[7:])
                        or t.source_binding.source_document_id is None):
                    raise ValueError("Task source version is invalid")
                if version and t.expected_raw_hash and version != "sha256:" + t.expected_raw_hash:
                    raise ValueError("Task source version and raw hash disagree")
            outcome_binding = t.pair_outcome.binding if t.pair_outcome else None
            if outcome_binding and outcome_binding.source_version and t.source_binding != outcome_binding:
                raise ValueError("Task lost its committed source binding")
        if [e.sequence for e in self.events] != list(range(1, self.next_sequence)):
            raise ValueError("Nonmonotonic event sequence")
        if not self.events or self.events[0].event_type != "job_created":
            raise ValueError("Missing job creation event")
        for event in self.events:
            if event.job_id != self.job_id:
                raise ValueError("Foreign job event")
            if event.task_key is not None:
                task = keys.get(event.task_key)
                if task is None or (event.claim_id, event.reference_id) != (task.claim_id, task.reference_id):
                    raise ValueError("Foreign task event")
                if event.attempt is None or not 1 <= event.attempt <= task.attempt:
                    raise ValueError("Invalid event attempt")
            elif event.claim_id is not None or event.reference_id is not None or event.attempt is not None:
                raise ValueError("Taskless event has task metadata")
            pair_states = {"pair_started": TaskState.RUNNING, "pair_completed": TaskState.COMPLETED,
                "pair_blocked_source": TaskState.BLOCKED_SOURCE, "pair_failed": TaskState.FAILED}
            if event.event_type in pair_states and (event.task_key is None or event.status != pair_states[event.event_type]):
                raise ValueError("Pair event type and status disagree")
            if event.event_type in pair_states:
                last_pair_events[event.task_key] = event
            if event.event_type == "pair_started":
                starts[event.task_key].append(event.attempt)
            if event.event_type == "pair_completed":
                if event.task_key in completed_events or keys[event.task_key].state != TaskState.COMPLETED:
                    raise ValueError("Duplicate or uncommitted completion event")
                completed_events.add(event.task_key)
        if completed_events != {t.task_key for t in self.tasks if t.state == TaskState.COMPLETED}:
            raise ValueError("Completed tasks and events must commit together")
        for task in self.tasks:
            if starts[task.task_key] != list(range(1, task.attempt + 1)):
                raise ValueError("Attempt counter must match durable start events")
            if task.state != TaskState.PENDING:
                last = last_pair_events.get(task.task_key)
                if last is None or last.status != task.state or last.attempt != task.attempt:
                    raise ValueError("Task state must match its last durable event")
        if self.state == JobState.COMPLETED and aggregate_state(self) != JobState.COMPLETED:
            raise ValueError("Job completion hides a coverage gap")
        return self


class JobCoverage(DomainModel):
    total_claims: Count
    total_references: Count
    total_pairs: Count
    pending_pairs: Count
    running_pairs: Count
    completed_pairs: Count
    blocked_source_pairs: Count
    failed_pairs: Count
    ambiguous_claims: Count
    unresolved_claims: Count
    failed_extraction_contexts: Count
    skipped_extraction_contexts: Count
    coverage_complete: bool


def coverage(snapshot):
    states = [t.state for t in snapshot.tasks]
    extraction = snapshot.extraction
    return JobCoverage(total_claims=len(extraction.claims), total_references=len(snapshot.parsed.references),
        total_pairs=len(states), pending_pairs=states.count(TaskState.PENDING),
        running_pairs=states.count(TaskState.RUNNING), completed_pairs=states.count(TaskState.COMPLETED),
        blocked_source_pairs=states.count(TaskState.BLOCKED_SOURCE), failed_pairs=states.count(TaskState.FAILED),
        ambiguous_claims=sum(c.attribution_status == AttributionStatus.AMBIGUOUS for c in extraction.claims),
        unresolved_claims=sum(c.attribution_status == AttributionStatus.UNRESOLVED for c in extraction.claims),
        failed_extraction_contexts=sum(c.status == ExtractionStatus.FAILED for c in extraction.context_results),
        skipped_extraction_contexts=sum(c.status == ExtractionStatus.SKIPPED for c in extraction.context_results),
        coverage_complete=aggregate_state(snapshot) == JobState.COMPLETED)


def aggregate_state(snapshot):
    states = {t.state for t in snapshot.tasks}
    if states & {TaskState.PENDING, TaskState.RUNNING}:
        return JobState.RUNNING
    if TaskState.BLOCKED_SOURCE in states:
        return JobState.WAITING_FOR_SOURCE
    if (snapshot.tasks and states == {TaskState.COMPLETED} and not snapshot.attribution_blocked
            and snapshot.extraction.status == ExtractionStatus.COMPLETED
            and all(c.status == ExtractionStatus.COMPLETED for c in snapshot.extraction.context_results)):
        return JobState.COMPLETED
    return JobState.PARTIALLY_COMPLETED
