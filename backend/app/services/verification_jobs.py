"""Managed single-process workers and explicit selective resume for local jobs."""
import asyncio
from datetime import datetime, timezone
import hashlib
import os
from uuid import uuid4

from anyio import to_thread

from app.researchguard.domain import ProcessingStatus, VerificationResult
from app.researchguard.manuscript_verification import PairOutcome
from app.services.manuscript_verification import (
    verify_manuscript_core, validate_combined_input, plan_manuscript_pairs,
)
from app.services.source_store import LocalSourceStore, verify_source_durability
from app.services.verification_job_models import (
    JobSnapshot, TaskRecord, TaskState, JobState, EventRecord, task_key, aggregate_state,
)
from app.services.verification_job_store import LocalJobStore, JobError, positive_setting
from app.utils.doi import normalize_doi
from app.services.source_locator import reference_locator

RETRYABLE = frozenset({"VERIFIER_EXECUTION_FAILURE", "VERIFIER_LLM_UNAVAILABLE",
    "VERIFIER_VERIFICATION_FAILED", "PAPERQA2_ADAPTER_FAILURE", "EVIDENCE_RETRIEVAL_FAILURE",
    "SOURCE_PROVIDER_ERROR", "SOURCE_PREPARATION_FAILURE", "SOURCE_DURABILITY_UNAVAILABLE",
    "SOURCE_DURABILITY_MISMATCH", "SOURCE_DURABILITY_HASH_REQUIRED"})
RECOVERABLE_SOURCE = frozenset({"SOURCE_REQUIRED_METADATA_ONLY", "SOURCE_REQUIRED_FULL_TEXT_UNAVAILABLE",
    "SOURCE_REQUIRED_PARSING_FAILURE", "SOURCE_NOT_FOUND", "SOURCE_DOI_MISMATCH", "SOURCE_VERSION_CONFLICT",
    'SOURCE_IDENTITY_CONFLICT', 'SOURCE_IDENTITY_UNCERTAIN', 'SOURCE_VERSION_UNCONFIRMED'})


def jobs_enabled():
    return os.getenv("RESEARCHGUARD_JOBS_ENABLED", "0") == "1"


def require_single_process():
    for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS", "RESEARCHGUARD_JOB_PROCESSES"):
        if positive_setting(name, 1) != 1:
            raise JobError("JOB_MULTIPROCESS_UNSUPPORTED", 503)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def evolve(snapshot, event_type, state, *, tasks=None, task=None, reason=None):
    now = timestamp()
    event = EventRecord(job_id=snapshot.job_id, sequence=snapshot.next_sequence,
        event_type=event_type, status=task.state if task else state, timestamp=now,
        task_key=task.task_key if task else None, claim_id=task.claim_id if task else None,
        reference_id=task.reference_id if task else None, reason_code=reason,
        attempt=task.attempt if task else None)
    return snapshot.model_copy(update={"revision": snapshot.revision + 1, "state": state,
        "tasks": tuple(tasks) if tasks is not None else snapshot.tasks,
        "events": snapshot.events + (event,), "next_sequence": snapshot.next_sequence + 1,
        "updated_at": now})


