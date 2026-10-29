from __future__ import annotations

from anyio import to_thread
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request, Response
import ipaddress
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError
from typing import Literal

from app.config import source_max_size
from app.services.manual_source import accept_manual_pdf, ManualSourceError
from app.utils.doi import InvalidDOIError
from app.researchguard.source_locator import SourceLocator
from app.researchguard.domain import Reference

router = APIRouter(prefix="/api/sources", tags=["sources"])


class PrepareSourceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reference: Reference
    retrieve: bool = False


@router.post('/prepare')
async def prepare_source(payload: PrepareSourceRequest, request: Request, response: Response):
    """Validate local reuse, or acquire a cited source, without a Job or model call."""
    from functools import partial
    from app.services.source_preparation import prepare_reference
    peer = request.client.host if request.client else ''
    try:
        local = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        local = peer == 'testclient'
    if not local:
        raise HTTPException(403, detail={'code': 'SOURCES_LOCAL_ONLY'})
    response.headers['Cache-Control'] = 'no-store'
    return await to_thread.run_sync(partial(prepare_reference, payload.reference, retrieve=payload.retrieve))


@router.post('/manual-reference')
async def upload_reference_source(request: Request, reference: str = Form(...), file: UploadFile = File(...), locator: str | None = Form(None)):
    from app.services.manual_source import accept_reference_pdf
    try:
        peer = request.client.host if request.client else ''
        if peer != 'testclient' and not ipaddress.ip_address(peer).is_loopback:
            raise HTTPException(403, detail={'code': 'SOURCES_LOCAL_ONLY'})
        if len(reference.encode('utf-8')) > 100_000:
            raise HTTPException(413, detail={'code': 'REFERENCE_TOO_LARGE'})
        parsed = Reference.model_validate_json(reference)
        content = await file.read(source_max_size() + 1)
        if locator is not None and len(locator) > 8192:
            raise HTTPException(413, detail={'code': 'SOURCE_LOCATOR_TOO_LARGE'})
        selected = SourceLocator.model_validate_json(locator) if locator else None
        from functools import partial
        return await to_thread.run_sync(partial(accept_reference_pdf, parsed, content, locator=selected))
    except ValidationError:
        raise HTTPException(422, detail={'code': 'REFERENCE_INVALID'}) from None
    except ManualSourceError as exc:
        raise HTTPException(exc.status_code, detail={'code': exc.code, 'message': str(exc)}) from exc
    except ValueError:
        raise HTTPException(422, detail={'code': 'SOURCE_IDENTITY_OR_URL_INVALID'}) from None
    finally:
        await file.close()


@router.post('/status')
async def source_status(locator: SourceLocator, request: Request, response: Response):
    """Read the current cache pointer and verify bytes. Never fetch a remote source."""
    from app.services.source_store import LocalSourceStore
    peer = request.client.host if request.client else ''
    try:
        local = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        local = peer == 'testclient'
    if not local:
        raise HTTPException(403, detail={'code': 'SOURCES_LOCAL_ONLY'})
    response.headers['Cache-Control'] = 'no-store'
    artifact = await to_thread.run_sync(LocalSourceStore().get_locator, locator)
    if artifact is None or not artifact.paper.full_text_available or artifact.paper.full_text_format != artifact.format:
        return {'availability': 'not_cached', 'remote_status': 'not_checked', 'raw_content_sha256': None, 'format': None}
    return {'availability': 'available', 'remote_status': 'not_checked',
            'raw_content_sha256': artifact.raw_content_sha256, 'format': artifact.format}


class ManualSourceResponse(BaseModel):
    status: Literal["accepted"]
    doi: str
    raw_content_sha256: str
    identity_match: Literal["doi", "title_author_year"]


@router.post("/manual", response_model=ManualSourceResponse)
async def upload_manual_source(doi: str = Form(...), file: UploadFile = File(...)):
    try:
        # The uploaded filename is never used, stored, or logged.
        limit = source_max_size()
        content = await file.read(limit + 1)
        if len(content) > limit:
            raise ManualSourceError("FILE_TOO_LARGE", "The PDF exceeds the configured upload size limit.", 413)
        return await to_thread.run_sync(accept_manual_pdf, doi, content)
    except InvalidDOIError as exc:
        raise HTTPException(400, detail={"code": "INVALID_DOI", "message": "Provide a valid DOI."}) from exc
    except ManualSourceError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    finally:
        await file.close()
