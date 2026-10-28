"""Loopback-only configuration administration with Origin/Host and CSRF guards."""
import hmac
import json
import os
import secrets
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.settings_catalog import CATALOG, loopback
from app.settings_store import SettingsError, public_settings, save_connection, candidate, effective
from app.services.settings_checks import probe, remember_result, system_status

_TOKEN = secrets.token_urlsafe(32)
_PROBES = BoundedSemaphore(1)


def require_local(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    if any(name in request.headers for name in ('forwarded', 'x-forwarded-for', 'x-forwarded-host', 'x-real-ip')):
        raise HTTPException(403, detail={'message': 'Use a direct loopback connection for settings administration.'})
    peer = request.client.host if request.client else ''
    host = request.headers.get('host', '')
    try:
        parsed = urlsplit('http://' + host)
        parsed.port  # Reject malformed Host ports as well as DNS-rebinding hosts.
        valid_host = loopback(parsed.hostname) and not parsed.username and not parsed.password and not parsed.path
    except ValueError:
        valid_host = False
    if (os.getenv('RESEARCHGUARD_SETTINGS_ENABLED', '1') != '1' or
            not (loopback(peer) or peer == 'testclient') or not valid_host):
        raise HTTPException(403, detail={'message': 'Settings administration is available on loopback only.'})
    origin = request.headers.get('origin')
    allowed = {'http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:5174', 'http://localhost:5174',
               str(request.base_url).rstrip('/')}
    configured = os.getenv('FRONTEND_URL', '')
    if configured:
        try:
            if loopback(urlsplit(configured).hostname):
                allowed.add(configured.rstrip('/'))
        except ValueError:
            pass
    if origin and origin not in allowed:
        raise HTTPException(403, detail={'message': 'This page is not an allowed local settings origin.'})
    for name in ('WEB_CONCURRENCY', 'UVICORN_WORKERS', 'RESEARCHGUARD_JOB_PROCESSES'):
        if os.getenv(name, '1') != '1':
            raise HTTPException(503, detail={'message': 'Settings administration requires one backend process.'})
    if request.method != 'GET' and not hmac.compare_digest(request.headers.get('x-settings-token', ''), _TOKEN):
        raise HTTPException(403, detail={'message': 'Reload Settings before making this change.'})


router = APIRouter(prefix='/api/settings', tags=['local settings'], dependencies=[Depends(require_local)])


def _error(exc):
    return HTTPException(exc.status, detail={'message': str(exc)})


async def payload(request):
    if request.headers.get('content-type', '').split(';')[0] != 'application/json':
        raise HTTPException(415, detail={'message': 'Use a JSON settings request.'})
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > 32 * 1024:
            raise HTTPException(413, detail={'message': 'The settings request is too large.'})
        content.extend(chunk)
    try:
        body = json.loads(content)
        if not isinstance(body, dict) or not body.keys() <= {'values', 'api_key', 'clear_api_key', 'revision', 'allow_paid'}:
            raise ValueError()
        return body
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, detail={'message': 'Invalid settings request.'}) from None


@router.get('')
async def get_settings():
    try:
        return {**await to_thread.run_sync(public_settings), 'management_token': _TOKEN}
    except SettingsError as exc:
        raise _error(exc) from None


@router.put('/connections/{id}')
async def update_connection(id: str, request: Request):
    body = await payload(request)
    try:
        return await to_thread.run_sync(save_connection, id, body.get('values'), body.get('api_key'),
                                       body.get('clear_api_key', False), body.get('revision'))
    except SettingsError as exc:
        raise _error(exc) from None


@router.post('/connections/{id}/test')
async def test_connection(id: str, request: Request):
    if id not in CATALOG:
        raise HTTPException(404, detail={'message': 'Unknown API service.'})
    body = await payload(request)
    if CATALOG[id]['paid_test'] and body.get('allow_paid') is not True:
        raise HTTPException(400, detail={'message': 'Confirm the possible model charge before testing.'})
    try:
        profiles = candidate(id, body.get('values'), body.get('api_key'), body.get('clear_api_key', False))
        row = effective(profiles, id)
        if not _PROBES.acquire(blocking=False):
            raise HTTPException(429, detail={'message': 'Another service check is running. Try again shortly.'})
        try:
            result = await to_thread.run_sync(probe, id, row)
            remember_result(id, row, result)
            return result
        finally:
            _PROBES.release()
    except SettingsError as exc:
        raise _error(exc) from None


@router.get('/status')
async def status():
    return system_status()


@router.post('/status/refresh')
async def refresh_status():
    if not _PROBES.acquire(blocking=False):
        raise HTTPException(429, detail={'message': 'Another service check is running. Try again shortly.'})
    try:
        return await to_thread.run_sync(system_status, True)
    finally:
        _PROBES.release()
