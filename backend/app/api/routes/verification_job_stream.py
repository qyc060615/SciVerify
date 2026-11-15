"""Read-only SSE projection of durable events; no event bus or worker ownership."""
import asyncio
import json
import time

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.routes.verification_jobs import get_job_runtime
from app.services.verification_job_models import JobState
from app.services.verification_job_store import JobError

router = APIRouter(prefix="/api/verification/jobs", tags=["local verification jobs"])
POLL_INTERVAL = 1.0
HEARTBEAT_INTERVAL = 15.0
MAX_EVENT_BYTES = 16 * 1024


def event_cursor(after, last_event_id):
    # Browser reconnect acknowledgment takes precedence over the original URL.
    if last_event_id is None:
        return after
    if not last_event_id.isascii() or not last_event_id.isdecimal() or len(last_event_id) > 16:
        raise HTTPException(422, detail={"code": "JOB_EVENT_CURSOR_INVALID"})
    value = int(last_event_id)
    if value > 9007199254740991:
        raise HTTPException(422, detail={"code": "JOB_EVENT_CURSOR_INVALID"})
    return value


def encode_event(event):
    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    if len(payload.encode("utf-8")) > MAX_EVENT_BYTES:
        raise JobError("JOB_EVENT_TOO_LARGE", 500)
    return f"id: {event.sequence}\nevent: job\ndata: {payload}\n\n"


async def stream_job_events(runtime, request, job_id, cursor, initial, *,
                            poll_interval=POLL_INTERVAL, heartbeat_interval=HEARTBEAT_INTERVAL):
    snapshot = initial
    heartbeat = time.monotonic()
    yield ": connected\nretry: 3000\n\n"
    try:
        while not await request.is_disconnected():
            for event in snapshot.events:
                if event.sequence > cursor:
                    if await request.is_disconnected():
                        return
                    yield encode_event(event)
                    cursor = event.sequence
            if snapshot.state in {JobState.COMPLETED, JobState.FAILED}:
                return
            if time.monotonic() - heartbeat >= heartbeat_interval:
                yield ": heartbeat\n\n"
                heartbeat = time.monotonic()
            # Never hold a runtime writer lock while waiting/yielding. Store I/O is
            # off the event loop; its existing read lock is released before yield.
            await asyncio.sleep(poll_interval)
            if await request.is_disconnected():
                return
            snapshot = await to_thread.run_sync(runtime.get, job_id)
    except JobError as exc:
        # Headers may already be sent. This control message carries no fake
        # durable sequence, verdict, source body or private storage location.
        yield "event: stream_error\ndata: " + json.dumps({"code": exc.code}) + "\n\n"


@router.get("/{job_id}/stream")
async def stream_job(job_id: str, request: Request, after: int = Query(0, ge=0, le=9007199254740991),
                     runtime=Depends(get_job_runtime)):
    cursor = event_cursor(after, request.headers.get("last-event-id"))
    try:
        snapshot = await to_thread.run_sync(runtime.get, job_id)
        if cursor >= snapshot.next_sequence:
            raise JobError("JOB_EVENT_CURSOR_AHEAD", 409)
    except JobError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code}) from None
    return StreamingResponse(stream_job_events(runtime, request, job_id, cursor, snapshot),
        media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
