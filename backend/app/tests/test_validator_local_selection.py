"""Explicit local selection survives broad envelopes; provenance guards remain."""
import pytest

from app.schemas.claim_extraction import ClaimProposal
from app.services.citation_context import build_contexts
from app.services.claim_attribution import ProposalRejected, validate_proposal
from app.services.manuscript_verification import plan_manuscript_pairs
from app.tests.test_citation_context import manuscript
from app.tests.test_claim_extractor import FakeProvider, run


APPOSITIVE = (
    "We previously reported phase 1 results for BNT162b2, [4] "
    "a lipid nanoparticle-formulated, [5] nucleoside-modified RNA (modRNA) [6] "
    "encoding the SARS-CoV-2 full-length spike, modified by two proline mutations "
    "to lock it in the prefusion conformation. [7]"
)


def proposed(quote, labels, intent="cited"):
    return ClaimProposal(text=quote, evidence_quote=quote,
                         attribution_intent=intent, citation_labels=labels)


def check(parsed, quote, labels):
    return validate_proposal(parsed, build_contexts(parsed)[0].context,
                             proposed(quote, labels)).claim


@pytest.mark.parametrize("quote,label", [
    ("We previously reported phase 1 results for BNT162b2,", "4"),
    ("a lipid nanoparticle-formulated,", "5"),
    ("nucleoside-modified RNA (modRNA)", "6"),
    ("modified by two proline mutations to lock it in the prefusion conformation.", "7"),
])
@pytest.mark.parametrize("full_quote", [False, True])
def test_appositive_explicit_labels_resolve_with_short_or_broad_evidence(quote, label, full_quote):
    parsed = manuscript(APPOSITIVE)
    claim = check(parsed, APPOSITIVE if full_quote else quote, (label,))
    assert claim.attribution_status == "resolved"
    assert claim.reference_ids == ("r" + label,)
    assert claim.citation_callout_ids == ("callout:" + str(int(label) - 4),)


def test_wrong_but_local_encoding_selection_is_not_silently_corrected():
    quote = "nucleoside-modified RNA (modRNA) [6] encoding the SARS-CoV-2 full-length spike,"
    claim = check(manuscript(APPOSITIVE), quote, ("6",))
    # Structurally valid, semantically wrong per candidate gold: never guess 7.
    assert claim.attribution_status == "resolved" and claim.reference_ids == ("r6",)


@pytest.mark.parametrize("marker", ["[4,8]", "[4][8]"])
@pytest.mark.parametrize("labels", [("4", "8"), ("4",), ("8",)])
def test_addressable_group_subsets_inside_multi_group_envelope(marker, labels):
    parsed = manuscript(f"Earlier safety results {marker} informed formulation [5].")
    claim = check(parsed, "Earlier safety results", labels)
    resolved = marker == "[4][8]" or len(labels) == 2
    assert claim.attribution_status == ("resolved" if resolved else "ambiguous")
    assert claim.reference_ids == (tuple("r"+label for label in labels) if resolved else ())
    if not resolved:
        assert not claim.citation_callout_ids


@pytest.mark.parametrize("labels", [("99",), ("c1",), ("callout:0",), ("r4",), ("4", "4")])
def test_broad_envelope_does_not_relax_label_allowlist(labels):
    with pytest.raises(ProposalRejected) as exc:
        check(manuscript(APPOSITIVE), "a lipid nanoparticle-formulated,", labels)
    assert exc.value.code == "UNKNOWN_CITATION_CALLOUT"


def test_repeated_visible_label_still_rejects_unique_mapping_failure():
    with pytest.raises(ProposalRejected) as exc:
        check(manuscript("A improves accuracy [4] and B reduces latency [4]."), "A improves accuracy", ("4",))
    assert exc.value.code == "AMBIGUOUS_CITATION_LABEL"


@pytest.mark.parametrize("quote,code", [("Not in manuscript", "QUOTE_NOT_FOUND"), ("[5]", "CITATION_MARKER_AS_SOURCE")])
def test_broad_selection_keeps_exact_grounding_and_marker_guard(quote, code):
    with pytest.raises(ProposalRejected) as exc:
        check(manuscript(APPOSITIVE), quote, ("5",))
    assert exc.value.code == code


@pytest.mark.parametrize("status,refs", [("partial", ("r5",)), ("unresolved", ())])
def test_broad_selection_cannot_promote_incomplete_target(status, refs):
    parsed = manuscript(APPOSITIVE, statuses={1: status})
    claim = check(parsed, "a lipid nanoparticle-formulated,", ("5",))
    assert claim.attribution_status == "unresolved" and claim.reference_ids == refs
    assert claim.citation_callout_ids == ("callout:1",)


def test_strong_boundary_still_rejects_foreign_clause_with_multiple_local_groups():
    parsed = manuscript("A improves accuracy [3] and robustness [4]; B reduces latency [5].")
    with pytest.raises(ProposalRejected) as exc:
        check(parsed, "A improves accuracy", ("5",))
    assert exc.value.code == "WRONG_CITATION_SCOPE"


def test_evidence_spanning_strong_boundary_remains_ambiguous():
    text = "A improves accuracy [3]; B reduces latency [4]."
    claim = check(manuscript(text), text, ("3", "4"))
    assert claim.attribution_status == "ambiguous" and not claim.reference_ids


@pytest.mark.parametrize("intent", ["none", "uncertain"])
def test_empty_intents_are_not_promoted_in_broad_envelope(intent):
    quote = "a lipid nanoparticle-formulated,"
    payload = proposed(quote, (), intent).model_dump(mode="json")
    result = run(manuscript(APPOSITIVE), provider=FakeProvider(lambda _: {"claims": [payload]}))
    if intent == "none":
        assert not result.claims
        assert [d.code for d in result.diagnostics] == ["NO_EXTERNAL_ATTRIBUTION"]
    else:
        assert len(result.claims) == 1 and result.claims[0].attribution_status == "ambiguous"
        assert not result.claims[0].reference_ids and not result.claims[0].citation_callout_ids


def test_newly_resolved_selection_plans_only_backend_derived_reference():
    parsed = manuscript(APPOSITIVE)
    payload = proposed("a lipid nanoparticle-formulated,", ("5",)).model_dump(mode="json")
    result = run(parsed, provider=FakeProvider(lambda _: {"claims": [payload]}))
    planned, blocked = plan_manuscript_pairs(parsed, result)
    assert not blocked
    assert [(claim.id, reference.id, calls) for claim, reference, calls in planned] == [
        (result.claims[0].id, "r5", ("callout:1",))]
