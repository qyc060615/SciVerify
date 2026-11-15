"""Offline worker/checkpoint/resume tests using actual JSON and source stores."""
import asyncio
from dataclasses import replace
import hashlib

import pytest

from app.researchguard.domain import AttributionStatus, ProcessingStatus
from app.schemas.paper import PaperRetrievalStatus
from app.services.source_store import AcceptedSourceArtifact, LocalSourceStore
from app.services.verification_job_models import JobState, TaskState, coverage
from app.services.verification_job_store import LocalJobStore, JobError, JobLimits
from app.services.verification_jobs import VerificationJobRuntime, evolve
from app.services.manuscript_verification import verify_manuscript_core
from app.tests.test_manuscript_verification import inputs, FakeRetriever, verifier, paper


class Harness:
    def __init__(self, root, paper, *, blocked=(), verify=None, limits=None, mode="ok"):
        self.paper, self.blocked = paper, set(blocked)
        self.sources, self.queries, self.verified = [], [], []
        self.source_store = LocalSourceStore(root / "sources")
        self.store = LocalJobStore(root / "jobs", limits=limits)
        self.verify = verify or verifier
        async def counted(claim, response):
            self.verified.append(response)
            return await self.verify(claim, response)
        self.dependencies = {"source_retriever": self.retrieve,
            "evidence_retriever_factory": lambda chunks: FakeRetriever(chunks, self.queries, mode),
            "prepared_verifier": counted}
        self.runtime = VerificationJobRuntime(self.store, source_store=self.source_store,
                                             core_dependencies=self.dependencies)

    def retrieve(self, doi):
        self.sources.append(doi)
        response = self.paper.model_copy(deep=True)
        response.paper.doi = response.paper.paper_id = doi
        for chunk in response.chunks:
            chunk.paper_id = doi
        artifact = self.source_store.get(doi)
        if artifact:
            return artifact.response(cache_hit=True, chunks=response.chunks)
        if doi in self.blocked:
            response.status = PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
            response.chunks = []
        return response

    def accept(self, doi, content=b"deterministic accepted source"):
        metadata = self.paper.paper.model_copy(update={"doi": doi, "paper_id": doi})
        artifact = AcceptedSourceArtifact.create(doi=doi, content=content, format="html",
            source_url=None, provider="fixture", origin="manual", paper=metadata)
        self.source_store.put(artifact)
        return artifact.raw_content_sha256


@pytest.fixture
async def harness(tmp_path, paper):
    instances = []
    def make(**kwargs):
        instance = Harness(tmp_path / str(len(instances)), paper, **kwargs)
        instances.append(instance)
        return instance
    yield make
    for instance in instances:
        await instance.runtime.shutdown(0)


@pytest.mark.anyio
async def test_job_creation_durable_stable_plan_no_extraction(harness, monkeypatch):
    h = harness()
    def forbidden(*args, **kwargs):
        pytest.fail("Parser/extractor must not run")
    monkeypatch.setattr("app.services.claim_extractor.extract_claims", forbidden)
    monkeypatch.setattr("app.services.manuscript_parser.parse_manuscript", forbidden)
    initial = await h.runtime.create(*inputs((("r1", "r2"), ("r1",))))
    on_disk = h.store.load(initial.job_id)
    assert initial == on_disk and not h.sources
    assert [(t.claim_id, t.reference_id) for t in initial.tasks] == [("claim0", "r1"), ("claim0", "r2"), ("claim1", "r1")]
    result = await h.runtime.wait(initial.job_id)
    assert result.state == JobState.COMPLETED and len(h.sources) == 1 and len(h.verified) == 3
    assert not h.runtime._workers


@pytest.mark.anyio
async def test_checkpoint_visible_before_next_pair_finishes(harness):
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def pause(claim, response):
        calls.append(1)
        if len(calls) == 2:
            entered.set()
            await release.wait()
        return await verifier(claim, response)
    h = harness(verify=pause)
    job = await h.runtime.create(*inputs((("r1",),) * 3))
    await asyncio.wait_for(entered.wait(), 5)
    saved = LocalJobStore(h.store.root).load(job.job_id)
    assert [t.state for t in saved.tasks] == [TaskState.COMPLETED, TaskState.RUNNING, TaskState.PENDING]
    assert saved.tasks[0].pair_outcome.verification.verdict == "SUPPORTED"
    assert len([e for e in saved.events if e.event_type == "pair_completed"]) == 1
    release.set()
    assert (await h.runtime.wait(job.job_id)).state == JobState.COMPLETED


