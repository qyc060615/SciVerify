"""Gold attribution, malicious valid IDs, exact grounding and limited semantics."""
import pytest
from pydantic import ValidationError

from app.schemas.claim_extraction import ClaimProposal, SourceQuote
from app.services.citation_context import build_contexts
from app.services.claim_attribution import ProposalRejected, validate_proposal
from app.tests.test_citation_context import manuscript


def proposal(text, quotes=None, ids=("callout:0",), **kwargs):
    return ClaimProposal(text=text, source_quotes=tuple(
        q if isinstance(q, SourceQuote) else SourceQuote(quote=q) for q in (quotes or [text])),
        citation_callout_ids=ids, **kwargs)


def check(parsed, proposed, index=0):
    return validate_proposal(parsed, build_contexts(parsed)[index].context, proposed).claim


@pytest.mark.parametrize("label,text,quote,refs", [
    ("A", "A improves accuracy [3].", "A improves accuracy", ("r3",)),
    ("H", "A improves accuracy [3–5].", "A improves accuracy", ("r3", "r5")),
    ("I", "A improves accuracy [3][4].", "A improves accuracy", ("r3", "r4")),
    ("L", "A did not improve accuracy [3].", "A did not improve accuracy", ("r3",)),
    ("M", "A may improve accuracy only on small datasets [3].", "A may improve accuracy only on small datasets", ("r3",)),
    ("N", "A improves accuracy by 5% compared with baseline B [3].", "A improves accuracy by 5% compared with baseline B", ("r3",)),
])
def test_gold_simple_range_adjacent_and_semantics(label, text, quote, refs):
    p = manuscript(text)
    c = check(p, proposal(quote, ids=tuple(x.id for x in p.citation_callouts)))
    assert c.attribution_status == "resolved" and c.reference_ids == refs
    assert [p.paragraphs[0].text[s.start:s.end] for s in c.source_spans] == [quote]
    assert all(r.doi is None for r in p.references)  # DOI readiness is not attribution.


@pytest.mark.parametrize("marker", ["[3]", "[3,4]"])
def test_gold_b_d_compound_shared_subject(marker):
    p = manuscript(f"A improves accuracy and reduces latency {marker}.")
    first = check(p, proposal("A improves accuracy"))
    second = check(p, proposal("A reduces latency", [SourceQuote(quote="A", role="shared_subject"), "reduces latency"]))
    assert first.reference_ids == second.reference_ids == p.citation_callouts[0].reference_ids
    assert len(second.source_spans) == 2 and second.attribution_status == "resolved"


def test_gold_c_clause_local():
    p = manuscript("A improves accuracy [3], while B reduces latency [4].")
    assert check(p, proposal("A improves accuracy")).reference_ids == ("r3",)
    assert check(p, proposal("B reduces latency", ids=("callout:1",))).reference_ids == ("r4",)


@pytest.mark.parametrize("prefix,suffix", [("Previous work", "reports that A improves accuracy"), ("Smith et al.", "showed that A improves accuracy")])
def test_gold_e_f_reporting_frame(prefix, suffix):
    p = manuscript(f"{prefix} [3] {suffix}.")
    c = check(p, proposal(f"{prefix} {suffix}", [prefix, suffix]))
    assert c.attribution_status == "resolved" and c.reference_ids == ("r3",)


def test_gold_g_trailing_marker():
    p = manuscript("A improves accuracy. [3]", [(0, 20), (21, 24)])
    assert check(p, proposal("A improves accuracy")).attribution_status == "resolved"


def test_gold_j_separate_contexts():
    first = "A improves accuracy [3]."
    text = first + " B reduces latency [4]."
    p = manuscript(text, [(0, len(first)), (len(first) + 1, len(text))])
    assert check(p, proposal("A improves accuracy")).reference_ids == ("r3",)
    assert check(p, proposal("B reduces latency", ids=("callout:1",)), 1).reference_ids == ("r4",)


