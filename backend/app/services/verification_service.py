from __future__ import annotations

import logging

from app.schemas.evidence import EvidenceRetrievalResponse, EvidenceRetrievalStatus
from app.schemas.verification import (
    VerificationResponse,
    VerificationStatus,
    Verdict,
)
from app.services.agents import run_adjudicator, run_defender, run_prosecutor
from app.services.evidence_pipeline import retrieve_evidence_for_claim
from app.services.llm.provider import (
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseError,
    LLMUnavailableError,
    get_llm_provider,
)
from app.services.paper_retriever import (
    DocumentRetrievalFailure,
    PaperNotFoundError,
    PaperProviderError,
)
from app.services.claim_traceability import build_claim_traceability
from app.services.verification_validator import validate_verification_result
from app.utils.claim_preprocessor import InvalidClaimError, preprocess_claim
from app.utils.doi import InvalidDOIError

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_STATUSES = {
    EvidenceRetrievalStatus.NO_CHUNKS,
    EvidenceRetrievalStatus.NO_RELEVANT_EVIDENCE,
}


class VerificationServiceError(Exception):
    """Raised when verification cannot be completed."""


def analyze_verification(
    claim: str,
    doi: str,
    *,
    llm: LLMProvider | None = None,
) -> VerificationResponse:
    """Run the full multi-agent verification pipeline for a claim and DOI."""
    logger.info("verification_started")

    processed_claim = preprocess_claim(claim)
    logger.info("claim_preprocessed")

    evidence_response = retrieve_evidence_for_claim(processed_claim.original, doi)
    return _verify_evidence(processed_claim.original, evidence_response, llm=llm)


def _verify_evidence(claim: str, evidence_response: EvidenceRetrievalResponse, *, llm: LLMProvider | None = None) -> VerificationResponse:
    processed_claim = preprocess_claim(claim)
    paper = evidence_response.paper

    if evidence_response.status == EvidenceRetrievalStatus.NOT_FOUND:
        logger.info("verification_completed status=not_found")
        raise PaperNotFoundError(evidence_response.detail or "Paper not found.")

    if evidence_response.status == EvidenceRetrievalStatus.PROVIDER_ERROR:
        logger.info("verification_completed status=provider_error")
        raise PaperProviderError(evidence_response.detail or "External provider unavailable.")

    if evidence_response.status in {
        EvidenceRetrievalStatus.FULL_TEXT_UNAVAILABLE,
        EvidenceRetrievalStatus.METADATA_ONLY,
        EvidenceRetrievalStatus.PARSING_FAILURE,
    }:
        from app.config import source_max_size
        from app.schemas.verification import SourceRecovery
        logger.info("verification_completed status=source_required")
        return VerificationResponse(
            status=VerificationStatus.SOURCE_REQUIRED, claim=processed_claim.original,
            paper=paper, source_recovery=SourceRecovery(
                reason=evidence_response.status.value, max_size_bytes=source_max_size()),
            detail="The cited paper could not be retrieved automatically. Upload the cited PDF to continue.",
        )

    if evidence_response.status in INSUFFICIENT_EVIDENCE_STATUSES or not evidence_response.evidence:
        logger.info("verification_completed status=insufficient_evidence")
        traceability = build_claim_traceability(
            processed_claim.original,
            [],
            verdict=Verdict.INSUFFICIENT,
        )
        return VerificationResponse(
            status=VerificationStatus.INSUFFICIENT_EVIDENCE,
            claim=processed_claim.original,
            verdict=Verdict.INSUFFICIENT,
            confidence=0.0,
            summary="Insufficient evidence available to verify this claim against the cited paper.",
            reasoning=evidence_response.detail
            or "Evidence retrieval did not produce usable chunks for agent analysis.",
            paper=paper,
            evidence=[],
            claim_traceability=traceability,
            detail=evidence_response.detail,
        )

    logger.info("evidence_retrieved chunks=%s", len(evidence_response.evidence))

    provider = llm or get_llm_provider()
    try:
        prosecutor = run_prosecutor(processed_claim.original, evidence_response.evidence, provider)
        logger.info("prosecutor_completed")
        defender = run_defender(processed_claim.original, evidence_response.evidence, provider)
        logger.info("defender_completed")
        adjudicator = run_adjudicator(
            processed_claim.original,
            evidence_response.evidence,
            prosecutor,
            defender,
            provider,
        )
        logger.info("adjudicator_completed")
    except LLMUnavailableError as exc:
        logger.info("verification_completed status=llm_unavailable")
        return VerificationResponse(
            status=VerificationStatus.LLM_UNAVAILABLE,
            claim=processed_claim.original,
            paper=paper,
            evidence=evidence_response.evidence,
            detail=str(exc),
        )
    except (LLMProviderError, LLMResponseError) as exc:
        logger.info(
            "verification_completed status=verification_failed error_type=%s",
            type(exc).__name__,
        )
        return VerificationResponse(
            status=VerificationStatus.VERIFICATION_FAILED,
            claim=processed_claim.original,
            paper=paper,
            evidence=evidence_response.evidence,
            detail=str(exc),
        )

    validated = validate_verification_result(
        claim=processed_claim.original,
        evidence=evidence_response.evidence,
        prosecutor=prosecutor,
        defender=defender,
        adjudicator=adjudicator,
    )

    traceability = build_claim_traceability(
        processed_claim.original,
        evidence_response.evidence,
        verdict=validated.verdict,
        adjudicator=adjudicator,
        prosecutor=prosecutor,
    )

    logger.info(
        "verification_completed status=success original_verdict=%s validated_verdict=%s",
        adjudicator.verdict.value,
        validated.verdict.value,
    )
    return VerificationResponse(
        status=VerificationStatus.SUCCESS,
        claim=processed_claim.original,
        verdict=validated.verdict,
        confidence=validated.confidence,
        summary=adjudicator.analysis,
        reasoning=adjudicator.reasoning,
        paper=paper,
        evidence=evidence_response.evidence,
        prosecutor=prosecutor,
        defender=defender,
        adjudicator=adjudicator,
        suggested_correction=validated.suggested_correction,
        agent_agreement=validated.agent_agreement,
        validation_warnings=validated.validation_warnings or None,
        claim_traceability=traceability,
    )


async def analyze_verification_async(
    claim: str, doi: str, *, llm: LLMProvider | None = None,
) -> VerificationResponse:
    """Await evidence engine, then offload the unchanged synchronous verifier."""
    from functools import partial
    from anyio import to_thread
    from app.services.evidence_pipeline import aretrieve_evidence_for_claim

    evidence_response = await aretrieve_evidence_for_claim(claim, doi)
    return await to_thread.run_sync(partial(_verify_evidence, claim, evidence_response, llm=llm))


__all__ = [
    "DocumentRetrievalFailure",
    "InvalidClaimError",
    "InvalidDOIError",
    "PaperNotFoundError",
    "PaperProviderError",
    "VerificationServiceError",
    "analyze_verification",
]
