from __future__ import annotations

from anyio import to_thread
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from typing import Literal

from app.config import source_max_size
from app.services.manual_source import accept_manual_pdf, ManualSourceError
from app.utils.doi import InvalidDOIError

router = APIRouter(prefix="/api/sources", tags=["sources"])


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