class VerificationJobRuntime:
    def __init__(self, store=None, *, source_store=None, core_dependencies=None, max_workers=2):
        self.store = store or LocalJobStore()
        self.source_store = source_store or LocalSourceStore()
        self.core_dependencies = dict(core_dependencies or {})
        if self.core_dependencies.keys() & {"selected_pairs", "on_pair_started", "on_pair_finished",
                "expected_raw_hashes", "expected_source_versions", "source_durability_check"}:
            raise JobError("JOB_CONFIGURATION_INVALID", 503)
        if type(max_workers) is not int or max_workers <= 0:
            raise JobError("JOB_CONFIGURATION_INVALID", 503)
        self._semaphore = asyncio.Semaphore(max_workers)
        self._locks, self._workers, self.errors = {}, {}, {}
        self._closing = False

    def _lock(self, job_id):
        # Unknown IDs cannot create an unbounded collection of in-memory locks.
        if job_id not in self._locks:
            self.store.load(job_id)
        return self._locks.setdefault(job_id, asyncio.Lock())

    async def start(self):
        require_single_process()
        for job_id in self.store.list_job_ids():
            async with self._lock(job_id):
                snapshot = self.store.load(job_id)
                if snapshot.state == JobState.RUNNING or any(t.state == TaskState.RUNNING for t in snapshot.tasks):
                    self._interrupt(snapshot)
        # Recovery deliberately schedules nothing and initializes no providers.

    def _interrupt(self, snapshot):
        tasks = list(snapshot.tasks)
        plan, _ = plan_manuscript_pairs(snapshot.parsed, snapshot.extraction)
        # An exhausted interrupted attempt becomes a processing failure, never a verdict.
        exhausted = []
        for i, task in enumerate(tasks):
            if task.state != TaskState.RUNNING:
                continue
            if task.attempt >= self.store.limits.max_attempts:
                reason = "PROCESS_INTERRUPTED_RETRY_LIMIT"
                old = task.pair_outcome
                outcome = PairOutcome(reference_id=task.reference_id, citation_callout_ids=plan[i][2],
                    reason_code=reason, binding=task.source_binding, verification=VerificationResult(
                        claim_id=task.claim_id, processing_status=ProcessingStatus.FAILED,
                        evidence_chunks=old.verification.evidence_chunks if old else ()))
                tasks[i] = task.model_copy(update={"state": TaskState.FAILED, "reason_code": reason,
                    "last_error_code": reason, "pair_outcome": outcome})
                exhausted.append(tasks[i])
            else:
                tasks[i] = task.model_copy(update={"state": TaskState.PENDING,
                    "reason_code": "PROCESS_INTERRUPTED", "last_error_code": "PROCESS_INTERRUPTED"})
        tasks = tuple(tasks)
        candidate = snapshot.model_copy(update={"tasks": tasks})
        state = JobState.INTERRUPTED if any(t.state == TaskState.PENDING for t in tasks) else aggregate_state(candidate)
        event_type = "job_interrupted" if state == JobState.INTERRUPTED else "job_" + state.value
        updated = evolve(snapshot, event_type, state, tasks=tasks, reason="PROCESS_INTERRUPTED")
        # All exhausted outcomes and their events are included in this same atomic revision.
        for task in exhausted:
            now = timestamp()
            event = EventRecord(job_id=snapshot.job_id, sequence=updated.next_sequence,
                event_type="pair_failed", status=TaskState.FAILED, timestamp=now, task_key=task.task_key,
                claim_id=task.claim_id, reference_id=task.reference_id, attempt=task.attempt, reason_code=task.reason_code)
            updated = updated.model_copy(update={"events": updated.events + (event,),
                "next_sequence": updated.next_sequence + 1})
        return self.store.commit(updated, expected_revision=snapshot.revision)

    async def create(self, parsed, extraction):
        if self._closing:
            raise JobError("JOB_RUNTIME_STOPPING", 503)
        parsed, extraction = validate_combined_input(parsed, extraction)
        plan, blocked = plan_manuscript_pairs(parsed, extraction)
        job_id, now = "job_" + uuid4().hex, timestamp()
        fingerprint = extraction.metadata.input_fingerprint
        tasks = tuple(TaskRecord(task_key=task_key(job_id, fingerprint, c.id, r.id),
            claim_id=c.id, reference_id=r.id) for c, r, _ in plan)
        snapshot = JobSnapshot(job_id=job_id, input_fingerprint=fingerprint, parsed=parsed,
            extraction=extraction, tasks=tasks, attribution_blocked=blocked,
            events=(EventRecord(job_id=job_id, sequence=1, event_type="job_created",
                status=JobState.PENDING, timestamp=now),), next_sequence=2, created_at=now, updated_at=now)
        self.store.create(snapshot)
        async with self._lock(job_id):
            return self._schedule(snapshot, tasks, "job_started")

    def _schedule(self, snapshot, tasks, event_type):
        if self._closing:
            raise JobError("JOB_RUNTIME_STOPPING", 503)
        if snapshot.job_id in self._workers:
            raise JobError("JOB_RUNNING")
        selected = tuple((t.claim_id, t.reference_id) for t in tasks if t.state == TaskState.PENDING)
        updated = self.store.commit(evolve(snapshot, event_type, JobState.RUNNING, tasks=tasks),
                                    expected_revision=snapshot.revision)
        # Registry ownership is assigned while the job lock is held; exceptions are managed below.
        self._workers[snapshot.job_id] = asyncio.create_task(self._worker(snapshot.job_id, selected),
                                                          name="verification-" + snapshot.job_id)
        self.errors.pop(snapshot.job_id, None)
        return updated

    def _check_source_durability(self, response):
        # Legacy injected fixtures without raw-byte provenance keep the Phase 1 contract.
        # Every response claiming a raw hash is checked, including injected retrievers.
        injected = "source_retriever" in self.core_dependencies
        verify_source_durability(response, self.source_store, allow_legacy=injected)

    def get(self, job_id):
        # A worker error never hides committed data or masks snapshot corruption.
        return self.store.load(job_id)

    async def wait(self, job_id):
        task = self._workers.get(job_id)
        if task:
            await task
        snapshot = self.get(job_id)
        if job_id in self.errors:
            raise JobError(self.errors[job_id], 503)
        return snapshot

    async def resume(self, job_id, *, expected_revision, reference_ids=None, source_hashes=None, retry_failed=False):
        async with self._lock(job_id):
            if self._closing:
                raise JobError("JOB_RUNTIME_STOPPING", 503)
            snapshot = self.store.load(job_id)
            references = {r.id: r for r in snapshot.parsed.references}
            requested = set(reference_ids) if reference_ids is not None else set(references)
            hashes = source_hashes or {}
            duplicates = reference_ids is not None and len(requested) != len(reference_ids)
            if duplicates or not requested <= references.keys() or not hashes.keys() <= references.keys():
                raise JobError("JOB_REFERENCE_UNKNOWN", 422)
            if snapshot.revision != expected_revision:
                raise JobError("JOB_REVISION_CONFLICT")
            if job_id in self._workers:
                raise JobError("JOB_RUNNING")
            if snapshot.state == JobState.COMPLETED:
                return snapshot
            if snapshot.state == JobState.FAILED:
                raise JobError("JOB_RESUME_UNAVAILABLE")
            selected = [t for t in snapshot.tasks if t.reference_id in requested and
                (t.state in {TaskState.PENDING, TaskState.BLOCKED_SOURCE} or
                 (t.state == TaskState.FAILED and retry_failed and t.reason_code in RETRYABLE))]
            if not selected:
                raise JobError("JOB_RESUME_UNAVAILABLE")
            if any(t.attempt >= self.store.limits.max_attempts for t in selected):
                raise JobError("JOB_RETRY_LIMIT")
            accepted, updates, doi_versions = {}, {}, {}
            for task in selected:
                try:
                    locator = reference_locator(references[task.reference_id])
                    if locator is None:
                        raise ValueError('No recoverable locator')
                    doi = locator.key
                except (ValueError, AttributeError):
                    # Unstarted work can still lack a locator after interruption.
                    # Let core classify it (e.g. DOI_MISSING), as on initial run;
                    # it must not prevent all other pending pairs from resuming.
                    if (task.state != TaskState.PENDING or task.source_version is not None
                            or task.expected_raw_hash is not None or task.reference_id in hashes):
                        raise JobError("JOB_SOURCE_NOT_RECOVERABLE") from None
                    updates[task.task_key] = task.model_copy(update={"reason_code": "RESUME_REQUESTED"})
                    continue
                expected = hashes.get(task.reference_id) or task.expected_raw_hash
                if task.source_version is not None:
                    if doi in doi_versions and doi_versions[doi] != task.source_version:
                        raise JobError("JOB_SOURCE_VERSION_CONFLICT")
                    doi_versions[doi] = task.source_version
                if task.state == TaskState.BLOCKED_SOURCE and not expected:
                    raise JobError("JOB_SOURCE_HASH_REQUIRED", 422)
                if expected is not None:
                    if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
                        raise JobError("JOB_SOURCE_HASH_INVALID", 422)
                    if doi not in accepted:
                        accepted[doi] = await to_thread.run_sync(self.source_store.get_locator, locator)
                    artifact = accepted[doi]
                    if artifact is None:
                        raise JobError("JOB_SOURCE_NOT_ACCEPTED")
                    if (artifact.source_locator != locator
                            or artifact.raw_content_sha256 != expected
                            or hashlib.sha256(artifact.content).hexdigest() != expected
                            or (task.expected_raw_hash is not None and task.expected_raw_hash != expected)
                            or (task.source_version is not None and task.source_version != "sha256:" + expected)):
                        raise JobError("JOB_SOURCE_VERSION_CONFLICT")
                updates[task.task_key] = task.model_copy(update={"state": TaskState.PENDING,
                    "reason_code": "RESUME_REQUESTED", "expected_raw_hash": expected})
            tasks = tuple(updates.get(t.task_key, t) for t in snapshot.tasks)
            if self._closing:
                raise JobError("JOB_RUNTIME_STOPPING", 503)
            # Selection must remain explicit; unrelated pending tasks are not scheduled.
            updated = self.store.commit(evolve(snapshot, "job_resumed", JobState.RUNNING, tasks=tasks),
                                        expected_revision=snapshot.revision)
            self._workers[job_id] = asyncio.create_task(self._worker(job_id,
                tuple((t.claim_id, t.reference_id) for t in selected)), name="verification-" + job_id)
            return updated

    async def _worker(self, job_id, selected):
        attempts = {}
        try:
            async with self._semaphore:
                snapshot = self.store.load(job_id)
                expectations, versions = {}, {}
                references = {r.id: r for r in snapshot.parsed.references}
                for t in snapshot.tasks:
                    if (t.claim_id, t.reference_id) not in selected:
                        continue
                    if t.expected_raw_hash or t.source_version:
                        locator = reference_locator(references[t.reference_id])
                        if locator is None:
                            raise JobError('JOB_SOURCE_NOT_RECOVERABLE')
                        doi = locator.key
                        for mapping, value in ((expectations, t.expected_raw_hash), (versions, t.source_version)):
                            if value is not None:
                                if doi in mapping and mapping[doi] != value:
                                    raise JobError("JOB_SOURCE_VERSION_CONFLICT")
                                mapping[doi] = value

                async def started(claim_id, reference_id):
                    async with self._lock(job_id):
                        current = self.store.load(job_id)
                        task = next(t for t in current.tasks if (t.claim_id, t.reference_id) == (claim_id, reference_id))
                        if task.state != TaskState.PENDING or task.attempt >= self.store.limits.max_attempts:
                            raise JobError("JOB_ATTEMPT_CONFLICT")
                        running = task.model_copy(update={"state": TaskState.RUNNING, "attempt": task.attempt + 1,
                            "reason_code": None})
                        tasks = tuple(running if t.task_key == task.task_key else t for t in current.tasks)
                        self.store.commit(evolve(current, "pair_started", JobState.RUNNING, tasks=tasks, task=running),
                                          expected_revision=current.revision)
                        attempts[task.task_key] = running.attempt

                async def finished(outcome):
                    async with self._lock(job_id):
                        current = self.store.load(job_id)
                        task = next(t for t in current.tasks if (t.claim_id, t.reference_id) == (outcome.claim_id, outcome.reference_id))
                        if task.state != TaskState.RUNNING or task.attempt != attempts.get(task.task_key):
                            raise JobError("JOB_STALE_ATTEMPT")
                        if outcome.processing_status == ProcessingStatus.COMPLETED:
                            state, event = TaskState.COMPLETED, "pair_completed"
                        elif outcome.reason_code in RECOVERABLE_SOURCE:
                            state, event = TaskState.BLOCKED_SOURCE, "pair_blocked_source"
                        else:
                            state, event = TaskState.FAILED, "pair_failed"
                        digest = task.expected_raw_hash
                        if outcome.binding and outcome.binding.source_version and any(
                                c.metadata.get("content_hash_kind") == "raw_bytes" for c in outcome.verification.evidence_chunks):
                            digest = outcome.binding.source_version.removeprefix("sha256:")
                        terminal = task.model_copy(update={"state": state, "reason_code": outcome.reason_code,
                            "pair_outcome": outcome, "expected_raw_hash": digest,
                            "source_binding": outcome.binding if outcome.binding and outcome.binding.source_version
                                else task.source_binding or outcome.binding,
                            "last_error_code": None if state == TaskState.COMPLETED else outcome.reason_code})
                        tasks = tuple(terminal if t.task_key == task.task_key else t for t in current.tasks)
                        self.store.commit(evolve(current, event, JobState.RUNNING, tasks=tasks, task=terminal,
                            reason=outcome.reason_code), expected_revision=current.revision)

                await verify_manuscript_core(snapshot.parsed, snapshot.extraction, selected_pairs=selected,
                    on_pair_started=started, on_pair_finished=finished, expected_raw_hashes=expectations,
                    expected_source_versions=versions, source_durability_check=self._check_source_durability,
                    **self.core_dependencies)
                async with self._lock(job_id):
                    current = self.store.load(job_id)
                    state = aggregate_state(current)
                    # A reference-filtered resume can leave unrelated pending work.
                    if state == JobState.RUNNING:
                        state, event = JobState.INTERRUPTED, "job_interrupted"
                    else:
                        event = "job_" + state.value
                    self.store.commit(evolve(current, event, state), expected_revision=current.revision)
                    # Clear execution diagnostics only after a successful recovery checkpoint.
                    self.errors.pop(job_id, None)
        except asyncio.CancelledError:
            async with self._lock(job_id):
                try:
                    self._interrupt(self.store.load(job_id))
                except JobError as exc:
                    self.errors[job_id] = exc.code
            raise
        except JobError as exc:
            # Includes storage errors propagated by core callbacks. Never create a pair verdict.
            self.errors[job_id] = exc.code
            async with self._lock(job_id):
                try:
                    self._interrupt(self.store.load(job_id))
                except JobError:
                    pass
        except Exception:
            async with self._lock(job_id):
                try:
                    current = self.store.load(job_id)
                    if any(t.state == TaskState.RUNNING for t in current.tasks):
                        current = self._interrupt(current)
                    self.store.commit(evolve(current, "job_failed", JobState.FAILED,
                        reason="JOB_WORKER_FAILURE"), expected_revision=current.revision)
                except JobError as exc:
                    self.errors[job_id] = exc.code
        finally:
            async with self._lock(job_id):
                if self._workers.get(job_id) is asyncio.current_task():
                    del self._workers[job_id]

    async def shutdown(self, timeout=30):
        self._closing = True
        workers = tuple(self._workers.values())
        if workers:
            _, pending = await asyncio.wait(workers, timeout=timeout)
            for task in pending:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
