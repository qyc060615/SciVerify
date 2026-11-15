from __future__ import annotations

from app.config import CHUNK_OVERLAP, CHUNK_SIZE
from app.schemas.paper import DocumentSection, EvidenceChunk


def chunk_sections(
    sections: list[DocumentSection],
    paper_id: str,
    source_url: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[EvidenceChunk]:
    """Split parsed sections into evidence-ready chunks."""
    effective_chunk_size = chunk_size if chunk_size is not None else CHUNK_SIZE
    effective_overlap = chunk_overlap if chunk_overlap is not None else CHUNK_OVERLAP

    if effective_overlap >= effective_chunk_size:
        raise ValueError("Chunk overlap must be smaller than chunk size.")

    chunks: list[EvidenceChunk] = []
    global_index = 0

    for section in sections:
        section_chunks = _chunk_section_text(
            text=section.text,
            section_name=section.section_name,
            paper_id=paper_id,
            source_url=source_url,
            start_index=global_index,
            chunk_size=effective_chunk_size,
            chunk_overlap=effective_overlap,
        )
        chunks.extend(section_chunks)
        global_index += len(section_chunks)

    return chunks


def _chunk_section_text(
    text: str,
    section_name: str,
    paper_id: str,
    source_url: str | None,
    start_index: int,
    chunk_size: int,
    chunk_overlap: int,
) -> list[EvidenceChunk]:
    normalized = text.strip()
    if not normalized:
        return []

    paragraphs = [part.strip() for part in normalized.split("\n\n") if part.strip()]
    if not paragraphs:
        return []

    section_chunks: list[EvidenceChunk] = []
    buffer = ""
    chunk_index = 0

    def emit_chunk(chunk_text: str) -> None:
        nonlocal chunk_index
        cleaned = chunk_text.strip()
        if not cleaned:
            return
        section_chunks.append(
            EvidenceChunk(
                chunk_id=f"{paper_id}:{section_name}:{start_index + chunk_index}",
                paper_id=paper_id,
                section=section_name,
                chunk_index=start_index + chunk_index,
                text=cleaned,
                source_url=source_url,
                page=None,
                metadata={"section_order": chunk_index},
            )
        )
        chunk_index += 1

    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
        if len(candidate) <= chunk_size:
            buffer = candidate
            continue

        if buffer:
            emit_chunk(buffer)
            buffer = _overlap_tail(buffer, chunk_overlap)

        if len(paragraph) <= chunk_size:
            buffer = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
            continue

        start = 0
        while start < len(paragraph):
            end = min(start + chunk_size, len(paragraph))
            piece = paragraph[start:end].strip()
            if piece:
                emit_chunk(piece)
            if end >= len(paragraph):
                break
            start = max(end - chunk_overlap, start + 1)

        buffer = ""

    if buffer:
        emit_chunk(buffer)

    return section_chunks


def _overlap_tail(text: str, overlap: int) -> str:
    if overlap <= 0:
        return ""
    if len(text) <= overlap:
        return text
    return text[-overlap:].lstrip()