@pytest.mark.anyio
@pytest.mark.parametrize("links", [(("r1",), ("r1",), ("r2",)), (("r1", "r2"),)])
async def test_selective_manual_resume_no_completed_rerun(harness, links):
    h = harness(blocked=["10.1234/a"])
    job = await h.runtime.create(*inputs(links, {"r1": "10.1234/a", "r2": "10.1234/b"}))
    waiting = await h.runtime.wait(job.job_id)
    assert waiting.state == JobState.WAITING_FOR_SOURCE
    completed = [t for t in waiting.tasks if t.state == TaskState.COMPLETED]
    assert len(completed) == len(h.verified) == 1
    assert all(t.pair_outcome.verification.verdict is None for t in waiting.tasks if t.state == TaskState.BLOCKED_SOURCE)
    digest = h.accept("10.1234/a")
    resumed = await h.runtime.resume(job.job_id, expected_revision=waiting.revision,
        reference_ids=("r1",), source_hashes={"r1": digest})
    result = await h.runtime.wait(job.job_id)
    assert result.state == JobState.COMPLETED
    assert all(result.tasks[waiting.tasks.index(t)] == t for t in completed)
    assert len(h.verified) == sum(len(row) for row in links)
    assert h.sources.count("10.1234/a") == 2  # Once per invocation, including two resumed claims.
    assert len([e for e in result.events if e.event_type == "pair_completed"]) == len(result.tasks)
    repeat = await h.runtime.resume(job.job_id, expected_revision=result.revision,
        reference_ids=("r1",), source_hashes={"r1": digest})
    assert repeat == result and len(h.verified) == len(result.tasks)
    assert coverage(result).total_pairs == len(result.tasks)


@pytest.mark.anyio
async def test_concurrent_resume_and_running_guard(harness):
    entered, release = asyncio.Event(), asyncio.Event()
    async def pause(claim, response):
        entered.set()
        await release.wait()
        return await verifier(claim, response)
    h = harness(blocked=["10.1234/local"], verify=pause)
    job = await h.runtime.create(*inputs())
    waiting = await h.runtime.wait(job.job_id)
    digest = h.accept("10.1234/local")
    kwargs = {"expected_revision": waiting.revision, "reference_ids": ("r1",), "source_hashes": {"r1": digest}}
    responses = await asyncio.gather(h.runtime.resume(job.job_id, **kwargs),
        h.runtime.resume(job.job_id, **kwargs), return_exceptions=True)
    assert sum(isinstance(x, JobError) for x in responses) == 1
    await asyncio.wait_for(entered.wait(), 5)
    with pytest.raises(JobError, match="JOB_RUNNING"):
        await h.runtime.resume(job.job_id, expected_revision=h.store.load(job.job_id).revision)
    assert len(h.runtime._workers) == len(h.verified) == 1
    release.set()
    final = await h.runtime.wait(job.job_id)
    assert len([e for e in final.events if e.event_type == "pair_completed"]) == 1


@pytest.mark.anyio
async def test_restart_repairs_running_retains_completed_and_attempt(harness):
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def pause(claim, response):
        calls.append(1)
        if len(calls) == 2:
            entered.set()
            await release.wait()
        return await verifier(claim, response)
    h = harness(verify=pause)
    job = await h.runtime.create(*inputs((("r1",),) * 3))
    await asyncio.wait_for(entered.wait(), 5)
    saved = h.store.load(job.job_id)
    await h.runtime.shutdown(0)
    # Restore the exact committed snapshot left by an abrupt process exit.
    restarted_store = LocalJobStore(h.store.root)
    payload = saved.model_dump(mode="json")
    from app.services.verification_job_store import _encoded
    (h.store.root / (job.job_id + ".json")).write_bytes(_encoded({"schema_version": 1,
        "sha256": hashlib.sha256(_encoded(payload)).hexdigest(), "snapshot": payload}))
    h.runtime = VerificationJobRuntime(restarted_store, source_store=h.source_store,
        core_dependencies={**h.dependencies, "prepared_verifier": verifier})
    await h.runtime.start()
    recovered = h.runtime.get(job.job_id)
    assert recovered.state == JobState.INTERRUPTED and not h.runtime._workers
    assert recovered.tasks[0] == saved.tasks[0]
    assert [t.state for t in recovered.tasks] == [TaskState.COMPLETED, TaskState.PENDING, TaskState.PENDING]
    assert [t.attempt for t in recovered.tasks] == [1, 1, 0]
    await h.runtime.resume(job.job_id, expected_revision=recovered.revision)
    final = await h.runtime.wait(job.job_id)
    assert final.tasks[0] == saved.tasks[0] and [t.attempt for t in final.tasks] == [1, 2, 1]
    assert len([e for e in final.events if e.event_type == "pair_completed"]) == 3


