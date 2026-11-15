"""Controlled frozen replay plus targeted real verification; old runs stay intact."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
from functools import partial
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
RUNS = {
    "benchmark": ("contradiction-benchmark-20261109-run1", Path("C:/Users/Administrator/Downloads/ResearchGuard_Contradiction_Benchmark.pdf")),
    "soil": ("2217137-full-e2e-20261109-run1", ROOT.parent / "2217137.pdf"),
    "entropy": ("entropy-full-e2e-20261110-run1", ROOT.parent / "entropy-25-00463.pdf"),
    "nano": ("nanomaterials-full-e2e-20261110-run2", ROOT.parent / "nanomaterials-15-00588.pdf"),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "model-calls").mkdir()
    save = lambda name, data: (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    def progress(stage, **data):
        row = {"time": datetime.now(timezone.utc).isoformat(), "stage": stage, **data}
        with (out / "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps(row, ensure_ascii=False), flush=True)
    from app.main import app
    os.environ["RESEARCHGUARD_JOB_DIR"] = str(out / "jobs")
    from fastapi.testclient import TestClient
    from app.researchguard.domain import ParsedManuscript, VerificationResult, SourceDocument
    from app.services.claim_extractor import extract_claims
    from app.services.reference_notice import is_unreferenced_publisher_notice
    from app.services.bibliographic_recovery import recover_bibliographic_result
    from app.services.manuscript_verification import verify_manuscript_core, plan_manuscript_pairs
    from app.services.source_store import LocalSourceStore, verify_source_durability
    from app.services.llm.provider import LLMProvider, OpenAICompatibleLLMProvider
    logging.getLogger().addHandler(logging.FileHandler(out / "backend.log", encoding="utf-8"))
    save("manifest.json", {"started_at": datetime.now(timezone.utc).isoformat(), "live": args.live,
        "selection": "All old ambiguous entropy claims; all 3 soil metadata insufficients; entropy empty-evidence claim. Acquisition failures excluded.",
        "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            ROOT / "backend/app/services/claim_attribution.py", ROOT / "backend/app/services/reference_notice.py",
            ROOT / "backend/app/services/bibliographic_recovery.py", ROOT / "backend/app/services/manuscript_verification.py",
            ROOT / "backend/app/researchguard/adapters/grobid_tei.py")}})
    prepared, replay = {}, {}
    for name, (directory, pdf) in RUNS.items():
        old = ROOT / "output" / directory
        view = json.loads((old / "06-job-final.json").read_text(encoding="utf-8"))
        snapshot = json.loads((old / "jobs" / (view["job_id"] + ".json")).read_text(encoding="utf-8"))["snapshot"]
        parsed = ParsedManuscript.model_validate(snapshot["parsed"])
        cited = {rid for call in parsed.citation_callouts for rid in call.reference_ids}
        notices = [r for r in parsed.references if is_unreferenced_publisher_notice(r, cited)]
        clean = parsed.model_copy(update={"references": tuple(r for r in parsed.references if r not in notices)})
        responses = {}
        for request_file in (old / "model-calls").glob("*-_ProposalEnvelope-request.json"):
            response_file = request_file.with_name(request_file.name.replace("-request.json", "-response.json"))
            payload = json.loads(json.loads(request_file.read_text(encoding="utf-8"))["prompt"])
            responses[payload["context_id"]] = json.loads(response_file.read_text(encoding="utf-8"))["result"]
        class ReplayProvider(LLMProvider):
            model = "frozen-real-output"
            def generate(self, prompt, *, response_model=None, **kwargs):
                return response_model.model_validate(responses[json.loads(prompt)["context_id"]])
        extraction = asyncio.run(extract_claims(clean, provider=ReplayProvider()))
        old_by_text = {(c["context_id"], c["text"]): c for c in view["claims"]}
        attr_rows = []
        for claim in extraction.claims:
            previous = old_by_text[(claim.context_id, claim.text)]
            assert claim.source_spans == tuple(type(s).model_validate(s0) for s, s0 in zip(claim.source_spans, previous["source_spans"]))
            if previous["attribution_status"] == "resolved":
                assert claim.attribution_status == "resolved" and list(claim.reference_ids) == previous["reference_ids"]
            attr_rows.append({"text": claim.text, "old": previous["attribution_status"], "new": claim.attribution_status.value,
                              "old_reference_ids": previous["reference_ids"], "new_reference_ids": claim.reference_ids})
        assert len(extraction.claims) == len(view["claims"])
        verdict_rows = []
        for task in view["tasks"]:
            if task["state"] != "completed":
                continue
            original = VerificationResult.model_validate(task["pair_outcome"]["verification"])
            binding = task["pair_outcome"]["binding"]
            source = SourceDocument(id=binding["source_document_id"], reference_id=binding["reference_id"],
                                    doi=binding["doi"], content_hash=binding["source_version"], retrieval_status="available")
            claim = next(c for c in view["claims"] if c["id"] == task["claim_id"])
            current = recover_bibliographic_result(claim["text"], original, source)
            if original.verdict != "INSUFFICIENT":
                assert current == original
            verdict_rows.append({"text": claim["text"], "old": original.verdict.value, "new": current.verdict.value,
                "recovery": current.traceability.metadata.get("bibliographic_recovery")})
        replay[name] = {"old_claims": len(view["claims"]), "new_claims": len(extraction.claims),
            "attribution": attr_rows, "verdicts": verdict_rows,
            "removed_notices": [r.model_dump(mode="json") for r in notices],
            "old_references": len(parsed.references), "new_references": len(clean.references)}
        prepared[name] = (clean, extraction, view)
        save(name + "-extraction.json", extraction.model_dump(mode="json"))
        save(name + "-parsed.json", clean.model_dump(mode="json"))
        progress("frozen_replay", paper=name, attribution_changes=sum(r["old"] != r["new"] for r in attr_rows),
                 verdict_changes=sum(r["old"] != r["new"] for r in verdict_rows), notices=len(notices))
    save("01-frozen-replay.json", replay)
    # Exercise the actual PDF -> GROBID -> TEI -> API filter, independent of LLMs.
    parse_checks = {}
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        for name, (directory, pdf) in RUNS.items():
            response = client.post("/api/manuscripts/parse", files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")})
            data = response.json()
            save(name + "-reparse.json", data)
            assert response.status_code == 200, (name, response.status_code)
            old_parse = json.loads((ROOT / "output" / directory / "01-parse.json").read_text(encoding="utf-8"))
            new_ids = {r["id"] for r in data["parsed"]["references"]}
            removed_ids = {r["id"] for r in replay[name]["removed_notices"]}
            old_ids = {r["id"] for r in old_parse["parsed"]["references"]}
            assert old_ids - new_ids == removed_ids and not new_ids - old_ids
            assert data["parsed"]["citation_callouts"] == old_parse["parsed"]["citation_callouts"]
            parse_checks[name] = {"removed_ids": sorted(removed_ids), "normal_ids_preserved": True,
                                 "callouts_unchanged": True, "new_reference_count": len(new_ids)}
            progress("pdf_reparse", paper=name, removed=len(removed_ids))
    save("02-parse-checks.json", parse_checks)
    if not args.live:
        return
    original_generate = OpenAICompatibleLLMProvider.generate
    counter, lock = 0, threading.Lock()
    def recording(self, prompt, *, system=None, response_model=None):
        nonlocal counter
        with lock:
            counter += 1
            index = counter
        prefix = f"model-calls/{index:03d}-{response_model.__name__ if response_model else 'text'}"
        save(prefix + "-request.json", {"prompt": prompt, "system": system, "model": self.model})
        try:
            result = original_generate(self, prompt, system=system, response_model=response_model)
            save(prefix + "-response.json", result.model_dump(mode="json") if hasattr(result, "model_dump") else result)
            return result
        except Exception as exc:
            save(prefix + "-error.json", {"type": type(exc).__name__})
            raise
    OpenAICompatibleLLMProvider.generate = recording
    async def run_selected(name):
        parsed, extraction, view = prepared[name]
        selected_texts = {r["text"] for r in replay[name]["attribution"] if r["old"] != r["new"]}
        old_tasks = {t["claim_id"]: t for t in view["tasks"]}
        for claim in view["claims"]:
            t = old_tasks.get(claim["id"])
            if t and t["state"] == "completed" and t["pair_outcome"]["verification"]["verdict"] == "INSUFFICIENT":
                selected_texts.add(claim["text"])
        plan, _ = plan_manuscript_pairs(parsed, extraction)
        selected = [(c.id, r.id) for c, r, _ in plan if c.text in selected_texts]
        expected = {t["reference_id"]: t["source_binding"]["source_version"] for t in view["tasks"]
                    if t.get("source_binding") and t["source_binding"].get("source_version")}
        records = []
        async def finished(pair):
            claim = next(c for c in extraction.claims if c.id == pair.claim_id)
            row = pair.model_dump(mode="json")
            row["claim_text"] = claim.text
            records.append(row)
            save(name + "-live-pairs.json", records)
            progress("live_pair", paper=name, completed=len(records), total=len(selected),
                     reason=pair.reason_code, verdict=pair.verification.verdict)
        progress("live_started", paper=name, pairs=len(selected))
        result = await verify_manuscript_core(parsed, extraction, selected_pairs=selected,
            expected_source_versions=expected, on_pair_finished=finished,
            source_durability_check=partial(verify_source_durability, store=LocalSourceStore()))
        save(name + "-live-result.json", result.model_dump(mode="json"))
        progress("live_finished", paper=name, coverage=result.coverage.model_dump(mode="json"))
    async def run_all():
        await asyncio.gather(run_selected("soil"), run_selected("entropy"))
    try:
        asyncio.run(run_all())
    finally:
        OpenAICompatibleLLMProvider.generate = original_generate
    progress("retest_finished")


if __name__ == "__main__":
    main()
