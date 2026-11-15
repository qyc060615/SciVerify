# Whole-paper five-stage workflow

Baseline: develop, 23fbf97. No commit or push is performed by this task.

## User flow

1. **Upload** — accessible PDF picker/dropzone with actual filename, size and backend upload limit. Parse is an explicit, deduplicated request. On success the picker is replaced by a compact summary and the UI opens References. Replace PDF clears parse/identity/review/extraction/confirmation state. Raw parser titles stay in details; filenames identify the current manuscript.
2. **References** — explicit identity resolution and review. Compact rows show reference number, title, DOI/URL and identity status. Original metadata, candidate evidence and diagnostic codes are collapsed. The list scrolls inside its panel, keeping Continue to Claims near the list. Upload is optional and does not rerun manuscript parsing.
3. **Claims** — user-triggered model extraction, cost warning and deduplication. Read-only Claim text/attribution/reference labels; original context, Unicode code-point spans, callouts and diagnostics remain accessible. Diagnostics are grouped by code and raw records are retained, avoiding duplicate display of the same aggregate/context copy. Extraction failures/zero pairs cannot advance. Re-extraction is secondary and clears review/partial confirmation.
4. **Verification** — actual executable pair count, excluded claims, ambiguous/unresolved counts, cost warning and explicit Start. Partial extraction still requires the original checkbox. Step navigation does not create jobs or bypass review/confirmation. Job Create DTO/fingerprint/locator bridge are unchanged.
5. **Report** — existing durable URL and SSE/query hook. Overview separates processing from scientific verdicts. Desktop Claim navigator/detail columns become a single column on mobile. One selected Claim is shown; its reference pairs retain separate verdicts, valid confidence, explanation and original evidence. The first backend-ordered evidence is expanded. Other evidence and technical audit fields are collapsed.

Completed preparation stages can be revisited. Saved-job preparation views are read-only and cannot rerun extraction/create a duplicate job. The Report section stays mounted while revisiting steps so recovery state and the selected Claim are preserved.

## Pre-job sources: real persistence, not optimistic upload cards

The existing POST /api/sources/manual is reused unchanged. It validates PDF type/size/readability and identity against the target DOI, writes real raw PDF bytes through LocalSourceStore, and returns the raw SHA-256. The reference-to-source association is the exact reference DOI; no fake DOI/Reference ID or new scientific binding is created in the browser.

The only backend addition is read-only POST /api/sources/status, accepting the existing SourceLocator shape. It reads the current DOI/URL pointer via LocalSourceStore.get_locator, verifies the stored bytes/hash/metadata and confirms the artifact is recorded as full text in the same format. It returns availability, real format/hash and an explicit remote_status=not_checked. It performs no remote retrieval, no writes and no model calls. It is loopback-only and no-store; no server paths or credentials are returned.

A usable current cached file shows Available locally and hides upload. No cache hit is shown as Full text: Not checked, with a secondary Add Source inside source details. It is never equated with missing remote full text. Upload success is followed by a fresh status read and an exact receipt-hash check before the UI reports the saved source as confirmed. Stale/failed checks cannot show a green available status. Neither PDF bytes nor source receipts are put into localStorage.

Production retrieve_paper checks the same source store before remote discovery. The integration test uploads a real PDF before creating the job, forbids external retrieval, executes the existing job/core using offline verifier/evidence fixtures and proves the production cached reader returned cache_hit and the task pinned the uploaded raw SHA-256. It is offline integration with real persistence, not live scientific/model E2E.

### Compatibility limits

- Manual PDF upload currently requires a DOI. URL-only references retain their existing report-page Fetch URL source and explicit Resume flow. A safe URL-only manual-PDF endpoint would additionally need a matching identity-validation contract; it is not fabricated in this redesign.
- Pre-job upload registers the current DOI source pointer, not a new hash field in Job Create. The unmodified job core pins the actual source/version it uses. An intervening upload of another version for the same DOI can change that pointer before a job reads it; the report exposes the actual pinned version.
- Source status confirms local stored bytes, not remote availability or scientific support. Upload still uses existing metadata-resolution services to validate identity.

## Report semantics and recovery

The DomainVerdict display mapping is unchanged. Failed/blocked/incomplete tasks show no scientific verdict or confidence even if a retained outcome exists. Insufficient evidence stays distinct from contradiction; completed processing never implies support. Confidence is shown only for finite values within [0,1]. HTML evidence receives no fabricated PDF page. Exact/probable identity and historical-version warnings remain beside the result.