def test_gold_k_shared_subject_cannot_widen_scope():
    p = manuscript("Although A improved accuracy [3], it increased latency [4].")
    assert check(p, proposal("A improved accuracy")).reference_ids == ("r3",)
    second = proposal("A increased latency", [SourceQuote(quote="A", role="shared_subject", left_anchor="Although "), "increased latency"], ids=("callout:1",))
    assert check(p, second).reference_ids == ("r4",)


def test_wv1_swapped_valid_ids_rejected():
    p = manuscript("A improves accuracy [3], while B reduces latency [4].")
    for q, ids in [("A improves accuracy", ("callout:1",)), ("B reduces latency", ("callout:0",))]:
        with pytest.raises(ProposalRejected, match="attribution") as e:
            check(p, proposal(q, ids=ids))
        assert e.value.code == "WRONG_CITATION_SCOPE"


def test_wv2_neighbor_valid_id_rejected():
    first = "A improves accuracy [3]."
    text = first + " B reduces latency [4]."
    p = manuscript(text, [(0, len(first)), (len(first) + 1, len(text))])
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("A improves accuracy", ids=("callout:1",)))
    assert e.value.code == "UNKNOWN_CITATION_CALLOUT"
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("B reduces latency"))
    assert e.value.code == "QUOTE_NOT_FOUND"


def test_wv3_narrative_swapped_rejected():
    p = manuscript("Smith [3] reports accuracy, while Jones [4] reports latency.")
    for text, parts, ids in [("Smith reports accuracy", ["Smith", "reports accuracy"], ("callout:1",)), ("Jones reports latency", ["Jones", "reports latency"], ("callout:0",))]:
        with pytest.raises(ProposalRejected) as e:
            check(p, proposal(text, parts, ids))
        assert e.value.code == "WRONG_CITATION_SCOPE"


def test_wv4_shared_subject_wrong_group_rejected():
    p = manuscript("Although A improved accuracy [3], it increased latency [4].")
    q = proposal("A increased latency", [SourceQuote(quote="A", role="shared_subject", left_anchor="Although "), "increased latency"])
    with pytest.raises(ProposalRejected) as e:
        check(p, q)
    assert e.value.code == "WRONG_CITATION_SCOPE"


def test_wv5_union_foreign_groups_rejected():
    p = manuscript("A improves accuracy [3], while B reduces latency [4][5].")
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("A improves accuracy", ids=tuple(c.id for c in p.citation_callouts)))
    assert e.value.code == "WRONG_CITATION_SCOPE"


def test_wv6_repeated_quote_no_citation_disambiguation():
    p = manuscript("A improves accuracy [3], while A improves accuracy [4].")
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("A improves accuracy"))
    assert e.value.code == "QUOTE_AMBIGUOUS"
    c = check(p, proposal("A improves accuracy", [SourceQuote(quote="A improves accuracy", left_anchor="while ")], ids=("callout:1",)))
    assert c.reference_ids == ("r4",)


@pytest.mark.parametrize("source,changed,quote", [
    ("A did not improve accuracy", "A improved accuracy", None),
    ("A may improve accuracy", "A improves accuracy", None),
    ("A improves accuracy by 5%", "A improves accuracy by 50%", None),
    ("A improves accuracy only on small datasets", "A improves accuracy", "A improves accuracy"),
    ("A improves accuracy compared with baseline B", "A improves accuracy compared with baseline C", None),
])
def test_obvious_semantic_drift_rejected(source, changed, quote):
    p = manuscript(source + " [3].")
    with pytest.raises(ProposalRejected):
        check(p, proposal(changed, [quote or source]))


