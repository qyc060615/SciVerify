"""Read-only historical replay and data integrity audit. No model/network calls."""
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
from app.services.verification_job_store import LocalJobStore
from app.services.verification_job_models import JobSnapshot
from app.tests.test_scientific_verdict_quality import REAL, CASES, real_inputs, validate, analyses, item

OUT = Path(__file__).parent
before = json.loads((OUT / "integrity-before.json").read_text(encoding="utf-8"))
integrity = {p: hashlib.sha256((REPO / p).read_bytes()).hexdigest() == digest for p, digest in before.items()}
store = LocalJobStore(REPO / "backend/data/researchguard/jobs")
compatibility = []
for name in ["job_355c3d27d93e47ecaa4126378989f61b", "job_3dbc1247f5f34c20b65a81831455e40f"]:
    snapshot = store.load(name)
    roundtrip = JobSnapshot.model_validate_json(snapshot.model_dump_json())
    compatibility.append({"job_id": name, "load": "PASS", "roundtrip": roundtrip == snapshot,
                          "state": snapshot.state.value, "tasks": len(snapshot.tasks),
                          "persisted_verdicts": [t.pair_outcome.verification.verdict.value
                              for t in snapshot.tasks if t.pair_outcome and t.pair_outcome.verification.verdict]})
evidence, agents = real_inputs()
replay = validate(evidence, agents, REAL["claim"]["text"])
results = []
for case in CASES:
    result = validate([item(case["text"])] if case["text"] else [],
                      analyses(case["expected"], case["text"], case["reason"]), case["claim"])
    results.append({"case": case["id"], "expected": case["expected"], "actual": result.verdict.value,
                    "confidence": result.confidence, "pass": result.verdict.value == case["expected"]})
report = {"mode": "Offline deterministic replay + human-labeled agent fixtures; no live model evaluation",
          "historical_replay": {"original_verdict": replay.original_verdict.value,
              "original_confidence": replay.original_confidence, "validated_verdict": replay.verdict.value,
              "validated_confidence": replay.confidence, "warnings": replay.validation_warnings},
          "old_jobs": compatibility, "protected_file_count": len(integrity),
          "protected_files_unchanged": all(integrity.values()),
          "changed_protected_files": [p for p, unchanged in integrity.items() if not unchanged],
          "fixture_cases": results}
(OUT / "offline-audit-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "fixture_cases"}, indent=2))
assert all(integrity.values()) and all(r["pass"] for r in results)
assert all(j["roundtrip"] for j in compatibility)
