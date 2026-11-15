from __future__ import annotations

from app.schemas.evidence import EvidenceItem
from app.schemas.verification import (
    AdjudicatorAnalysis,
    DefenderAnalysis,
    ProsecutorAnalysis,
)


def available_chunk_ids(evidence: list[EvidenceItem]) -> set[str]:
    return {item.chunk_id for item in evidence}


def filter_valid_chunk_ids(
    chunk_ids: list[str],
    valid_ids: set[str],
) -> list[str]:
    return [chunk_id for chunk_id in chunk_ids if chunk_id in valid_ids]


def sanitize_prosecutor_analysis(
    analysis: ProsecutorAnalysis,
    valid_ids: set[str],
) -> ProsecutorAnalysis:
    return analysis.model_copy(
        update={
            "supporting_evidence": filter_valid_chunk_ids(
                analysis.supporting_evidence,
                valid_ids,
            ),
            "contradicting_evidence": filter_valid_chunk_ids(
                analysis.contradicting_evidence,
                valid_ids,
            ),
        }
    )


def sanitize_defender_analysis(
    analysis: DefenderAnalysis,
    valid_ids: set[str],
) -> DefenderAnalysis:
    return analysis.model_copy(
        update={
            "supporting_evidence": filter_valid_chunk_ids(
                analysis.supporting_evidence,
                valid_ids,
            ),
            "contradicting_evidence": filter_valid_chunk_ids(
                analysis.contradicting_evidence,
                valid_ids,
            ),
        }
    )


def sanitize_adjudicator_analysis(
    analysis: AdjudicatorAnalysis,
    valid_ids: set[str],
) -> AdjudicatorAnalysis:
    return analysis.model_copy(
        update={
            "supporting_evidence": filter_valid_chunk_ids(
                analysis.supporting_evidence,
                valid_ids,
            ),
            "contradicting_evidence": filter_valid_chunk_ids(
                analysis.contradicting_evidence,
                valid_ids,
            ),
        }
    )


def format_evidence_for_prompt(evidence: list[EvidenceItem]) -> str:
    payload = [
        {
            "chunk_id": item.chunk_id,
            "section": item.section,
            "text": item.text,
        }
        for item in evidence
    ]
    import json

    return json.dumps(payload, indent=2)
