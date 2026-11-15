"""M4 offline identity counterexamples and whole-paper contract checks."""
import pytest

from app.researchguard.domain import (
    AtomicClaim, AttributionStatus, CitationCallout, CitationContext,
    ClaimExtractionMetadata, ClaimExtractionResult, ContextExtractionResult,
    Manuscript, Paragraph, ParsedManuscript, Reference, TextSpan,
)
from app.researchguard.adapters.sciverify import accepted_source_to_domain
from app.researchguard.adapters.paperqa2 import PaperQA2EvidenceRetriever, PaperQA2RetrievalError
from app.schemas.verification import VerificationResponse, VerificationStatus, Verdict as LegacyVerdict
from app.services.citation_context import fingerprint
from app.tests.test_paperqa2_integration import LocalEmbedding, LocalSummary, paper, config
from app.services.manuscript_verification import verify_manuscript_core
from app.researchguard.manuscript_verification import ManuscriptCoreResult
from app.schemas.paper import PaperRetrievalStatus


def inputs(links=(("r1",),), dois=None):
    dois = dois or {r: "10.1234/local" for row in links for r in row}
    paragraphs, calls, contexts, claims, results = [], [], [], [], []
    for i, refs in enumerate(links):
        text = "Treatment reduces risk [1]."
        pid, cid, xid, qid = f"p{i}", f"call{i}", f"ctx{i}", f"claim{i}"
        paragraphs.append(Paragraph(id=pid, manuscript_id="m", text=text, order=i))
        calls.append(CitationCallout(id=cid, manuscript_id="m", paragraph_id=pid,
            text="[1]", span=TextSpan(start=23, end=26), order=i, reference_ids=refs))
        contexts.append(CitationContext(id=xid, manuscript_id="m", paragraph_id=pid,
            text=text, span=TextSpan(start=0, end=len(text)),
            focal_span=TextSpan(start=0, end=len(text)), scope_kind="paragraph_fallback",
            citation_callout_ids=(cid,)))
        claims.append(AtomicClaim(id=qid, manuscript_id="m", text="Treatment reduces risk",
            paragraph_id=pid, context_id=xid, citation_callout_ids=(cid,), reference_ids=refs,
            source_spans=(TextSpan(start=0, end=22),), attribution_status="resolved"))
        results.append(ContextExtractionResult(context_id=xid, status="completed", accepted_claim_ids=(qid,)))
    parsed = ParsedManuscript(manuscript=Manuscript(id="m", content_locator="memory://m"),
        paragraphs=tuple(paragraphs), citation_callouts=tuple(calls),
        references=tuple(Reference(id=r, manuscript_id="m", raw_text=r, doi=d) for r, d in dois.items()))
    extraction = ClaimExtractionResult(manuscript_id="m", status="completed", contexts=tuple(contexts),
        claims=tuple(claims), context_results=tuple(results), metadata=ClaimExtractionMetadata(
        prompt_version="fixture", context_policy_version="fixture", attribution_policy_version="fixture",
        input_fingerprint="sha256:" + fingerprint(parsed)))
    return parsed, extraction


async def verifier(claim, response):
    return VerificationResponse(status="success" if response.evidence else "insufficient_evidence",
        claim=claim, paper=response.paper, evidence=response.evidence,
        verdict="SUPPORTS" if response.evidence else "INSUFFICIENT", confidence=0.8)


@pytest.mark.anyio
async def test_original_claim_fails_canonical_guard(paper, config):
    _, extraction = inputs()
    source, chunks = accepted_source_to_domain(paper)
    retriever = PaperQA2EvidenceRetriever(chunks, config, embedding_model=LocalEmbedding(), summary_model=LocalSummary())
    with pytest.raises(PaperQA2RetrievalError, match="reference_mismatch"):
        await retriever.retrieve(extraction.claims[0], source, 1)


