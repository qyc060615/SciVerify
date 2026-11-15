from __future__ import annotations

from app.schemas.evidence import EvidenceItem
from app.schemas.verification import (
    AdjudicatorAnalysis,
    ClaimSegmentStatus,
    ProsecutorAnalysis,
    Verdict,
)
from app.services.claim_traceability import build_claim_traceability
from app.utils.claim_segmenter import segment_claim


def _evidence(
    chunk_id: str,
    text: str,
    *,
    relevance: float = 0.8,
    claim_overlap: float = 0.7,
    numeric_overlap: float = 0.0,
    evidence_numbers: list[str] | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        chunk_id=chunk_id,
        section="Results",
        chunk_index=0,
        text=text,
        relevance_score=relevance,
        claim_overlap=claim_overlap,
        numeric_overlap=numeric_overlap,
        evidence_numbers=evidence_numbers or [],
    )


CAS9_CLAIM = (
    "Cas9 can be programmed with guide RNA to cleave specific "
    "double-stranded DNA target sequences."
)


class TestClaimSegmenter:
    def test_multi_segment_claim(self) -> None:
        segments = segment_claim(CAS9_CLAIM)
        assert len(segments) >= 2
        assert "Cas9" in segments[0]
        assert any("cleave" in segment for segment in segments)