@pytest.mark.parametrize("source,parts,code", [
    ("A did not improve accuracy", ["A", "improve accuracy"], "SEMANTIC_MODIFIER_DRIFT"),
    ("A may improve accuracy", ["A", "improve accuracy"], "SEMANTIC_MODIFIER_DRIFT"),
    ("A improves accuracy by 5%", ["A improves accuracy"], "SEMANTIC_NUMERIC_DRIFT"),
])
def test_exact_parts_still_cannot_drop_modifiers(source, parts, code):
    with pytest.raises(ProposalRejected) as e:
        check(manuscript(source + " [3]."), proposal(" ".join(parts), parts))
    assert e.value.code == code


@pytest.mark.parametrize("quote", ["a improves accuracy", "A  improves accuracy", "A improves accuracý"])
def test_no_case_whitespace_unicode_repair(quote):
    with pytest.raises(ProposalRejected) as e:
        check(manuscript(), proposal(quote))
    assert e.value.code == "QUOTE_NOT_FOUND"


@pytest.mark.parametrize("parts,code", [(["improves accuracy", "A"], "INVALID_SOURCE_SPAN_ORDER"), (["A improves accuracy", "accuracy"], "INVALID_SOURCE_SPAN_ORDER"), (["A improves accuracy [3]"], "CITATION_MARKER_AS_SOURCE")])
def test_source_span_order_overlap_marker(parts, code):
    with pytest.raises(ProposalRejected) as e:
        check(manuscript(), proposal(" ".join(parts), parts))
    assert e.value.code == code


def test_abstention_and_group_subset_remove_all_links():
    p = manuscript("A improves accuracy [3][4].")
    for q in [proposal("A improves accuracy"), proposal("A improves accuracy", ids=("callout:0", "callout:1"), association="abstain")]:
        c = check(p, q)
        assert c.attribution_status == "ambiguous" and not c.reference_ids and not c.citation_callout_ids


def test_mixed_partial_cannot_be_resolved():
    p = manuscript("A improves accuracy [3], while B reduces latency [4].", statuses={1: "partial"})
    c = check(p, proposal("B reduces latency", ids=("callout:1",)))
    assert c.attribution_status == "unresolved" and c.reference_ids == ("r4",)


def test_fallback_single_group_cannot_bind_other_statement():
    p = manuscript("A improves accuracy. B reduces latency [3].", sentences=[])
    c = check(p, proposal("A improves accuracy"))
    assert c.attribution_status == "ambiguous" and not c.reference_ids
    assert check(p, proposal("B reduces latency")).attribution_status == "resolved"


@pytest.mark.parametrize("unit", ["%", " mg", " ms", " seconds"])
def test_exact_quote_cannot_drop_numeric_unit(unit):
    p = manuscript(f"A improves accuracy by 5{unit} [3].")
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("A improves accuracy by 5"))
    assert e.value.code == "SEMANTIC_NUMERIC_DRIFT"


def test_b9_trimmed_current_focal_rejects_reattached_marker_source_and_id():
    from app.tests.test_citation_context import boundary_manuscript
    p = boundary_manuscript("A supports T-cell responses.", "8 B shows higher titers [9].", ("8", "[9]"))
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("B shows higher titers", ids=("callout:0",)), 1)
    assert e.value.code == "UNKNOWN_CITATION_CALLOUT"
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("8 B shows higher titers", ids=("callout:1",)), 1)
    assert e.value.code == "QUOTE_NOT_FOUND"
    c = check(p, proposal("B shows higher titers", ids=("callout:1",)), 1)
    assert c.attribution_status == "resolved" and c.reference_ids == ("r1",)
    assert all(s.start >= p.citation_callouts[0].span.end for s in c.source_spans)
    assert check(p, proposal("A supports T-cell responses")).reference_ids == ("r0",)


def test_boundary_partial_group_is_never_promoted_to_resolved():
    from app.researchguard.domain import CitationResolutionStatus
    from app.tests.test_citation_context import boundary_manuscript
    p = boundary_manuscript("A supports T-cell responses.", "8,9 B shows higher titers.", ("8", "9"))
    calls = (p.citation_callouts[0], p.citation_callouts[1].model_copy(update={"resolution_status": CitationResolutionStatus.PARTIAL}))
    p = p.model_copy(update={"citation_callouts": calls})
    c = check(p, proposal("A supports T-cell responses", ids=("callout:0", "callout:1")))
    assert c.attribution_status == "unresolved"


