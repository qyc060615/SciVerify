"""Real pinned Docs API with local input and deterministic model injection."""
from __future__ import annotations

import inspect
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from lmi import EmbeddingModel, LLMModel, LLMResult
from paperqa import Docs
from paperqa.types import Context, Doc, Text
from pydantic import Field

from app.config import EvidenceEngineConfigurationError, get_evidence_engine
from app.main import app
from app.researchguard.adapters.paperqa2 import (
    PAPERQA2_VERSION, PaperQA2Config, PaperQA2EvidenceRetriever, PaperQA2RetrievalError,
)
from app.researchguard.adapters.sciverify import (
    accepted_source_to_domain, evidence_to_legacy, standalone_claim_to_domain,
)
from app.researchguard.domain import RetrievalStatus
from app.schemas.paper import PaperMetadata, PaperRetrievalStatus, PaperSource, RetrievePaperResponse
from app.schemas.verification import AdjudicatorAnalysis, DefenderAnalysis, ProsecutorAnalysis, VerificationResponse
from app.services.document_parser import parse_html
from app.services.evidence_chunker import chunk_sections
from app.services.evidence_pipeline import aretrieve_evidence_for_claim, build_evidence_response, retrieve_evidence_for_claim
from app.services.verification_service import analyze_verification_async
from app.tests.test_agents import MockLLMProvider
from app.utils.claim_preprocessor import preprocess_claim


class LocalEmbedding(EmbeddingModel):
    name: str = "fixture-embedding"
    calls: list[list[str]] = Field(default_factory=list)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[1.0, 0.1] if any(w in t.lower() for w in ("risk", "treatment", "benefit")) else [0.1, 1.0] for t in texts]


class LocalSummary(LLMModel):
    name: str = "fixture-summary"
    mode: str = "normal"
    calls: list[str] = Field(default_factory=list)

    async def call_single(self, messages, callbacks=None, name=None, **kwargs):
        self.calls.append(name or "")
        if self.mode == "provider_error":
            raise RuntimeError("secret provider body / source content must not escape")
        prompt = str(messages[-1].content)
        score = 8 if "12%" in prompt and "Laboratory equipment" not in prompt else 2
        if self.mode == "irrelevant":
            score = 0
        output = json.dumps({"summary": "Query-specific fixture summary", "relevance_score": score})
        if self.mode == "invalid_json":
            output = "unparseable secret source text"
        if self.mode == "invalid_score":
            output = json.dumps({"summary": "fixture", "relevance_score": 99})
        return LLMResult(model=self.name, text=output, prompt_count=1, completion_count=1)


@pytest.fixture
def paper():
    html = (Path(__file__).parent / "fixtures" / "paperqa2_source.html").read_text()
    sections = parse_html(html)
    return RetrievePaperResponse(
        status=PaperRetrievalStatus.SUCCESS,
        paper=PaperMetadata(paper_id="10.1234/local", doi="10.1234/local", title="Local treatment fixture", full_text_available=True, full_text_format="html"),
        sections=sections,
        chunks=chunk_sections(sections, "10.1234/local", source_url="https://accepted.example/source"),
        source=PaperSource(url="https://accepted.example/source", provider="fixture"),
    )


@pytest.fixture
def config():
    return PaperQA2Config(model="fixture-summary", embedding_model="fixture-embedding", candidate_k=2)


@pytest.fixture
def paperqa_env(monkeypatch):
    monkeypatch.setenv("RESEARCHGUARD_EVIDENCE_ENGINE", "paperqa2")
    monkeypatch.setenv("PAPERQA2_MODEL", "fixture-summary")
    monkeypatch.setenv("PAPERQA2_EMBEDDING_MODEL", "fixture-embedding")
    monkeypatch.setenv("PAPERQA2_EVIDENCE_CANDIDATES", "2")
    monkeypatch.setenv("RESEARCHGUARD_EVIDENCE_TOP_K", "1")


def injected_factory(monkeypatch, summary=None, embedding=None):
    instances = []

    def make(chunks, config):
        instance = PaperQA2EvidenceRetriever(chunks, config, embedding_model=embedding or LocalEmbedding(), summary_model=summary or LocalSummary())
        instances.append(instance)
        return instance

    monkeypatch.setattr("app.researchguard.adapters.paperqa2.PaperQA2EvidenceRetriever", make)
    return instances


