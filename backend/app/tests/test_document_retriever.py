from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from app.services.citation_resolver import USER_AGENT
from app.services.document_retriever import (
    DOCUMENT_ACCEPT_HEADER,
    DocumentRetrievalError,
    DocumentTooLargeError,
    InterstitialPageError,
    UnsupportedContentTypeError,
    is_interstitial_content,
    retrieve_document,
)


def _mock_response(
    *,
    status_code: int = 200,
    content: bytes = b"<html><body>Example</body></html>",
    content_type: str = "text/html",
    url: str = "https://example.org/paper.html",
) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.headers = {"content-type": content_type}
    response.url = url
    response.iter_bytes.return_value = [content]
    response.content = content
    return response


class TestDocumentRetriever:
    def test_successful_html_download(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response()

        document = retrieve_document("https://example.org/paper.html", client=client)

        assert document.format == "html"
        assert "Example" in (document.text or "")
        client.get.assert_called_once_with(
            "https://example.org/paper.html",
            headers={"Accept": DOCUMENT_ACCEPT_HEADER, "User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    def test_successful_pdf_download(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            content=b"%PDF-1.4 example",
            content_type="application/pdf",
            url="https://example.org/paper.pdf",
        )

        document = retrieve_document("https://example.org/paper.pdf", client=client)

        assert document.format == "pdf"
        assert document.text is None

    def test_http_error(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(status_code=404)

        with pytest.raises(DocumentRetrievalError):
            retrieve_document("https://example.org/missing", client=client)

    def test_timeout(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.side_effect = httpx.TimeoutException("timeout")

        with pytest.raises(DocumentRetrievalError):
            retrieve_document("https://example.org/paper.html", client=client)

    def test_unsupported_content_type(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(content_type="application/octet-stream")

        with pytest.raises(UnsupportedContentTypeError):
            retrieve_document("https://example.org/file.bin", client=client)

    def test_oversized_response(self) -> None:
        client = MagicMock(spec=httpx.Client)
        oversized = b"x" * 100
        response = _mock_response(content=oversized, content_type="text/html")
        response.headers = {
            "content-type": "text/html",
            "content-length": str(30 * 1024 * 1024),
        }
        client.get.return_value = response

        with pytest.raises(DocumentTooLargeError):
            retrieve_document("https://example.org/huge.html", client=client)

    def test_empty_download_rejected(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(content=b"", content_type="text/html")

        with pytest.raises(DocumentRetrievalError, match="empty"):
            retrieve_document("https://example.org/empty.html", client=client)

    def test_invalid_pdf_content_rejected(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            content=b"not-a-pdf",
            content_type="application/pdf",
            url="https://example.org/paper.pdf",
        )

        with pytest.raises(DocumentRetrievalError, match="not a valid PDF"):
            retrieve_document(
                "https://example.org/paper.pdf",
                expected_format="pdf",
                client=client,
            )

    def test_html_instead_of_pdf_rejected(self) -> None:
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(
            content=b"<!DOCTYPE html><html><body>Not a PDF document</body></html>",
            content_type="application/pdf",
            url="https://example.org/paper.pdf",
        )

        with pytest.raises(DocumentRetrievalError, match="not a valid PDF"):
            retrieve_document(
                "https://example.org/paper.pdf",
                expected_format="pdf",
                client=client,
            )

    def test_captcha_interstitial_html_rejected(self) -> None:
        captcha_html = b"""<!DOCTYPE html><html><body>
        Checking your browser before accessing pmc.ncbi.nlm.nih.gov
        reCAPTCHA
        </body></html>"""
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(content=captcha_html)

        with pytest.raises(InterstitialPageError, match="interstitial"):
            retrieve_document("https://pmc.ncbi.nlm.nih.gov/articles/PMC1/", client=client)

    def test_valid_scientific_html_accepted(self) -> None:
        scientific_html = b"""<!DOCTYPE html><html><body>
        <p>Cas9 can be directed by RNA to cleave double-stranded DNA target sequences.</p>
        </body></html>"""
        client = MagicMock(spec=httpx.Client)
        client.get.return_value = _mock_response(content=scientific_html)

        document = retrieve_document(
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC6286148/",
            client=client,
        )

        assert "Cas9" in (document.text or "")

    def test_is_interstitial_content_detects_browser_check(self) -> None:
        content = b"Checking your browser before accessing pmc.ncbi.nlm.nih.gov"
        assert is_interstitial_content(content) is True

    def test_is_interstitial_content_allows_scientific_text(self) -> None:
        content = b"Cas9 endonuclease introduces double-stranded DNA breaks."
        assert is_interstitial_content(content) is False
