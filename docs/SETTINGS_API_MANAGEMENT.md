# Settings and local API management

Baseline: develop at 54d6950. This change does not alter scientific algorithms, Verdicts, Agent prompts, History, Repository storage or authentication.

## Source audit

| Category / actual provider | Purpose and consumer | Existing configuration / required fields | Model / key |
| --- | --- | --- | --- |
| LLM / OpenAI-compatible, currently DeepSeek | M3B Claim Extraction: services/claim_extractor.py → adapters/claim_llm.py. Verification/Prosecutor/Defender/Adjudicator: services/verification_service.py → services/llm/provider.py | LLM_PROVIDER, LLM_BASE_URL, LLM_MODEL, LLM_REQUEST_TIMEOUT, LLM_API_KEY; supported protocols match get_llm_provider | Model required; key normally required for cloud providers. These roles share one connection and model. |
| PaperQA2 summarization / LiteLLM, currently OpenAI-compatible DeepSeek | researchguard/adapters/paperqa2.py → PaperQA Settings | PAPERQA2_MODEL, PAPERQA2_API_BASE, PAPERQA2_API_KEY, PAPERQA2_REQUEST_TIMEOUT | Provider-qualified model, e.g. openai/model; independent model, optional shared connection. |
| Embedding / LiteLLM, currently Alibaba Beijing | Same PaperQA2 adapter, embedding_config | PAPERQA2_EMBEDDING_MODEL, PAPERQA2_EMBEDDING_API_BASE, PAPERQA2_EMBEDDING_API_KEY, PAPERQA2_EMBEDDING_BATCH_SIZE | Independent vector model and key; existing default batch size 10 retained. |
| GROBID / local service | M3A manuscript_parser.py → adapters/grobid.py | GROBID_BASE_URL; existing timeout/size settings remain in .env | No model or API key field. |
| Crossref / public API | citation_resolver.py, reference_resolver.py | CROSSREF_API_URL, CITATION_USER_AGENT | No key consumed by existing code. |
| OpenAlex | citation_resolver.py, reference_resolver.py, paper_retriever.py | OPENALEX_API_URL, optional OPENALEX_API_KEY | Key is currently sent only by reference metadata search; DOI/full-text paths keep their existing behavior. |
| Semantic Scholar | citation_resolver.py legacy endpoint and paper_retriever.py Graph discovery | SEMANTIC_SCHOLAR_API_URL; previously hardcoded Graph endpoint now SEMANTIC_SCHOLAR_RETRIEVAL_URL | Existing consumers send no API key; none is added to the UI. Two distinct endpoints are shown honestly. |
| Europe PMC | paper_retriever.py public REST search | Previously fixed REST root now EUROPEPMC_API_URL | No key. |
| Unpaywall | paper_retriever.py OA location discovery | Previously fixed root/contact now UNPAYWALL_API_URL, UNPAYWALL_EMAIL | Contact email, no key. Existing defaults retained; use a valid contact email for live checks. |
| PMC, Europe PMC HTML, publishers | Per-citation PDF/HTML retrieval via document_retriever.py / public_http.py | Discovered document URLs and existing size/network limits | No universal connection, model or key; boundaries explained in API tab. No new paywall or authentication flow. |
| Supabase | Frontend authService/profileService/historyService | VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, deployment-time frontend settings | Deployment-managed; intentionally not changed by backend API management. ACCOUNT keeps existing normal-mode capabilities. |
| Validator / traceability | Local deterministic validation | Existing algorithm configuration | No external API or new credentials. |

Numeric retrieval/candidate/concurrency limits and GROBID parser limits remain in .env. They are algorithm/runtime controls rather than new API connections. No arbitrary role-to-model remapping is introduced.

## Design references

