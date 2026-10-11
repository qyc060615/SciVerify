"""Visible-label mapping remains local, exact and occurrence-safe."""
import pytest

from app.services.citation_labels import visible_labels
from app.services.claim_attribution import ProposalRejected
from app.tests.test_claim_attribution import check, proposal
from app.tests.test_citation_context import manuscript
from app.tests.test_claim_extractor import FakeProvider, run


def test_cf1_visible_eight_maps_to_local_occurrence_and_backend_references():
    p = manuscript("A improves accuracy [8].", targets={"[8]": ["opaque-reference"]})
    c = check(p, proposal("A improves accuracy", ids=("8",)))
    assert c.citation_callout_ids == ("callout:0",)
    assert c.reference_ids == ("opaque-reference",) and c.attribution_status == "resolved"


@pytest.mark.parametrize("label", ["7", "99", "c1", "callout:0", "opaque-reference", "08", " 8", "[8]"])
def test_cf2_cf3_no_unknown_synthetic_internal_or_fuzzy_identifier(label):
    p = manuscript("A improves accuracy [8].", targets={"[8]": ["opaque-reference"]})
    with pytest.raises(ProposalRejected) as exc:
        check(p, proposal("A improves accuracy", ids=(label,)))
    assert exc.value.code == "UNKNOWN_CITATION_CALLOUT"


@pytest.mark.parametrize("surface", ["[4,8]", "[4][8]"])
def test_cf4_group_labels_resolve_exactly_independent_of_output_order(surface):
    p = manuscript(f"A improves accuracy {surface}.")
    a = check(p, proposal("A improves accuracy", ids=("4", "8")))
    b = check(p, proposal("A improves accuracy", ids=("8", "4")))
    assert a == b and a.attribution_status == "resolved" and a.reference_ids == ("r4", "r8")


def test_group_subset_cannot_silently_expand_selected_references():
    c = check(manuscript("A improves accuracy [4,8]."), proposal("A improves accuracy", ids=("4",)))
    assert c.attribution_status == "ambiguous"
    assert not c.reference_ids and not c.citation_callout_ids


def test_cf5_duplicate_visible_label_does_not_guess_even_with_unique_evidence():
    p = manuscript("A improves accuracy [8], while B reduces latency [8].")
    with pytest.raises(ProposalRejected) as exc:
        check(p, proposal("A improves accuracy", ids=("8",)))
    assert exc.value.code == "AMBIGUOUS_CITATION_LABEL"


def test_cf8_neighbor_label_cannot_enter_current_allowlist():
    first = "A improves accuracy [8]."
    text = first + " B reduces latency [9]."
    p = manuscript(text, [(0, len(first)), (len(first) + 1, len(text))])
    with pytest.raises(ProposalRejected) as exc:
        check(p, proposal("B reduces latency", ids=("8",)), 1)
    assert exc.value.code == "UNKNOWN_CITATION_CALLOUT"


def test_cf8_same_label_in_neighbor_maps_only_to_focal_occurrence():
    first = "A improves accuracy [8]."
    text = first + " B reduces latency [8]."
    p = manuscript(text, [(0, len(first)), (len(first) + 1, len(text))])
    c = check(p, proposal("B reduces latency", ids=("8",)), 1)
    assert c.citation_callout_ids == ("callout:1",) and c.attribution_status == "resolved"
    with pytest.raises(ProposalRejected) as exc:
        check(p, proposal("A improves accuracy", ids=("8",)), 1)
    assert exc.value.code == "QUOTE_NOT_FOUND"


@pytest.mark.parametrize("surface,labels", [
    ("8", ("8",)), ("4,", ("4",)), ("[4,8]", ("4", "8")),
    ("[3–5]", ("3", "4", "5")), ("(08)", ("08",)),
    ("Smith et al., 2020", ("Smith et al., 2020",)),
    ("[1-99999999]", ("1-99999999",)),
])
def test_visible_surface_formatting_is_not_reference_metadata_inference(surface, labels):
    assert visible_labels(surface) == labels


def test_cf10_prompt_payload_and_generic_defined_noun_contract():
    provider = FakeProvider(lambda p: {"claims": []})
    run(manuscript("A improves accuracy [4,8]."), provider=provider)
    payload = provider.prompts[0]
    assert payload["callouts"][0]["labels"] == ["4", "8"]
    assert "id" not in payload["callouts"][0]
    schema = payload["output_schema"]["$defs"]["ClaimProposal"]
    assert "citation_labels" in schema["required"] and "citation_aliases" not in schema["properties"]
    system = provider.systems[0]
    for instruction in ["Use visible citation labels", "only labels present in focal context",
                        "Do not invent labels", "standalone", "Defined abstract noun rule",
                        "must retain its necessary definition", "do not merge",
                        "abstain", "chain-of-thought"]:
        assert instruction in system
    assert "98.6" not in system and "FDA" not in system and "NEJM" not in system
