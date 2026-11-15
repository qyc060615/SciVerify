from __future__ import annotations

import logging
from app.schemas.evidence import EvidenceItem
from app.schemas.verification import (
    AdjudicatorAnalysis,
    ClaimSegmentStatus,
    ClaimSegmentTrace,
    ClaimTraceability,
    ProsecutorAnalysis,
    Verdict,
)
from app.utils.claim_preprocessor import (
    STOPWORDS,
    ProcessedClaim,
    _extract_numbers,
    _normalize_claim_text,
    preprocess_claim,
)
from app.utils.claim_segmenter import segment_claim

import re

logger = logging.getLogger(__name__)

SUPPORTED_THRESHOLD = 0.65
PARTIAL_THRESHOLD = 0.35
EVIDENCE_LINK_THRESHOLD = 0.25
CONTRADICTION_MATCH_THRESHOLD = 0.40


def build_claim_traceability(
    claim: str,
    evidence: list[EvidenceItem],
    *,
    verdict: Verdict | None,
    adjudicator: AdjudicatorAnalysis | None = None,
    prosecutor: ProsecutorAnalysis | None = None,
) -> ClaimTraceability | None:
    """Build deterministic claim-to-evidence traceability metadata."""
    segment_texts = segment_claim(claim)
    if not segment_texts:
        return None

    contradicting_ids = _collect_contradicting_ids(adjudicator, prosecutor)
    segments: list[ClaimSegmentTrace] = []

    for index, segment_text in enumerate(segment_texts, start=1):
        segment = _safe_preprocess_segment(segment_text)
        scored_evidence = _score_segment_evidence(segment, evidence)
        coverage_score, linked_ids = _compute_segment_coverage(
            segment,
            scored_evidence,
            evidence,
        )
        status = _determine_segment_status(
            coverage_score=coverage_score,
            linked_ids=linked_ids,
            contradicting_ids=contradicting_ids,
            scored_evidence=scored_evidence,
        )
        segments.append(
            ClaimSegmentTrace(
                id=f"segment_{index}",
                text=segment_text,
                status=status,
                coverage_score=_clamp(coverage_score),
                evidence_ids=linked_ids,
            )
        )

    overall_coverage = _clamp(
        sum(segment.coverage_score for segment in segments) / len(segments)
    )
    warnings = _build_traceability_warnings(segments, verdict)

    logger.info(
        "Claim traceability: segments=%s overall_coverage=%s warnings=%s",
        len(segments),
        overall_coverage,
        len(warnings),
    )

    return ClaimTraceability(
        segments=segments,
        overall_coverage=overall_coverage,
        warnings=warnings,
    )


def _safe_preprocess_segment(segment_text: str) -> ProcessedClaim:
    try:
        return preprocess_claim(segment_text)
    except Exception:
        normalized = _normalize_claim_text(segment_text)
        return ProcessedClaim(
            original=segment_text,
            normalized=normalized,
            tokens=tuple(_extract_segment_tokens(normalized)),
            claim_numbers=tuple(_extract_numbers(segment_text)),
        )


