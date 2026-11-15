from __future__ import annotations

import json
from pathlib import Path

from app.schemas.evidence import EvidenceItem, EvidencePaperSummary
from app.schemas.verification import (
    AdjudicatorAnalysis,
    ClaimSegmentStatus,
    ClaimSegmentTrace,
    ClaimTraceability,
    DefenderAnalysis,
    ProsecutorAnalysis,
    Verdict,
    VerificationResponse,
    VerificationStatus,
)

PAPER = EvidencePaperSummary(
    paper_id="10.1126/science.1225829",
    doi="10.1126/science.1225829",
    title="A programmable dual-RNA-guided DNA endonuclease in adaptive bacterial immunity",
)


def _evidence(
    chunk_id: str,
    text: str,
    *,
    relevance: float = 0.8,
    overlap: float = 0.75,
) -> EvidenceItem:
    return EvidenceItem(
        chunk_id=chunk_id,
        section="Results",
        chunk_index=0,
        text=text,
        relevance_score=relevance,
        claim_overlap=overlap,
        numeric_overlap=0.0,
    )


def _traceability(segments: list[tuple[str, ClaimSegmentStatus, float, list[str]]]) -> ClaimTraceability:
    return ClaimTraceability(
        segments=[
            ClaimSegmentTrace(
                id=segment_id,
                text=text,
                status=status,
                coverage_score=coverage,
                evidence_ids=evidence_ids,
            )
            for segment_id, text, status, coverage, evidence_ids in segments
        ],
        overall_coverage=sum(item[3] for item in segments) / len(segments),
        warnings=[],
    )


CASE_IDS = (
    "cas9_supports_001",
    "accuracy_overstated_001",
    "mortality_contradicts_001",
    "insufficient_evidence_001",
    "fabricated_claim_001",
    "numeric_supports_001",
    "universal_overstated_001",
    "weak_insufficient_001",
    "mechanism_supports_002",
    "direction_contradicts_002",
    "magnitude_overstated_002",
    "legacy_no_traceability_001",
    "conditional_supports_003",
    "dose_response_supports_003",
    "photosynthesis_supports_003",
    "conclusion_reversal_003",
    "opposite_direction_003",
    "safety_contradicts_003",
    "always_eliminates_003",
    "proves_guarantees_003",
    "compound_unsupported_detail_003",
    "multi_assertion_one_supported_003",
    "related_not_establishing_003",
    "tangential_topic_003",
    "unrelated_numbers_003",
    "weak_conditional_003",
    "not_in_paper_003",
    "invented_statistic_003",
    "no_evidence_present_003",
    "never_occurs_003",
)


def build_fixture(case_id: str) -> VerificationResponse:
    builders = {
        "cas9_supports_001": _cas9_supports,
        "accuracy_overstated_001": _accuracy_overstated,
        "mortality_contradicts_001": _mortality_contradicts,
        "insufficient_evidence_001": _insufficient_evidence,
        "fabricated_claim_001": _fabricated_claim,
        "numeric_supports_001": _numeric_supports,
        "universal_overstated_001": _universal_overstated,
        "weak_insufficient_001": _weak_insufficient,
        "mechanism_supports_002": _mechanism_supports,
        "direction_contradicts_002": _direction_contradicts,
        "magnitude_overstated_002": _magnitude_overstated,
        "legacy_no_traceability_001": _legacy_no_traceability,
        "conditional_supports_003": _conditional_supports,
        "dose_response_supports_003": _dose_response_supports,
        "photosynthesis_supports_003": _photosynthesis_supports,
        "conclusion_reversal_003": _conclusion_reversal,
        "opposite_direction_003": _opposite_direction,
        "safety_contradicts_003": _safety_contradicts,
        "always_eliminates_003": _always_eliminates,
        "proves_guarantees_003": _proves_guarantees,
        "compound_unsupported_detail_003": _compound_unsupported_detail,
        "multi_assertion_one_supported_003": _multi_assertion_one_supported,
        "related_not_establishing_003": _related_not_establishing,
        "tangential_topic_003": _tangential_topic,
        "unrelated_numbers_003": _unrelated_numbers,
        "weak_conditional_003": _weak_conditional,
        "not_in_paper_003": _not_in_paper,
        "invented_statistic_003": _invented_statistic,
        "no_evidence_present_003": _no_evidence_present,
        "never_occurs_003": _never_occurs,
    }
    return builders[case_id]()


