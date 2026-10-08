"""Offline M2 artifact, identity, recovery, and real PaperQA index regressions."""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from paperqa import Docs

from app.main import app
from app.schemas.citation import CitationMetadata
from app.schemas.evidence import EvidenceRetrievalResponse, EvidenceRetrievalStatus, EvidencePaperSummary
from app.schemas.paper import PaperMetadata
from app.schemas.verification import ProsecutorAnalysis, DefenderAnalysis, AdjudicatorAnalysis
from app.services.source_store import AcceptedSourceArtifact, LocalSourceStore
from app.services.manual_source import accept_manual_pdf, match_pdf_identity, ManualSourceError
from app.services import paper_retriever as retrieval
from app.services.document_retriever import RetrievedDocument
from app.services.citation_resolver import CitationResolverError
from app.services.verification_service import _verify_evidence
from app.researchguard.adapters.sciverify import accepted_source_to_domain, standalone_claim_to_domain
from app.researchguard.adapters.paperqa2 import PaperQA2Config, PaperQA2EvidenceRetriever
from app.tests.test_paperqa2_integration import LocalEmbedding, LocalSummary, injected_factory
from app.tests.test_agents import MockLLMProvider
from app.utils.claim_preprocessor import preprocess_claim

DOI = "10.1234/recovery"
TITLE = "Deterministic treatment reduces patient risk in a controlled trial"
CITATION = CitationMetadata(doi=DOI, title=TITLE, authors=["Ada Lovelace"], year=2020,
                            source="crossref", type="journal-article")


