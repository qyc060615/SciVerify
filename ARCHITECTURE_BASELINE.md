# Repository Baseline

Audit date: 2026-10-08 (Asia/Shanghai). Milestone: M0.

| Item | Observed result |
| --- | --- |
| Inherited repository | qyc060615/SciVerify; origin https://github.com/qyc060615/SciVerify.git |
| Upstream | https://github.com/Prithiv04/SciVerify.git |
| Baseline commit | cb564f045ddaf423efd0a1c6e018c38d51f3e1ef; matches requested cb564f0 |
| Branch | develop, tracking origin/develop |
| Initial working tree | Clean; git status --short --branch showed only branch tracking |
| Python | 3.12.7 |
| Node / npm | v24.14.0 / 11.9.0 |
| Initial backend attempt | python -m pytest -q: 18 collection errors, missing fastapi/pypdf; dependency/environment failure |
| Backend baseline after environment setup | .venv/Scripts/python.exe -m pytest -q: 468 passed, 1 warning, 20.08s |
| Frontend baseline | npm ci then npm run build: exit 0, TypeScript and Vite production build successful |
| Frontend final validation | npm run build: exit 0; same generated asset names/sizes as baseline |
| Backend final validation | .venv/Scripts/python.exe -m pytest -q: 511 passed (468 existing + 43 new), 1 warning, 13.60s |

The host initially rejected ordinary terminal process creation; approved elevated
terminal execution restored access. An ignored backend/.venv was created using
python -m venv .venv and populated using its Python with pip install -r requirements.txt.
No tracked dependency declaration changed. Backend has lower-bound requirements,
not a lockfile. Installed versions relevant to this run: fastapi 0.142.3,
starlette 1.7.0, pydantic 2.13.5, pytest 9.1.1, httpx 0.28.1, pypdf 6.19.0,
beautifulsoup4 4.15.0, python-dotenv 1.2.4, uvicorn 0.54.0.

Frontend has package-lock.json. npm ci was used instead of npm install to honor
its exact resolution without updating dependencies. It installed 250 packages;
Vite reports 8.2.1. Both builds emitted the existing >500 kB chunk warning
(main JavaScript 858.58 kB, gzip 246.84 kB). npm audit --json reports three
high-severity affected packages: axios, brace-expansion, source-map-js. No audit
fix or upgrade was applied. The backend warning is Starlette's httpx TestClient
deprecation under the installed dependency versions; it is not a test failure.

Repository roots: backend/ (FastAPI, services, schemas, tests, evaluation),
frontend/ (React/TypeScript/Vite), supabase/migrations/ (profiles/history and RLS),
docs/, root package.json and deployment configuration. No applicable AGENTS.md
was found in the repository or ancestor directories.

Validation proves automated regression/build compatibility. It does not claim
live provider availability, configured Supabase operation, or successful live LLM calls.

# Existing SciVerify Architecture

The audit is based on the following implementation paths, not README claims.

1. frontend/src/pages/VerifyPage.tsx renders components/verification/VerificationForm.tsx.
   A user enters one claim and a citation/DOI plus optional context. Source-type
   controls include DOI, URL, citation and reference, but all submissions must yield
   a DOI through lib/doi.ts. services/verificationService.ts sends only trimmed
   claim and extracted doi to POST /api/verification/analyze. Context and sourceType
   are retained in the frontend report; they are not sent for backend analysis.
2. frontend/src/services/api.ts supplies an Axios client. backend/app/main.py
   registers citations, papers, evidence, verification routes and health endpoints.
   These are ordinary synchronous handlers; there is no job API.
3. backend/app/api/routes/verification.py calls services/verification_service.py:
   preprocess_claim -> evidence_pipeline.retrieve_evidence_for_claim -> retrieve_paper.
   The preprocessing is normalization/number extraction, not manuscript atomic claim extraction.
4. services/citation_resolver.py resolves DOI metadata from Crossref, then OpenAlex,
   then Semantic Scholar fallback. /api/citations/resolve exposes this separately;
   the verification path calls the service internally, not the citations endpoint.