@pytest.mark.anyio
async def test_real_docs_index_embedding_context_ranking_and_mapping(paper, config, monkeypatch):
    from importlib.metadata import version
    assert version("paper-qa") == PAPERQA2_VERSION
    source, chunks = accepted_source_to_domain(paper)
    claim = standalone_claim_to_domain(preprocess_claim("Treatment reduces risk."), source)
    embedding, summary = LocalEmbedding(), LocalSummary()
    calls = []
    add, retrieve, get_evidence = Docs.aadd_texts, Docs.retrieve_texts, Docs.aget_evidence

    async def record_add(self, *args, **kwargs):
        calls.append("aadd_texts")
        result = await add(self, *args, **kwargs)
        assert set(self.docs) == {source.id}
        return result

    async def record_retrieve(self, *args, **kwargs):
        calls.append("retrieve_texts")
        return await retrieve(self, *args, **kwargs)

    async def record_evidence(self, *args, **kwargs):
        calls.append("aget_evidence")
        return await get_evidence(self, *args, **kwargs)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Discovery/download/final answer API must not be called")

    monkeypatch.setattr(Docs, "aadd_texts", record_add)
    monkeypatch.setattr(Docs, "retrieve_texts", record_retrieve)
    monkeypatch.setattr(Docs, "aget_evidence", record_evidence)
    for method in ("aadd", "aadd_file", "aadd_url", "aquery"):
        monkeypatch.setattr(Docs, method, forbidden)
    retriever = PaperQA2EvidenceRetriever(chunks, config, embedding_model=embedding, summary_model=summary)
    result = await retriever.retrieve(claim, source, 1)
    assert calls == ["aadd_texts", "aget_evidence", "retrieve_texts"]
    assert len(embedding.calls) >= 2 and len(summary.calls) == 2
    assert len(result) == 1 and result[0].retrieval_score == 8
    original = next(c for c in chunks if c.id == result[0].id)
    assert result[0].text == original.text and "12%" in result[0].text
    assert result[0].source_document_id == source.id
    assert result[0].page is None and result[0].section == original.section
    assert result[0].source_url == "https://accepted.example/source"
    assert result[0].metadata["paperqa_context_summary"] != result[0].text
    assert result[0].metadata["source_format"] == "html"
    json.dumps(result[0].metadata)


@pytest.mark.anyio
async def test_chunk_identity_is_stable_across_queries_and_changes_with_content(paper, config):
    source, chunks = accepted_source_to_domain(paper)
    retriever = PaperQA2EvidenceRetriever(chunks, config, embedding_model=LocalEmbedding(), summary_model=LocalSummary())
    results = []
    for text in ("Treatment reduces risk.", "Does treatment benefit patients?"):
        claim = standalone_claim_to_domain(preprocess_claim(text), source)
        results.append((await retriever.retrieve(claim, source, 1))[0])
    assert results[0].id == results[1].id
    assert results[0].metadata["paperqa_context_id"] != results[1].metadata["paperqa_context_id"]
    changed = paper.model_copy(deep=True)
    changed.chunks[0].text += " Additional finding."
    other_source, other_chunks = accepted_source_to_domain(changed)
    assert other_source.content_hash != source.content_hash
    assert other_chunks[0].id != chunks[0].id


@pytest.mark.anyio
@pytest.mark.parametrize("mismatch", ["source", "reference", "unavailable", "duplicate"])
async def test_adapter_rejects_source_or_reference_identity_mismatch(paper, config, mismatch):
    source, chunks = accepted_source_to_domain(paper)
    claim = standalone_claim_to_domain(preprocess_claim("Treatment reduces risk."), source)
    if mismatch == "source":
        chunks[0] = chunks[0].model_copy(update={"source_document_id": "different"})
    elif mismatch == "reference":
        claim = claim.model_copy(update={"reference_ids": ("different",)})
    elif mismatch == "unavailable":
        source = source.model_copy(update={"retrieval_status": RetrievalStatus.UNAVAILABLE})
    else:
        chunks.append(chunks[0])
    with pytest.raises(PaperQA2RetrievalError):
        await PaperQA2EvidenceRetriever(chunks, config).retrieve(claim, source, 1)


