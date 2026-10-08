from __future__ import annotations

from app.schemas.evidence import (
    EvidenceItem,
    EvidencePaperSummary,
    EvidenceRetrievalResponse,
    EvidenceRetrievalStatus,
)
from app.schemas.paper import PaperRetrievalStatus, RetrievePaperResponse
from app.services.evidence_retriever import rank_evidence_for_claim
from app.services.paper_retriever import retrieve_paper
from app.utils.claim_preprocessor import ProcessedClaim, preprocess_claim
from app.utils.doi import normalize_doi


def retrieve_evidence_for_claim(
    claim: str,
    doi: str,
) -> EvidenceRetrievalResponse:
    """Retrieve ranked evidence for a claim and DOI using the Milestone 3/4 pipeline."""
    from app.config import EvidenceEngineConfigurationError, get_evidence_engine
    if get_evidence_engine() != "lexical":
        raise EvidenceEngineConfigurationError("PaperQA2 requires the async evidence entrypoint.")
    processed_claim = preprocess_claim(claim)
    normalize_doi(doi)
    paper_result = retrieve_paper(doi)
    return build_evidence_response(processed_claim, paper_result)


def build_evidence_response(
    processed_claim: ProcessedClaim,
    paper_result: RetrievePaperResponse,
) -> EvidenceRetrievalResponse:
    claim = processed_claim.original
    paper_summary = EvidencePaperSummary(
        paper_id=paper_result.paper.paper_id,
        doi=paper_result.paper.doi,
        title=paper_result.paper.title,
    )

    if paper_result.status == PaperRetrievalStatus.NOT_FOUND:
        return EvidenceRetrievalResponse(
            status=EvidenceRetrievalStatus.NOT_FOUND,
            claim=claim,
            paper=paper_summary,
            evidence=[],
            total_chunks_considered=0,
            detail="Paper not found.",
        )

    if paper_result.status == PaperRetrievalStatus.PROVIDER_ERROR:
        return EvidenceRetrievalResponse(
            status=EvidenceRetrievalStatus.PROVIDER_ERROR,
            claim=claim,
            paper=paper_summary,
            evidence=[],
            total_chunks_considered=0,
            detail=paper_result.detail or "External provider unavailable.",
        )

    if paper_result.status == PaperRetrievalStatus.METADATA_ONLY:
        return EvidenceRetrievalResponse(
            status=EvidenceRetrievalStatus.METADATA_ONLY,
            claim=claim,
            paper=paper_summary,
            evidence=[],
            total_chunks_considered=0,
            detail="Paper metadata retrieved, but evidence chunks are unavailable.",
        )

    if paper_result.status == PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE:
        return EvidenceRetrievalResponse(
            status=EvidenceRetrievalStatus.FULL_TEXT_UNAVAILABLE,
            claim=claim,
            paper=paper_summary,
            evidence=[],
            total_chunks_considered=0,
            detail="Full text is unavailable for evidence retrieval.",
        )

    if paper_result.status == PaperRetrievalStatus.PARSING_FAILURE:
        return EvidenceRetrievalResponse(
            status=EvidenceRetrievalStatus.PARSING_FAILURE,
            claim=claim,
            paper=paper_summary,
            evidence=[],
            total_chunks_considered=0,
            detail=paper_result.detail or "Document parsing failed.",
        )

    chunks = paper_result.chunks
    if not chunks:
        return EvidenceRetrievalResponse(
            status=EvidenceRetrievalStatus.NO_CHUNKS,
            claim=claim,
            paper=paper_summary,
            evidence=[],
            total_chunks_considered=0,
            detail="Paper retrieved but no evidence chunks were produced.",
        )

    ranked = rank_evidence_for_claim(processed_claim, chunks)

    if not ranked:
        return EvidenceRetrievalResponse(
            status=EvidenceRetrievalStatus.NO_RELEVANT_EVIDENCE,
            claim=claim,
            paper=paper_summary,
            evidence=[],
            total_chunks_considered=len(chunks),
            detail="No evidence chunks met the minimum relevance threshold.",
        )

    return EvidenceRetrievalResponse(
        status=EvidenceRetrievalStatus.SUCCESS,
        claim=claim,
        paper=paper_summary,
        evidence=ranked,
        total_chunks_considered=len(chunks),
    )



async def aretrieve_evidence_for_claim(claim: str, doi: str) -> EvidenceRetrievalResponse:
    """Async evidence application path; existing lexical implementation is intact."""
    from anyio import to_thread
    from app.config import EvidenceEngineConfigurationError, EVIDENCE_TOP_K, get_evidence_engine

    engine = get_evidence_engine()
    if engine == "lexical":
        return await to_thread.run_sync(retrieve_evidence_for_claim, claim, doi)

    # Parse only the already accepted source. Never give PaperQA a DOI to discover.
    from app.researchguard.adapters.paperqa2 import PaperQA2Config, PaperQA2EvidenceRetriever, PaperQA2RetrievalError
    from app.researchguard.adapters.sciverify import accepted_source_to_domain, evidence_to_legacy, standalone_claim_to_domain
    import os

    processed = preprocess_claim(claim)
    normalize_doi(doi)
    try:
        top_k = int(os.getenv("RESEARCHGUARD_EVIDENCE_TOP_K", str(EVIDENCE_TOP_K)))
        if top_k <= 0:
            raise ValueError("Nonpositive top_k")
    except ValueError as exc:
        raise EvidenceEngineConfigurationError("RESEARCHGUARD_EVIDENCE_TOP_K must be a positive integer.") from exc
    config = PaperQA2Config.from_environment()
    paper_result = await to_thread.run_sync(retrieve_paper, doi)
    if paper_result.status != PaperRetrievalStatus.SUCCESS or not paper_result.chunks:
        # Preserve retrieval-status semantics and never invoke lexical ranking.
        return build_evidence_response(processed, paper_result)
    try:
        source, source_chunks = accepted_source_to_domain(paper_result)
        atomic_claim = standalone_claim_to_domain(processed, source)
        retriever = PaperQA2EvidenceRetriever(source_chunks, config)
        chunks = await retriever.retrieve(atomic_claim, source, top_k)
        evidence = evidence_to_legacy(chunks, processed)
    except (ValueError, TypeError) as exc:
        raise PaperQA2RetrievalError("paperqa2_source_or_mapping_failed") from exc
    return EvidenceRetrievalResponse(
        status=EvidenceRetrievalStatus.SUCCESS if evidence else EvidenceRetrievalStatus.NO_RELEVANT_EVIDENCE,
        claim=processed.original,
        paper=EvidencePaperSummary(paper_id=paper_result.paper.paper_id, doi=paper_result.paper.doi, title=paper_result.paper.title),
        evidence=evidence, total_chunks_considered=len(source_chunks),
        detail=None if evidence else "PaperQA2 returned no relevant evidence from the accepted source.",
    )
