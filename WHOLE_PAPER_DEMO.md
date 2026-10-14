# Whole-paper local demo

This integrates the existing M3A parser, M3B extraction and durable M4 jobs.
It is a local single-user demo. M3B scientific extraction fidelity remains open;
the UI requires review and reports coverage gaps rather than asserting complete
scientific correctness.

## Start

Use one backend process on loopback, with your configured local GROBID service
and model settings. Set `RESEARCHGUARD_JOBS_ENABLED=1` in the backend environment
(the project loads `backend/.env` with override enabled). Jobs remain off by
default. Keep keys out of committed files.

From `backend/`:

```powershell
& 'D:\conda_envs\researchguard\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

From `frontend/`:

```powershell
$env:VITE_LOCAL_DEMO_MODE='true'
$env:VITE_API_BASE_URL='http://127.0.0.1:8000'
npm run dev -- --host 127.0.0.1
```

Open `/app/manuscripts`. These routes and navigation are gated by the existing
development-only `isLocalDemoMode()`. A production build does not expose this
demo flow. Supabase and single-claim history are independent of whole-paper jobs.

## Workflow and contracts

1. Upload the manuscript PDF; GET `/api/manuscripts/limits` supplies actual PDF
   bounds. POST `/api/manuscripts/parse` returns a public DTO and safe diagnostics.
2. Explicitly extract claims (an external LLM may incur fees), then inspect text,
   citations, references, attribution and code-point spans. Claims are read-only.
3. Start verification explicitly after the cost warning. Partial extraction
   requires separate confirmation; failed/empty extraction cannot start a job.
4. Open `/app/manuscripts/jobs/{jobId}` for progress, separate reference pairs,
   original evidence and technical traceability. Refresh reads the saved job.
5. Upload a matching cited PDF for recoverable sources. Upload returns the actual
   raw SHA-256; review Reference IDs and confirm selective Resume with the latest
   revision. The source hash map uses Reference IDs, including DOI aliases.
   A 409 refreshes the report and requires confirmation, without blind retries.
6. Retry eligible processing failures separately using `retry_failed=true`.
   Completed pairs remain immutable and never rerun through Resume.

`manuscriptBridge.ts` mirrors M3B `from_request()` exactly: preserve the DTO,
add `submitted:client-structure` as the internal locator, and default internal
diagnostics to `[]`. Outer M3A diagnostics are display-only. No frontend hash,
ID, offset, attribution or scientific verdict is recomputed. Shared Unicode
fixtures are checked against the actual backend bridge.

## Real-time updates

GET `/api/verification/jobs/{jobId}/stream` projects persisted EventRecord JSON:

```text
id: 12
event: job
data: {"job_id":"...","sequence":12,...}
```

`Last-Event-ID` takes precedence over `after=N`. Invalid/ahead cursors fail
explicitly. The stream polls at one second, sends a comment heartbeat every
15 seconds, releases read locks before yielding and exits on disconnect or
completed/failed jobs. Storage errors after headers use an unnumbered
`stream_error` control message, never a fabricated durable event.

The frontend deduplicates sequences and coalesces notifications for 150 ms.
TanStack Query owns the snapshot; older revisions cannot overwrite newer ones.
Stream errors retain results and fall back to three-second GET/reconnect attempts.
Routes and unmounts close streams and timers. SSE failure is not a scientific
verification failure. Runtime error codes remain independent diagnostics.

## Report semantics and limits

Each Claim–Reference pair has its own domain verdict. `CONTRADICTED` may accompany
completed processing. Blocked, failed, pending and running tasks show no semantic
verdict or confidence. `INSUFFICIENT` never maps to `FABRICATED`. Progress uses
completed / total pairs, with extraction and attribution coverage gaps visible.
HTML evidence legitimately has no PDF page. Identity is confirmed, uncertain or
unknown based on backend provenance; it is never inferred by the UI.

Only eight recent job IDs are optionally stored in localStorage. Full manuscript
text and reports remain in the backend snapshots. There is no job synchronization
to Supabase, multi-user authentication, distributed worker or public deployment.
Uncertain source identity and PDF/HTML parser limitations remain applicable.

## Validation

New tests cover the contract bridge, local-only SSE/cursors/heartbeats/disconnects,
revision races, explicit cost gates, source hashes and selective recovery. Existing
single-claim and Supabase tests remain intact. Browser QA can use deterministic
providers and real temporary JSON/PDF persistence; that is **OFFLINE E2E**, even
when the real browser, HTTP routes and SSE transport run. Full **LIVE E2E** needs
a real manuscript, GROBID and approved model costs and must be reported separately.

## Phase 3 acceptance (2026-10-14)

| Stage | Main deliverable | Validation |
| --- | --- | --- |
| 1 | Typed DTO bridge and shared Unicode fixture | Backend HTTP bridge, fingerprint equality, multi-reference/missing DOI/ambiguous attribution; frontend golden payload tests |
| 2 | Manuscript upload and extraction review | PDF bounds, read-only previews, partial/failed/empty states and explicit cost gates |
| 3 | Durable job URL and snapshot report | Single create, direct-route restoration and backend error messages |
| 4 | Local-only durable event SSE | Cursor precedence, replay, heartbeat, bounded payload, disconnect and resume |
| 5 | Query-owned snapshot and transport fallback | Sequence deduplication, revision ordering, in-flight event races, reconnect and cleanup |
| 6 | Pair-specific report and evidence | Domain verdict mapping, incomplete processing, Unicode spans and uncertain/unknown identity |
| 7 | Existing source upload and selective resume | Actual raw hash, Reference ID mapping, revision/hash conflicts and separate failed-task retry |
| 8 | Full regression and actual browser QA | 1151 backend passed / 1 skipped; 108 frontend passed; build and lint passed |

Actual headless Chrome browser acceptance used the real Vite frontend, loopback
HTTP routes and SSE against an explicitly isolated **offline** parser/provider/
verifier harness. It passed PDF upload, extraction, job creation, event reception,
browser refresh, matching manual PDF validation/persistence, selective resume,
desktop/mobile layout and evidence expansion. Parse/extract/create/resume each
issued one POST. Verifier calls increased from 1 to 2 after recovery; exactly one
job persisted, and the existing completed pair did not rerun. There were no browser
exceptions or mobile horizontal overflow.

**LIVE E2E: NOT RUN.** No real LLM, embedding or GROBID calls were made. Full live
scientific/model acceptance remains pending. The existing Starlette/httpx warning,
the skipped opt-in GROBID smoke test and the Vite large-bundle warning are recorded;
no tests or checks were disabled to hide failures.
