from __future__ import annotations

import pytest

from app.schemas.paper import DocumentSection
from app.services.evidence_chunker import chunk_sections


def _section(name: str, text: str, order: int) -> DocumentSection:
    return DocumentSection(section_name=name, text=text, order=order)


class TestEvidenceChunker:
    def test_chunks_generated(self) -> None:
        sections = [
            _section(
                "Results",
                "Sentence one.\n\nSentence two with more detail about outcomes.",
                0,
            )
        ]
        chunks = chunk_sections(sections, paper_id="10.1000/test", chunk_size=40, chunk_overlap=5)

        assert len(chunks) >= 1
        assert chunks[0].section == "Results"

    def test_section_metadata_preserved(self) -> None:
        sections = [
            _section("Methods", "Step one.\n\nStep two.", 0),
            _section("Discussion", "Interpretation paragraph.", 1),
        ]
        chunks = chunk_sections(sections, paper_id="10.1000/test", chunk_size=100, chunk_overlap=10)

        assert {chunk.section for chunk in chunks} == {"Methods", "Discussion"}

    def test_chunk_ordering_preserved(self) -> None:
        sections = [
            _section("Introduction", "Alpha paragraph.\n\nBeta paragraph.", 0),
        ]
        chunks = chunk_sections(sections, paper_id="10.1000/test", chunk_size=20, chunk_overlap=0)

        indices = [chunk.chunk_index for chunk in chunks]
        assert indices == sorted(indices)

    def test_overlap_behavior(self) -> None:
        text = "A" * 30 + "\n\n" + "B" * 30
        sections = [_section("Body", text, 0)]
        chunks = chunk_sections(sections, paper_id="10.1000/test", chunk_size=35, chunk_overlap=10)

        assert len(chunks) >= 2

    def test_short_section(self) -> None:
        sections = [_section("Conclusion", "Short.", 0)]
        chunks = chunk_sections(sections, paper_id="10.1000/test")

        assert len(chunks) == 1
        assert chunks[0].text == "Short."

    def test_empty_section(self) -> None:
        sections = [_section("References", "   ", 0)]
        chunks = chunk_sections(sections, paper_id="10.1000/test")

        assert chunks == []

    def test_chunk_ids_unique(self) -> None:
        sections = [
            _section(
                "Results",
                "First paragraph with enough content.\n\nSecond paragraph with enough content.",
                0,
            )
        ]
        chunks = chunk_sections(sections, paper_id="10.1000/test", chunk_size=30, chunk_overlap=5)
        chunk_ids = [chunk.chunk_id for chunk in chunks]

        assert len(chunk_ids) == len(set(chunk_ids))

    def test_invalid_overlap(self) -> None:
        sections = [_section("Body", "Some text.", 0)]
        with pytest.raises(ValueError):
            chunk_sections(sections, paper_id="10.1000/test", chunk_size=10, chunk_overlap=10)
