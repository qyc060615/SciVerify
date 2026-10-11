"""Gold attribution, malicious valid IDs, exact grounding and evidence integrity."""
import pytest
from pydantic import ValidationError

from app.schemas.claim_extraction import ClaimProposal
from app.services.citation_context import build_contexts
from app.services.citation_labels import visible_labels
from app.services.claim_attribution import ProposalRejected, validate_proposal
from app.tests.test_citation_context import manuscript


def proposal(text, quote=None, ids=("3",)):
    return ClaimProposal(text=text, evidence_quote=quote or text, citation_labels=ids)


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
    c = check(p, proposal(quote, ids=tuple(label for c in p.citation_callouts for label in visible_labels(c.text))))
    assert c.attribution_status == "resolved" and c.reference_ids == refs
    assert [p.paragraphs[0].text[s.start:s.end] for s in c.source_spans] == [quote]
    assert all(r.doi is None for r in p.references)  # DOI readiness is not attribution.


@pytest.mark.parametrize("marker", ["[3]", "[3,4]"])
def test_gold_b_d_compound_contiguous_evidence(marker):
    p = manuscript(f"A improves accuracy and reduces latency {marker}.")
    labels = visible_labels(marker)
    first = check(p, proposal("A improves accuracy", ids=labels))
    second = check(p, proposal("A reduces latency", f"A improves accuracy and reduces latency {marker}.", ids=labels))
    assert first.reference_ids == second.reference_ids == p.citation_callouts[0].reference_ids
    assert len(second.source_spans) == 1 and second.attribution_status == "resolved"


def test_gold_c_clause_local():
    p = manuscript("A improves accuracy [3], while B reduces latency [4].")
    assert check(p, proposal("A improves accuracy")).reference_ids == ("r3",)
    assert check(p, proposal("B reduces latency", ids=("4",))).reference_ids == ("r4",)


@pytest.mark.parametrize("prefix,suffix", [("Previous work", "reports that A improves accuracy"), ("Smith et al.", "showed that A improves accuracy")])
def test_gold_e_f_reporting_frame(prefix, suffix):
    p = manuscript(f"{prefix} [3] {suffix}.")
    c = check(p, proposal(f"{prefix} {suffix}", f"{prefix} [3] {suffix}"))
    assert c.attribution_status == "resolved" and c.reference_ids == ("r3",)


def test_gold_g_trailing_marker():
    p = manuscript("A improves accuracy. [3]", [(0, 20), (21, 24)])
    assert check(p, proposal("A improves accuracy")).attribution_status == "resolved"


def test_gold_j_separate_contexts():
    first = "A improves accuracy [3]."
    text = first + " B reduces latency [4]."
    p = manuscript(text, [(0, len(first)), (len(first) + 1, len(text))])
    assert check(p, proposal("A improves accuracy")).reference_ids == ("r3",)
    assert check(p, proposal("B reduces latency", ids=("4",)), 1).reference_ids == ("r4",)


def test_wv1_swapped_valid_ids_rejected():
    p = manuscript("A improves accuracy [3], while B reduces latency [4].")
    for q, ids in [("A improves accuracy", ("4",)), ("B reduces latency", ("3",))]:
        with pytest.raises(ProposalRejected, match="attribution") as e:
            check(p, proposal(q, ids=ids))
        assert e.value.code == "WRONG_CITATION_SCOPE"


def test_wv2_neighbor_valid_id_rejected():
    first = "A improves accuracy [3]."
    text = first + " B reduces latency [4]."
    p = manuscript(text, [(0, len(first)), (len(first) + 1, len(text))])
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("A improves accuracy", ids=("4",)))
    assert e.value.code == "UNKNOWN_CITATION_CALLOUT"
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("B reduces latency"))
    assert e.value.code == "QUOTE_NOT_FOUND"


def test_wv3_narrative_swapped_rejected():
    p = manuscript("Smith [3] reports accuracy, while Jones [4] reports latency.")
    for text, parts, ids in [("Smith reports accuracy", "Smith [3] reports accuracy", ("4",)), ("Jones reports latency", "Jones [4] reports latency", ("3",))]:
        with pytest.raises(ProposalRejected) as e:
            check(p, proposal(text, parts, ids))
        assert e.value.code == "WRONG_CITATION_SCOPE"


