from __future__ import annotations

import re
from dataclasses import dataclass

CLAIM_MAX_LENGTH = 2000

PUNCTUATION_PATTERN = re.compile(r"[^\w\s.%\-/+]", re.UNICODE)
WHITESPACE_PATTERN = re.compile(r"\s+")
NUMBER_PATTERN = re.compile(
    r"""
    (?:
        \d+(?:\.\d+)?\s*(?:%|percent|mg|ml|kg|hz|khz|mhz|ghz|nm|μm|mm|cm|m|s|ms|min|hr|hours?|days?)
        |
        \d+(?:\.\d+)?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "by",
        "with",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "that",
        "this",
        "these",
        "those",
        "it",
        "its",
        "their",
        "our",
        "we",
        "they",
        "he",
        "she",
        "can",
    }
)


class InvalidClaimError(ValueError):
    """Raised when a claim cannot be processed."""


@dataclass(frozen=True)
class ProcessedClaim:
    original: str
    normalized: str
    tokens: tuple[str, ...]
    claim_numbers: tuple[str, ...]


def preprocess_claim(claim: str) -> ProcessedClaim:
    """Normalize a scientific claim for deterministic evidence retrieval."""
    if claim is None or not claim.strip():
        raise InvalidClaimError("Claim is required.")

    original = claim.strip()
    if len(original) > CLAIM_MAX_LENGTH:
        raise InvalidClaimError(
            f"Claim exceeds the maximum length of {CLAIM_MAX_LENGTH} characters."
        )

    normalized = _normalize_claim_text(original)
    tokens = tuple(_extract_tokens(normalized))
    claim_numbers = tuple(_extract_numbers(original))

    return ProcessedClaim(
        original=original,
        normalized=normalized,
        tokens=tokens,
        claim_numbers=claim_numbers,
    )


def _normalize_claim_text(text: str) -> str:
    lowered = text.lower()
    cleaned = PUNCTUATION_PATTERN.sub(" ", lowered)
    cleaned = re.sub(r"(?<!\d)\.(?!\d)", " ", cleaned)
    return WHITESPACE_PATTERN.sub(" ", cleaned).strip()


def _extract_tokens(normalized_text: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw_token in normalized_text.split():
        token = raw_token.strip(".")
        if len(token) < 2:
            continue
        if token in STOPWORDS:
            continue
        if token.isdigit():
            continue
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def _extract_numbers(text: str) -> list[str]:
    matches = NUMBER_PATTERN.findall(text.lower())
    normalized_numbers: list[str] = []
    seen: set[str] = set()
    for match in matches:
        value = WHITESPACE_PATTERN.sub("", match.strip())
        if value and value not in seen:
            seen.add(value)
            normalized_numbers.append(value)
    return normalized_numbers