Recovery is colocated with the selected Claim, with a top-level issue shortcut. The existing recovery functions retain Reference ID selection, actual uploaded hash, latest revision validation, source-version conflicts, explicit paid Resume, 409 refresh/reconfirmation and separate retry_failed behavior. Hidden reference groups stay mounted so switching Claims does not discard a pending accepted upload. Completed pairs are not rerun.

Job ID, version/hash, source document/evidence IDs, traceability metadata, original reason/warning codes and diagnostics remain available in technical details. Report references preserve original DOI/URL/raw reference text and candidate metadata.

Recent Local Jobs keeps the original localStorage key/ID envelope/limit. Metadata is read lazily when expanded through existing job GETs. Recorded titles/status are used only when returned; missing data falls back to Job ID. No timestamp exists in the current JobView, so none is invented. Raw manuscript titles are labeled recorded/not independently verified. A filename from navigation state is used when available; direct saved URLs fall back to the persistent Job ID.

## Files

Modified:
- frontend/src/pages/WholePaperVerifyPage.tsx — local five-stage preparation state and gates.
- frontend/src/pages/WholePaperJobPage.tsx — persistent Report stage/read-only look-back.
- frontend/src/components/manuscript/ReferenceReview.tsx — compact identities and optional source handling.
- frontend/src/components/manuscript/ClaimExtractionPreview.tsx — read-only layered Claim review.
- frontend/src/components/manuscript/WholePaperReport.tsx — selected Claim/pair/evidence report.
- frontend/src/components/manuscript/JobSourceRecovery.tsx — placement/filtering, preserved recovery state, clearer action labels.
- backend/app/api/routes/sources.py — additive read-only source-status route; original upload contract unchanged.
- frontend/tests/whole-paper-ui.test.tsx and whole-paper-recovery.test.tsx — adapt original interactions/assertions and extend stage/report/recovery coverage; no tests removed.

Added:
- frontend/src/components/manuscript/WorkflowStepper.tsx
- frontend/src/components/manuscript/PdfPicker.tsx
- frontend/src/components/manuscript/DiagnosticDetails.tsx
- frontend/src/components/manuscript/RecentLocalJobs.tsx
- frontend/src/services/sourceService.ts
- frontend/tests/reference-sources.test.tsx
- backend/app/tests/test_source_status.py
- docs/WHOLE_PAPER_FRONTEND_REDESIGN.md

History, Repository, source storage layout, M3/M4 algorithms, Agent/Validator, verdict mapping, job create/SSE/resume schemas and the recent-ID storage format are unchanged.

## Validation boundary

New and existing tests cover explicit parse/resolve/review/extract/create, duplicate prevention, PDF replacement reset, unknown vs available sources, pre-upload hash confirmation, real later-job cache reuse, ambiguous exclusion, partial confirmation, separate pair verdicts, invalid confidence, saved-job restoration, SSE behavior, 409/version recovery and Claim switching with accepted uploads.

The responsive implementation uses bounded scroll regions, a five-column wrapping Stepper, breakable DOI/hash content and an lg-only report column layout. The browser tool inventory returned no connected browsers, so real desktop/mobile rendered overflow checks and browser E2E were not available. jsdom/ASGI tests are not claimed as browser or live model E2E. No real paid model calls were made.

The backend must be restarted after running jobs finish to load the additive source-status route. Existing running jobs were not interrupted for this UI work.

### Final results (2026-10-28)

- Frontend: `npm run test` — 156 passed across 14 files; `npm run lint` — passed without warnings; `npm run build` — passed, retaining Vite's existing large-bundle warning.
- Backend: source status + source lifecycle + verification job API suites — 91 passed. The existing Starlette/httpx deprecation warning remains.
- The pre-upload integration used a real PDF, real content-addressed source files, actual job persistence and the production cached-paper reader, with offline evidence/verifier fixtures and forbidden remote retrieval. The later task pinned the uploaded SHA-256.
- Browser inventory: no connected browser. Rendered desktop/mobile acceptance and live model E2E were not run; no model charges were triggered.
- `git diff --check` passed. Protected History, Repository, scientific core, bridge DTO, job services and SSE hook files have no changes.
