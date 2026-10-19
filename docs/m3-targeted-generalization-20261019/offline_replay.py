"""Run with the backend Python environment. No network or jobs I/O.

The contract overlay is human-authored, not output from the changed model prompt.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

from app.researchguard.adapters.grobid_tei import parse_tei
from app.researchguard.domain import ParsedManuscript
from app.services.claim_extractor import extract_claims
from app.services.llm.provider import LLMProvider
from app.services.manuscript_verification import plan_manuscript_pairs, validate_combined_input

LIVE = ROOT / "docs/e2e-main-20261019-live"
OUT = Path(__file__).parent


def read(name):
    return json.loads((LIVE / name).read_text(encoding="utf-8"))


def parsed(name):
    payload = read(name)["parsed"]
    payload["manuscript"]["content_locator"] = "replay:committed-asset"
    return ParsedManuscript.model_validate(payload)


class RecordedProvider(LLMProvider):
    model = "offline-frozen-contract-not-live-model"

    def __init__(self, records, overlay):
        self.records, self.overlay = records, overlay

    def generate(self, prompt, *, system=None, response_model=None):
        request = json.loads(prompt)
        record = self.records[request["context_id"]]
        assert record["focal_text"] == request["focal_text"]
        value = record.get("manual_contract_proposal", record["recorded_proposal"]) if self.overlay else record["recorded_proposal"]
        return response_model.model_validate(value)


def summarize(p, result):
    validate_combined_input(p, result)
    plan, blocked = plan_manuscript_pairs(p, result)
    return {"pair_count": len(plan), "blocked_claim_count": len(blocked),
            "pairs": [{"text": c.text, "context_id": c.context_id, "reference_number": p.references.index(r) + 1} for c, r, _ in plan],
            "claims": [{"text":c.text, "context_id":c.context_id, "attribution_status":c.attribution_status.value,
                        "references": [next(i for i,r in enumerate(p.references, 1) if r.id == rid) for rid in c.reference_ids]} for c in result.claims],
            "diagnostics": [d.model_dump(mode="json") for d in result.diagnostics]}


def forbidden(*args, **kwargs):
    raise AssertionError("All network access is forbidden during this offline replay")


def main():
    fixture = json.loads((ROOT / "backend/app/tests/fixtures/scientific_m3_ownership.json").read_text(encoding="utf-8"))
    records = {c["context_id"]:c for c in fixture["contexts"]}
    p = parsed("resolved-response.json")
    async def replay():
        # Let Windows initialize the event loop's internal socketpair first.
        with patch.object(socket.socket, "connect", forbidden), patch.object(socket, "getaddrinfo", forbidden):
            baseline = await extract_claims(p, provider=RecordedProvider(records, False))
            contract = await extract_claims(p, provider=RecordedProvider(records, True))
        return baseline, contract
    baseline, contract = asyncio.run(replay())
    old = parsed("parse-response.json")
    fresh = parse_tei((LIVE / "grobid-original.tei.xml").read_bytes(), old.manuscript)
    before_audit = json.loads((OUT / "audit-before.json").read_text(encoding="utf-8"))
    assert all(hashlib.sha256((LIVE/name).read_bytes()).hexdigest() == digest for name,digest in before_audit["asset_sha256"].items())
    report = {"real_llm_calls":0, "public_api_calls":0,
              "recorded_output_replay":summarize(p, baseline),
              "human_authored_contract_overlay_NOT_model_improvement":summarize(p, contract),
              "metadata": {"title_before":old.manuscript.title, "title_after":fresh.manuscript.title,
                           "new_title_diagnostics":[d.model_dump(mode="json") for d in fresh.diagnostics if d.code.startswith("MANUSCRIPT_TITLE")],
                           "resource_doi_before":old.references[4].doi, "resource_doi_after":fresh.references[4].doi,
                           "resource_url_after":fresh.references[4].url,
                           "paragraphs_unchanged":fresh.paragraphs == old.paragraphs,
                           "callouts_unchanged":fresh.citation_callouts == old.citation_callouts,
                           "references":len(fresh.references), "callouts":len(fresh.citation_callouts)},
              "committed_audit_assets_unchanged":True}
    (OUT / "pair-plan-replay.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    print("Recorded replay: 17 pairs; manual contract overlay: 5 pairs. Real LLM/API calls: 0.")


if __name__ == "__main__":
    main()