def write_all_fixtures(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for case_id in CASE_IDS:
        response = build_fixture(case_id)
        path = output_dir / f"{case_id}.json"
        path.write_text(
            json.dumps(response.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )


def _cas9_supports() -> VerificationResponse:
    claim = (
        "Cas9 can be programmed with guide RNA to cleave specific "
        "double-stranded DNA target sequences."
    )
    evidence = [
        _evidence("c1", "Cas9 can be programmed with guide RNA in vitro.", relevance=0.91, overlap=0.88),
        _evidence("c2", "Cas9 cleaves specific double-stranded DNA target sequences.", relevance=0.89, overlap=0.86),
    ]
    return _success_response(
        claim,
        Verdict.SUPPORTS,
        0.86,
        evidence,
        traceability=_traceability(
            [
                (
                    "segment_1",
                    "Cas9 can be programmed with guide RNA",
                    ClaimSegmentStatus.SUPPORTED,
                    0.91,
                    ["c1"],
                ),
                (
                    "segment_2",
                    "to cleave specific double-stranded DNA target sequences",
                    ClaimSegmentStatus.SUPPORTED,
                    0.88,
                    ["c2"],
                ),
            ]
        ),
        agent_agreement=True,
    )


def _accuracy_overstated() -> VerificationResponse:
    claim = "DeepMind AlphaFold2 achieves 92.4% accuracy on protein structure prediction."
    evidence = [_evidence("c1", "AlphaFold2 achieved a median GDT-TS score of 92.4 in the CASP14 assessment.", relevance=0.82, overlap=0.74)]
    return _success_response(
        claim,
        Verdict.OVERSTATED,
        0.78,
        evidence,
        traceability=_traceability(
            [
                (
                    "segment_1",
                    claim,
                    ClaimSegmentStatus.PARTIALLY_SUPPORTED,
                    0.62,
                    ["c1"],
                )
            ]
        ),
        agent_agreement=False,
        adjudicator_verdict=Verdict.OVERSTATED,
    )


def _mortality_contradicts() -> VerificationResponse:
    claim = "The SPRINT trial shows that intensive blood pressure treatment reduces mortality."
    evidence = [_evidence("c1", "The SPRINT trial did not show a significant reduction in all-cause mortality.", relevance=0.84, overlap=0.8)]
    prosecutor = ProsecutorAnalysis(
        agent="prosecutor",
        analysis="Challenge",
        stance="skeptical",
        contradicting_evidence=["c1"],
        confidence=0.74,
    )
    return _success_response(
        claim,
        Verdict.CONTRADICTS,
        0.81,
        evidence,
        prosecutor=prosecutor,
        traceability=_traceability(
            [
                (
                    "segment_1",
                    claim,
                    ClaimSegmentStatus.CONTRADICTED,
                    0.79,
                    ["c1"],
                )
            ]
        ),
        agent_agreement=False,
        adjudicator_verdict=Verdict.CONTRADICTS,
    )


def _insufficient_evidence() -> VerificationResponse:
    return VerificationResponse(
        status=VerificationStatus.INSUFFICIENT_EVIDENCE,
        claim="The ENCODE project proves that 80% of the human genome is functional.",
        verdict=Verdict.INSUFFICIENT,
        confidence=0.0,
        summary="Insufficient evidence.",
        reasoning="Not enough evidence.",
        paper=PAPER,
        evidence=[],
        claim_traceability=_traceability(
            [
                (
                    "segment_1",
                    "The ENCODE project proves that 80% of the human genome is functional.",
                    ClaimSegmentStatus.UNSUPPORTED,
                    0.0,
                    [],
                )
            ]
        ),
    )


def _fabricated_claim() -> VerificationResponse:
    claim = "The original CRISPR-Cas9 paper demonstrated a 95% editing efficiency in human cells."
    return _success_response(
        claim,
        Verdict.FABRICATED,
        0.72,
        [],
        traceability=_traceability(
            [
                (
                    "segment_1",
                    claim,
                    ClaimSegmentStatus.UNSUPPORTED,
                    0.05,
                    [],
                )
            ]
        ),
        validation_warnings=["The claim lacks adequate supporting evidence in the cited paper. The efficiency statistic is not in the original paper."],
    )


def _numeric_supports() -> VerificationResponse:
    claim = "The AlphaFold2 model achieved a median Global Distance Test-TS (GDT-TS) score of 92.4."
    evidence = [
        _evidence(
            "c1",
            "AlphaFold2 achieved a median GDT-TS score of 92.4 in the CASP14 assessment.",
            relevance=0.9,
            overlap=0.88,
        )
    ]
    item = evidence[0].model_copy(update={"numeric_overlap": 1.0, "evidence_numbers": ["92.4"]})
    return _success_response(
        claim,
        Verdict.SUPPORTS,
        0.88,
        [item],
        traceability=_traceability(
            [
                (
                    "segment_1",
                    claim,
                    ClaimSegmentStatus.SUPPORTED,
                    0.9,
                    ["c1"],
                )
            ]
        ),
    )


def _universal_overstated() -> VerificationResponse:
    claim = "The SPRINT intensive blood pressure treatment improves survival across all patient subgroups."
    evidence = [_evidence("c1", "Survival improved in some predefined subgroups but not uniformly across all.", relevance=0.7, overlap=0.55)]
    return _success_response(
        claim,
        Verdict.OVERSTATED,
        0.76,
        evidence,
        traceability=_traceability(
            [
                (
                    "segment_1",
                    "The SPRINT intensive blood pressure treatment improves survival",
                    ClaimSegmentStatus.PARTIALLY_SUPPORTED,
                    0.58,
                    ["c1"],
                ),
                (
                    "segment_2",
                    "across all patient subgroups",
                    ClaimSegmentStatus.UNSUPPORTED,
                    0.12,
                    [],
                ),
            ]
        ),
    )


def _weak_insufficient() -> VerificationResponse:
    claim = "The CRISPR-Cas9 system fully eliminates off-target effects in every tested cell line."
    evidence = [_evidence("c1", "Off-target effects were observed in some cell lines.", relevance=0.22, overlap=0.18)]
    return _success_response(
        claim,
        Verdict.INSUFFICIENT,
        0.41,
        evidence,
        traceability=_traceability(
            [
                (
                    "segment_1",
                    claim,
                    ClaimSegmentStatus.UNSUPPORTED,
                    0.15,
                    [],
                )
            ]
        ),
        adjudicator_verdict=Verdict.INSUFFICIENT,
    )


def _mechanism_supports() -> VerificationResponse:
    claim = "RNA interference can silence target genes through sequence-specific mRNA degradation."
    evidence = [_evidence("c1", "RNA interference silences target genes through sequence-specific mRNA degradation.", relevance=0.87, overlap=0.84)]
    return _success_response(
        claim,
        Verdict.SUPPORTS,
        0.85,
        evidence,
        traceability=_traceability(
            [
                (
                    "segment_1",
                    claim,
                    ClaimSegmentStatus.SUPPORTED,
                    0.86,
                    ["c1"],
                )
            ]
        ),
    )


def _direction_contradicts() -> VerificationResponse:
    claim = "Expression of the p53 tumor suppressor gene increases under DNA damage conditions."
    evidence = [_evidence("c1", "p53 protein accumulates under DNA damage, but gene expression may not increase.", relevance=0.83, overlap=0.79)]
    return _success_response(
        claim,
        Verdict.CONTRADICTS,
        0.8,
        evidence,
        traceability=_traceability(
            [
                (
                    "segment_1",
                    claim,
                    ClaimSegmentStatus.CONTRADICTED,
                    0.77,
                    ["c1"],
                )
            ]
        ),
        adjudicator_verdict=Verdict.CONTRADICTS,
    )


def _magnitude_overstated() -> VerificationResponse:
    claim = "The ENCODE project identified biochemical functions for 80% of the human genome."
    evidence = [_evidence("c1", "The ENCODE project identified biochemical activity for many genomic regions, but the 80% figure was controversial.", relevance=0.8, overlap=0.7)]
    return _success_response(
        claim,
        Verdict.OVERSTATED,
        0.77,
        evidence,
        traceability=_traceability(
            [
                (
                    "segment_1",
                    claim,
                    ClaimSegmentStatus.PARTIALLY_SUPPORTED,
                    0.6,
                    ["c1"],
                )
            ]
        ),
    )


def _legacy_no_traceability() -> VerificationResponse:
    claim = "Improved sample preparation protocols enhanced reproducibility in mass spectrometry experiments."
    evidence = [_evidence("c1", "Improved sample preparation protocols enhanced reproducibility in mass spectrometry experiments.", relevance=0.8, overlap=0.78)]
    return _success_response(
        claim,
        Verdict.SUPPORTS,
        0.82,
        evidence,
        traceability=None,
        agent_agreement=None,
    )


def _success_response(
    claim: str,
    verdict: Verdict,
    confidence: float,
    evidence: list[EvidenceItem],
    *,
    traceability: ClaimTraceability | None,
    agent_agreement: bool | None = True,
    adjudicator_verdict: Verdict | None = None,
    prosecutor: ProsecutorAnalysis | None = None,
    validation_warnings: list[str] | None = None,
) -> VerificationResponse:
    final_verdict = verdict
    adjudicator = AdjudicatorAnalysis(
        agent="adjudicator",
        analysis="Benchmark adjudicator analysis.",
        verdict=adjudicator_verdict or verdict,
        confidence=confidence,
        reasoning="Benchmark reasoning.",
        supporting_evidence=[item.chunk_id for item in evidence[:1]],
        contradicting_evidence=[],
    )
    if adjudicator_verdict and adjudicator_verdict != final_verdict:
        validation_warnings = validation_warnings or ["Verdict adjusted during validation."]

    return VerificationResponse(
        status=VerificationStatus.SUCCESS,
        claim=claim,
        verdict=final_verdict,
        confidence=confidence,
        summary="Benchmark summary.",
        reasoning="Benchmark reasoning.",
        paper=PAPER,
        evidence=evidence,
        prosecutor=prosecutor
        or ProsecutorAnalysis(
            agent="prosecutor",
            analysis="Benchmark prosecutor analysis.",
            stance="neutral",
            confidence=0.65,
        ),
        defender=DefenderAnalysis(
            agent="defender",
            analysis="Benchmark defender analysis.",
            stance="supportive",
            supporting_evidence=[item.chunk_id for item in evidence[:1]],
            confidence=0.7,
        ),
        adjudicator=adjudicator,
        agent_agreement=agent_agreement,
        validation_warnings=validation_warnings,
        claim_traceability=traceability,
    )


def _conditional_supports() -> VerificationResponse:
    claim = "Imatinib reduces BCR-ABL kinase activity when ATP is present in the binding pocket."
    evidence = [_evidence("c1", "Imatinib reduces BCR-ABL kinase activity when ATP is present in the binding pocket.", relevance=0.86, overlap=0.83)]
    return _success_response(
        claim,
        Verdict.SUPPORTS,
        0.84,
        evidence,
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.SUPPORTED, 0.84, ["c1"])]
        ),
    )