5. services/paper_retriever.py obtains citation metadata, fetches the OpenAlex work,
   discovers candidates, downloads/parses candidates sequentially, and returns the
   first candidate producing chunks. Candidate discovery uses OpenAlex OA locations,
   Europe PMC DOI-to-PMCID search, Unpaywall, and Semantic Scholar OA PDFs.
   Candidates include PMC PDF/HTML, Europe PMC HTML, repository PDFs/HTML and
   publisher OA URLs; helpers expand PMC mirrors and order/deduplicate candidates.
   An OpenAlex provider error can return metadata_only before other discovery;
   OpenAlex 404 propagates PaperNotFoundError even after citation resolution.
6. services/document_retriever.py uses httpx to fetch candidate PDF/HTML bytes,
   follows redirects and rejects unsupported types, oversize content, anti-bot
   interstitials, and detected paywalls. services/document_parser.py uses pypdf
   for downloaded source PDFs and BeautifulSoup for HTML, with heuristic sections
   and repository chrome filtering. This parses cited sources, not manuscripts.
7. services/evidence_chunker.py chunks section text with character size/overlap
   (defaults 1000/200). It generates DOI/section/index-based chunk IDs, source_url
   and section metadata; page is explicitly None. evidence_pipeline.py handles
   retrieval statuses and invokes evidence_retriever.rank_evidence_for_claim.
8. services/evidence_retriever.py computes phrase/lexical overlap, contextual numeric
   overlap, section weight/bonus and deterministic ordering. Score weights are
   0.50 phrase, 0.30 enhanced claim overlap, 0.10 numeric, 0.10 section, plus bonus.
   It applies relevance filtering, normalized-text deduplication, near-duplicate
   suppression and section diversity. No embedding, vector index or semantic
   retrieval engine is used. LLM interpretation occurs later.
9. verification_service.py runs prosecutor -> defender -> adjudicator sequentially
   through services/agents/. evidence_validation.py sanitizes evidence IDs.
   verification_validator.py may adjust the adjudicator verdict, calibrates
   confidence, computes agreement/warnings and normalizes corrections.
10. services/claim_traceability.py heuristically splits the submitted claim using
    utils/claim_segmenter.py (at most five segments), scores segment coverage and
    links evidence IDs. Definitive contradicting IDs come from the adjudicator,
    not the prosecutor. This is per-claim tracing, not manuscript citation mapping.
11. frontend/src/services/verificationMapper.ts maps response schemas to frontend
    types/verification.ts, scales confidence/coverage to percentages, and preserves
    evidence/source URLs, warnings, corrections and traces. components/verification/
    renders the report. stores/verificationStore.ts maintains records and delegates
    history persistence to services/historyService.ts -> Supabase verification_history.
    result_json stores the report; migrations enable user-specific RLS. There is no
    backend persistent source/index store. The loading display is indeterminate,
    not driven by server progress events.

Separate endpoints /api/papers/retrieve and /api/evidence/retrieve expose earlier
stages. Existing processing paths include HTTP 400/404/503 errors; insufficient
evidence returns a response without running agents; unavailable/failed LLM returns
llm_unavailable/verification_failed with no verdict. They remain unchanged in M0.

## Existing contracts and LLM boundary

backend/app/schemas/verification.py defines top-level verdicts SUPPORTS,
OVERSTATED, CONTRADICTS, INSUFFICIENT, FABRICATED; statuses success,
insufficient_evidence, llm_unavailable, verification_failed, not_found, provider_error.
Confidence is a 0..1 scalar, with existing agent validators clamping it.

ClaimTraceability contains segments, overall_coverage and warnings. Each segment
has id, text, status (SUPPORTED/PARTIALLY_SUPPORTED/UNSUPPORTED/CONTRADICTED),
coverage_score and evidence_ids. A segment's PARTIALLY_SUPPORTED is not an existing
top-level verdict. EvidenceItem contains chunk_id, section/index, text, relevance,
claim/numeric overlap, numbers, optional source_url/page.

