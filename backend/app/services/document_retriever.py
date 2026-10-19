from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

import httpx

from app.config import MAX_DOCUMENT_SIZE, PAPER_REQUEST_TIMEOUT
from app.services.citation_resolver import USER_AGENT

logger = logging.getLogger(__name__)

DocumentFormat = Literal["pdf", "html"]

PDF_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
}
HTML_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}

DOCUMENT_ACCEPT_HEADER = (
    "text/html,application/xhtml+xml,application/pdf,application/xml;q=0.9,*/*;q=0.8"
)

_INTERSTITIAL_PATTERNS = (
    re.compile(r"checking your browser", re.IGNORECASE),
    re.compile(r"recaptcha/challengepage", re.IGNORECASE),
    re.compile(r"g-recaptcha-response", re.IGNORECASE),
    re.compile(r"class=[\"']g-recaptcha[\"']", re.IGNORECASE),
    re.compile(r"recaptcha-checkbox", re.IGNORECASE),
    re.compile(r"recaptcha challenge", re.IGNORECASE),
    re.compile(r"checking your browser before accessing", re.IGNORECASE),
    re.compile(r"cf-browser-verification", re.IGNORECASE),
    re.compile(r"just a moment\.\.\.", re.IGNORECASE),
    re.compile(r"enable javascript and cookies", re.IGNORECASE),
    re.compile(r"bot detection", re.IGNORECASE),
    re.compile(r"access denied", re.IGNORECASE),
)

_PAYWALL_PATTERNS = (
    re.compile(r"subscription required", re.IGNORECASE),
    re.compile(r"purchase access", re.IGNORECASE),
    re.compile(r"paywall", re.IGNORECASE),
    re.compile(r"sign in to access", re.IGNORECASE),
    re.compile(r"institutional access", re.IGNORECASE),
    re.compile(r"buy this article", re.IGNORECASE),
    re.compile(r"full text requires", re.IGNORECASE),
)


class DocumentRetrievalError(Exception):
    """Raised when a document cannot be retrieved."""


class InterstitialPageError(DocumentRetrievalError):
    """Raised when a download returns a browser challenge or anti-bot page."""


class UnsupportedContentTypeError(DocumentRetrievalError):
    """Raised when the response content type is not supported."""


class DocumentTooLargeError(DocumentRetrievalError):
    """Raised when a document exceeds the configured size limit."""


class PaywallError(DocumentRetrievalError):
    """Raised when a document is behind a paywall or requires subscription."""


@dataclass(frozen=True)
class RetrievedDocument:
    content: bytes
    text: str | None
    format: DocumentFormat
    content_type: str
    source_url: str


def is_interstitial_content(content: bytes, text: str | None = None) -> bool:
    """Return True when downloaded content looks like a CAPTCHA or browser-check page."""
    sample = text if text is not None else content.decode("utf-8", errors="replace")
    normalized = sample.strip()
    if not normalized:
        return False

    return any(pattern.search(normalized) for pattern in _INTERSTITIAL_PATTERNS)


def is_paywall_content(content: bytes, text: str | None = None) -> bool:
    """Return True when downloaded content looks like a paywall or subscription page."""
    sample = text if text is not None else content.decode("utf-8", errors="replace")
    normalized = sample.strip()
    if not normalized:
        return False

    return any(pattern.search(normalized) for pattern in _PAYWALL_PATTERNS)