def pdf_bytes(lines=None, metadata=None):
    """Real local PDF generated with pypdf, including extractable fixture text."""
    lines = lines if lines is not None else [TITLE, "Ada Lovelace 2020", "doi: " + DOI,
                                          "Results", "Treatment reduces risk by 12% in patients."]
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
        DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    escaped = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    stream.set_data(("BT /F1 11 Tf 40 740 Td 16 TL " + " ".join("(" + line + ") Tj T*" for line in escaped) + " ET").encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    if metadata:
        writer.add_metadata(metadata)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def artifact(content=b"<article><p>Treatment reduces risk by 12%.</p></article>", doi=DOI):
    return AcceptedSourceArtifact.create(doi=doi, content=content, format="html",
        source_url="https://accepted.example/source", provider="fixture", origin="remote",
        paper=PaperMetadata(paper_id=doi, doi=doi, title=TITLE,
                            full_text_available=True, full_text_format="html"))


@pytest.fixture
def canonical(monkeypatch):
    resolver = Mock(return_value=CITATION)
    monkeypatch.setattr("app.services.manual_source.resolve_doi", resolver)
    return resolver


def offline_auto(monkeypatch, available=True):
    metadata = Mock(return_value=CITATION)
    monkeypatch.setattr(retrieval, "resolve_doi", metadata)
    work = {"open_access": {"is_oa": available}, "best_oa_location":
            {"oa_url": "https://accepted.example/source.html"} if available else None}
    provider = Mock(return_value=work)
    monkeypatch.setattr(retrieval, "_fetch_openalex_work", provider)
    discoveries = []
    for name in ("_discover_europe_pmc_candidates", "_discover_unpaywall_candidates", "_discover_semantic_scholar_candidates"):
        fn = Mock(return_value=[])
        discoveries.append(fn)
        monkeypatch.setattr(retrieval, name, fn)
    return metadata, provider, discoveries


def test_automatic_raw_bytes_persist_and_cached_retrieval_bypasses_all_network(monkeypatch, caplog):
    caplog.set_level("INFO")
    metadata, provider, discoveries = offline_auto(monkeypatch)
    content = b"<article><p>Treatment reduces risk by 12%.</p></article>"
    download = Mock(return_value=RetrievedDocument(content, content.decode(), "html", "text/html", "https://accepted.example/source.html"))
    monkeypatch.setattr(retrieval, "retrieve_document", download)
    first = retrieval.retrieve_paper("https://doi.org/" + DOI.upper())
    digest = hashlib.sha256(content).hexdigest()
    assert first.source.raw_content_sha256 == digest and not first.source.cache_hit
    stored = LocalSourceStore().get(DOI)
    assert stored.content == content and stored.raw_content_sha256 == digest
    source, chunks = accepted_source_to_domain(first)
    assert source.content_hash == "sha256:" + digest
    assert chunks[0].metadata["parsed_content_fingerprint"] != digest
    assert chunks[0].metadata["content_hash_kind"] == "raw_bytes"
    for fn in (metadata, provider, download, *discoveries):
        fn.reset_mock()
        fn.side_effect = AssertionError("Cache hit must not reach providers")
    cached = retrieval.retrieve_paper(DOI)
    assert cached.source.cache_hit and cached.chunks == first.chunks
    assert "source_cache_hit" in caplog.text and "source_cache_miss" in caplog.text
    for fn in (metadata, provider, download, *discoveries):
        fn.assert_not_called()


def test_store_survives_recreation_and_same_bytes_support_multiple_dois(tmp_path):
    first = artifact()
    LocalSourceStore(tmp_path).put(first)
    assert LocalSourceStore(tmp_path).get(DOI) == first
    second = artifact(doi="10.1234/alias")
    LocalSourceStore(tmp_path).put(second)
    assert LocalSourceStore(tmp_path).get(DOI) == first
    assert LocalSourceStore(tmp_path).get(second.doi) == second
    assert len([p for p in tmp_path.iterdir() if p.name != "doi"]) == 1


@pytest.mark.parametrize("corrupt", ["raw", "missing_raw", "metadata", "pointer", "traversal", "wrong_doi", "missing_metadata"])
def test_corrupt_cache_is_a_safe_miss(tmp_path, corrupt):
    store = LocalSourceStore(tmp_path)
    item = artifact()
    store.put(item)
    raw = tmp_path / item.raw_content_sha256 / "source.html"
    pointer = store._lookup_path(DOI)
    metadata = raw.parent / pointer.name
    if corrupt == "raw":
        raw.write_bytes(b"tampered")
    elif corrupt == "missing_raw":
        raw.unlink()
    elif corrupt == "metadata":
        metadata.write_text("{broken")
    elif corrupt == "missing_metadata":
        metadata.unlink()
    elif corrupt == "pointer":
        pointer.write_text("[]")
    elif corrupt == "traversal":
        pointer.write_text(json.dumps({"raw_content_sha256": "../../escape"}))
    else:
        data = json.loads(metadata.read_text())
        data["paper"]["doi"] = "10.1234/wrong"
        metadata.write_text(json.dumps(data))
    assert LocalSourceStore(tmp_path).get(DOI) is None


def test_corrupt_cache_falls_back_to_existing_automatic_retrieval(monkeypatch):
    store = LocalSourceStore()
    store.put(artifact())
    (store.root / artifact().raw_content_sha256 / "source.html").unlink()
    metadata, provider, _ = offline_auto(monkeypatch, available=False)
    result = retrieval.retrieve_paper(DOI)
    assert result.status.value == "full_text_unavailable"
    metadata.assert_called_once()
    provider.assert_called_once()


def test_valid_upload_real_pdf_hash_provenance_and_safe_filename(canonical, caplog):
    caplog.set_level("INFO")
    content = pdf_bytes()
    response = TestClient(app).post("/api/sources/manual", data={"doi": DOI},
                                   files={"file": ("../../outside.pdf", content, "application/pdf")})
    assert response.status_code == 200
    assert response.json()["identity_match"] == "doi"
    stored = LocalSourceStore().get(DOI)
    assert stored.content == content and stored.origin == "manual" and stored.source_url is None
    assert stored.raw_content_sha256 == hashlib.sha256(content).hexdigest()
    assert set(p.name for p in LocalSourceStore().root.iterdir()) == {"doi", stored.raw_content_sha256}
    result = retrieval.retrieve_paper(DOI)
    source, chunks = accepted_source_to_domain(result)
    assert source.source_type.value == "manual" and result.source.cache_hit
    assert chunks[0].metadata["source_cache_hit"] is True
    assert "manual_source_accepted" in caplog.text and TITLE not in caplog.text
    assert "outside" not in json.dumps(response.json())
    assert "content" not in response.json() and "path" not in response.json()


@pytest.mark.parametrize("lines,metadata", [
    (["Completely different article", "10.1234/wrong", "Results", "Other finding."], None),
    (["Other paper", "References", DOI, "Results", "Other finding."], None),
    ([TITLE, "Ada Lovelace 2020", "10.1234/wrong", "Results", "Other finding."], None),
    ([TITLE, "Ada Lovelace 2020", DOI, "10.1234/wrong"], None),
    (["Generic text without identity", "Results", "Other finding."], None),
])
def test_wrong_or_ambiguous_pdf_is_rejected_and_does_not_replace_cache(canonical, lines, metadata):
    original = artifact()
    LocalSourceStore().put(original)
    response = TestClient(app).post("/api/sources/manual", data={"doi": DOI},
                                   files={"file": ("wrong.pdf", pdf_bytes(lines, metadata), "application/pdf")})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "SOURCE_MISMATCH"
    assert LocalSourceStore().get(DOI) == original


@pytest.mark.parametrize("header,metadata,expected", [
    ("Other text", {"/DOI": DOI}, "doi"),
    (TITLE + "\nAda Lovelace 2020", {}, "title_author_year"),
    (TITLE + "\n2020", {}, None),
    (TITLE + "\nAda Lovelace", {}, None),
    ("References\n" + TITLE + "\nAda Lovelace 2020", {}, None),
    ("x" * 4001 + DOI, {}, None),
    ("10.1234/recovery-extra", {}, None),
])
def test_deterministic_matching_policy(header, metadata, expected):
    assert match_pdf_identity(DOI, CITATION, header, metadata) == expected


def test_title_fallback_accepts_real_pdf(canonical):
    result = accept_manual_pdf(DOI, pdf_bytes([TITLE, "Ada Lovelace 2020", "Results", "Treatment reduces risk."]))
    assert result["identity_match"] == "title_author_year"


@pytest.mark.parametrize("content", [b"", b"not a PDF", b"%PDF-1.7 broken"])
def test_invalid_upload_returns_safe_error_without_resolving(canonical, content):
    response = TestClient(app).post("/api/sources/manual", data={"doi": DOI},
                                   files={"file": ("source.pdf", content, "application/pdf")})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_PDF"
    canonical.assert_not_called()


def test_oversized_upload_and_invalid_doi(canonical, monkeypatch):
    monkeypatch.setenv("RESEARCHGUARD_SOURCE_MAX_SIZE", "16")
    response = TestClient(app).post("/api/sources/manual", data={"doi": DOI}, files={"file": ("source.pdf", pdf_bytes())})
    assert response.status_code == 413 and response.json()["detail"]["code"] == "FILE_TOO_LARGE"
    response = TestClient(app).post("/api/sources/manual", data={"doi": "bad"}, files={"file": ("x.pdf", b"%PDF-")})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_DOI"
    canonical.assert_not_called()


@pytest.mark.parametrize("failure", ["metadata", "store"])
def test_upload_failures_are_safe_and_retryable(canonical, monkeypatch, failure):
    if failure == "metadata":
        canonical.side_effect = CitationResolverError("secret provider body")
    else:
        monkeypatch.setattr(LocalSourceStore, "put", Mock(side_effect=OSError("secret local path")))
    response = TestClient(app).post("/api/sources/manual", data={"doi": DOI}, files={"file": ("x.pdf", pdf_bytes())})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == ("METADATA_UNAVAILABLE" if failure == "metadata" else "SOURCE_STORE_FAILED")
    assert "secret" not in response.text


@pytest.mark.parametrize("status", ["full_text_unavailable", "metadata_only", "parsing_failure", "no_chunks", "no_relevant_evidence"])
def test_source_recovery_is_distinct_from_available_but_insufficient(status):
    evidence = EvidenceRetrievalResponse(status=EvidenceRetrievalStatus(status), claim="Treatment reduces risk.",
        paper=EvidencePaperSummary(paper_id=DOI, doi=DOI), evidence=[])
    result = _verify_evidence(evidence.claim, evidence)
    if status in {"no_chunks", "no_relevant_evidence"}:
        assert result.status.value == "insufficient_evidence" and result.verdict.value == "INSUFFICIENT"
    else:
        assert result.status.value == "source_required" and result.verdict is None and result.confidence is None
        assert result.adjudicator is None and result.claim_traceability is None
        assert result.source_recovery.reason == status


def domain_source():
    accept_manual_pdf(DOI, pdf_bytes())
    result = retrieval.retrieve_paper(DOI)
    return accepted_source_to_domain(result)


@pytest.mark.anyio
async def test_real_index_reuses_embeddings_but_queries_have_fresh_summaries(canonical, monkeypatch):
    source, chunks = domain_source()
    embedding, summary = LocalEmbedding(), LocalSummary()
    config = PaperQA2Config(model="fixture-summary", embedding_model="fixture-embedding", candidate_k=2)
    adds = []
    original = Docs.aadd_texts
    async def add(self, *args, **kwargs):
        adds.append(1)
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(Docs, "aadd_texts", add)
    results = []
    for text in ("Treatment reduces risk.", "Does treatment benefit patients?"):
        retriever = PaperQA2EvidenceRetriever(chunks, config, embedding_model=embedding, summary_model=summary)
        results.append(await retriever.retrieve(standalone_claim_to_domain(preprocess_claim(text), source), source, 1))
    assert len(adds) == 1 and len(embedding.calls) == 3  # one source batch, two queries
    assert len(summary.calls) == 2 * min(2, len(chunks))
    assert results[0][0].metadata["paperqa_context_id"] != results[1][0].metadata["paperqa_context_id"]


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["bytes", "parsed", "embedding_model", "embedding_api_base", "credential"])
async def test_index_identity_changes_invalidate_cache(canonical, change):
    source, chunks = domain_source()
    embedding, summary = LocalEmbedding(), LocalSummary()
    config = PaperQA2Config(model="fixture-summary", embedding_model="fixture-embedding", candidate_k=2)
    async def query(src, cs, cfg):
        return await PaperQA2EvidenceRetriever(cs, cfg, embedding_model=embedding, summary_model=summary).retrieve(
            standalone_claim_to_domain(preprocess_claim("Treatment reduces risk."), src), src, 1)
    await query(source, chunks, config)
    if change == "bytes":
        content = pdf_bytes() + b"\n% different accepted bytes"
        accept_manual_pdf(DOI, content)
        source, chunks = accepted_source_to_domain(retrieval.retrieve_paper(DOI))
    elif change == "parsed":
        chunks[0] = chunks[0].model_copy(update={"text": chunks[0].text + " Different parsing."})
    elif change == "embedding_model":
        config = replace(config, embedding_model="other-embedding")
    elif change == "embedding_api_base":
        config = replace(config, embedding_api_base="https://different.example")
    else:
        config = replace(config, embedding_api_key="different-account")
    await query(source, chunks, config)
    assert len(embedding.calls) == 4  # two source batches + two query embeddings


