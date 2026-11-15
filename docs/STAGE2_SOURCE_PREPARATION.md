# Stage 2 source preparation and Stage 4 reuse

Date: 2026-10-29. Branch: develop; HEAD before work: `3df9c0b`.
The preceding uncommitted Stage 2–5 layout changes were retained. No commit/push or live service restart was performed.

## Files changed in this task

Backend:
- `app/api/routes/sources.py`: additive loopback-only `/prepare` and `/manual-reference` endpoints. Existing `/status` and DOI `/manual` contracts remain intact.
- `app/services/source_preparation.py` (new): pre-job reference eligibility, local checks, acquisition projection and real durability verification.
- `app/services/source_requests.py` (new): per-source in-process lock coordination, shared by prefetch and normal verification readers.
- `app/services/paper_retriever.py`: optional cache-only reading, explicit invalid-cache rejection and per-DOI coordination. Existing DOI discovery/download logic and `/api/papers/retrieve` DTOs are reused.
- `app/services/source_acquisition.py`: local-only DOI/URL source preparation, URL cache validation/fallback and preservation of manual upload provenance.
- `app/services/manual_source.py`: URL-only PDF validation using the existing parser, substantial-document checks, strong title matching and shared Source Store. DOI upload behavior remains intact.
- `app/services/source_store.py`: repair corrupt bytes only when they fail their own content-addressed hash, using incoming hash-verified bytes. Healthy versions, metadata and locator/index structure remain unchanged.
- `app/tests/test_source_preparation.py` (new): 25 offline preparation/reuse/fallback/security tests, including actual HTTP handlers, source files, hashes and durable job execution.

Frontend:
- `src/pages/WholePaperVerifyPage.tsx`: automatically resolve identities after parsing; allow continuing while source preparation is unfinished. Existing explicit review, paid start, partial gate and create deduplication remain.
- `src/components/manuscript/ReferenceReview.tsx`: automatically prepare each source, compact loading/available/missing/attention display, direct failure upload/retry, verified receipts and alias refresh.
- `src/services/sourceService.ts`: existing DOI retrieval call, pre-job checks/URL acquisition, cancellation, two-preparation concurrency limit, DOI in-flight deduplication and upload association.
- `tests/reference-sources.test.tsx`, `tests/whole-paper-ui.test.tsx`: adapt existing tests and extend cache retention, cancellation, unfinished-source continuation, real upload confirmation and alias refresh assertions.
- `tests/source-preparation.test.ts` (new): actual frontend orchestration with controlled HTTP responses, local-hit/no-download, DOI/URL paths, persistence failure, identity/fetch errors, deduplication, queue cancellation and reference association.
- This document.

Other modified files visible in git status belong to the preceding uncommitted UI task. This task did not redesign Claims, Report, Settings, History, Repository or Sidebar.

## Stage 2 flow

1. Parsing transitions to References and automatically resolves reference identities. A failed identity request can still be retried explicitly.
2. Each reference is checked through `POST /api/sources/prepare` with `{reference, retrieve:false}`. Backend local-only readers parse/check the cached document, recheck the reference association and validate actual persisted bytes/hash/format.
3. A local hit is immediately reusable. An ambiguous/unresolved or unsafe target becomes Needs Attention, with no guessed download.
4. On a local miss, DOI references call the original `POST /api/papers/retrieve` with `{doi}`. Afterwards a local-only `/prepare` confirms persistence and association. HTTP 200/success alone is insufficient.
5. URL-only references call `/prepare` with `{reference, retrieve:true}`. This uses the existing `retrieve_reference_source` / `retrieve_url_source` implementation and verifies durability before returning available. It requires no Job or Revision.
6. Failed rows display Upload PDF and Retry where eligible. Each retry repeats the real local-first preparation once; automatic retries are disabled.
7. Continue to Claims stays enabled while automatic preparations run or some sources are missing. Manual upload retains the existing busy gate until its receipt is checked.

UI semantics: loading means queued/checking/fetching; green means verified persistent reusable full text; red means preparation failed or no usable full text; yellow means reference/source identity needs attention; grey means not checked. Exact backend state/reason, source/provider/format/hash and version warnings stay in More details. These are availability states, not scientific verdicts.

Query results are retained in the app QueryClient for 30 minutes without mount/window-focus re-fetches. A browser refresh starts with a real local check, so saved files are not downloaded again. No PDF, fake source record or optimistic availability is written to localStorage. An upload revalidates same-locator aliases independently and does not retry unrelated references.

## Upload, identity, persistence

DOI uploads use the unchanged `/api/sources/manual` and its DOI or title/author/year validation. URL-only uploads use `/api/sources/manual-reference`, with the actual serialized Reference and PDF multipart parts. A substantive readable PDF plus a sufficiently specific matching title are required; weak/absent titles or mismatches are rejected. This conservative path does not let an arbitrary file establish a URL association. Manual bytes have no fabricated download URL or final URL.

