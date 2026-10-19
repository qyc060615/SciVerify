"""Frozen outputs and hand-authored contracts are NOT a model quality evaluation."""
import json
from pathlib import Path

import pytest

from app.researchguard.adapters.claim_llm import PROMPT_VERSION, SYSTEM_PROMPT
from app.researchguard.domain import ClaimExtractionResult, ParsedManuscript
from app.services.manuscript_verification import plan_manuscript_pairs, validate_combined_input
from app.tests.test_claim_extractor import FakeProvider, run
from app.tests.test_citation_context import manuscript

FIXTURE = Path(__file__).parent / "fixtures/scientific_m3_ownership.json"
LIVE = Path(__file__).resolve().parents[3] / "docs/e2e-main-20261019-live"


def real_replay(overlay=False):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload = json.loads((LIVE / "resolved-response.json").read_text(encoding="utf-8"))["parsed"]
    payload["manuscript"]["content_locator"] = "replay:committed-resolved-response"
    parsed = ParsedManuscript.model_validate(payload)
    by_context = {r["context_id"]: r for r in data["contexts"]}
    def handler(payload):
        recorded = by_context[payload["context_id"]]
        assert payload["focal_text"] == recorded["focal_text"]
        return recorded.get("manual_contract_proposal", recorded["recorded_proposal"]) if overlay else recorded["recorded_proposal"]
    result = run(parsed, provider=FakeProvider(handler))
    validate_combined_input(parsed, result)
    return parsed, result


def test_real_recorded_outputs_remain_seventeen_pairs_not_claimed_as_prompt_improvement():
    parsed, result = real_replay()
    saved = ClaimExtractionResult.model_validate_json((LIVE / "extraction-response.json").read_text(encoding="utf-8"))
    assert result.claims == saved.claims
    plan, blocked = plan_manuscript_pairs(parsed, result)
    assert len(plan) == 17 and len(blocked) == 1
    assert result.metadata.prompt_version == PROMPT_VERSION


def test_real_manual_ownership_contract_blocks_specific_errors_without_changing_other_outputs():
    parsed, baseline = real_replay()
    _, contract = real_replay(overlay=True)
    before, _ = plan_manuscript_pairs(parsed, baseline)
    after, blocked = plan_manuscript_pairs(parsed, contract)
    assert len(before) == 17 and len(after) == 5 and len(blocked) == 4
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    role_contexts = {r["contract_role"]:r["context_id"] for r in data["contexts"] if "contract_role" in r}
    for role in ["collective_examples", "data_and_method_group", "unclear_current_curves_method_scope"]:
        claims = [c for c in contract.claims if c.context_id == role_contexts[role]]
        assert claims and all(c.attribution_status == "ambiguous" and not c.reference_ids for c in claims)
    assert not any(c.context_id == role_contexts["current_manuscript_panels"] for c in contract.claims)
    assert any(d.code == "NO_EXTERNAL_ATTRIBUTION" for d in contract.diagnostics)
    untouched = set(c.context_id for c in baseline.claims) - set(role_contexts.values())
    assert [c for c in baseline.claims if c.context_id in untouched] == [c for c in contract.claims if c.context_id in untouched]


def candidate(text, quote, intent, labels=()):
    return {"text":text,"evidence_quote":quote,"attribution_intent":intent,"citation_labels":labels}


@pytest.mark.parametrize("text,proposals,refs,ambiguous", [
    ("We processed observations from a dataset using an algorithm [3][4].",
     [candidate("The observations came from a dataset.", "We processed observations from a dataset using an algorithm", "uncertain")], [], 1),
    ("Our plot displays the measured loss using the published estimator [3].",
     [candidate("Our plot displays the measured loss.", "Our plot displays the measured loss", "none"),
      candidate("The analysis uses the published estimator.", "using the published estimator", "cited", ["3"])], ["r3"], 0),
    ("A, B and C are representative systems [3][4].",
     [candidate("A, B and C are representative systems.", "A, B and C are representative systems", "uncertain")], [], 1),
    ("Earlier work reports improved calibration [3].",
     [candidate("Earlier work reports improved calibration.", "Earlier work reports improved calibration", "cited", ["3"])], ["r3"], 0),
    ("Both independent reports found improved calibration [3][4].",
     [candidate("Both independent reports found improved calibration.", "Both independent reports found improved calibration", "cited", ["3","4"])], ["r3","r4"], 0),
    ("Both independent reports found improved calibration [3,4].",
     [candidate("Both independent reports found improved calibration.", "Both independent reports found improved calibration", "cited", ["3","4"])], ["r3","r4"], 0),
    ("Our experiment measured a latency of 7 ms with the published method [3].",
     [candidate("Our experiment measured a latency of 7 ms.", "Our experiment measured a latency of 7 ms", "none")], [], 0),
])
def test_abstract_source_roles_route_intents_without_semantic_validator(text, proposals, refs, ambiguous):
    parsed = manuscript(text)
    result = run(parsed, provider=FakeProvider(lambda _: {"claims":proposals}))
    validate_combined_input(parsed, result)
    plan, blocked = plan_manuscript_pairs(parsed, result)
    assert [r.id for _, r, _ in plan] == refs
    assert len(blocked) == ambiguous


@pytest.mark.parametrize("marker", ["[3][4]", "[3,4]"])
def test_heterogeneous_group_subset_cannot_bypass_integrity(marker):
    text = "We used observations from the original report and an analysis method " + marker + "."
    proposal = candidate("Observations came from the original report.", text, "cited", ["3"])
    result = run(manuscript(text), provider=FakeProvider(lambda _: {"claims":[proposal]}))
    assert result.claims[0].attribution_status == "ambiguous"
    assert not result.claims[0].reference_ids


def test_prompt_distinguishes_group_identity_semantics_and_preserves_existing_contract():
    for phrase in ["independent verification pair with EACH", "collective support", "dataset contents",
                   "current-study figure", "Never select a subset", "Do not invent a one-to-one mapping",
                   "Do not invent a generic method claim", "Ordinary single citations"]:
        assert phrase in SYSTEM_PROMPT
    assert PROMPT_VERSION == "focal-atomic-semantic-ownership-v6"
