# ResearchGuard M2 implementation report

Completed locally on 2026-10-08 (Asia/Shanghai), on develop starting from
cbaf909185f2b2ba329bc02eb25f6c293a19a5df. No commit or push was performed.

1. **Python version/path.** The existing Conda researchguard environment provides
   Python 3.11.17 at D:/conda_envs/researchguard/python.exe. python --version and
   where.exe python were run with that environment first on PATH. No venv was created.
   python-multipart 0.0.32 was installed in this environment and added to requirements.

2. **Files changed/added.** See the complete inventory below. The implementation
   adds lifecycle glue and a dedicated recovery component while reusing existing
   discovery, parsing, chunking, PaperQA and verifier functionality.

3. **Artifact design.** AcceptedSourceArtifact is an internal dataclass holding
   normalized DOI, exact raw bytes, raw_content_sha256, PDF/HTML format, source URL,
   original provider, remote/manual origin and a copied canonical PaperMetadata.
   Bytes and filesystem paths are absent from domain and response schemas.

4. **Filesystem layout.** backend/data/researchguard/sources/doi/<DOI SHA>.json
   points to a raw SHA directory. That directory contains source.pdf or source.html
   and <DOI SHA>.json metadata. Per-DOI metadata supports aliases sharing bytes.
   Atomic file replacement and pointer-last publication avoid partial acceptance.
   The root is configurable and gitignored; corrupt or missing entries safely miss.

5. **Hash semantics.** raw_content_sha256 hashes exact raw bytes.
   SourceDocument.content_hash uses sha256:<raw SHA> when an artifact exists.
   parsed_content_fingerprint separately hashes chunk IDs/text/sections/pages.
   Artifact-free M1 fixtures retain the explicitly marked parsed_chunks hash.
   The PaperQA index fingerprint is a separate source/configuration identity.

6. **Automatic flow.** Normalize DOI, inspect/validate the local artifact, parse/chunk
   on hit and skip all metadata/provider/download calls. On miss, run the existing
   SciVerify resolver and Europe PMC/OpenAlex/Unpaywall/Semantic Scholar discovery.
   Persist a successfully parsed/chunked accepted candidate's exact bytes, then use
   the same downstream verification path. An automatic cache write error allows the
   current verification to proceed with a safe warning.

7. **Upload API.** POST /api/sources/manual, multipart doi + file. PDF only, non-empty,
   default 20 MiB, %PDF- signature, readable unencrypted PDF with extractable text.
   Internally generated paths ignore the uploaded filename. Success returns accepted,
   DOI, raw hash and matching method. Structured safe failure codes cover invalid
   DOI/PDF, oversized file, SOURCE_MISMATCH, metadata failure and storage failure.

8. **Matching algorithm.** Canonical metadata comes from the existing DOI resolver.
   Expected DOI must be the sole normalized DOI in PDF identity metadata or the
   first-page header (up to 4000 characters before body/reference headings). If no
   DOI is present, require a contiguous canonical title after NFKC/case/punctuation/
   whitespace normalization, at least six words and 35 characters, in the first
   2000 header characters or Title metadata; also require a canonical author surname
   of at least three characters and the publication year in the header. Conflicting
   DOI evidence rejects fallback. Body/bibliography mentions cannot establish identity.
   No LLM or paper discovery is used. The exact policy is documented and tested.

9. **Recovery semantics.** FULL_TEXT_UNAVAILABLE, METADATA_ONLY and PARSING_FAILURE
   after DOI resolution return source_required with paper identity and structured
   recovery reason/upload limit. Verdict, confidence, agents, evidence and semantic
   traceability are absent; the response schema enforces this. NO_CHUNKS and
   NO_RELEVANT_EVIDENCE can still produce scientific INSUFFICIENT after a usable source.

10. **Frontend UX.** The service recognizes source_required as a typed recovery
    signal. VerifyPage keeps claim, citation/source label and context. The PDF panel
    displays paper identity and the size limit, uploads DOI+PDF, allows another PDF
    after safe failures, and automatically retries original input on success. No fake
    report/history entry is produced while a source is missing. The backend request
    remains claim + DOI. Failed verification retries can reuse the preserved input.

11. **Index-cache key/lifecycle.** Bounded LRU (default 8, 0 disables), event-loop-local
    within the process; startup/shutdown clear it. The key hashes SourceDocument,
    canonical chunk payload, PaperQA 2026.8.12, embedding model/base/timeout,
    credential fingerprint and defer_embedding=false. Injected embedding objects add
    object identity and are retained to avoid ID reuse. A simple build lock avoids
    duplicate indexing; per-source query locks protect lazy text-index construction.
    Source byte/chunk/embedding changes invalidate reuse. No persisted vector index.
    Each claim creates a fresh PaperQA session/summary/selection; failures stay explicit.