def _dose_response_supports() -> VerificationResponse:
    claim = "A 10 mg dose of atorvastatin reduced LDL cholesterol in the trial."
    evidence = [_evidence("c1", "The 10 mg dose of atorvastatin reduced LDL cholesterol in the trial.", relevance=0.88, overlap=0.85)]
    return _success_response(
        claim,
        Verdict.SUPPORTS,
        0.87,
        evidence,
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.SUPPORTED, 0.87, ["c1"])]
        ),
    )


def _photosynthesis_supports() -> VerificationResponse:
    claim = "Plants convert light energy into chemical energy during photosynthesis in chloroplasts."
    evidence = [
        _evidence(
            "c1",
            "Photosynthesis converts light energy into chemical energy in chloroplasts.",
            relevance=0.9,
            overlap=0.87,
        )
    ]
    return _success_response(
        claim,
        Verdict.SUPPORTS,
        0.89,
        evidence,
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.SUPPORTED, 0.89, ["c1"])]
        ),
    )


def _conclusion_reversal() -> VerificationResponse:
    claim = "The SPRINT trial proves that intensive blood pressure treatment is safe for all patients."
    evidence = [_evidence("c1", "Serious adverse events were observed in the intensive treatment group during follow-up.", relevance=0.85, overlap=0.81)]
    return _success_response(
        claim,
        Verdict.CONTRADICTS,
        0.83,
        evidence,
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.CONTRADICTED, 0.8, ["c1"])]
        ),
        adjudicator_verdict=Verdict.CONTRADICTS,
        agent_agreement=False,
    )