@pytest.mark.parametrize("score", [8, -1, 11])
def test_real_context_mapping_preserves_raw_text_and_validates_score(paper, score):
    source, chunks = accepted_source_to_domain(paper)
    doc = Doc(docname="fixture", dockey=source.id, citation="fixture")
    context = Context(context="summary", score=score, text=Text(text=chunks[0].text, name=chunks[0].id, doc=doc))
    if score == 8:
        mapped = PaperQA2EvidenceRetriever._map_context(context, source, {c.id: c for c in chunks})
        assert mapped.id == chunks[0].id and mapped.text == chunks[0].text
        assert mapped.metadata["paperqa_score"] == 8
    else:
        with pytest.raises(PaperQA2RetrievalError, match="invalid_score"):
            PaperQA2EvidenceRetriever._map_context(context, source, {c.id: c for c in chunks})


@pytest.mark.parametrize("mutation", ["foreign_doc", "changed_text", "unknown_chunk"])
def test_real_context_cannot_escape_accepted_source(paper, mutation):
    source, chunks = accepted_source_to_domain(paper)
    doc = Doc(docname="fixture", dockey="other" if mutation == "foreign_doc" else source.id, citation="fixture")
    context = Context(context="summary", score=8, text=Text(text="other" if mutation == "changed_text" else chunks[0].text, name="unknown" if mutation == "unknown_chunk" else chunks[0].id, doc=doc))
    with pytest.raises(PaperQA2RetrievalError, match="source_mismatch"):
        PaperQA2EvidenceRetriever._map_context(context, source, {c.id: c for c in chunks})


@pytest.mark.anyio
@pytest.mark.parametrize("mode,error", [("provider_error", "summary_failed"), ("invalid_json", "invalid_summary"), ("invalid_score", "invalid_summary")])
async def test_real_paperqa_summary_failure_is_explicit_without_source_logging(paper, config, mode, error, caplog):
    source, chunks = accepted_source_to_domain(paper)
    claim = standalone_claim_to_domain(preprocess_claim("Treatment reduces risk."), source)
    with pytest.raises(PaperQA2RetrievalError, match=error) as failure:
        await PaperQA2EvidenceRetriever(chunks, config, embedding_model=LocalEmbedding(), summary_model=LocalSummary(mode=mode)).retrieve(claim, source, 1)
    assert "secret" not in str(failure.value)
    assert "Risk decreased by 12%" not in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.anyio
async def test_legitimate_irrelevant_context_is_empty_not_failure(paper, config):
    source, chunks = accepted_source_to_domain(paper)
    claim = standalone_claim_to_domain(preprocess_claim("Treatment reduces risk."), source)
    result = await PaperQA2EvidenceRetriever(chunks, config, embedding_model=LocalEmbedding(), summary_model=LocalSummary(mode="irrelevant")).retrieve(claim, source, 1)
    assert result == []


def test_legacy_diagnostics_keep_paperqa_order_and_score_without_ranking(paper, monkeypatch):
    from app.services.evidence_retriever import _score_chunk
    source, chunks = accepted_source_to_domain(paper)
    chunks = [c.model_copy(update={"retrieval_score": 8 - i}) for i, c in enumerate(reversed(chunks))]
    processed = preprocess_claim("Treatment reduced risk by 12%.")
    forbidden = Mock(side_effect=AssertionError("Legacy ranking must not select PaperQA evidence"))
    monkeypatch.setattr("app.services.evidence_retriever.rank_evidence_for_claim", forbidden)
    items = evidence_to_legacy(chunks, processed)
    assert [item.chunk_id for item in items] == [c.id for c in chunks]
    assert [item.relevance_score for item in items] == [(8 - i) / 10 for i in range(len(chunks))]
    from app.schemas.paper import EvidenceChunk as LegacyChunk
    for i, (chunk, item) in enumerate(zip(chunks, items)):
        expected = _score_chunk(processed, LegacyChunk(chunk_id=chunk.id, paper_id=source.id, section=chunk.section, chunk_index=i, text=chunk.text))
        assert item.claim_overlap == expected.claim_overlap
        assert item.numeric_overlap == expected.numeric_overlap
        assert item.claim_numbers == expected.claim_numbers
    forbidden.assert_not_called()


@pytest.mark.parametrize("score", [None, -1, 11, float("nan")])
def test_legacy_conversion_rejects_invalid_score(paper, score):
    _, chunks = accepted_source_to_domain(paper)
    with pytest.raises(ValueError):
        evidence_to_legacy([chunks[0].model_copy(update={"retrieval_score": score})], preprocess_claim("Treatment reduces risk."))


