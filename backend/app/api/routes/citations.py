from fastapi import APIRouter, HTTPException

from app.schemas.citation import CitationMetadata, ResolveCitationRequest
from app.services.citation_resolver import (
    CitationNotFoundError,
    CitationResolverError,
    resolve_doi,
)
from app.utils.doi import InvalidDOIError

router = APIRouter(prefix="/api/citations", tags=["citations"])


@router.post("/resolve", response_model=CitationMetadata)
def resolve_citation(request: ResolveCitationRequest) -> CitationMetadata:
    """Resolve a DOI to normalized citation metadata (Crossref → OpenAlex)."""
    try:
        return resolve_doi(request.doi)
    except InvalidDOIError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CitationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CitationResolverError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
