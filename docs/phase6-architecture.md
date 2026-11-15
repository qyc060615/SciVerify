# SciVerify Phase 6 — Architecture & Implementation Plan

> Generated from repository inspection (Step 1).  
> **Scope of this document:** architecture, contracts, and milestones only. No backend code has been implemented yet.

---

## 1. Repository inspection summary

### 1.1 Current layout

```
SciVerify/
├── frontend/                 # React + Vite + TypeScript (sole application code)
├── supabase/
│   └── migrations/
│       └── 001_create_profiles.sql
├── implementation1.md        # Phase 6 plan (source of truth)
├── README.md
└── LICENSE
```

| Area | Status |
|------|--------|
| Backend (FastAPI / Python) | **Does not exist** — no `backend/`, no `.py` files |
| Frontend verification UI | **Complete (mock-only)** |
| Supabase Auth + profiles | **Configured** |
| Verification persistence | **In-memory Zustand only** |
| Real citation/paper APIs | **Not integrated** |
| `docs/` | **Created by Phase 6 Step 1** |

### 1.2 Frontend stack (preserve)

- React, Vite, TypeScript, Tailwind CSS
- Zustand (`verificationStore`, `authStore`)
- React Router (protected `/app/*` routes)
- Supabase client (anon key only, browser-side)
- Existing report components: `VerificationLoading`, `VerificationResultView`, `VerificationReportView`, `AgentAnalysisPanel`, `EvidenceCard`, etc.

### 1.3 Frontend routes (do not break)

| Route | Purpose |
|-------|---------|
| `/app/home` | Dashboard |
| `/app/verify` | New verification form |
| `/app/verify/:verificationId` | Historical report |
| `/app/history` | Verification history |
| `/app/settings` | User settings |

### 1.4 Verification types (reuse as API contract target)

**Source:** `frontend/src/types/verification.ts`

The backend should ultimately produce responses mappable to **`VerificationResult`**:

```typescript
interface VerificationResult {
  id: string
  claim: string
  citation: string
  sourceType: 'doi' | 'url' | 'citation' | 'reference'
  context?: string
  citationStatus: 'verified' | 'fabricated' | 'unverified'
  verdict: VerdictKey          // SUPPORTS | OVERSTATED | CONTRADICTS | INSUFFICIENT | FABRICATED
  confidence: number
  summary: string
  reasoning: string
  evidenceFactors: EvidenceFactor[]
  prosecutor: AgentAnalysis    // UI maps to Claim Challenger
  defender: AgentAnalysis      // UI maps to Evidence Defender
  adjudicator: AgentAnalysis   // UI maps to Final Reviewer
  evidence: EvidenceItem[]
  suggestedCorrection: SuggestedCorrection
  createdAt: string
}
```

**Verdict keys:** `frontend/src/constants/verdicts.ts`

**Form input:** `VerificationFormInput` — claim, citation, sourceType, context?

**Progress callbacks:** `VerificationProgressUpdate` — stageId, stageIndex, message?

### 1.5 Mock verification (keep as fallback)

| File | Role |
|------|------|
| `frontend/src/services/mockVerificationService.ts` | `verifyCitationMock()` — simulates 7 stages, ~3.5s |
| `frontend/src/mocks/verification.ts` | `VERIFICATION_STAGES`, `MOCK_VERIFICATION_HISTORY`, `buildMockVerificationResult()` |
| `frontend/src/pages/VerifyPage.tsx` | Calls `verifyCitationMock()` directly today |

Mock pipeline stages (internal IDs; public UI uses Claim Challenger / Evidence Defender / Final Reviewer):

1. `citation-identified`
2. `paper-checked`
3. `evidence-retrieved`
4. `prosecutor` (Claim Challenger)
5. `defender` (Evidence Defender)
6. `adjudicator` (Final Reviewer)
7. `report`

### 1.6 Zustand verification store

**File:** `frontend/src/stores/verificationStore.ts`

- `records: VerificationResult[]` — seeded with `MOCK_VERIFICATION_HISTORY`
- `addRecord`, `getRecord`
- **Not persisted** — data lost on refresh

### 1.7 Supabase (current)

**Migration:** `supabase/migrations/001_create_profiles.sql`

