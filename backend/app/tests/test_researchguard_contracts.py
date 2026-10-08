"""Domain and boundary contracts, independent of future integration libraries."""
import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.researchguard.domain import (
    AtomicClaim, CitationCallout, CitationContext, EvidenceChunk, Job, JobEvent,
    Manuscript, Paragraph, ParsedManuscript, ProcessingStatus, Reference,
    RetrievalStatus, SourceDocument, SourceType, VerificationResult,
    VerificationTraceability, Verdict,
)
from app.researchguard.ports import EvidenceRetriever, ManuscriptParser
from app.researchguard.adapters.sciverify import map_sciverify_verdict
from app.schemas.verification import Verdict as SciVerifyVerdict


def manuscript_payload():
    return {
        "manuscript": {"id": "m1", "content_locator": "storage:manuscript.pdf"},
        "paragraphs": [{"id": "p1", "manuscript_id": "m1", "text": "Treatment reduces risk [1].", "order": 0}],
        "references": [{"id": "r1", "manuscript_id": "m1", "raw_text": "Author. Treatment study."}],
        "citation_callouts": [{"id": "c1", "manuscript_id": "m1", "paragraph_id": "p1", "text": "[1]", "reference_ids": ["r1"]}],
        "citation_contexts": [{"id": "ctx1", "manuscript_id": "m1", "paragraph_id": "p1", "text": "Treatment reduces risk [1].", "citation_callout_ids": ["c1"]}],
    }


def test_manuscript_claim_source_evidence_identity_chain_and_round_trip():
    parsed = ParsedManuscript.model_validate(manuscript_payload())
    context = parsed.citation_contexts[0]
    callout = parsed.citation_callouts[0]
    claim = AtomicClaim(
        id="claim1", manuscript_id=parsed.manuscript.id, text="Treatment reduces risk.",
        paragraph_id=context.paragraph_id, context_id=context.id,
        citation_callout_ids=context.citation_callout_ids, reference_ids=callout.reference_ids,
    )
    source = SourceDocument(
        id="source1", reference_id=claim.reference_ids[0], doi="10.1234/study",
        title="Treatment study", authors=("Author",), year=2025,
        content_locator="storage:source.pdf", content_hash="sha256:example",
        source_type=SourceType.REMOTE, provider="repository",
        retrieval_status=RetrievalStatus.AVAILABLE,
    )
    chunk = EvidenceChunk(id="chunk1", source_document_id=source.id, text="Risk decreased.", page=3, section="Results", retrieval_score=2.4)
    result = VerificationResult(
        claim_id=claim.id, processing_status=ProcessingStatus.COMPLETED,
        verdict=Verdict.PARTIALLY_SUPPORTED, confidence=0.7,
        evidence_chunks=(chunk,), explanation="Limited population coverage.",
        traceability=VerificationTraceability(evidence_ids=(chunk.id,), method="test"),
    )
    assert parsed.references[0].id == source.reference_id
    assert result.evidence_chunks[0].source_document_id == source.id
    assert ParsedManuscript.model_validate_json(parsed.model_dump_json()) == parsed
    assert VerificationResult.model_validate_json(result.model_dump_json()) == result
    job = Job(id="job1", manuscript_id=parsed.manuscript.id)
    event = JobEvent(job_id=job.id, sequence=0, event_type="claim_processed", status=result.processing_status, claim_id=claim.id)
    assert event.claim_id == result.claim_id
    assert job.status == ProcessingStatus.PENDING


@pytest.mark.parametrize("collection,field,value", [
    ("paragraphs", "manuscript_id", "other"),
    ("references", "manuscript_id", "other"),
    ("citation_callouts", "manuscript_id", "other"),
    ("citation_contexts", "manuscript_id", "other"),
    ("citation_callouts", "paragraph_id", "unknown"),
    ("citation_callouts", "reference_ids", ["unknown"]),
    ("citation_contexts", "paragraph_id", "unknown"),
    ("citation_contexts", "citation_callout_ids", ["unknown"]),
])
def test_parser_output_rejects_broken_relationships(collection, field, value):
    payload = manuscript_payload()
    payload[collection][0][field] = value
    with pytest.raises(ValidationError):
        ParsedManuscript.model_validate(payload)


@pytest.mark.parametrize("collection", ["paragraphs", "references", "citation_callouts", "citation_contexts"])
def test_parser_output_rejects_duplicate_identity(collection):
    payload = manuscript_payload()
    payload[collection].append(payload[collection][0].copy())
    with pytest.raises(ValidationError, match="Duplicate IDs"):
        ParsedManuscript.model_validate(payload)


def test_context_cannot_link_callout_in_another_paragraph():
    payload = manuscript_payload()
    payload["paragraphs"].append({"id": "p2", "manuscript_id": "m1", "text": "Another paragraph.", "order": 1})
    payload["citation_contexts"][0]["paragraph_id"] = "p2"
    with pytest.raises(ValidationError, match="same paragraph"):
        ParsedManuscript.model_validate(payload)


def test_unresolved_callout_is_representable_without_inventing_reference():
    payload = manuscript_payload()
    payload["references"] = []
    payload["citation_callouts"][0]["reference_ids"] = []
    parsed = ParsedManuscript.model_validate(payload)
    assert parsed.citation_callouts[0].reference_ids == ()


def test_evidence_allows_unknown_provenance_and_page_without_provider_objects():
    chunk = EvidenceChunk(id="e1", source_document_id="s1", text="Evidence")
    assert chunk.page is None and chunk.section is None and chunk.source_url is None
    assert chunk.retrieval_score is None and chunk.metadata == {}
    with pytest.raises(ValidationError):
        EvidenceChunk(id="e2", source_document_id="s1", text="Evidence", metadata={"external_object": object()})


