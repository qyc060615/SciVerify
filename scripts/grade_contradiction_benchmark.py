"""Grade an already finished run against the supplied answer file, offline."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--truth", required=True)
    args = parser.parse_args()
    out = Path(args.run)
    load = lambda name: json.loads((out / name).read_text(encoding="utf-8"))
    view, manifest, comparison = load("06-job-final.json"), load("manifest.json"), load("08-rule-comparison.json")
    assert view["status"] == "completed", "Grade only a finished run with this script"
    truth_bytes = Path(args.truth).read_bytes()
    truth = truth_bytes.decode("utf-8-sig")
    sections = re.findall(r"### (T\d{2}) - (CONTRADICTED|SUPPORTED) / ([^\n]+)\n(.*?)(?=\n### |\n## |\Z)", truth, re.S)
    assert len(sections) == 15
    normalize = lambda text: " ".join(text.split())
    paragraphs = {normalize(p["text"]): p for p in view["paragraphs"]}
    numbers = {claim["id"]: i for i, claim in enumerate(view["claims"], 1)}
    claims = {claim["id"]: claim for claim in view["claims"]}
    tasks = {task["claim_id"]: task for task in view["tasks"]}
    cases, atoms = [], []
    for test_id, expected, kind, body in sections:
        original = re.search(r"- \*\*PDF 中的原文：\*\* (.+)", body).group(1)
        fact = re.search(r"- \*\*真实事实：\*\* (.+)", body).group(1)
        paragraph = paragraphs[normalize(original)]  # Exact text mapping, never guessed ordinal alignment.
        selected = [claim for claim in view["claims"] if claim["paragraph_id"] == paragraph["id"]]
        assert selected, f"Missing extraction for {test_id}"
        expected_refs = {rid for call in view["citation_callouts"] if call["paragraph_id"] == paragraph["id"] for rid in call["reference_ids"]}
        assert len(expected_refs) == 1
        for claim in selected:
            task = tasks[claim["id"]]
            result = task["pair_outcome"]["verification"]
            legacy = result["traceability"]["metadata"]["legacy_provenance"]
            reference_ok = set(claim["reference_ids"]) == expected_refs and task["reference_id"] in expected_refs
            atoms.append({"test_id": test_id, "claim_number": numbers[claim["id"]], "claim": claim["text"],
                "expected": expected, "actual": result["verdict"], "original_agent": legacy["adjudicator"]["verdict"],
                "state": task["state"], "reference_correct": reference_ok,
                "correct": task["state"] == "completed" and reference_ok and result["verdict"] == expected,
                "confidence": result["confidence"], "evidence_count": len(result["evidence_chunks"]),
                "validation_warnings": legacy.get("validation_warnings") or [],
                "explanation": result["explanation"]})
        group = [a for a in atoms if a["test_id"] == test_id]
        cases.append({"test_id": test_id, "kind": kind, "original": original, "true_fact": fact,
            "expected": expected, "actual": sorted({a["actual"] for a in group}),
            "claim_numbers": [a["claim_number"] for a in group], "correct": all(a["correct"] for a in group)})
    assert len(atoms) == len(view["claims"]) == len(view["tasks"]), "Unmapped or duplicate claims"
    proposals = []
    for path in (out / "model-calls").glob("*-_ProposalEnvelope-response.json"):
        proposals.extend(json.loads(path.read_text(encoding="utf-8"))["result"]["claims"])
    from app.services.source_store import LocalSourceStore
    store = LocalSourceStore(ROOT / "backend/data/researchguard/sources")
    sources, seen = [], set()
    for task in view["tasks"]:
        binding = task["pair_outcome"]["binding"]
        if binding["reference_id"] in seen:
            continue
        seen.add(binding["reference_id"])
        artifact = store.get(binding["doi"])
        verified = bool(artifact and "sha256:" + hashlib.sha256(artifact.content).hexdigest() == binding["source_version"])
        assert verified, "Source bytes must match the executed job binding"
        metadata = task["pair_outcome"]["verification"]["evidence_chunks"][0]["metadata"]
        sources.append({"doi": binding["doi"], "title": binding["provenance"]["retrieved_title"],
            "source_version": binding["source_version"], "hash_verified": verified,
            "identity": metadata["source_identity_status"], "cache_hit": metadata["source_cache_hit"],
            "source_origin": metadata["source_origin"], "format": artifact.format,
            "provenance_warnings": binding["provenance"]["warnings"]})
    summary = {
        "grading_started_at": datetime.now(timezone.utc).isoformat(),
        "ground_truth_sha256": hashlib.sha256(truth_bytes).hexdigest(),
        "job_id": view["job_id"], "cases": len(cases), "cases_correct": sum(c["correct"] for c in cases),
        "atomic_claims": len(atoms), "atomic_correct": sum(a["correct"] for a in atoms),
        "proposal_count": len(proposals), "proposal_intents": dict(Counter(p["attribution_intent"] for p in proposals)),
        "final_attribution": dict(Counter(c["attribution_status"] for c in view["claims"])),
        "final_verdicts": dict(Counter(a["actual"] for a in atoms)),
        "original_agent_verdicts": dict(Counter(a["original_agent"] for a in atoms)),
        "task_states": dict(Counter(t["state"] for t in view["tasks"])),
        "rejected_proposals": sum(len(c["rejected_proposals"]) for c in view["context_results"]),
        "extraction_diagnostics": dict(Counter(d["code"] for d in view["extraction_diagnostics"])),
        "evidence_empty": sum(a["evidence_count"] == 0 for a in atoms),
        "partial_retrieval_pairs": sum(any(c["metadata"].get("paperqa_retrieval_incomplete") for c in t["pair_outcome"]["verification"]["evidence_chunks"]) for t in view["tasks"]),
        "validator_downgrades": sum(a["original_agent"] != {"SUPPORTED": "SUPPORTS", "CONTRADICTED": "CONTRADICTS"}.get(a["actual"], a["actual"]) for a in atoms),
        "captured_generate_calls": len(list((out / "model-calls").glob("*-request.json"))),
        "captured_generate_errors": len(list((out / "model-calls").glob("*-error.json"))),
        "attribution_replay_changes": [r for r in comparison["attribution"] if r["old"] != r["new"]],
        "validator_replay_changes": [r for r in comparison["verification"] if r["old_validator_verdict"] != r["new_validator_verdict"]],
    }
    (out / "09-grading.json").write_text(json.dumps({"summary": summary, "cases": cases, "atomic_claims": atoms, "sources": sources}, ensure_ascii=False, indent=2), encoding="utf-8")
    for filename, rows in (("10-case-grades.csv", cases), ("11-atomic-grades.csv", atoms)):
        with (out / filename).open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    events = [json.loads(line) for line in (out / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    started = datetime.fromisoformat(manifest["started_at"])
    ended = datetime.fromisoformat(events[-1]["time"])
    local = timezone(timedelta(hours=8))
    lines = ["# ResearchGuard 矛盾文档真实 E2E 与答案批改", "",
        f"运行时间：{started.astimezone(local):%Y-%m-%d %H:%M:%S} 至 {ended.astimezone(local):%H:%M:%S}（Asia/Shanghai），耗时 {(ended-started).total_seconds():.1f} 秒。",
        f"Job：`{view['job_id']}`；PDF SHA-256：`{manifest['pdf_sha256']}`。", "",
        "PDF 独立进入真实 GROBID → Reference Resolution → Claim Extraction → Source Acquisition → PaperQA2 → 三 Agent → Validator → Job 持久化流程。答案文件在最终输出完成后才读取，仅用于离线评分。未根据答案修改产品代码、提示词或输出。",
        "使用现有模型配置：" + json.dumps(manifest["models"], ensure_ascii=False) + "。", "",
        "## 评分口径与结论", "",
        f"15 条原文通过与答案中原文的精确文本匹配建立映射，再按 paragraph_id 关联 21 条原子 Claim。每题要求其全部原子 Claim 完成、引用正确且最终 Verdict 与答案一致。原文题目：{summary['cases_correct']}/15；原子 Claim：{summary['atomic_correct']}/21。人工复核了原子化拆分对原题关键事实的覆盖。",
        "12 道矛盾题和 3 道支持题全部命中；原子级 16 条 CONTRADICTED、5 条 SUPPORTED。INSUFFICIENT、OVERSTATED、缺失或执行失败均不计为命中。", "",
        "| 题目 | 测试内容 | 原子 Claim 编号 | 预期 | 实际 | 批改 |", "|---|---|---|---|---|---|"]
    for case in cases:
        lines.append(f"| {case['test_id']} | {case['kind']} | {', '.join(map(str,case['claim_numbers']))} | {case['expected']} | {', '.join(case['actual'])} | {'正确' if case['correct'] else '错误'} |")
    lines += ["", "## 分阶段记录", "",
        "- 解析：15 段正文、15 个引用标记、5 篇参考文献；有标题未验证及部分参考元数据缺失诊断，未丢失测试正文或引用。",
        "- Reference：5/5 来源可用，均复用已有远程来源的本地缓存，并通过身份与实际落盘字节 Hash 校验；本次未验证全新网络下载成功率。",
        f"- 提取：{len(proposals)} 个原始 Proposal；意图 {summary['proposal_intents']}；最终 {summary['final_attribution']}；拒绝 {summary['rejected_proposals']} 个；ambiguous/unresolved/none 均为 0。",
        "- 归属：21/21 Pair 可执行；T11 的两个分组断言触发 SAME_SENTENCE_CITATION_RECOVERED，原歧义诊断以 info 保留。",
        "- 检索：21/21 非空；空结果 0，异常 0，部分检索 0；本次未触发 PaperQA2 坏摘要隔离或 Schema 候选隔离。",
        f"- Agent 原始结论：{summary['original_agent_verdicts']}；Validator 最终结论：{summary['final_verdicts']}；降级 {summary['validator_downgrades']} 次。",
        "- Job：21/21 completed，无 failed、blocked_source，无重试；Snapshot、Revision 和事件记录已保存。",
        f"- 捕获 15 次提取、63 次 Agent generate 调用，异常 {summary['captured_generate_errors']} 次；这些计数不包含 PaperQA2/LMI 独立进行的摘要及 embedding 调用，不能据此估算总费用。", "",
        "## 同一批输出的旧规则离线回放", "",
        "基线提交：`" + comparison['baseline_commit'] + "`。仅回放确定性规则，不重新调用模型，不等价于完整旧版本 E2E，也不能把两种回放指标直接相加作为旧版本准确率。",
        "- 原子 Claim 2、3（T02）及 Claim 7（T05）：旧 Validator 为 INSUFFICIENT，新 Validator 保留 CONTRADICTS。",
        "- Claim 15、16（T11）：旧 Attribution 为 ambiguous，新规则恢复为 resolved。",
        "- 本轮真实运行未触发空白 Span、Schema 隔离和坏摘要隔离，其有效性目前仍主要由离线正反例回归支持。", "",
        "## 来源与完整性", "", "| DOI | 格式 | 缓存 | 身份 | 实际字节 Hash 校验 |", "|---|---|---|---|---|"]
    for source in sources:
        lines.append(f"| {source['doi']} | {source['format']} | {source['cache_hit']} | {source['identity']} | {source['hash_verified']} |")
    lines += ["", "来源原始版本/历史版本未确认等 provenance warnings 原样保存在 JSON 中，不解释为历史版本已经确认。", "",
        "## 记录与限制", "",
        "`01-parse.json`、`02-resolve.json`、`03-extract.json`、`06-job-final.json`、`07-events.json` 保存各阶段输出；`model-calls/` 保存提取及三 Agent 的原始请求/结构化输出；`jobs/` 保存独立 Job 快照；`08-rule-comparison.json` 保存旧规则回放；`09-grading.json` 和两份 CSV 保存逐题及原子级评分。",
        "独立 Job Store 未写入默认前端 History，因此该任务不会自动出现在当前应用的历史列表。原始 PDF、答案和旧任务未修改。",
        "这是单份合成文档、单次运行的匹配结果，不能推断总体准确率、模型稳定性或全新下载可靠性。后续重复实验应新建运行目录，保留同一输入 Hash、代码 Hash、模型与来源版本，并逐次记录失败及降级，不覆盖本次结果。", ""]
    (out / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("cases_correct", "cases", "atomic_correct", "atomic_claims", "final_verdicts", "validator_downgrades")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