services/llm/provider.py defines LLMProvider.generate(prompt, system, response_model)
and UnavailableLLMProvider/OpenAICompatibleLLMProvider. The concrete provider calls
an OpenAI-compatible /chat/completions endpoint via httpx and validates JSON with
Pydantic. Configuration supports openai/compatible/groq aliases and configurable
base URL/model/key; 429 retry/quota logic and structured-response normalization
are present. No provider SDK or PaperQA2 object participates in the core flow.

# Current Capabilities

| Capability | Code-backed status |
| --- | --- |
| Single claim + DOI verification | Implemented, synchronous multi-agent analysis when LLM configured |
| DOI metadata and OA source resolution | Implemented through the providers above |
| Source PDF/HTML parsing and chunking | Implemented for downloaded cited sources |
| Lexical/numeric/section evidence ranking | Implemented |
| Embedding/vector RAG or scientific semantic retrieval | Absent |
| Persistent source/content/index cache | Absent; frontend report history and evaluation checkpoints are different concerns |
| Manuscript PDF input | Absent; no upload route or UI |
| Manual source PDF upload | Absent |
| SSE/WebSocket incremental job | Absent |
| Traceable single-claim result/history | Implemented; page provenance unavailable in produced chunks |
| Existing evaluation utilities | Present in app/evaluation and backend/evaluation; not expanded by M0 |

# Missing ResearchGuard Capabilities

Manuscript PDF pipeline, structural citation mapping, atomic claim extraction,
claim-citation attribution, scientific semantic RAG, manual source recovery,
whole-manuscript orchestration and incremental SSE are absent. Heuristic claim
segmentation and DOI metadata resolution do not provide those manuscript capabilities.
Source/index persistence and hash-cache implementation are absent. There is no
dedicated privacy audit workflow; Supabase history RLS is an existing access-control
mechanism, not a complete processing/privacy audit.

# ResearchGuard Architecture Direction

SciVerify remains the application scaffold. GROBID is planned for structural
manuscript parsing. PaperQA2 is planned as the scientific evidence engine.
ResearchGuard owns internal domain contracts, future orchestration and adapters.
citefact is design/implementation reference only; Docling is not a first-level
component, and may later be a fallback/indirect dependency. Neither is added here.

Dependency direction:

~~~text
API / application service -> ResearchGuard domain / ports
Adapters / external integrations -> ResearchGuard domain / ports
GROBID -> parser adapter -> ParsedManuscript
PaperQA2 -> evidence adapter -> EvidenceChunk
SciVerify schemas/services -> legacy adapter/application -> internal models
~~~

app/researchguard/ is chosen because app/schemas/ currently serves the legacy HTTP
and service contracts; placing future manuscript types there would couple them to
that API. domain.py imports only standard-library types and existing Pydantic.
ports.py imports domain types and Protocol. adapters/sciverify.py may import legacy
schemas; the core never imports that adapter. No existing route/service imports
ResearchGuard in M0. No new runtime dependency or production refactor is required.

# Domain Model

| Model | Stable role/relationships |
| --- | --- |
| Manuscript | Opaque internal ID, content locator, optional title/hash |
| Paragraph | Manuscript ID, text, zero-based order, optional one-based page/section |
| CitationCallout | Manuscript/paragraph IDs, marker text, zero or more reference IDs |
| Reference | Manuscript ID, raw bibliography text, optional DOI/title/authors/year |
| CitationContext | Manuscript/paragraph IDs, context text, callout IDs, optional page |
| ParsedManuscript | Parser aggregate containing manuscript, paragraphs, references, callouts, contexts |
| AtomicClaim | Claim/manuscript IDs, text, paragraph/context identity, callout/reference IDs, optional page |
| SourceDocument | Internal/reference IDs, optional bibliography/locator/hash, source type/provider/URL, retrieval status |
| EvidenceChunk | Chunk/source document IDs, text, optional page/section/score/URL, JSON metadata |
| VerificationResult | Claim ID, processing status, optional semantic verdict/confidence, chunks, explanation, traceability |
| VerificationTraceability | Evidence IDs, optional method, warnings and normalized JSON diagnostics |
| Job / JobEvent | Manuscript job identity/status and job-linked ordered event records; no execution/transport |