@pytest.mark.parametrize("page", [0, -1, 1.5, True])
def test_pages_are_one_based_integers(page):
    with pytest.raises(ValidationError):
        EvidenceChunk(id="e1", source_document_id="s1", text="Evidence", page=page)


@pytest.mark.parametrize("text", ["", " "])
def test_identity_and_content_cannot_be_blank(text):
    with pytest.raises(ValidationError):
        Manuscript(id=text, content_locator="file.pdf")
    with pytest.raises(ValidationError):
        AtomicClaim(id="c1", manuscript_id="m1", text=text, paragraph_id="p1", context_id="ctx1")


def test_verdict_contract_is_exact_and_processing_failures_are_not_verdicts():
    assert {v.value for v in Verdict} == {
        "SUPPORTED", "PARTIALLY_SUPPORTED", "OVERSTATED", "CONTRADICTED", "INSUFFICIENT",
    }
    for status in (ProcessingStatus.SOURCE_UNAVAILABLE, ProcessingStatus.CITATION_UNRESOLVED, ProcessingStatus.SOURCE_MISMATCH):
        with pytest.raises(ValueError):
            Verdict(status.value)


@pytest.mark.parametrize("status", [s for s in ProcessingStatus if s != ProcessingStatus.COMPLETED])
def test_incomplete_pipeline_cannot_publish_semantic_outcome(status):
    result = VerificationResult(claim_id="c1", processing_status=status, explanation="Processing status only")
    assert result.verdict is None
    for outcome in ({"verdict": Verdict.CONTRADICTED}, {"confidence": 0.5}):
        with pytest.raises(ValidationError, match="Incomplete processing"):
            VerificationResult(claim_id="c1", processing_status=status, **outcome)
    for legacy_verdict in SciVerifyVerdict:
        assert map_sciverify_verdict(legacy_verdict, processing_status=status) is None


def test_completed_insufficient_is_valid_but_completed_without_verdict_is_not():
    assert VerificationResult(claim_id="c1", processing_status="completed", verdict="INSUFFICIENT").evidence_chunks == ()
    with pytest.raises(ValidationError, match="requires a semantic verdict"):
        VerificationResult(claim_id="c1", processing_status="completed")
    with pytest.raises(ValueError, match="requires a SciVerify verdict"):
        map_sciverify_verdict(None, processing_status=ProcessingStatus.COMPLETED)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan"), float("inf")])
def test_confidence_is_finite_and_bounded(confidence):
    with pytest.raises(ValidationError):
        VerificationResult(claim_id="c1", processing_status="completed", verdict="SUPPORTED", confidence=confidence)


def test_verification_traceability_must_link_unique_returned_evidence():
    chunk = EvidenceChunk(id="e1", source_document_id="s1", text="Evidence")
    with pytest.raises(ValidationError, match="absent from the result"):
        VerificationResult(claim_id="c1", processing_status="completed", verdict="SUPPORTED", evidence_chunks=(chunk,), traceability=VerificationTraceability(evidence_ids=("unknown",)))
    with pytest.raises(ValidationError, match="Duplicate evidence"):
        VerificationResult(claim_id="c1", processing_status="completed", verdict="SUPPORTED", evidence_chunks=(chunk, chunk))


@pytest.mark.parametrize("legacy,internal", [
    (SciVerifyVerdict.SUPPORTS, Verdict.SUPPORTED),
    (SciVerifyVerdict.OVERSTATED, Verdict.OVERSTATED),
    (SciVerifyVerdict.CONTRADICTS, Verdict.CONTRADICTED),
    (SciVerifyVerdict.INSUFFICIENT, Verdict.INSUFFICIENT),
    (SciVerifyVerdict.FABRICATED, Verdict.INSUFFICIENT),
])
def test_explicit_completed_legacy_verdict_mapping(legacy, internal):
    assert map_sciverify_verdict(legacy, processing_status=ProcessingStatus.COMPLETED) == internal


def test_invalid_legacy_verdict_or_processing_status_cannot_be_silently_mapped():
    with pytest.raises(ValueError):
        map_sciverify_verdict("source_mismatch", processing_status=ProcessingStatus.COMPLETED)
    with pytest.raises(ValueError):
        map_sciverify_verdict(SciVerifyVerdict.CONTRADICTS, processing_status="typo")


def test_ports_accept_domain_only_implementations():
    class FixtureParser:
        def parse(self, manuscript: Manuscript) -> ParsedManuscript:
            return ParsedManuscript(manuscript=manuscript)

    class FixtureRetriever:
        def retrieve(self, claim: AtomicClaim, source_document: SourceDocument, top_k: int) -> list[EvidenceChunk]:
            if top_k <= 0:
                raise ValueError("top_k must be positive")
            return [EvidenceChunk(id="e1", source_document_id=source_document.id, text=claim.text)]

    parser: ManuscriptParser = FixtureParser()
    retriever: EvidenceRetriever = FixtureRetriever()
    manuscript = Manuscript(id="m1", content_locator="fixture.pdf")
    claim = AtomicClaim(id="c1", manuscript_id="m1", text="Claim", paragraph_id="p1", context_id="ctx1")
    source = SourceDocument(id="s1", reference_id="r1")
    assert parser.parse(manuscript).manuscript == manuscript
    assert retriever.retrieve(claim, source, 1)[0].source_document_id == source.id
    with pytest.raises(ValueError):
        retriever.retrieve(claim, source, 0)


def test_core_dependency_direction():
    core = Path(__file__).resolve().parents[1] / "researchguard"
    # Adapters may import legacy schemas; domain/ports/package must not.
    allowed = {"__future__", "enum", "typing", "pydantic", "domain"}
    for path in core.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            assert all(module.split(".")[0] in allowed for module in modules), (path.name, modules)