class TestClaimTraceability:
    def test_single_segment_claim_with_strong_evidence(self) -> None:
        claim = "The model achieved 94.2% accuracy."
        evidence = [
            _evidence(
                "c1",
                "The model achieved an accuracy of 94.2% on the benchmark.",
                claim_overlap=0.9,
                numeric_overlap=1.0,
                evidence_numbers=["94.2%"],
            )
        ]
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.SUPPORTS,
        )

        assert result is not None
        assert len(result.segments) == 1
        assert result.segments[0].status == ClaimSegmentStatus.SUPPORTED
        assert result.segments[0].evidence_ids == ["c1"]
        assert result.overall_coverage >= 0.65

    def test_multi_segment_cas9_claim(self) -> None:
        evidence = [
            _evidence(
                "c1",
                "Cas9 can be programmed with guide RNA in vitro.",
                claim_overlap=0.82,
            ),
            _evidence(
                "c2",
                "Cas9 introduces double-stranded breaks at specific DNA target sequences.",
                claim_overlap=0.78,
            ),
        ]
        result = build_claim_traceability(
            CAS9_CLAIM,
            evidence,
            verdict=Verdict.SUPPORTS,
        )

        assert result is not None
        assert len(result.segments) >= 2
        assert result.overall_coverage > 0

    def test_partially_supported_segment(self) -> None:
        claim = "The treatment improves survival and eliminates all side effects."
        evidence = [
            _evidence(
                "c1",
                "The treatment improved survival in the trial cohort.",
                claim_overlap=0.55,
                relevance=0.6,
            )
        ]
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.OVERSTATED,
        )

        assert result is not None
        statuses = {segment.status for segment in result.segments}
        assert ClaimSegmentStatus.PARTIALLY_SUPPORTED in statuses or ClaimSegmentStatus.UNSUPPORTED in statuses

    def test_unsupported_segment_without_evidence(self) -> None:
        result = build_claim_traceability(
            "Unknown compound cures all diseases instantly.",
            [],
            verdict=Verdict.INSUFFICIENT,
        )

        assert result is not None
        assert all(
            segment.status == ClaimSegmentStatus.UNSUPPORTED for segment in result.segments
        )
        assert result.overall_coverage == 0.0

    def test_contradicted_segment_uses_agent_contradicting_ids(self) -> None:
        claim = "The treatment reduces mortality."
        evidence = [
            _evidence(
                "c1",
                "No mortality reduction was observed in the treatment arm.",
                claim_overlap=0.72,
            )
        ]
        adjudicator = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Final",
            verdict=Verdict.CONTRADICTS,
            confidence=0.8,
            reasoning="Evidence conflicts with the claim.",
            contradicting_evidence=["c1"],
        )
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.CONTRADICTS,
            adjudicator=adjudicator,
        )

        assert result is not None
        assert any(
            segment.status == ClaimSegmentStatus.CONTRADICTED for segment in result.segments
        )

    def test_numeric_claim_matching(self) -> None:
        claim = "Accuracy improved by 12%."
        evidence = [
            _evidence(
                "c1",
                "Accuracy improved by 12% relative to baseline.",
                claim_overlap=0.7,
                numeric_overlap=1.0,
                evidence_numbers=["12%"],
            )
        ]
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.SUPPORTS,
        )

        assert result is not None
        assert result.segments[0].evidence_ids == ["c1"]

    def test_evidence_ids_preserved(self) -> None:
        evidence = [
            _evidence("alpha", "Cas9 uses guide RNA for DNA cleavage.", claim_overlap=0.8),
            _evidence("beta", "Target DNA sequences are cleaved by Cas9.", claim_overlap=0.75),
        ]
        result = build_claim_traceability(
            CAS9_CLAIM,
            evidence,
            verdict=Verdict.SUPPORTS,
        )

        assert result is not None
        linked = {chunk_id for segment in result.segments for chunk_id in segment.evidence_ids}
        assert linked.issubset({"alpha", "beta"})

    def test_overall_coverage_calculation(self) -> None:
        evidence = [
            _evidence("c1", "Cas9 can be programmed with guide RNA.", claim_overlap=0.9),
            _evidence("c2", "Cas9 cleaves double-stranded DNA target sequences.", claim_overlap=0.85),
        ]
        result = build_claim_traceability(
            CAS9_CLAIM,
            evidence,
            verdict=Verdict.SUPPORTS,
        )

        assert result is not None
        expected = sum(segment.coverage_score for segment in result.segments) / len(
            result.segments
        )
        assert result.overall_coverage == round(min(1.0, max(0.0, expected)), 4)

    def test_supports_verdict_warning_when_segment_unsupported(self) -> None:
        claim = "Accuracy improved and cured every disease."
        evidence = [
            _evidence("c1", "Accuracy improved in the benchmark.", claim_overlap=0.7),
        ]
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.SUPPORTS,
        )

        assert result is not None
        assert any("not directly supported" in warning for warning in result.warnings)

    def test_insufficient_verdict_warning(self) -> None:
        result = build_claim_traceability(
            CAS9_CLAIM,
            [],
            verdict=Verdict.INSUFFICIENT,
        )

        assert result is not None
        assert any("insufficient" in warning.lower() for warning in result.warnings)

    def test_overstated_verdict_warning(self) -> None:
        evidence = [
            _evidence("c1", "Cas9 uses RNA guides.", claim_overlap=0.55, relevance=0.5),
        ]
        result = build_claim_traceability(
            CAS9_CLAIM,
            evidence,
            verdict=Verdict.OVERSTATED,
        )

        assert result is not None
        assert result.warnings

    def test_contradicts_verdict_warning(self) -> None:
        evidence = [
            _evidence("c1", "Cas9 did not cleave the tested DNA target.", claim_overlap=0.7),
        ]
        adjudicator = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Final",
            verdict=Verdict.CONTRADICTS,
            confidence=0.8,
            reasoning="Conflict",
            contradicting_evidence=["c1"],
        )
        result = build_claim_traceability(
            CAS9_CLAIM,
            evidence,
            verdict=Verdict.CONTRADICTS,
            adjudicator=adjudicator,
        )

        assert result is not None
        assert any("contradict" in warning.lower() for warning in result.warnings)

    def test_no_llm_calls_are_required(self) -> None:
        result = build_claim_traceability(
            CAS9_CLAIM,
            [_evidence("c1", "Cas9 guide RNA DNA cleavage.", claim_overlap=0.8)],
            verdict=Verdict.SUPPORTS,
        )
        assert result is not None

    def test_backward_compatibility_when_traceability_absent(self) -> None:
        assert build_claim_traceability("   ", [], verdict=Verdict.INSUFFICIENT) is None

    def test_prosecutor_contradicting_ids_can_mark_segment(self) -> None:
        claim = "The drug reduces inflammation."
        evidence = [
            _evidence(
                "c1",
                "Inflammation markers increased in treated subjects.",
                claim_overlap=0.68,
            )
        ]
        prosecutor = ProsecutorAnalysis(
            agent="prosecutor",
            analysis="Challenge",
            stance="skeptical",
            contradicting_evidence=["c1"],
            confidence=0.7,
        )
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.CONTRADICTS,
            prosecutor=prosecutor,
        )

        assert result is not None
        assert result.segments[0].evidence_ids == ["c1"]


