# Embedding Batch Compatibility Patch

Baseline: `b8140e5171c00e490e28829ce111c7f5afde6869` on `develop`.

## Root cause and change

PaperQA's production embedding factory constructs LMI's
`LiteLLMEmbeddingModel`. Without `config["batch_size"]`, the installed LMI
implementation defaults to 16 input texts per request. Alibaba Model Studio
Beijing's `text-embedding-v4` accepts at most 10, causing the real PDF index build
to fail with HTTP 400. Injected LocalEmbedding tests bypassed this production
batching path and could not expose the incompatibility.

`PaperQA2Config.embedding_batch_size` now defaults to 10 and reads
`PAPERQA2_EMBEDDING_BATCH_SIZE`. It must be a positive integer. Invalid environment
values or constructor values raise the existing safe `paperqa2_configuration`
error without echoing input values, provider bodies, or credentials.

`make_settings()` supplies:

```python
embedding_config = {
    "batch_size": self.embedding_batch_size,
    "kwargs": {"timeout": self.timeout, ...},
}
```

Configured embedding API key/base remain under `kwargs`. Batch size is neither
an embedding provider keyword nor PaperQA's independent `Settings.batch_size`.
No model-name-specific provider branches were added. The source-index cache key
is unchanged: request batching does not change embedding vector semantics or
source/chunk identity.

## Files

- `backend/app/researchguard/adapters/paperqa2.py`: config, validation, factory input.
- `backend/.env.example`: `PAPERQA2_EMBEDDING_BATCH_SIZE=10`.
- `README.md`: Local Demo setting and provider compatibility explanation.
- `backend/app/tests/test_paperqa2_integration.py`: 16 additional offline cases.
- This report.

## Production-style offline regression

Tests call real `Settings.get_embedding_model()` and assert the result is a
`LiteLLMEmbeddingModel` with the configured batch size. Only `litellm.aembedding`
is mocked; PaperQA's factory, LMI's embedding loop and router remain real. The
mock provider rejects any batch larger than 10 and returns deterministic vectors.
For 25 texts, actual calls contain 10/10/5 inputs; an explicit setting of 8
produces 8/8/8/1. Input ordering and all 25 returned vectors are checked, as are
API key/base/timeout forwarding and the absence of a provider `batch_size` kwarg.

The pinned LMI API embeds a single query using `embed_documents([query])`; a
one-item test confirms that path works. A real Docs-index test constructs
production embedding models with batch sizes 10 then 8, injects only the offline
summary model, and verifies a single index build followed by a cache hit.
Existing source reuse and M2 regressions remain in the full suite.

Final validation in `backend`: `python -m pytest -q` — **662 passed**, one existing
Starlette TestClient deprecation warning. The suite's public-network guard was
active. No real provider, DOI, browser, or E2E was called; no backend/frontend
service was started or restarted. Real `.env` files were untouched. No commit
or push was performed for this patch.

## Limits

The positive integer setting does not automatically discover provider limits.
Changing providers may require a different batch size; a value exceeding that
provider's input-count or token limits can still fail. This patch does not change
chunk count/size, source retrieval/qualification, manual recovery, evidence
algorithms, verifier, agents, frontend, or Local Demo behavior. A separately
authorized real E2E is still needed to validate the complete live report chain.

Recommended commit: `fix: configure PaperQA embedding batch size`.