@pytest.mark.anyio
async def test_rebinding_source_breaks_existing_index_cache(paper, config, monkeypatch):
    from paperqa import Docs
    source, chunks = accepted_source_to_domain(paper)
    embedding, summary = LocalEmbedding(), LocalSummary()
    count = []
    add = Docs.aadd_texts
    async def counted(self, *args, **kwargs):
        count.append(1)
        return await add(self, *args, **kwargs)
    monkeypatch.setattr(Docs, "aadd_texts", counted)
    _, extraction = inputs((("r1",), ("r2",)))
    for claim in extraction.claims:
        rebound = source.model_copy(update={"reference_id": claim.reference_ids[0]})
        await PaperQA2EvidenceRetriever(chunks, config, embedding_model=embedding,
            summary_model=summary).retrieve(claim, rebound, 1)
    assert len(count) == 2


class FakeRetriever:
    def __init__(self, chunks, queries, mode="ok"):
        self.chunks, self.queries, self.mode = chunks, queries, mode

    async def retrieve(self, claim, source, top_k):
        assert source.reference_id in claim.reference_ids
        assert claim.id.startswith("m4-query:")
        self.queries.append((claim, source))
        if self.mode == "raise":
            raise PaperQA2RetrievalError("paperqa2_retrieval_failed")
        if self.mode == "empty":
            return []
        chunk = self.chunks[0].model_copy(update={"retrieval_score": 8.0})
        if self.mode == "foreign":
            chunk = chunk.model_copy(update={"source_document_id": "foreign"})
        if self.mode == "text":
            chunk = chunk.model_copy(update={"text": "invented"})
        if self.mode == "metadata":
            chunk = chunk.model_copy(update={"metadata": {}})
        if self.mode == "duplicate":
            return [chunk, chunk]
        if self.mode == "score":
            chunk = chunk.model_copy(update={"retrieval_score": 99})
        return [chunk]


async def run(parsed, extraction, paper, *, mode="ok", verify=verifier, retrieve=None):
    sources, queries, verifications = [], [], []
    def source(doi):
        sources.append(doi)
        return retrieve(doi) if retrieve else paper
    async def checked_verify(claim, response):
        verifications.append(response)
        return await verify(claim, response)
    result = await verify_manuscript_core(parsed, extraction, source_retriever=source,
        evidence_retriever_factory=lambda chunks: FakeRetriever(chunks, queries, mode),
        prepared_verifier=checked_verify)
    return result, sources, queries, verifications


@pytest.mark.anyio
async def test_single_pair_identity_and_serialization(paper):
    parsed, extraction = inputs()
    before = (parsed.model_dump_json(), extraction.model_dump_json())
    result, sources, queries, verified = await run(parsed, extraction, paper)
    pair = result.pairs[0]
    canonical, chunks = accepted_source_to_domain(paper)
    assert result.parsed == parsed and result.extraction == extraction
    assert before == (parsed.model_dump_json(), extraction.model_dump_json())
    assert pair.claim_id == "claim0" and pair.reference_id == "r1"
    assert pair.citation_callout_ids == ("call0",)
    assert pair.binding.reference_id == "r1" and pair.binding.source_document_id == canonical.id
    assert pair.binding.source_version == canonical.content_hash
    assert result.sources == (canonical,)
    assert pair.verification.evidence_chunks[0].id == chunks[0].id
    assert pair.verification.evidence_chunks[0].text == chunks[0].text
    assert verified[0].claim == extraction.claims[0].text
    assert queries[0][0].id != pair.claim_id
    assert pair.verification.verdict == "SUPPORTED"
    assert ManuscriptCoreResult.model_validate_json(result.model_dump_json()) == result
    assert result.coverage.coverage_complete


