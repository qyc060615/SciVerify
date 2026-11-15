from __future__ import annotations

from app.config import EVIDENCE_TOP_K
from app.schemas.paper import EvidenceChunk
from app.services.evidence_retriever import rank_evidence_for_claim
from app.utils.claim_preprocessor import preprocess_claim
from app.utils.evidence_text import normalize_evidence_text


def _chunk(
    chunk_id: str,
    section: str,
    text: str,
    chunk_index: int = 0,
) -> EvidenceChunk:
    return EvidenceChunk(
        chunk_id=chunk_id,
        paper_id="10.1000/test",
        section=section,
        chunk_index=chunk_index,
        text=text,
        source_url="https://example.org/paper.pdf",
        page=4,
    )


CAS9_CLAIM = (
    "Cas9 can be programmed with guide RNA to cleave specific "
    "double-stranded DNA target sequences."
)


class TestEvidenceRanking:
    def test_high_relevance_wins_over_weak_match(self) -> None:
        claim = preprocess_claim(CAS9_CLAIM)
        chunks = [
            _chunk(
                "direct",
                "Results",
                "Cas9 can be programmed with guide RNA to cleave specific double-stranded DNA target sequences.",
                0,
            ),
            _chunk("weak", "Introduction", "DNA is an important biological molecule.", 1),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert ranked[0].chunk_id == "direct"
        assert ranked[0].relevance_score > ranked[1].relevance_score

    def test_claim_overlap_prefers_important_terms(self) -> None:
        claim = preprocess_claim(CAS9_CLAIM)
        chunks = [
            _chunk(
                "specific",
                "Results",
                "Cas9 uses guide RNA to introduce double-stranded DNA breaks at target sites.",
                0,
            ),
            _chunk("generic", "Results", "DNA molecules are present in many organisms.", 1),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert ranked[0].chunk_id == "specific"
        assert ranked[0].claim_overlap > ranked[1].claim_overlap

    def test_section_bonus_prefers_results_over_references(self) -> None:
        claim = preprocess_claim("accuracy improved in benchmark experiments")
        shared = "The benchmark experiments report improved accuracy in the evaluation."
        chunks = [
            _chunk("results", "Results", shared, 0),
            _chunk("refs", "References", shared, 1),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert len(ranked) == 1
        assert ranked[0].chunk_id == "results"

    def test_numeric_match_improves_ranking(self) -> None:
        claim = preprocess_claim("The model achieved 94.2% accuracy.")
        chunks = [
            _chunk("numeric", "Results", "The model achieved an accuracy of 94.2%.", 0),
            _chunk("text", "Results", "The model achieved strong accuracy on the benchmark.", 1),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert ranked[0].chunk_id == "numeric"
        assert ranked[0].numeric_overlap == 1.0

    def test_numeric_only_match_does_not_dominate_without_text_overlap(self) -> None:
        claim = preprocess_claim("The model achieved 94.2% accuracy.")
        chunks = [
            _chunk(
                "numeric_only",
                "Results",
                "Figure 3 runtime was 94.2 seconds under the baseline configuration.",
                0,
            ),
            _chunk(
                "textual",
                "Results",
                "The model achieved strong accuracy on the held-out evaluation benchmark.",
                1,
            ),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert ranked[0].chunk_id == "textual"

    def test_exact_phrase_match_ranks_highly(self) -> None:
        claim = preprocess_claim("The method improves accuracy by 40%.")
        chunks = [
            _chunk("c1", "Results", "The method improves accuracy by 12% on real tasks.", 0),
            _chunk("c2", "References", "Unrelated citation list.", 1),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert ranked[0].chunk_id == "c1"
        assert ranked[0].relevance_score > ranked[1].relevance_score

    def test_keyword_overlap(self) -> None:
        claim = preprocess_claim("accuracy improved on software development tasks")
        chunks = [
            _chunk("c1", "Results", "We measured accuracy on software development tasks.", 0),
            _chunk("c2", "Introduction", "This paper discusses unrelated biology.", 1),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert ranked[0].chunk_id == "c1"
        assert ranked[0].claim_overlap > ranked[1].claim_overlap

    def test_irrelevant_chunk_ranks_low(self) -> None:
        claim = preprocess_claim("accuracy improved by 40%")
        chunks = [
            _chunk("c1", "Results", "The weather was sunny during the experiments.", 0),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert ranked[0].relevance_score < 0.3

    def test_numeric_overlap_with_different_values(self) -> None:
        claim = preprocess_claim("The method improves accuracy by 40%.")
        chunks = [
            _chunk("c1", "Results", "The proposed method improves accuracy by 12%.", 0),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert ranked[0].numeric_overlap == 0.5
        assert ranked[0].claim_numbers == ["40%"]
        assert ranked[0].evidence_numbers == ["12%"]

    def test_numeric_claim_without_numeric_evidence(self) -> None:
        claim = preprocess_claim("The method improves accuracy by 40%.")
        chunks = [
            _chunk("c1", "Results", "The method improves accuracy on real tasks.", 0),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert ranked[0].numeric_overlap == 0.0

    def test_section_weighting(self) -> None:
        claim = preprocess_claim("accuracy improved")
        shared = "The experiment reports improved accuracy in the benchmark."
        chunks = [
            _chunk("c1", "Results", shared, 0),
            _chunk("c2", "References", shared, 1),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert len(ranked) == 1
        assert ranked[0].chunk_id == "c1"

    def test_deterministic_ordering(self) -> None:
        claim = preprocess_claim("accuracy improved on software tasks")
        chunks = [
            _chunk("c1", "Results", "accuracy improved on software tasks significantly", 0),
            _chunk("c2", "Discussion", "accuracy improved on software tasks moderately", 1),
        ]

        first = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)
        second = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert [item.chunk_id for item in first] == [item.chunk_id for item in second]

    def test_scores_are_bounded(self) -> None:
        claim = preprocess_claim("accuracy improved by 40%")
        chunks = [
            _chunk("c1", "Results", "accuracy improved by 40% on software tasks", 0),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert 0.0 <= ranked[0].relevance_score <= 1.0
        assert 0.0 <= ranked[0].claim_overlap <= 1.0
        assert 0.0 <= ranked[0].numeric_overlap <= 1.0

    def test_duplicate_chunks_are_deduped(self) -> None:
        claim = preprocess_claim("accuracy improved")
        chunk = _chunk("c1", "Results", "accuracy improved on benchmark", 0)
        ranked = rank_evidence_for_claim(claim, [chunk, chunk], min_relevance=0.0)

        assert len(ranked) == 1

    def test_duplicate_evidence_text_keeps_highest_score(self) -> None:
        claim = preprocess_claim("Cas9 can be directed by RNA to cleave DNA.")
        shared_text = (
            "Cas9 can be directed by RNA to introduce site-specific "
            "double-stranded breaks in target DNA."
        )
        chunks = [
            _chunk("permalink:63", "PERMALINK", shared_text, 63),
            _chunk("permalink:90", "PERMALINK", shared_text, 90),
            _chunk(
                "results:1",
                "Results",
                "In vitro assays confirmed programmable RNA-guided DNA cleavage by Cas9.",
                1,
            ),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert len(ranked) == 2
        assert {item.chunk_id for item in ranked} == {"permalink:63", "results:1"}
        permalink_items = [item for item in ranked if item.chunk_id.startswith("permalink:")]
        assert len(permalink_items) == 1
        assert permalink_items[0].chunk_id == "permalink:63"

    def test_valid_distinct_evidence_is_preserved(self) -> None:
        claim = preprocess_claim("Cas9 RNA DNA cleavage")
        chunks = [
            _chunk("c1", "Abstract", "Cas9 uses RNA guides for DNA cleavage.", 0),
            _chunk("c2", "Results", "The endonuclease introduces double-stranded breaks.", 1),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert len(ranked) == 2
        assert {item.chunk_id for item in ranked} == {"c1", "c2"}

    def test_maximum_evidence_limit(self) -> None:
        claim = preprocess_claim("accuracy improved on benchmark tasks")
        chunks = [
            _chunk(f"c{i}", "Results", f"accuracy improved in experiment {i}", i)
            for i in range(10)
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert len(ranked) <= EVIDENCE_TOP_K

    def test_diverse_selection_avoids_near_duplicate_passages(self) -> None:
        claim = preprocess_claim(CAS9_CLAIM)
        base = (
            "Cas9 can be programmed with guide RNA to cleave specific "
            "double-stranded DNA target sequences in vitro."
        )
        chunks = [
            _chunk("a", "Results", base, 0),
            _chunk("b", "Results", base + " Additional experimental detail.", 1),
            _chunk("c", "Discussion", "PAM sequences are required adjacent to the target.", 2),
            _chunk("d", "Methods", "Guide RNA was engineered as a single chimeric transcript.", 3),
            _chunk("e", "Conclusion", "Cas9 introduces double-stranded breaks at target DNA.", 4),
            _chunk("f", "Introduction", "DNA interference systems are widespread in bacteria.", 5),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert len(ranked) <= EVIDENCE_TOP_K
        assert len({normalize_evidence_text(item.text) for item in ranked}) == len(ranked)
        assert ranked[0].chunk_id == "a"

    def test_evidence_metadata_is_preserved(self) -> None:
        claim = preprocess_claim("accuracy improved")
        chunks = [
            EvidenceChunk(
                chunk_id="c1",
                paper_id="10.1000/test",
                section="Results",
                chunk_index=3,
                text="accuracy improved in practice",
                source_url="https://example.org/paper.pdf",
                page=7,
            )
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert ranked[0].chunk_id == "c1"
        assert ranked[0].section == "Results"
        assert ranked[0].chunk_index == 3
        assert ranked[0].text == "accuracy improved in practice"
        assert ranked[0].source_url == "https://example.org/paper.pdf"
        assert ranked[0].page == 7

    def test_missing_section_and_page_are_preserved(self) -> None:
        claim = preprocess_claim("accuracy improved")
        chunks = [
            EvidenceChunk(
                chunk_id="c1",
                paper_id="10.1000/test",
                section="",
                chunk_index=0,
                text="accuracy improved in practice",
            )
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)

        assert ranked[0].section == "Unknown"
        assert ranked[0].page is None
        assert ranked[0].source_url is None


class TestCas9PaperRegression:
    def test_cas9_claim_selects_relevant_scientific_evidence(self) -> None:
        claim = preprocess_claim(CAS9_CLAIM)
        chunks = [
            _chunk(
                "intro",
                "Introduction",
                "DNA interference systems are widespread in bacteria and archaea.",
                0,
            ),
            _chunk(
                "mechanism",
                "Results",
                "Cas9 can be programmed with guide RNA to cleave specific double-stranded DNA target sequences.",
                1,
            ),
            _chunk(
                "pam",
                "Discussion",
                "Target recognition requires a PAM sequence adjacent to the protospacer.",
                2,
            ),
            _chunk(
                "fig",
                "Fig. 4. PAM requirement",
                "A PAM is required to license target DNA cleavage by the Cas9 complex.",
                3,
            ),
            _chunk(
                "generic",
                "References",
                "DNA molecules contain nucleotide bases.",
                4,
            ),
        ]

        ranked = rank_evidence_for_claim(claim, chunks, min_relevance=0.0)
        combined = " ".join(item.text.lower() for item in ranked)

        assert ranked[0].chunk_id == "mechanism"
        assert "cas9" in combined
        assert "guide rna" in combined or "rna" in combined
        assert "double-stranded dna" in combined or "dsdna" in combined
        assert "cleave" in combined or "break" in combined
        assert "pam" in combined
        assert all("permalink" not in item.section.lower() for item in ranked)
