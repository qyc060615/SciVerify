from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.schemas.manuscript import ManuscriptParseResponse
from app.services.manuscript_errors import ManuscriptParseError
from app.services.manuscript_parser import create_parser, get_manuscript_limit, parse_manuscript

router = APIRouter(prefix="/api/manuscripts", tags=["manuscripts"])


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
