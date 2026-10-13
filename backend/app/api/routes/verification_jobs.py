"""Explicitly enabled, loopback-only local single-user verification jobs."""
import ipaddress
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError

from app.schemas.verification_jobs import JobCreateRequest, JobResumeRequest, JobView, job_view
from app.services.manuscript_verification import MAX_INPUT_BYTES
from app.services.verification_job_store import JobError
from app.services.verification_jobs import jobs_enabled

router = APIRouter(prefix="/api/verification/jobs", tags=["local verification jobs"])


def get_job_runtime(request: Request):
    if not jobs_enabled():
        raise HTTPException(404, detail={"code": "JOBS_DISABLED"})
    peer = request.client.host if request.client else ""
    try:
        local = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        # Starlette's in-memory ASGI test transport; real sockets report an IP.
        local = peer == "testclient"
    if not local:
        raise HTTPException(403, detail={"code": "JOBS_LOCAL_ONLY"})
    runtime = getattr(request.app.state, "verification_jobs", None)
    if runtime is None:
        raise HTTPException(503, detail={"code": "JOB_RUNTIME_UNAVAILABLE"})
    return runtime


def _http_error(exc):
    return HTTPException(exc.status_code, detail={"code": exc.code})


async def _payload(request, model):
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_INPUT_BYTES:
            raise HTTPException(413, detail={"code": "JOB_INPUT_TOO_LARGE"})
        content.extend(chunk)
    try:
        return model.model_validate(json.loads(content))
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, detail={"code": "JOB_INPUT_INVALID"}) from None


@router.post("", status_code=202, response_model=JobView)
async def create_job(request: Request, runtime=Depends(get_job_runtime)):
    payload = await _payload(request, JobCreateRequest)
    try:
        snapshot = await runtime.create(payload.parsed, payload.extraction)
        return job_view(snapshot, runtime.store.limits.max_attempts,
                        runtime_error_code=runtime.errors.get(snapshot.job_id))
    except JobError as exc:
        raise _http_error(exc) from None
    except ValueError:
        raise HTTPException(422, detail={"code": "JOB_INPUT_INVALID"}) from None


@router.get("/{job_id}", response_model=JobView)
async def get_job(job_id: str, runtime=Depends(get_job_runtime)):
    try:
        snapshot = runtime.get(job_id)
        return job_view(snapshot, runtime.store.limits.max_attempts,
                        runtime_error_code=runtime.errors.get(job_id))
    except JobError as exc:
        raise _http_error(exc) from None


@router.get("/{job_id}/events")
async def get_events(job_id: str, after: int = Query(0, ge=0), runtime=Depends(get_job_runtime)):
    try:
        snapshot = runtime.get(job_id)
        return {"job_id": job_id, "events": [e.model_dump(mode="json") for e in snapshot.events if e.sequence > after],
                "next_sequence": snapshot.next_sequence, "runtime_error_code": runtime.errors.get(job_id)}
    except JobError as exc:
        raise _http_error(exc) from None


@router.post("/{job_id}/resume", status_code=202, response_model=JobView)
async def resume_job(job_id: str, request: Request, runtime=Depends(get_job_runtime)):
    payload = await _payload(request, JobResumeRequest)
    try:
        snapshot = await runtime.resume(job_id, **payload.model_dump())
        return job_view(snapshot, runtime.store.limits.max_attempts,
                        runtime_error_code=runtime.errors.get(snapshot.job_id))
    except JobError as exc:
        raise _http_error(exc) from None