- Open WebUI: https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai-compatible/ — protocol-oriented connections and explicit Base URL/Model ID.
- Dify: https://docs.dify.ai/en/cloud/use-dify/workspace/model-providers — provider-grouped configuration and shared workspace credentials.
- LibreChat: https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/custom_endpoint — endpoint/key/model separation and redacted credentials.
- LiteLLM: https://docs.litellm.ai/docs/proxy/ui — separate model and credential management.

The implementation uses compact expandable service forms, manual model IDs (no invented model list), explicit Save/Cancel and cost-gated Test Connection. It adds no UI framework or model-provider SDK.

## Settings UX

ACCOUNT, SYSTEM STATUS, API appear in that order. ACCOUNT is the default. Existing account fields and normal logout remain; Local Demo stays read-only. Visited panels remain mounted to preserve unsaved API drafts across tab switches. Tabs support arrow keys/Home/End.

SYSTEM STATUS is one compact row per audited service plus backend, one Refresh, no polling. Green means the defined check passed; red means it failed; gray means untested/unsupported. Row tooltips explain scope. GET status performs no external calls. Refresh checks only GROBID and public metadata services, using the ACTIVE process configuration. Model status changes only after an explicit matching model test; testing a different draft cannot mark the active model healthy.

API forms show key presence only, never the saved secret. New input is masked and can be temporarily revealed. Empty input retains the saved key. Removal is a separate explicit action followed by Save; Cancel reverses it. Failed saves retain the draft. A revision prevents overwriting another tab's newer save. PaperQA2 can reuse the LLM Base URL/key; embedding can reuse LLM or PaperQA2; models remain independent and sharing cannot cycle.

All model tests require an explicit cost opt-in. Tests use the visible draft and the latest saved shared connection. Tests never save or activate configurations. One small Chat Completions request (16 output tokens) or one short embedding input is used, without retries. Native non-openai/ LiteLLM models are preserved but this lightweight probe returns unknown for them. Successful text/vector responses do not assert scientific correctness. GROBID checks /api/isalive, not actual parsing; metadata checks validate response structures, not source availability for every paper. Semantic Scholar checks both distinct consumers.

## Storage, access and activation

- Backend-only file: backend/.researchguard-settings.bin; ignored by Git, outside the static frontend and literature directories. RESEARCHGUARD_SETTINGS_FILE can override the server-side path. Do not publish this file.
- Windows: entire payload encrypted with the current OS user's DPAPI. No additional cryptography dependency or raw key file. It is tied to the OS user and is not portable to another machine/account.
- POSIX: owner-only 0600 file, not encrypted at rest. The host account/filesystem is the trust boundary; deployments needing a central vault should keep using their existing environment/secret injection.
- Existing .env is never rewritten. Overlay settings take precedence for the matching service only during startup. Explicitly clearing a managed key overrides its .env fallback; it does not erase the original .env file.
- Save/Test never modify os.environ or rebuild provider objects. Existing jobs keep their process configuration. Users must finish jobs before manually restarting; no automatic restart or hot reconfiguration is attempted.
- Configuration is loaded after .env and before consumers import static configuration. All controlled default endpoint behavior is preserved when no override exists.
- Corrupted/unreadable saved settings fail explicitly without replacement or credential fallback. Back up/manage the private file as a local secret; copying it to another Windows user will not unlock it.
- Administration requires a direct loopback peer and loopback Host, rejects forwarded/proxy headers, validates browser Origin, and requires a per-process management token for every mutation/test/refresh. Allowed browser origins are localhost/127.0.0.1 ports 5173/5174, the same backend origin, and the configured loopback FRONTEND_URL. Custom frontend ports must be explicitly configured. Run one backend worker; bind it to 127.0.0.1. Set RESEARCHGUARD_SETTINGS_ENABLED=0 to disable administration.
- Key values never appear in query responses, browser localStorage, URL query strings or ordinary application logs. URL-embedded credentials/query parameters are rejected for managed connections and stripped from legacy configuration responses. Request validation errors and provider failures are sanitized.
- External probes allow public HTTPS or loopback HTTP(S), disallow redirects and URL-embedded secrets, bound response size/time, and use the existing DNS-pinning public transport. No user manuscript is sent by a test.