@pytest.mark.anyio
async def test_checkpoint_storage_failure_stops_without_semantic_failure(harness, monkeypatch):
    h = harness()
    original = h.store.commit
    def fail(snapshot, **kwargs):
        if snapshot.events[-1].event_type == "pair_completed":
            raise JobError("JOB_STORAGE_ERROR", 503)
        return original(snapshot, **kwargs)
    monkeypatch.setattr(h.store, "commit", fail)
    job = await h.runtime.create(*inputs((("r1",),) * 3))
    with pytest.raises(JobError, match="STORAGE_ERROR"):
        await h.runtime.wait(job.job_id)
    saved = h.store.load(job.job_id)
    assert saved.state == JobState.INTERRUPTED and len(h.verified) == 1
    assert all(t.pair_outcome is None for t in saved.tasks)
    assert not any(e.event_type == "pair_completed" for e in saved.events)


@pytest.mark.anyio
async def test_late_attempt_cannot_overwrite_new_attempt(harness):
    h = harness()
    async def supersede(claim, response):
        job_id = next(iter(h.runtime._workers))
        saved = h.store.load(job_id)
        current = saved.tasks[0]
        pending = current.model_copy(update={"state": TaskState.PENDING})
        saved = h.store.commit(evolve(saved, "job_interrupted", JobState.INTERRUPTED, tasks=(pending,)),
                               expected_revision=saved.revision)
        newer = current.model_copy(update={"attempt": current.attempt + 1})
        h.store.commit(evolve(saved, "pair_started", JobState.RUNNING, tasks=(newer,), task=newer),
                       expected_revision=saved.revision)
        return await verifier(claim, response)
    h.verify = supersede
    job = await h.runtime.create(*inputs())
    with pytest.raises(JobError, match="STALE_ATTEMPT"):
        await h.runtime.wait(job.job_id)
    saved = h.store.load(job.job_id)
    assert saved.tasks[0].pair_outcome is None and saved.tasks[0].attempt == 2
    assert not any(e.event_type == "pair_completed" for e in saved.events)


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["raise", "llm"])
async def test_explicit_bounded_retry_not_automatic(harness, mode):
    async def fail(claim, response):
        raise RuntimeError("fixture LLM failure")
    h = harness(mode="raise" if mode == "raise" else "ok", verify=fail if mode == "llm" else None,
        limits=replace(JobLimits(), max_attempts=2))
    job = await h.runtime.create(*inputs())
    first = await h.runtime.wait(job.job_id)
    assert first.state == JobState.PARTIALLY_COMPLETED and first.tasks[0].attempt == 1
    assert first.tasks[0].pair_outcome.verification.verdict is None
    with pytest.raises(JobError, match="RESUME_UNAVAILABLE"):
        await h.runtime.resume(job.job_id, expected_revision=first.revision)
    await h.runtime.resume(job.job_id, expected_revision=first.revision, retry_failed=True)
    final = await h.runtime.wait(job.job_id)
    with pytest.raises(JobError, match="RETRY_LIMIT"):
        await h.runtime.resume(job.job_id, expected_revision=final.revision, retry_failed=True)
    assert final.tasks[0].attempt == 2 and final.tasks[0].pair_outcome.verification.verdict is None


