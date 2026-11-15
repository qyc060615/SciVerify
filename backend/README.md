# SciVerify Backend

FastAPI backend for the SciVerify evidence-backed citation verification platform.

## Milestones

| Milestone | Status | Description |
|-----------|--------|-------------|
| 1 | Complete | FastAPI scaffold, health check, CORS |
| 2 | Complete | DOI citation resolver (Crossref → OpenAlex) |
| 3 | Complete | Paper metadata & content retrieval, evidence chunking |
| 4 | Complete | Deterministic evidence retrieval & ranking |
| 5 | Complete | Multi-agent verification (Prosecutor, Defender, Adjudicator) |
| 6+ | Planned | Frontend integration, persistence |

## Prerequisites

- Python 3.11+ recommended
- pip

## Setup

From the repository root:

```bash
cd backend
```

Create and activate a virtual environment:

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy environment placeholders (optional):

```bash
copy .env.example .env
```

On macOS/Linux:

```bash
cp .env.example .env
```

## Run the server

With the virtual environment activated, from the `backend/` directory:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Default development URLs:

| URL | Description |
|-----|-------------|
| http://127.0.0.1:8001 | API root |
| http://127.0.0.1:8001/api/health | Health check |
| http://127.0.0.1:8001/docs | Swagger UI |

## Health check

```bash
curl http://127.0.0.1:8001/api/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "sciverify-backend"
}
```

## Citation resolver (Milestone 2)

`POST /api/citations/resolve` resolves a DOI to normalized paper metadata.

**This endpoint only resolves citation metadata. It does NOT verify scientific claims.**

### Resolution flow

1. Normalize the DOI input (raw DOI, `doi:` prefix, or `doi.org` URL)
2. Query **Crossref** (`GET /works/{doi}`)
3. If Crossref cannot resolve usable metadata, fall back to **OpenAlex**
4. Return a consistent internal `CitationMetadata` structure

No API keys are required for Crossref or OpenAlex public metadata endpoints.

### Example request

```bash
curl -X POST http://127.0.0.1:8001/api/citations/resolve \
  -H "Content-Type: application/json" \
  -d "{\"doi\": \"10.1038/s41586-020-2649-2\"}"
```

### Example response

```json
{
  "doi": "10.1038/s41586-020-2649-2",
  "title": "Example Paper Title",
  "authors": ["Ada Lovelace", "Alan Turing"],
  "journal": "Nature",
  "publisher": "Nature Publishing Group",
  "year": 2020,
  "url": "https://doi.org/10.1038/s41586-020-2649-2",
  "source": "crossref",
  "type": "journal-article"
}
```

### HTTP status codes

| Code | Meaning |
|------|---------|
| 200 | Citation resolved |
| 400 | Invalid DOI |
| 404 | Citation not found in Crossref or OpenAlex |
| 503 | External provider failure (timeout, unavailable) |

## Paper retrieval (Milestone 3)

`POST /api/papers/retrieve` resolves a DOI, discovers publicly accessible full text when available, parses the document, and returns evidence-ready chunks.

**This endpoint prepares evidence for later verification. It does NOT verify scientific claims.**

### Retrieval flow

1. Normalize the DOI and resolve citation metadata via the existing citation resolver
2. Enrich metadata from **OpenAlex** (abstract, open-access locations)
3. Discover the best publicly accessible **PDF or HTML** source (no paywall bypass)
4. Download, parse, clean, and chunk the document when full text is accessible
5. Return normalized paper metadata, sections, and evidence chunks

If full text is unavailable, the API still returns metadata with `full_text_available: false` and status `full_text_unavailable`.

### Example request

```bash
curl -X POST http://127.0.0.1:8001/api/papers/retrieve \
  -H "Content-Type: application/json" \
  -d "{\"doi\": \"10.1038/s41586-020-2649-2\"}"
```

### Example response (metadata only)