# ---------------------------------------------------------------------------
# Regression tests for consistency between traceability status and final
# verdict — added to cover the real-world report inconsistency issues.
# ---------------------------------------------------------------------------


class TestTraceabilityVerdictConsistency:
    """Traceability segment status must never override or masquerade as the
    final verdict.

    Rules verified:
    - Final verdict SUPPORTS is not contradicted by a PARTIALLY_SUPPORTED
      segment (the segment describes coverage, not the verdict).
    - CONTRADICTED status only appears when the adjudicator definitively
      references a chunk as contradicting.
    - Prosecutor's normal adversarial contradicting_evidence does NOT mark
      segments as CONTRADICTED on a SUPPORTS verdict.
    - Multiple segments with mixed coverage still yield the correct overall
      coverage without polluting the verdict.
    """

    def test_supports_verdict_with_partially_supported_segment_is_not_contradicted(
        self,
    ) -> None:
        """SUPPORTS final verdict + PARTIALLY_SUPPORTED segment — segment status
        must be PARTIALLY_SUPPORTED, not CONTRADICTED."""
        claim = (
            "Cas9 can be programmed with guide RNA to introduce double-strand "
            "breaks in DNA."
        )
        evidence = [
            _evidence(
                "c1",
                "Cas9 can be programmed with guide RNA.",
                claim_overlap=0.6,
                relevance=0.7,
            )
        ]
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.SUPPORTS,
        )

        assert result is not None
        statuses = {seg.status for seg in result.segments}
        assert ClaimSegmentStatus.CONTRADICTED not in statuses, (
            "Segments must not be marked CONTRADICTED when verdict is SUPPORTS"
        )
        assert ClaimSegmentStatus.PARTIALLY_SUPPORTED in statuses or (
            ClaimSegmentStatus.SUPPORTED in statuses
        )

    def test_supports_52_percent_coverage_does_not_use_contradicted_label(
        self,
    ) -> None:
        """52% coverage with a SUPPORTS verdict must NOT render CONTRADICTED."""
        claim = (
            "Cas9 can be programmed with guide RNA to introduce double-strand "
            "breaks in DNA."
        )
        evidence = [
            _evidence(
                "c1",
                "Cas9 uses guide RNA.",
                claim_overlap=0.4,
                relevance=0.55,
            )
        ]
        adjudicator = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Claim is supported.",
            verdict=Verdict.SUPPORTS,
            confidence=0.84,
            reasoning="Evidence supports the claim.",
            supporting_evidence=["c1"],
            contradicting_evidence=[],
        )
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.SUPPORTS,
            adjudicator=adjudicator,
        )

        assert result is not None
        statuses = {seg.status for seg in result.segments}
        assert ClaimSegmentStatus.CONTRADICTED not in statuses, (
            "52% coverage on a SUPPORTS verdict must not label any segment CONTRADICTED"
        )

    def test_prosecutor_adversarial_contradicting_evidence_does_not_mark_contradicted(
        self,
    ) -> None:
        """The Prosecutor routinely lists contradicting evidence — this is its
        role.  When the adjudicator verdict is SUPPORTS and the adjudicator
        has NO contradicting_evidence, no segment must be CONTRADICTED."""
        claim = "Cas9 can be programmed with guide RNA."
        evidence = [
            _evidence(
                "c1",
                "We demonstrate Cas9 can be programmed with single guide RNAs.",
                claim_overlap=0.85,
                relevance=0.9,
            )
        ]
        prosecutor = ProsecutorAnalysis(
            agent="prosecutor",
            analysis="Attempting to challenge the claim.",
            stance="challenge",
            contradicting_evidence=["c1"],  # prosecutor challenged via c1
            confidence=0.6,
        )
        adjudicator = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Claim is well supported.",
            verdict=Verdict.SUPPORTS,
            confidence=0.85,
            reasoning="Clear evidence found.",
            supporting_evidence=["c1"],
            contradicting_evidence=[],  # adjudicator did NOT flag c1 as contradicting
        )
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.SUPPORTS,
            adjudicator=adjudicator,
            prosecutor=prosecutor,
        )

        assert result is not None
        for segment in result.segments:
            assert segment.status != ClaimSegmentStatus.CONTRADICTED, (
                f"Segment '{segment.text}' must not be CONTRADICTED when adjudicator "
                f"verdict is SUPPORTS and adjudicator has no contradicting_evidence. "
                f"Got: {segment.status}"
            )

    def test_genuine_contradicted_segment_when_adjudicator_references_chunk(
        self,
    ) -> None:
        """When the adjudicator explicitly lists a chunk as contradicting
        evidence, that segment CAN and SHOULD be marked CONTRADICTED."""
        claim = "The drug reduces inflammation."
        evidence = [
            _evidence(
                "c1",
                "Inflammation increased significantly in the treatment arm.",
                claim_overlap=0.72,
                relevance=0.8,
            )
        ]
        adjudicator = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Evidence contradicts the claim.",
            verdict=Verdict.CONTRADICTS,
            confidence=0.88,
            reasoning="The evidence shows the opposite effect.",
            supporting_evidence=[],
            contradicting_evidence=["c1"],  # adjudicator definitively flags c1
        )
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.CONTRADICTS,
            adjudicator=adjudicator,
        )

        assert result is not None
        assert any(
            seg.status == ClaimSegmentStatus.CONTRADICTED for seg in result.segments
        ), "A genuinely contradicted segment must be labeled CONTRADICTED"

    def test_prosecutor_challenges_defender_supports_normal_adversarial_role(
        self,
    ) -> None:
        """Normal adversarial role behavior: prosecutor challenges (contradicting
        evidence listed) and defender supports — when the adjudicator's verdict
        is SUPPORTS and its contradicting_evidence list is empty, NO segment
        must be marked CONTRADICTED."""
        claim = "The treatment improves patient outcomes."
        evidence = [
            _evidence(
                "c1",
                "Patients in the treatment arm showed improved outcomes.",
                claim_overlap=0.78,
                relevance=0.82,
            )
        ]
        prosecutor = ProsecutorAnalysis(
            agent="prosecutor",
            analysis="Challenging the claim: limited sample size.",
            stance="challenge",
            contradicting_evidence=["c1"],
            supporting_evidence=[],
            confidence=0.6,
        )
        adjudicator = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Claim is supported on balance.",
            verdict=Verdict.SUPPORTS,
            confidence=0.8,
            reasoning="Defender evidence is stronger.",
            supporting_evidence=["c1"],
            contradicting_evidence=[],
        )
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.SUPPORTS,
            adjudicator=adjudicator,
            prosecutor=prosecutor,
        )

        assert result is not None
        statuses = {seg.status for seg in result.segments}
        assert ClaimSegmentStatus.CONTRADICTED not in statuses

    def test_backend_verdict_is_independent_of_traceability_segment_status(
        self,
    ) -> None:
        """The segment statuses describe coverage only; they must not determine
        the final verdict.  A segment can be PARTIALLY_SUPPORTED while the
        overall verdict remains SUPPORTS."""
        from app.services.verification_validator import validate_verification_result
        from app.schemas.evidence import EvidenceItem
        from app.schemas.verification import (
            DefenderAnalysis,
        )

        evidence_items = [
            EvidenceItem(
                chunk_id="c1",
                section="Results",
                chunk_index=0,
                text="Cas9 can be programmed with guide RNA.",
                relevance_score=0.82,
                claim_overlap=0.76,
                numeric_overlap=0.0,
            )
        ]
        prosecutor = ProsecutorAnalysis(
            agent="prosecutor",
            analysis="Challenging.",
            stance="challenge",
            contradicting_evidence=["c1"],
            supporting_evidence=[],
            confidence=0.6,
        )
        defender = DefenderAnalysis(
            agent="defender",
            analysis="Supporting.",
            stance="supported",
            supporting_evidence=["c1"],
            contradicting_evidence=[],
            confidence=0.9,
        )
        adj = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="SUPPORTS.",
            verdict=Verdict.SUPPORTS,
            confidence=0.85,
            reasoning="Evidence clearly supports.",
            supporting_evidence=["c1"],
            contradicting_evidence=[],
        )

        validated = validate_verification_result(
            claim="Cas9 can be programmed with guide RNA.",
            evidence=evidence_items,
            prosecutor=prosecutor,
            defender=defender,
            adjudicator=adj,
        )

        # Verified verdict is SUPPORTS regardless of traceability segment status
        assert validated.verdict == Verdict.SUPPORTS

        # Build traceability with prosecutor present
        traceability = build_claim_traceability(
            "Cas9 can be programmed with guide RNA.",
            evidence_items,
            verdict=Verdict.SUPPORTS,
            adjudicator=adj,
            prosecutor=prosecutor,
        )
        assert traceability is not None
        # No segment should be CONTRADICTED because adjudicator has no
        # contradicting_evidence
        for seg in traceability.segments:
            assert seg.status != ClaimSegmentStatus.CONTRADICTED

    def test_overall_coverage_is_informational_not_verdict_override(
        self,
    ) -> None:
        """Even 52% overall coverage must not alter the SUPPORTS verdict.
        Coverage is purely informational."""
        claim = (
            "Cas9 can be programmed with guide RNA to introduce double-strand "
            "breaks in DNA."
        )
        evidence = [
            _evidence("c1", "Cas9 uses RNA guides.", claim_overlap=0.4, relevance=0.55)
        ]
        adjudicator = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Supports.",
            verdict=Verdict.SUPPORTS,
            confidence=0.84,
            reasoning="Evidence supports the general claim.",
            supporting_evidence=["c1"],
            contradicting_evidence=[],
        )
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.SUPPORTS,
            adjudicator=adjudicator,
        )

        assert result is not None
        # Coverage may be below 65% (partial) — that is acceptable
        assert 0.0 <= result.overall_coverage <= 1.0
        # No segments should be CONTRADICTED
        statuses = {seg.status for seg in result.segments}
        assert ClaimSegmentStatus.CONTRADICTED not in statuses

    def test_existing_suggested_correction_behavior_unchanged(self) -> None:
        """Existing suggested_correction test must pass — traceability changes
        must not affect suggested_correction logic."""
        from app.services.verification_validator import validate_verification_result
        from app.schemas.evidence import EvidenceItem
        from app.schemas.verification import DefenderAnalysis

        evidence_items = [
            EvidenceItem(
                chunk_id="c1",
                section="Results",
                chunk_index=0,
                text="Method improves accuracy by 12%.",
                relevance_score=0.82,
                claim_overlap=0.76,
                numeric_overlap=0.0,
            )
        ]
        result = validate_verification_result(
            claim="The method improves accuracy by 40%.",
            evidence=evidence_items,
            prosecutor=ProsecutorAnalysis(
                agent="prosecutor",
                analysis="Challenged.",
                stance="skeptical",
                contradicting_evidence=["c1"],
                supporting_evidence=[],
                confidence=0.7,
            ),
            defender=DefenderAnalysis(
                agent="defender",
                analysis="Supported.",
                stance="supportive",
                supporting_evidence=["c1"],
                contradicting_evidence=[],
                confidence=0.7,
            ),
            adjudicator=AdjudicatorAnalysis(
                agent="adjudicator",
                analysis="Overstated.",
                verdict=Verdict.OVERSTATED,
                confidence=0.8,
                reasoning="12% not 40%.",
                supporting_evidence=["c1"],
                contradicting_evidence=[],
                suggested_correction="The method improves accuracy by about 12%.",
            ),
        )

        assert result.verdict == Verdict.OVERSTATED
        assert result.suggested_correction == "The method improves accuracy by about 12%."


