"""Local GROBID 0.9.1 REST integration, behind the existing async parser port."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from dataclasses import dataclass

import httpx
from anyio import to_thread

from app.config import grobid_settings
from app.researchguard.domain import Manuscript, ParsedManuscript
from app.researchguard.adapters.grobid_tei import parse_tei
from app.services.manuscript_errors import ManuscriptParseError

logger = logging.getLogger(__name__)
FULLTEXT_OPTIONS = {
    "consolidateHeader": "0", "consolidateCitations": "0", "consolidateFunders": "0",
    "includeRawCitations": "1", "segmentSentences": "1",
}


@dataclass(frozen=True)
class GrobidConfig:
    base_url: str = "http://127.0.0.1:8070"
    connect_timeout: float = 5.0
    read_timeout: float = 180.0
    total_timeout: float = 240.0
    max_tei_size: int = 20 * 1024 * 1024

    def __post_init__(self):
        try:
            url = httpx.URL(self.base_url)
            valid = url.scheme in {"http", "https"} and bool(url.host) and not url.userinfo and not url.query and not url.fragment
        except (httpx.InvalidURL, TypeError):
            valid = False
        if not valid or any(not math.isfinite(v) or v <= 0 for v in
                           (self.connect_timeout, self.read_timeout, self.total_timeout)):
            raise ValueError("Invalid GROBID endpoint or timeout configuration")
        if type(self.max_tei_size) is not int or self.max_tei_size <= 0:
            raise ValueError("Invalid TEI size limit")

    @classmethod
    def from_environment(cls):
        try:
            return cls(**grobid_settings())
        except (ValueError, TypeError, OverflowError) as exc:
            raise ManuscriptParseError("GROBID_CONFIGURATION_ERROR", "Manuscript parser configuration is invalid.", 503) from exc


class GrobidAdapter:
    """Request-scoped memory binding; no arbitrary locator/path reads or disk cache.

    The application binds bytes to an opaque locator before calling parse(manuscript).
    An injected AsyncClient is caller-owned. Production clients ignore environment
    proxies and redirects, so local PDFs cannot be redirected to other services.
    """

    def __init__(self, content: bytes, locator: str, *, config: GrobidConfig | None = None,
                 client: httpx.AsyncClient | None = None):
        self.content = content
        self.locator = locator
        self.config = config or GrobidConfig.from_environment()
        self.client = client

    async def parse(self, manuscript: Manuscript) -> ParsedManuscript:
        digest = "sha256:" + hashlib.sha256(self.content).hexdigest()
        if manuscript.content_locator != self.locator or manuscript.content_hash != digest:
            raise ManuscriptParseError("MANUSCRIPT_PARSE_FAILED", "The manuscript input binding is inconsistent.")
        logger.info("grobid_parse_started size_bytes=%d", len(self.content))
        timeout = httpx.Timeout(connect=self.config.connect_timeout, read=self.config.read_timeout,
                                write=30.0, pool=self.config.connect_timeout)
        owned = self.client is None
        client = self.client or httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False)
        try:
            async with asyncio.timeout(self.config.total_timeout):
                xml = await self._fulltext(client, timeout)
                parsed = await to_thread.run_sync(parse_tei, xml, manuscript)
            logger.info("grobid_parse_completed paragraphs=%d references=%d callouts=%d",
                        len(parsed.paragraphs), len(parsed.references), len(parsed.citation_callouts))
            return parsed
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ManuscriptParseError("GROBID_TIMEOUT", "The manuscript parser timed out.", 504) from exc
        except httpx.RequestError as exc:
            raise ManuscriptParseError("GROBID_UNAVAILABLE", "The local manuscript parser is unavailable.", 503) from exc
        finally:
            if owned:
                await client.aclose()

    async def _fulltext(self, client, timeout):
        for attempt in range(3):
            # Rebuild multipart every attempt; fixed server-side filename only.
            async with client.stream("POST", self.config.base_url.rstrip("/") + "/api/processFulltextDocument",
                data=FULLTEXT_OPTIONS, files={"input": ("manuscript.pdf", self.content, "application/pdf")},
                headers={"Accept": "application/xml"}, timeout=timeout, follow_redirects=False) as response:
                if response.status_code == 503:
                    if attempt == 2:
                        raise ManuscriptParseError("GROBID_BUSY", "The manuscript parser is busy. Try again later.", 503)
                elif response.status_code == 204:
                    raise ManuscriptParseError("MANUSCRIPT_PARSE_FAILED", "No manuscript text could be extracted.", 422)
                elif response.status_code != 200:
                    # Do not log, expose or classify using provider raw response bodies.
                    raise ManuscriptParseError("MANUSCRIPT_PARSE_FAILED", "The manuscript parser could not process the document.")
                else:
                    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if media_type not in {"application/xml", "text/xml", "application/tei+xml"}:
                        raise ManuscriptParseError("MALFORMED_TEI", "The manuscript parser did not return TEI XML.")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > self.config.max_tei_size:
                            raise ManuscriptParseError("MALFORMED_TEI", "The manuscript parser response exceeds the size limit.")
                        content.extend(chunk)
                    return bytes(content)
            await asyncio.sleep(5.0 * (attempt + 1))
        raise AssertionError("Unreachable bounded retry state")
