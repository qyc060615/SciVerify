from __future__ import annotations

import re

_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_evidence_text(text: str) -> str:
    """Normalize evidence text for duplicate comparison only."""
    if not text:
        return ""

    normalized = text.replace("\u00a0", " ")
    normalized = _HTML_TAG_PATTERN.sub(" ", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _WHITESPACE_PATTERN.sub(" ", normalized)
    return normalized.strip().casefold()