12. **Demonstrable reuse.** Real pinned PaperQA tests assert exactly one source
    embedding batch plus two query embedding calls for two claims, one aadd_texts
    invocation, fresh context session IDs/summaries, and concurrent single indexing.
    Production-style model construction also reuses an index across summary changes.

13. **New tests.** 53 backend cases cover persistence, automatic cache miss/hit,
    corrupt entries, alias identity, raw hash/provenance, real PDF matching/rejection,
    safe filenames/size/errors, semantic separation/schema invariants, real index
    reuse/concurrency/invalidation/LRU/disable/failed builds, E2E recovery, and safe
    verifier logs. Eight frontend tests cover typed recovery, multipart upload,
    failure/oversize handling, another-file retry and complete VerifyPage upload →
    original-request retry → report-save behavior with context preserved.
    The earlier unavailable-source regression was updated to the corrected semantics.

14. **Final backend result.** 610 passed, 1 warning in 22.34s using
    D:/conda_envs/researchguard/python.exe -m pytest -q. The warning is the installed
    Starlette/httpx TestClient deprecation. Public networking is blocked in the suite.

15. **Frontend results.** npm run test: 8 passed (one test file). npm run build:
    passed (TypeScript + Vite production build), with the existing large-bundle
    warning. git diff --check passed. No unrelated audit fixes were attempted.

16. **End-to-end result.**
    test_local_end_to_end_manual_recovery_with_real_paperqa_and_existing_verifier
    passes within the full suite: unavailable automatic source → source_required →
    actual local PDF fixture upload → deterministic acceptance → same verification
    request → real PaperQA Docs/local models → existing verifier → SUPPORTS.
    Another claim uses the cached artifact/index without external provider calls.
    Existing lexical and deterministic PaperQA integration regressions also pass.

17. **Known limitations.** Single-user local storage, no TTL/freshness/garbage
    collection/disk quota; cache hit reparses bytes and avoids the network. The
    matcher intentionally rejects some legitimate unusual/short-title PDFs; no OCR
    or encrypted PDF support. Identity evidence is not cryptographic authentication
    against forged documents. In-memory indexes disappear at restart. Existing page
    provenance loss, generic HTML duplication, and provider early-return behavior
    remain. No live provider/LLM or recorded-video acceptance claim was made; the
    recovery flows were validated with deterministic local tests. Existing frontend
    npm audit findings and production bundle-size warning remain.

18. **Intentionally deferred.** M3 can take manuscript upload/parsing, references
    and callouts, atomic claims, claim-citation attribution and whole-paper
    orchestration. GROBID, SSE, persistent vector indexes and production infrastructure
    remain outside M2. No Redis/vector DB/distributed cache/CI/CD/cloud deployment
    or authentication changes were added.

19. **Recommended commit.** feat: add source recovery and local caching

## Complete changed-file inventory

Added:

- backend/app/api/routes/sources.py
- backend/app/services/source_store.py
- backend/app/services/manual_source.py
- backend/app/tests/test_source_lifecycle.py
- frontend/src/components/verification/ManualSourceRecovery.tsx
- frontend/tests/source-recovery.test.tsx
- frontend/vitest.config.ts
- docs/SOURCE_LIFECYCLE.md
- docs/M2_IMPLEMENTATION_REPORT.md

Modified:

- .gitignore
- ARCHITECTURE_BASELINE.md
- backend/.env.example
- backend/requirements.txt
- backend/app/config.py
- backend/app/main.py
- backend/app/schemas/paper.py
- backend/app/schemas/verification.py
- backend/app/services/paper_retriever.py
- backend/app/services/verification_service.py
- backend/app/services/llm/provider.py
- backend/app/researchguard/adapters/sciverify.py
- backend/app/researchguard/adapters/paperqa2.py
- backend/app/tests/conftest.py
- backend/app/tests/test_verification_service.py
- frontend/src/types/backend-verification.ts
- frontend/src/services/api.ts
- frontend/src/services/verificationService.ts
- frontend/src/pages/VerifyPage.tsx
- frontend/package.json
- frontend/package-lock.json

The existing source providers, parser, chunker and verifier agents were not rebuilt.
The small provider change removes inherited content-bearing diagnostic logs and
partial-key output so the demo's INFO logs remain useful without those payloads.