def test_wv5_union_foreign_groups_rejected():
    p = manuscript("A improves accuracy [3], while B reduces latency [4][5].")
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("A improves accuracy", ids=tuple(label for c in p.citation_callouts for label in visible_labels(c.text))))
    assert e.value.code == "WRONG_CITATION_SCOPE"


def test_wv6_repeated_quote_no_citation_disambiguation():
    p = manuscript("A improves accuracy [3], while A improves accuracy [4].")
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("A improves accuracy"))
    assert e.value.code == "QUOTE_AMBIGUOUS"
    c = check(p, proposal("A improves accuracy", "A improves accuracy [4]", ids=("4",)))
    assert c.reference_ids == ("r4",)


@pytest.mark.parametrize("quote", ["a improves accuracy", "A  improves accuracy", "A improves accuracý"])
def test_no_case_whitespace_unicode_repair(quote):
    with pytest.raises(ProposalRejected) as e:
        check(manuscript(), proposal(quote))
    assert e.value.code == "QUOTE_NOT_FOUND"


def test_abstention_and_group_subset_remove_all_links():
    p = manuscript("A improves accuracy [3][4].")
    for q in [proposal("A improves accuracy"), proposal("A improves accuracy", ids=())]:
        c = check(p, q)
        assert c.attribution_status == "ambiguous" and not c.reference_ids and not c.citation_callout_ids


def test_mixed_partial_cannot_be_resolved():
    p = manuscript("A improves accuracy [3], while B reduces latency [4].", statuses={1: "partial"})
    c = check(p, proposal("B reduces latency", ids=("4",)))
    assert c.attribution_status == "unresolved" and c.reference_ids == ("r4",)


def test_fallback_single_group_cannot_bind_other_statement():
    p = manuscript("A improves accuracy. B reduces latency [3].", sentences=[])
    c = check(p, proposal("A improves accuracy"))
    assert c.attribution_status == "ambiguous" and not c.reference_ids
    assert check(p, proposal("B reduces latency")).attribution_status == "resolved"


def test_b9_trimmed_current_focal_rejects_reattached_marker_source_and_id():
    from app.tests.test_citation_context import boundary_manuscript
    p = boundary_manuscript("A supports T-cell responses.", "8 B shows higher titers [9].", ("8", "[9]"))
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("B shows higher titers", ids=("8",)), 1)
    assert e.value.code == "UNKNOWN_CITATION_CALLOUT"
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal("8 B shows higher titers", ids=("9",)), 1)
    assert e.value.code == "QUOTE_NOT_FOUND"
    c = check(p, proposal("B shows higher titers", ids=("9",)), 1)
    assert c.attribution_status == "resolved" and c.reference_ids == ("r1",)
    assert all(s.start >= p.citation_callouts[0].span.end for s in c.source_spans)
    assert check(p, proposal("A supports T-cell responses", ids=("8",))).reference_ids == ("r0",)


def test_boundary_partial_group_is_never_promoted_to_resolved():
    from app.researchguard.domain import CitationResolutionStatus
    from app.tests.test_citation_context import boundary_manuscript
    p = boundary_manuscript("A supports T-cell responses.", "8,9 B shows higher titers.", ("8", "9"))
    calls = (p.citation_callouts[0], p.citation_callouts[1].model_copy(update={"resolution_status": CitationResolutionStatus.PARTIAL}))
    p = p.model_copy(update={"citation_callouts": calls})
    c = check(p, proposal("A supports T-cell responses", ids=("8", "9")))
    assert c.attribution_status == "unresolved"


@pytest.mark.parametrize("extra", ["reference_ids", "offsets", "verdict", "confidence", "DOI", "reasoning", "start", "end"])
def test_proposal_forbids_model_authority_fields(extra):
    data = proposal("A improves accuracy").model_dump()
    data[extra] = "untrusted"
    with pytest.raises(ValidationError):
        ClaimProposal.model_validate(data)


