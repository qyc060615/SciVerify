"""Bounded SSE replay/heartbeat/disconnect tests with no live provider calls."""
import asyncio
import json

import httpx
import pytest

from app.main import app
from app.api.routes.verification_job_stream import encode_event, event_cursor, stream_job_events
from app.services.verification_job_store import JobError
from app.tests.test_manuscript_verification import inputs, paper
from app.tests.test_verification_jobs import harness


def decode(text):
    records = []
    for block in text.split('\n\n'):
        fields = dict(line.split(': ', 1) for line in block.splitlines() if ': ' in line and not line.startswith(':'))
        if fields.get('event') == 'job':
            records.append((int(fields['id']), json.loads(fields['data'])))
    return records


@pytest.mark.anyio
async def test_stream_completed_replays_exact_json_events_and_no_fake_progress(harness, monkeypatch):
    h = harness()
    monkeypatch.setenv('RESEARCHGUARD_JOBS_ENABLED', '1')
    monkeypatch.setattr(app.state, 'verification_jobs', h.runtime, raising=False)
    job = await h.runtime.create(*inputs())
    saved = await h.runtime.wait(job.job_id)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1)), base_url='http://test') as client:
        events = (await client.get(f'/api/verification/jobs/{job.job_id}/events')).json()['events']
        for headers, after, cursor in [({}, 0, 0), ({}, 2, 2), ({'Last-Event-ID': '3'}, 1, 3), ({'Last-Event-ID': '1'}, 3, 1)]:
            response = await client.get(f'/api/verification/jobs/{job.job_id}/stream?after={after}', headers=headers)
            assert response.status_code == 200 and response.headers['content-type'].startswith('text/event-stream')
            decoded = decode(response.text)
            assert [r for _, r in decoded] == [e for e in events if e['sequence'] > cursor]
            assert all(seq == event['sequence'] for seq, event in decoded)
            assert 'content_locator' not in response.text and 'Treatment reduces risk' not in response.text
        assert h.runtime.get(job.job_id) == saved
        assert len(h.verified) == 1


@pytest.mark.anyio
@pytest.mark.parametrize('case, status', [('disabled', 404), ('nonlocal', 403), ('missing', 404), ('corrupt', 500), ('cursor', 422), ('ahead', 409)])
async def test_stream_access_integrity_and_cursor_errors(harness, monkeypatch, case, status):
    h = harness()
    monkeypatch.setenv('RESEARCHGUARD_JOBS_ENABLED', '0' if case == 'disabled' else '1')
    monkeypatch.setattr(app.state, 'verification_jobs', h.runtime, raising=False)
    job = await h.runtime.create(*inputs())
    await h.runtime.wait(job.job_id)
    if case == 'corrupt':
        (h.store.root / (job.job_id + '.json')).write_bytes(b'{bad')
    job_id = 'job_' + 'f' * 32 if case == 'missing' else job.job_id
    headers = {'Last-Event-ID': 'private-path'} if case == 'cursor' else {}
    suffix = '?after=9999' if case == 'ahead' else ''
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('192.0.2.1' if case == 'nonlocal' else '127.0.0.1', 1)), base_url='http://test') as client:
        response = await client.get(f'/api/verification/jobs/{job_id}/stream{suffix}', headers=headers)
        assert response.status_code == status and 'private-path' not in response.text


@pytest.mark.parametrize('header', ['', '-1', 'NaN', '1.1', '１', '9007199254740992'])
def test_invalid_last_event_id_is_bounded(header):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        event_cursor(0, header)


class Connection:
    disconnected = False
    async def is_disconnected(self):
        return self.disconnected


@pytest.mark.anyio
async def test_heartbeat_disconnect_and_resume_use_same_durable_sequence(harness):
    h = harness(blocked=['10.1234/local'])
    job = await h.runtime.create(*inputs())
    waiting = await h.runtime.wait(job.job_id)
    request = Connection()
    stream = stream_job_events(h.runtime, request, job.job_id, waiting.next_sequence - 1, waiting,
                               poll_interval=.01, heartbeat_interval=0)
    assert ': connected' in await anext(stream)
    heartbeat = await asyncio.wait_for(anext(stream), 1)
    assert heartbeat == ': heartbeat\n\n' and 'id:' not in heartbeat
    # Streaming holds no writer lock; upload/resume proceeds while generator is suspended.
    digest = h.accept('10.1234/local')
    await h.runtime.resume(job.job_id, expected_revision=waiting.revision, source_hashes={'r1': digest})
    final = await h.runtime.wait(job.job_id)
    remainder = []
    async def collect():
        async for chunk in stream:
            remainder.append(chunk)
    await asyncio.wait_for(collect(), 2)
    assert [event for _, event in decode(''.join(remainder))] == [e.model_dump(mode='json') for e in final.events if e.sequence >= waiting.next_sequence]
    request = Connection()
    active = stream_job_events(h.runtime, request, job.job_id, 0, waiting, poll_interval=.01)
    await anext(active)
    request.disconnected = True
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(active), 1)
    await active.aclose()


@pytest.mark.anyio
async def test_midstream_storage_error_is_control_message_not_business_event(harness, monkeypatch):
    h = harness(blocked=['10.1234/local'])
    job = await h.runtime.create(*inputs())
    waiting = await h.runtime.wait(job.job_id)
    stream = stream_job_events(h.runtime, Connection(), job.job_id, waiting.next_sequence - 1, waiting, poll_interval=.01)
    await anext(stream)
    monkeypatch.setattr(h.runtime, 'get', lambda _: (_ for _ in ()).throw(JobError('JOB_SNAPSHOT_CORRUPT', 500)))
    chunk = await asyncio.wait_for(anext(stream), 1)
    assert 'event: stream_error' in chunk and 'id:' not in chunk
    await stream.aclose()


def test_event_payload_is_bounded_and_has_no_snapshot_body():
    from app.services.verification_job_models import EventRecord
    event = EventRecord(job_id='job_' + 'a' * 32, sequence=1, event_type='job_created', status='pending', timestamp='now')
    assert decode(encode_event(event))[0][1] == event.model_dump(mode='json')
    with pytest.raises(JobError, match='JOB_EVENT_TOO_LARGE'):
        encode_event(event.model_copy(update={'reason_code': 'x' * 20000}))