```json
{
  "status": "full_text_unavailable",
  "paper": {
    "paper_id": "10.1038/s41586-020-2649-2",
    "doi": "10.1038/s41586-020-2649-2",
    "title": "Example Paper Title",
    "authors": ["Ada Lovelace"],
    "abstract": "Example abstract text.",
    "journal": "Nature",
    "publisher": "Nature Publishing Group",
    "publication_date": "2020-05-28",
    "year": 2020,
    "url": "https://doi.org/10.1038/s41586-020-2649-2",
    "source_url": "https://example.org/landing",
    "open_access": false,
    "full_text_available": false,
    "full_text_format": null,
    "full_text_url": null
  },
  "sections": [],
  "chunks": [],
  "source": {
    "url": "https://openalex.org/W123",
    "provider": "openalex"
  }
}
```

### Supported document formats

| Format | Parser |
|--------|--------|
| PDF | `pypdf` text extraction with section heuristics |
| HTML | `beautifulsoup4` heading-based section detection |

### Chunking behavior

- Section-aware chunking (Abstract, Introduction, Methods, Results, etc.)
- Configurable via `CHUNK_SIZE` (default 1000) and `CHUNK_OVERLAP` (default 200)
- Each chunk retains `paper_id`, section name, index, and source URL

### Paper retrieval HTTP status codes

| Code | Meaning |
|------|---------|
| 200 | Paper metadata returned (including metadata-only / unavailable full text) |
| 400 | Invalid DOI |
| 404 | Paper not found |
| 503 | External provider or document download failure |

## Evidence retrieval (Milestone 4)

`POST /api/evidence/retrieve` ranks the most relevant evidence chunks from a paper against a scientific claim.

**This milestone performs deterministic evidence retrieval and ranking. It does not produce the final scientific verdict.**

### Retrieval flow

1. Validate and preprocess the claim (normalization, token extraction, numeric extraction)
2. Retrieve the paper and evidence chunks via the existing Milestone 3 pipeline
3. Score every chunk deterministically against the claim
4. Return the highest-ranked evidence items

### Scoring approach

Each chunk receives a bounded `relevance_score` between 0 and 1 based on:

| Component | Weight | Description |
|-----------|--------|-------------|
| Token overlap | 50% | Share of meaningful claim tokens present in the chunk |
| Phrase overlap | 25% | Bonus for consecutive claim phrases found in the chunk |
| Numeric overlap | 15% | Whether numeric claims align (`1.0` exact match, `0.5` different values, `0.0` missing) |
| Section weight | 10% | Preference for Results/Methods over References |

Section weighting influences ranking only. It does not determine correctness.

### Example request

```bash
curl -X POST http://127.0.0.1:8001/api/evidence/retrieve \
  -H "Content-Type: application/json" \
  -d "{\"claim\": \"The method improves accuracy by 40%.\", \"doi\": \"10.1038/s41586-020-2649-2\"}"
```

### Example response

```json
{
  "status": "success",
  "claim": "The method improves accuracy by 40%.",
  "paper": {
    "paper_id": "10.1038/s41586-020-2649-2",
    "doi": "10.1038/s41586-020-2649-2",
    "title": "Array programming with NumPy"
  },
  "evidence": [
    {
      "chunk_id": "10.1038/s41586-020-2649-2:Results:0",
      "section": "Results",
      "chunk_index": 0,
      "text": "The proposed method improves accuracy by 12% on benchmark tasks.",
      "relevance_score": 0.78,
      "claim_overlap": 0.75,
      "numeric_overlap": 0.5,
      "claim_numbers": ["40%"],
      "evidence_numbers": ["12%"],
      "source_url": "https://example.org/paper.pdf",
      "page": 4
    }
  ],
  "total_chunks_considered": 25
}
```

### Evidence retrieval HTTP status codes

| Code | Meaning |
|------|---------|
| 200 | Evidence response returned (including no chunks / unavailable full text cases) |
| 400 | Invalid claim or DOI |
| 404 | Paper not found |
| 503 | External provider or document download failure |

