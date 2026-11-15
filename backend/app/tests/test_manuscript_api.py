from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from starlette.datastructures import UploadFile

from app.main import app
from app.api.routes.manuscripts import get_parser_factory
from app.researchguard.adapters.grobid import GrobidAdapter, GrobidConfig
from app.researchguard.adapters.grobid_tei import parse_tei
from app.researchguard.domain import Manuscript, ParsedManuscript
from app.schemas.evidence import EvidencePaperSummary
from app.schemas.verification import VerificationResponse, VerificationStatus, Verdict
from app.services.manuscript_errors import ManuscriptParseError
from app.services.manuscript_parser import parse_manuscript, validate_pdf

FIXTURES = Path(__file__).parent / "fixtures"
PDF = (FIXTURES / "manuscript.pdf").read_bytes()
XML = (FIXTURES / "manuscript.tei.xml").read_bytes()


@pytest.fixture
def fixture_parser():
    requests = []

    class Parser:
        async def parse(self, manuscript):
            return parse_tei(XML, manuscript)

    def factory(content, manuscript):
        requests.append((content, manuscript))
        return Parser()

    app.dependency_overrides[get_parser_factory] = lambda: factory
    yield requests
    app.dependency_overrides.pop(get_parser_factory, None)


@pytest.fixture
def closed_uploads(monkeypatch):
    uploads = []
    close = UploadFile.close

    async def capture(file):
        uploads.append(file)
        await close(file)

    monkeypatch.setattr(UploadFile, "close", capture)
    yield uploads
    assert uploads and all(file.file.closed for file in uploads)