# ---------------------------------------------------------------------------
# Regression tests for coverage robustness across scientific claims,
# including multi-chunk evidence, numeric matches, paraphrases, and hedges.
# ---------------------------------------------------------------------------


class TestTraceabilityCoverageRobustness:
    """Verifies that traceability coverage accurately reflects semantic and
    numeric support across evidence chunks, without artificial penalties
    due to paraphrasing, parenthetical statistics, or multi-chunk splits.
    """

    def test_bnt162b2_covid_vaccine_claim_is_fully_supported(self) -> None:
        """BNT162b2 95% efficacy claim with multi-chunk clinical trial evidence
        must achieve SUPPORTED status (>= 65% coverage) rather than being
        artificially penalized as PARTIALLY_SUPPORTED."""
        claim = (
            "The BNT162b2 mRNA vaccine was approximately 95% effective at "
            "preventing COVID-19 after the second dose in the phase 2/3 trial."
        )
        evidence = [
            _evidence(
                "c1",
                (
                    "A total of 43,548 participants underwent randomization: "
                    "21,720 with BNT162b2 and 21,728 with placebo. There were 8 cases "
                    "of Covid-19 with onset at least 7 days after the second dose "
                    "among participants assigned to receive BNT162b2 and 162 cases "
                    "among those assigned to placebo; BNT162b2 was 95.0% effective "
                    "(95% credible interval, 90.3 to 97.6) in preventing Covid-19."
                ),
                relevance=0.85,
                claim_overlap=0.72,
                numeric_overlap=1.0,
                evidence_numbers=["43548", "21720", "21728", "8", "7days", "162", "95.0%", "95%", "90.3", "97.6"],
            ),
            _evidence(
                "c2",
                (
                    "The favorable safety profile observed during phase 1 testing of BNT162b2 "
                    "was confirmed in the phase 2/3 portion of the trial."
                ),
                relevance=0.75,
                claim_overlap=0.65,
                numeric_overlap=1.0,
                evidence_numbers=["1", "2", "3", "2/3"],
            ),
            _evidence(
                "c3",
                (
                    "A two-dose regimen of BNT162b2 (30 μg per dose, given 21 days apart) "
                    "was found to be safe and 95% effective in preventing Covid-19."
                ),
                relevance=0.80,
                claim_overlap=0.70,
                numeric_overlap=1.0,
                evidence_numbers=["30μg", "21days", "95%"],
            ),
        ]

        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.SUPPORTS,
        )

        assert result is not None
        assert result.overall_coverage >= 0.65, (
            f"Expected overall coverage >= 65%, got {result.overall_coverage*100:.1f}%"
        )
        assert all(seg.status == ClaimSegmentStatus.SUPPORTED for seg in result.segments), (
            f"Expected all segments to be SUPPORTED, got {[s.status for s in result.segments]}"
        )
        assert len(result.segments[0].evidence_ids) >= 2, (
            "Expected multiple linked evidence chunks"
        )

    def test_exact_numerical_support_yields_high_coverage(self) -> None:
        """Exact numeric matches (e.g. 94.2% accuracy) achieve >= 65% coverage."""
        claim = "The model achieved 94.2% accuracy on the benchmark."
        evidence = [
            _evidence(
                "c1",
                "The proposed architecture achieved an accuracy of 94.2% on the benchmark dataset.",
                relevance=0.9,
                claim_overlap=0.85,
                numeric_overlap=1.0,
                evidence_numbers=["94.2%"],
            )
        ]
        result = build_claim_traceability(claim, evidence, verdict=Verdict.SUPPORTS)
        assert result is not None
        assert result.overall_coverage >= 0.65
        assert result.segments[0].status == ClaimSegmentStatus.SUPPORTED

    def test_approximate_numerical_hedges_do_not_penalize_coverage(self) -> None:
        """Hedges like 'approximately 95%' matching '95%' must achieve SUPPORTED status."""
        claim = "Efficacy was approximately 95% across the cohort."
        evidence = [
            _evidence(
                "c1",
                "Vaccine efficacy was 95% across the evaluated cohort.",
                relevance=0.88,
                claim_overlap=0.82,
                numeric_overlap=1.0,
                evidence_numbers=["95%"],
            )
        ]
        result = build_claim_traceability(claim, evidence, verdict=Verdict.SUPPORTS)
        assert result is not None
        assert result.overall_coverage >= 0.65
        assert result.segments[0].status == ClaimSegmentStatus.SUPPORTED

    def test_paraphrase_with_intercalated_parenthetical_qualifiers(self) -> None:
        """Scientific sentences with intervening CI intervals or preposition differences
        (e.g., 'at preventing' vs 'in preventing') maintain SUPPORTED status."""
        claim = "The drug was effective at preventing infection after the second dose."
        evidence = [
            _evidence(
                "c1",
                "The drug demonstrated efficacy in preventing infection (95% CI, 90 to 98) 7 days after the second dose.",
                relevance=0.82,
                claim_overlap=0.74,
                numeric_overlap=0.5,
                evidence_numbers=["95%", "90", "98", "7days"],
            )
        ]
        result = build_claim_traceability(claim, evidence, verdict=Verdict.SUPPORTS)
        assert result is not None
        assert result.overall_coverage >= 0.65
        assert result.segments[0].status == ClaimSegmentStatus.SUPPORTED

    def test_multi_part_claim_with_each_part_supported(self) -> None:
        """Multi-part claim where each segment is supported by complementary chunks."""
        claim = "Cas9 uses guide RNA and introduces double-strand breaks in DNA."
        evidence = [
            _evidence("c1", "Cas9 uses single guide RNA in the complex.", relevance=0.85, claim_overlap=0.75),
            _evidence("c2", "Cas9 introduces double-strand breaks in target DNA.", relevance=0.88, claim_overlap=0.78),
        ]
        result = build_claim_traceability(claim, evidence, verdict=Verdict.SUPPORTS)
        assert result is not None
        assert result.overall_coverage >= 0.65
        assert all(seg.status == ClaimSegmentStatus.SUPPORTED for seg in result.segments)

    def test_genuinely_partial_claim_preserves_partial_status(self) -> None:
        """When evidence supports only one part of a multi-part claim, the unsupported
        part must remain PARTIALLY_SUPPORTED or UNSUPPORTED."""
        claim = "The treatment improves survival and eliminates all side effects."
        evidence = [
            _evidence(
                "c1",
                "The treatment improved overall survival in the trial cohort.",
                relevance=0.65,
                claim_overlap=0.50,
            )
        ]
        result = build_claim_traceability(claim, evidence, verdict=Verdict.OVERSTATED)
        assert result is not None
        statuses = [s.status for s in result.segments]
        assert (
            ClaimSegmentStatus.PARTIALLY_SUPPORTED in statuses
            or ClaimSegmentStatus.UNSUPPORTED in statuses
        )

    def test_genuinely_contradicted_segment_preserves_contradicted_status(self) -> None:
        """When adjudicator definitively flags contradicting evidence, segment is CONTRADICTED."""
        claim = "The treatment reduces patient mortality."
        evidence = [
            _evidence(
                "c1",
                "Mortality was significantly higher in the treatment arm compared to control.",
                relevance=0.85,
                claim_overlap=0.75,
            )
        ]
        adjudicator = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Evidence directly contradicts the claim.",
            verdict=Verdict.CONTRADICTS,
            confidence=0.9,
            reasoning="Trial mortality increased.",
            contradicting_evidence=["c1"],
        )
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.CONTRADICTS,
            adjudicator=adjudicator,
        )
        assert result is not None
        assert any(seg.status == ClaimSegmentStatus.CONTRADICTED for seg in result.segments)

    def test_prosecutor_adversarial_evidence_does_not_override_supports_traceability(self) -> None:
        """Prosecutor challenging does not mark segments CONTRADICTED when final verdict is SUPPORTS."""
        claim = "The treatment improves survival."
        evidence = [
            _evidence("c1", "Treatment significantly improved survival across all trial sites.", relevance=0.9, claim_overlap=0.85)
        ]
        prosecutor = ProsecutorAnalysis(
            agent="prosecutor",
            analysis="Challenging sample size.",
            stance="challenge",
            contradicting_evidence=["c1"],
            confidence=0.6,
        )
        adjudicator = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Claim is supported.",
            verdict=Verdict.SUPPORTS,
            confidence=0.88,
            reasoning="Evidence is strong.",
            supporting_evidence=["c1"],
            contradicting_evidence=[],
        )
        result = build_claim_traceability(
            claim,
            evidence,
            verdict=Verdict.SUPPORTS,
            adjudicator=adjudicator,
            prosecutor=prosecutor,
        )
        assert result is not None
        assert all(seg.status != ClaimSegmentStatus.CONTRADICTED for seg in result.segments)
        assert result.segments[0].status == ClaimSegmentStatus.SUPPORTED

