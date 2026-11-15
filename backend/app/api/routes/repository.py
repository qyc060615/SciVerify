"""Local-only, read-only literature inventory. Existing source APIs stay unchanged."""
import ipaddress

from anyio import to_thread
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from typing import Literal

from app.services.literature_repository import list_literature

router = APIRouter(prefix='/api/repository', tags=['local literature repository'])


class LiteratureRecord(BaseModel):
    id: str
    title: str | None
    doi: str | None
    literature_type: Literal['Reference']
    format: Literal['pdf', 'html']
    source_type: Literal['Uploaded PDF', 'Retrieved HTML', 'Other']
    availability: Literal['available', 'missing', 'corrupt', 'unavailable']
    raw_content_sha256: str
    source_url: str | None
    related_job_ids: list[str]


class RepositoryResponse(BaseModel):
    records: list[LiteratureRecord]
    warnings: list[str]


@router.get('', response_model=RepositoryResponse)
async def repository(request: Request, response: Response):
    peer = request.client.host if request.client else ''
    try:
        local = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        local = peer == 'testclient'
    if not local:
        raise HTTPException(403, detail={'code': 'REPOSITORY_LOCAL_ONLY'})
    response.headers['Cache-Control'] = 'no-store'
    try:
        return await to_thread.run_sync(list_literature)
    except OSError:
        raise HTTPException(503, detail={'code': 'REPOSITORY_STORAGE_UNAVAILABLE',
                                       'message': 'The local literature storage could not be read.'}) from None
