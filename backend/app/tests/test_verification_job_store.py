"""Durable snapshot integrity, atomic failure windows, and bounded storage."""
import hashlib
import json
from dataclasses import replace

import pytest

from app.services.verification_job_models import JobSnapshot, TaskRecord, EventRecord, task_key, JobState
from app.services.verification_job_store import LocalJobStore, JobLimits, JobError, _encoded
from app.services.verification_jobs import evolve
from app.services.manuscript_verification import plan_manuscript_pairs
from app.tests.test_manuscript_verification import inputs


def snapshot(job_id="job_" + "a" * 32):
    parsed, extraction = inputs()
    plan, blocked = plan_manuscript_pairs(parsed, extraction)
    fingerprint = extraction.metadata.input_fingerprint
    return JobSnapshot(job_id=job_id, input_fingerprint=fingerprint, parsed=parsed, extraction=extraction,
        tasks=tuple(TaskRecord(task_key=task_key(job_id, fingerprint, c.id, r.id), claim_id=c.id, reference_id=r.id)
                    for c, r, _ in plan), attribution_blocked=blocked,
        events=(EventRecord(job_id=job_id, sequence=1, event_type="job_created", status="pending", timestamp="fixture"),),
        next_sequence=2, created_at="fixture", updated_at="fixture")


def test_create_roundtrip_revision_and_plan(tmp_path):
    store = LocalJobStore(tmp_path)
    original = snapshot()
    assert store.create(original) == original == LocalJobStore(tmp_path).load(original.job_id)
    assert JobSnapshot.model_validate_json(original.model_dump_json()) == original
    assert store.list_job_ids() == (original.job_id,)
    newer = evolve(original, "job_started", JobState.RUNNING)
    store.commit(newer, expected_revision=0)
    assert store.load(original.job_id).revision == 1
    with pytest.raises(JobError, match="REVISION_CONFLICT"):
        store.commit(newer, expected_revision=0)
    with pytest.raises(JobError, match="ALREADY_EXISTS"):
        store.create(original)


@pytest.mark.parametrize("after_replace", [False, True])
def test_atomic_replace_failure_window(tmp_path, monkeypatch, after_replace):
    store, original = LocalJobStore(tmp_path), snapshot()
    store.create(original)
    path = tmp_path / (original.job_id + ".json")
    before = path.read_bytes()
    import app.services.verification_job_store as module
    original_replace = module.os.replace
    def failure(src, dst):
        if after_replace:
            original_replace(src, dst)
        raise OSError("fixture disk fault")
    monkeypatch.setattr(module.os, "replace", failure)
    newer = evolve(original, "job_started", JobState.RUNNING)
    with pytest.raises(JobError, match="STORAGE_ERROR"):
        store.commit(newer, expected_revision=0)
    recovered = LocalJobStore(tmp_path).load(original.job_id)
    assert recovered == (newer if after_replace else original)
    if not after_replace:
        assert path.read_bytes() == before
    assert not list(tmp_path.glob(".pending-*"))


@pytest.mark.parametrize("damage", ["json", "schema", "hash", "id", "graph", "sequence", "fingerprint", "inner_schema", "payload_type"])
def test_corruption_never_becomes_missing_or_overwritten(tmp_path, damage):
    store, original = LocalJobStore(tmp_path), snapshot()
    store.create(original)
    path = tmp_path / (original.job_id + ".json")
    envelope = json.loads(path.read_bytes())
    if damage == "json":
        content = b"{bad"
    else:
        if damage == "schema":
            envelope["schema_version"] = 2
        elif damage == "hash":
            envelope["sha256"] = "bad"
        elif damage == "payload_type":
            envelope["snapshot"] = []
            envelope["sha256"] = hashlib.sha256(_encoded([])).hexdigest()
        else:
            if damage == "id":
                envelope["snapshot"]["job_id"] = "../../foreign"
            elif damage == "graph":
                envelope["snapshot"]["tasks"][0]["reference_id"] = "foreign"
            elif damage == "sequence":
                envelope["snapshot"]["next_sequence"] = 999
            elif damage == "fingerprint":
                envelope["snapshot"]["input_fingerprint"] = "bad"
            else:
                envelope["snapshot"]["schema_version"] = 2
            envelope["sha256"] = hashlib.sha256(_encoded(envelope["snapshot"])).hexdigest()
        content = _encoded(envelope)
    path.write_bytes(content)
    with pytest.raises(JobError) as exc:
        store.load(original.job_id)
    assert exc.value.code in {"JOB_SNAPSHOT_CORRUPT", "JOB_SCHEMA_UNSUPPORTED"}
    assert path.read_bytes() == content


@pytest.mark.parametrize("job_id", ["../../outside", "job_bad", "", "job_" + "a" * 32 + "/other"])
def test_job_id_path_guard(tmp_path, job_id):
    with pytest.raises(JobError, match="ID_INVALID"):
        LocalJobStore(tmp_path).load(job_id)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("resource", ["jobs", "bytes", "snapshot", "events"])
def test_resource_limits_leave_old_snapshot_intact(tmp_path, resource):
    limits = JobLimits()
    limits = replace(limits, **{"jobs": {"max_jobs": 1}, "bytes": {"max_storage_bytes": 1},
        "snapshot": {"max_snapshot_bytes": 1}, "events": {"max_events": 1}}[resource])
    store, original = LocalJobStore(tmp_path, limits=limits), snapshot()
    if resource in {"bytes", "snapshot"}:
        with pytest.raises(JobError):
            store.create(original)
        assert not list(tmp_path.glob("*.json"))
    else:
        store.create(original)
        path = tmp_path / (original.job_id + ".json")
        before = path.read_bytes()
        with pytest.raises(JobError):
            if resource == "jobs":
                store.create(snapshot("job_" + "b" * 32))
            else:
                store.commit(evolve(original, "job_started", JobState.RUNNING), expected_revision=0)
        assert path.read_bytes() == before


def test_input_is_immutable_across_commits(tmp_path):
    store, original = LocalJobStore(tmp_path), snapshot()
    store.create(original)
    candidate = evolve(original, "job_started", JobState.RUNNING)
    candidate = candidate.model_copy(update={"parsed": original.parsed.model_copy(update={
        "manuscript": original.parsed.manuscript.model_copy(update={"content_locator": "changed://locator"})})})
    with pytest.raises(JobError, match="IMMUTABLE_DATA"):
        store.commit(candidate, expected_revision=0)
    assert store.load(original.job_id) == original


def test_storage_capacity_includes_orphaned_temporaries(tmp_path):
    (tmp_path / ".pending-orphan.tmp").write_bytes(b"x" * 10000)
    store = LocalJobStore(tmp_path, limits=replace(JobLimits(), max_storage_bytes=10000))
    with pytest.raises(JobError, match="STORAGE_CAPACITY"):
        store.create(snapshot())
    assert (tmp_path / ".pending-orphan.tmp").stat().st_size == 10000
    assert not list(tmp_path.glob("*.json"))