- `profiles` table linked to `auth.users`
- RLS: users read/update own profile
- Signup trigger creates profile row

**Missing for Phase 6:** `verifications`, `citations`, `evidence`, `agent_analyses`

**Client:** `frontend/src/lib/supabase.ts` — anon key only (correct)

**Env (frontend):** `frontend/src/lib/env.ts`

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_API_BASE_URL` (defined in code, **not** in `.env.example` yet)

### 1.8 API client scaffold (unused)

**File:** `frontend/src/services/api.ts`

- Axios `apiClient` with `baseURL: env.apiBaseUrl`
- **Never imported** — ready to wire in Step 12

### 1.9 Security rules (must hold)

- Service-role key **backend only**
- Never `VITE_*` for secrets
- Never commit `.env`
- Frontend never calls Crossref / OpenAlex / LLM directly

---

## 2. Target pipeline (Phase 6 end state)

```
User claim + citation/DOI
        ↓
React (verificationService.ts — MOCK | REAL)
        ↓
FastAPI Backend
        ↓
Citation Resolver (Crossref → OpenAlex fallback)
        ↓
Paper Metadata Retrieval
        ↓
Paper Content Retrieval (open access only; no paywall bypass)
        ↓
Document Parser + Chunking
        ↓
Evidence Retrieval (lexical v1 → embeddings later)
        ↓
Claim Challenger → Evidence Defender → Final Reviewer
        ↓
Structured Verdict
        ↓
Supabase Persistence (RLS per user)
        ↓
Existing React Verification Report (VerificationResult)
```

**Phase 6A first milestone (before agents):**

```
React → FastAPI → DOI/citation → real metadata → content/evidence → structured response (verdict may be null)
```

---

## 3. Proposed backend folder structure

Create new `backend/` (nothing exists to extend):

```
backend/
├── app/
│   ├── main.py                      # FastAPI app, CORS, router registration
│   ├── api/
│   │   ├── deps.py                  # Auth: validate Supabase JWT, current user
│   │   └── routes/
│   │       ├── health.py            # GET /api/health
│   │       ├── verification.py      # POST/GET verification
│   │       └── citations.py         # Optional: POST /api/citations/resolve (debug)
│   ├── core/
│   │   ├── config.py                # pydantic-settings from env
│   │   └── logging.py               # Structured logging (Step 16)
│   ├── schemas/
│   │   ├── verification.py          # Request/response Pydantic models
│   │   ├── citation.py              # NormalizedCitation
│   │   ├── evidence.py              # EvidenceItem, DocumentChunk
│   │   └── agents.py                # Agent output schemas (Step 9)
│   ├── services/
│   │   ├── citation_resolver.py     # Normalize DOI/URL/citation string
│   │   ├── paper_retriever.py       # Metadata + full-text/abstract fetch
│   │   ├── document_parser.py       # HTML/XML/PDF → chunks
│   │   ├── evidence_retriever.py    # Rank chunks vs claim
│   │   ├── verification_service.py  # Orchestrates pipeline
│   │   └── agents/
│   │       ├── claim_challenger.py
│   │       ├── evidence_defender.py
│   │       └── final_reviewer.py
│   ├── clients/
│   │   ├── crossref.py
│   │   ├── openalex.py
│   │   └── llm.py                   # Replaceable LLM client
│   ├── db/
│   │   ├── supabase_client.py       # Service-role client (server only)
│   │   └── repositories/
│   │       └── verification_repo.py
│   └── utils/
│       ├── doi.py                   # DOI normalization
│       └── errors.py                # Structured API errors
├── tests/
│   ├── test_citation_resolver.py
│   ├── test_paper_retriever.py
│   ├── test_evidence_retriever.py
│   ├── test_verification_api.py
│   └── test_agents.py
├── requirements.txt
├── pyproject.toml                   # optional; prefer requirements.txt for simplicity
├── .env.example
└── README.md
```

**Design principle:** Route handlers are thin; orchestration lives in `verification_service.py`; external I/O in `clients/` and `services/`.

---

## 4. Environment configuration

### 4.1 Backend `.env.example` (placeholders only)

```env
# Server
ENV=development
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173

