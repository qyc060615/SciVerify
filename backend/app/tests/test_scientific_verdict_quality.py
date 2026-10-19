"""Offline contract tests. Fixture LLM outputs are labels, not semantic model evals."""
import json
from pathlib import Path

import pytest

from app.researchguard.adapters.sciverify import evidence_to_legacy, map_sciverify_verdict
from app.researchguard.domain import EvidenceChunk, ProcessingStatus
from app.schemas.evidence import EvidenceItem, EvidencePaperSummary, EvidenceRetrievalResponse
from app.schemas.verification import AdjudicatorAnalysis, DefenderAnalysis, ProsecutorAnalysis, Verdict, VerificationResponse
from app.services.verification_service import _verify_evidence
from app.services.verification_validator import validate_verification_result
from app.tests.test_agents import MockLLMProvider
from app.utils.claim_preprocessor import preprocess_claim

FIXTURES = Path(__file__).parent / "fixtures"
CASES = json.loads((FIXTURES / "scientific_verdict_cases.json").read_text(encoding="utf-8"))["cases"]
REAL = json.loads((FIXTURES / "scientific_c3_ref4.json").read_text(encoding="utf-8"))


def item(text, chunk_id="c1", relevance=0.9, overlap=0.7):
    return EvidenceItem(chunk_id=chunk_id, section="Results", chunk_index=0, text=text,
                        relevance_score=relevance, claim_overlap=overlap, numeric_overlap=0)


def analyses(verdict, text, reason="", *, ids=None, confidence=0.98):
    ids = ["c1"] if ids is None else ids
    positive = ids if verdict in {"SUPPORTS", "OVERSTATED"} else []
    negative = ids if verdict in {"CONTRADICTS", "FABRICATED"} else []
    return (
        ProsecutorAnalysis(analysis=reason, stance="neutral", confidence=0.4,
                           contradicting_evidence=negative),
        DefenderAnalysis(analysis=reason, stance="neutral", confidence=0.4,
                         supporting_evidence=positive),
        AdjudicatorAnalysis(analysis=reason, verdict=verdict, confidence=confidence,
            reasoning=f'{reason} Source says: "{text}"' if text else reason,
            supporting_evidence=positive, contradicting_evidence=negative,
            suggested_correction="Restrict the claim to the source's measured scope." if verdict == "OVERSTATED" else None),
    )


def validate(evidence, agents, claim="Scientific claim."):
    return validate_verification_result(claim=claim, evidence=evidence,
        prosecutor=agents[0], defender=agents[1], adjudicator=agents[2])


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_labeled_scientific_cases_preserve_evidence_contract(case):
    # The fake provider supplies the human label. This checks that guards/mapping
    # preserve evidence-backed labels, not that an LLM independently predicts them.
    evidence = [item(case["text"])] if case["text"] else []
    agents = analyses(case["expected"], case["text"], case["reason"])
    response = EvidenceRetrievalResponse(status="success" if evidence else "no_relevant_evidence",
        claim=case["claim"], paper=EvidencePaperSummary(paper_id="fixture"), evidence=evidence)
    result = _verify_evidence(case["claim"], response, llm=MockLLMProvider(list(agents)))
    assert result.verdict.value == case["expected"]
    assert 0 <= result.confidence <= 1
    assert VerificationResponse.model_validate_json(result.model_dump_json()) == result
    expected_domain = {"SUPPORTS": "SUPPORTED", "CONTRADICTS": "CONTRADICTED"}.get(case["expected"], case["expected"])
    assert map_sciverify_verdict(result.verdict, processing_status=ProcessingStatus.COMPLETED).value == expected_domain


def real_inputs():
    original = REAL["original_verification"]
    chunks = [EvidenceChunk.model_validate(c) for c in original["evidence_chunks"]]
    evidence = evidence_to_legacy(chunks, preprocess_claim(REAL["claim"]["text"]))
    provenance = original["traceability"]["metadata"]["legacy_provenance"]
    agents = (ProsecutorAnalysis.model_validate(provenance["prosecutor"]),
              DefenderAnalysis.model_validate(provenance["defender"]),
              AdjudicatorAnalysis.model_validate(provenance["adjudicator"]))
    return evidence, agents


def test_real_historical_agents_replayed_without_new_llm():
    evidence, agents = real_inputs()
    result = validate(evidence, agents, REAL["claim"]["text"])
    assert result.original_verdict == Verdict.CONTRADICTS
    assert result.original_confidence == REAL["original_verification"]["confidence"] == 0.98
    assert result.verdict == Verdict.INSUFFICIENT
    assert result.confidence <= 0.5
    assert result.validation_warnings
    # It is unsafe to manufacture SUPPORTS from historically incorrect agent output.


def test_reconstructed_real_case_with_human_labeled_support():
    evidence, _ = real_inputs()
    source = evidence[0]
    agents = analyses("SUPPORTS", source.text,
        "The cited phase 1 report is prior work relative to the manuscript; its Results and Methods report BNT162b2 outcomes.", ids=[source.chunk_id, evidence[1].chunk_id])
    result = validate(evidence, agents, REAL["claim"]["text"])
    assert result.verdict == Verdict.SUPPORTS


