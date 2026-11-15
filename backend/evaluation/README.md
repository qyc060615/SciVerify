# SciVerify Evaluation & Regression Framework

Developer-only benchmark tooling for measuring SciVerify quality over time. This package evaluates stored `VerificationResponse` fixtures against labeled benchmark cases. It does **not** modify the production verification pipeline.

## Purpose

Use this framework to detect regressions when changing:

- evidence retrieval, parsing, deduplication, or ranking
- verdict validation
- claim traceability

Offline evaluation is the default. No API keys or Groq calls are required for tests or normal CLI usage.

## Dataset

Benchmark cases live in `evaluation/dataset.json`. Each case includes:

- `id` — unique case identifier
- `claim` — user claim text
- `doi` — normalized DOI for the cited paper
- `expected_verdict` — one of `SUPPORTS`, `OVERSTATED`, `CONTRADICTS`, `INSUFFICIENT`, `FABRICATED`
- `description` — human-readable case note
- optional `expected_min_evidence_count`
- optional `expected_traceability_statuses`

The dataset is a developer benchmark only. Expected labels reflect benchmark intent, not universal scientific truth.

## Offline fixtures

Deterministic `VerificationResponse` JSON files live in `evaluation/fixtures/{case_id}.json`. These power offline evaluation and unit tests.

Regenerate fixtures after changing `app/evaluation/fixture_factory.py`:

```bash
cd backend
python -c "from app.evaluation.fixture_factory import write_all_fixtures; from app.evaluation.dataset_loader import default_fixtures_dir; write_all_fixtures(default_fixtures_dir())"
```

## Run offline evaluation

```bash
cd backend
python -m app.evaluation.run
```

Optional flags:

```bash
python -m app.evaluation.run --dataset evaluation/dataset.json
python -m app.evaluation.run --fixtures-dir evaluation/fixtures
python -m app.evaluation.run --output-dir evaluation/results
```

Reports are written to:

- `evaluation/results/latest.json`
- `evaluation/results/latest.md`

## Compare against baseline

```bash
cd backend
python -m app.evaluation.run --compare-baseline
```

Baseline metrics are stored in `evaluation/baseline.json`. The CLI exits with code `1` when a regression is detected.

Configurable tolerances (environment variables):

- `VERDICT_ACCURACY_TOLERANCE` (default `0.02`)
- `EVIDENCE_COVERAGE_TOLERANCE` (default `0.03`)
- `DUPLICATE_RATE_TOLERANCE` (default `0.01`)
- `TRACEABILITY_COMPLETENESS_TOLERANCE` (default `0.03`)
- `AVERAGE_RELEVANCE_TOLERANCE` (default `0.03`)

## Update baseline

The baseline is **never** updated automatically. After reviewing current metrics:

```bash
cd backend
python -m app.evaluation.run --update-baseline
```

Review the printed report before using this flag.

## Metrics

- **Verdict accuracy** — correct verdicts / evaluated cases, plus confusion matrix
- **Evidence** — count, duplicate rate, average relevance, average claim overlap
- **Traceability** — completeness, segment status rates, overall coverage
- **Validation** — override rate, warning rate
- **Agent agreement** — agreement rate when the field is present
- **Confidence** — averages for correct/incorrect cases, min/max, simple confidence error diagnostic

Confidence error is a simple diagnostic (`abs(confidence - correctness)`), not formal calibration.

## Optional live evaluation

Live mode runs the real verification pipeline and may call external APIs:

```bash
cd backend
python -m app.evaluation.run --live
```

Use only when you explicitly want live pipeline results. Automated tests never use live mode.

### Live evaluation health check

Before running live evaluation, you can check which benchmark cases are likely to succeed:

```bash
cd backend
python -m app.evaluation.run --live-health-check
```

This checks:
- DOI resolution (Crossref → OpenAlex)
- Full-text availability via OpenAlex
- Known open access repository access (PMC, Europe PMC, arXiv, etc.)

Health check results are written to `evaluation/results/health_check.json`.

### Skip unhealthy cases

To skip cases marked as unhealthy during live evaluation:

```bash
cd backend
python -m app.evaluation.run --live --skip-unhealthy
```

This requires running the health check first to generate the health check data.

### Live evaluation requirements

Live evaluation requires:
- LLM provider configured (via `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`)
- Network access to external APIs (Crossref, OpenAlex, publisher sites)
- Some benchmark cases may fail due to:
  - DOI not indexed in citation databases
  - Full text behind paywall
  - Publisher blocking automated access
  - Network timeouts or rate limits

### Failure classification

Live evaluation failures are classified into categories:
- **DOI_NOT_FOUND**: DOI not indexed in Crossref or OpenAlex
- **FULL_TEXT_UNAVAILABLE**: Metadata exists but no accessible full text
- **ANTI_BOT_BLOCKED**: Publisher blocks automated access (CAPTCHA, bot detection)
- **PAYWALLED**: Content requires subscription or purchase
- **HTTP_403**: Access forbidden
- **HTTP_404**: Resource not found
- **RATE_LIMITED**: API rate limit exceeded
- **NETWORK_TIMEOUT**: Request timeout
- **NETWORK_ERROR**: General network error
- **LLM_FAILURE**: LLM provider error
- **INVALID_DOCUMENT**: Document parsing or validation error

Deterministic failures (DOI_NOT_FOUND, FULL_TEXT_UNAVAILABLE, ANTI_BOT_BLOCKED, PAYWALLED, HTTP_404, INVALID_DOCUMENT) are not retried. Transient failures (NETWORK_TIMEOUT, RATE_LIMITED, HTTP_403) are retried up to 3 times.

## Limitations

- Benchmark quality depends on case labels and fixture fidelity.
- Offline fixtures test the evaluator and regression tooling; they do not replace end-to-end live verification.
- Small floating-point drift is tolerated via regression thresholds.

## Robustness & failure analysis

The evaluation report includes:

- per-verdict accuracy
- evidence coverage rate and traceability link rate
- confidence risk rate
- unsupported-claim detection rate
- deterministic failure categories (wrong verdict, weak evidence, missing evidence, poor traceability, overconfidence, agent disagreement, invalid evidence references, insufficient-evidence not detected)
- worst-performing cases with diagnostic details

Regression thresholds (environment variables):

- `EVAL_MIN_VERDICT_ACCURACY` (default `0.80`) — absolute floor
- `EVAL_MAX_CONFIDENCE_REGRESSION` (default `0.10`)
- `EVAL_MAX_TRACEABILITY_REGRESSION` (default `0.10`)
- `EVAL_MAX_EVIDENCE_REGRESSION` (default `0.10`)

See also the baseline-relative tolerances listed above.

## Tests

```bash
cd backend
python -m pytest app/tests/test_evaluation_metrics.py app/tests/test_evaluation_dataset.py app/tests/test_evaluation_regression.py -q
```