@pytest.mark.anyio
async def test_source_version_conflict_before_resume_and_during_query(harness):
    h = harness(blocked=["10.1234/local"])
    job = await h.runtime.create(*inputs())
    waiting = await h.runtime.wait(job.job_id)
    old_hash = h.accept("10.1234/local", b"old")
    new_hash = h.accept("10.1234/local", b"new")
    with pytest.raises(JobError, match="VERSION_CONFLICT"):
        await h.runtime.resume(job.job_id, expected_revision=waiting.revision,
            source_hashes={"r1": old_hash})
    assert h.store.load(job.job_id) == waiting and not h.verified
    original = h.runtime.core_dependencies["source_retriever"]
    def changed(doi):
        response = original(doi)
        response.source.raw_content_sha256 = "f" * 64
        return response
    h.runtime.core_dependencies["source_retriever"] = changed
    await h.runtime.resume(job.job_id, expected_revision=waiting.revision, source_hashes={"r1": new_hash})
    result = await h.runtime.wait(job.job_id)
    assert result.state == JobState.WAITING_FOR_SOURCE
    assert result.tasks[0].reason_code == "SOURCE_VERSION_CONFLICT"
    assert result.tasks[0].pair_outcome.verification.verdict is None and not h.verified


@pytest.mark.anyio
async def test_invalid_doi_not_upload_recoverable_and_claim_gap_preserved(harness):
    h = harness()
    parsed, extraction = inputs((("r1",), ("r2",)), {"r1": None, "r2": "10.1234/local"})
    claims = (extraction.claims[0], extraction.claims[1].model_copy(update={
        "attribution_status": AttributionStatus.UNRESOLVED}))
    extraction = extraction.model_copy(update={"claims": claims})
    job = await h.runtime.create(parsed, extraction)
    result = await h.runtime.wait(job.job_id)
    assert result.state == JobState.PARTIALLY_COMPLETED
    assert len(result.tasks) == 1 and result.tasks[0].state == TaskState.FAILED
    assert result.tasks[0].reason_code == "DOI_MISSING" and coverage(result).unresolved_claims == 1
    assert not h.sources and not coverage(result).coverage_complete


@pytest.mark.anyio
async def test_zero_claims_is_partial_not_completed(harness):
    h = harness()
    job = await h.runtime.create(*inputs(()))
    result = await h.runtime.wait(job.job_id)
    assert result.state == JobState.PARTIALLY_COMPLETED and not coverage(result).coverage_complete


@pytest.mark.anyio
async def test_event_limit_failure_does_not_publish_completion(harness):
    h = harness(limits=replace(JobLimits(), max_events=3))
    job = await h.runtime.create(*inputs())
    with pytest.raises(JobError, match="EVENT_LIMIT"):
        await h.runtime.wait(job.job_id)
    saved = h.store.load(job.job_id)
    assert len(saved.events) == 3 and saved.tasks[0].state == TaskState.RUNNING
    assert saved.tasks[0].pair_outcome is None


@pytest.mark.anyio
async def test_core_selection_and_callback_storage_error_propagates(paper):
    parsed, extraction = inputs((("r1", "r2"),))
    sources, queries = [], []
    def source(doi):
        sources.append(doi)
        return paper
    async def finish(outcome):
        raise JobError("JOB_STORAGE_ERROR", 503)
    with pytest.raises(JobError, match="STORAGE_ERROR"):
        await verify_manuscript_core(parsed, extraction, source_retriever=source,
            evidence_retriever_factory=lambda chunks: FakeRetriever(chunks, queries), prepared_verifier=verifier,
            selected_pairs=(("claim0", "r2"),), on_pair_finished=finish)
    assert len(queries) == len(sources) == 1
    with pytest.raises(ValueError, match="selection"):
        await verify_manuscript_core(parsed, extraction, selected_pairs=(("claim0", "foreign"),))


@pytest.mark.anyio
async def test_reject_multiple_processes_before_recovery(harness, monkeypatch):
    h = harness()
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with pytest.raises(JobError, match="MULTIPROCESS_UNSUPPORTED"):
        await h.runtime.start()
    assert not h.sources


