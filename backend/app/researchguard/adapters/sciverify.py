"""Legacy/domain conversion; verdict translation remains explicitly opt-in."""
from app.schemas.verification import Verdict as SciVerifyVerdict
from app.schemas.paper import RetrievePaperResponse
from app.schemas.evidence import EvidenceItem
from app.utils.claim_preprocessor import ProcessedClaim
from ..domain import AtomicClaim, EvidenceChunk, SourceDocument

from ..domain import ProcessingStatus, Verdict


_VERDICTS = {
    SciVerifyVerdict.SUPPORTS: Verdict.SUPPORTED,
    SciVerifyVerdict.OVERSTATED: Verdict.OVERSTATED,
    SciVerifyVerdict.CONTRADICTS: Verdict.CONTRADICTED,
    SciVerifyVerdict.INSUFFICIENT: Verdict.INSUFFICIENT,
    # Lack of support is not positive evidence of contradiction. Lossy mapping;
    # future application adapters should retain the raw verdict in trace metadata.
    SciVerifyVerdict.FABRICATED: Verdict.INSUFFICIENT,
}


def map_sciverify_verdict(
    verdict: SciVerifyVerdict | None, *, processing_status: ProcessingStatus
) -> Verdict | None:
    """Map only a completed semantic assessment.

    The caller must classify processing using retrieval diagnostics, not the
    legacy verdict alone. SciVerify insufficient_evidence combines unavailable
    sources and empty evidence; it cannot safely determine completion by itself.
    There is no legacy top-level equivalent of PARTIALLY_SUPPORTED.
    """
    status = ProcessingStatus(processing_status)
    if status != ProcessingStatus.COMPLETED:
        return None
    if verdict is None:
        raise ValueError("Completed assessment requires a SciVerify verdict")
    return _VERDICTS[SciVerifyVerdict(verdict)]


def accepted_source_to_domain(paper_result: RetrievePaperResponse) -> tuple[SourceDocument, list[EvidenceChunk]]:
    """Map all chunks from the exact accepted source, without retrieval/ranking.

    content_hash identifies raw artifact bytes when present. Legacy fixtures
    without an artifact retain an explicitly marked parsed-chunk fingerprint.
    """
    import hashlib
    import json

    from app.schemas.paper import PaperRetrievalStatus
    from ..domain import EvidenceChunk, RetrievalStatus, SourceDocument, SourceType

    if paper_result.status != PaperRetrievalStatus.SUCCESS or not paper_result.chunks:
        raise ValueError("Accepted source must contain parsed chunks")
    paper = paper_result.paper
    if any(c.paper_id != paper.paper_id for c in paper_result.chunks):
        raise ValueError("Accepted source contains foreign paper chunks")
    payload = [(c.chunk_id, c.text, c.section, c.page) for c in paper_result.chunks]
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    parsed_fingerprint = digest
    digest = paper_result.source.raw_content_sha256 or parsed_fingerprint
    source_id = "source:" + hashlib.sha256((paper.doi + ":" + digest).encode()).hexdigest()
    reference_id = "reference:" + paper.doi
    source_url = paper_result.source.url
    source = SourceDocument(
        id=source_id, reference_id=reference_id, doi=paper.doi, title=paper.title,
        authors=tuple(paper.authors), year=paper.year,
        content_locator="memory://" + source_id, content_hash="sha256:" + digest,
        source_type=SourceType(paper_result.source.origin), provider=paper_result.source.provider,
        source_url=source_url, retrieval_status=RetrievalStatus.AVAILABLE,
    )
    chunks = []
    for chunk in paper_result.chunks:
        identity = hashlib.sha256((source_id + ":" + chunk.chunk_id + ":" + chunk.text).encode()).hexdigest()
        chunks.append(EvidenceChunk(
            id="evidence:" + identity, source_document_id=source.id,
            text=chunk.text, page=chunk.page, section=chunk.section,
            source_url=chunk.source_url or source_url,
            metadata={
                "legacy_chunk_id": chunk.chunk_id, "legacy_chunk_index": chunk.chunk_index,
                "legacy_metadata": chunk.metadata or {},
                "source_format": paper.full_text_format,
                "content_hash_kind": "raw_bytes" if paper_result.source.raw_content_sha256 else "parsed_chunks",
                "parsed_content_fingerprint": parsed_fingerprint,
                "source_origin": paper_result.source.origin, "source_cache_hit": paper_result.source.cache_hit,
            },
        ))
    return source, chunks


def standalone_claim_to_domain(processed_claim: ProcessedClaim, source: SourceDocument) -> AtomicClaim:
    """Represent an existing single claim request; no manuscript extraction.

    Synthetic standalone identity is request provenance, not an uploaded manuscript.
    """
    import hashlib
    from ..domain import AtomicClaim

    identity = hashlib.sha256((source.reference_id + ":" + processed_claim.original).encode()).hexdigest()
    return AtomicClaim(
        id="claim:" + identity, manuscript_id="standalone:" + identity,
        paragraph_id="standalone-paragraph:" + identity,
        context_id="standalone-context:" + identity, text=processed_claim.original,
        reference_ids=(source.reference_id,),
    )


def evidence_to_legacy(chunks: list[EvidenceChunk], processed_claim: ProcessedClaim) -> list[EvidenceItem]:
    """Keep PaperQA ordering; compute legacy diagnostics after selection.

    Score is PaperQA's 0..10 relevance divided by 10, not a probability.
    Legacy overlap measures use the unchanged deterministic scoring helper;
    they do not filter, rank or replace PaperQA's selected evidence.
    """
    import math
    from app.schemas.paper import EvidenceChunk as LegacyChunk
    from app.services.evidence_retriever import _score_chunk

    items = []
    for index, chunk in enumerate(chunks):
        score = chunk.retrieval_score
        if score is None or not math.isfinite(score) or not 0 <= score <= 10:
            raise ValueError("PaperQA relevance score must be finite and in 0..10")
        legacy_chunk = LegacyChunk(
            chunk_id=chunk.id, paper_id=chunk.source_document_id,
            section=chunk.section or "Unknown", chunk_index=index,
            text=chunk.text, page=chunk.page, source_url=chunk.source_url,
        )
        item = _score_chunk(processed_claim, legacy_chunk)
        items.append(item.model_copy(update={"relevance_score": score / 10.0}))
    return items
