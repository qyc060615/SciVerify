from __future__ import annotations

from fastapi import APIRouter, HTTPException
from anyio import to_thread
from app.config import EvidenceEngineConfigurationError, get_evidence_engine
from app.researchguard.adapters.paperqa2 import PaperQA2RetrievalError

from app.schemas.verification import VerificationAnalyzeRequest, VerificationResponse
from app.services.paper_retriever import (
    DocumentRetrievalFailure,
    FullTextUnavailableError,
    PaperNotFoundError,
    PaperProviderError,
)
from app.services.verification_service import analyze_verification, analyze_verification_async
from app.utils.claim_preprocessor import InvalidClaimError
from app.utils.doi import InvalidDOIError

router = APIRouter(prefix="/api/verification", tags=["verification"])


@router.post("/analyze", response_model=VerificationResponse)
async def analyze_verification_endpoint(
    request: VerificationAnalyzeRequest,
) -> VerificationResponse:
    """Analyze a scientific claim against a cited paper using the multi-agent verification layer."""
    try:
        if get_evidence_engine() == "lexical":
            return await to_thread.run_sync(analyze_verification, request.claim, request.doi)
        return await analyze_verification_async(request.claim, request.doi)
    except (EvidenceEngineConfigurationError, PaperQA2RetrievalError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InvalidClaimError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InvalidDOIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (DocumentRetrievalFailure, FullTextUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PaperProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