# Supabase (service role — NEVER expose to frontend)
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=          # optional if validating JWT locally

# External APIs
CROSSREF_API_URL=https://api.crossref.org
OPENALEX_API_URL=https://api.openalex.org
CROSSREF_MAILTO=              # polite pool per Crossref guidelines

# LLM (Step 9+)
LLM_API_KEY=
LLM_MODEL=

# Feature flags
ENABLE_AGENTS=false           # Phase 6A: citation + retrieval only
```

### 4.2 Frontend `.env.example` (add when wiring Step 12)

```env
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_API_BASE_URL=http://localhost:8000
VITE_VERIFICATION_MODE=mock    # mock | real
```

---

## 5. Database schema proposal

New migration: `supabase/migrations/002_create_verifications.sql`

### 5.1 Entity relationships

```
auth.users
    ↓
profiles (existing)
    ↓
verifications (user_id → auth.users)
    ├── citations (1:1 or 1:N per verification)
    ├── evidence (1:N)
    └── agent_analyses (1:N, max 3 per run)
```

### 5.2 Tables

#### `verifications`

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | `verification_id` in API |
| user_id | uuid FK → auth.users | owner |
| claim | text | user input |
| source_type | text | doi \| url \| citation \| reference |
| context | text nullable | optional |
| status | text | processing \| completed \| failed |
| verdict | text nullable | SUPPORTS \| … \| FABRICATED |
| confidence | numeric nullable | 0–100 |
| summary | text nullable | |
| reasoning | text nullable | |
| citation_status | text | verified \| fabricated \| unverified |
| suggested_correction | jsonb nullable | `{ originalClaim, problem, suggestedWording }` |
| evidence_factors | jsonb nullable | `[{ text, supported }]` |
| error_code | text nullable | structured failure |
| error_message | text nullable | user-safe message |
| created_at | timestamptz | |
| updated_at | timestamptz | |

**Indexes:** `(user_id, created_at DESC)`, `(user_id, status)`

#### `citations`

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| verification_id | uuid FK | |
| raw_input | text | original citation string |
| identifier | text nullable | normalized DOI or URL |
| identifier_type | text | doi \| url \| citation |
| title | text nullable | |
| authors | jsonb nullable | string[] |
| journal | text nullable | |
| publication_year | int nullable | |
| doi | text nullable | |
| source_url | text nullable | |
| abstract | text nullable | |
| retrieval_status | text | resolved \| partial \| not_found |
| access_level | text nullable | full_text \| abstract_only \| metadata_only \| unavailable |
| created_at | timestamptz | |

#### `evidence`

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | maps to `EvidenceItem.id` |
| verification_id | uuid FK | |
| chunk_id | text nullable | internal parser id |
| title | text nullable | |
| authors | text nullable | |
| source | text | |
| year | int nullable | |
| excerpt | text | |
| why_it_matters | text nullable | |
| relevance | numeric | 0–100 |
| strength | text nullable | HIGH \| MEDIUM \| LOW |
| evidence_type | text | |
| identifier | text nullable | |
| source_url | text nullable | |
| section | text nullable | |
| page | int nullable | |
| relevance_score | numeric nullable | raw retrieval score |
| verdict | text nullable | per-evidence tag if used |
| created_at | timestamptz | |

#### `agent_analyses`

| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| verification_id | uuid FK | |
| agent | text | claim_challenger \| evidence_defender \| final_reviewer |
| role | text | display label |
| summary | text | |
| finding | text | |
| position | text nullable | supports \| challenges \| uncertain |
| reasoning | text nullable | extended reasoning |
| evidence_ids | uuid[] nullable | FK to evidence.id |
| confidence | numeric nullable | |
| status | text | completed \| running \| failed |
| created_at | timestamptz | |

### 5.3 RLS policies

- Enable RLS on all four tables
- `SELECT/INSERT/UPDATE/DELETE` where `auth.uid() = user_id` on `verifications`
- Child tables: access via `verification_id IN (SELECT id FROM verifications WHERE user_id = auth.uid())`
- Backend service-role bypasses RLS for server-side writes only when using user-scoped inserts with validated JWT `sub`

---

## 6. API contracts

Base path: `/api`  
Auth: `Authorization: Bearer <supabase_access_token>` on all verification routes (except health).

### 6.1 Health (Milestone 1)

```
GET /api/health
→ 200 { "status": "ok", "version": "0.1.0" }
```

### 6.2 Create verification (Milestone 7 — Phase 6A partial)

```
POST /api/verification
Content-Type: application/json