@pytest.mark.parametrize("source,text", [
    ("BNT162b2, a modified RNA encoding the spike", "BNT162b2 encodes the spike."),
    ("BNT162b2, a lipid nanoparticle-formulated RNA", "BNT162b2 is a lipid nanoparticle-formulated RNA."),
    ("Findings among healthy adults showed that two 30-μg doses of BNT162b2 elicited high antibody titers and robust CD8+ and Th1-type CD4+ responses", "Findings among healthy adults showed that two 30-μg doses of BNT162b2 elicited high antibody titers."),
])
def test_normalized_text_does_not_depend_on_semantic_regex(source, text):
    p = manuscript(source + " [3].")
    c = check(p, proposal(text, source))
    assert c.text == text and c.attribution_status == "resolved"
    assert len(c.source_spans) == 1
    assert p.paragraphs[0].text[c.source_spans[0].start:c.source_spans[0].end] == source


@pytest.mark.parametrize("index,quote", [(0, "B reduces latency"), (1, "A improves accuracy")])
def test_previous_and_next_neighbor_quotes_rejected(index, quote):
    first = "A improves accuracy [3]."
    text = first + " B reduces latency [4]."
    p = manuscript(text, [(0, len(first)), (len(first) + 1, len(text))])
    with pytest.raises(ProposalRejected) as e:
        check(p, proposal(quote, ids=("3",) if index == 0 else ("4",)), index)
    assert e.value.code == "QUOTE_NOT_FOUND"


@pytest.mark.parametrize("aliases", [("99",), ("c1",), ("callout:0",), ("r3",), ("10.1234/fake",), ("3", "3")])
def test_label_allowlist_and_unique_selection(aliases):
    with pytest.raises(ProposalRejected) as e:
        check(manuscript(), proposal("A improves accuracy", ids=aliases))
    assert e.value.code == "UNKNOWN_CITATION_CALLOUT"


@pytest.mark.parametrize("field,value", [("text", ""), ("text", "   "), ("evidence_quote", ""), ("evidence_quote", "\n"), ("citation_labels", "c1"), ("citation_labels", [3]), ("text", 3)])
def test_schema_nonblank_and_typed_aliases(field, value):
    data = proposal("A improves accuracy").model_dump()
    data[field] = value
    with pytest.raises(ValidationError):
        ClaimProposal.model_validate(data)


@pytest.mark.parametrize("extra", ["source_quotes", "subject", "predicate", "qualifier", "shared_subject", "citation_callout_ids", "citation_aliases", "association"])
def test_old_proposal_contract_removed(extra):
    data = proposal("A improves accuracy").model_dump()
    data[extra] = "untrusted"
    with pytest.raises(ValidationError):
        ClaimProposal.model_validate(data)


def test_long_cross_scope_evidence_is_ambiguous():
    source = "Although A improved accuracy [3], it increased latency [4]."
    c = check(manuscript(source), proposal("A increased latency", source, ("4",)))
    assert c.attribution_status == "ambiguous" and not c.reference_ids


def test_full_sentence_evidence_with_marker_and_exact_offsets():
    from app.researchguard.domain import TextSpan
    source = "BNT162b2, a modified RNA encoding the spike [3]."
    c = check(manuscript(source), proposal("BNT162b2 encodes the spike.", source))
    assert c.source_spans == (TextSpan(start=0, end=len(source)),)
    assert c.attribution_status == "resolved"


def test_overlapping_repeated_quote_rejected():
    from app.researchguard.domain import TextSpan
    from app.services.claim_attribution import exact_span
    with pytest.raises(ProposalRejected) as e:
        exact_span("aaaa", "aaa", TextSpan(start=0, end=4))
    assert e.value.code == "QUOTE_AMBIGUOUS"


@pytest.mark.parametrize("quote", ["[3]", " [3]."])
def test_citation_marker_alone_cannot_be_evidence(quote):
    with pytest.raises(ProposalRejected) as e:
        check(manuscript(), proposal("A improves accuracy", quote))
    assert e.value.code == "CITATION_MARKER_AS_SOURCE"