@pytest.mark.anyio
async def test_concurrent_same_source_is_indexed_once(canonical, monkeypatch):
    source, chunks = domain_source()
    embedding, summary = LocalEmbedding(), LocalSummary()
    config = PaperQA2Config(model="fixture-summary", embedding_model="fixture-embedding")
    calls = []
    original = Docs.aadd_texts
    async def delayed(self, *args, **kwargs):
        calls.append(1)
        await asyncio.sleep(0.01)
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(Docs, "aadd_texts", delayed)
    async def query(text):
        return await PaperQA2EvidenceRetriever(chunks, config, embedding_model=embedding, summary_model=summary).retrieve(
            standalone_claim_to_domain(preprocess_claim(text), source), source, 1)
    first, second = await asyncio.gather(query("Treatment reduces risk."), query("Treatment benefits patients."))
    assert len(calls) == 1 and first and second and len(embedding.calls) == 3


def test_local_end_to_end_manual_recovery_with_real_paperqa_and_existing_verifier(canonical, monkeypatch):
    metadata, provider, discoveries = offline_auto(monkeypatch, available=False)
    monkeypatch.setenv("RESEARCHGUARD_EVIDENCE_ENGINE", "paperqa2")
    monkeypatch.setenv("PAPERQA2_MODEL", "fixture-summary")
    monkeypatch.setenv("PAPERQA2_EMBEDDING_MODEL", "fixture-embedding")
    monkeypatch.setenv("PAPERQA2_EVIDENCE_CANDIDATES", "2")
    monkeypatch.setenv("RESEARCHGUARD_EVIDENCE_TOP_K", "1")
    embedding, summary = LocalEmbedding(), LocalSummary()
    injected_factory(monkeypatch, embedding=embedding, summary=summary)
    request = {"claim": "Treatment reduces risk.", "doi": DOI}
    with TestClient(app) as client:
        missing = client.post("/api/verification/analyze", json=request)
        assert missing.status_code == 200 and missing.json()["status"] == "source_required"
        assert missing.json()["verdict"] is None
        upload = client.post("/api/sources/manual", data={"doi": DOI}, files={"file": ("fixture.pdf", pdf_bytes(), "application/pdf")})
        assert upload.status_code == 200
        source, chunks = accepted_source_to_domain(retrieval.retrieve_paper(DOI))
        evidence_id = next(c.id for c in chunks if c.section.lower() == "results")
        def verifier():
            return MockLLMProvider([
                ProsecutorAnalysis(analysis="Limited scope", stance="uncertain", confidence=0.3),
                DefenderAnalysis(analysis="Direct evidence", stance="support", supporting_evidence=[evidence_id], confidence=0.8),
                AdjudicatorAnalysis(analysis="Supported", verdict="SUPPORTS", confidence=0.8, reasoning="Source reports lower risk.", supporting_evidence=[evidence_id]),
            ])
        monkeypatch.setattr("app.services.verification_service.get_llm_provider", verifier)
        for fn in (metadata, provider, *discoveries):
            fn.reset_mock()
            fn.side_effect = AssertionError("Recovered source must be cache-first")
        recovered = client.post("/api/verification/analyze", json=request)
        assert recovered.status_code == 200
        assert recovered.json()["status"] == "success" and recovered.json()["verdict"] == "SUPPORTS"
        assert recovered.json()["evidence"][0]["chunk_id"] == evidence_id
        repeated = client.post("/api/verification/analyze", json={**request, "claim": "Treatment benefits patients."})
        assert repeated.status_code == 200 and repeated.json()["status"] == "success"
        assert len(embedding.calls) == 3  # exactly one source embedding, two fresh queries
        for fn in (metadata, provider, *discoveries):
            fn.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("limit", ["0", "1"])