IDs/text cannot be blank. ParsedManuscript rejects duplicate IDs within each
collection, foreign manuscript identities, dangling paragraph/reference/callout
links and context callouts from another paragraph. Unresolved callouts use empty
reference_ids. AtomicClaim expresses attribution but performs no extraction; a
future application service must validate claim IDs/attribution against the parser
aggregate. Separate objects do not query a database to enforce foreign keys.

Pages are one-based integers when known. Chunk retrieval scores are finite but not
restricted to 0..1 because engines have different score scales. Confidence is a
finite 0..1 value. Source metadata/hash and chunk provenance/page can be unknown.
Locators describe content without accessing it. No hash/cache is computed.

Completed verification requires a semantic verdict; all other processing statuses
forbid semantic verdict/confidence. Completed INSUFFICIENT can have no chunks;
source_unavailable, citation_unresolved and source_mismatch are processing states.
Trace evidence IDs must exist in the result; returned chunk IDs must be unique.
Models forbid unknown fields and field reassignment. Tuples protect relationship
collections; JSON metadata dictionaries are not deeply immutable. Adapters must
normalize third-party objects to JSON and stable fields, not attach library objects.

The domain EvidenceChunk and legacy schemas.paper.EvidenceChunk deliberately
represent different contracts (source identity and generic metadata versus DOI/
section/index HTTP/service schema). Legacy models are retained for compatibility,
not duplicated into competing production paths. JobEvent defines records only,
not SSE, job scheduling, event persistence or a lifecycle state machine.

# Integration Boundaries

ports.EvidenceRetriever.retrieve(claim, source_document, top_k) returns a list of
internal EvidenceChunk. top_k must be positive; an implementation returns at most
that many ranked chunks with stable IDs belonging to the supplied source. It owns
locator/content loading or injected repository access. Empty relevant results are
distinct from source retrieval failure. Error translation belongs in the adapter/
application layer. The Protocol describes a contract, not runtime enforcement.

ports.ManuscriptParser.parse(manuscript) returns ParsedManuscript preserving its
identity. Future GrobidManuscriptParser must translate TEI into these records,
including unresolved markers and optional page metadata. No TEI classes, HTTP
client or GROBID process is added.

Ports are synchronous to match current services. A future service can decide how
to execute blocking adapter work; M0 adds no async job execution. Test-local fake
implementations exercise domain inputs/outputs without external libraries.

For M1, implement PaperQA2EvidenceRetriever behind EvidenceRetriever, normalize
PaperQA2 evidence/source IDs and provenance in the adapter, and inject it into a
ResearchGuard application service. If a lexical adapter is needed, it can load
source content, use existing parsing/chunking and rank_evidence_for_claim with the
same preprocessing/settings, then map selected items to domain chunks. Keep this
conversion outside domain and verify equivalence before changing production
wiring. The legacy function currently accepts ProcessedClaim plus a list of legacy
chunks, not SourceDocument; forcing it through the new port in M0 would require
content-loading and identity policy beyond a safe small refactor.

## Verdict contract and legacy mapping

The opt-in adapters/sciverify.py exposes map_sciverify_verdict with a required,
explicit processing_status. Existing API/frontend verdicts remain unchanged.

| SciVerify verdict on completed assessment | ResearchGuard verdict |
| --- | --- |
| SUPPORTS | SUPPORTED |
| OVERSTATED | OVERSTATED |
| CONTRADICTS | CONTRADICTED |
| INSUFFICIENT | INSUFFICIENT |
| FABRICATED | INSUFFICIENT (conservative, lossy; absence of support does not prove contradiction) |
| No top-level equivalent | PARTIALLY_SUPPORTED remains available for future assessment |