def retrieve_document(
    url: str,
    expected_format: DocumentFormat | None = None,
    client: httpx.Client | None = None,
    *, public_only: bool = False,
) -> RetrievedDocument:
    """Download an accessible PDF or HTML document."""
    owns_client = client is None
    from app.services.public_http import source_client, fetch_public, UnsafeSourceURL
    http_client = client or source_client(PAPER_REQUEST_TIMEOUT)

    try:
        logger.info("Document retrieval started: candidate_url=%s", url)

        try:
            if owns_client or public_only:
                response = fetch_public(http_client, url,
                    headers={"Accept": DOCUMENT_ACCEPT_HEADER, "User-Agent": USER_AGENT},
                    max_bytes=MAX_DOCUMENT_SIZE, timeout=PAPER_REQUEST_TIMEOUT)
            else:
                # Trusted injected dependency, retained for existing DOI callers/tests.
                response = http_client.get(
                    url, headers={"Accept": DOCUMENT_ACCEPT_HEADER, "User-Agent": USER_AGENT},
                    follow_redirects=True)
        except UnsafeSourceURL as exc:
            raise DocumentRetrievalError(str(exc)) from exc
        except ValueError as exc:
            raise DocumentRetrievalError('SOURCE_URL_INVALID') from exc
        except httpx.TimeoutException as exc:
            raise DocumentRetrievalError("Document request timed out.") from exc
        except httpx.RequestError as exc:
            raise DocumentRetrievalError("Document request failed.") from exc

        final_url = str(response.url)
        content_type = _normalize_content_type(
            response.headers.get("content-type", "")
        )
        if public_only and content_type not in PDF_CONTENT_TYPES | HTML_CONTENT_TYPES:
            raise UnsupportedContentTypeError('SOURCE_CONTENT_TYPE_UNSUPPORTED')

        logger.info(
            "Document retrieval response: candidate_url=%s status=%s final_url=%s content_type=%s",
            url,
            response.status_code,
            final_url,
            content_type or "unknown",
        )

        if response.status_code >= 400:
            raise DocumentRetrievalError(
                f"Document request failed with status {response.status_code}."
            )

        detected_format = _detect_format(content_type, url, expected_format)

        raw_content = _read_limited_content(response)
        _validate_downloaded_content(raw_content, detected_format, expected_format)
        text = raw_content.decode("utf-8", errors="replace") if detected_format == "html" else None

        if detected_format == "html" and is_interstitial_content(raw_content, text):
            logger.warning(
                "Document retrieval rejected interstitial content: candidate_url=%s final_url=%s content_type=%s",
                url,
                final_url,
                content_type or "unknown",
            )
            raise InterstitialPageError(
                "Downloaded content is a browser challenge or anti-bot interstitial page."
            )

        if detected_format == "html" and is_paywall_content(raw_content, text):
            logger.warning(
                "Document retrieval rejected paywall content: candidate_url=%s final_url=%s content_type=%s",
                url,
                final_url,
                content_type or "unknown",
            )
            raise PaywallError(
                "Downloaded content is behind a paywall or requires subscription."
            )

        logger.info(
            "Document retrieval accepted: candidate_url=%s final_url=%s format=%s interstitial=false",
            url,
            final_url,
            detected_format,
        )

        return RetrievedDocument(
            content=raw_content,
            text=text,
            format=detected_format,
            content_type=content_type or detected_format,
            source_url=final_url,
        )
    finally:
        if owns_client:
            http_client.close()


def _read_limited_content(response: httpx.Response) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_DOCUMENT_SIZE:
                raise DocumentTooLargeError(
                    "Document exceeds the configured maximum size."
                )
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > MAX_DOCUMENT_SIZE:
            raise DocumentTooLargeError(
                "Document exceeds the configured maximum size."
            )
        chunks.append(chunk)

    if not chunks:
        content = response.content
        if len(content) > MAX_DOCUMENT_SIZE:
            raise DocumentTooLargeError(
                "Document exceeds the configured maximum size."
            )
        return content

    return b"".join(chunks)


def _validate_downloaded_content(
    content: bytes,
    detected_format: DocumentFormat,
    expected_format: DocumentFormat | None,
) -> None:
    if not content:
        raise DocumentRetrievalError("Downloaded document is empty.")

    effective_format = expected_format or detected_format

    if effective_format == "pdf":
        if not content.startswith(b"%PDF"):
            if is_interstitial_content(content):
                raise InterstitialPageError(
                    "Downloaded content is a browser challenge or anti-bot interstitial page."
                )
            raise DocumentRetrievalError(
                "Downloaded content is not a valid PDF document."
            )
        return

    if effective_format == "html":
        sample = content[:512].lstrip().lower()
        if sample.startswith(b"<!doctype html") or sample.startswith(b"<html"):
            return
        if b"<body" in sample or b"<p" in sample or b"<div" in sample:
            return
        raise DocumentRetrievalError(
            "Downloaded content is not a valid HTML document."
        )


def _normalize_content_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def _detect_format(
    content_type: str,
    url: str,
    expected_format: DocumentFormat | None,
) -> DocumentFormat:
    if expected_format is not None:
        return expected_format

    if content_type in PDF_CONTENT_TYPES or url.lower().endswith(".pdf"):
        return "pdf"

    if content_type in HTML_CONTENT_TYPES or url.lower().endswith((".html", ".htm")):
        return "html"

    raise UnsupportedContentTypeError(
        f"Unsupported document content type: {content_type or 'unknown'}"
    )
