"""Parser-fragment label contract; no provider, bibliography or semantic inference."""
import pytest

from app.researchguard.adapters.claim_llm import PROMPT_VERSION, SYSTEM_PROMPT
from app.researchguard.domain import CitationCallout, Reference, TextSpan
from app.services.citation_context import build_contexts, groups
from app.services.citation_labels import canonicalize_visible_citation_label, local_label_index, visible_labels
from app.services.claim_attribution import ProposalRejected, validate_proposal
from app.services.manuscript_verification import plan_manuscript_pairs
from app.tests.test_citation_context import manuscript
from app.tests.test_claim_attribution import check, proposal
from app.tests.test_claim_extractor import FakeProvider, run


def fragmented(surfaces):
    prefix = "A improves accuracy "
    text = prefix + "".join(surfaces) + "."
    parsed = manuscript()
    paragraph = parsed.paragraphs[0].model_copy(update={
        "text": text, "sentence_spans": (TextSpan(start=0, end=len(text)),)})
    calls, references, offset = [], [], len(prefix)
    for i, surface in enumerate(surfaces):
        rid = f"opaque-reference:{i}"
        calls.append(CitationCallout(id=f"callout:{i}", manuscript_id="m", paragraph_id="p",
            text=surface, span=TextSpan(start=offset, end=offset + len(surface)), order=i,
            reference_ids=(rid,)))
        references.append(Reference(id=rid, manuscript_id="m", raw_text="Unrelated metadata"))
        offset += len(surface)
    return parsed.model_copy(update={"paragraphs": (paragraph,), "citation_callouts": tuple(calls),
                                     "references": tuple(references)})


@pytest.mark.parametrize("surface,label", [
    ("(1,", "1"), ("2)", "2"), ("[4,", "4"), ("8]", "8"),
    ("(12;", "12"), ("13)", "13"), ("[12;", "12"), ("13]", "13"),
    ("9", "9"), ("  24) ", "24"), (" ( 12 ; ", "12"), ("08)", "08"),
    ("(1", "1"), ("[4", "4"), ("4,", "4"), ("4;", "4"),
])
def test_single_number_fragment_has_one_canonical_label(surface, label):
    assert canonicalize_visible_citation_label(surface) == label
    assert visible_labels(surface) == (label,)


@pytest.mark.parametrize("surface", [
    "(1]", "[1)", "((1,)", "[1))", "1†", "¹", "1 2)", "(1,2", "(1-3",
    "1/2", "-1)", "1.5)", "1e3", "c1", "callout:1", "r1", "", "(,)",
    "Smith et al., 2020",
])
def test_unrecognized_or_mixed_surface_does_not_guess_a_numeric_token(surface):
    assert canonicalize_visible_citation_label(surface) is None
    assert "1" not in visible_labels(surface)


@pytest.mark.parametrize("surface,labels", [
    ("(1,2)", ("1", "2")), ("[4,8]", ("4", "8")),
    ("(1-3)", ("1", "2", "3")), ("[03–05]", ("03", "04", "05")),
    ("[1-99999999]", ("1-99999999",)),
])
def test_existing_multi_label_range_and_bound_semantics_are_unchanged(surface, labels):
    assert canonicalize_visible_citation_label(surface) is None
    assert visible_labels(surface) == labels


@pytest.mark.parametrize("surfaces,labels", [(("(1,", "2)"), ("1", "2")),
                                              (("[4,", "8]"), ("4", "8"))])
def test_full_fragmented_group_preserves_identity_raw_offsets_and_references(surfaces, labels):
    parsed = fragmented(surfaces)
    before = parsed.model_dump_json()
    context = build_contexts(parsed)[0].context
    grouped = groups(parsed.paragraphs[0].text, parsed.citation_callouts)
    assert len(grouped) == 1 and tuple(c.id for c in grouped[0]) == ("callout:0", "callout:1")
    result = validate_proposal(parsed, context, proposal("A improves accuracy", ids=labels))
    assert result.claim.attribution_status == "resolved"
    assert result.claim.citation_callout_ids == ("callout:0", "callout:1")
    assert result.claim.reference_ids == ("opaque-reference:0", "opaque-reference:1")
    assert parsed.model_dump_json() == before


@pytest.mark.parametrize("selected", [("1",), ("2",)])
def test_partial_fragmented_group_does_not_expand_or_resolve(selected):
    claim = check(fragmented(("(1,", "2)")), proposal("A improves accuracy", ids=selected))
    assert claim.attribution_status == "ambiguous"
    assert not claim.reference_ids and not claim.citation_callout_ids


def test_duplicate_canonical_label_keeps_all_occurrences_and_rejects_ambiguity():
    parsed = fragmented(("(1,", "1)"))
    assert [c.id for c in local_label_index(parsed.citation_callouts)["1"]] == ["callout:0", "callout:1"]
    with pytest.raises(ProposalRejected) as exc:
        check(parsed, proposal("A improves accuracy", ids=("1",)))
    assert exc.value.code == "AMBIGUOUS_CITATION_LABEL"


@pytest.mark.parametrize("selected", [("4",), ("99",), ("(1,",), ("2)",), (" 1",), ("[1]",), ("callout:0",)])
def test_unknown_missing_or_raw_proposal_label_is_not_normalized_by_validator(selected):
    parsed = fragmented(("(1,", "2)"))
    parsed = parsed.model_copy(update={"references": parsed.references + (
        Reference(id="bibliography-only", manuscript_id="m", raw_text="4. Metadata without occurrence"),)})
    with pytest.raises(ProposalRejected) as exc:
        check(parsed, proposal("A improves accuracy", ids=selected))
    assert exc.value.code == "UNKNOWN_CITATION_CALLOUT"


def test_payload_and_allowlist_share_canonical_labels_while_raw_text_remains():
    parsed = fragmented(("(1,", "2)"))
    provider = FakeProvider(lambda _: {"claims": []})
    run(parsed, provider=provider)
    callouts = provider.prompts[0]["callouts"]
    assert [c["labels"] for c in callouts] == [["1"], ["2"]]
    assert [c["text"] for c in callouts] == ["(1,", "2)"]
    assert set(local_label_index(parsed.citation_callouts)) == {"1", "2"}
    assert provider.systems == [SYSTEM_PROMPT]
    assert PROMPT_VERSION == "focal-atomic-attribution-intent-v5"


def test_fragmented_group_pair_plan_uses_only_backend_occurrence_targets():
    parsed = fragmented(("(1,", "2)"))
    fields = proposal("A improves accuracy", ids=("1", "2")).model_dump(mode="json")
    result = run(parsed, provider=FakeProvider(lambda _: {"claims": [fields]}))
    pairs, blocked = plan_manuscript_pairs(parsed, result)
    assert not blocked
    assert [(reference.id, calls) for _, reference, calls in pairs] == [
        ("opaque-reference:0", ("callout:0",)), ("opaque-reference:1", ("callout:1",))]
