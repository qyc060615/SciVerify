from __future__ import annotations

import re

MIN_SEGMENT_WORDS = 3
MAX_SEGMENTS = 5

_CONJUNCTION_PATTERN = re.compile(
    r"\s+(?:and|but|while|whereas)\s+",
    re.IGNORECASE,
)
_TO_SPLIT_PATTERN = re.compile(r"\s+to\s+", re.IGNORECASE)
_SEMICOLON_PATTERN = re.compile(r";\s+")
_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")


def segment_claim(claim: str) -> list[str]:
    """Split a claim into a small number of meaningful segments."""
    text = claim.strip()
    if not text:
        return []

    parts: list[str] = []
    for sentence in _SENTENCE_PATTERN.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        parts.extend(_split_sentence(sentence))

    merged = _merge_short_segments(parts)
    if not merged:
        return [text]

    return merged[:MAX_SEGMENTS]


def _split_sentence(sentence: str) -> list[str]:
    segments: list[str] = [sentence]

    for pattern in (_SEMICOLON_PATTERN, _CONJUNCTION_PATTERN):
        next_segments: list[str] = []
        for segment in segments:
            next_segments.extend(_split_with_pattern(segment, pattern))
        segments = next_segments

    final_segments: list[str] = []
    for segment in segments:
        final_segments.extend(_split_on_to(segment))

    return [segment.strip(" ,;") for segment in final_segments if segment.strip(" ,;")]


def _split_with_pattern(text: str, pattern: re.Pattern[str]) -> list[str]:
    parts = [part.strip(" ,;") for part in pattern.split(text) if part.strip(" ,;")]
    return parts or [text]


def _split_on_to(text: str) -> list[str]:
    match = _TO_SPLIT_PATTERN.search(text)
    if not match:
        return [text]

    left = text[: match.start()].strip(" ,;")
    right = f"to {text[match.end() :].strip(' ,;')}"

    if (
        len(left.split()) >= MIN_SEGMENT_WORDS
        and len(right.split()) >= MIN_SEGMENT_WORDS
    ):
        return [left, right]

    return [text]


def _merge_short_segments(segments: list[str]) -> list[str]:
    if not segments:
        return []

    merged: list[str] = []
    buffer = segments[0]

    for segment in segments[1:]:
        if len(buffer.split()) < MIN_SEGMENT_WORDS:
            buffer = f"{buffer} {segment}".strip()
            continue

        if len(segment.split()) < MIN_SEGMENT_WORDS:
            buffer = f"{buffer} {segment}".strip()
            continue

        merged.append(buffer)
        buffer = segment

    if buffer:
        merged.append(buffer)

    return merged