Request:
{
  "claim": "AI improves software development productivity by 50%",
  "citation": "10.1000/example",
  "source_type": "doi",
  "context": "optional"
}

Response 202 | 200:
{
  "verification_id": "uuid",
  "status": "completed" | "processing" | "failed",
  "citation": { /* NormalizedCitation */ },
  "evidence": [ /* EvidenceItem[] */ ],
  "verdict": null,           // Phase 6A: null until agents (Step 9)
  "confidence": null,
  "summary": "Citation resolved; evidence retrieved.",
  "agents": null             // or partial during processing
}
```

**Phase 6A:** When agents disabled, return real citation + evidence with `verdict: null` and UI shows retrieval status (or map to `INSUFFICIENT` with explanation — decision at integration time).

**Errors (structured):**

```json
{
  "error": {
    "code": "CITATION_NOT_FOUND",
    "message": "The citation could not be resolved.",
    "details": {}
  }
}
```

| HTTP | Code | When |
|------|------|------|
| 400 | `INVALID_REQUEST` | validation failure |
| 401 | `UNAUTHORIZED` | missing/invalid JWT |
| 404 | `CITATION_NOT_FOUND` | DOI not in Crossref/OpenAlex |
| 422 | `CITATION_UNRESOLVED` | partial/unparseable citation |
| 503 | `EXTERNAL_API_ERROR` | Crossref timeout/rate limit |
| 500 | `INTERNAL_ERROR` | generic (no stack trace to client) |

### 6.3 Get verification

```
GET /api/verification/{verification_id}
→ 200 VerificationResponse (full, mappable to VerificationResult)
→ 404 if not found or not owned by user
```

### 6.4 Get evidence only

```
GET /api/verification/{verification_id}/evidence
→ 200 { "evidence": [ ... ] }
```

### 6.5 Internal schema: NormalizedCitation

```json
{
  "identifier": "10.1000/example",
  "identifier_type": "doi",
  "title": "...",
  "authors": ["Smith, J."],
  "journal": "Example Journal",
  "publication_year": 2024,
  "doi": "10.1000/example",
  "source_url": "https://doi.org/10.1000/example",
  "abstract": "...",
  "retrieval_status": "resolved"
}
```

### 6.6 Internal schema: Document + chunks

```json
{
  "document_id": "uuid",
  "title": "...",
  "source_url": "...",
  "content_type": "html|xml|pdf|abstract",
  "access_level": "full_text|abstract_only|metadata_only|unavailable",
  "text": "...",
  "chunks": [
    {
      "chunk_id": "...",
      "text": "...",
      "section": "Results",
      "page": 4,
      "source_url": "..."
    }
  ]
}
```

### 6.7 Agent outputs (Step 9)

**Claim Challenger / Evidence Defender:**

```json
{
  "agent": "claim_challenger",
  "position": "supports|challenges|uncertain",
  "reasoning": "...",
  "evidence_ids": ["uuid", "..."],
  "confidence": 0.82
}
```

**Final Reviewer:**

```json
{
  "verdict": "OVERSTATED",
  "confidence": 76,
  "explanation": "...",
  "evidence_factors": [{ "text": "...", "supported": true }],
  "suggested_correction": "..."
}
```

### 6.8 Mapping backend → frontend `VerificationResult`

| Frontend field | Backend source |
|----------------|----------------|
| `id` | `verification_id` |
| `prosecutor` | `agent_analyses` where agent = claim_challenger |
| `defender` | evidence_defender |
| `adjudicator` | final_reviewer |
| `citationStatus` | derived from `citations.retrieval_status` + fabrication checks |
| `evidence` | `evidence` table rows |

**Verdict rules (Step 10):** Inaccessible paper → `INSUFFICIENT`, not `FABRICATED`, unless citation itself is invalid/fabricated.

---

## 7. Frontend integration plan (Step 12 — later)

### 7.1 New service abstraction

**Create:** `frontend/src/services/verificationService.ts`

```typescript
export type VerificationMode = 'mock' | 'real'