async def test_index_cache_disable_and_lru_eviction(canonical, monkeypatch, limit):
    monkeypatch.setenv("RESEARCHGUARD_PAPERQA_CACHE_SIZE", limit)
    source, chunks = domain_source()
    embedding, summary = LocalEmbedding(), LocalSummary()
    config = PaperQA2Config(model="fixture-summary", embedding_model="fixture-embedding")
    async def query(cfg):
        return await PaperQA2EvidenceRetriever(chunks, cfg, embedding_model=embedding, summary_model=summary).retrieve(
            standalone_claim_to_domain(preprocess_claim("Treatment reduces risk."), source), source, 1)
    await query(config)
    await query(replace(config, embedding_model="other-model"))
    await query(config)
    assert len(embedding.calls) == 6  # each query embeds its evicted/uncached source again


@pytest.mark.anyio
async def test_production_style_model_construction_reuses_index_across_summary_changes(canonical, monkeypatch):
    from paperqa import Settings
    source, chunks = domain_source()
    embedding, summary = LocalEmbedding(), LocalSummary()
    monkeypatch.setattr(Settings, "get_embedding_model", lambda _: embedding)
    monkeypatch.setattr(Settings, "get_summary_llm", lambda _: summary)
    config = PaperQA2Config(model="fixture-summary", embedding_model="fixture-embedding")
    for cfg in (config, replace(config, model="different-summary")):
        await PaperQA2EvidenceRetriever(chunks, cfg).retrieve(
            standalone_claim_to_domain(preprocess_claim("Treatment reduces risk."), source), source, 1)
    assert len(embedding.calls) == 3
    assert len(summary.calls) == 2 * len(chunks)


