import asyncio
import hashlib
import logging
from pathlib import Path

import httpx
import pytest

from app.researchguard.adapters.grobid import FULLTEXT_OPTIONS, GrobidAdapter, GrobidConfig
from app.researchguard.domain import Manuscript
from app.services.manuscript_errors import ManuscriptParseError

XML = (Path(__file__).parent / "fixtures/manuscript.tei.xml").read_bytes()
PDF = b"%PDF-fixture transport bytes"
MANUSCRIPT = Manuscript(id="m1", content_locator="memory:m1", content_hash="sha256:" + hashlib.sha256(PDF).hexdigest())


@pytest.mark.anyio
async def test_request_options_file_timeout_no_consolidation_and_client_ownership():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=XML, headers={"content-type": "application/xml; charset=utf-8"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = GrobidAdapter(PDF, MANUSCRIPT.content_locator, client=client)
        parsed = await adapter.parse(MANUSCRIPT)
        assert not client.is_closed
    request = requests[0]
    assert request.method == "POST" and str(request.url) == "http://127.0.0.1:8070/api/processFulltextDocument"
    assert request.headers["accept"] == "application/xml"
    assert b'name="input"; filename="manuscript.pdf"' in request.content
    assert b"Content-Type: application/pdf" in request.content and PDF in request.content
    for name, value in FULLTEXT_OPTIONS.items():
        assert (f'name="{name}"\r\n\r\n{value}\r\n').encode() in request.content
    assert request.extensions["timeout"]["connect"] == 5.0
    assert request.extensions["timeout"]["read"] == 180.0
    assert len(parsed.paragraphs) == 3


@pytest.mark.anyio
@pytest.mark.parametrize("failure,code,status", [
    (httpx.ConnectError, "GROBID_UNAVAILABLE", 503),
    (httpx.ReadTimeout, "GROBID_TIMEOUT", 504),
    (httpx.ConnectTimeout, "GROBID_TIMEOUT", 504),
])
async def test_transport_failures_are_safe_and_timeout_is_not_retried(failure, code, status):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        raise failure("secret provider raw body and C:/private/file.pdf", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ManuscriptParseError) as error:
            await GrobidAdapter(PDF, MANUSCRIPT.content_locator, client=client).parse(MANUSCRIPT)
    assert (error.value.code, error.value.status_code) == (code, status)
    assert count == 1 and "private" not in str(error.value) and "secret" not in str(error.value)


@pytest.mark.anyio
@pytest.mark.parametrize("recover", [True, False])
async def test_busy_retry_bounded_fresh_multipart_async_sleep(monkeypatch, recover):
    requests, sleeps = [], []

    async def sleep(delay):
        sleeps.append(delay)

    def handler(request):
        requests.append(request)
        if recover and len(requests) == 3:
            return httpx.Response(200, content=XML, headers={"content-type": "application/xml"})
        return httpx.Response(503, content=b"secret body")

    monkeypatch.setattr("app.researchguard.adapters.grobid.asyncio.sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = GrobidAdapter(PDF, MANUSCRIPT.content_locator, client=client)
        if recover:
            await adapter.parse(MANUSCRIPT)
        else:
            with pytest.raises(ManuscriptParseError) as error:
                await adapter.parse(MANUSCRIPT)
            assert error.value.code == "GROBID_BUSY"
    assert len(requests) == 3 and sleeps == [5.0, 10.0]
    assert all(PDF in request.content for request in requests)


@pytest.mark.anyio
async def test_total_deadline_bounds_slow_response():
    async def handler(request):
        await asyncio.sleep(0.1)
        return httpx.Response(200, content=XML, headers={"content-type": "application/xml"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ManuscriptParseError) as error:
            await GrobidAdapter(PDF, MANUSCRIPT.content_locator, client=client,
                config=GrobidConfig(total_timeout=0.01)).parse(MANUSCRIPT)
    assert error.value.code == "GROBID_TIMEOUT"


@pytest.mark.anyio
@pytest.mark.parametrize("status,media,body,code,http_status", [
    (204, "application/xml", b"", "MANUSCRIPT_PARSE_FAILED", 422),
    (500, "text/plain", b"secret", "MANUSCRIPT_PARSE_FAILED", 502),
    (400, "text/plain", b"secret", "MANUSCRIPT_PARSE_FAILED", 502),
    (302, "application/xml", b"secret", "MANUSCRIPT_PARSE_FAILED", 502),
    (200, "text/html", b"secret", "MALFORMED_TEI", 502),
    (200, "application/xml", b"<broken>", "MALFORMED_TEI", 502),
    (200, "application/xml", b"x" * 2048, "MALFORMED_TEI", 502),
])
async def test_upstream_status_media_xml_and_size_validation(status, media, body, code, http_status):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(
        status, content=body, headers={"content-type": media, "location": "https://untrusted.invalid"}))) as client:
        with pytest.raises(ManuscriptParseError) as error:
            await GrobidAdapter(PDF, MANUSCRIPT.content_locator, client=client,
                                config=GrobidConfig(max_tei_size=1024)).parse(MANUSCRIPT)
    assert (error.value.code, error.value.status_code) == (code, http_status)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("settings", [
    {"base_url": "file:///private"}, {"base_url": "http://user:password@localhost:8070"},
    {"base_url": "http://localhost:8070?url=elsewhere"}, {"base_url": "http://localhost:8070#fragment"},
    {"read_timeout": 0}, {"connect_timeout": float("nan")}, {"total_timeout": float("inf")},
    {"max_tei_size": -1}, {"max_tei_size": True},
])
def test_invalid_backend_config(settings):
    with pytest.raises(ValueError):
        GrobidConfig(**settings)


def test_config_read_at_use_time_safe_failure(monkeypatch):
    monkeypatch.setenv("GROBID_READ_TIMEOUT", "not-a-number")
    with pytest.raises(ManuscriptParseError) as error:
        GrobidConfig.from_environment()
    assert error.value.code == "GROBID_CONFIGURATION_ERROR"


@pytest.mark.anyio
async def test_input_identity_binding_prevents_cross_manuscript_bytes():
    with pytest.raises(ManuscriptParseError):
        await GrobidAdapter(PDF, "other-locator").parse(MANUSCRIPT)


@pytest.mark.anyio
async def test_logs_only_counts_no_manuscript_or_provider_payload(caplog):
    with caplog.at_level(logging.INFO, logger="app.researchguard.adapters.grobid"):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(
            200, content=XML, headers={"content-type": "application/xml"}))) as client:
            await GrobidAdapter(PDF, MANUSCRIPT.content_locator, client=client).parse(MANUSCRIPT)
    logs = "\n".join(r.message for r in caplog.records if r.name == "app.researchguard.adapters.grobid")
    assert "grobid_parse_started size_bytes=" in logs and "grobid_parse_completed paragraphs=3" in logs
    assert "Accuracy study" not in logs and "A & B" not in logs and "<TEI" not in logs and "%PDF" not in logs