def _opposite_direction() -> VerificationResponse:
    claim = "The BRCA1 mutation always increases enzyme activity in DNA repair pathways."
    evidence = [_evidence("c1", "BRCA1 mutations are associated with reduced DNA repair capacity, not increased activity.", relevance=0.84, overlap=0.79)]
    return _success_response(
        claim,
        Verdict.CONTRADICTS,
        0.82,
        evidence,
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.CONTRADICTED, 0.78, ["c1"])]
        ),
        adjudicator_verdict=Verdict.CONTRADICTS,
    )


def _safety_contradicts() -> VerificationResponse:
    claim = "Imatinib has no toxic effects in vivo at therapeutic doses."
    evidence = [_evidence("c1", "Significant toxicity and side effects were observed at therapeutic doses.", relevance=0.86, overlap=0.82)]
    return _success_response(
        claim,
        Verdict.CONTRADICTS,
        0.84,
        evidence,
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.CONTRADICTED, 0.81, ["c1"])]
        ),
        adjudicator_verdict=Verdict.CONTRADICTS,
        agent_agreement=False,
    )


def _always_eliminates() -> VerificationResponse:
    claim = "The CRISPR-Cas9 treatment always eliminates the targeted gene sequence."
    evidence = [_evidence("c1", "CRISPR-Cas9 editing efficiency varied across experiments and was not always 100%.", relevance=0.76, overlap=0.58)]
    return _success_response(
        claim,
        Verdict.OVERSTATED,
        0.74,
        evidence,
        traceability=_traceability(
            [
                ("segment_1", "The CRISPR-Cas9 treatment", ClaimSegmentStatus.PARTIALLY_SUPPORTED, 0.55, ["c1"]),
                ("segment_2", "always eliminates the targeted gene sequence", ClaimSegmentStatus.UNSUPPORTED, 0.15, []),
            ]
        ),
    )


