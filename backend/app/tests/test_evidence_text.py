from __future__ import annotations

from app.utils.evidence_text import normalize_evidence_text


class TestEvidenceTextNormalization:
    def test_collapses_whitespace(self) -> None:
        assert normalize_evidence_text("Cas9   can\n\nbind RNA") == "cas9 can bind rna"

    def test_strips_html_artifacts(self) -> None:
        assert (
            normalize_evidence_text("<p>Cas9</p> can bind RNA")
            == "cas9 can bind rna"
        )

    def test_casefolds_for_comparison_only(self) -> None:
        left = normalize_evidence_text("Cas9 RNA")
        right = normalize_evidence_text("cas9 rna")
        assert left == right