@pytest.mark.anyio
@pytest.mark.parametrize("links", [(("r1",), ("r1",)), (("r1", "r2"),), (("r1",), ("r2",))])
async def test_same_doi_prepared_once_independent_pairs(paper, links):
    parsed, extraction = inputs(links)
    result, sources, queries, verified = await run(parsed, extraction, paper)
    expected = [(claim.id, rid) for claim in extraction.claims for rid in claim.reference_ids]
    assert [(p.claim_id, p.reference_id) for p in result.pairs] == expected
    assert sources == ["10.1234/local"]
    assert len(queries) == len(verified) == len(expected) == 2
    assert len(result.sources) == 1 and result.coverage.completed == 2
    assert not hasattr(result, "verdict")


@pytest.mark.anyio
async def test_real_index_reused_across_manuscript_references(paper, config, monkeypatch):
    from paperqa import Docs
    embedding, summary, builds, queries, sources = LocalEmbedding(), LocalSummary(), [], [], []
    add, query = Docs.aadd_texts, Docs.aget_evidence
    async def counted_add(self, *args, **kwargs):
        builds.append(1)
        return await add(self, *args, **kwargs)
    async def counted_query(self, *args, **kwargs):
        queries.append(1)
        return await query(self, *args, **kwargs)
    async def forbidden(*args, **kwargs):
        pytest.fail("Discovery/download/final answer must never run")
    monkeypatch.setattr(Docs, "aadd_texts", counted_add)
    monkeypatch.setattr(Docs, "aget_evidence", counted_query)
    for method in ("aadd", "aadd_file", "aadd_url", "aquery"):
        monkeypatch.setattr(Docs, method, forbidden)
    def source(doi):
        sources.append(doi)
        return paper
    parsed, extraction = inputs((("r1",), ("r2",)), {"r1": "DOI:10.1234/LOCAL", "r2": "https://doi.org/10.1234/local"})
    result = await verify_manuscript_core(parsed, extraction, source_retriever=source,
        evidence_retriever_factory=lambda chunks: PaperQA2EvidenceRetriever(chunks, config,
            embedding_model=embedding, summary_model=summary), prepared_verifier=verifier, top_k=1)
    assert len(builds) == 1 and len(queries) == 2 and len(sources) == 1
    assert result.coverage.completed == 2
    assert [p.reference_id for p in result.pairs] == ["r1", "r2"]
    assert {p.binding.source_document_id for p in result.pairs} == {result.sources[0].id}


@pytest.mark.anyio
@pytest.mark.parametrize("mutation", ["manuscript", "fingerprint", "reference", "span", "owner", "callout", "context", "attribution", "parsed_owner"])
async def test_invalid_combined_input_before_dependencies(paper, mutation):
    parsed, extraction = inputs()
    claim = extraction.claims[0]
    if mutation == "manuscript":
        extraction = extraction.model_copy(update={"manuscript_id": "foreign"})
    elif mutation == "fingerprint":
        extraction = extraction.model_copy(update={"metadata": extraction.metadata.model_copy(update={"input_fingerprint": "bad"})})
    elif mutation == "parsed_owner":
        parsed = parsed.model_copy(update={"references": (parsed.references[0].model_copy(update={"manuscript_id": "foreign"}),)})
    elif mutation == "context":
        extraction = extraction.model_copy(update={"contexts": (extraction.contexts[0].model_copy(update={"span": TextSpan(start=0, end=999)}),)})
    else:
        updates = {"reference": {"reference_ids": ("foreign",)},
            "span": {"source_spans": (TextSpan(start=0, end=999),)},
            "owner": {"manuscript_id": "foreign"},
            "callout": {"citation_callout_ids": ("foreign",)},
            "attribution": {"attribution_status": None}}[mutation]
        extraction = extraction.model_copy(update={"claims": (claim.model_copy(update=updates),)})
    def forbidden(*args):
        pytest.fail("Invalid input reached a dependency")
    with pytest.raises(ValueError):
        await verify_manuscript_core(parsed, extraction, source_retriever=forbidden,
            evidence_retriever_factory=forbidden, prepared_verifier=forbidden)