@pytest.mark.anyio
async def test_async_lexical_engine_matches_original_result(paper, monkeypatch):
    monkeypatch.setenv("RESEARCHGUARD_EVIDENCE_ENGINE", "lexical")
    monkeypatch.setattr("app.services.evidence_pipeline.retrieve_paper", lambda doi: paper)
    expected = build_evidence_response(preprocess_claim("Treatment reduces risk."), paper)
    assert await aretrieve_evidence_for_claim("Treatment reduces risk.", paper.paper.doi) == expected


@pytest.mark.parametrize("engine", ["lexical", "paperqa2", "wrong"])
def test_engine_selection_is_explicit(engine, monkeypatch):
    monkeypatch.setenv("RESEARCHGUARD_EVIDENCE_ENGINE", engine)
    if engine == "wrong":
        with pytest.raises(EvidenceEngineConfigurationError):
            get_evidence_engine()
    else:
        assert get_evidence_engine() == engine


def test_default_engine_and_sync_entrypoint_guard(monkeypatch, paperqa_env):
    with pytest.raises(EvidenceEngineConfigurationError, match="async"):
        retrieve_evidence_for_claim("Treatment reduces risk.", "10.1234/local")
    monkeypatch.delenv("RESEARCHGUARD_EVIDENCE_ENGINE")
    assert get_evidence_engine() == "lexical"


@pytest.mark.anyio
async def test_paperqa_application_uses_exact_retrieved_source_without_lexical_fallback(paper, paperqa_env, monkeypatch):
    retrieval = Mock(return_value=paper)
    monkeypatch.setattr("app.services.evidence_pipeline.retrieve_paper", retrieval)
    forbidden = Mock(side_effect=AssertionError("No lexical ranking"))
    monkeypatch.setattr("app.services.evidence_pipeline.rank_evidence_for_claim", forbidden)
    instances = injected_factory(monkeypatch)
    result = await aretrieve_evidence_for_claim("Treatment reduces risk.", paper.paper.doi)
    assert result.status.value == "success" and len(result.evidence) == 1
    assert result.evidence[0].relevance_score == 0.8
    retrieval.assert_called_once_with(paper.paper.doi)
    assert len(instances) == 1
    assert {c.text for c in instances[0].chunks} == {c.text for c in paper.chunks}
    forbidden.assert_not_called()


@pytest.mark.anyio
async def test_embedding_failure_does_not_fall_back(paper, paperqa_env, monkeypatch):
    class BrokenEmbedding(LocalEmbedding):
        async def embed_documents(self, texts):
            raise RuntimeError("provider content")
    monkeypatch.setattr("app.services.evidence_pipeline.retrieve_paper", lambda doi: paper)
    fallback = Mock(side_effect=AssertionError("No fallback"))
    monkeypatch.setattr("app.services.evidence_pipeline.rank_evidence_for_claim", fallback)
    injected_factory(monkeypatch, embedding=BrokenEmbedding())
    with pytest.raises(PaperQA2RetrievalError, match="retrieval_failed"):
        await aretrieve_evidence_for_claim("Treatment reduces risk.", paper.paper.doi)
    fallback.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("status", [PaperRetrievalStatus.METADATA_ONLY, PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE, PaperRetrievalStatus.PARSING_FAILURE])
async def test_unavailable_source_never_runs_paperqa_or_lexical_rank(paper, paperqa_env, monkeypatch, status):
    result = paper.model_copy(update={"status": status, "chunks": []})
    monkeypatch.setattr("app.services.evidence_pipeline.retrieve_paper", lambda doi: result)
    adapter = Mock(side_effect=AssertionError("No source index"))
    monkeypatch.setattr("app.researchguard.adapters.paperqa2.PaperQA2EvidenceRetriever", adapter)
    response = await aretrieve_evidence_for_claim("Treatment reduces risk.", paper.paper.doi)
    assert response.evidence == [] and response.status.value == status.value
    adapter.assert_not_called()


