"""Summarize a finished real manuscript run without inventing ground truth."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--source-cache", default=str(ROOT / "backend/data/researchguard/sources"))
    args = parser.parse_args()
    out = Path(args.run)
    load = lambda name: json.loads((out / name).read_text(encoding="utf-8"))
    view, parsed, extraction, manifest = load("06-job-final.json"), load("01-parse.json"), load("03-extract.json"), load("manifest.json")
    assert view["status"] not in {"pending", "running"}
    refs = {ref["id"]: ref for ref in view["references"]}
    tasks = {}
    for task in view["tasks"]:
        tasks.setdefault(task["claim_id"], []).append(task)
    rows = []
    for index, claim in enumerate(view["claims"], 1):
        for task in tasks.get(claim["id"], [None]):
            outcome = (task or {}).get("pair_outcome") or {}
            result = outcome.get("verification") or {}
            trace = result.get("traceability") or {}
            legacy = (trace.get("metadata") or {}).get("legacy_provenance") or {}
            judge = legacy.get("adjudicator") or {}
            evidence = result.get("evidence_chunks") or []
            binding = outcome.get("binding") or {}
            reference = refs.get((task or {}).get("reference_id")) or {}
            actual = result.get("verdict")
            mapped = {"SUPPORTED": "SUPPORTS", "CONTRADICTED": "CONTRADICTS"}.get(actual, actual)
            rows.append({"claim_number": index, "claim_id": claim["id"], "text": claim["text"],
                "attribution": claim["attribution_status"], "doi": reference.get("doi"),
                "reference_id": reference.get("id"), "task_state": (task or {}).get("state", "attribution_blocked"),
                "reason_code": (task or {}).get("reason_code"), "original_agent_verdict": judge.get("verdict"),
                "final_verdict": actual, "confidence": result.get("confidence"), "evidence_count": len(evidence),
                "validator_changed": bool(judge.get("verdict") and judge["verdict"] != mapped),
                "validation_warnings": legacy.get("validation_warnings") or [],
                "source_version": binding.get("source_version"),
                "partial_retrieval": any(c["metadata"].get("paperqa_retrieval_incomplete") for c in evidence),
                "explanation": result.get("explanation")})
    proposals = []
    for path in (out / "model-calls").glob("*-_ProposalEnvelope-response.json"):
        proposals.extend(json.loads(path.read_text(encoding="utf-8"))["result"]["claims"])
    from app.services.source_store import LocalSourceStore
    store = LocalSourceStore(args.source_cache)
    sources = []
    for number, reference in enumerate(view["references"], 1):
        related = [t for t in view["tasks"] if t["reference_id"] == reference["id"]]
        bindings = [(t.get("pair_outcome") or {}).get("binding") or {} for t in related]
        bound = next((b for b in bindings if b.get("source_version")), {})
        doi = reference.get("doi")
        artifact = store.get(doi) if doi and related else None
        hash_ok = bool(artifact and bound.get("source_version") == "sha256:" + hashlib.sha256(artifact.content).hexdigest())
        metadata = next((c["metadata"] for t in related for c in ((t.get("pair_outcome") or {}).get("verification") or {}).get("evidence_chunks", [])), {})
        sources.append({"reference_number": number, "reference_id": reference["id"], "doi": doi,
            "title": artifact.paper.title if artifact else reference.get("title"), "pair_count": len(related),
            "task_states": dict(Counter(t["state"] for t in related)), "source_version": bound.get("source_version"),
            "hash_verified": hash_ok, "identity": metadata.get("source_identity_status"),
            "cache_hit": metadata.get("source_cache_hit"), "origin": metadata.get("source_origin"),
            "format": artifact.format if artifact else None,
            "provenance": bound.get("provenance"), "raw_reference": reference["raw_text"]})
    completed = [row for row in rows if row["task_state"] == "completed"]
    summary = {"job_id": view["job_id"], "job_status": view["status"],
        "ground_truth_available": False, "classification_accuracy": None,
        "paragraphs": len(view["paragraphs"]), "reference_records": len(view["references"]),
        "references_with_pairs": sum(s["pair_count"] > 0 for s in sources),
        "sources_hash_verified": sum(s["hash_verified"] for s in sources),
        "callouts": len(view["citation_callouts"]), "contexts": len(view["contexts"]),
        "context_states": dict(Counter(c["status"] for c in view["context_results"])),
        "raw_proposals": len(proposals), "proposal_intents": dict(Counter(p["attribution_intent"] for p in proposals)),
        "final_claims": len(view["claims"]), "final_attribution": dict(Counter(c["attribution_status"] for c in view["claims"])),
        "rejected_proposals": sum(len(c["rejected_proposals"]) for c in view["context_results"]),
        "pair_count": len(view["tasks"]), "task_states": dict(Counter(t["state"] for t in view["tasks"])),
        "original_agent_verdicts": dict(Counter(row["original_agent_verdict"] for row in completed)),
        "final_verdicts": dict(Counter(row["final_verdict"] for row in completed)),
        "validator_changes": sum(row["validator_changed"] for row in completed),
        "nonempty_evidence_completed_pairs": sum(row["evidence_count"] > 0 for row in completed),
        "empty_evidence_completed_pairs": sum(row["evidence_count"] == 0 for row in completed),
        "partial_retrieval_pairs": sum(row["partial_retrieval"] for row in completed),
        "model_generate_errors": len(list((out / "model-calls").glob("*-error.json"))),
        "parse_diagnostics": dict(Counter(d["code"] for d in parsed["diagnostics"])),
        "extraction_diagnostics": dict(Counter(d["code"] for d in extraction["diagnostics"])),
        "generated_at": datetime.now(timezone.utc).isoformat()}
    (out / "09-summary.json").write_text(json.dumps({"summary": summary, "claims": rows, "sources": sources}, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, values in (("10-claim-results.csv", rows), ("11-source-results.csv", sources)):
        with (out / name).open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)
    events = [json.loads(line) for line in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    started, ended = datetime.fromisoformat(manifest["started_at"]), datetime.fromisoformat(events[-1]["time"])
    local = timezone(timedelta(hours=8))
    lines = [f"# {manifest['pdf_name']} 全量真实流程测试", "",
        f"运行：{started.astimezone(local):%Y-%m-%d %H:%M:%S} 至 {ended.astimezone(local):%H:%M:%S}（Asia/Shanghai），耗时 {(ended-started).total_seconds():.1f} 秒。",
        f"Job：`{view['job_id']}`，最终状态 `{view['status']}`；PDF SHA-256：`{manifest['pdf_sha256']}`。", "",
        "使用实际 GROBID、Reference Resolver、来源获取、模型提取、PaperQA2、三 Agent 和 Validator。只测试当前代码，没有按本次结果修改产品逻辑。输出使用独立 Job Store，不会自动出现在默认前端 History。", "",
        "## 分阶段结果", "", "| 指标 | 结果 |", "|---|---|"]
    for key in ("paragraphs", "reference_records", "references_with_pairs", "sources_hash_verified", "callouts", "contexts", "context_states", "raw_proposals", "proposal_intents", "final_claims", "final_attribution", "rejected_proposals", "pair_count", "task_states", "original_agent_verdicts", "final_verdicts", "validator_changes", "partial_retrieval_pairs", "model_generate_errors"):
        lines.append(f"| {key} | {summary[key]} |")
    lines += ["", "## 每条 Claim 输出", "", "| 编号 | Claim | 原始 Agent | 最终判定 | 状态 |", "|---|---|---|---|---|"]
    for row in rows:
        text = row["text"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['claim_number']} | {text} | {row['original_agent_verdict']} | {row['final_verdict']} | {row['task_state']} |")
    lines += ["", "## 来源", "", "| 引用记录 | DOI | Pair 数 | 状态 | Hash |", "|---|---|---|---|---|"]
    for source in sources:
        lines.append(f"| R{source['reference_number']} | {source['doi']} | {source['pair_count']} | {source['task_states']} | {source['hash_verified']} |")
    lines += ["", "## 非支持结果及诊断", ""]
    for row in rows:
        if row["final_verdict"] != "SUPPORTED":
            lines += [f"### Claim {row['claim_number']}：{row['final_verdict'] or row['task_state']}", "", row["text"], "", row["explanation"] or str(row["reason_code"]), "",
                      "Validator warnings: " + json.dumps(row["validation_warnings"], ensure_ascii=False), ""]
    lines += ["## 解释边界", "",
        "这篇文章没有单独的逐条标准答案，classification_accuracy 保持 null。SUPPORTED 比例表示系统输出分布，不能作为正确率；INSUFFICIENT 是未完成事实判定，也不自动等同于原文错误。模型给出的 CONTRADICTED/OVERSTATED 仍需结合对应证据人工审核。",
        "流程按当前产品范围处理引用句内的 Claim，并不表示已经独立核验整篇文章所有无引用句中的事实。原始 Proposal、排除意图和诊断均保存，不能只以完成 Pair 数评价提取覆盖。",
        "来源复用缓存时重新检查身份和实际字节 Hash；新获取与缓存命中情况见 11-source-results.csv。版本不确定等 provenance warnings 原样保存在 JSON。",
        "原始记录：01-parse.json、02-resolve.json、03-extract.json、06-job-final.json、07-events.json、model-calls/ 和 jobs/。09-summary.json、10-claim-results.csv、11-source-results.csv 为本报告可检查的明细。", ""]
    (out / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
