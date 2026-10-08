# SciVerify

## Evidence-Backed AI Scientific Claim Verification

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19.0+-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6?style=flat&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=flat&logo=supabase&logoColor=white)](https://supabase.com/)
[![Pytest](https://img.shields.io/badge/Tests-466%20Passed-brightgreen?style=flat&logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **SciVerify** is an evidence-backed AI verification engine that analyzes whether a scientific claim is supported, overstated, contradicted, insufficiently evidenced, or associated with a fabricated citation by cross-examining the claim directly against retrieved passages from the cited research paper.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Why SciVerify?](#2-why-sciverify)
3. [The Problem](#3-the-problem)
4. [The Solution](#4-the-solution)
5. [Key Features](#5-key-features)
6. [AI-Driven vs. Deterministic Architecture](#6-ai-driven-vs-deterministic-architecture)
7. [System Architecture](#7-system-architecture)
8. [End-to-End Verification Flow](#8-end-to-end-verification-flow)
9. [Multi-Agent Verification Layer](#9-multi-agent-verification-layer)
10. [Evidence Retrieval Pipeline](#10-evidence-retrieval-pipeline)
11. [Claim Traceability Engine](#11-claim-traceability-engine)
12. [Verification & Confidence Validation](#12-verification--confidence-validation)
13. [Rate-Limit & Failure Handling](#13-rate-limit--failure-handling)
14. [Technology Stack](#14-technology-stack)
15. [Project Structure](#15-project-structure)
16. [Data & Persistence](#16-data--persistence)
17. [API Reference](#17-api-reference)
18. [Frontend Architecture](#18-frontend-architecture)
19. [Backend Architecture](#19-backend-architecture)
20. [Testing & Quality Assurance](#20-testing--quality-assurance)
21. [Example Verification (BNT162b2 Clinical Trial)](#21-example-verification-bnt162b2-clinical-trial)
22. [Installation & Setup](#22-installation--setup)
23. [Environment Configuration](#23-environment-configuration)
24. [Running Locally](#24-running-locally)
25. [Production Build](#25-production-build)
26. [Limitations](#26-limitations)
27. [Future Improvements](#27-future-improvements)
28. [Contributing](#28-contributing)
29. [License](#29-license)

---

## 1. Overview

SciVerify is designed to reduce scientific citation misrepresentation. It compares a natural-language claim against the full text and structured evidence extracted from a cited academic paper.

The pipeline moves deterministically through distinct layers:

$$\text{Claim + DOI} \longrightarrow \text{Paper Discovery} \longrightarrow \text{Evidence Extraction} \longrightarrow \text{Adversarial Agents} \longrightarrow \text{Validator} \longrightarrow \text{Traceability} \longrightarrow \text{Report}$$

Rather than treating Large Language Models as ungrounded authorities, SciVerify combines **deterministic document parsing, multi-tier open-access paper retrieval, numeric verification, adversarial agent debate, rule-based response validation, and clause-level claim traceability**.

---

## 2. Why SciVerify?

LLMs generate fluent summaries but frequently hallucinate facts, invent citations, or misattribute findings. Human reviewers, on the other hand, spend hours skimming 30-page PDFs to verify whether a single sentence in an article accurately reflects a study's results.

SciVerify acts as an **evidence-backed, AI-assisted verification assistant**:
- It locates the actual open-access paper via standard academic APIs.
- It extracts the specific section chunks containing relevant numerical and lexical data.
- It subjects the claim to an adversarial debate between a **Prosecutor** (looking for flaws and overstatements) and a **Defender** (finding corroborating evidence), adjudicated by an **Adjudicator**.
- It validates the verdict and calculates clause-level traceability scores so users can inspect the exact evidence backing each part of the claim.

---

## 3. The Problem

Scientific literature and digital media suffer from common forms of citation misattribution:
- **Exaggerated Claims**: Reporting that a compound "cures cancer" when the paper demonstrated a 15% reduction in tumor cell growth in in-vitro models.
- **Numerical Mismatches**: Quoting numbers, percentages, or sample sizes that conflict with published tables.
- **Scope Creep**: Asserting human causality from animal models or uncontrolled pilot studies.
- **Contradictory Citations**: Citing a paper whose conclusion reached the exact opposite finding.
- **Fabricated Citations**: Citing non-existent papers or DOIs that resolve to unrelated disciplines.
- **Opaque Attribution**: Presenting claims without clear reference to the specific paragraphs or sections in the cited work.

---

## 4. The Solution

SciVerify enforces strict groundedness:
1. **Source Grounding**: Agents only have access to chunked passages extracted from the cited document.
2. **Adversarial Cross-Examination**: An agent specifically tasked with challenging the claim balances out confirmatory bias.
3. **Canonical Validator**: The backend validator audits agent outputs, normalizes confidence ratings, and prevents invalid verdict states.
4. **Deterministic Traceability**: Clause-level token, stem, skip-bigram, and numeric match algorithms independently measure evidence support without relying on LLM self-reporting.

---

## 5. Key Features

- **Multi-Source Legal Paper Discovery**: Integrates Europe PMC, OpenAlex, Unpaywall, Semantic Scholar, and CrossRef without bypassing paywalls or anti-bot protections.
- **Adversarial 3-Agent Architecture**: Uses specialized Prosecutor, Defender, and Adjudicator agent roles.
- **Clause-Level Claim Traceability**: Segments compound claims into individual factual clauses and maps each clause to corresponding paper chunks.
- **Morphological & Numeric Verification**: Accommodates natural scientific variations (e.g. parenthetical confidence intervals, verb inflections) while enforcing numerical precision.
- **Five-Tier Scientific Verdict System**: Categorizes claims into `SUPPORTS`, `OVERSTATED`, `CONTRADICTS`, `INSUFFICIENT`, or `FABRICATED`.
- **Fault-Tolerant Provider Handling**: Backoff and delay parsing for HTTP 429 rate limits, with clean UI error isolation to prevent stale report display.
- **Authentication & History**: Optional Supabase-backed user authentication and verification history with Row Level Security.
- **Interactive Report Interface**: Clean, responsive UI featuring evidence factor breakdowns, agreement badges, and synchronized chunk highlighting.

---

## 6. AI-Driven vs. Deterministic Architecture

SciVerify separates probabilistic generative tasks from deterministic verification rules:

| Component | Nature | Description |
| :--- | :--- | :--- |
| **Claim Preprocessing** | Deterministic | Cleans text, extracts target numbers, and normalizes tokens. |
| **DOI Resolution** | Deterministic / API | Standardizes DOI format and resolves CrossRef/OpenAlex metadata. |
| **Paper Retrieval** | Deterministic / API | Queries academic discovery endpoints and enforces legal access tiers. |
| **Document Parsing & Chunking** | Deterministic | Extracts sections and partitions text into overlapping character chunks. |
| **Evidence Ranking** | Deterministic | Computes TF-IDF/lexical overlap, numeric matching, and section weighting. |
| **Prosecutor Agent** | LLM-Driven | Adversarial prompt targeting discrepancies, limitations, and overclaims. |
| **Defender Agent** | LLM-Driven | Supportive prompt identifying corroborating data and author conclusions. |
| **Adjudicator Agent** | LLM-Driven | Synthesizes opposing arguments to form the initial reasoning and verdict. |
| **Verification Validator** | Deterministic | Audits verdict consistency, calibrates confidence, and filters corrections. |
| **Claim Traceability Engine** | Deterministic | Computes multi-chunk token, stem, skip-bigram, and numeric coverage scores. |
| **Data Persistence** | Deterministic | Stores structured JSON records in Supabase PostgreSQL tables. |

---

## 7. System Architecture

```mermaid
flowchart TD
    subgraph Client ["Frontend Layer (React 19 + TypeScript + Vite)"]
        UI[User Interface]
        Store[Zustand Verification Store]
        Mapper[Verification Result Mapper]
    end

    subgraph API ["Backend API Layer (FastAPI)"]
        VRoute["/api/verification/analyze"]
        PRoute["/api/papers/retrieve"]
        ERoute["/api/evidence/retrieve"]
        CRoute["/api/citations/resolve"]
    end

    subgraph Retrieval ["Academic Retrieval Engine"]
        Retriever[Universal Paper Retriever]
        EPMC[Europe PMC REST]
        OAlex[OpenAlex API]
        Unpay[Unpaywall API]
        SScholar[Semantic Scholar Graph API]
        Parser[Document Parser & Section Chunker]
    end

    subgraph EvidenceEngine ["Evidence Pipeline"]
        Scorer[Evidence Ranker & Filter]
        Chunks[(Evidence Chunks)]
    end

    subgraph AgentLayer ["Multi-Agent Verification Layer"]
        LLMGate[LLM Provider Gateway]
        Pros[Prosecutor Agent]
        Def[Defender Agent]
        Adj[Adjudicator Agent]
    end

    subgraph ValidationEngine ["Deterministic Auditing Layer"]
        Validator[Verification Validator]
        TraceEngine[Claim Traceability Engine]
    end

    subgraph Persistence ["Persistence Layer"]
        DB[(Supabase PostgreSQL)]
    end

    UI --> Store
    Store --> Mapper
    UI --> VRoute
    VRoute --> Retriever
    Retriever --> EPMC & OAlex & Unpay & SScholar
    Retriever --> Parser
    Parser --> Scorer
    Scorer --> Chunks
    Chunks --> Pros & Def
    LLMGate --> Pros & Def
    Pros & Def --> Adj
    LLMGate --> Adj
    Adj --> Validator
    Chunks --> TraceEngine
    Validator --> TraceEngine
    TraceEngine --> VRoute
    VRoute --> Mapper
    Store --> DB
```

---

## 8. End-to-End Verification Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant FE as React Frontend
    participant API as FastAPI Backend
    participant Ret as Paper Retriever
    participant Agents as Prosecutor / Defender / Adjudicator
    participant Val as Validator & Traceability
    participant DB as Supabase DB

    User->>FE: Enters Claim and DOI
    FE->>API: POST /api/verification/analyze
    API->>API: Preprocess claim & extract numbers
    API->>Ret: Resolve DOI & fetch open-access paper
    Ret-->>API: Extracted & ranked evidence chunks
    API->>Agents: Run Prosecutor & Defender in parallel
    Agents-->>API: Agent key points & evidence IDs
    API->>Agents: Run Adjudicator with combined arguments
    Agents-->>API: Adjudicator verdict, confidence & reasoning
    API->>Val: Validate verdict, calibrate confidence & compute traceability
    Val-->>API: Validated VerificationResponse payload
    API-->>FE: HTTP 200 VerificationResponse
    FE->>DB: Save record to verification_history (if authenticated)
    FE-->>User: Renders interactive Verification Report
```

---

## 9. Multi-Agent Verification Layer

```mermaid
flowchart TD
    E[Ranked Evidence Chunks] --> P[Prosecutor Agent]
    E --> D[Defender Agent]

    subgraph Debate ["Dialectic Cross-Examination"]
        P -->|Challenges, Overstatements, Limitations| A[Adjudicator Agent]
        D -->|Corroborations, Numbers, Direct Findings| A
    end

    A --> V[Adjudicated Verdict & Reasoning]
```

### 1. Prosecutor Agent
- **Goal**: Attempt to disprove, weaken, or challenge the claim using only the supplied evidence chunks.
- **Focus**: Numeric mismatches, unstated assumptions, scope limitations, sample size constraints, and overclaimed causal relationships.
- **Constraint**: Cannot invent outside facts; must reference evidence only by `chunk_id`.

### 2. Defender Agent
- **Goal**: Find and present the strongest supporting evidence for the claim.
- **Focus**: Direct statistical matches, corroborating conclusions, and affirmative context from the study results.

### 3. Adjudicator Agent
- **Goal**: Weigh the Prosecutor's critique against the Defender's evidence.
- **Focus**: Determine the initial verdict, provide comprehensive reasoning, evaluate agent agreement, and propose a calibrated correction if the claim is overstated or contradicted.

---

## 10. Evidence Retrieval Pipeline

SciVerify operates a legal, multi-tier open-access discovery pipeline that strictly respects publisher access boundaries without bypassing paywalls or anti-bot challenges:

| Tier | Source Type | Implementation |
| :--- | :--- | :--- |
| **Tier 0** | **PMC PDF** | Authoritative NIH Open Access PDF repository. |
| **Tier 1** | **Europe PMC / PMC HTML** | Open access biomedical XML/HTML repositories. |
| **Tier 2** | **OA Repository PDF** | arXiv, bioRxiv, Zenodo, and Unpaywall repository locations. |
| **Tier 3** | **OA Repository HTML** | Institutional repository landing and full-text pages. |
| **Tier 4** | **Semantic Scholar OA PDF** | Open-access PDFs discovered via the Semantic Scholar Graph API. |
| **Tier 5** | **Publisher OA PDF** | Legitimate open-access publisher PDF distributions. |
| **Tier 6** | **Publisher OA HTML** | Legitimate open-access publisher HTML articles. |

### Document Parsing & Chunking
When a paper document is retrieved:
1. **Structure Extraction**: The document is segmented into standard sections (`Abstract`, `Introduction`, `Methods`, `Results`, `Discussion`, `Conclusions`).
2. **Chunking**: Sections are divided into overlapping character chunks (default: 1,000 characters with 200-character overlap).
3. **Scoring & Selection**: Chunks are scored against the claim using token overlap, claim overlap, numerical matching, and section weights (e.g. prioritizing `Results` and `Conclusions` over `Introduction`).
4. **Diversity Guarantee**: The top $K$ chunks are selected with diversity caps per section to prevent over-representation of a single paragraph.

---

## 11. Claim Traceability Engine

The Claim Traceability Engine ([`backend/app/services/claim_traceability.py`](backend/app/services/claim_traceability.py)) provides deterministic verification visibility by mapping each clause of a claim to corresponding evidence chunks.

```mermaid
flowchart LR
    Claim["Scientific Claim"] --> Seg["Claim Segmenter"]
    Seg --> S1["Clause 1: Efficacy Value"]
    Seg --> S2["Clause 2: Timing / Regimen"]
    Seg --> S3["Clause 3: Study Phase"]

    S1 & S2 & S3 --> Matcher["Multi-Chunk Matcher (Tokens, Stems, Skip-Bigrams, Numbers)"]
    Matcher --> Trace["Traceability Status & Coverage Score"]
```

### Matching Algorithms
1. **Morphological Stemming**: Tokens are normalized using suffix stripping (`_stem_token`) to match verb and noun inflections (e.g., *prevents* $\leftrightarrow$ *prevented*, *improves* $\leftrightarrow$ *improvement*).
2. **Skip-Bigram Phrase Matching**: Evaluates content-word pairs within a 5-word window to tolerate parenthetical confidence intervals and prepositional qualifiers without losing phrase specificity (e.g., `"95% effective (95% CI, 90.3 to 97.6) in preventing"` $\leftrightarrow$ `"approximately 95% effective at preventing"`).
3. **Numeric Overlap**: Detects exact numbers, ranges, and percentage expressions.
4. **Multi-Chunk Coverage Aggregation**:
   $$\text{Coverage}_{\text{multi}} = \max\left(\text{Score}_{\text{top}}, 0.50 \cdot \text{Score}_{\text{top}} + 0.35 \cdot \text{Overlap}_{\text{union}} + 0.10 \cdot \mathbb{I}_{\text{numeric}} + 0.05 \cdot \mathbb{I}_{N \ge 3}\right)$$

### Clause Traceability Statuses

| Status | Threshold / Condition |
| :--- | :--- |
| **`SUPPORTED`** | Aggregated segment coverage score $\ge 0.65$. |
| **`PARTIALLY_SUPPORTED`** | Aggregated segment coverage score between $0.35$ and $0.65$. |
| **`UNSUPPORTED`** | Aggregated segment coverage score $< 0.35$. |
| **`CONTRADICTED`** | Adjudicator explicitly flags the segment chunk as contradicting with match score $\ge 0.40$. |

*(Note: Segment traceability statuses describe clause-level evidence alignment and are distinct from the top-level verification verdict.)*

---

## 12. Verification & Confidence Validation

The Verification Validator ([`backend/app/services/verification_validator.py`](backend/app/services/verification_validator.py)) is the authoritative gatekeeper between raw LLM outputs and the API response:

- **Single Source of Truth**: Overrides ungrounded confidence scores and resolves agent disagreements.
- **Suggested Correction Rules**:
  - Stripped for `SUPPORTS` and `INSUFFICIENT` verdicts (where no rewording is appropriate).
  - Validated for `OVERSTATED`, `CONTRADICTS`, and `FABRICATED` to provide a grounded replacement phrasing.
- **Confidence Calibration**: Clamps confidence values between $0.0$ and $1.0$, penalizing verdicts that exhibit high agent disagreement or low evidence coverage.

### Scientific Verdict System

| Verdict | Definition | Example Scenario |
| :--- | :--- | :--- |
| **`SUPPORTS`** | The cited paper's evidence directly and accurately confirms the claim. | Paper states 95% vaccine efficacy; claim asserts ~95% efficacy in the trial. |
| **`OVERSTATED`** | The underlying finding is supported, but the claim exaggerates scope, numbers, or causality. | Study shows a 12% improvement in rodents; claim asserts a 40% cure in humans. |
| **`CONTRADICTS`** | The cited evidence directly refutes or proves the opposite of the claim. | Clinical trial finds no reduction in mortality; claim asserts significantly reduced mortality. |
| **`INSUFFICIENT`** | Full text is inaccessible or retrieved chunks contain insufficient data to verify. | Short metadata abstract with no numeric tables or trial findings. |
| **`FABRICATED`** | The paper has no topical relationship to the claim, or the DOI is fraudulent. | An astronomy paper cited as proof for a cardiovascular drug claim. |

---

## 13. Rate-Limit & Failure Handling

SciVerify incorporates a resilient handling strategy for external LLM API rate limits (HTTP 429) and network failures:

```mermaid
flowchart TD
    Req[LLM Request] --> Gateway[LLM Gateway]
    Gateway --> Res{HTTP Status}

    Res -->|200 OK| Success[Parse & Validate Structured Output]
    Res -->|429 Rate Limit| CheckRetry{Transient or Quota Exhausted?}

    CheckRetry -->|Transient 429| Delay[Parse Retry-After Header & Sleep]
    Delay --> RetryReq[Retry Attempt up to max_retries]
    RetryReq --> Gateway

    CheckRetry -->|Daily Quota or Retries Exhausted| RLError[Raise LLMRateLimitError]
    RLError --> FailResp[Return VerificationStatus.VERIFICATION_FAILED]

    FailResp --> FEMapper[Frontend Service throws VerificationServiceError status 429]
    FEMapper --> ErrorUI[Render Rate-Limit Error Banner in UI]
```

### Deterministic UI Error Isolation
- When an LLM request fails, the backend returns `VerificationStatus.VERIFICATION_FAILED` with `verdict=None` and `confidence=None`.
- The frontend state machine immediately enters `phase === 'error'` and resets any `freshResult` state.
- **Stale Cached Reports Prevented**: Failed verification attempts never fall back to displaying previous verification results from history.

---

## 14. Technology Stack

### Backend
| Technology | Purpose |
| :--- | :--- |
| **Python 3.11+** | Core runtime environment. |
| **FastAPI** | High-performance asynchronous REST API framework. |
| **Uvicorn** | Production-ready ASGI web server. |
| **Pydantic v2** | Strict schema definition and runtime validation. |
| **HTTPX** | Async/Sync HTTP client with custom connection pooling and retry policies. |
| **PyPDF** | PDF text extraction engine. |
| **BeautifulSoup4 / lxml** | HTML article scraping and DOM section parsing. |
| **Pytest** | Automated unit, service, and regression testing suite. |
| **OpenAI / Groq API** | Compatible LLM provider gateway (`gpt-oss-120b`, `gpt-4o-mini`, etc.). |

### Frontend
| Technology | Purpose |
| :--- | :--- |
| **React 19** | Component-based user interface library. |
| **TypeScript** | Static typing mirroring backend schema models. |
| **Vite** | Modern frontend bundler and development server. |
| **Tailwind CSS** | Utility-first CSS styling with custom design tokens. |
| **Zustand** | Lightweight client-side state management. |
| **React Hook Form + Zod** | Form management and schema validation. |
| **React Router v7** | Single-page application routing and parameter handling. |
| **Lucide React** | Scalable vector icons. |
| **Sonner** | Toast notification system. |

### Database & Auth
| Technology | Purpose |
| :--- | :--- |
| **Supabase** | Managed PostgreSQL backend with Row Level Security (RLS). |
| **Supabase Auth** | User authentication, token management, and password recovery. |

---

## 15. Project Structure

```
SciVerify/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/           # REST route handlers (verification, papers, evidence, citations)
│   │   ├── evaluation/           # Benchmark fixtures, metrics, and diagnostics
│   │   ├── schemas/              # Pydantic models (evidence, verification, citation, paper)
│   │   ├── services/
│   │   │   ├── agents/           # Prosecutor, Defender, and Adjudicator agent logic
│   │   │   ├── llm/              # LLM provider wrapper, rate limiter, and error hierarchy
│   │   │   ├── claim_traceability.py    # Clause segmentation and evidence mapping
│   │   │   ├── citation_resolver.py     # DOI resolution (Crossref / OpenAlex)
│   │   │   ├── document_parser.py       # PDF/HTML section extractor
│   │   │   ├── evidence_chunker.py      # Overlapping chunk generator
│   │   │   ├── evidence_pipeline.py     # Evidence retrieval, ranking, and filtering
│   │   │   ├── paper_retriever.py       # 7-tier legal full-text paper retriever
│   │   │   └── verification_validator.py# Single-source confidence and verdict validator
│   │   ├── utils/                # Preprocessors, segmenters, and DOI regex
│   │   └── tests/                # 466 Pytest unit and integration tests
│   ├── config.py                 # Environment and hyperparameter configuration
│   ├── main.py                   # FastAPI entrypoint and CORS configuration
│   └── requirements.txt          # Python dependencies
│
├── frontend/
│   ├── src/
│   │   ├── components/           # UI, layout, verification, and app components
│   │   ├── constants/            # Verdict mappings and application routes
│   │   ├── hooks/                # Custom React hooks (auth, user)
│   │   ├── layouts/              # AppLayout, RootLayout
│   │   ├── lib/                  # DOI parsing, Supabase client, and utility functions
│   │   ├── pages/                # VerifyPage, HistoryPage, AppHomePage, LoginPage
│   │   ├── routes/               # React Router definitions and ProtectedRoute
│   │   ├── services/             # Axios API client, history service, and mappers
│   │   ├── stores/               # Zustand state stores
│   │   └── types/                # TypeScript interface declarations
│   ├── package.json              # Frontend scripts and npm dependencies
│   ├── tsconfig.json             # TypeScript configuration
│   └── vite.config.ts            # Vite build configuration
│
├── supabase/
│   └── migrations/               # SQL schema migrations (profiles, verification_history)
├── LICENSE                       # MIT License
└── README.md                     # Project documentation
```

---

## 16. Data & Persistence

When configured with Supabase, SciVerify stores verification records and user profiles with PostgreSQL Row Level Security (RLS).

### Entity-Relationship Diagram

```mermaid
erDiagram
    AUTH_USERS ||--o| PROFILES : "has profile"
    AUTH_USERS ||--o{ VERIFICATION_HISTORY : "owns records"

    PROFILES {
        uuid id PK,FK
        text full_name
        timestamptz updated_at
    }

    VERIFICATION_HISTORY {
        uuid id PK
        uuid user_id FK
        text claim
        text doi
        text paper_title
        text verdict
        numeric confidence
        text summary
        jsonb result_json
        timestamptz created_at
    }
```

- `public.profiles`: Synchronized automatically on user registration via database trigger.
- `public.verification_history`: Stores the full verification output (`result_json`), claim, DOI, verdict, and confidence. Protected by RLS policies ensuring users can only read, write, and delete their own records.

---

## 17. API Reference

Interactive OpenAPI documentation is available locally at `http://127.0.0.1:8000/docs` when the backend is running with the Local Demo commands below.

### Key Endpoints

#### 1. Analyze Verification
```http
POST /api/verification/analyze
```
**Request Body**:
```json
{
  "claim": "The BNT162b2 mRNA vaccine was approximately 95% effective at preventing COVID-19 after the second dose in the phase 2/3 trial.",
  "doi": "10.1056/NEJMoa2034577"
}
```
**Response (Sample)**:
```json
{
  "status": "success",
  "claim": "The BNT162b2 mRNA vaccine was approximately 95% effective at preventing COVID-19 after the second dose in the phase 2/3 trial.",
  "verdict": "SUPPORTS",
  "confidence": 0.854,
  "summary": "The evidence directly demonstrates 95% vaccine efficacy against Covid-19 after the second dose in the Phase 2/3 trial.",
  "reasoning": "Results section reports 8 cases of Covid-19 with onset at least 7 days after the second dose in the vaccine group vs 162 in the placebo group, corresponding to 95.0% efficacy.",
  "paper": {
    "paper_id": "10.1056/nejmoa2034577",
    "doi": "10.1056/nejmoa2034577",
    "title": "Safety and Efficacy of the BNT162b2 mRNA Covid-19 Vaccine"
  },
  "evidence": [...],
  "agent_agreement": false,
  "claim_traceability": {
    "segments": [
      {
        "id": "segment_1",
        "text": "The BNT162b2 mRNA vaccine was approximately 95% effective at preventing COVID-19 after the second dose in the phase 2/3 trial.",
        "status": "SUPPORTED",
        "coverage_score": 0.789,
        "evidence_ids": ["10.1056/nejmoa2034577:Results:3", "10.1056/nejmoa2034577:Conclusions:7"]
      }
    ],
    "overall_coverage": 0.789,
    "warnings": []
  }
}
```

#### 2. Retrieve Paper
```http
POST /api/papers/retrieve
```
Retrieves academic metadata, open-access status, and parsed section chunks for a DOI.

#### 3. Retrieve Evidence
```http
POST /api/evidence/retrieve
```
Extracts and ranks evidence chunks specifically for a given claim and DOI.

#### 4. Resolve Citation
```http
POST /api/citations/resolve
```
Resolves a raw DOI into normalized bibliographic metadata via CrossRef and OpenAlex.

---

## 18. Frontend Architecture

- **State Management**: Zustand stores manage verification records and asynchronous loading states.
- **View Transitions**: Deterministic state transitions (`form` $\rightarrow$ `loading` $\rightarrow$ `result` / `error`) isolate fresh submissions from stored records.
- **Interactive Highlighting**: Clicking on a claim traceability clause automatically focuses and highlights the supporting evidence cards in the report.
- **Accessibility & Design**: Built with responsive containers, ARIA labels, semantic HTML5 tags, and dark-mode styling.

---

## 19. Backend Architecture

- **Modularity**: Dedicated service packages for paper retrieval, document parsing, evidence chunking, agent execution, validation, and claim traceability.
- **Defensive Error Handling**: Maps domain exceptions (`PaperNotFoundError` $\rightarrow$ 404, `FullTextUnavailableError` $\rightarrow$ 503, `InvalidClaimError` $\rightarrow$ 400).
- **Extensible LLM Providers**: Abstracted base provider supporting OpenAI-compatible gateways and custom model deployments.

---

## 20. Testing & Quality Assurance

SciVerify maintains an automated test suite with **466 passing backend tests** and verified TypeScript compilation.

### Run Backend Tests
```bash
cd backend
python -m pytest -q
```
```
================================ 466 passed in 18.16s ================================
```

### Test Categories
- **Claim Traceability Tests** (`test_claim_traceability.py`): Multi-chunk coverage, skip-bigrams, stemming, parenthetical CI handling, and contradiction isolation.
- **Universal Retrieval Tests** (`test_universal_retrieval.py`): Legal 7-tier ranking, paywall rejection, and PMCID resolution.
- **Agent Execution Tests** (`test_agents.py`): Structured output formatting and prompt compilation for Prosecutor, Defender, and Adjudicator.
- **Validation Consistency Tests** (`test_verification_validator.py`, `test_verification_consistency.py`): Confidence calibration and correction filtering.
- **Rate Limit & Fault Tolerance Tests** (`test_llm_quota_retry.py`, `test_verification_service.py`): HTTP 429 delay parsing, retry logic, and error isolation.

---

## 21. Example Verification (BNT162b2 Clinical Trial)

*The following is an example verification run against the NEJM Phase 2/3 Covid-19 vaccine trial paper:*

- **Claim**: `"The BNT162b2 mRNA vaccine was approximately 95% effective at preventing COVID-19 after the second dose in the phase 2/3 trial."`
- **DOI**: `10.1056/NEJMoa2034577`
- **Paper**: *Safety and Efficacy of the BNT162b2 mRNA Covid-19 Vaccine (Polack et al., NEJM)*

### Verification Results
- **Final Verdict**: `SUPPORTS`
- **Calibrated Confidence**: ~85%
- **Agent Agreement**: `False` (Prosecutor highlighted follow-up duration and subgroup nuances; Adjudicator confirmed primary endpoint efficacy)
- **Claim Traceability**: `SUPPORTED`
- **Traceability Coverage**: `78.9%` (10 supporting evidence chunks linked across Results and Conclusions)

*(Note: Verification confidence and narrative summaries may vary slightly between runtime evaluations depending on the underlying LLM provider model.)*

---

## 22. Installation & Setup — Local Demo

### Prerequisites
- **Git**
- **Conda** (the environment below uses Python 3.11)
- **Node.js 24.x** (recommended) or **22.x ≥22.13**, and **npm**
- Your own **DeepSeek** API key and **Alibaba Model Studio Beijing** embedding API key

Local Demo requires no Supabase project or account. It runs the existing backend verification pipeline; it does not supply fake scientific results. Real verification requires external source and model services.

From a new terminal:

```bash
git clone --branch develop https://github.com/qyc060615/SciVerify.git ResearchGuard
cd ResearchGuard
conda env create -f environment.yml
conda activate researchguard
cd backend
python -m pip install -r requirements.txt
cd ../frontend
npm ci
cd ..
```

---

## 23. Environment Configuration

### Backend Configuration
Copy `backend/.env.example` to `backend/.env`. On PowerShell, from the repository root:

```powershell
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
```

On macOS/Linux use `cp` with the same source and destination paths. Do not overwrite an existing file containing your credentials.

In `backend/.env`, set the evidence engine to `paperqa2` and fill **two** private keys: `LLM_API_KEY` for DeepSeek, and `PAPERQA2_EMBEDDING_API_KEY` for Alibaba Beijing. The relevant settings are:

```env
RESEARCHGUARD_EVIDENCE_ENGINE=paperqa2
RESEARCHGUARD_LOG_LEVEL=INFO

LLM_PROVIDER=openai-compatible
LLM_API_KEY=your_deepseek_key
LLM_MODEL=deepseek-flash
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_REQUEST_TIMEOUT=60

PAPERQA2_MODEL=openai/deepseek-flash
PAPERQA2_API_KEY=${LLM_API_KEY}
PAPERQA2_API_BASE=https://api.deepseek.com/v1

PAPERQA2_EMBEDDING_MODEL=openai/text-embedding-v4
PAPERQA2_EMBEDDING_API_KEY=your_alibaba_beijing_key
PAPERQA2_EMBEDDING_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1

RESEARCHGUARD_SOURCE_CACHE_DIR=
RESEARCHGUARD_PAPERQA_CACHE_SIZE=8
LITELLM_LOCAL_MODEL_COST_MAP=True
```

`python-dotenv` expands `${LLM_API_KEY}`, so the DeepSeek key need only be filled once. A blank source-cache directory uses `backend/data/researchguard/sources/`. The repository template retains the default lexical engine; change it to `paperqa2` for the planned PaperQA evaluation.

### Frontend Configuration
Set `frontend/.env.local` to:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_LOCAL_DEMO_MODE=true
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

> [!WARNING]
> Never commit real credentials. `backend/.env` and `frontend/.env.local` are ignored. Model API keys belong only in the backend, never in a `VITE_*` variable.

Local Demo is enabled only when **Vite development mode AND the flag is exactly `true`**. It uses a stable local identity with no session/token. Supabase authentication, profiles and history are not called, even if Supabase environment values remain populated. Login/register and password-recovery routes return to the workspace; settings are read-only and no logout action is shown.

For normal Supabase mode, set `VITE_LOCAL_DEMO_MODE=false` (or omit it), configure `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`, and restart the frontend. Missing Supabase configuration does not automatically enable Demo.

---

## 24. Running Local Demo

### Terminal 1: Start the Backend (from the repository root)
```bash
conda activate researchguard
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
The backend health endpoint is `http://127.0.0.1:8000/health` and API documentation is `http://127.0.0.1:8000/docs`.

### Terminal 2: Start the Frontend (from the repository root)
```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```
Open **`http://127.0.0.1:5173`** and select **Start verifying** or **Enter Local Demo**.

Demo history stores complete reports in browser localStorage under `researchguard:demo:history:v1`, using `{ "version": 1, "records": [...] }`. It supports reopening report URLs after refresh and deleting records. History belongs to the current browser and origin: `localhost` and `127.0.0.1` do **not** share it, nor do different ports, browsers or computers. There is no cloud synchronization. Browser data deletion removes this history.

Unreadable storage produces a nonblocking warning; individual invalid records are skipped without inventing a verdict. An invalid/unsupported top-level envelope is left untouched by save/delete; remove that local history key in browser storage to start fresh. If saving fails (for example, storage is full or disabled), the current report remains available in memory, but may be lost on refresh. Failed deletion is reported rather than shown as successful.

Application logs default to INFO via `RESEARCHGUARD_LOG_LEVEL`. The five events to observe during the **later, manual real E2E** are `source_cache_miss`, `source_cache_hit`, `manual_source_accepted`, `paperqa_index_cache_miss`, and `paperqa_index_cache_hit`. Repeat an actual verification request to test reuse; opening a saved report does not exercise backend caches. Keep the same backend process running for index-cache reuse: indexes are process-local and cleared on restart, whereas accepted source files persist locally.

This patch is validated with offline automated tests and production compilation only. **Real DOI E2E, real manual-PDF recovery, live model/provider calls and a second-computer Clone & Run test have not been executed for this patch.** Next: local real E2E → teammate Clone & Run → M3. No launch scripts or Docker are required by this patch.

---

## 25. Production Build

### Frontend Production Build
```bash
cd frontend
npm run build
```
This executes TypeScript validation (`tsc -b`) and Vite production bundling. Output assets are placed in `frontend/dist/`.

**Production builds always disable Local Demo**, even with `VITE_LOCAL_DEMO_MODE=true` left in `.env.local`. Production/preview uses the normal Supabase mode and needs its configuration. Local Demo is intended for the development server, not an authentication mechanism for a public deployment.

---

## 26. Limitations

- **Probabilistic Reasoning**: LLM reasoning is probabilistic. Outputs should assist human researchers, not replace peer review or expert scientific analysis.
- **Full-Text Availability**: If a paper is behind an unpermitted commercial paywall or lacks an open-access repository mirror, the system will return `INSUFFICIENT` (`FULL_TEXT_UNAVAILABLE`).
- **Table & Visual Data**: Scientific data embedded solely within complex multi-column images or vector charts may not be fully parsed by standard text extraction.
- **Scope of Verdicts**: A `SUPPORTS` verdict confirms alignment between the submitted claim and the cited paper; it does not guarantee universal scientific consensus across all other literature.
- **Traceability Metric**: Clause coverage scores are system-specific algorithmic metrics designed for evidence navigation, not standard statistical measures.

---

## 27. Future Improvements

- [ ] **Multilingual Verification**: Support for claims and literature published in languages beyond English.
- [ ] **Table & Figure OCR**: Deep layout parsing for scientific tables, charts, and supplementary data files.
- [ ] **Cross-Paper Consensus**: Cross-referencing claims across multiple related papers via citation graph traversal.
- [ ] **Human-in-the-Loop Review**: Collaborative annotation workflows for academic research teams.
- [ ] **Expanded Offline Benchmarking**: Standardized evaluation datasets for continuous verdict calibration.

---

## 28. Production Deployment Guide

SciVerify follows a simple, standard three-tier deployment architecture:

```
Browser
  ↕ HTTPS
Deployed Frontend (Vercel / Netlify / Cloudflare Pages)
  ↕ HTTPS API calls
Deployed Backend FastAPI (Cloud Run / Render / Railway / Fly.io)
  ↕ HTTPS
Supabase (PostgreSQL + Auth)    ←→    Groq / OpenAI API
```

### 28.1 Architecture Overview

| Component | Recommended Host | Notes |
| :--- | :--- | :--- |
| **Frontend** (React + Vite) | Vercel / Netlify / Cloudflare Pages | Static SPA build. SPA routing covered by `vercel.json` and `public/_redirects`. |
| **Backend** (FastAPI + Uvicorn) | Google Cloud Run / Render / Railway / Fly.io | Stateless; scales horizontally. Uses `PORT` env var from platform. |
| **Database + Auth** | Supabase | Managed PostgreSQL with Row Level Security. |
| **LLM Provider** | Groq Cloud (or any OpenAI-compatible endpoint) | Configured entirely through `LLM_*` environment variables. |

---

### 28.2 Required Environment Variables

#### Backend

Set these in your hosting platform's environment configuration. **Never commit real values.**

```env
# Server (your platform injects PORT automatically on most hosts)
PORT=8000

# CORS — your deployed frontend URL
ALLOWED_ORIGINS=https://your-frontend.vercel.app

# LLM Provider
LLM_PROVIDER=groq
LLM_API_KEY=your_groq_api_key_here
LLM_MODEL=openai/gpt-oss-120b
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_REQUEST_TIMEOUT=60

# Document / Retrieval tuning (optional — defaults shown)
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
EVIDENCE_TOP_K=5
PAPER_REQUEST_TIMEOUT=30
```

#### Frontend

Set these in your hosting platform's environment configuration.

```env
VITE_API_BASE_URL=https://your-backend.run.app
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_public_key_here
```

> [!WARNING]
> Only the Supabase **anon/public** key should ever appear in frontend environment variables.
> Never place your Supabase `service_role` key, Groq key, or any secret in `VITE_*` variables.

---

### 28.3 Backend Deployment

#### Option A — Docker (Cloud Run / Fly.io / Render)

A production-ready `Dockerfile` is included at `backend/Dockerfile`.

```bash
# Build and test the Docker image locally
cd backend
docker build -t sciverify-backend .

# Run with your actual environment variables
docker run --rm -p 8000:8000 \
  -e LLM_API_KEY=your_api_key \
  -e LLM_MODEL=openai/gpt-oss-120b \
  -e LLM_BASE_URL=https://api.groq.com/openai/v1 \
  -e ALLOWED_ORIGINS=https://your-frontend.vercel.app \
  sciverify-backend
```

Verify the health check:
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","service":"sciverify-backend"}
```

#### Option B — Direct Uvicorn (Render / Railway / Fly.io)

Configure your host to run:
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The `PORT` env variable is automatically injected by Cloud Run, Render, Railway, and Fly.io.

---

### 28.4 Frontend Deployment

#### Vercel (recommended)

1. Connect your GitHub repository to Vercel.
2. Set **Root Directory** to `frontend`.
3. Framework Preset: **Vite**.
4. Set environment variables in Vercel Dashboard → Settings → Environment Variables.
5. Deploy. SPA routing is handled automatically by `frontend/vercel.json`.

#### Netlify

1. Connect your GitHub repository.
2. Set **Base directory** to `frontend`, **Build command** to `npm run build`, **Publish directory** to `dist`.
3. Set environment variables in Site Settings → Environment variables.
4. SPA routing is handled automatically by `frontend/public/_redirects`.

#### Cloudflare Pages

1. Create a new Pages project from your GitHub repository.
2. Build command: `npm run build`, Output directory: `dist`.
3. Environment variables: add `VITE_*` keys in the Cloudflare dashboard.
4. SPA routing is handled by `frontend/public/_redirects`.

---

### 28.5 Supabase Configuration

1. Create a project at [supabase.com](https://supabase.com).
2. Go to **SQL Editor** and run migrations in order:
   ```bash
   supabase/migrations/001_create_profiles.sql
   supabase/migrations/002_create_verification_history.sql
   ```
3. Under **Authentication → URL Configuration**:
   - **Site URL**: `https://your-frontend.vercel.app`
   - **Redirect URLs**: add `https://your-frontend.vercel.app/reset-password`
4. Copy **Project URL** and **anon/public key** from Project Settings → API.

---

### 28.6 CORS Configuration

Set the `ALLOWED_ORIGINS` environment variable on your backend to your deployed frontend URL:

```env
ALLOWED_ORIGINS=https://your-frontend.vercel.app
```

For multiple origins (e.g. staging and production):
```env
ALLOWED_ORIGINS=https://your-frontend.vercel.app,https://staging.your-frontend.vercel.app
```

`localhost` origins are always included automatically for local development.

---

### 28.7 Health Check

Both endpoints return `{"status":"ok","service":"sciverify-backend"}`:

```
GET /health          (platform-level health probes)
GET /api/health      (application-level health probes)
```

Use `/health` as your platform's health check or liveness probe path.

---

### 28.8 Local Production Verification

Run these checks before deploying:

```bash
# 1. Backend: full test suite (must stay at 466 passing)
cd backend
python -m pytest -q

# 2. Frontend: production build (must complete with 0 errors)
cd ../frontend
npm run build

# 3. Backend: production startup
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8001

# 4. Health check
curl http://localhost:8001/health

# 5. Verification endpoint smoke test
curl -s -X POST http://localhost:8001/api/verification/analyze \
  -H "Content-Type: application/json" \
  -d '{"claim":"test","doi":"10.0000/invalid"}' | python -m json.tool
```

---

### 28.9 Common Deployment Issues

| Issue | Cause | Fix |
| :--- | :--- | :--- |
| Frontend shows "Cannot connect to SciVerify backend" | `VITE_API_BASE_URL` is wrong or missing | Set correct backend URL in frontend env vars; rebuild and redeploy. |
| CORS errors in browser | `ALLOWED_ORIGINS` on backend not set to your frontend URL | Update `ALLOWED_ORIGINS` env var and restart backend. |
| Deep page refresh returns 404 | SPA routing not configured on the host | `frontend/vercel.json` covers Vercel; `public/_redirects` covers Netlify / Cloudflare. |
| Backend returns `verification_failed` on every request | `LLM_API_KEY` is missing or invalid | Set the correct `LLM_API_KEY` for your provider. |
| Backend container exits immediately | `PORT` not injected or startup command missing | Confirm your host injects `PORT`; use the Uvicorn CMD shown above. |
| Supabase auth redirect fails | Site URL and Redirect URLs not updated in Supabase dashboard | Update under Authentication → URL Configuration. |

---

### 28.10 Security Notes

- **Never commit** `.env` files — both are git-ignored by `.gitignore`.
- The **Supabase anon key** is safe to expose in frontend builds; it is subject to Row Level Security.
- **Do not** expose `SUPABASE_SERVICE_ROLE_KEY` in frontend code or any `VITE_*` variable.
- **Do not** expose `LLM_API_KEY` in frontend code — it must only be set on the backend.
- Use `.env.example` templates (placeholders only) for onboarding contributors.

---

## 29. Contributing

Contributions to SciVerify are welcome:
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/improvement`).
3. Ensure all backend tests pass (`python -m pytest -q`) and frontend builds cleanly (`npm run build`).
4. Commit your changes (`git commit -m 'Add improvement'`).
5. Push to the branch (`git push origin feature/improvement`).
6. Open a Pull Request.

---

## 30. License

This project is licensed under the [MIT License](LICENSE).

