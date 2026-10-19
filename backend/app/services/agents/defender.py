from __future__ import annotations

from app.services.agents.scientific_policy import SCIENTIFIC_VERDICT_POLICY
from app.schemas.evidence import EvidenceItem
from app.schemas.verification import DefenderAnalysis
from app.services.evidence_validation import (
    format_evidence_for_prompt,
    sanitize_defender_analysis,
)
from app.services.llm.provider import LLMProvider, LLMResponseError

DEFENDER_SYSTEM_PROMPT = """You are the Defender agent in a scientific claim verification system.
Your job is to build the strongest evidence-based case that the claim is supported by the cited paper.
Use ONLY the supplied evidence chunks.
Do not invent papers, quotes, numbers, citations, or experimental results.
Reference evidence only by chunk_id from the supplied list.
Return JSON matching the requested schema exactly.""" + "\n\n" + SCIENTIFIC_VERDICT_POLICY


def run_defender(
    claim: str,
    evidence: list[EvidenceItem],
    llm: LLMProvider,
) -> DefenderAnalysis:
    prompt = _build_agent_prompt(
        role="Defender",
        claim=claim,
        evidence=evidence,
        instructions=(
            "Build the strongest evidence-based case that the claim is supported. Focus on direct "
            "supporting meaning, reasonable numerical rounding, relevant Results/Methods evidence, "
            "experimental findings, and appropriate context."
        ),
    )
    result = llm.generate(
        prompt,
        system=DEFENDER_SYSTEM_PROMPT,
        response_model=DefenderAnalysis,
    )
    if not isinstance(result, DefenderAnalysis):
        raise LLMResponseError("Defender returned unexpected response type.")

    valid_ids = {item.chunk_id for item in evidence}
    return sanitize_defender_analysis(result, valid_ids)


def _build_agent_prompt(
    *,
    role: str,
    claim: str,
    evidence: list[EvidenceItem],
    instructions: str,
) -> str:
    return f"""
Role: {role}

Claim:
{claim}

Instructions:
{instructions}

Evidence chunks (use only these chunk_id values):
{format_evidence_for_prompt(evidence)}

Return JSON with fields:
- agent
- analysis
- stance
- key_points
- supporting_evidence (array of chunk_id strings)
- contradicting_evidence (array of chunk_id strings)
- confidence (number between 0 and 1)
""".strip()