@pytest.mark.anyio
@pytest.mark.parametrize("status", list(PaperRetrievalStatus)[1:] + ["exception", "mismatch", "empty"])
async def test_source_failure_partial_continue(paper, status):
    parsed, extraction = inputs((("r1",), ("r2",), ("r3",)),
        {"r1": "10.1234/local", "r2": "10.1234/bad", "r3": "10.1234/local"})
    def source(doi):
        if doi == "10.1234/local":
            return paper
        if status == "exception":
            raise RuntimeError("secret")
        if status == "mismatch":
            return paper
        response = paper.model_copy(deep=True)
        response.paper.doi = doi
        if status == "empty":
            response.chunks = []
        else:
            response.status = PaperRetrievalStatus(status)
        return response
    result, sources, queries, verified = await run(parsed, extraction, paper, retrieve=source)
    assert [p.processing_status for p in result.pairs][::2] == ["completed", "completed"]
    assert result.pairs[1].verification.verdict is None and result.pairs[1].legacy_verdict is None
    assert result.coverage.completed == 2 and result.coverage.pairs == 3
    assert len(verified) == len(queries) == 2
    assert not result.coverage.coverage_complete


@pytest.mark.anyio
@pytest.mark.parametrize("doi,reason", [(None, "DOI_MISSING"), ("bad", "DOI_INVALID")])
async def test_missing_or_invalid_doi_blocks_only_pair(paper, doi, reason):
    parsed, extraction = inputs((("r1",), ("r2",)), {"r1": doi, "r2": "10.1234/local"})
    result, sources, _, verified = await run(parsed, extraction, paper)
    assert result.pairs[0].reason_code == reason and result.pairs[0].verification.verdict is None
    assert result.coverage.completed == 1 and len(sources) == len(verified) == 1


@pytest.mark.anyio
async def test_attribution_blocked_with_partial_links_preserved(paper):
    parsed, extraction = inputs((("r1",), ("r1",), ("r1",)))
    claims = list(extraction.claims)
    claims[0] = claims[0].model_copy(update={"attribution_status": AttributionStatus.AMBIGUOUS,
        "citation_callout_ids": (), "reference_ids": ()})
    claims[1] = claims[1].model_copy(update={"attribution_status": AttributionStatus.UNRESOLVED})
    extraction = extraction.model_copy(update={"claims": tuple(claims)})
    result, sources, queries, _ = await run(parsed, extraction, paper)
    assert [b.reason_code for b in result.attribution_blocked] == ["ATTRIBUTION_AMBIGUOUS", "ATTRIBUTION_UNRESOLVED"]
    assert result.extraction.claims[1].reference_ids == ("r1",)
    assert len(result.pairs) == len(queries) == len(sources) == 1
    assert result.pairs[0].claim_id == "claim2"
    assert result.coverage.unresolved_claims == result.coverage.ambiguous_claims == 1


@pytest.mark.anyio
async def test_no_relevant_evidence_after_successful_source(paper):
    result, sources, queries, verified = await run(*inputs(), paper, mode="empty")
    assert len(sources) == len(queries) == len(verified) == 1
    assert result.pairs[0].reason_code == "NO_RELEVANT_EVIDENCE"
    assert result.pairs[0].verification.verdict == "INSUFFICIENT"
    assert result.coverage.completed == 1


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["raise", "foreign", "text", "metadata", "duplicate", "score"])
async def test_invalid_evidence_never_enters_verifier(paper, mode):
    result, _, _, verified = await run(*inputs(), paper, mode=mode)
    assert not verified and result.pairs[0].verification.verdict is None
    assert result.coverage.failed + result.coverage.blocked == 1


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["exception", "llm_unavailable", "verification_failed", "foreign_claim", "foreign_evidence"])
async def test_verifier_failure_isolated(paper, mode):
    count = []
    async def failing(claim, response):
        count.append(1)
        if len(count) > 1:
            return await verifier(claim, response)
        if mode == "exception":
            raise RuntimeError("secret")
        value = await verifier(claim, response)
        if mode in {"llm_unavailable", "verification_failed"}:
            return value.model_copy(update={"status": VerificationStatus(mode), "verdict": None, "confidence": None})
        if mode == "foreign_claim":
            return value.model_copy(update={"claim": "foreign"})
        return value.model_copy(update={"evidence": []})
    result, _, _, _ = await run(*inputs((("r1",), ("r1",))), paper, verify=failing)
    assert result.coverage.failed == result.coverage.completed == 1
    assert result.pairs[0].verification.verdict is None