@pytest.mark.anyio
async def test_actual_process_exit_preserves_checkpoint_and_resumes(harness):
    import subprocess
    import sys
    import textwrap
    h = harness()
    script = textwrap.dedent('''
        import asyncio, os, sys
        from pathlib import Path
        from app.tests.test_verification_jobs import Harness
        from app.tests.test_paperqa2_integration import paper
        from app.tests.test_manuscript_verification import inputs, verifier
        calls = []
        async def exit_on_second(claim, response):
            calls.append(1)
            if len(calls) == 2:
                os._exit(23)
            return await verifier(claim, response)
        async def main():
            h = Harness(Path(sys.argv[1]), paper.__wrapped__(), verify=exit_on_second)
            job = await h.runtime.create(*inputs((("r1",),) * 3))
            await h.runtime.wait(job.job_id)
        asyncio.run(main())
    ''')
    result = await asyncio.to_thread(subprocess.run, [sys.executable, "-c", script, str(h.store.root.parent)],
        capture_output=True, timeout=30)
    assert result.returncode == 23, result.stderr.decode(errors="replace")
    job_id, = h.store.list_job_ids()
    before = h.store.load(job_id)
    assert [t.state for t in before.tasks] == [TaskState.COMPLETED, TaskState.RUNNING, TaskState.PENDING]
    await h.runtime.start()
    repaired = h.runtime.get(job_id)
    await h.runtime.resume(job_id, expected_revision=repaired.revision)
    final = await h.runtime.wait(job_id)
    assert final.state == JobState.COMPLETED and final.tasks[0] == before.tasks[0]
    assert len(h.verified) == 2 and [t.attempt for t in final.tasks] == [1, 2, 1]


@pytest.mark.anyio
async def test_interrupted_last_attempt_is_terminal_processing_failure(harness):
    entered = asyncio.Event()
    async def pause(claim, response):
        entered.set()
        await asyncio.Event().wait()
    h = harness(verify=pause, limits=replace(JobLimits(), max_attempts=1))
    job = await h.runtime.create(*inputs())
    await asyncio.wait_for(entered.wait(), 5)
    await h.runtime.shutdown(0)
    snapshot = h.store.load(job.job_id)
    assert snapshot.state == JobState.PARTIALLY_COMPLETED
    assert snapshot.tasks[0].state == TaskState.FAILED
    assert snapshot.tasks[0].reason_code == "PROCESS_INTERRUPTED_RETRY_LIMIT"
    assert snapshot.tasks[0].pair_outcome.verification.verdict is None


@pytest.mark.anyio
async def test_failed_retry_preserves_canonical_source_version(harness):
    async def fail(claim, response):
        raise RuntimeError("LLM fixture failure")
    h = harness(verify=fail)
    digest = h.accept("10.1234/local", b"original bytes")
    job = await h.runtime.create(*inputs())
    failed = await h.runtime.wait(job.job_id)
    assert failed.tasks[0].source_version == "sha256:" + digest
    replacement = h.accept("10.1234/local", b"changed bytes")
    with pytest.raises(JobError, match="VERSION_CONFLICT"):
        await h.runtime.resume(job.job_id, expected_revision=failed.revision, retry_failed=True,
            source_hashes={"r1": replacement})
    assert h.store.load(job.job_id) == failed


@pytest.mark.anyio
async def test_partial_reference_resume_does_not_schedule_other_pending(harness):
    entered = asyncio.Event()
    async def pause(claim, response):
        entered.set()
        await asyncio.Event().wait()
    h = harness(verify=pause)
    job = await h.runtime.create(*inputs((("r1", "r2"),)))
    await asyncio.wait_for(entered.wait(), 5)
    await h.runtime.shutdown(0)
    h.runtime = VerificationJobRuntime(h.store, source_store=h.source_store,
        core_dependencies={**h.dependencies, "prepared_verifier": verifier})
    await h.runtime.start()
    snapshot = h.runtime.get(job.job_id)
    await h.runtime.resume(job.job_id, expected_revision=snapshot.revision, reference_ids=("r2",))
    partial = await h.runtime.wait(job.job_id)
    assert [t.state for t in partial.tasks] == [TaskState.PENDING, TaskState.COMPLETED]
    assert partial.state == JobState.INTERRUPTED and not coverage(partial).coverage_complete


@pytest.mark.anyio
async def test_completed_task_cannot_be_rewritten_by_store(harness):
    h = harness()
    job = await h.runtime.create(*inputs())
    final = await h.runtime.wait(job.job_id)
    changed = final.tasks[0].model_copy(update={"reason_code": "CHANGED"})
    candidate = evolve(final, "job_completed", JobState.COMPLETED, tasks=(changed,))
    with pytest.raises(JobError, match="COMPLETED_TASK_IMMUTABLE"):
        h.store.commit(candidate, expected_revision=final.revision)
    assert h.store.load(job.job_id) == final


