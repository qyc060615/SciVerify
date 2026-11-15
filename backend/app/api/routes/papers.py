from fastapi import APIRouter, HTTPException

from app.schemas.paper import RetrievePaperRequest, RetrievePaperResponse
from app.services.paper_retriever import (
    DocumentRetrievalFailure,
    FullTextUnavailableError,
    PaperNotFoundError,
    PaperProviderError,
    retrieve_paper,
)
from app.utils.doi import InvalidDOIError

router = APIRouter(prefix="/api/papers", tags=["papers"])


@router.post("/retrieve", response_model=RetrievePaperResponse)
def retrieve_paper_endpoint(
    request: RetrievePaperRequest,
) -> RetrievePaperResponse:
    """Retrieve paper metadata and evidence-ready chunks when full text is accessible."""
    try:
        return retrieve_paper(request.doi)
    except InvalidDOIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PaperNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (DocumentRetrievalFailure, FullTextUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PaperProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
