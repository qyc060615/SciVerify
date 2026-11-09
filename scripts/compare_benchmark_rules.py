"""Offline replay of pre-fix rules on frozen real model outputs; no API calls."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def baseline(name, path, revision):
    source = subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT).decode("utf-8")
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(source, "baseline:" + path, "exec"), module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--baseline", default="f653d342e44dc496c0113e7c626c705db174d83a",
                        help="Pre-recovery revision; fixed rather than HEAD so replay remains reproducible")
    args = parser.parse_args()
    out = Path(args.run)
    view = json.loads((out / "06-job-final.json").read_text(encoding="utf-8"))
    saved = json.loads((out / "jobs" / (view["job_id"] + ".json")).read_text(encoding="utf-8"))["snapshot"]
    from app.researchguard.domain import ParsedManuscript, EvidenceChunk
    from app.schemas.claim_extraction import ClaimProposal
    from app.schemas.verification import AdjudicatorAnalysis, DefenderAnalysis, ProsecutorAnalysis
    from app.researchguard.adapters.sciverify import evidence_to_legacy
    from app.services.verification_validator import validate_verification_result, _has_grounded_counterevidence
    from app.services.claim_attribution import validate_proposal
    from app.utils.claim_preprocessor import preprocess_claim
    old_attribution = baseline("baseline_attribution", "backend/app/services/claim_attribution.py", args.baseline)
    old_validator = baseline("baseline_validator", "backend/app/services/verification_validator.py", args.baseline)
    parsed = ParsedManuscript.model_validate(saved["parsed"])
    from app.researchguard.domain import CitationContext
    contexts = {c["id"]: CitationContext.model_validate(c) for c in view["contexts"]}
    attribution = []
    for request_path in sorted((out / "model-calls").glob("*-_ProposalEnvelope-request.json")):
        response_path = request_path.with_name(request_path.name.replace("-request.json", "-response.json"))
        if not response_path.exists():
            continue
        request = json.loads(request_path.read_text(encoding="utf-8"))
        payload = json.loads(request["prompt"])
        result = json.loads(response_path.read_text(encoding="utf-8"))["result"]
        context = contexts[payload["context_id"]]
        for proposal in result["claims"]:
            proposed = ClaimProposal.model_validate(proposal)
            if proposed.attribution_intent == "none":
                continue
            row = {"text": proposed.text, "context_id": context.id}
            for key, validator in (("old", old_attribution.validate_proposal), ("new", validate_proposal)):
                try:
                    checked = validator(parsed, context, proposed)
                    row[key] = {"status": checked.claim.attribution_status.value,
                                "reference_ids": checked.claim.reference_ids}
                except Exception as exc:
                    row[key] = {"rejection": getattr(exc, "code", type(exc).__name__)}
            attribution.append(row)
    claims = {c["id"]: c for c in view["claims"]}
    verdicts = []
    for index, task in enumerate(view["tasks"], 1):
        if task["state"] != "completed":
            continue
        result = task["pair_outcome"]["verification"]
        legacy = result["traceability"]["metadata"]["legacy_provenance"]
        judge = AdjudicatorAnalysis.model_validate(legacy["adjudicator"])
        evidence = evidence_to_legacy([EvidenceChunk.model_validate(c) for c in result["evidence_chunks"]],
                                     preprocess_claim(claims[task["claim_id"]]["text"]))
        kwargs = dict(claim=claims[task["claim_id"]]["text"], evidence=evidence,
                      prosecutor=ProsecutorAnalysis.model_validate(legacy["prosecutor"]),
                      defender=DefenderAnalysis.model_validate(legacy["defender"]), adjudicator=judge)
        verdicts.append({"claim_number": index, "text": kwargs["claim"],
            "original_agent_verdict": judge.verdict.value,
            "old_validator_verdict": old_validator.validate_verification_result(**kwargs).verdict.value,
            "new_validator_verdict": validate_verification_result(**kwargs).verdict.value,
            "old_quote_grounded": old_validator._has_grounded_counterevidence(judge, evidence),
            "new_quote_grounded": _has_grounded_counterevidence(judge, evidence)})
    data = {"method": "Same frozen outputs, offline deterministic replay; not a second E2E run",
        "baseline_commit": subprocess.check_output(["git", "rev-parse", args.baseline], cwd=ROOT).decode().strip(),
        "attribution": attribution, "verification": verdicts}
    (out / "08-rule-comparison.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"attribution_changes": sum(r["old"] != r["new"] for r in attribution),
        "validator_verdict_changes": sum(r["old_validator_verdict"] != r["new_validator_verdict"] for r in verdicts)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