@pytest.mark.anyio
async def test_shutdown_prevents_resume_and_drains_committed_outcome(harness):
    entered, release = asyncio.Event(), asyncio.Event()
    async def pause(claim, response):
        entered.set()
        await release.wait()
        return await verifier(claim, response)
    h = harness(verify=pause)
    job = await h.runtime.create(*inputs())
    await asyncio.wait_for(entered.wait(), 5)
    draining = asyncio.create_task(h.runtime.shutdown(timeout=5))
    await asyncio.sleep(0)
    with pytest.raises(JobError, match="RUNTIME_STOPPING"):
        await h.runtime.resume(job.job_id, expected_revision=h.store.load(job.job_id).revision)
    release.set()
    await draining
    final = h.store.load(job.job_id)
    assert final.state == JobState.COMPLETED and final.tasks[0].pair_outcome.verification.verdict == "SUPPORTED"
    assert len([e for e in final.events if e.event_type == "pair_completed"]) == 1


@pytest.mark.anyio
async def test_unknown_job_ids_do_not_allocate_locks(harness):
    h = harness()
    with pytest.raises(JobError, match="NOT_FOUND"):
        await h.runtime.resume("job_" + "a" * 32, expected_revision=0)
    assert not h.runtime._locks


@pytest.mark.anyio
async def test_completed_processing_can_have_contradicted_verdict(harness):
    from app.schemas.verification import Verdict as LegacyVerdict
    async def contradict(claim, response):
        return (await verifier(claim, response)).model_copy(update={"verdict": LegacyVerdict.CONTRADICTS})
    h = harness(verify=contradict)
    job = await h.runtime.create(*inputs())
    final = await h.runtime.wait(job.job_id)
    assert final.state == JobState.COMPLETED and coverage(final).coverage_complete
    assert final.tasks[0].pair_outcome.verification.verdict == "CONTRADICTED"


@pytest.mark.anyio
async def test_committed_pair_survives_error_after_replace_without_duplicate(harness, monkeypatch):
    h = harness()
    original = h.store.commit
    def fail_after_complete(snapshot, **kwargs):
        saved = original(snapshot, **kwargs)
        if snapshot.events[-1].event_type == "pair_completed":
            raise JobError("JOB_STORAGE_ERROR", 503)
        return saved
    monkeypatch.setattr(h.store, "commit", fail_after_complete)
    job = await h.runtime.create(*inputs())
    with pytest.raises(JobError, match="STORAGE_ERROR"):
        await h.runtime.wait(job.job_id)
    saved = h.store.load(job.job_id)
    assert saved.state == JobState.COMPLETED and len(h.verified) == 1
    assert len([e for e in saved.events if e.event_type == "pair_completed"]) == 1
    h.runtime = VerificationJobRuntime(LocalJobStore(h.store.root), source_store=h.source_store,
        core_dependencies=h.dependencies)
    await h.runtime.start()
    repeated = await h.runtime.resume(job.job_id, expected_revision=saved.revision)
    assert repeated == saved and len(h.verified) == 1


@pytest.mark.anyio
async def test_version_conflict_outcome_retains_previous_pinned_binding(harness):
    async def fail(claim, response):
        raise RuntimeError("fixture")
    h = harness(verify=fail)
    job = await h.runtime.create(*inputs())
    failed = await h.runtime.wait(job.job_id)
    pinned = failed.tasks[0].source_binding
    assert pinned.source_version is not None
    h.paper.chunks[0].text = "A different accepted source version."
    await h.runtime.resume(job.job_id, expected_revision=failed.revision, retry_failed=True)
    blocked = await h.runtime.wait(job.job_id)
    assert blocked.tasks[0].reason_code == "SOURCE_VERSION_CONFLICT"
    assert blocked.tasks[0].source_binding == pinned
    assert blocked.tasks[0].pair_outcome.binding.source_version is None
    new_hash = h.accept("10.1234/local", b"replacement bytes")
    with pytest.raises(JobError, match="VERSION_CONFLICT"):
        await h.runtime.resume(job.job_id, expected_revision=blocked.revision, source_hashes={"r1": new_hash})
    assert h.store.load(job.job_id) == blocked