@pytest.mark.parametrize("top_k", ["0", "-1", "wrong"])
def test_paperqa_configuration_error_is_api_503(top_k, paperqa_env, monkeypatch):
    monkeypatch.setenv("RESEARCHGUARD_EVIDENCE_TOP_K", top_k)
    response = TestClient(app).post("/api/verification/analyze", json={"claim": "Treatment reduces risk.", "doi": "10.1234/local"})
    assert response.status_code == 503
    assert "positive integer" in response.json()["detail"]


def test_model_settings_pass_credentials_to_correct_model_abstractions(monkeypatch):
    cfg = PaperQA2Config(model="provider/summary", embedding_model="provider/embedding", api_key="fake-summary-key", api_base="https://summary.example", embedding_api_key="fake-embedding-key", embedding_api_base="https://embedding.example")
    settings = cfg.make_settings(3)
    params = settings.summary_llm_config["model_list"][0]["litellm_params"]
    assert params["api_key"] == "fake-summary-key" and params["api_base"] == "https://summary.example"
    assert settings.embedding_config["kwargs"]["api_key"] == "fake-embedding-key"
    assert settings.embedding_config["kwargs"]["api_base"] == "https://embedding.example"
    assert settings.answer.evidence_k == 10
    assert "fake-summary-key" not in repr(cfg)


def test_full_existing_verification_api_with_real_docs_evidence(paper, paperqa_env, monkeypatch):
    from app.api.routes.verification import analyze_verification_endpoint
    assert inspect.iscoroutinefunction(analyze_verification_endpoint)
    monkeypatch.setattr("app.services.evidence_pipeline.retrieve_paper", lambda doi: paper)
    instances = injected_factory(monkeypatch)
    source, chunks = accepted_source_to_domain(paper)
    evidence_id = next(c.id for c in chunks if c.section.lower() == "results")
    llm = MockLLMProvider([
        ProsecutorAnalysis(analysis="Limited scope", stance="uncertain", confidence=0.3),
        DefenderAnalysis(analysis="Direct evidence", stance="support", supporting_evidence=[evidence_id], confidence=0.8),
        AdjudicatorAnalysis(analysis="Supported", verdict="SUPPORTS", confidence=0.8, reasoning="Source reports lower risk.", supporting_evidence=[evidence_id]),
    ])
    monkeypatch.setattr("app.services.verification_service.get_llm_provider", lambda: llm)
    response = TestClient(app).post("/api/verification/analyze", json={"claim": "Treatment reduces risk.", "doi": paper.paper.doi})
    assert response.status_code == 200
    body = response.json()
    VerificationResponse.model_validate(body)
    assert body["status"] == "success" and body["verdict"] == "SUPPORTS"
    assert body["paper"]["doi"] == paper.paper.doi
    assert body["evidence"][0]["chunk_id"] == evidence_id
    assert "12%" in body["evidence"][0]["text"]
    assert body["claim_traceability"] is not None
    assert len(llm.prompts) == 3 and len(instances) == 1


def test_paperqa_failure_is_api_error_not_semantic_verdict(paper, paperqa_env, monkeypatch):
    monkeypatch.setattr("app.services.evidence_pipeline.retrieve_paper", lambda doi: paper)
    injected_factory(monkeypatch, summary=LocalSummary(mode="provider_error"))
    response = TestClient(app).post("/api/verification/analyze", json={"claim": "Treatment reduces risk.", "doi": paper.paper.doi})
    assert response.status_code == 503
    assert response.json() == {"detail": "paperqa2_summary_failed"}


def test_evidence_api_uses_same_paperqa_path(paper, paperqa_env, monkeypatch):
    monkeypatch.setattr("app.services.evidence_pipeline.retrieve_paper", lambda doi: paper)
    injected_factory(monkeypatch)
    response = TestClient(app).post("/api/evidence/retrieve", json={"claim": "Treatment reduces risk.", "doi": paper.paper.doi})
    assert response.status_code == 200
    assert response.json()["evidence"][0]["relevance_score"] == 0.8


def test_configured_production_model_construction_uses_pinned_lmi_api():
    cfg = PaperQA2Config(model="openai/fixture-summary", embedding_model="openai/fixture-embedding", api_key="fake-summary-key", embedding_api_key="fake-embedding-key")
    settings = cfg.make_settings(1)
    summary = settings.get_summary_llm()
    embedding = settings.get_embedding_model()
    assert summary.name == cfg.model
    assert embedding.name == cfg.embedding_model
    assert embedding.config["kwargs"]["api_key"] == "fake-embedding-key"


