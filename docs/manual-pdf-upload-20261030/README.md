# Manual PDF upload validation — 2026-10-30

Branch: `develop`; unchanged HEAD: `2f777ea9f985d367cfa69a4cfe8222d6d9730ea2`.

Manual selection binds the file to a cited Locator; it is not proof that the PDF
contains that DOI. A readable PDF with usable body text is accepted unless its
identity region provides definite contrary evidence. A reliable title or printed
matching DOI confirms identity. Missing identity evidence is accepted as
`UNCERTAIN`, with manual-selection provenance and version warnings.

The same manual identity review is used by upload, Step 2 checks and Step 4 source
acquisition. Accepted uploads update the current Locator pointer. Prior raw files
remain intact. When identical bytes already exist, prior acquisition metadata is
retained in a `.previous` sidecar before writing manual provenance.

Reference rows show `Uploading PDF...` immediately, then `Validating Source...`
while checking the saved source. Green requires an available reread with the
receipt's valid SHA-256. Errors end loading and allow another upload. The matching
reference query is cancelled before upload and updated after confirmation; other
aliases of the same Locator are invalidated.

## Real local files

`validate_local.py` posts both real PDFs to the application route in an isolated
temporary Source Store, then invokes the actual Step 2 and Step 4 source readers
and verifies persisted bytes, Locator binding, provenance and SHA-256. Public
network access is blocked. No model or scientific verdict is requested. Current
Demo cache and jobs are untouched.

- R10, CVPR ResNet: old cached identity conflict → `available / CONFIRMED`, using
  the PDF's title without requiring DOI, authors or year together.
  Hash: `51b5de45eb0b558b19c3affe49503cff50cb170a32de602983d6e2ec286942a7`.
  Step 4 reads 74 chunks with the same hash. The old conflicting PDF is still
  identified as conflicting and its bytes are preserved.
- R12, LSTM: no local source → `available / CONFIRMED`, using its title despite
  legacy font extraction spacing.
  Hash: `ceb9e53dbc0493f5b3bf5520ed940f3e6b526064d17b2118d77e51f79c0edcc6`.
  Step 4 reads 920 chunks with the same hash.

Both retain `HISTORICAL_VERSION_UNCONFIRMED`. Neither records the user-selected DOI
as a DOI found in the PDF. Machine-readable results: `real-pdf-results.json`.

## Checks

- Backend selected regression suite: 364 passed. Includes manual upload policy,
  source lifecycle, preparation, confirmation, unified sources, local recovery,
  paper retrieval, source status, identity generalization, lenient acquisition,
  verification jobs/API and manuscript verification.
- Frontend `npm run test -- --reporter=dot`: 254 passed in 16 files. Includes
  conflict → uploading → validating → uncertain green, failed-upload retry,
  saved-hash mismatch, source aliases and existing Step 2 continuation tests.
- Frontend `npm run lint`: passed.
- Frontend `npm run build`: passed; existing large bundle advisory remains.
- `git diff --check`: passed.

The frontend phase checks use component tests, not a browser session. The running
Demo backend does not auto-reload; restart it to load these changes, then upload
through the page. No Commit/Push; no paid models; no scientific algorithm changes.