@pytest.mark.anyio
async def test_durability_missing_artifact_blocks_verdict_and_can_resume(harness):
    h = harness()
    h.paper.source.raw_content_sha256 = hashlib.sha256(b'not persisted').hexdigest()
    job = await h.runtime.create(*inputs((('r1',), ('r1',))))
    failed = await h.runtime.wait(job.job_id)
    assert all(t.reason_code == 'SOURCE_DURABILITY_UNAVAILABLE' for t in failed.tasks)
    assert not h.verified and not h.queries
    assert all(t.pair_outcome.verification.verdict is None for t in failed.tasks)
    digest = h.accept('10.1234/local')
    await h.runtime.resume(job.job_id, expected_revision=failed.revision,
        source_hashes={'r1': digest}, retry_failed=True)
    completed = await h.runtime.wait(job.job_id)
    assert completed.state == JobState.COMPLETED
    assert [t.attempt for t in completed.tasks] == [2, 2]


@pytest.mark.anyio
async def test_durability_same_doi_checks_once_and_retains_completed_pairs(harness, monkeypatch):
    h = harness()
    h.accept('10.1234/local')
    checks = []
    original = h.runtime._check_source_durability
    def checked(response):
        checks.append(response.paper.doi)
        return original(response)
    monkeypatch.setattr(h.runtime, '_check_source_durability', checked)
    # The second source claims raw provenance but has no artifact.
    h.paper.source.raw_content_sha256 = hashlib.sha256(b'missing').hexdigest()
    job = await h.runtime.create(*inputs((('r1',), ('r2',), ('r1',)),
        dois={'r1': '10.1234/local', 'r2': '10.1234/missing'}))
    saved = await h.runtime.wait(job.job_id)
    assert checks == ['10.1234/local', '10.1234/missing']
    assert [t.state for t in saved.tasks] == [TaskState.COMPLETED, TaskState.FAILED, TaskState.COMPLETED]
    original_completed = (saved.tasks[0], saved.tasks[2])
    digest = h.accept('10.1234/missing')
    await h.runtime.resume(job.job_id, expected_revision=saved.revision, reference_ids=['r2'],
        source_hashes={'r2': digest}, retry_failed=True)
    final = await h.runtime.wait(job.job_id)
    assert (final.tasks[0], final.tasks[2]) == original_completed
    assert len(h.verified) == 3


@pytest.mark.anyio
@pytest.mark.parametrize('damage', ['raw', 'wrong_doi', 'wrong_hash', 'wrong_version'])
async def test_durability_corruption_or_identity_mismatch_has_no_verdict(harness, monkeypatch, damage):
    from dataclasses import replace as replace_artifact
    h = harness()
    digest = h.accept('10.1234/local')
    artifact = h.source_store.get('10.1234/local')
    response = artifact.response(chunks=h.paper.chunks)
    h.dependencies['source_retriever'] = lambda doi: response
    h.runtime.core_dependencies = dict(h.dependencies)
    if damage == 'raw':
        (h.source_store.root / digest / 'source.html').write_bytes(b'corrupt')
    elif damage == 'wrong_version':
        h.accept('10.1234/local', b'changed persisted version')
    else:
        wrong = replace_artifact(artifact, **({'doi': '10.1234/other'} if damage == 'wrong_doi' else {'content': b'tampered'}))
        monkeypatch.setattr(h.source_store, 'get', lambda doi: wrong)
    job = await h.runtime.create(*inputs())
    saved = await h.runtime.wait(job.job_id)
    assert saved.tasks[0].reason_code.startswith('SOURCE_DURABILITY_')
    assert saved.tasks[0].state == TaskState.FAILED
    assert saved.tasks[0].pair_outcome.verification.verdict is None
    assert not h.verified


@pytest.mark.anyio
async def test_durability_production_runtime_requires_raw_hash(harness):
    from app.services.source_store import SourceDurabilityError
    h = harness()
    runtime = VerificationJobRuntime(h.store, source_store=h.source_store)
    with pytest.raises(SourceDurabilityError, match='HASH_REQUIRED'):
        runtime._check_source_durability(h.paper)
    # Existing standalone core and explicit legacy test retrievers remain supported.
    job = await h.runtime.create(*inputs())
    assert (await h.runtime.wait(job.job_id)).state == JobState.COMPLETED