@pytest.mark.anyio
@pytest.mark.parametrize("legacy,domain", [("SUPPORTS", "SUPPORTED"), ("OVERSTATED", "OVERSTATED"),
    ("CONTRADICTS", "CONTRADICTED"), ("INSUFFICIENT", "INSUFFICIENT"), ("FABRICATED", "INSUFFICIENT")])
async def test_legacy_verdict_mapping_preserves_provenance(paper, legacy, domain):
    async def mapped(claim, response):
        value = await verifier(claim, response)
        return value.model_copy(update={"verdict": LegacyVerdict(legacy)})
    result, _, _, _ = await run(*inputs(), paper, verify=mapped)
    pair = result.pairs[0]
    assert pair.verification.verdict == domain and pair.legacy_verdict == legacy
    assert pair.verification.traceability.metadata["legacy_provenance"]["verdict"] == legacy


@pytest.mark.anyio
async def test_different_pair_verdicts_never_aggregated(paper):
    verdicts = iter(["SUPPORTS", "CONTRADICTS"])
    async def mapped(claim, response):
        value = await verifier(claim, response)
        return value.model_copy(update={"verdict": LegacyVerdict(next(verdicts))})
    result, _, _, _ = await run(*inputs((("r1", "r2"),)), paper, verify=mapped)
    assert [p.verification.verdict for p in result.pairs] == ["SUPPORTED", "CONTRADICTED"]
    assert result.coverage.claims == 1 and result.coverage.references == result.coverage.pairs == 2


@pytest.mark.anyio
async def test_zero_claims_never_means_all_verified(paper):
    result, sources, queries, verified = await run(*inputs(()), paper)
    assert not result.coverage.coverage_complete and result.coverage.claims == result.coverage.pairs == 0
    assert not sources and not queries and not verified


@pytest.mark.anyio
async def test_failure_memo_expires_between_invocations(paper):
    parsed, extraction = inputs((("r1",), ("r1",)))
    calls = []
    def source(doi):
        calls.append(doi)
        raise RuntimeError("temporary")
    for _ in range(2):
        result, _, _, _ = await run(parsed, extraction, paper, retrieve=source)
        assert result.coverage.failed == 2
    assert len(calls) == 2


@pytest.mark.anyio
async def test_prepared_public_entry_reuses_real_agents_off_loop(paper, monkeypatch):
    import threading
    from app.services import verification_service as service
    from app.tests.test_agents import MockLLMProvider
    main_thread = threading.get_ident()
    calls = []
    original = service._verify_evidence
    def counted(*args, **kwargs):
        calls.append(threading.get_ident())
        return original(*args, **kwargs)
    monkeypatch.setattr(service, "_verify_evidence", counted)
    def forbidden(*args):
        pytest.fail("Prepared verifier must not retrieve source again")
    monkeypatch.setattr(service, "retrieve_evidence_for_claim", forbidden)
    async def real(claim, response):
        from app.schemas.verification import ProsecutorAnalysis, DefenderAnalysis, AdjudicatorAnalysis
        eid = response.evidence[0].chunk_id
        provider = MockLLMProvider([
            ProsecutorAnalysis(analysis="fixture", stance="skeptical", confidence=0.8, supporting_evidence=[eid]),
            DefenderAnalysis(analysis="fixture", stance="supportive", confidence=0.8, supporting_evidence=[eid]),
            AdjudicatorAnalysis(analysis="fixture", reasoning="fixture", verdict="SUPPORTS", confidence=0.8, supporting_evidence=[eid]),
        ])
        return await service.verify_prepared_evidence(claim, response, llm=provider)
    result, _, _, _ = await run(*inputs(), paper, verify=real)
    assert result.coverage.completed == 1
    assert calls and calls[0] != main_thread
    provenance = result.pairs[0].verification.traceability.metadata["legacy_provenance"]
    assert all(provenance[k] for k in ("prosecutor", "defender", "adjudicator", "claim_traceability"))