The shared store remains content-addressed: DOI/URL index → actual SHA-256 → PDF/HTML bytes and metadata. `verify_source_durability` rereads the artifact and checks locator, paper identity, hash, format and origin. Preparation also requires accepted full-text content and usable chunks. Source association uses the same application-layer reference reader as M4. Accepted identity/version uncertainty warnings remain available; a green availability mark does not certify an exact historical cited version.

If DOI retrieval reports success but the source cannot be confirmed locally, the frontend reports `SOURCE_PERSISTENCE_UNCONFIRMED`, never green. Store write/hash errors remain safe, explicit preparation failures. Server paths and exception details are not included in preparation errors.

## Stage 4 and recovery

No changes were made to manuscript verification, PaperQA2, Agent execution, pair planning, evidence retrieval, DomainVerdict, Job DTOs, persisted snapshots, SSE, expected revision, source hash, Resume or 409 handling.

The existing core already memoizes source preparation across pairs. Its production reader now shares the same local-only/validated cache behavior and per-source locks with Stage 2. Valid sources avoid network full-text retrieval; evidence retrieval and the prepared verifier still run per executable pair.

Network acquisition remains available when Stage 2 was skipped, failed or unfinished, or when a local artifact is missing, corrupt, not full text or fails identity validation. Normal bounded provider/download fallback is reused. Healthy content-addressed versions are preserved; a downloaded artifact may repair corrupt bytes only if the incoming content verifies to the exact expected hash. A different valid version has a different address. Fallback failures retain existing blocked_source/processing failure and explicit Source Recovery/Resume behavior. Completed pairs are not rerun.

## Cancellation, concurrency and URL safety

- Frontend: two active preparations, shared DOI in-flight requests, no unlimited retry, 120-second local-check and 180-second acquisition client limits. Unmount aborts active/queued UI requests; cancelled queries cannot commit success into an unmounted component. Upload UI updates check mount state.
- A synchronous server download already in progress may finish after a client disconnects. It uses the existing bounded provider/HTTP timeouts. Per-source in-process locks prevent the same source being downloaded concurrently by Stage 2 and Stage 4; the next caller checks the persisted artifact after acquiring the lock.
- Coordination targets the existing single-worker local launcher. It is not a new distributed scheduler or cross-process lock service. Multiple backend processes would need cross-process coordination to guarantee the same download deduplication.
- URL acquisition uses existing public HTTP/DNS-pinned transport, validates each redirect, rejects private/loopback/metadata targets, enforces size/type/time limits and rejects abstract/landing/error/anti-bot/paywall content. No access-control bypass was added.

## Verified chain and test evidence

`Reference → DOI/URL → Retrieve → Persist → SHA-256 → Stage 4 local cache hit → Evidence Retrieval → Verification`

`test_stage2_to_stage4_real_local_hit_evidence_verification_and_hash` runs DOI/PDF and URL/HTML through real ASGI endpoints, real parsing/files/store, and the actual durable Job runtime. In the prepared scenario it forbids metadata/download access before starting Stage 4 and asserts:

- exactly one initial controlled document download;
- `hits == [True]` for source preparation shared by two independent pairs;
- two evidence queries and two prepared-verifier invocations;
- both tasks pin `sha256:` plus the Stage 2 file digest;
- both tasks retain real fixture evidence and independent verdicts.

Skipped, missing-file and corrupt-file variants prove bounded fallback and reuse across two pairs. Failed-fallback variants assert waiting_for_source, blocked_source, zero evidence queries and zero verifier calls. Other tests cover storage failure despite successful retrieval, unsafe initial URLs/redirects, abstracts/errors, ambiguous targets, direct upload, wrong PDFs, per-source concurrent requests and manual origin preservation.

These are offline integration tests with MockTransport download responses and injected evidence/verifier fixtures, not public-network or paid-model scientific E2E. Existing PaperQA2/Agent/SSE/Resume/version-conflict regressions also ran in the complete backend suite.

## Final validation

- Frontend `npm run test`: 189 passed, 15 files.
- Frontend `npm run lint`: passed without warnings.
- Frontend `npm run build`: passed, including TypeScript checking. Existing >500 kB bundle warning remains.
- Backend project command, using its configured researchguard environment: `D:/conda_envs/researchguard/python.exe -m pytest -q --tb=short`: 1589 passed, 1 skipped. Existing Starlette/httpx deprecation warning remains. No separate backend type/lint script is configured.
- `git diff --check`: passed.
- No paid model calls, live public-source batch downloads, browser screenshots or mobile rendered acceptance were performed.
- Restart the backend after running jobs finish to load the additive endpoints, then refresh the frontend. Existing live services/jobs were not interrupted.
