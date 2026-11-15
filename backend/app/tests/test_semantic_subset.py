"""Semantic subsets select occurrences; structure cannot certify source semantics."""
import json
from pathlib import Path

import pytest

from app.researchguard.domain import ParsedManuscript, TextSpan
from app.schemas.claim_extraction import ClaimProposal
from app.services.citation_context import build_contexts
from app.services.claim_attribution import validate_proposal
from app.services.manuscript_verification import plan_manuscript_pairs, validate_combined_input
from app.tests.test_citation_label_canonicalization import fragmented
from app.tests.test_claim_attribution import check, proposal
from app.tests.test_claim_extractor import FakeProvider, run
from app.tests.test_citation_context import manuscript

LIVE = Path(__file__).resolve().parents[3] / "docs/e2e-main-20261019-live"


def role_group(prose):
    p = fragmented(("[data-source]", "[method-source]"))
    old_prefix = "A improves accuracy"
    delta = len(prose) - len(old_prefix)
    text = p.paragraphs[0].text.replace(old_prefix, prose, 1)
    return p.model_copy(update={
        "paragraphs": (p.paragraphs[0].model_copy(update={"text":text,
            "sentence_spans":(TextSpan(start=0, end=len(text)),)}),),
        "citation_callouts": tuple(c.model_copy(update={"span":TextSpan(
            start=c.span.start+delta, end=c.span.end+delta)}) for c in p.citation_callouts)})


@pytest.mark.parametrize("quote,labels,expected", [
    ("The dataset contains 48 records", ("data-source",), ("opaque-reference:0",)),
    ("the algorithm reconstructs records", ("method-source",), ("opaque-reference:1",)),
    ("The dataset contains 48 records", ("data-source","method-source"), ("opaque-reference:0","opaque-reference:1")),
])
def test_heterogeneous_group_subset_and_full_group_are_structurally_legal(quote, labels, expected):
    p = role_group("The dataset contains 48 records, and the algorithm reconstructs records")
    before = p.model_dump_json()
    c = check(p, proposal(quote, ids=labels))
    assert c.attribution_status == "resolved" and c.reference_ids == expected
    assert p.model_dump_json() == before


def test_wrong_but_local_selection_is_not_semantically_corrected():
    p = role_group("The dataset contains 48 records, and the algorithm reconstructs records")
    c = check(p, proposal("The dataset contains 48 records", ids=("method-source",)))
    assert c.attribution_status == "resolved"
    assert c.reference_ids == ("opaque-reference:1",)  # Deliberately wrong semantics.


@pytest.mark.parametrize("labels,expected", [((), ()), (("3",),("r3",)), (("4",),("r4",)), (("3","4"),("r3","r4"))])
def test_collective_uncertainty_and_explicit_subsets_are_not_reinterpreted(labels, expected):
    p = manuscript("A, B and C are representative systems [3][4].")
    c = check(p, proposal("A, B and C are representative systems", ids=labels))
    assert c.attribution_status == ("resolved" if labels else "ambiguous")
    assert c.reference_ids == expected


def test_current_study_fact_is_excluded_without_attaching_method_group():
    text = "Our experiment measured 7 ms with the published estimator [3][4]."
    fields = {"text":"Our experiment measured 7 ms.", "evidence_quote":"Our experiment measured 7 ms",
              "attribution_intent":"none", "citation_labels":[]}
    result = run(manuscript(text), provider=FakeProvider(lambda _: {"claims":[fields]}))
    assert not result.claims
    assert [d.code for d in result.diagnostics] == ["NO_EXTERNAL_ATTRIBUTION"]


def test_unselected_unresolved_neighbor_does_not_veto_selected_resolved_target():
    p = manuscript("A improves accuracy [3][4].", statuses={1:"unresolved"})
    assert check(p, proposal("A improves accuracy", ids=("3",))).reference_ids == ("r3",)
    c = check(p, proposal("A improves accuracy", ids=("4",)))
    assert c.attribution_status == "unresolved" and not c.reference_ids


@pytest.mark.parametrize("labels,expected", [(("1",),(0,)), (("6",),(5,)), (("1","6"),(0,5))])
@pytest.mark.parametrize("claim_number", [3,4])
def test_real_figure_location_counterfactual_selects_only_backend_targets(labels, expected, claim_number):
    payload = json.loads((LIVE / "resolved-response.json").read_text(encoding="utf-8"))["parsed"]
    payload["manuscript"]["content_locator"] = "replay:subset"
    p = ParsedManuscript.model_validate(payload)
    old = json.loads((LIVE / "extraction-response.json").read_text(encoding="utf-8"))
    claim = old["claims"][claim_number]
    context = next(c.context for c in build_contexts(p) if c.context.id == claim["context_id"])
    paragraph = next(v for v in p.paragraphs if v.id == context.paragraph_id)
    span = claim["source_spans"][0]
    fields = {"text":claim["text"], "evidence_quote":paragraph.text[span["start"]:span["end"]],
              "attribution_intent":"cited", "citation_labels":list(labels)}
    checked = validate_proposal(p, context, ClaimProposal.model_validate(fields)).claim
    assert checked.attribution_status == "resolved"
    assert checked.reference_ids == tuple(p.references[i].id for i in expected)
    # Feed the real counterfactual through extraction and the unchanged planner.
    result = run(p, provider=FakeProvider(lambda request: {"claims":[fields] if request["context_id"] == context.id else []}))
    validate_combined_input(p, result)
    pairs, blocked = plan_manuscript_pairs(p, result)
    assert not blocked
    assert [r.id for _,r,_ in pairs] == list(checked.reference_ids)


@pytest.mark.parametrize("label", ["4","5","6","7"])
def test_technical_property_local_labels_stay_clause_local(label):
    text = "Prior phase 1 results [4], lipid nanoparticle formulation [5], nucleoside-modified RNA [6], and prefusion modification [7]."
    quote = {"4":"Prior phase 1 results", "5":"lipid nanoparticle formulation",
             "6":"nucleoside-modified RNA", "7":"prefusion modification"}[label]
    c = check(manuscript(text), proposal(quote, ids=(label,)))
    assert c.attribution_status == "resolved" and c.reference_ids == ("r"+label,)
