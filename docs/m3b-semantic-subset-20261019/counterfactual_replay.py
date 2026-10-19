"""Offline comparison of the pinned baseline validator and current validator.

Only deterministic proposals are constructed. No model/provider or Job is run.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.researchguard.domain import ClaimExtractionResult, ParsedManuscript
from app.schemas.claim_extraction import ClaimProposal
from app.services.claim_attribution import validate_proposal
from app.services.manuscript_verification import plan_manuscript_pairs, validate_combined_input

BASELINE = "071f22cb9bc967e5055ef05e72868031fee2d414"
LIVE = ROOT / "docs/e2e-main-20261019-live"
OUT = Path(__file__).parent


def main():
    source = subprocess.check_output(["git", "show", BASELINE+":backend/app/services/claim_attribution.py"], cwd=ROOT)
    old = types.ModuleType("app.services._subset_baseline")
    sys.modules[old.__name__] = old
    exec(compile(source, "<pinned-baseline-validator>", "exec"), old.__dict__)
    payload = json.loads((LIVE / "resolved-response.json").read_text(encoding="utf-8"))["parsed"]
    payload["manuscript"]["content_locator"] = "replay:subset-counterfactual"
    parsed = ParsedManuscript.model_validate(payload)
    saved = ClaimExtractionResult.model_validate_json((LIVE / "extraction-response.json").read_text(encoding="utf-8"))
    rows = []
    for index in (3, 4):
        original = saved.claims[index]
        context = next(c for c in saved.contexts if c.id == original.context_id)
        paragraph = next(p for p in parsed.paragraphs if p.id == original.paragraph_id)
        span = original.source_spans[0]
        for labels in (("1",), ("6",), ("1", "6")):
            proposal = ClaimProposal(text=original.text, evidence_quote=paragraph.text[span.start:span.end],
                attribution_intent="cited", citation_labels=labels)
            before = old.validate_proposal(parsed, context, proposal).claim
            after = validate_proposal(parsed, context, proposal).claim
            # The existing result/planner contracts require only the new claim
            # and matching accepted-claim IDs; parsed source data is untouched.
            result = saved.model_copy(update={"claims":(after,), "context_results":tuple(
                c.model_copy(update={"accepted_claim_ids":(after.id,) if c.context_id == context.id else ()})
                for c in saved.context_results)})
            validate_combined_input(parsed, result)
            pairs, blocked = plan_manuscript_pairs(parsed, result)
            def numbers(ids):
                return [i for i,r in enumerate(parsed.references, 1) if r.id in ids]
            rows.append({"case":"C"+str(index+1), "context_id":context.id,
                "proposal":proposal.model_dump(mode="json"),
                "before":{"status":before.attribution_status.value,"references":numbers(before.reference_ids)},
                "after":{"status":after.attribution_status.value,"references":numbers(after.reference_ids)},
                "planned_reference_numbers":[parsed.references.index(r)+1 for _,r,_ in pairs],
                "blocked_count":len(blocked),
                "semantics":"R6-only is deliberately wrong-but-local; structural acceptance does not certify correctness." if labels == ("6",) else "Deterministic contract only, not a new LLM result."})
            assert after.attribution_status == "resolved" and not blocked
            assert numbers(after.reference_ids) == [int(x) for x in labels]
            assert before.attribution_status == ("resolved" if len(labels) == 2 else "ambiguous")
    report = {"baseline":BASELINE,"baseline_validator_sha256":hashlib.sha256(source).hexdigest(),
        "real_llm_calls":0,"cases":rows,"single_multi_label_occurrence_limit":
        "Without a per-label target mapping, an opaque aggregate occurrence cannot safely yield one selected reference; do not infer targets from order."}
    (OUT / "counterfactual-results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("6 real-context counterfactuals PASS; baseline subsets ambiguous, new subsets resolved; zero LLM calls.")


if __name__ == "__main__":
    main()