## Verification boundaries

Automated tests use temporary private settings files, simulated startup and HTTP MockTransport. They cover retention/removal, isolation, encryption on Windows, concurrent revisions, non-hot-updating saves, redaction, remote/Host/Origin/token access, paid opt-in, all nine service probes, unknown native-model probes and active-vs-draft status. Frontend tests cover default account behavior, tab order, draft persistence, save/cancel/failure, shared connections, no localStorage key writes and cost gating. Existing History/Repository/whole-paper suites remain unchanged.

No real paid model test is authorized or executed. Real free-service check results and final test counts are recorded in the delivery report. Desktop/mobile visual browser QA is separate from jsdom interaction tests; do not treat jsdom as rendered browser acceptance.


### Validation record (2026-10-28)

- Frontend offline suite: 135 passed (includes existing account, History, Repository and whole-paper regression).
- Full backend offline suite at first checkpoint: 1548 passed, 1 skipped. Additional service-schema, pending-model and forwarded-request contracts were then added and are checked separately in the final settings run.
- Real, explicit lightweight non-model probes: Crossref, Europe PMC and Unpaywall passed their response-schema checks; GROBID connection failed; OpenAlex returned HTTP 429; the existing Semantic Scholar legacy resolver returned HTTP 404. These are current environment results, not fabricated green statuses or a claim of end-to-end scientific correctness.
- LLM, PaperQA2 summarization and embedding: real external model tests NOT RUN. Probe contracts verified offline only.
- No GUI/mobile visual acceptance is claimed. Current UI verification is jsdom interaction tests, responsive layout code and TypeScript/production compilation. Browser computer-use was unavailable in this session, and the user's existing running services were not restarted.
- Run docs/settings_free_service_check.py manually to exercise the settings ASGI routes and lightweight service probes without app lifespan/job recovery. It does not test models.


## File inventory

Modified:
- README.md — clarify that Local Demo account identity stays read-only while API management is available.
- .gitignore — exclude private settings files.
- backend/.env.example — document local management and newly configurable existing service endpoints.
- backend/app/config.py — apply the private overlay after .env at startup.
- backend/app/main.py — load overlay before consumer imports and register management routes.
- backend/app/services/paper_retriever.py — parameterize existing service URL/contact constants only; retrieval logic/defaults unchanged.
- frontend/src/pages/SettingsPage.tsx — compact ACCOUNT and ordered accessible tabs.

Added:
- backend/app/settings_catalog.py — audited field/consumer definitions and validation.
- backend/app/settings_store.py — private persistence, redaction, sharing and restart-only activation.
- backend/app/api/routes/settings.py — local administration routes and access guards.
- backend/app/services/settings_checks.py — bounded explicit probes and truthful status projection.
- backend/app/tests/test_settings_management.py — offline API/security/persistence/probe tests.
- frontend/src/services/settingsService.ts — typed management requests.
- frontend/src/components/settings/ApiConnectionForm.tsx — reusable credential/model form.
- frontend/src/components/settings/ApiSettingsPanel.tsx — grouped configuration management.
- frontend/src/components/settings/SystemStatusPanel.tsx — compact service list and single refresh.
- frontend/src/components/settings/StatusMark.tsx — accessible status symbols.
- frontend/tests/settings.test.tsx — account/tab/form/status interaction contracts.
- docs/SETTINGS_API_MANAGEMENT.md — this audit and delivery report.
- docs/settings_free_service_check.py — explicit non-model probe helper through local ASGI routes.

Final Settings backend contracts: 38 passed after controlled-error and malformed-model-response checks. Frontend production build and lint pass; Vite retains its existing large-bundle warning. Backend retains the existing Starlette/httpx deprecation warning. A failed status refresh clears prior green results to unknown.
