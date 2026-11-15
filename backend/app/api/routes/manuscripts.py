from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.schemas.manuscript import ManuscriptParseResponse
from app.services.manuscript_errors import ManuscriptParseError
from app.services.manuscript_parser import create_parser, get_manuscript_limit, parse_manuscript

router = APIRouter(prefix="/api/manuscripts", tags=["manuscripts"])


@router.get("/limits")
def upload_limits():
    """Read-only upload bounds shared with the local manuscript/source UI."""
    from app.config import source_max_size
    try:
        return {"manuscript_max_bytes": get_manuscript_limit(), "source_max_bytes": source_max_size()}
    except (ValueError, ManuscriptParseError):
        raise HTTPException(503, detail={"code": "UPLOAD_CONFIGURATION_INVALID"}) from None


def get_parser_factory():
    """Dependency override for offline tests; never accepts a URL from the user."""
    return create_parser


@router.post("/parse", response_model=ManuscriptParseResponse)
async def parse_manuscript_endpoint(file: UploadFile = File(...), parser_factory=Depends(get_parser_factory)):
    """Parse body prose, bibliography and citation markers. No claims or verification."""
    try:
        limit = get_manuscript_limit()
        content = await file.read(limit + 1)
        parsed = await parse_manuscript(content, parser_factory=parser_factory, limit=limit)
        return ManuscriptParseResponse.from_domain(parsed)
    except ManuscriptParseError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    finally:
        await file.close()


def get_extraction_provider_factory():
    from app.services.llm.provider import get_llm_provider
    return get_llm_provider


def get_reference_resolver(request: Request):
    from functools import partial
    from ipaddress import ip_address
    from app.services.reference_resolver import resolve_references
    peer = request.client.host if request.client else ''
    try:
        local = ip_address(peer).is_loopback
    except ValueError:
        local = peer == 'testclient'
    return partial(resolve_references, local_cache=local)


@router.post("/resolve-references", response_model=ManuscriptParseResponse)
async def resolve_references_endpoint(request: Request, resolver=Depends(get_reference_resolver)):
    """Enrich original M3A identities before extraction. No LLM/source retrieval."""
    import json
    from app.schemas.claim_extraction import ClaimExtractionRequest
    from app.services.citation_context import MAX_REQUEST_BYTES, ExtractionInputError, from_request
    from app.services.reference_resolver import ResolutionInputError

    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(413, detail={"code": "RESOLUTION_INPUT_TOO_LARGE"})
        content.extend(chunk)
    try:
        parsed = from_request(ClaimExtractionRequest.model_validate(json.loads(content)))
        enriched = await resolver(parsed)
        return ManuscriptParseResponse.from_domain(enriched)
    except ResolutionInputError as exc:
        raise HTTPException(422, detail={"code": str(exc)}) from None
    except ExtractionInputError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code}) from None
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, detail={"code": "INVALID_MANUSCRIPT_STRUCTURE"}) from None


@router.post("/extract-claims")
async def extract_claims_endpoint(request: Request, provider_factory=Depends(get_extraction_provider_factory)):
    """Extract attributed claims from client-supplied M3A structure using an external LLM.

    No GROBID, cited-source retrieval or scientific verification is performed.
    """
    import json
    from app.schemas.claim_extraction import ClaimExtractionRequest
    from app.services.citation_context import MAX_REQUEST_BYTES, ExtractionInputError, from_request
    from app.services.claim_extractor import extract_claims, failure_http_status

    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(413, detail={"code": "EXTRACTION_INPUT_TOO_LARGE", "message": "The extraction input exceeds the size limit."})
        content.extend(chunk)
    try:
        payload = ClaimExtractionRequest.model_validate(json.loads(content))
        parsed = from_request(payload)
    except ExtractionInputError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": "Submit a valid bounded M3A manuscript structure."}) from None
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        # Pydantic errors can echo manuscript text or client secrets. Never expose them.
        raise HTTPException(422, detail={"code": "INVALID_MANUSCRIPT_STRUCTURE", "message": "Submit a valid M3A manuscript structure."}) from None
    try:
        result = await extract_claims(parsed, provider_factory=provider_factory)
    except ExtractionInputError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": "Submit a valid bounded M3A manuscript structure."}) from None
    return JSONResponse(status_code=failure_http_status(result), content=result.model_dump(mode="json"))
