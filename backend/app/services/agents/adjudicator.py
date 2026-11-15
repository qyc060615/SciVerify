from __future__ import annotations

from app.services.agents.scientific_policy import SCIENTIFIC_VERDICT_POLICY
from app.schemas.evidence import EvidenceItem
from app.schemas.verification import (
    AdjudicatorAnalysis,
    DefenderAnalysis,
    ProsecutorAnalysis,
)
from app.services.evidence_validation import (
    format_evidence_for_prompt,
    sanitize_adjudicator_analysis,
)
from app.services.llm.provider import LLMProvider, LLMResponseError

ADJUDICATOR_SYSTEM_PROMPT = """You are the Adjudicator agent in a scientific claim verification system.
Evaluate the original claim, retrieved evidence, Prosecutor analysis, and Defender analysis.
Consider both sides rather than simply selecting whichever agent sounds more confident.
Use ONLY the supplied evidence chunks when referencing evidence.
Do not invent papers, quotes, numbers, citations, or experimental results.
Reference evidence only by chunk_id from the supplied list.
Choose exactly one verdict from: SUPPORTS, OVERSTATED, CONTRADICTS, INSUFFICIENT, FABRICATED.
Do not use FABRICATED simply because evidence retrieval failed.
Return JSON matching the requested schema exactly.""" + "\n\n" + SCIENTIFIC_VERDICT_POLICY


def run_adjudicator(
    claim: str,
    evidence: list[EvidenceItem],
    prosecutor: ProsecutorAnalysis,
    defender: DefenderAnalysis,
    llm: LLMProvider,
) -> AdjudicatorAnalysis:
    prompt = f"""
Role: Adjudicator

Claim:
{claim}

Evidence chunks (use only these chunk_id values):
{format_evidence_for_prompt(evidence)}

Prosecutor analysis:
{prosecutor.model_dump_json()}

Defender analysis:
{defender.model_dump_json()}

Instructions:
Evaluate both analyses and produce the final verdict.
Verdict must be one of: SUPPORTS, OVERSTATED, CONTRADICTS, INSUFFICIENT, FABRICATED.

Return JSON with fields:
- agent
- analysis
- verdict
- confidence (number between 0 and 1)
- reasoning
- supporting_evidence (array of chunk_id strings)
- contradicting_evidence (array of chunk_id strings)
- suggested_correction (string or null)
""".strip()

    result = llm.generate(
        prompt,
        system=ADJUDICATOR_SYSTEM_PROMPT,
        response_model=AdjudicatorAnalysis,
    )
    if not isinstance(result, AdjudicatorAnalysis):
        raise LLMResponseError("Adjudicator returned unexpected response type.")

    valid_ids = {item.chunk_id for item in evidence}
    return sanitize_adjudicator_analysis(result, valid_ids)
