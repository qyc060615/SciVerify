from __future__ import annotations

from app.schemas.verification import (
    AdjudicatorAnalysis,
    DefenderAnalysis,
    ProsecutorAnalysis,
    Verdict,
)
from app.services.evidence_validation import (
    filter_valid_chunk_ids,
    sanitize_adjudicator_analysis,
    sanitize_defender_analysis,
    sanitize_prosecutor_analysis,
)


class TestEvidenceValidation:
    def test_filter_valid_chunk_ids(self) -> None:
        valid = {"c1", "c2"}
        assert filter_valid_chunk_ids(["c1", "fake", "c2"], valid) == ["c1", "c2"]

    def test_reject_hallucinated_prosecutor_references(self) -> None:
        analysis = ProsecutorAnalysis(
            agent="prosecutor",
            analysis="Challenge",
            stance="skeptical",
            key_points=["Numeric mismatch"],
            supporting_evidence=["c1", "hallucinated"],
            contradicting_evidence=["fake-id", "c2"],
            confidence=0.7,
        )
        sanitized = sanitize_prosecutor_analysis(analysis, {"c1", "c2"})
        assert sanitized.supporting_evidence == ["c1"]
        assert sanitized.contradicting_evidence == ["c2"]

    def test_reject_hallucinated_defender_references(self) -> None:
        analysis = DefenderAnalysis(
            agent="defender",
            analysis="Support",
            stance="supportive",
            key_points=["Direct support"],
            supporting_evidence=["valid", "invalid"],
            contradicting_evidence=[],
            confidence=0.8,
        )
        sanitized = sanitize_defender_analysis(analysis, {"valid"})
        assert sanitized.supporting_evidence == ["valid"]

    def test_reject_hallucinated_adjudicator_references(self) -> None:
        analysis = AdjudicatorAnalysis(
            agent="adjudicator",
            analysis="Final review",
            verdict=Verdict.OVERSTATED,
            confidence=0.75,
            reasoning="Claim exaggerates magnitude.",
            supporting_evidence=["c1", "missing"],
            contradicting_evidence=["ghost"],
            suggested_correction="Reduce claimed effect size.",
        )
        sanitized = sanitize_adjudicator_analysis(analysis, {"c1"})
        assert sanitized.supporting_evidence == ["c1"]
        assert sanitized.contradicting_evidence == []

    def test_format_evidence_for_prompt_is_token_efficient(self) -> None:
        import json
        from app.schemas.evidence import EvidenceItem
        from app.services.evidence_validation import format_evidence_for_prompt

        item = EvidenceItem(
            chunk_id="chunk_001",
            section="Results",
            chunk_index=0,
            text="Sample evidence text.",
            relevance_score=0.95,
            claim_overlap=0.8,
            numeric_overlap=1.0,
            claim_numbers=["10"],
            evidence_numbers=["10"],
            source_url="https://example.com/very/long/url/to/paper.pdf",
            page=1,
        )
        output = format_evidence_for_prompt([item])
        parsed = json.loads(output)
        assert len(parsed) == 1
        assert parsed[0]["chunk_id"] == "chunk_001"
        assert parsed[0]["section"] == "Results"
        assert parsed[0]["text"] == "Sample evidence text."
        assert "source_url" not in parsed[0]
        assert "relevance_score" not in parsed[0]
        assert "claim_numbers" not in parsed[0]