@pytest.mark.parametrize("extra", ["reference_ids", "offsets", "verdict", "confidence", "DOI", "reasoning", "start", "end"])
def test_proposal_forbids_model_authority_fields(extra):
    data = proposal("A improves accuracy").model_dump()
    data[extra] = "untrusted"
    with pytest.raises(ValidationError):
        ClaimProposal.model_validate(data)


@pytest.mark.parametrize("subject,predicate", [
    ("The favorable safety profile observed during phase 1 testing of BNT162b2",
     "was confirmed in the phase 2/3 portion of the trial"),
    ("Findings from studies conducted in the United States and Germany among healthy men and women",
     "showed that two 30-μg doses of BNT162b2 elicited high neutralizing antibody titers"),
])
def test_sr_long_local_and_reporting_subjects_resolved(subject, predicate):
    p = manuscript(f"{subject} {predicate} [3].")
    c = check(p, proposal(f"{subject} {predicate}", [
        SourceQuote(quote=subject, role="subject"), SourceQuote(quote=predicate, role="predicate")]))
    assert c.attribution_status == "resolved" and c.reference_ids == ("r3",)
    assert [p.paragraphs[0].text[s.start:s.end] for s in c.source_spans] == [subject, predicate]


@pytest.mark.parametrize("subject", ["A", "Long phrase A"])
@pytest.mark.parametrize("association", ["proposed", "abstain"])
def test_sr_subject_cannot_borrow_from_wrong_clause(subject, association):
    p = manuscript(f"{subject} improves accuracy [3], while B reduces latency [4].")
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal(f"{subject} reduces latency", [
            SourceQuote(quote=subject, role="subject"), "reduces latency"], association=association))
    assert e.value.code == "WRONG_CITATION_SCOPE"


def test_sr_subject_from_read_only_neighbor_rejected():
    first = "Long phrase A improves accuracy [3]."
    text = first + " B reduces latency [4]."
    p = manuscript(text, [(0, len(first)), (len(first) + 1, len(text))])
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("Long phrase A reduces latency", [
            SourceQuote(quote="Long phrase A", role="subject"), "reduces latency"],
            ids=("callout:1",)), 1)
    assert e.value.code == "QUOTE_NOT_FOUND"


def test_sr_subject_and_qualifier_require_predicate():
    with pytest.raises(ProposalRejected) as e:
        check(manuscript(), proposal("A improves accuracy", [
            SourceQuote(quote="A", role="subject"),
            SourceQuote(quote="improves accuracy", role="qualifier")]))
    assert e.value.code == "INVALID_ATOMIC_PROPOSITION"


@pytest.mark.parametrize("extra", ["reference_ids", "offsets", "verdict", "confidence", "reasoning"])
def test_sr_subject_quote_forbids_authority_fields(extra):
    with pytest.raises(ValidationError):
        SourceQuote.model_validate({"quote": "A", "role": "subject", extra: "untrusted"})


@pytest.mark.parametrize("subject,predicate", [
    ("The 30-μg doses", "elicited high titers"),
    ("The potentially favorable profile", "was confirmed experimentally"),
    ("Findings among healthy adults", "showed high titers"),
])
def test_sr_semantic_guards_include_subject(subject, predicate):
    p = manuscript(f"{subject} {predicate} [3].")
    assert check(p, proposal(f"{subject} {predicate}", [
        SourceQuote(quote=subject, role="subject"), predicate])).attribution_status == "resolved"
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal(predicate))
    assert e.value.code in {"SEMANTIC_NUMERIC_DRIFT", "SEMANTIC_MODIFIER_DRIFT", "SEMANTIC_SCOPE_DRIFT"}