export async function verifyCitation(
  input: VerificationFormInput,
  onProgress?: (update: VerificationProgressUpdate) => void,
): Promise<VerificationResult>
```

- Read mode from `VITE_VERIFICATION_MODE` (default `mock`)
- **mock:** delegate to existing `verifyCitationMock()`
- **real:** `POST /api/verification` via `apiClient`, attach Supabase session token, map response → `VerificationResult`
- Optionally poll `GET /api/verification/{id}` if async processing

### 7.2 Minimal VerifyPage change

Replace direct `verifyCitationMock` import with `verifyCitation` from `verificationService.ts`.

### 7.3 Store evolution

Phase 6A: keep Zustand for client cache; optionally hydrate from `GET /api/verification` on history/report routes.

Phase 6B: load history from Supabase via backend list endpoint (future).

**Do not remove mock store seed** until real persistence is verified.

---

## 8. Development milestones (ordered)

| # | Milestone | Deliverable |
|---|-----------|-------------|
| 1 | Backend health | `GET /api/health`, FastAPI scaffold, CORS |
| 2 | Citation resolver | DOI/URL normalization, Crossref client |
| 3 | Paper metadata | OpenAlex fallback, `NormalizedCitation` |
| 4 | Paper content | Open-access fetch, access_level enum |
| 5 | Document parser | PDF/HTML text + chunks |
| 6 | Evidence retrieval | Lexical ranking v1 |
| 7 | Verification API | `POST/GET /api/verification` (verdict null) |
| 8 | Claim Challenger | LLM + evidence ID validation |
| 9 | Evidence Defender | LLM + evidence ID validation |
| 10 | Final Reviewer | Verdict + suggested correction |
| 11 | Supabase persistence | Migration 002 + RLS + repo |
| 12 | Frontend integration | `verificationService.ts`, env flag |
| 13 | End-to-end | Real DOI → report in UI |

---

## 9. Recommended first implementation (next session)

**Start with Milestone 1 only:**

1. Create `backend/` FastAPI app with `GET /api/health`
2. Add `backend/.env.example` and `backend/requirements.txt`
3. Add `backend/README.md` with local run instructions
4. Update `frontend/.env.example` with `VITE_API_BASE_URL` (no code wiring yet)
5. Verify CORS from `http://localhost:5173`

**Then Milestone 2–3:**

6. `utils/doi.py` + `clients/crossref.py`
7. `services/citation_resolver.py` + unit tests
8. Optional debug route `POST /api/citations/resolve`

**Do not yet:**

- Modify dashboard or report UI components
- Remove mock verification
- Add LLM agents
- Commit secrets or service-role keys to frontend

---

## 10. Risk & constraint checklist

| Rule | Approach |
|------|----------|
| Do not break frontend | MOCK mode remains default |
| Do not fabricate metadata | Return structured `not_found` / `partial` |
| Do not bypass paywalls | `access_level: unavailable` → INSUFFICIENT path |
| Agents cite evidence IDs only | Validate IDs against retrieval set |
| Service role server-only | `db/supabase_client.py` reads env, never imported in frontend |
| Buildable after each step | Each milestone has tests + manual curl check |
| No commit/push | Per project instructions |

---

## 11. Files referenced (inspection index)

| Path | Purpose |
|------|---------|
| `frontend/src/types/verification.ts` | Canonical UI/API types |
| `frontend/src/services/mockVerificationService.ts` | Mock pipeline |
| `frontend/src/mocks/verification.ts` | Mock data + stage definitions |
| `frontend/src/stores/verificationStore.ts` | In-memory history |
| `frontend/src/pages/VerifyPage.tsx` | Verification entry point |
| `frontend/src/services/api.ts` | Axios scaffold |
| `frontend/src/lib/env.ts` | Frontend env loader |
| `frontend/src/lib/supabase.ts` | Supabase browser client |
| `supabase/migrations/001_create_profiles.sql` | Existing DB |

---

*End of Phase 6 Step 1 architecture document.*
