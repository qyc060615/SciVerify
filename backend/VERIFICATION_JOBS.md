# Local verification jobs (M4 Phase 2)

This is a local, single-user demo. Job routes are disabled by default and accept
only loopback clients when enabled. There is no multi-user authorization model.
Run exactly **one Uvicorn process**; JSON snapshots and worker locks do not
coordinate multiple processes. Known multi-worker environment settings are
rejected. Do not expose these routes through a public reverse proxy.

Enable `RESEARCHGUARD_JOBS_ENABLED=1`, set `RESEARCHGUARD_JOB_DIR` to a private
local directory, and run from `backend`:

```powershell
$env:RESEARCHGUARD_JOBS_ENABLED='1'
python -m uvicorn app.main:app --host 127.0.0.1 --workers 1
```

Job storage is independent of `RESEARCHGUARD_SOURCE_CACHE_DIR`. Limits have the
prefix `RESEARCHGUARD_JOB_`: `MAX_JOBS` (64), `MAX_STORAGE_BYTES` (512 MiB),
`MAX_SNAPSHOT_BYTES` (16 MiB), `MAX_EVENTS` (10000), and `MAX_ATTEMPTS` (3).
Limits reject changes explicitly; they never discard results or events.

- `POST /api/verification/jobs`: submit `parsed` and `extraction`; returns 202.
  These remain client-supplied structures, not server-authenticated parser records.
- `GET /api/verification/jobs/{job_id}`: revision, processing coverage, original
  identities, all task states, and committed pair outcomes. Private locators are omitted.
- `GET /api/verification/jobs/{job_id}/events?after=N`: durable events with sequence > N.
- `POST /api/verification/jobs/{job_id}/resume`: supply `expected_revision`, optional
  `reference_ids`, and `source_hashes` keyed by **reference ID**, not DOI. Use the
  raw hash returned by the existing `POST /api/sources/manual` upload. Only blocked
  pairs for these references are resumed; completed pairs remain immutable.
  Failed tasks require `retry_failed=true`, an allowed failure reason, and available attempts.

Job/task/outcome/events commit together using fsync and atomic replace, with a
versioned SHA-256 envelope and optimistic revision guard. Source preparation and
verification reuse the Phase 1 core. Running tasks are checkpointed before I/O;
each outcome is checkpointed before processing the next pair.

On restart, committed completed results are reused. Running attempts become
pending under an interrupted job (or failed if attempts are exhausted). Startup
does not call providers. Resume is explicit. Uncommitted requests may execute
again: this does **not** guarantee exactly-once model calls. Raw source hash and
previous source version preconditions are checked again during preparation.
Snapshots never rely on memory:// locators to reconstruct a source index.

Shutdown drains workers for up to 30 seconds, then interrupts outstanding work.
Storage failures stop the worker and produce an explicit API error; the last
valid disk snapshot remains authoritative. Corrupt snapshots are never replaced
with empty jobs. A checksum detects accidental corruption, not hostile tampering.

Completed means processing coverage, regardless of the scientific verdict. Empty
extractions and attribution/extraction gaps yield partial coverage. SSE, frontend
job pages, database persistence, and multi-process execution are not implemented.