@pytest.mark.anyio
async def test_failed_index_build_is_not_cached_and_next_attempt_recovers(canonical, monkeypatch):
    from app.researchguard.adapters.paperqa2 import PaperQA2RetrievalError
    source, chunks = domain_source()
    embedding, summary = LocalEmbedding(), LocalSummary()
    original = Docs.aadd_texts
    attempts = []
    async def flaky(self, *args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("secret provider content")
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(Docs, "aadd_texts", flaky)
    config = PaperQA2Config(model="fixture-summary", embedding_model="fixture-embedding")
    async def query():
        return await PaperQA2EvidenceRetriever(chunks, config, embedding_model=embedding, summary_model=summary).retrieve(
            standalone_claim_to_domain(preprocess_claim("Treatment reduces risk."), source), source, 1)
    with pytest.raises(PaperQA2RetrievalError, match="retrieval_failed"):
        await query()
    assert await query()
    assert len(attempts) == 2


def test_doi_in_first_page_body_is_not_source_identity():
    assert match_pdf_identity(DOI, CITATION, "Unrelated paper\nAbstract\nEarlier work " + DOI, {}) is None


def test_source_recovery_response_schema_rejects_scientific_verdict():
    from pydantic import ValidationError
    from app.schemas.verification import VerificationResponse, SourceRecovery
    with pytest.raises(ValidationError, match="semantic assessment"):
        VerificationResponse(status="source_required", claim="Treatment reduces risk.",
            paper=EvidencePaperSummary(paper_id=DOI, doi=DOI), verdict="INSUFFICIENT",
            source_recovery=SourceRecovery(reason="full_text_unavailable", max_size_bytes=1024))


@pytest.mark.parametrize("failure", ["invalid_json", "invalid_schema", "provider_error", "rate_limit"])
def test_verifier_error_logs_do_not_contain_source_or_secrets(failure, caplog, monkeypatch):
    import httpx
    from app.services.llm.provider import OpenAICompatibleLLMProvider, LLMProviderError, get_llm_provider
    caplog.set_level("INFO")
    secret = "SECRET_PDF_TEXT_AND_PROVIDER_BODY"
    key = "sk-secret-key-tail-9876"
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_API_KEY", key)
    get_llm_provider()
    if failure == "invalid_json":
        content = secret
    else:
        content = json.dumps({"analysis": secret, "confidence": secret})
    response = httpx.Response(503 if failure == "provider_error" else 429 if failure == "rate_limit" else 200,
        json={"choices": [{"message": {"content": content}}], "error": {"message": secret}})
    client = Mock(spec=httpx.Client)
    client.post.return_value = response
    provider = OpenAICompatibleLLMProvider(api_key=key, model="fixture", base_url="https://example.test/v1",
        client=client, max_rate_limit_retries=0)
    with pytest.raises(LLMProviderError):
        provider.generate(secret, response_model=ProsecutorAnalysis)
    assert secret not in caplog.text and key not in caplog.text
    assert "9876" not in caplog.text and "sk-s" not in caplog.text