@pytest.mark.anyio
async def test_blocking_source_and_legacy_verifier_run_off_event_loop(paper, paperqa_env, monkeypatch):
    import threading
    event_thread = threading.get_ident()
    source_threads, verifier_threads = [], []

    def retrieve(doi):
        source_threads.append(threading.get_ident())
        return paper

    class ThreadLLM(MockLLMProvider):
        def generate(self, *args, **kwargs):
            verifier_threads.append(threading.get_ident())
            return super().generate(*args, **kwargs)

    source, chunks = accepted_source_to_domain(paper)
    evidence_id = next(c.id for c in chunks if c.section.lower() == "results")
    llm = ThreadLLM([
        ProsecutorAnalysis(analysis="Scope", stance="uncertain", confidence=0.3),
        DefenderAnalysis(analysis="Support", stance="support", supporting_evidence=[evidence_id], confidence=0.8),
        AdjudicatorAnalysis(analysis="Supported", verdict="SUPPORTS", confidence=0.8, reasoning="Source finding", supporting_evidence=[evidence_id]),
    ])
    monkeypatch.setattr("app.services.evidence_pipeline.retrieve_paper", retrieve)
    injected_factory(monkeypatch)
    result = await analyze_verification_async("Treatment reduces risk.", paper.paper.doi, llm=llm)
    assert result.status.value == "success"
    assert len(source_threads) == 1 and len(verifier_threads) == 3
    assert all(t != event_thread for t in source_threads + verifier_threads)


@pytest.mark.anyio
async def test_adapter_rejects_unexpected_installed_release(paper, config, monkeypatch):
    monkeypatch.setattr("importlib.metadata.version", lambda name: "unexpected")
    source, chunks = accepted_source_to_domain(paper)
    claim = standalone_claim_to_domain(preprocess_claim("Treatment reduces risk."), source)
    with pytest.raises(PaperQA2RetrievalError, match="version_mismatch"):
        await PaperQA2EvidenceRetriever(chunks, config, embedding_model=LocalEmbedding(), summary_model=LocalSummary()).retrieve(claim, source, 1)


def test_known_page_and_source_metadata_are_preserved(paper):
    paper.chunks[0].page = 4
    paper.chunks[0].metadata = {"page_range": [4, 5], "section_order": 0}
    source, chunks = accepted_source_to_domain(paper)
    doc = Doc(docname="fixture", dockey=source.id, citation="fixture")
    context = Context(context="summary", score=7, text=Text(text=chunks[0].text, name=chunks[0].id, doc=doc))
    mapped = PaperQA2EvidenceRetriever._map_context(context, source, {c.id: c for c in chunks})
    assert mapped.page == 4
    assert mapped.metadata["legacy_metadata"]["page_range"] == [4, 5]


@pytest.mark.parametrize("variable,value", [("PAPERQA2_MODEL", ""), ("PAPERQA2_EMBEDDING_MODEL", ""), ("PAPERQA2_EVIDENCE_CANDIDATES", "0"), ("PAPERQA2_REQUEST_TIMEOUT", "nan")])
def test_invalid_model_config_fails_clearly_without_retrieval(paperqa_env, monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(PaperQA2RetrievalError, match="configuration"):
        PaperQA2Config.from_environment()


def test_embedding_batch_size_defaults_and_environment(paperqa_env, monkeypatch):
    monkeypatch.delenv("PAPERQA2_EMBEDDING_BATCH_SIZE", raising=False)
    assert PaperQA2Config(model="fixture", embedding_model="fixture").embedding_batch_size == 10
    assert PaperQA2Config.from_environment().embedding_batch_size == 10
    monkeypatch.setenv("PAPERQA2_EMBEDDING_BATCH_SIZE", "8")
    assert PaperQA2Config.from_environment().embedding_batch_size == 8


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "invalid-secret-input", ""])
def test_invalid_embedding_batch_environment_is_safe(paperqa_env, monkeypatch, value):
    monkeypatch.setenv("PAPERQA2_EMBEDDING_BATCH_SIZE", value)
    with pytest.raises(PaperQA2RetrievalError, match="paperqa2_configuration") as error:
        PaperQA2Config.from_environment()
    assert "invalid-secret-input" not in str(error.value)


