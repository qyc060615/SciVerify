from __future__ import annotations

import re

MULTIPLE_BLANK_LINES = re.compile(r"\n{3,}")
MULTIPLE_SPACES = re.compile(r"[ \t]{2,}")
CARRIAGE_RETURN = re.compile(r"\r\n?")


def clean_text(text: str) -> str:
    """Normalize whitespace while preserving paragraph structure and scientific content."""
    if not text:
        return ""

    normalized = CARRIAGE_RETURN.sub("\n", text)
    normalized = normalized.replace("\u00a0", " ")
    normalized = _remove_repeated_short_lines(normalized)
    normalized = _normalize_paragraphs(normalized)
    return normalized.strip()


def clean_section_text(text: str) -> str:
    """Clean section text while preserving internal paragraph breaks."""
    return clean_text(text)


def _normalize_paragraphs(text: str) -> str:
    lines = text.split("\n")
    cleaned_lines: list[str] = []
    for line in lines:
        stripped = MULTIPLE_SPACES.sub(" ", line.strip())
        cleaned_lines.append(stripped)

    joined = "\n".join(cleaned_lines)
    joined = MULTIPLE_BLANK_LINES.sub("\n\n", joined)
    return joined


def _remove_repeated_short_lines(text: str) -> str:
    """Remove obvious repeated header/footer lines when they appear on many pages."""
    lines = text.split("\n")
    if len(lines) < 6:
        return text

    counts: dict[str, int] = {}
    for line in lines:
        candidate = line.strip()
        if not candidate or len(candidate) > 120:
            continue
        counts[candidate] = counts.get(candidate, 0) + 1

    repeated = {line for line, count in counts.items() if count >= 4}
    if not repeated:
        return text

    filtered = [line for line in lines if line.strip() not in repeated]
    return "\n".join(filtered)