@pytest.mark.anyio
async def test_prepared_entry_rejects_source_failure_and_claim_mismatch(paper):
    from app.services.verification_service import verify_prepared_evidence
    from app.schemas.evidence import EvidenceRetrievalResponse, EvidencePaperSummary
    for status, claim in [("full_text_unavailable", "claim"), ("success", "claim"), ("no_relevant_evidence", "foreign")]:
        response = EvidenceRetrievalResponse(status=status, claim="claim",
            paper=EvidencePaperSummary(paper_id="p", doi="10.1234/local"))
        with pytest.raises(ValueError):
            await verify_prepared_evidence(claim, response)


@pytest.mark.anyio
@pytest.mark.parametrize("limit", ["claims", "pairs", "top_k"])
async def test_limits_checked_before_dependencies(limit):
    from app.services.manuscript_verification import MAX_CLAIMS, MAX_PAIRS
    if limit == "claims":
        parsed, extraction = inputs((("r1",),) * (MAX_CLAIMS + 1))
    elif limit == "pairs":
        parsed, extraction = inputs((tuple(f"r{i}" for i in range(MAX_PAIRS + 1)),))
    else:
        parsed, extraction = inputs()
    def forbidden(*args):
        pytest.fail("Over-limit input reached external dependency")
    with pytest.raises(ValueError):
        await verify_manuscript_core(parsed, extraction, source_retriever=forbidden,
            top_k=21 if limit == "top_k" else 5)


@pytest.mark.anyio
async def test_fingerprint_uses_m3b_projection_including_diagnostics(paper):
    from app.researchguard.domain import ManuscriptDiagnostic
    parsed, extraction = inputs()
    # M3B intentionally excludes the locator, but includes domain diagnostics.
    relocated = parsed.model_copy(update={"manuscript": parsed.manuscript.model_copy(update={"content_locator": "other://location"})})
    result, _, _, _ = await run(relocated, extraction, paper)
    assert result.coverage.completed == 1
    changed = parsed.model_copy(update={"diagnostics": (ManuscriptDiagnostic(
        code="CLIENT_DIAGNOSTIC", severity="warning", safe_message="fixture"),)})
    with pytest.raises(ValueError, match="fingerprint"):
        await run(changed, extraction, paper)


@pytest.mark.anyio
async def test_adapter_failure_partial_continue(paper, config):
    class FailingEmbedding(LocalEmbedding):
        async def embed_documents(self, texts):
            raise RuntimeError("fixture embedding failure")
    queries = []
    def factory(chunks):
        queries.append(1)
        if len(queries) == 1:
            return PaperQA2EvidenceRetriever(chunks, config,
                embedding_model=FailingEmbedding(), summary_model=LocalSummary())
        return FakeRetriever(chunks, [])
    result = await verify_manuscript_core(*inputs((("r1",), ("r1",))),
        source_retriever=lambda doi: paper, evidence_retriever_factory=factory, prepared_verifier=verifier)
    assert result.pairs[0].reason_code == "PAPERQA2_ADAPTER_FAILURE"
    assert result.pairs[0].verification.verdict is None
    assert result.coverage.failed == result.coverage.completed == 1


