from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.config import (
    EVIDENCE_DIVERSITY_THRESHOLD,
    EVIDENCE_MAX_PER_SECTION,
    EVIDENCE_MIN_RELEVANCE,
    EVIDENCE_TOP_K,
)
from app.schemas.evidence import EvidenceItem
from app.schemas.paper import EvidenceChunk
from app.utils.claim_preprocessor import (
    ProcessedClaim,
    STOPWORDS,
    _extract_numbers,
    _normalize_claim_text,
)
from app.utils.evidence_text import normalize_evidence_text

logger = logging.getLogger(__name__)

# Section weights influence ranking only — they do not determine correctness.
SECTION_WEIGHTS: dict[str, float] = {
    "results": 1.0,
    "findings": 1.0,
    "experiments": 0.95,
    "experimental results": 0.95,
    "methods": 0.85,
    "materials and methods": 0.85,
    "methodology": 0.85,
    "abstract": 0.75,
    "discussion": 0.7,
    "conclusion": 0.65,
    "conclusions": 0.65,
    "limitations": 0.6,
    "introduction": 0.6,
    "background": 0.55,
    "body": 0.5,
    "references": 0.2,
}

SECTION_BONUSES: dict[str, float] = {
    "abstract": 0.05,
    "results": 0.05,
    "conclusion": 0.05,
    "conclusions": 0.05,
    "discussion": 0.04,
    "methods": 0.02,
    "materials and methods": 0.02,
    "methodology": 0.02,
    "introduction": 0.0,
    "background": 0.0,
    "references": -0.05,
    "acknowledgments": -0.05,
    "acknowledgements": -0.05,
}

DEFAULT_SECTION_WEIGHT = 0.5

PHRASE_SIGNAL_WEIGHT = 0.50
CLAIM_OVERLAP_WEIGHT = 0.30
NUMERIC_WEIGHT = 0.10
SECTION_SIGNAL_WEIGHT = 0.10

_FIGURE_SECTION_PATTERN = re.compile(r"^(fig\.?|figure|table)\b", re.IGNORECASE)


@dataclass(frozen=True)
class RankedEvidence:
    item: EvidenceItem
    sort_key: tuple[float, float, float, int, str]


def rank_evidence_for_claim(
    claim: ProcessedClaim,
    chunks: list[EvidenceChunk],
    *,
    top_k: int | None = None,
    min_relevance: float | None = None,
) -> list[EvidenceItem]:
    """Rank paper chunks against a processed claim."""
    effective_top_k = top_k if top_k is not None else EVIDENCE_TOP_K
    effective_min_relevance = (
        min_relevance if min_relevance is not None else EVIDENCE_MIN_RELEVANCE
    )

    deduped_chunks = _dedupe_chunks(chunks)
    ranked: list[RankedEvidence] = []

    for chunk in deduped_chunks:
        item = _score_chunk(claim, chunk)
        ranked.append(
            RankedEvidence(
                item=item,
                sort_key=(
                    -item.relevance_score,
                    -item.claim_overlap,
                    -item.numeric_overlap,
                    chunk.chunk_index,
                    chunk.chunk_id,
                ),
            )
        )

    ranked.sort(key=lambda entry: entry.sort_key)

    filtered = [
        entry.item
        for entry in ranked
        if entry.item.relevance_score >= effective_min_relevance
    ]

    if not filtered and ranked:
        logger.info(
            "Evidence ranking: candidate_count=%s deduplicated_count=0 selected_count=0 top_score=%s",
            len(deduped_chunks),
            None,
        )
        return []

    deduplicated = dedupe_evidence_items(filtered)
    selected = select_diverse_evidence(deduplicated, effective_top_k)

    logger.info(
        "Evidence ranking: candidate_count=%s deduplicated_count=%s selected_count=%s top_score=%s",
        len(deduped_chunks),
        len(deduplicated),
        len(selected),
        selected[0].relevance_score if selected else None,
    )

    return selected