@pytest.mark.anyio
@pytest.mark.parametrize("bad", [False, True])
async def test_owned_client_and_stream_closed_on_success_or_failure(monkeypatch, bad):
    clients, streams = [], []
    original = httpx.AsyncClient

    class Stream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"<broken>" if bad else XML

        async def aclose(self):
            self.closed = True

    def handler(request):
        stream = Stream()
        streams.append(stream)
        return httpx.Response(200, stream=stream, headers={"content-type": "application/xml"})

    def create(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        client = original(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr("app.researchguard.adapters.grobid.httpx.AsyncClient", create)
    adapter = GrobidAdapter(PDF, MANUSCRIPT.content_locator)
    if bad:
        with pytest.raises(ManuscriptParseError):
            await adapter.parse(MANUSCRIPT)
    else:
        await adapter.parse(MANUSCRIPT)
    assert clients[0].is_closed and streams[0].closed


@pytest.mark.anyio
async def test_total_deadline_also_bounds_busy_retry_waits():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ManuscriptParseError) as error:
            await GrobidAdapter(PDF, MANUSCRIPT.content_locator, client=client,
                                config=GrobidConfig(total_timeout=0.02)).parse(MANUSCRIPT)
    assert error.value.code == "GROBID_TIMEOUT" and len(requests) == 1
