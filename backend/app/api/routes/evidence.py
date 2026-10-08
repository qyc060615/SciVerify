from __future__ import annotations

from fastapi import APIRouter, HTTPException
from anyio import to_thread
from app.config import EvidenceEngineConfigurationError, get_evidence_engine
from app.researchguard.adapters.paperqa2 import PaperQA2RetrievalError

from app.schemas.evidence import EvidenceRetrievalRequest, EvidenceRetrievalResponse
from app.services.evidence_pipeline import aretrieve_evidence_for_claim, build_evidence_response, retrieve_evidence_for_claim
from app.services.paper_retriever import (
    DocumentRetrievalFailure,
    FullTextUnavailableError,
    PaperNotFoundError,
    PaperProviderError,
    retrieve_paper,
)
from app.utils.claim_preprocessor import InvalidClaimError, preprocess_claim
from app.utils.doi import InvalidDOIError

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


def _retrieve_lexical_evidence(
    request: EvidenceRetrievalRequest,
) -> EvidenceRetrievalResponse:
    """Retrieve and rank the most relevant evidence chunks for a claim against a paper."""
    try:
        processed_claim = preprocess_claim(request.claim)
    except InvalidClaimError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        paper_result = retrieve_paper(request.doi)
    except InvalidDOIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (DocumentRetrievalFailure, FullTextUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PaperProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return build_evidence_response(processed_claim, paper_result)


@router.post("/retrieve", response_model=EvidenceRetrievalResponse)
async def retrieve_evidence_endpoint(request: EvidenceRetrievalRequest) -> EvidenceRetrievalResponse:
    try:
        if get_evidence_engine() == "lexical":
            return await to_thread.run_sync(_retrieve_lexical_evidence, request)
        return await aretrieve_evidence_for_claim(request.claim, request.doi)
    except (EvidenceEngineConfigurationError, PaperQA2RetrievalError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (InvalidClaimError, InvalidDOIError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (DocumentRetrievalFailure, FullTextUnavailableError, PaperProviderError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


__all__ = ["retrieve_evidence_for_claim", "router"]