@pytest.mark.parametrize("value", [0, -1, 1.5, "10", True])
def test_direct_embedding_batch_config_requires_positive_integer(value):
    with pytest.raises(PaperQA2RetrievalError, match="paperqa2_configuration"):
        PaperQA2Config(model="fixture", embedding_model="fixture", embedding_batch_size=value)


def batch_config(batch_size=10):
    return PaperQA2Config(model="openai/fixture-summary", embedding_model="openai/fixture-embedding",
        embedding_batch_size=batch_size, embedding_api_key="fake-embedding-key",
        embedding_api_base="https://embedding.example/v1", timeout=17.0)


def test_embedding_batch_settings_are_model_config_not_provider_kwargs():
    settings = batch_config().make_settings(3)
    assert settings.embedding_config == {"batch_size": 10, "kwargs": {
        "timeout": 17.0, "api_key": "fake-embedding-key", "api_base": "https://embedding.example/v1"}}
    assert settings.batch_size == 1  # PaperQA's LLM batch setting is independent.


@pytest.fixture
def embedding_api_calls(monkeypatch):
    import litellm
    calls = []

    async def embedding_api(**kwargs):
        texts = list(kwargs["input"])
        assert 0 < len(texts) <= 10, "Simulated provider rejects oversized batches"
        calls.append({**kwargs, "input": texts})
        return litellm.EmbeddingResponse(model=kwargs["model"],
            data=[{"object": "embedding", "index": i, "embedding": [1.0, 0.1]} for i in range(len(texts))],
            usage={"prompt_tokens": len(texts), "total_tokens": len(texts)})

    # Mock only the provider boundary. Keep PaperQA factory, LMI model/router and batching real.
    monkeypatch.setattr(litellm, "aembedding", embedding_api)
    return calls


@pytest.mark.anyio
@pytest.mark.parametrize("batch_size,expected", [(10, [10, 10, 5]), (8, [8, 8, 8, 1])])
async def test_production_embedding_factory_batches_25_texts(embedding_api_calls, batch_size, expected):
    from lmi import LiteLLMEmbeddingModel
    model = batch_config(batch_size).make_settings(1).get_embedding_model()
    assert isinstance(model, LiteLLMEmbeddingModel)
    assert model.config["batch_size"] == batch_size
    texts = [f"Offline text {i}" for i in range(25)]
    vectors = await model.embed_documents(texts)
    assert len(vectors) == 25 and all(vector == [1.0, 0.1] for vector in vectors)
    assert [len(call["input"]) for call in embedding_api_calls] == expected
    assert [text for call in embedding_api_calls for text in call["input"]] == texts
    for call in embedding_api_calls:
        assert call["api_key"] == "fake-embedding-key"
        assert call["api_base"] == "https://embedding.example/v1" and call["timeout"] == 17.0
        assert "batch_size" not in call


@pytest.mark.anyio
async def test_production_single_query_embedding(embedding_api_calls):
    model = batch_config().make_settings(1).get_embedding_model()
    # The pinned LMI/PaperQA path embeds a query as a one-item documents list.
    assert await model.embed_documents(["Offline query"]) == [[1.0, 0.1]]
    assert [call["input"] for call in embedding_api_calls] == [["Offline query"]]


@pytest.mark.anyio
async def test_changing_batch_size_reuses_production_source_index(paper, embedding_api_calls, monkeypatch, caplog):
    source, chunks = accepted_source_to_domain(paper)
    claim = standalone_claim_to_domain(preprocess_claim("Treatment reduces risk."), source)
    cfg = batch_config()
    added = []
    original_add = Docs.aadd_texts

    async def record_add(self, *args, **kwargs):
        added.append(True)
        return await original_add(self, *args, **kwargs)

    monkeypatch.setattr(Docs, "aadd_texts", record_add)
    caplog.set_level("INFO")
    # Actual embedding factories, same semantic config; only transport batch size changes.
    for config in (cfg, replace(cfg, embedding_batch_size=8)):
        retriever = PaperQA2EvidenceRetriever(chunks, config, summary_model=LocalSummary())
        assert await retriever.retrieve(claim, source, 1)
    assert len(added) == 1
    assert "paperqa_index_cache_miss" in caplog.text and "paperqa_index_cache_hit" in caplog.text
    assert len([call for call in embedding_api_calls if len(call["input"]) == 1]) >= 2
