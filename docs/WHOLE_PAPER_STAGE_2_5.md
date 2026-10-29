# Whole-paper Stage 2–5 refinement

Baseline: `develop`, `3df9c0b`. Stage 1 is unchanged. No commit or push.

## Interface

- References: compact numbered title rows, full-text status at the right, natural page scrolling. DOI, identities, provider, URLs, candidate evidence and actual local hash/format are in More details. Parsing and reference diagnostics are combined under bottom Warnings, with original records retained. Reference review and Continue to Claims remain explicit.
- Claims: input extraction order is retained without sorting. Resolved attribution is a green check; all other attribution states use yellow attention. Exact attribution, original paragraph, callouts, references and code-point spans are retained in More details. Context results, rejected proposals and diagnostics are folded at the bottom. Partial extraction still requires confirmation before Start.
- Start: executable pair count, a short attention count when applicable, API cost notice, partial confirmation and explicit Start. No new configuration. Existing action guards and Job Create DTO are unchanged.
- Report: a single column of all claims, without a Claim navigator or internal list scrolling. Each card has the claim, independent pair verdict labels, and More details. Only a genuinely single-reference claim displays the backend pair explanation as its default opinion, visually limited to two lines; the full text remains in details. Multi-reference claims never receive a synthesized opinion or verdict. Up to three pairs display reference-labelled statuses; larger groups use a neutral result count.
- Report details retain per-reference titles, verdicts, valid confidence, complete explanations, original evidence, actual source links and recorded section/page. Hashes, traceability, version and runtime records remain in secondary Technical Details. Global references are folded into bottom Technical Details & Diagnostics and loaded only when expanded.
- Source recovery: eligible references have shortcuts at the report top; opening one expands its recovery controls above claims. Accepted uploads remain mounted while changing reference selection. Completed reports without eligible issues have no recovery module.

## Real source status and limits

The existing source-store API and persistence implementation were inspected; no backend changes were made.

`POST /api/sources/manual` validates DOI/PDF identity and persists actual bytes and metadata through LocalSourceStore. Its content-addressed file is located through the DOI pointer. The production paper retriever reads this same store before remote retrieval, so pre-job uploads remain reusable. Upload success is still confirmed against a new status read with the exact returned SHA-256. No PDF bytes or invented source records are stored in localStorage. Repository continues reading the original persisted records unchanged.

`POST /api/sources/status` verifies current local bytes and metadata. It returns either `available` or `not_cached`, always with `remote_status=not_checked`. A valid file/hash/format is green; checking is a lightweight loading indicator. No confirmed cache or an unsuccessful status read remains grey/unknown. The summary says “not confirmed”, not “missing”. A DOI resolution never makes a source available.

**Stage 2 currently has no existing remote-fetch or remote-failure result to consume.** It therefore cannot honestly produce a red “remote full text missing” row or a remote retrieval Retry button. Add Source remains inside More details for unchecked DOI references; a failed local status read offers a real status-check retry. The known full-text recovery and processing retry actions remain available in Stage 5, using actual job task state. No Stage 2 Resume request is made. To add confirmed Stage 2 remote-missing states later would require a pre-job retrieval result/contract; this frontend task does not introduce one.

URL-only manual PDF validation remains unsupported by the existing upload contract. Existing URL acquisition and explicit paid Resume remain available in Report. Pre-upload updates a current DOI pointer; it does not pre-pin the future job. The unmodified core pins the version actually read when verification starts.

## Scientific and recovery contracts

Only completed tasks with completed verification results and a real DomainVerdict display scientific verdicts. Pending/running/blocked/failed states are processing states. Invalid, missing or verdict-less confidence is hidden. Processing progress is not a support percentage. Scientific verdicts retain their original semantics; Overstated uses an orange visual treatment.

SourceRecovery eligibility helpers were moved unchanged into a shared frontend service so report shortcuts and the existing controls use the same rules. Upload, exact hash under Reference ID, expected revision, explicit Resume, retry_failed, 409 refresh/reconfirmation and version-conflict behavior are unchanged. Upload never automatically resumes. Completed pairs are not rerun. Job persistence, GET restoration, SSE hook, bridge, backend schemas and science code are unchanged.

## Files

- `frontend/src/pages/WholePaperVerifyPage.tsx`
- `frontend/src/pages/WholePaperJobPage.tsx`
- `frontend/src/components/manuscript/ReferenceReview.tsx`
- `frontend/src/components/manuscript/ClaimExtractionPreview.tsx`
- `frontend/src/components/manuscript/WholePaperReport.tsx`
- `frontend/src/components/manuscript/JobSourceRecovery.tsx`
- `frontend/src/components/manuscript/DiagnosticDetails.tsx`
- `frontend/src/services/sourceRecovery.ts` (new)
- `frontend/tests/reference-sources.test.tsx`
- `frontend/tests/whole-paper-ui.test.tsx`
- This document (new).

## Verification

- `npm run test`: 171 passed across 14 files. Existing tests were adapted, none removed. New coverage includes compact/unknown/loading source states, source-status retry, claim order and two attribution visuals, simultaneous report cards, multi-reference partial scheduling, independent pair outcomes, stale-result guards, absent/invalid confidence and report recovery shortcuts. Existing preupload, duplicate-job, partial gate, saved-job, SSE, hash/revision, 409, URL acquisition and explicit Resume tests pass.
- `npm run lint`: passed without warnings.
- `npm run build`: passed. Existing >500 kB chunk-size warning remains.
- Browser inventory exposed no connected browser. A native Edge inspection was attempted using the computer-use skill, but Computer Use stopped because it could not reliably determine the browser URL for policy enforcement. No further browser input was issued. Desktop/mobile screenshots, rendered overflow acceptance and browser E2E remain unverified. jsdom tests do not establish pixel-level layout correctness.
- No paid model calls or live scientific E2E were performed.