@pytest.mark.anyio
async def test_durability_real_retrieval_write_failure_then_retry(harness, monkeypatch):
    from unittest.mock import Mock
    from app.services import paper_retriever as retrieval
    from app.services.document_retriever import RetrievedDocument
    from app.tests.test_source_lifecycle import offline_auto, DOI
    from app.tests.full_text_fixtures import FULL_TEXT_HTML
    h = harness()
    monkeypatch.setenv('RESEARCHGUARD_SOURCE_CACHE_DIR', str(h.source_store.root))
    offline_auto(monkeypatch)
    monkeypatch.setattr(retrieval, 'retrieve_document', Mock(return_value=RetrievedDocument(
        FULL_TEXT_HTML, FULL_TEXT_HTML.decode(), 'html', 'text/html', 'https://accepted.example/source.html')))
    h.runtime.core_dependencies['source_retriever'] = retrieval.retrieve_paper
    original_put = LocalSourceStore.put
    def disk_failure(*args):
        raise OSError('injected source persistence error')
    monkeypatch.setattr(LocalSourceStore, 'put', disk_failure)
    parsed, extracted = inputs((('r1',), ('r1',)), dois={'r1': DOI})
    job = await h.runtime.create(parsed, extracted)
    failed = await h.runtime.wait(job.job_id)
    assert all(t.reason_code == 'SOURCE_DURABILITY_UNAVAILABLE' for t in failed.tasks)
    assert not h.verified and not h.queries and h.source_store.get(DOI) is None
    monkeypatch.setattr(LocalSourceStore, 'put', original_put)
    await h.runtime.resume(job.job_id, expected_revision=failed.revision, retry_failed=True)
    final = await h.runtime.wait(job.job_id)
    artifact = h.source_store.get(DOI)
    assert final.state == JobState.COMPLETED and artifact.content == FULL_TEXT_HTML
    assert all(t.source_version == 'sha256:' + artifact.raw_content_sha256 for t in final.tasks)
    assert len(h.verified) == 2


@pytest.mark.anyio
async def test_interrupted_resume_classifies_missing_locator_and_continues(harness):
    from app.services.verification_job_models import JobSnapshot, TaskRecord, EventRecord, task_key
    from app.services.manuscript_verification import plan_manuscript_pairs
    parsed, extraction = inputs((("r1",), ("r2",)),
        {"r1": None, "r2": "10.1234/local"})
    plan, blocked = plan_manuscript_pairs(parsed, extraction)
    job_id, stamp = "job_" + "d" * 32, "fixture"
    initial = JobSnapshot(job_id=job_id, input_fingerprint=extraction.metadata.input_fingerprint,
        parsed=parsed, extraction=extraction, attribution_blocked=blocked,
        tasks=tuple(TaskRecord(task_key=task_key(job_id, extraction.metadata.input_fingerprint, c.id, r.id),
            claim_id=c.id, reference_id=r.id) for c, r, _ in plan),
        events=(EventRecord(job_id=job_id, sequence=1, event_type="job_created", status="pending", timestamp=stamp),),
        next_sequence=2, created_at=stamp, updated_at=stamp)
    h = harness()
    h.store.create(initial)
    interrupted = h.store.commit(evolve(initial, "job_interrupted", JobState.INTERRUPTED), expected_revision=0)
    await h.runtime.resume(job_id, expected_revision=interrupted.revision)
    final = await h.runtime.wait(job_id)
    assert final.state == JobState.PARTIALLY_COMPLETED
    assert final.tasks[0].reason_code == "DOI_MISSING"
    assert final.tasks[0].pair_outcome.verification.verdict is None
    assert final.tasks[1].state == TaskState.COMPLETED
    assert len(h.verified) == 1


@pytest.mark.anyio
async def test_missing_locator_resume_still_rejects_supplied_source_hash(harness):
    from app.tests.test_verification_job_store import snapshot
    from app.services.citation_context import fingerprint
    from app.services.verification_job_models import task_key
    h = harness()
    original = snapshot()
    parsed = original.parsed.model_copy(update={"references": tuple(
        r.model_copy(update={"doi": None}) for r in original.parsed.references)})
    fp = "sha256:" + fingerprint(parsed)
    extraction = original.extraction.model_copy(update={"metadata": original.extraction.metadata.model_copy(
        update={"input_fingerprint": fp})})
    original = original.model_copy(update={"parsed": parsed, "extraction": extraction, "input_fingerprint": fp,
        "tasks": tuple(t.model_copy(update={"task_key": task_key(original.job_id, fp, t.claim_id, t.reference_id)}) for t in original.tasks)})
    h.store.create(original)
    with pytest.raises(JobError, match="JOB_SOURCE_NOT_RECOVERABLE"):
        await h.runtime.resume(original.job_id, expected_revision=0, source_hashes={"r1": "a" * 64})
    assert not h.verified and not h.runtime._workers