For incomplete/error processing the mapping returns None, even if a legacy
verdict is supplied. Missing/unknown completed verdict or invalid processing
status raises ValueError. Never infer CONTRADICTED from source unavailable,
unresolved citation or source mismatch. A future full response adapter should
retain the raw legacy verdict in trace diagnostics when mapping FABRICATED.

SciVerify insufficient_evidence aggregates no_chunks/no_relevant_evidence with
full_text_unavailable/metadata_only/parsing_failure and sets verdict INSUFFICIENT.
A caller must inspect upstream retrieval diagnostics to distinguish semantic
INSUFFICIENT after an assessment from a pipeline failure; the final legacy
response alone does not always preserve that distinction. M0 does not silently
reinterpret this response or infer partial support from lexical segment coverage.

# Technical Debt / Risks

These are observations of the checked baseline, not changes made in M0.

- backend/requirements.txt has only lower bounds and no backend lockfile; this
  run's installed versions are recorded above. Later installs can differ.
- The exact locked frontend install reports three high-severity affected packages;
  this is npm's audit finding, not proof of exploitability in this application.
  Production bundle size also triggers the existing build warning.
- document_parser.parse_pdf concatenates page text; evidence_chunker emits page=None.
  Source URL/section tracing exists, but page-level provenance is lost.
- In retrieve_paper, all rejected/parse-failed candidates ultimately become
  FULL_TEXT_UNAVAILABLE plus the last detail. Detailed structured failure reasons
  do not consistently survive to the runtime verification result.
- An OpenAlex provider-error early return skips other source-discovery providers;
  a work 404 can abort a DOI already resolved by another metadata provider.
- Unpaywall contact email is hardcoded as team@sciverify.local; optional discovery
  helpers catch broad exceptions and return no candidates, limiting diagnostics.
- document_retriever calls client.get before checking buffered content length;
  MAX_DOCUMENT_SIZE does not prevent the entire response from being downloaded
  into memory first. Candidate URLs are fetched with redirects, without an explicit
  private-network host allowlist in this module.
- Frontend's API interceptor converts Axios errors to plain Error; downstream
  verificationService.parseApiError therefore cannot always access HTTP status/
  detail via axios.isAxiosError. This is observed loss of error metadata.
- Frontend accepts optional context/source labels, but backend receives only claim
  and DOI. Citation/reference input without an extractable DOI is not free-form
  bibliographic resolution.
- Backend routes have no authentication dependency; frontend protected routes
  and Supabase RLS do not authenticate access to these FastAPI routes.
- LLM prompts send claim/evidence to the configured external endpoint. Provider
  error/debug logging can include response bodies, parsed outputs, partial API-key
  characters and key length. No dedicated privacy-audit mechanism is present.
- Existing claim segmentation is capped at five segments and uses heuristics;
  its coverage scores are not scientific semantic verification or calibrated
  probability estimates. Lexical retrieval should remain a fallback when M1 adds
  scientific evidence retrieval.

# M0 Scope and Self Review

Only new contracts, opt-in legacy verdict mapping, tests and this document are
added. Existing services, ranking, verification semantics, routes, schemas,
frontend and dependency files are unchanged. The domain/ports import-direction
check ensures core files depend only on approved standard-library/Pydantic/domain
modules; contract tests cover relationship rejection, optional provenance,
round-trips, bounded confidence, verdict mapping and error/verdict separation.

There are exactly two integration ports, no speculative claim/source interface
hierarchy and no empty external adapter placeholders. There is no PaperQA2 or
GROBID implementation, embedding/vector store/reranker, manuscript/manual upload,
source hash cache, job queue/SSE, privacy UI or new evaluation benchmark. M1 starts
with the PaperQA2 evidence adapter/application integration; other manuscript and
orchestration capabilities remain for their later milestones.