@pytest.mark.anyio
async def test_source_preparation_off_event_loop_and_unique_dois(paper):
    import threading
    main_thread, threads = threading.get_ident(), []
    def source(doi):
        threads.append(threading.get_ident())
        response = paper.model_copy(deep=True)
        response.paper.doi = response.paper.paper_id = doi
        for chunk in response.chunks:
            chunk.paper_id = doi
        return response
    parsed, extraction = inputs((("r1", "r2"),), {"r1": "10.1234/one", "r2": "10.1234/two"})
    result, sources, _, _ = await run(parsed, extraction, paper, retrieve=source)
    assert sources == ["10.1234/one", "10.1234/two"]
    assert all(t != main_thread for t in threads)
    assert len(result.sources) == result.coverage.completed == 2
    assert [p.binding.doi for p in result.pairs] == sources


@pytest.mark.anyio
async def test_pair_callouts_filtered_to_its_reference(paper):
    parsed, extraction = inputs((("r1", "r2"),))
    text = "Treatment reduces risk [1], [2]."
    paragraph = parsed.paragraphs[0].model_copy(update={"text": text})
    calls = (parsed.citation_callouts[0].model_copy(update={"reference_ids": ("r1",)}),
        CitationCallout(id="call1", manuscript_id="m", paragraph_id="p0", text="[2]",
            reference_ids=("r2",), span=TextSpan(start=28, end=31), order=1))
    parsed = parsed.model_copy(update={"paragraphs": (paragraph,), "citation_callouts": calls})
    context = extraction.contexts[0].model_copy(update={"text": text,
        "span": TextSpan(start=0, end=len(text)), "focal_span": TextSpan(start=0, end=len(text)),
        "citation_callout_ids": ("call0", "call1")})
    extraction = extraction.model_copy(update={"contexts": (context,),
        "claims": (extraction.claims[0].model_copy(update={"citation_callout_ids": ("call0", "call1")}),),
        "metadata": extraction.metadata.model_copy(update={"input_fingerprint": "sha256:" + fingerprint(parsed)})})
    result, _, _, _ = await run(parsed, extraction, paper)
    assert [p.citation_callout_ids for p in result.pairs] == [("call0",), ("call1",)]


@pytest.mark.anyio
async def test_empty_prepared_evidence_uses_existing_insufficient_contract_without_llm(paper, monkeypatch):
    from app.services import verification_service as service
    def forbidden():
        pytest.fail("Empty evidence must not initialize LLM provider")
    monkeypatch.setattr(service, "get_llm_provider", forbidden)
    result, _, _, _ = await run(*inputs(), paper, mode="empty", verify=service.verify_prepared_evidence)
    assert result.pairs[0].verification.verdict == "INSUFFICIENT"
    assert result.pairs[0].verification.confidence == 0


@pytest.mark.anyio
@pytest.mark.parametrize("boundary,reason", [("source", "SOURCE_METADATA_SIZE_LIMIT"),
    ("evidence", "EVIDENCE_SIZE_LIMIT"), ("verifier", "VERIFIER_SIZE_LIMIT")])
async def test_output_payload_limits_isolate_pair(paper, boundary, reason):
    from app.services.manuscript_verification import MAX_PAIR_PAYLOAD_BYTES
    oversized = "x" * (MAX_PAIR_PAYLOAD_BYTES + 1)
    if boundary == "source":
        paper.paper.title = oversized
    elif boundary == "evidence":
        paper.chunks[0].text = oversized
    async def response(claim, evidence):
        value = await verifier(claim, evidence)
        return value.model_copy(update={"summary": oversized}) if boundary == "verifier" else value
    result, _, _, verified = await run(*inputs(), paper, verify=response)
    assert result.pairs[0].reason_code == reason
    assert result.coverage.failed == 1 and result.pairs[0].verification.verdict is None
    if boundary != "verifier":
        assert not verified