@pytest.mark.parametrize("fault", ["prosecutor_only", "id_only", "foreign_quote", "foreign_id", "weak_cited", "no_evidence"])
def test_unsupported_negative_cannot_use_ids_stance_or_unrelated_strong_chunks(fault):
    text = "The same trial found no significant survival benefit."
    agents = list(analyses("CONTRADICTS", text, "The claim asserts a significant survival benefit."))
    evidence = [item(text)]
    if fault == "prosecutor_only":
        agents[2] = agents[2].model_copy(update={"contradicting_evidence": []})
    elif fault == "id_only":
        agents[2] = agents[2].model_copy(update={"reasoning": "Possibly incorrect; the prosecutor objects."})
    elif fault == "foreign_quote":
        agents[2] = agents[2].model_copy(update={"reasoning": 'Source says "A fabricated source quote that is absent."'})
    elif fault == "foreign_id":
        agents[2] = agents[2].model_copy(update={"contradicting_evidence": ["ghost"]})
    elif fault == "weak_cited":
        evidence = [item(text, relevance=0.05, overlap=0.04), item("Unrelated high scoring text.", "other")]
    else:
        evidence = []
    result = validate(evidence, agents)
    assert result.verdict == Verdict.INSUFFICIENT
    assert result.confidence <= 0.5


def test_support_requires_own_valid_evidence():
    agents = list(analyses("SUPPORTS", "The intervention reduced mortality."))
    agents[2] = agents[2].model_copy(update={"supporting_evidence": ["ghost"]})
    assert validate([item("The intervention reduced mortality.")], agents).verdict == Verdict.INSUFFICIENT


def test_semantic_paraphrase_not_rejected_by_low_lexical_overlap():
    evidence = [item("The intervention reduced mortality.", overlap=0.01)]
    result = validate(evidence, analyses("SUPPORTS", evidence[0].text, "Lower death rates means reduced mortality."))
    assert result.verdict == Verdict.SUPPORTS


def test_disagreement_is_not_itself_counterevidence():
    text = "Vaccine efficacy was 94.8%."
    agents = list(analyses("SUPPORTS", text, "Approximately 95% is reasonable rounding."))
    agents[0] = agents[0].model_copy(update={"stance": "challenge", "confidence": 0.95, "contradicting_evidence": ["c1"]})
    agents[1] = agents[1].model_copy(update={"stance": "support", "confidence": 0.95})
    result = validate([item(text)], agents, "Efficacy was approximately 95%.")
    assert result.verdict == Verdict.SUPPORTS
    assert result.agent_agreement is False


def test_grounded_clear_contradiction_can_retain_high_confidence():
    text = "The model was evaluated on three datasets."
    result = validate([item(text), item(text, "c2")],
        analyses("CONTRADICTS", text, "The same evaluation used three, not twenty datasets.", ids=["c1", "c2"]))
    assert result.verdict == Verdict.CONTRADICTS
    assert result.confidence >= 0.9


@pytest.mark.parametrize("verdict", ["FABRICATED", "OVERSTATED", "SUPPORTS", "CONTRADICTS"])
def test_absence_never_establishes_a_categorical_judgment(verdict):
    assert validate([], analyses(verdict, "", ids=[])).verdict == Verdict.INSUFFICIENT


@pytest.mark.anyio
async def test_builtin_m4_verifier_receives_context_without_changing_claim_or_evidence():
    from app.tests.test_manuscript_verification import inputs, FakeRetriever
    from app.tests.test_paperqa2_integration import paper as paper_fixture
    from app.services.manuscript_verification import verify_manuscript_core
    # Invoke the fixture's underlying constructor, without I/O or remote providers.
    paper = paper_fixture.__wrapped__()
    parsed, extraction = inputs()
    class RecordingLLM(MockLLMProvider):
        def generate(self, prompt, **kwargs):
            assert parsed.paragraphs[0].text in prompt
            assert parsed.manuscript.title is None
            assert '"manuscript_title": null' in prompt
            assert "Manuscript context" in prompt
            return super().generate(prompt, **kwargs)
    llm = RecordingLLM(list(analyses("INSUFFICIENT", "", "The selected excerpt does not settle the claim.", ids=[])))
    result = await verify_manuscript_core(parsed, extraction, source_retriever=lambda doi: paper,
        evidence_retriever_factory=lambda chunks: FakeRetriever(chunks, []), llm=llm)
    assert result.coverage.completed == 1
    assert len(llm.prompts) == 3
    assert result.extraction.claims[0].text == extraction.claims[0].text
    assert result.pairs[0].verification.verdict.value == "INSUFFICIENT"


def test_replayed_response_explains_withdrawn_judgment_and_keeps_raw_agents():
    evidence, agents = real_inputs()
    response = EvidenceRetrievalResponse(status="success", claim=REAL["claim"]["text"],
        paper=EvidencePaperSummary(paper_id="historical-source"), evidence=evidence)
    result = _verify_evidence(response.claim, response, llm=MockLLMProvider(list(agents)))
    assert result.verdict == Verdict.INSUFFICIENT
    assert "changed CONTRADICTS to INSUFFICIENT" in result.summary
    assert "not accepted as the final judgment" in result.reasoning
    assert result.adjudicator == agents[2]
    assert result.suggested_correction is None