def _proves_guarantees() -> VerificationResponse:
    claim = "The AlphaFold2 data proves the mechanism guarantees perfect protein structure prediction."
    evidence = [_evidence("c1", "AlphaFold2 achieved high accuracy but the paper acknowledges limitations and does not guarantee perfection.", relevance=0.72, overlap=0.52)]
    return _success_response(
        claim,
        Verdict.OVERSTATED,
        0.73,
        evidence,
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.PARTIALLY_SUPPORTED, 0.48, ["c1"])]
        ),
    )


def _compound_unsupported_detail() -> VerificationResponse:
    claim = "CRISPR-Cas9 editing is highly efficient and has no off-target effects in human cells."
    evidence = [_evidence("c1", "CRISPR-Cas9 editing showed high efficiency in targeted loci.", relevance=0.85, overlap=0.8)]
    return _success_response(
        claim,
        Verdict.OVERSTATED,
        0.79,
        evidence,
        traceability=_traceability(
            [
                ("segment_1", "CRISPR editing is efficient", ClaimSegmentStatus.SUPPORTED, 0.82, ["c1"]),
                ("segment_2", "has no off-target effects", ClaimSegmentStatus.UNSUPPORTED, 0.1, []),
            ]
        ),
    )


def _multi_assertion_one_supported() -> VerificationResponse:
    claim = "The mRNA COVID-19 vaccine prevents infection and eliminates transmission completely."
    evidence = [_evidence("c1", "The mRNA COVID-19 vaccine reduced symptomatic infection but did not completely eliminate transmission.", relevance=0.8, overlap=0.72)]
    return _success_response(
        claim,
        Verdict.OVERSTATED,
        0.77,
        evidence,
        traceability=_traceability(
            [
                ("segment_1", "The mRNA COVID-19 vaccine prevents infection", ClaimSegmentStatus.PARTIALLY_SUPPORTED, 0.68, ["c1"]),
                ("segment_2", "eliminates transmission completely", ClaimSegmentStatus.UNSUPPORTED, 0.08, []),
            ]
        ),
    )