def _score_chunk(claim: ProcessedClaim, chunk: EvidenceChunk) -> EvidenceItem:
    chunk_normalized = _normalize_claim_text(chunk.text)
    chunk_tokens = set(_tokenize(chunk_normalized))

    claim_overlap = _enhanced_claim_overlap(claim, chunk_normalized, chunk_tokens)
    phrase_overlap = _phrase_overlap_score(claim.normalized, chunk_normalized)
    evidence_numbers = tuple(_extract_numbers(chunk.text))
    numeric_overlap = _numeric_overlap_score(claim.claim_numbers, evidence_numbers)
    contextual_numeric = _contextual_numeric_overlap(
        claim.claim_numbers,
        evidence_numbers,
        claim_overlap,
    )
    section_weight = _section_weight(chunk.section)
    section_bonus = _section_bonus(chunk.section)

    relevance_score = _clamp(
        PHRASE_SIGNAL_WEIGHT * phrase_overlap
        + CLAIM_OVERLAP_WEIGHT * claim_overlap
        + NUMERIC_WEIGHT * contextual_numeric
        + SECTION_SIGNAL_WEIGHT * section_weight
        + section_bonus
    )

    return EvidenceItem(
        chunk_id=chunk.chunk_id,
        section=chunk.section or "Unknown",
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        relevance_score=relevance_score,
        claim_overlap=_clamp(claim_overlap),
        numeric_overlap=_clamp(numeric_overlap),
        claim_numbers=list(claim.claim_numbers),
        evidence_numbers=list(evidence_numbers),
        source_url=chunk.source_url,
        page=chunk.page,
    )


def _enhanced_claim_overlap(
    claim: ProcessedClaim,
    chunk_normalized: str,
    chunk_tokens: set[str],
) -> float:
    general = _claim_overlap_score(set(claim.tokens), chunk_tokens)
    important = _important_token_overlap(claim, chunk_tokens)
    phrase = _claim_phrase_overlap(claim.normalized, chunk_normalized)
    return _clamp(0.40 * general + 0.35 * important + 0.25 * phrase)


def _important_token_overlap(claim: ProcessedClaim, chunk_tokens: set[str]) -> float:
    important_tokens = _important_claim_tokens(claim)
    if not important_tokens:
        return 0.0
    overlap = important_tokens.intersection(chunk_tokens)
    return len(overlap) / len(important_tokens)


def _important_claim_tokens(claim: ProcessedClaim) -> set[str]:
    return {
        token
        for token in claim.tokens
        if len(token) >= 4 or "-" in token or any(char.isdigit() for char in token)
    }


def _claim_phrase_overlap(claim_normalized: str, chunk_normalized: str) -> float:
    words = claim_normalized.split()
    phrases: list[str] = []
    for size in (3, 2):
        if len(words) < size:
            continue
        for index in range(len(words) - size + 1):
            segment = words[index : index + size]
            if all(word in STOPWORDS for word in segment):
                continue
            phrases.append(" ".join(segment))

    if not phrases:
        return 0.0

    matches = sum(1 for phrase in phrases if phrase in chunk_normalized)
    return matches / len(phrases)


def _claim_overlap_score(claim_tokens: set[str], chunk_tokens: set[str]) -> float:
    if not claim_tokens:
        return 0.0
    overlap = claim_tokens.intersection(chunk_tokens)
    return len(overlap) / len(claim_tokens)


def _phrase_overlap_score(claim_normalized: str, chunk_normalized: str) -> float:
    claim_words = claim_normalized.split()
    if len(claim_words) < 2:
        return 0.0

    best = 0.0
    for size in (3, 2):
        if len(claim_words) < size:
            continue
        for index in range(len(claim_words) - size + 1):
            phrase = " ".join(claim_words[index : index + size])
            if phrase and phrase in chunk_normalized:
                best = max(best, size / len(claim_words))
    return _clamp(best)


def _numeric_overlap_score(
    claim_numbers: tuple[str, ...],
    evidence_numbers: tuple[str, ...],
) -> float:
    if not claim_numbers:
        return 1.0
    if not evidence_numbers:
        return 0.0

    claim_set = set(claim_numbers)
    evidence_set = set(evidence_numbers)
    if claim_set.intersection(evidence_set):
        return 1.0

    return 0.5


