# ResearchGuard M2 source lifecycle

M2 targets a single-user local execution and recorded demo. It composes the
existing SciVerify DOI resolver, OA discovery, parser, chunker, verifier, frontend
report, and pinned paper-qa==2026.8.12. It adds no cloud deployment or distributed
storage. The external retrieve_paper(doi) contract remains available.

## Automatic and cached retrieval

1. Normalize the DOI using the existing helper.
2. Read the DOI pointer from LocalSourceStore. Validate the metadata and SHA-256
   of the actual stored file. Missing, malformed, mismatched or unreadable entries
   are cache misses.
3. On a valid hit, parse the accepted bytes through the existing parser and chunker.
   No DOI metadata resolver, OA provider or download is called. An unparseable or
   chunkless cached artifact is a miss and resumes the automatic path.
4. On a miss, run the existing SciVerify metadata/discovery/candidate pipeline:
   Europe PMC, OpenAlex, Unpaywall and Semantic Scholar remain unchanged.
5. After a candidate parses and produces chunks, create an accepted artifact from
   its exact downloaded bytes, persist it, and return the normal retrieval response.
   A local write failure logs a safe warning and permits this remote verification
   to continue; later requests may need to retrieve again.

PaperQA receives only chunks from this accepted source. It never discovers papers,
substitutes a different paper, downloads sources or generates the final verdict.

## Artifact representation and on-disk layout

AcceptedSourceArtifact is an application dataclass, outside the domain and HTTP
schemas. It holds normalized DOI, raw_content_sha256, format (pdf/html), exact raw
content bytes, source URL, original provider, origin (remote/manual), and a copied
canonical PaperMetadata snapshot. API responses contain no raw bytes or paths.

The default root is backend/data/researchguard/sources/ and is gitignored:

```text
sources/
  doi/
    <SHA256(normalized DOI)>.json         # accepted raw-hash pointer
  <SHA256(exact raw bytes)>/
    source.pdf OR source.html             # exact bytes
    <SHA256(normalized DOI)>.json         # artifact metadata + paper snapshot
```

Metadata filenames are per DOI, allowing identical bytes under multiple DOI
aliases without overwriting another paper's snapshot. Version 1 metadata includes
DOI, raw hash, format, source URL, provider, origin and paper. Filenames are generated
internally; uploaded names are never used, stored or logged. Writes use a temporary
file in the target directory, flush/fsync and os.replace; the DOI pointer is published
last. A corrupt pointer cannot introduce a path because the hash must be 64 lowercase
hexadecimal characters. This is simple local persistence, with no migrations,
distributed locks, TTL, garbage collector or per-user isolation. Parsed results are
not persisted: current parser/chunker settings apply again on each cache hit.

## Three distinct identities

- raw_content_sha256: SHA-256 of the exact downloaded/uploaded bytes, including
  PDF metadata and byte-level differences. SourceDocument.content_hash is
  sha256:<raw hash> whenever an artifact exists.
- parsed_content_fingerprint: SHA-256 of the normalized legacy chunk payload
  (chunk ID, text, section and page), retained explicitly in domain chunk metadata.
  Legacy fixtures without an artifact use this as content_hash with
  content_hash_kind=parsed_chunks. Persisted artifacts use raw_bytes.
- PaperQA index key: SHA-256 of the complete SourceDocument snapshot, canonical
  chunks excluding retrieval_score/metadata, pinned PaperQA version, embedding model,
  embedding API base, timeout, credential fingerprint and defer_embedding=false.
  Custom injected embedding objects additionally use object identity; the cached
  entry retains that object to prevent ID reuse. A DOI alone is never the key.

Origin and cache reuse are separate: PaperSource.origin remains remote or manual,
PaperSource.cache_hit reports local reuse, and the original provider is preserved.
Domain SourceType remains REMOTE/MANUAL; domain chunk metadata carries cache reuse.
A manual upload has no invented full-text URL.

## Manual PDF API and deterministic matching

POST /api/sources/manual accepts multipart/form-data fields doi and file. It reads
at most the configured limit plus one byte from UploadFile, rejects oversized/empty
files, checks %PDF- at the beginning, and uses the existing parser plus pypdf to
validate readable, unencrypted, text-bearing PDF content. MIME/filename are not
identity authorities. The filename never determines a storage path.

The existing SciVerify DOI resolver supplies canonical metadata. Matching is
conservative and deterministic, without LLMs:

1. Inspect the first page's leading 4000 characters, stopping before an Abstract,
   Introduction, Background, Methods, Results, Discussion, References or Bibliography
   heading. Inspect explicit PDF DOI/doi, Subject and Keywords metadata as well.
2. Extract normalized DOI tokens. The expected DOI must be the sole distinct DOI
   in this identity region. A different or ambiguous DOI rejects the upload and
   blocks title fallback. A DOI in body text or a bibliography does not establish
   identity. DOI tokens are exact matches, not substring matches.
3. If no DOI is present, require the full canonical title as a contiguous sequence
   after Unicode NFKC/case/punctuation/whitespace normalization, within the first
   2000 header characters or PDF Title metadata. The title needs at least six words
   and 35 normalized characters. Also require a canonical author surname of at
   least three characters and the canonical publication year as a four-digit token
   in the header. Missing author/year evidence rejects fallback.
4. A match stores the same raw artifact that normal retrieval subsequently parses,
   chunks and verifies. A rejected upload leaves any prior accepted artifact intact.

Success: {status: accepted, doi, raw_content_sha256, identity_match: doi or
 title_author_year}. Errors expose a safe detail object with code and message:
INVALID_DOI, INVALID_PDF, FILE_TOO_LARGE (413), SOURCE_MISMATCH,
METADATA_UNAVAILABLE (503), SOURCE_STORE_FAILED (503). No provider body, raw source
text, local path or stack trace is returned by these handlers.

This is bibliographic identity evidence, not cryptographic authentication of a
paper. A deliberately forged PDF can fabricate its DOI/metadata/title. The policy
also intentionally rejects some legitimate PDFs with unusual layouts, omitted year,
short titles, encrypted content or scans requiring OCR. It does not inspect every
bibliographic variation or support alternate editions automatically.

## Source recovery versus scientific insufficiency

A resolved DOI with FULL_TEXT_UNAVAILABLE, METADATA_ONLY or PARSING_FAILURE returns
HTTP 200 with status=source_required, paper DOI/title, and source_recovery containing
required=true, the retrieval reason, accepts_manual_pdf=true and max_size_bytes.
There is no verdict, confidence, agent output, evidence or semantic traceability.
The response schema enforces this invariant. No verifier agents run in this state.

NO_CHUNKS and NO_RELEVANT_EVIDENCE after an accepted source remain
insufficient_evidence with verdict=INSUFFICIENT. Unresolved DOI/provider errors
retain their existing errors. PaperQA failure remains an explicit API 503 and never
silently falls back to lexical ranking. Lexical remains the default engine.

## Frontend recovery

The verification service recognizes source_required as a typed SourceRequiredError,
not a final VerificationResult. VerifyPage preserves original claim, citation/source
label and context in state. ManualSourceRecovery displays the cited DOI/title,
upload limit and PDF chooser. It uploads DOI+PDF with a browser-generated multipart
boundary and automatically resubmits the original verification input after acceptance.
Only a completed verification becomes a normal report/history item. Invalid PDFs,
mismatch, oversized files, metadata failures and local save failures show safe
messages and allow another selection. A failed verification retry can retry the
preserved input without retyping. Existing authentication/history behavior remains.

## PaperQA index reuse and concurrency

The cache holds indexed Docs and embeddings, not PQASession, contexts, summaries,
relevance scores, top-K selections or verifier outputs. It is bounded by an LRU
limit (default 8); 0 disables reuse. It is event-loop-local within the backend
process and cleared at application startup/shutdown. An asyncio lock serializes
index construction to prevent duplicate successful builds. Each retained Docs has
its own query lock because the pinned API initializes its text vector index lazily
and mutates MMR settings. Queries use a fresh session and freshly selected summary
model/settings. Failed index construction is never cached; failures can be retried.
Raw/parsed/embedding changes rekey the entry. Changing only the summary model can
reuse source embeddings. Process restart loses indexes; raw sources survive.

The deterministic integration tests use the real pinned Docs API and assert one
source embedding batch plus two query embedding calls for two claims, one
Docs.aadd_texts invocation, different context-session IDs, and fresh summaries.
Tests also cover concurrent requests, cache eviction/disable, failed builds,
changed raw bytes, parsed content, embedding model, API base and credentials.

## Configuration and local demo

Backend .env.example documents:

| Setting | Default | Meaning |
| --- | --- | --- |
| RESEARCHGUARD_SOURCE_CACHE_DIR | backend/data/researchguard/sources | Local artifact root; relative values use backend process cwd |
| RESEARCHGUARD_SOURCE_MAX_SIZE | 20971520 | Manual upload bytes (20 MiB) |
| RESEARCHGUARD_PAPERQA_CACHE_SIZE | 8 | Retained source indexes per event loop; 0 disables |

Existing CHUNK_SIZE/CHUNK_OVERLAP and PaperQA settings still apply. Use the existing
researchguard Conda environment, Python 3.11, and the unchanged lexical/paperqa2
engine selection. For INFO demo logs, start uvicorn with an INFO application logging
configuration. Look for source_cache_miss, source_cache_hit, manual_source_accepted,
paperqa_index_cache_miss and paperqa_index_cache_hit. These new logs contain DOI,
source identity or matching method, never PDF text, prompts or credentials.
Inherited verifier logs that printed model outputs, provider bodies, validation
payloads and partial API keys were also removed; failure logs retain safe error
types/status and retry timing.

Offline validation commands (from backend and frontend respectively):

```powershell
& D:\conda_envs\researchguard\python.exe -m pytest -q
npm run test
npm run build
```

The end-to-end test is in backend/app/tests/test_source_lifecycle.py:
test_local_end_to_end_manual_recovery_with_real_paperqa_and_existing_verifier.
It drives the API through unavailable automatic retrieval, source_required, a real
local PDF upload, identity acceptance, unchanged verification retry and a supported
result through local embeddings/summaries and the existing verifier. A second claim
verifies index reuse and no provider calls. Frontend tests drive the actual VerifyPage
through service response, upload panel, retry and report saving with preserved context.
The whole backend suite blocks public DNS/network and uses per-test source directories.

## Intentional limitations and later work

No automatic cache freshness checks: a cache hit deliberately avoids the network.
A validated manual upload can replace the DOI pointer; old content directories are
retained. No OCR, persistent PaperQA indexes, scan recovery, disk quota/cleanup,
multiple-user storage, distributed coordination or production persistence claims.
Existing parser page-provenance and HTML duplication limitations remain. Existing
source-provider early-return behavior remains unchanged. No live provider or cloud
model calls are required for regression validation.

M3 can address manuscript upload/parsing, reference/callout extraction, atomic claims,
claim-citation attribution and whole-paper orchestration. GROBID/SSE/production
infrastructure are outside M2 and are not silently introduced by this implementation.