def _related_not_establishing() -> VerificationResponse:
    claim = "The p53 protein directly regulates the glycolysis metabolic pathway."
    evidence = [_evidence("c1", "The p53 protein was detected in cells involved in metabolism but direct regulation of glycolysis was not established.", relevance=0.45, overlap=0.28)]
    return _success_response(
        claim,
        Verdict.INSUFFICIENT,
        0.44,
        evidence,
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.UNSUPPORTED, 0.22, [])]
        ),
        adjudicator_verdict=Verdict.INSUFFICIENT,
    )


def _tangential_topic() -> VerificationResponse:
    claim = "The CRISPR-Cas9 system improves cognitive performance in elderly patients."
    evidence = [_evidence("c1", "The CRISPR-Cas9 system is used for genome editing, not cognitive enhancement.", relevance=0.35, overlap=0.2)]
    return _success_response(
        claim,
        Verdict.INSUFFICIENT,
        0.4,
        evidence,
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.UNSUPPORTED, 0.18, [])]
        ),
        adjudicator_verdict=Verdict.INSUFFICIENT,
    )


def _unrelated_numbers() -> VerificationResponse:
    claim = "The AlphaFold2 model sensitivity is 98%."
    evidence = [_evidence("c1", "The AlphaFold2 paper reports GDT-TS scores, not sensitivity metrics.", relevance=0.3, overlap=0.12)]
    item = evidence[0].model_copy(update={"evidence_numbers": [], "numeric_overlap": 0.0})
    return _success_response(
        claim,
        Verdict.INSUFFICIENT,
        0.38,
        [item],
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.UNSUPPORTED, 0.1, [])]
        ),
        adjudicator_verdict=Verdict.INSUFFICIENT,
    )


def _weak_conditional() -> VerificationResponse:
    claim = "The enzyme is active only under acidic conditions in all tissues."
    evidence = [_evidence("c1", "Activity was observed at pH 5 in one cell line but not across all tissues.", relevance=0.28, overlap=0.2)]
    return _success_response(
        claim,
        Verdict.INSUFFICIENT,
        0.42,
        evidence,
        traceability=_traceability(
            [
                ("segment_1", "The enzyme is active only under acidic conditions", ClaimSegmentStatus.UNSUPPORTED, 0.2, []),
                ("segment_2", "in all tissues", ClaimSegmentStatus.UNSUPPORTED, 0.05, []),
            ]
        ),
        adjudicator_verdict=Verdict.INSUFFICIENT,
    )


def _not_in_paper() -> VerificationResponse:
    claim = "The authors reported a phase III multicenter trial with 10,000 patients in the original CRISPR-Cas9 paper."
    return _success_response(
        claim,
        Verdict.FABRICATED,
        0.7,
        [],
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.UNSUPPORTED, 0.04, [])]
        ),
        validation_warnings=["Claim references content not found in the cited paper. The original paper was an in vitro study."],
    )


def _invented_statistic() -> VerificationResponse:
    claim = "The SPRINT trial achieved an 87% five-year survival rate in the intensive treatment group."
    evidence = [_evidence("c1", "The SPRINT trial did not report this specific five-year survival rate.", relevance=0.25, overlap=0.1)]
    return _success_response(
        claim,
        Verdict.FABRICATED,
        0.68,
        evidence,
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.UNSUPPORTED, 0.06, [])]
        ),
        validation_warnings=["Survival statistic not supported by cited evidence."],
    )


def _no_evidence_present() -> VerificationResponse:
    claim = "The molecule binds irreversibly to the BCR-ABL kinase domain."
    return _success_response(
        claim,
        Verdict.FABRICATED,
        0.66,
        [],
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.UNSUPPORTED, 0.03, [])]
        ),
    )


def _never_occurs() -> VerificationResponse:
    claim = "Resistance never develops under imatinib treatment regimen."
    evidence = [_evidence("c1", "Resistance emerged in patients under imatinib treatment.", relevance=0.82, overlap=0.76)]
    return _success_response(
        claim,
        Verdict.CONTRADICTS,
        0.8,
        evidence,
        traceability=_traceability(
            [("segment_1", claim, ClaimSegmentStatus.CONTRADICTED, 0.77, ["c1"])]
        ),
        adjudicator_verdict=Verdict.CONTRADICTS,
    )