def _contextual_numeric_overlap(
    claim_numbers: tuple[str, ...],
    evidence_numbers: tuple[str, ...],
    claim_overlap: float,
) -> float:
    base = _numeric_overlap_score(claim_numbers, evidence_numbers)
    if base == 0.0:
        return 0.0
    if not claim_numbers:
        return base

    relevance_factor = min(1.0, 0.45 + claim_overlap)
    if base == 1.0:
        return base * relevance_factor
    return base * min(1.0, 0.35 + claim_overlap)


def _section_weight(section: str | None) -> float:
    if not section:
        return DEFAULT_SECTION_WEIGHT
    return SECTION_WEIGHTS.get(section.strip().lower(), DEFAULT_SECTION_WEIGHT)


def _section_bonus(section: str | None) -> float:
    if not section:
        return 0.0

    normalized = section.strip().lower()
    if _FIGURE_SECTION_PATTERN.match(normalized):
        return -0.02

    for key, bonus in SECTION_BONUSES.items():
        if normalized == key or normalized.startswith(f"{key} "):
            return bonus

    return 0.0


def _tokenize(normalized_text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in normalized_text.split():
        token = raw_token.strip(".")
        if len(token) < 2 or token in STOPWORDS or token.isdigit():
            continue
        tokens.append(token)
    return tokens


def dedupe_evidence_items(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """Remove duplicate evidence by normalized text, keeping the highest relevance score."""
    best_by_text: dict[str, EvidenceItem] = {}
    for item in items:
        key = normalize_evidence_text(item.text)
        if not key:
            continue
        existing = best_by_text.get(key)
        if existing is None or item.relevance_score > existing.relevance_score:
            best_by_text[key] = item

    deduped: list[EvidenceItem] = []
    seen_keys: set[str] = set()
    for item in items:
        key = normalize_evidence_text(item.text)
        if not key or key in seen_keys:
            continue
        if best_by_text.get(key) is item:
            deduped.append(item)
            seen_keys.add(key)
    return deduped


def select_diverse_evidence(
    items: list[EvidenceItem],
    max_items: int,
) -> list[EvidenceItem]:
    """Select a bounded, diverse evidence set from ranked candidates."""
    if max_items <= 0:
        return []

    selected: list[EvidenceItem] = []
    section_counts: dict[str, int] = {}

    for item in items:
        if len(selected) >= max_items:
            break
        if _is_near_duplicate(item, selected):
            continue
        section_key = item.section.strip().lower()
        if section_counts.get(section_key, 0) >= EVIDENCE_MAX_PER_SECTION:
            continue
        selected.append(item)
        section_counts[section_key] = section_counts.get(section_key, 0) + 1

    if len(selected) < max_items:
        for item in items:
            if len(selected) >= max_items:
                break
            if item in selected or _is_near_duplicate(item, selected):
                continue
            selected.append(item)

    return selected


def _is_near_duplicate(item: EvidenceItem, selected: list[EvidenceItem]) -> bool:
    item_key = normalize_evidence_text(item.text)
    item_tokens = set(item_key.split())
    if not item_key:
        return True

    for other in selected:
        other_key = normalize_evidence_text(other.text)
        if item_key == other_key:
            return True
        other_tokens = set(other_key.split())
        if not item_tokens or not other_tokens:
            continue
        overlap = len(item_tokens.intersection(other_tokens))
        union = len(item_tokens.union(other_tokens))
        if union and (overlap / union) >= EVIDENCE_DIVERSITY_THRESHOLD:
            return True
    return False


def _dedupe_chunks(chunks: list[EvidenceChunk]) -> list[EvidenceChunk]:
    seen_ids: set[str] = set()
    deduped: list[EvidenceChunk] = []
    for chunk in chunks:
        if chunk.chunk_id in seen_ids:
            continue
        seen_ids.add(chunk.chunk_id)
        deduped.append(chunk)
    return deduped


def _clamp(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return round(value, 4)