def test_upload_projection_identity_partial_no_path_bytes_xml_or_verdict(fixture_parser, closed_uploads):
    with TestClient(app) as client:
        response = client.post("/api/manuscripts/parse", files={"file": ("../../private/secret.pdf", PDF, "application/pdf")},
                               data={"grobid_url": "http://untrusted.invalid"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"  # Reconstructed bibliography entry is explicitly reported.
    assert body["scope"] == "body_prose" and body["offset_unit"] == "python_unicode_code_point"
    assert body["schema_version"] == 1
    manuscript = body["parsed"]["manuscript"]
    assert set(manuscript) == {"id", "title", "content_hash"}
    assert manuscript["content_hash"].startswith("sha256:")
    assert body["parsed"]["citation_contexts"] == []
    assert len(body["parsed"]["paragraphs"]) == 3
    assert len(body["parsed"]["references"]) == 2
    for token in ["content_locator", "memory:", "secret.pdf", "C:\\", "<TEI", "%PDF", "verdict", "untrusted.invalid"]:
        assert token not in response.text
    assert fixture_parser[0][0] == PDF


def test_missing_file_422(fixture_parser):
    with TestClient(app) as client:
        assert client.post("/api/manuscripts/parse").status_code == 422
    assert fixture_parser == []


@pytest.mark.parametrize("content", [b"", b"not-pdf", b"%PDF-broken", b"<html/>"])
def test_invalid_pdf_400_before_parser(fixture_parser, closed_uploads, content):
    with TestClient(app) as client:
        response = client.post("/api/manuscripts/parse", files={"file": ("input.pdf", content)})
    assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_MANUSCRIPT_PDF"
    assert fixture_parser == [] and "INSUFFICIENT" not in response.text


def test_oversize_limit_plus_one_before_parser(monkeypatch, fixture_parser, closed_uploads):
    monkeypatch.setenv("RESEARCHGUARD_MANUSCRIPT_MAX_SIZE", "8")
    with TestClient(app) as client:
        response = client.post("/api/manuscripts/parse", files={"file": ("input.pdf", PDF)})
    assert response.status_code == 413 and response.json()["detail"]["code"] == "MANUSCRIPT_TOO_LARGE"
    assert fixture_parser == []


@pytest.mark.parametrize("failure", [
    ("GROBID_UNAVAILABLE", 503), ("GROBID_BUSY", 503), ("GROBID_TIMEOUT", 504),
    ("MALFORMED_TEI", 502), ("MANUSCRIPT_PARSE_FAILED", 422),
])
def test_safe_api_failure_and_cleanup(fixture_parser, closed_uploads, failure):
    class Parser:
        async def parse(self, manuscript):
            raise ManuscriptParseError(failure[0], "Safe failure message.", failure[1])

    app.dependency_overrides[get_parser_factory] = lambda: lambda content, manuscript: Parser()
    with TestClient(app) as client:
        response = client.post("/api/manuscripts/parse", files={"file": ("input.pdf", PDF)})
    assert response.status_code == failure[1]
    assert response.json() == {"detail": {"code": failure[0], "message": "Safe failure message."}}
    assert "verdict" not in response.text and "INSUFFICIENT" not in response.text


@pytest.mark.parametrize("value", ["invalid", "0", "-1"])
def test_invalid_size_config_is_safe_503(monkeypatch, fixture_parser, closed_uploads, value):
    monkeypatch.setenv("RESEARCHGUARD_MANUSCRIPT_MAX_SIZE", value)
    with TestClient(app) as client:
        response = client.post("/api/manuscripts/parse", files={"file": ("input.pdf", PDF)})
    assert response.status_code == 503 and response.json()["detail"]["code"] == "GROBID_CONFIGURATION_ERROR"


def test_no_bibliography_or_callouts_returns_completed_200(fixture_parser):
    class Parser:
        async def parse(self, manuscript):
            return parse_tei(b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><p>Plain prose.</p></body></text></TEI>', manuscript)

    app.dependency_overrides[get_parser_factory] = lambda: lambda content, manuscript: Parser()
    with TestClient(app) as client:
        response = client.post("/api/manuscripts/parse", files={"file": ("input.pdf", PDF)})
    assert response.status_code == 200 and response.json()["status"] == "completed"
    assert {d["code"] for d in response.json()["diagnostics"]} >= {"NO_REFERENCES", "NO_CITATION_CALLOUTS"}


def test_api_unavailable_grobid_does_not_break_health_or_single_claim(monkeypatch):
    class OfflineParser:
        async def parse(self, manuscript):
            def unavailable(request):
                raise httpx.ConnectError("local unavailable", request=request)
            async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable)) as client:
                return await GrobidAdapter(PDF, manuscript.content_locator, client=client).parse(manuscript)

    app.dependency_overrides[get_parser_factory] = lambda: lambda content, manuscript: OfflineParser()
    baseline = VerificationResponse(status=VerificationStatus.SUCCESS, claim="A improves accuracy.",
        verdict=Verdict.SUPPORTS, confidence=0.9, paper=EvidencePaperSummary(paper_id="p", doi="10.1234/test"))
    analyze = Mock(return_value=baseline)
    monkeypatch.setattr("app.api.routes.verification.analyze_verification", analyze)
    try:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/api/health").status_code == 200
            response = client.post("/api/manuscripts/parse", files={"file": ("input.pdf", PDF)})
            assert response.status_code == 503 and response.json()["detail"]["code"] == "GROBID_UNAVAILABLE"
            response = client.post("/api/verification/analyze", json={"claim": "A improves accuracy.", "doi": "10.1234/test"})
            assert response.status_code == 200 and response.json()["verdict"] == "SUPPORTS"
        analyze.assert_called_once_with("A improves accuracy.", "10.1234/test")
    finally:
        app.dependency_overrides.pop(get_parser_factory, None)


@pytest.mark.anyio
async def test_real_pdf_mock_http_mapper_service_end_to_end_and_provider_isolation(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("M3A must not use cited sources or providers")

    monkeypatch.setattr("app.services.paper_retriever.retrieve_paper", forbidden)
    monkeypatch.setattr("app.services.source_store.LocalSourceStore.put", forbidden)
    monkeypatch.setattr("app.services.citation_resolver.resolve_doi", forbidden)
    monkeypatch.setattr("app.services.llm.provider.get_llm_provider", forbidden)

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, content=XML, headers={"content-type": "application/xml"}))) as client:
        parsed = await parse_manuscript(PDF, parser_factory=lambda content, manuscript:
            GrobidAdapter(content, manuscript.content_locator, client=client))
    assert len(parsed.paragraphs) == 3 and len(parsed.references) == 2
    assert parsed.citation_contexts == ()


@pytest.mark.parametrize("kind", ["empty", "encrypted"])
def test_empty_and_encrypted_pdf_rejected(kind):
    writer = PdfWriter()
    if kind == "encrypted":
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)
    with pytest.raises(ManuscriptParseError) as error:
        validate_pdf(output.getvalue(), 20 * 1024 * 1024)
    assert error.value.code == "INVALID_MANUSCRIPT_PDF"


@pytest.mark.anyio
async def test_parser_output_identity_must_match_input():
    class WrongParser:
        async def parse(self, manuscript):
            return ParsedManuscript(manuscript=Manuscript(id="foreign", content_locator="elsewhere"))

    with pytest.raises(ManuscriptParseError):
        await parse_manuscript(PDF, parser_factory=lambda content, manuscript: WrongParser())
