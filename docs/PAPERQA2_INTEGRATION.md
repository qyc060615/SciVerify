# PaperQA2 Known-Source Evidence Integration (M1)

## Verified environment and dependency

Formal environment: Conda researchguard, Python 3.11.17, executable
D:\conda_envs\researchguard\python.exe. M0's ignored backend/.venv was removed;
no new virtual environment was created. The default host python is a separate
3.12 install, so invoke the formal executable or activate/prepend this Conda
environment before running commands.

Pinned dependency: **paper-qa==2026.8.12**, installed from the configured Python
package index. The actual installed wheel source, not upstream main/README
assumptions, was inspected. PaperQA2's CalVer release policy does not promise
strong compatibility across releases; the adapter checks this exact version
before constructing its index. Upgrade the pin and adapter/tests together.
The upstream project is [Future-House/paper-qa](https://github.com/Future-House/paper-qa).

Actual tested transitive versions include fhlmi 1.0.7, fhaviary 0.37.0,
litellm 1.84.1, numpy 2.4.6, paper-qa-pypdf 2026.8.12. FastAPI 0.142.3,
Pydantic 2.13.5 and httpx 0.28.1 were not upgraded. pip's resolver selected
litellm 1.84.1 because installed fhlmi requires >=1.83.9, <=1.84.1. It selected
packaging 25.0 because coredis 5.7.0 requires packaging >=21,<26; this is a
transitive resolution, not an application dependency rewrite. Redis clients are
transitive LMI dependencies; ResearchGuard creates no Redis service or cache.
Only paper-qa is pinned here; this is not a mass-frozen dependency tree and does
not guarantee all future transitive resolutions will be identical.

Dependency reproducibility was checked with the same Python 3.11 executable:

~~~powershell
python -m pip install --ignore-installed --target .cache\requirements-check --report .cache\requirements-resolution.json -r requirements.txt
python -S -c "import site; site.addsitedir(r'C:\Users\31147\Desktop\coding_project\ResearchGuard\backend\.cache\requirements-check'); import paperqa, fastapi; print(paperqa.__file__)"
python -m pip check
~~~

The clean target installation succeeded; the independent -S import resolved
paperqa from that target and reported 2026.8.12. pip check reported no broken
requirements in the formal environment. The ignored target/report are local
validation artifacts, not a new environment or committed lockfile.

## Engine selection and configuration

RESEARCHGUARD_EVIDENCE_ENGINE accepts lexical (default) or paperqa2.
Unknown names are explicit configuration errors; there is no automatic fallback.
Existing /api/verification/analyze and /api/evidence/retrieve requests remain
{claim, doi}. Frontend source input/result UI and all HTTP response schemas
are unchanged. /api/papers/retrieve continues its original source behavior.

| Variable | Behavior |
| --- | --- |
| RESEARCHGUARD_EVIDENCE_ENGINE | lexical by default; paperqa2 opts into the adapter |
| RESEARCHGUARD_EVIDENCE_TOP_K | PaperQA selected output count; defaults to existing EVIDENCE_TOP_K |
| PAPERQA2_MODEL | Required summary model identifier when using paperqa2; no application hardcoded model |
| PAPERQA2_EMBEDDING_MODEL | Required embedding identifier when using paperqa2 |
| PAPERQA2_EVIDENCE_CANDIDATES | Candidate budget, default 10; actual evidence_k=max(top_k,budget) |
| PAPERQA2_MAX_CONCURRENT_REQUESTS | Context summary concurrency, default 4 |
| PAPERQA2_REQUEST_TIMEOUT | Model request timeout, default 60 seconds |
| PAPERQA2_API_KEY / PAPERQA2_API_BASE | Optional explicit summary credentials/endpoint |
| PAPERQA2_EMBEDDING_API_KEY / PAPERQA2_EMBEDDING_API_BASE | Optional explicit embedding credentials/endpoint |
| LITELLM_LOCAL_MODEL_COST_MAP | Set True as in .env.example to use bundled price/dimension metadata without a separate online refresh |

Model identifiers follow PaperQA/LMI/LiteLLM provider conventions. Standard
provider environment credentials also work when explicit keys are omitted.
The summary configuration supplies model_list/litellm_params; embedding_config
supplies kwargs to the pinned LMI embedding factory. The constructor APIs and
credential placement are tested without a provider call. Use an available
summary/embedding model from your configured provider; no keys are committed.

For local PowerShell validation in backend/:

~~~powershell
$env:PATH = 'D:\conda_envs\researchguard;D:\conda_envs\researchguard\Scripts;' + $env:PATH
python --version
where.exe python
python -m pytest -q
~~~

Configure the environment before starting the backend; backend/.env is loaded
by the existing application configuration. paperqa2 requires both model names,
positive top-k/candidate/concurrency values and a positive finite timeout.

## Actual source path: scheme A

~~~text
Claim + DOI
 -> SciVerify retrieve_paper (unchanged OA resolution/download/parse/chunk)
 -> exact successful RetrievePaperResponse source + all parsed chunks
 -> accepted_source_to_domain
 -> SourceDocument + internal EvidenceChunk[]
 -> one PaperQA Doc + Text[]
 -> await Docs.aadd_texts
 -> await Docs.aget_evidence
       -> await Docs.retrieve_texts (embedding/MMR)
       -> query-specific summaries and 0..10 relevance scores
 -> canonical ResearchGuard EvidenceChunk[]
 -> evidence_to_legacy
 -> original prosecutor / defender / adjudicator / validator / traceability
 -> original VerificationResponse -> original frontend report
~~~

Scheme A was chosen because the pinned Docs.aadd_texts API accepts already
parsed chunks and performs the real embedding/index/evidence path. The local
integration test validates this path. Scheme B is unnecessary: no redownload,
local PDF temporary files, raw bytes in domain/HTTP responses, or cleanup of a
new source artifact is needed. Index objects are request-scoped in memory.

All chunks from the accepted source are input candidates, not chunks preselected
by lexical ranking. Their paper_id must match the accepted paper identity.
A source SHA-256 hashes normalized parsed chunk IDs/text/section/page; metadata
marks content_hash_kind=parsed_chunks. It is **not the original PDF-byte hash**.
Source identity combines DOI and that hash; the in-memory locator is a descriptive
memory:// identifier, not an independently reopenable persisted file.

The adapter validates source status, every chunk's source_document_id, unique
chunk IDs and claim reference membership. It constructs exactly one Doc and checks
Docs contains only that source. Returned Contexts must reference the same Doc,
a known underlying Text name and unchanged original text. Any mismatch is an error.
No Docs.aadd/aadd_file/aadd_url/aquery, agents, metadata inference or discovery
workflow is invoked. No PaperQA final answer replaces SciVerify verification.

Standalone claim inputs use explicitly prefixed standalone manuscript/paragraph/
context IDs to satisfy domain provenance fields; these describe the existing
single-claim request and do not implement manuscript extraction or attribution.

## Actual pinned APIs and evidence semantics

The installed release exposes:

- Docs.aadd(path, citation, ...) and aadd_file(file, ...), for parsing artifacts;
  available but not used here.
- Docs.aadd_texts(texts, doc, settings, embedding_model), which embeds supplied
  Texts and registers the known Doc. The text index is built lazily at retrieval.
- Docs.retrieve_texts(query, k, settings, embedding_model), which performs MMR
  retrieval over the in-memory vector store.
- Docs.aget_evidence(query, settings, embedding_model, summary_llm_model), which
  returns PQASession.contexts after retrieval and contextual summary/scoring.

Settings enables retrieval and summaries, disables text-only context fallback,
sets JSON summary prompts and supplies injected/configured model objects.
aget_evidence returns an unordered set-derived Context list and filters scores
<=0. The adapter sorts positive contexts by PaperQA relevance descending, with
canonical chunk-ID tie breaks, deduplicates IDs and truncates to top_k. Candidate
retrieval and relevance scores come from PaperQA, never legacy lexical ranking.

The pinned upstream context helper normally catches some summary errors, retries
malformed JSON and can discard failed Contexts. _StrictSummaryModel translates
provider failures and validates JSON summary/0..10 score **before** that handler,
so those errors remain explicit and upstream does not log malformed source-bearing
output. Valid score-zero results remain legitimate irrelevant/empty evidence.
An empty relevant result follows the existing insufficient-evidence response path;
a provider/index/config failure does not become a semantic verdict.

## Domain mapping and compatibility

| Field | Mapping |
| --- | --- |
| EvidenceChunk.id | SHA-256 of stable source identity + original chunk identity + text; independent of claim/summary |
| source_document_id | Accepted internal SourceDocument.id |
| text | Original accepted chunk text; never Context.context alone |
| page / section / source_url | Accepted chunk provenance; unknown page remains None |
| retrieval_score | PaperQA Context.score, finite 0..10; not confidence/probability |
| metadata | JSON-compatible PaperQA doc/text names, query-specific Context ID/summary/score/version, legacy chunk ID/index/metadata, source format and hash kind |

Same unchanged source chunk selected for different queries has the same canonical
ID. Context.id can vary with the query and stays in metadata. The source parser
currently emits page=None; no page number is invented. If input provenance includes
page/range/section metadata it is retained. Normalized original source text is
retained, not a claim that original PDF binary bytes are persisted.

sciverify.evidence_to_legacy keeps selected ordering and IDs. It maps relevance_score
as PaperQA score / 10 to meet the inherited 0..1 relevance convention. This does
not make the score a probability. It invokes the unchanged deterministic _score_chunk
helper on already selected evidence solely for legacy claim_overlap/numeric_overlap
and number diagnostics; the helper's lexical relevance output is discarded.
No legacy filtering, diversity selection or ranking is performed on PaperQA output.

The existing verifier's deterministic validator and traceability still consume
these diagnostic overlaps. Thus M1 integrates scientific retrieval while retaining
legacy verification semantics; it does not claim those diagnostics or final
confidence have been scientifically calibrated for the new engine.

## Async application architecture

Both domain ports are async, including the future ManuscriptParser boundary.
No GROBID implementation is added. Verification/evidence FastAPI handlers are async.
The default lexical route offloads its existing synchronous function, preserving
baseline behavior and existing test seams. The paperqa2 route awaits
analyze_verification_async -> aretrieve_evidence_for_claim -> adapter.retrieve.

Source discovery/network/PDF parsing remain the inherited synchronous implementation
and run through anyio.to_thread.run_sync. First PaperQA import/model/index preparation
is also offloaded because importing/configuring third-party models can block.
PaperQA embedding and context APIs are awaited. The unchanged synchronous three-agent
verification/validation/traceability phase runs in a worker thread. Tests assert
source retrieval and all three verifier model calls do not execute on the event-loop
thread. There is no asyncio.run/run_until_complete wrapper in production.

Synchronous retrieve_evidence_for_claim remains available for lexical callers and
explicitly rejects paperqa2 configuration. The inherited synchronous offline/live
evaluation entrypoints are not converted into a PaperQA benchmark; future scientific
retrieval evaluation should call the async service instead.

## Failure contract

PaperQA2 model/configuration/dependency/index/context/source failures produce HTTP
503 with safe codes such as paperqa2_summary_failed, paperqa2_invalid_summary,
paperqa2_retrieval_failed, paperqa2_context_source_mismatch or version/config errors.
They never run lexical fallback, final-answer generation or verification agents.
Bad claim/DOI remain 400 and source-not-found remains 404 through existing handling.
Inherited source-unavailable/parsing statuses retain existing response semantics.

The adapter adds no source-text/debug/provider-body logging. Secret config fields
are excluded from dataclass repr. Source summaries are stored intentionally as
internal evidence metadata, not logs; HTTP legacy evidence remains original text.
Existing LLM provider error logging behavior is inherited technical debt documented
in ARCHITECTURE_BASELINE.md. Do not enable content-bearing third-party debug logging
for private sources.

## Tests and validation

46 new tests in app/tests/test_paperqa2_integration.py cover real Docs indexing,
embedding/MMR retrieval and contextual summaries with a local HTML fixture and
injected deterministic LMI EmbeddingModel/LLMModel implementations. The production
adapter is not mocked out in those tests. Source downloading is replaced with the
known fixture for application/API tests, and verifier models are deterministic.

Coverage includes raw evidence vs summary, canonical IDs across queries/content
changes, actual Context mapping, source/reference mismatches, page/metadata,
score scale, legacy overlap conversion without lexical ranking, engine/default
selection, failure without fallback, explicit configuration errors, installed
version checks, production-model constructor APIs and thread offload. A complete
TestClient request exercises real PaperQA evidence -> three original agents ->
validator/traceability -> VerificationResponse. The evidence endpoint is tested too.
M0 async port fixtures were updated, not removed.

app/tests/conftest.py selects AnyIO's asyncio backend and uses LiteLLM's local
bundled metadata. An autouse socket/DNS guard forbids public networks while allowing
loopback needed by local event-loop infrastructure. All original 511 tests continue
to run under this guard. No API key or public PDF is required. No live smoke test
was executed; local integration success does not measure real model accuracy or
live OA-provider availability.

Final backend full suite: 557 passed (511 existing + 46 new), 1 dependency deprecation warning, 15.55s.
Frontend npm run build: exit 0; existing bundle warning, same asset names/sizes.
Clean requirements target install/independent import and formal pip check: passed.

## Known limitations and M2

- Request-scoped indexing repeats embedding/summary work and consumes provider
  latency/cost on each request; it is intentionally not a persistent cache.
- Hashes are of normalized parsed content. Original-byte artifact hashing,
  persistence, content-addressed reuse and index invalidation belong to M2.
- Page provenance cannot be recovered by PaperQA when the inherited parser/chunker
  has already discarded it. No provenance is fabricated.
- Generic HTML parser may duplicate text in a Body chunk and section chunks. The
  local fixture exposed this inherited behavior; M1 does not rewrite the parser.
- No provider/LLM live calls were used for regression. Provider-specific access,
  embedding model dimensions/limits, real relevance/accuracy and runtime cost
  require later live validation/benchmarking.
- Optional sentence-transformer model families may need their additional upstream
  dependencies; none are installed automatically or downloaded by these tests.
- The API/frontend schema remains unchanged, so PaperQA context-summary metadata
  is internal and is not added to the frontend report or its history JSON.
- This milestone does not calibrate the legacy verifier's lexical diagnostic
  thresholds for PaperQA retrieval. Keep lexical as default pending evaluation.
- No manuscript parsing/upload, claim extraction/attribution, manual sources,
  multi-paper search, source/index DB, Redis service, job queue or SSE is added.

M2 should introduce explicit accepted-source artifacts, persistent source/index
lifecycle, raw-content hash reuse and cache invalidation behind these boundaries.
No commit or push was performed by this task.
