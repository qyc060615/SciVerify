"""Bounded positive recovery and preservation of real references/old outcomes."""
import hashlib
from types import SimpleNamespace

import pytest

from app.researchguard.domain import EvidenceChunk, SourceDocument, VerificationResult, VerificationTraceability, Reference
from app.services.bibliographic_recovery import recover_bibliographic_result
from app.services.reference_notice import is_unreferenced_publisher_notice
from app.services.claim_attribution import ProposalRejected
from app.tests.test_citation_context import manuscript
from app.tests.test_claim_attribution import check, proposal
from app.tests.test_grobid_tei import tei, bibliography, MANUSCRIPT
from app.researchguard.adapters.grobid_tei import parse_tei


@pytest.mark.parametrize("prefix", ["In", "According to", "As shown in", "As described in", "As reported in"])
def test_narrative_prefix_recovers_same_sentence(prefix):
    text = f"{prefix} [3], Smith et al. measured a 5% increase."
    parsed = manuscript(text)
    result = check(parsed, proposal("Smith et al. measured a 5% increase"))
    assert result.attribution_status == "resolved" and result.reference_ids == ("r3",)
    assert parsed.paragraphs[0].text[result.source_spans[0].start:result.source_spans[0].end] == "Smith et al. measured a 5% increase"


def test_prefix_never_infers_labels_or_expands_competing_sources():
    parsed = manuscript("In [3], Smith measured a 5% increase.")
    assert check(parsed, proposal("Smith measured a 5% increase", ids=())).attribution_status == "ambiguous"
    with pytest.raises(ProposalRejected):
        check(parsed, proposal("Smith measured a 5% increase", ids=("4",)))
    parsed = manuscript("In [3], Smith measured a 5% increase but Jones reported a decrease [4].")
    assert check(parsed, proposal("Smith measured a 5% increase")).attribution_status == "ambiguous"
    parsed = manuscript("We used [3], and our experiment measured an increase.")
    assert check(parsed, proposal("our experiment measured an increase")).attribution_status == "ambiguous"


NOTICE = "Disclaimer/Publisher’s Note: The statements, opinions and data are those of the authors."


@pytest.mark.parametrize("update", [
    {"raw_text": "An incomplete but valid article"}, {"raw_text": "Publisher's Note: Correction"},
    {"authors": ("A Author",)}, {"year": 2020}, {"doi": "10.1234/real"},
    {"url": "https://example.org/paper"}, {"journal": "Some Journal"},
    {"raw_text": NOTICE + " doi:10.1234/real"}, {"raw_text": NOTICE + " ISBN 123"},
])
def test_notice_filter_preserves_normal_or_identifiable_entries(update):
    ref = Reference(id="r", manuscript_id="m", raw_text=NOTICE).model_copy(update=update)
    assert not is_unreferenced_publisher_notice(ref, set())


def test_notice_filter_respects_citations_and_preserves_parse_audit():
    ref = Reference(id="r", manuscript_id="m", raw_text=NOTICE)
    assert is_unreferenced_publisher_notice(ref, set())
    assert not is_unreferenced_publisher_notice(ref, {"r"})
    back = bibliography(("b0", "A valid incomplete book"), ("b1", NOTICE), ("b2", "Another book"))
    parsed = parse_tei(tei('<p><s>A result <ref type="bibr" target="#b0">[1]</ref>.</s></p>', back), MANUSCRIPT)
    assert [r.id.rsplit(":", 1)[-1] for r in parsed.references] == ["0", "2"]
    note = next(d for d in parsed.diagnostics if d.code == "PUBLISHER_NOTICE_EXCLUDED")
    assert NOTICE in note.safe_message and note.entity_id.endswith(":1")
    cited = parse_tei(tei('<p><s>A result <ref type="bibr" target="#b1">[2]</ref>.</s></p>', back), MANUSCRIPT)
    assert len(cited.references) == 3 and cited.citation_callouts[0].resolution_status == "resolved"


