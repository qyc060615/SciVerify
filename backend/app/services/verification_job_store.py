"""Versioned local snapshots. Single process only; one atomic job/result/event commit."""
from dataclasses import dataclass
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import tempfile
from threading import RLock

from app.services.verification_job_models import JobSnapshot, TaskState

_JOB_ID = re.compile(r"^job_[0-9a-f]{32}$")


class JobError(RuntimeError):
    def __init__(self, code, status_code=409):
        super().__init__(code)
        self.code, self.status_code = code, status_code


def positive_setting(name, default):
    try:
        value = int(os.getenv(name, str(default)))
        if value <= 0:
            raise ValueError()
        return value
    except ValueError:
        raise JobError("JOB_CONFIGURATION_INVALID", 503) from None


@dataclass(frozen=True)
class JobLimits:
    max_jobs: int = 64
    max_storage_bytes: int = 512 * 1024 * 1024
    max_snapshot_bytes: int = 16 * 1024 * 1024
    max_events: int = 10000
    max_attempts: int = 3

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in vars(self).values()):
            raise JobError("JOB_CONFIGURATION_INVALID", 503)

    @classmethod
    def from_environment(cls):
        return cls(**{field: positive_setting("RESEARCHGUARD_JOB_" + field.upper(), default)
                      for field, default in vars(cls()).items()})


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


