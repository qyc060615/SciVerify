"""Manual opt-in smoke only. Never starts Docker, installs Java or uses providers.

Start grobid/grobid:0.9.1-crf on 127.0.0.1:8070 manually, then:
RUN_GROBID_LOCAL_TESTS=1 python -m pytest -q app/tests/test_grobid_local.py
The synthetic PDF and TEI contract fixture are independently authored; this smoke
checks actual PDF parsing rather than claiming the TEI was generated from the PDF.
"""
import os
from pathlib import Path

import httpx
import pytest

from app.services.manuscript_parser import parse_manuscript


@pytest.mark.skipif(os.getenv("RUN_GROBID_LOCAL_TESTS") != "1", reason="Local GROBID smoke requires explicit opt-in")
@pytest.mark.anyio
async def test_local_grobid_091_pdf_structure():
    from app.researchguard.adapters.grobid import GrobidConfig
    config = GrobidConfig.from_environment()
    assert httpx.URL(config.base_url).host in {"127.0.0.1", "localhost", "::1"}, "Smoke is loopback-only"
    async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
        probe = await client.get(config.base_url + "/api/isalive")
        assert probe.status_code == 200 and probe.text.strip().lower() == "true"
        version = await client.get(config.base_url + "/api/version")
        assert version.status_code == 200 and "0.9.1" in version.text
    pdf = (Path(__file__).parent / "fixtures/manuscript.pdf").read_bytes()
    parsed = await parse_manuscript(pdf)
    assert parsed.paragraphs and parsed.citation_contexts == ()
    paragraphs = {p.id: p for p in parsed.paragraphs}
    for c in parsed.citation_callouts:
        assert paragraphs[c.paragraph_id].text[c.span.start:c.span.end] == c.text