def _extract_segment_tokens(normalized_text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in normalized_text.split():
        token = raw_token.strip(".,;:()")
        if len(token) < 2 or token in STOPWORDS or token.isdigit():
            continue
        tokens.append(token)
    return tokens


def _score_segment_evidence(
    segment: ProcessedClaim,
    evidence: list[EvidenceItem],
) -> list[tuple[str, float]]:
    scored: list[tuple[str, float]] = []
    for item in evidence:
        score = _segment_match_score(segment, item)
        if score > 0:
            scored.append((item.chunk_id, score))

    scored.sort(key=lambda entry: entry[1], reverse=True)
    return scored


def _segment_match_score(segment: ProcessedClaim, evidence: EvidenceItem) -> float:
    chunk_normalized = _normalize_claim_text(evidence.text)
    chunk_tokens = set(_extract_segment_tokens(chunk_normalized))
    segment_tokens = set(segment.tokens)

    lexical = _token_overlap(segment_tokens, chunk_tokens)
    phrase = _phrase_overlap(segment.normalized, chunk_normalized)
    numeric = _segment_numeric_overlap(segment.claim_numbers, evidence)
    metadata = 0.35 * evidence.claim_overlap + 0.15 * evidence.relevance_score

    if segment_tokens:
        segment_specific = 0.30 * lexical + 0.20 * phrase + 0.10 * numeric
    else:
        segment_specific = 0.20 * phrase + 0.10 * numeric

    return _clamp(segment_specific + metadata)


def _compute_segment_coverage(
    segment: ProcessedClaim,
    scored_evidence: list[tuple[str, float]],
    evidence: list[EvidenceItem],
) -> tuple[float, list[str]]:
    """Compute segment coverage score and linked chunk IDs.

    Evaluates both the top matching chunk and multi-chunk aggregate coverage
    across all linked chunks so that evidence spanning multiple sections
    of a paper is not artificially penalized by single-chunk boundaries.
    """
    if not scored_evidence:
        return 0.0, []

    linked_ids = [
        chunk_id
        for chunk_id, score in scored_evidence
        if score >= EVIDENCE_LINK_THRESHOLD
    ]
    top_score = scored_evidence[0][1]

    if not linked_ids:
        return _clamp(top_score), []

    if len(linked_ids) == 1:
        return _clamp(top_score), linked_ids

    linked_items = [ev for ev in evidence if ev.chunk_id in linked_ids]
    segment_tokens = set(segment.tokens)

    all_chunk_tokens: set[str] = set()
    for ev in linked_items:
        all_chunk_tokens.update(
            _extract_segment_tokens(_normalize_claim_text(ev.text))
        )

    union_token_overlap = (
        len(segment_tokens.intersection(all_chunk_tokens)) / len(segment_tokens)
        if segment_tokens
        else 0.0
    )

    numeric_matched = False
    if segment.claim_numbers:
        for ev in linked_items:
            if _segment_numeric_overlap(segment.claim_numbers, ev) >= 0.8:
                numeric_matched = True
                break

    multi_chunk_score = 0.50 * top_score + 0.35 * union_token_overlap
    if numeric_matched:
        multi_chunk_score += 0.10
    if len(linked_ids) >= 3:
        multi_chunk_score += 0.05

    final_score = _clamp(max(top_score, multi_chunk_score))
    return final_score, linked_ids


def _stem_token(token: str) -> str:
    """Strip common English inflection suffixes for robust morphological matching."""
    t = token.lower().strip(".,;:()")
    if len(t) <= 3:
        return t
    for suffix in ("tion", "sion", "ment", "ing", "ies", "ied", "ed", "es", "s", "ive", "able"):
        if t.endswith(suffix) and len(t) - len(suffix) >= 3:
            return t[: -len(suffix)]
    return t


def _token_overlap(segment_tokens: set[str], chunk_tokens: set[str]) -> float:
    if not segment_tokens:
        return 0.0

    chunk_stems = {_stem_token(t) for t in chunk_tokens}
    overlap_count = 0
    for token in segment_tokens:
        if token in chunk_tokens or _stem_token(token) in chunk_stems:
            overlap_count += 1

    return overlap_count / len(segment_tokens)


def _phrase_overlap(segment_normalized: str, chunk_normalized: str) -> float:
    """Calculate phrase overlap between segment and evidence chunk.

    Combines contiguous n-gram matching with content-word skip bigrams to
    gracefully handle parenthetical qualifiers (e.g. 95% CI), minor preposition
    variations, morphological inflections, and hedges without losing semantic specificity.
    """
    words = segment_normalized.split()
    if len(words) < 2:
        return (
            1.0
            if segment_normalized and segment_normalized in chunk_normalized
            else 0.0
        )

    raw_matches = 0
    raw_total = 0
    for size in (3, 2):
        if len(words) < size:
            continue
        for index in range(len(words) - size + 1):
            phrase = " ".join(words[index : index + size])
            if all(word in STOPWORDS for word in phrase.split()):
                continue
            raw_total += 1
            if phrase in chunk_normalized:
                raw_matches += 1

    raw_score = (raw_matches / raw_total) if raw_total > 0 else 0.0

    content_words = _extract_segment_tokens(segment_normalized)
    cw_matches = 0
    cw_total = 0
    if len(content_words) >= 2:
        for index in range(len(content_words) - 1):
            cw_total += 1
            w1, w2 = content_words[index], content_words[index + 1]
            stem1 = _stem_token(w1)
            stem2 = _stem_token(w2)
            pattern = re.compile(
                rf"\b(?:{re.escape(w1)}|{re.escape(stem1)}\w*)\b(?:\s+\S+){{0,5}}\s+\b(?:{re.escape(w2)}|{re.escape(stem2)}\w*)\b",
                re.IGNORECASE,
            )
            if pattern.search(chunk_normalized):
                cw_matches += 1

    cw_score = (cw_matches / cw_total) if cw_total > 0 else 0.0

    return max(raw_score, cw_score, 0.5 * raw_score + 0.5 * cw_score)


def _segment_numeric_overlap(
    segment_numbers: tuple[str, ...],
    evidence: EvidenceItem,
) -> float:
    if not segment_numbers:
        return 0.0
    if not evidence.evidence_numbers:
        return 0.0

    segment_set = set(segment_numbers)
    evidence_set = set(evidence.evidence_numbers)
    if segment_set.intersection(evidence_set):
        return 1.0
    return evidence.numeric_overlap


def _determine_segment_status(
    *,
    coverage_score: float,
    linked_ids: list[str],
    contradicting_ids: set[str],
    scored_evidence: list[tuple[str, float]],
) -> ClaimSegmentStatus:
    contradiction_scores = [
        score
        for chunk_id, score in scored_evidence
        if chunk_id in contradicting_ids and score >= CONTRADICTION_MATCH_THRESHOLD
    ]
    if contradiction_scores:
        return ClaimSegmentStatus.CONTRADICTED

    if coverage_score >= SUPPORTED_THRESHOLD and linked_ids:
        return ClaimSegmentStatus.SUPPORTED
    if coverage_score >= PARTIAL_THRESHOLD or linked_ids:
        return ClaimSegmentStatus.PARTIALLY_SUPPORTED
    return ClaimSegmentStatus.UNSUPPORTED


def _collect_contradicting_ids(
    adjudicator: AdjudicatorAnalysis | None,
    prosecutor: ProsecutorAnalysis | None,  # noqa: ARG001  # kept for API compat
) -> set[str]:
    """Return chunk IDs that definitively contradict the claim.

    Only the Adjudicator's ``contradicting_evidence`` is used here.  The
    Prosecutor's list is intentionally adversarial — it always challenges the
    claim — so including it would mark segments as CONTRADICTED even when the
    final verdict is SUPPORTS.  The Adjudicator makes the authoritative call on
    which evidence genuinely contradicts the claim.
    """
    ids: set[str] = set()
    if adjudicator:
        ids.update(adjudicator.contradicting_evidence)
    # Deliberately NOT including prosecutor.contradicting_evidence here.
    # Prosecutors challenge by design; their evidence references are not
    # definitive contradictions and must not override the final verdict.
    return ids


def _build_traceability_warnings(
    segments: list[ClaimSegmentTrace],
    verdict: Verdict | None,
) -> list[str]:
    warnings: list[str] = []
    unsupported = [segment for segment in segments if segment.status == ClaimSegmentStatus.UNSUPPORTED]
    partial = [
        segment for segment in segments if segment.status == ClaimSegmentStatus.PARTIALLY_SUPPORTED
    ]
    contradicted = [
        segment for segment in segments if segment.status == ClaimSegmentStatus.CONTRADICTED
    ]

    if unsupported:
        warnings.append("No retrieved evidence directly supports this claim segment.")

    if partial:
        warnings.append("Part of the claim has limited evidence coverage.")

    if verdict == Verdict.SUPPORTS and (unsupported or partial):
        warnings.append("The claim contains a segment that is not directly supported.")

    if verdict == Verdict.OVERSTATED and unsupported:
        warnings.append(
            "Evidence supports the general mechanism but not the full specificity of the claim."
        )

    if verdict == Verdict.CONTRADICTS and contradicted:
        warnings.append("A claim segment is linked to contradicting evidence.")

    if verdict == Verdict.INSUFFICIENT and (unsupported or not segments):
        warnings.append("Evidence coverage is insufficient for one or more claim segments.")

    if verdict == Verdict.FABRICATED and not any(
        segment.status == ClaimSegmentStatus.SUPPORTED for segment in segments
    ):
        warnings.append("The claim lacks adequate supporting evidence in the cited paper.")

    deduped: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning not in seen:
            seen.add(warning)
            deduped.append(warning)
    return deduped


def _clamp(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return round(value, 4)


__all__ = ["build_claim_traceability"]