### Limitations

- Deterministic token/phrase matching — no embeddings yet
- Requires Milestone 3 to produce chunks; metadata-only papers return empty evidence

## Multi-agent verification (Milestone 5)

`POST /api/verification/analyze` runs the full backend verification pipeline:

```text
claim + DOI → citation/paper/evidence pipeline → Prosecutor → Defender → Adjudicator → final result
```

**This milestone performs multi-agent evidence analysis. It does not replace the frontend mock workflow yet.**

### Agent responsibilities

| Agent | Role |
|-------|------|
| Prosecutor | Challenges the claim using retrieved evidence only |
| Defender | Builds the strongest supporting case from retrieved evidence |
| Adjudicator | Weighs both analyses and returns the final verdict |

Supported verdicts: `SUPPORTS`, `OVERSTATED`, `CONTRADICTS`, `INSUFFICIENT`, `FABRICATED`

### LLM provider configuration

Verification agents depend on an LLM provider abstraction. Configure via environment variables:

| Variable | Description |
|----------|-------------|
| `LLM_PROVIDER` | `none` (default), `openai`, or `openai-compatible` |
| `LLM_API_KEY` | Provider API key (never commit real values) |
| `LLM_MODEL` | Model name (default `gpt-4o-mini`) |
| `LLM_BASE_URL` | OpenAI-compatible base URL |
| `LLM_REQUEST_TIMEOUT` | Request timeout in seconds |

If no LLM is configured, the API returns `status: "llm_unavailable"` rather than fabricating a verdict.

### Example request

```bash
curl -X POST http://127.0.0.1:8001/api/verification/analyze \
  -H "Content-Type: application/json" \
  -d "{\"claim\": \"The method improves accuracy by 40%.\", \"doi\": \"10.1000/test\"}"
```

### Example response

```json
{
  "status": "success",
  "claim": "The method improves accuracy by 40%.",
  "verdict": "OVERSTATED",
  "confidence": 0.78,
  "summary": "Claim is directionally supported but magnitude is overstated.",
  "reasoning": "Evidence reports 12%, not 40%.",
  "paper": {
    "paper_id": "10.1000/test",
    "doi": "10.1000/test",
    "title": "Example Paper"
  },
  "evidence": [],
  "prosecutor": { "agent": "prosecutor", "analysis": "...", "stance": "skeptical", "confidence": 0.7 },
  "defender": { "agent": "defender", "analysis": "...", "stance": "supportive", "confidence": 0.65 },
  "adjudicator": { "agent": "adjudicator", "analysis": "...", "verdict": "OVERSTATED", "confidence": 0.78 },
  "suggested_correction": "The method improves accuracy by about 12%."
}
```

### Verification HTTP status codes

| Code | Meaning |
|------|---------|
| 200 | Verification response returned (including insufficient evidence / LLM unavailable) |
| 400 | Invalid claim or DOI |
| 404 | Paper not found |
| 503 | External provider or document download failure |

### Milestone 5 limitations

- Backend-only — frontend still uses mock verification
- Requires usable evidence chunks; agents are not run without evidence
- LLM output is validated and evidence references are sanitized against retrieved chunks
- No vector database or embedding retrieval

## Tests

All external HTTP calls are mocked in tests.

```bash
cd backend
python -m pytest
```

## CORS

The backend allows requests from the Vite frontend origin configured in `FRONTEND_URL` (default `http://localhost:5173`).

## Frontend integration

The React app continues to use **mock verification** for `/app/verify`. Milestone 5 adds the backend multi-agent verification endpoint only; the verification UI is not wired to it yet.

## Security

- Never expose Supabase service-role keys or LLM API keys to the frontend.
- Keep secrets in `backend/.env` only (gitignored).
- Use `VITE_*` variables in the frontend for publishable configuration only.