class LocalJobStore:
    def __init__(self, root=None, *, limits=None):
        self.root = Path(root or os.getenv("RESEARCHGUARD_JOB_DIR") or
                         Path(__file__).resolve().parents[2] / "data/researchguard/jobs")
        self.limits = limits or JobLimits.from_environment()
        self._lock = RLock()

    def _path(self, job_id):
        if not isinstance(job_id, str) or not _JOB_ID.fullmatch(job_id):
            raise JobError("JOB_ID_INVALID", 422)
        return self.root / (job_id + ".json")

    def list_job_ids(self):
        try:
            paths = sorted(self.root.glob("*.json"))
            if len(paths) > self.limits.max_jobs:
                raise JobError("JOB_CAPACITY_EXCEEDED", 507)
            if any(not _JOB_ID.fullmatch(p.stem) or p.is_symlink() for p in paths):
                raise JobError("JOB_SNAPSHOT_CORRUPT", 500)
            return tuple(p.stem for p in paths)
        except OSError:
            raise JobError("JOB_STORAGE_ERROR", 503) from None

    def load(self, job_id):
        path = self._path(job_id)
        with self._lock:
            try:
                if path.is_symlink():
                    raise JobError("JOB_SNAPSHOT_CORRUPT", 500)
                if path.stat().st_size > self.limits.max_snapshot_bytes:
                    raise JobError("JOB_SNAPSHOT_TOO_LARGE", 507)
                envelope = json.loads(path.read_bytes())
                if not isinstance(envelope, dict):
                    raise ValueError()
                if type(envelope.get("schema_version")) is not int or envelope["schema_version"] != 1:
                    raise JobError("JOB_SCHEMA_UNSUPPORTED", 500)
                if set(envelope) != {"schema_version", "sha256", "snapshot"}:
                    raise ValueError()
                payload = envelope["snapshot"]
                if not isinstance(payload, dict):
                    raise ValueError()
                if hashlib.sha256(_encoded(payload)).hexdigest() != envelope["sha256"]:
                    raise ValueError()
                if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
                    raise JobError("JOB_SCHEMA_UNSUPPORTED", 500)
                snapshot = JobSnapshot.model_validate(payload)
                if snapshot.job_id != job_id:
                    raise ValueError()
                self._check_counts(snapshot)
                return snapshot
            except FileNotFoundError:
                raise JobError("JOB_NOT_FOUND", 404) from None
            except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
                raise JobError("JOB_SNAPSHOT_CORRUPT", 500) from None
            except OSError:
                raise JobError("JOB_STORAGE_ERROR", 503) from None

    def _check_counts(self, snapshot):
        if len(snapshot.events) > self.limits.max_events:
            raise JobError("JOB_EVENT_LIMIT", 507)
        if any(t.attempt > self.limits.max_attempts for t in snapshot.tasks):
            raise JobError("JOB_RETRY_LIMIT", 409)

    def create(self, snapshot):
        with self._lock:
            path = self._path(snapshot.job_id)
            if path.exists():
                raise JobError("JOB_ALREADY_EXISTS")
            if snapshot.revision != 0:
                raise JobError("JOB_REVISION_CONFLICT")
            return self._write(snapshot)

    def commit(self, snapshot, *, expected_revision):
        with self._lock:
            previous = self.load(snapshot.job_id)
            if previous.revision != expected_revision or snapshot.revision != expected_revision + 1:
                raise JobError("JOB_REVISION_CONFLICT")
            if (snapshot.parsed != previous.parsed or snapshot.extraction != previous.extraction
                    or snapshot.input_fingerprint != previous.input_fingerprint
                    or snapshot.created_at != previous.created_at
                    or snapshot.events[:len(previous.events)] != previous.events
                    or snapshot.next_sequence < previous.next_sequence):
                raise JobError("JOB_IMMUTABLE_DATA_CHANGED", 500)
            if len(snapshot.tasks) != len(previous.tasks):
                raise JobError("JOB_IMMUTABLE_DATA_CHANGED", 500)
            for old, new in zip(previous.tasks, snapshot.tasks):
                if (old.task_key, old.claim_id, old.reference_id) != (new.task_key, new.claim_id, new.reference_id):
                    raise JobError("JOB_IMMUTABLE_DATA_CHANGED", 500)
                if old.state == TaskState.COMPLETED and old != new:
                    raise JobError("JOB_COMPLETED_TASK_IMMUTABLE")
                transitions = {
                    TaskState.PENDING: {TaskState.PENDING, TaskState.RUNNING},
                    TaskState.RUNNING: {TaskState.RUNNING, TaskState.PENDING, TaskState.COMPLETED,
                                       TaskState.BLOCKED_SOURCE, TaskState.FAILED},
                    TaskState.BLOCKED_SOURCE: {TaskState.BLOCKED_SOURCE, TaskState.PENDING},
                    TaskState.FAILED: {TaskState.FAILED, TaskState.PENDING},
                    TaskState.COMPLETED: {TaskState.COMPLETED},
                }
                if new.state not in transitions[old.state]:
                    raise JobError("JOB_TASK_STATE_CONFLICT")
                if new.attempt < old.attempt or new.attempt > old.attempt + 1:
                    raise JobError("JOB_ATTEMPT_CONFLICT")
                starting = old.state == TaskState.PENDING and new.state == TaskState.RUNNING
                if new.attempt != old.attempt + int(starting):
                    raise JobError("JOB_ATTEMPT_CONFLICT")
            return self._write(snapshot)

    def _write(self, snapshot):
        try:
            snapshot = JobSnapshot.model_validate(snapshot.model_dump())
            self._check_counts(snapshot)
            payload = snapshot.model_dump(mode="json")
            content = _encoded({"schema_version": 1, "sha256": hashlib.sha256(_encoded(payload)).hexdigest(),
                                "snapshot": payload})
            if len(content) > self.limits.max_snapshot_bytes:
                raise JobError("JOB_SNAPSHOT_TOO_LARGE", 507)
            self.root.mkdir(parents=True, exist_ok=True)
            target = self._path(snapshot.job_id)
            paths = tuple(self.root.glob("*.json"))
            if not target.exists() and len(paths) >= self.limits.max_jobs:
                raise JobError("JOB_CAPACITY_EXCEEDED", 507)
            # Crash-orphaned temporary files also consume capacity; never delete unknown files.
            total = sum(p.stat().st_size for p in self.root.iterdir() if p.is_file() and p != target) + len(content)
            if total > self.limits.max_storage_bytes:
                raise JobError("JOB_STORAGE_CAPACITY", 507)
            descriptor, name = tempfile.mkstemp(prefix=".pending-", suffix=".tmp", dir=self.root)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, target)
            finally:
                Path(name).unlink(missing_ok=True)
            # A derived directory must never change the committed job's outcome.
            try:
                from app.services.task_literature import write_task_literature
                write_task_literature(snapshot, self.root)
            except (OSError, ValueError):
                logging.getLogger(__name__).warning("task_literature_directory_write_failed job_id=%s", snapshot.job_id)
            return snapshot
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise JobError("JOB_SNAPSHOT_INVALID", 500) from None
        except OSError:
            raise JobError("JOB_STORAGE_ERROR", 503) from None
