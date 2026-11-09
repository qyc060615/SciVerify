"""Offline paired regressions for bounded extraction and quote recovery."""
import pytest

from app.services.claim_attribution import ProposalRejected, grounded_span, validate_proposal
from app.services.citation_context import build_contexts
from app.services.verification_validator import _has_grounded_counterevidence, validate_verification_result
from app.tests.test_citation_context import manuscript
from app.tests.test_claim_attribution import check, proposal
from app.tests.test_claim_extractor import FakeProvider, run
from app.tests.test_verification_validator import _adjudicator, _strong_evidence, _prosecutor, _defender
from app.researchguard.domain import TextSpan


@pytest.mark.parametrize("join", ["but", "while", "whereas", ";"])
def test_single_terminal_group_recovers_parallel_clauses(join):
    text = f"Treatment reduced mortality {join} did not shorten admission [3]."
    parsed = manuscript(text)
    context = build_contexts(parsed)[0].context
    for quote in ("Treatment reduced mortality", f"{join} did not shorten admission"):
        result = validate_proposal(parsed, context, proposal(quote))
        assert result.claim.attribution_status == "resolved"
        assert result.claim.reference_ids == ("r3",)
        if quote == "Treatment reduced mortality" or join != ";":
            assert "SAME_SENTENCE_CITATION_RECOVERED" in {d.code for d in result.diagnostics}
    assert check(parsed, proposal("Treatment reduced mortality", ids=())).attribution_status == "ambiguous"


def test_shared_scope_does_not_cross_local_ownership_or_paragraph_sentences():
    parsed = manuscript("Treatment reduced mortality [3] but prolonged admission [4].")
    with pytest.raises(ProposalRejected):
        check(parsed, proposal("Treatment reduced mortality", ids=("4",)))
    parsed = manuscript("Treatment reduced mortality. It prolonged admission [3].", sentences=[])
    assert check(parsed, proposal("Treatment reduced mortality")).attribution_status == "ambiguous"
    parsed = manuscript("Treatment reduced mortality but prolonged admission [3][4].")
    assert check(parsed, proposal("Treatment reduced mortality")).attribution_status == "ambiguous"


@pytest.mark.parametrize("source,quote", [
    ("A improves accuracy", "A  improves accuracy"),
    ("A\n improves\taccuracy", "A improves accuracy"),
    ("A\u00a0improves accuracy", "A improves accuracy"),
])
def test_whitespace_grounding_retains_original_span(source, quote):
    parsed = manuscript(source + " [3].")
    context = build_contexts(parsed)[0].context
    result = validate_proposal(parsed, context, proposal("A improves accuracy", quote))
    span = result.claim.source_spans[0]
    assert parsed.paragraphs[0].text[span.start:span.end] == source
    assert "QUOTE_WHITESPACE_RECOVERED" in {d.code for d in result.diagnostics}


def test_whitespace_recovery_cannot_disambiguate_repetition_or_repair_numbers():
    text = "A improves accuracy; A  improves accuracy"
    with pytest.raises(ProposalRejected) as failure:
        grounded_span(text, "A\timproves accuracy", TextSpan(start=0, end=len(text)))
    assert failure.value.code == "QUOTE_AMBIGUOUS"
    for quote in ("Dose was 60 mg", "Dose was not 6 mg"):
        text = "Dose was 6 mg"
        with pytest.raises(ProposalRejected):
            grounded_span(text, quote, TextSpan(start=0, end=len(text)))


def test_mixed_schema_candidates_keep_valid_items_and_original_indices():
    good = dict(text="A improves accuracy", evidence_quote="A improves accuracy",
                attribution_intent="cited", citation_labels=["3"])
    result = run(manuscript(), provider=FakeProvider(lambda p: {"claims": [
        {**good, "unexpected": "private"}, good, {**good, "citation_labels": "3"}]}))
    assert result.status == "partial" and len(result.claims) == 1
    rejected = result.context_results[0].rejected_proposals
    assert [p.proposal_index for p in rejected] == [0, 2]
    assert all(p.reason_code == "EXTRACTION_INVALID_RESPONSE" for p in rejected)
    assert "private" not in result.model_dump_json()


def test_all_bad_schema_candidates_remain_failed_with_individual_indices():
    result = run(manuscript(), provider=FakeProvider(lambda p: {"claims": [{"text": "bad"}, None]}))
    assert result.status == "failed" and not result.claims
    assert [p.proposal_index for p in result.context_results[0].rejected_proposals] == [0, 1]


@pytest.mark.parametrize("opening,closing", [('"', '"'), ("'", "'"), ('“', '”'), ('‘', '’'), ('「', '」'), ('『', '』')])
def test_real_counterquote_typography_preserves_negative_verdict(opening, closing):
    evidence = [_strong_evidence(text="Median recovery was 10 days with treatment; placebo required 15 days.")]
    judge = _adjudicator(verdict="CONTRADICTS", supporting_evidence=[], contradicting_evidence=["c1"],
                         reasoning=f"The source states {opening}Median recovery was 10 days with treatment.{closing}")
    result = validate_verification_result(claim="Treatment recovery was 15 days", evidence=evidence,
        prosecutor=_prosecutor(), defender=_defender(), adjudicator=judge)
    assert result.verdict == "CONTRADICTS"


@pytest.mark.parametrize("quote", [
    "Median recovery was 15 days with treatment.",
    "Median recovery was not 10 days with treatment.",
    "Median recovery was 10 days with placebo.",
    "Median recovery was 10 hours with treatment.",
    "Median recovery was -10 days with treatment.",
])
def test_counterquote_content_changes_are_not_format_recovery(quote):
    judge = _adjudicator(reasoning=f"'{quote}'", contradicting_evidence=["c1"])
    assert not _has_grounded_counterevidence(judge, [_strong_evidence(
        text="Median recovery was 10 days with treatment; placebo required 15 days.")])


def test_short_numeric_quote_cannot_match_longer_decimal_or_wrong_evidence():
    judge = _adjudicator(reasoning="'Reported mortality was 22.9;'", contradicting_evidence=["c1"])
    assert not _has_grounded_counterevidence(judge, [_strong_evidence(text="Reported mortality was 22.95 percent.")])
    judge = judge.model_copy(update={"reasoning": "'Median recovery was 10 days.'", "contradicting_evidence": ["other"]})
    assert not _has_grounded_counterevidence(judge, [_strong_evidence(text="Median recovery was 10 days.")])


def test_wrapped_double_quote_and_apostrophe_are_source_grounded():
    judge = _adjudicator(reasoning='"Patients\n did not improve with treatment."', contradicting_evidence=["c1"])
    assert _has_grounded_counterevidence(judge, [_strong_evidence(text="Patients did not improve with treatment;")])
    judge = judge.model_copy(update={"reasoning": "'The patient's recovery required 10 days.'"})
    assert _has_grounded_counterevidence(judge, [_strong_evidence(text="The patient's recovery required 10 days;")])