def setup_metadata(html=None):
    content = (html or '<html><head><meta name="citation_title" content="Quantum Study 2">'
               '<meta name="citation_author" content="Ada Smith"></head></html>').encode()
    source = SourceDocument(id="s", reference_id="r", doi="10.1234/source", retrieval_status="available",
                            content_hash="sha256:" + hashlib.sha256(content).hexdigest())
    result = VerificationResult(claim_id="c", processing_status="completed", verdict="INSUFFICIENT", confidence=.6,
        evidence_chunks=(EvidenceChunk(id="e", source_document_id="s", text="Some actual body text"),),
        explanation="Original insufficient explanation", traceability=VerificationTraceability(evidence_ids=("e",)))
    artifact = SimpleNamespace(content=content, format="html", provenance=SimpleNamespace(identity="EXACT_IDENTITY"))
    return source, result, SimpleNamespace(get=lambda doi: artifact), artifact


@pytest.mark.parametrize("claim", ['The study is titled "Quantum Study 2".',
                                 'A review by Dr. Smith et al. is titled "Quantum Study 2".'])
def test_source_metadata_proves_only_pure_matching_bibliographic_assertion(claim):
    source, result, store, _ = setup_metadata()
    recovered = recover_bibliographic_result(claim, result, source, store=store)
    assert recovered.verdict == "SUPPORTED" and recovered.confidence == result.confidence
    assert recovered.evidence_chunks == result.evidence_chunks
    assert recovered.traceability.evidence_ids == ("e",)
    proof = recovered.traceability.metadata["bibliographic_recovery"]
    assert proof["source_hash"] == source.content_hash and proof["original_explanation"] == result.explanation
    assert "page" not in proof


@pytest.mark.parametrize("claim", ['The study is titled "Quantum Study 3".',
    'The study by Jones et al. is titled "Quantum Study 2".',
    'The study is not titled "Quantum Study 2".',
    'The study is titled "Quantum Study 2" and proves a 50% improvement.',
    'The study reported a 50% improvement.'])
def test_metadata_does_not_prove_wrong_title_wrong_author_or_scientific_content(claim):
    source, result, store, _ = setup_metadata()
    assert recover_bibliographic_result(claim, result, source, store=store) is result


@pytest.mark.parametrize("verdict", ["SUPPORTED", "OVERSTATED", "CONTRADICTED"])
def test_existing_non_insufficient_verdicts_are_untouched(verdict):
    source, result, store, _ = setup_metadata()
    result = result.model_copy(update={"verdict": verdict})
    assert recover_bibliographic_result('The study is titled "Quantum Study 2".', result, source, store=store) is result


def test_coauthor_is_not_accepted_as_first_author():
    source, result, store, artifact = setup_metadata('<meta name="citation_title" content="Quantum Study 2">'
        '<meta name="citation_author" content="Ada Smith"><meta name="citation_author" content="Jane Jones">')
    assert recover_bibliographic_result('The study by Jones et al. is titled "Quantum Study 2".', result, source, store=store) is result
    source = source.model_copy(update={"retrieval_status": "unavailable"})
    assert recover_bibliographic_result('The study is titled "Quantum Study 2".', result, source, store=store) is result


@pytest.mark.parametrize("failure", ["hash", "identity", "format", "missing_metadata", "no_evidence"])
def test_metadata_failure_falls_back_without_rejecting_old_result(failure):
    source, result, store, artifact = setup_metadata()
    if failure == "hash": source = source.model_copy(update={"content_hash": "sha256:wrong"})
    if failure == "identity": artifact.provenance.identity = "IDENTITY_UNCERTAIN"
    if failure == "format": artifact.format = "pdf"
    if failure == "missing_metadata":
        source, result, store, artifact = setup_metadata('<html><body>Quantum Study 2, Ada Smith</body></html>')
    if failure == "no_evidence": result = result.model_copy(update={"evidence_chunks": ()})
    assert recover_bibliographic_result('The study is titled "Quantum Study 2".', result, source, store=store) is result
