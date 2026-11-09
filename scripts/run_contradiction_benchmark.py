"""Run the real local API pipeline without loading any grading answer key."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "model-calls").mkdir()

    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def progress(stage, **values):
        record = {"time": datetime.now(timezone.utc).isoformat(), "stage": stage, **values}
        with (out / "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(json.dumps(record, ensure_ascii=False), flush=True)

    from app.main import app
    from fastapi.testclient import TestClient
    from app.services.llm.provider import OpenAICompatibleLLMProvider
    # A separate job directory prevents startup recovery from touching old jobs.
    os.environ["RESEARCHGUARD_JOB_DIR"] = str(out / "jobs")
    os.environ["RESEARCHGUARD_JOBS_ENABLED"] = "1"
    logging.getLogger().addHandler(logging.FileHandler(out / "backend.log", encoding="utf-8"))
    content = Path(args.pdf).read_bytes()
    save("manifest.json", {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pdf_name": Path(args.pdf).name,
        "pdf_sha256": hashlib.sha256(content).hexdigest(),
        "answer_key_used_by_pipeline": False,
        "job_store_isolated": True,
        "source_cache_policy": "Reuse configured cache with normal identity/hash validation",
        "models": {key: os.getenv(key) for key in ("LLM_MODEL", "PAPERQA2_MODEL", "PAPERQA2_EMBEDDING_MODEL")},
        "code_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            "backend/app/services/claim_attribution.py", "backend/app/services/claim_extractor.py",
            "backend/app/researchguard/adapters/claim_llm.py", "backend/app/researchguard/adapters/paperqa2.py",
            "backend/app/services/verification_validator.py")},
    })
    original_generate = OpenAICompatibleLLMProvider.generate
    lock = threading.Lock()
    sequence = 0

    def recorded_generate(provider, prompt, *, system=None, response_model=None):
        nonlocal sequence
        with lock:
            sequence += 1
            index = sequence
        name = response_model.__name__ if response_model else "text"
        prefix = f"model-calls/{index:03d}-{name}"
        save(prefix + "-request.json", {"prompt": prompt, "system": system, "model": provider.model,
                                      "response_schema": name})
        started = time.monotonic()
        try:
            result = original_generate(provider, prompt, system=system, response_model=response_model)
            save(prefix + "-response.json", {"elapsed_seconds": time.monotonic() - started,
                "result": result.model_dump(mode="json") if hasattr(result, "model_dump") else result})
            return result
        except Exception as exc:
            save(prefix + "-error.json", {"elapsed_seconds": time.monotonic() - started,
                                         "exception_type": type(exc).__name__})
            raise

    OpenAICompatibleLLMProvider.generate = recorded_generate

    def request(client, stage, path, **kwargs):
        progress(stage + "_started")
        started = time.monotonic()
        response = client.post(path, **kwargs)
        data = response.json()
        save(stage + ".json", data)
        progress(stage + "_finished", http_status=response.status_code,
                 elapsed_seconds=round(time.monotonic() - started, 2))
        if response.status_code >= 400:
            raise RuntimeError(f"{stage} failed: HTTP {response.status_code}; inspect saved artifact")
        return data

    try:
        with TestClient(app, base_url="http://127.0.0.1:8000") as client:
            parsed = request(client, "01-parse", "/api/manuscripts/parse",
                files={"file": (Path(args.pdf).name, content, "application/pdf")})
            def envelope(value):
                return {key: value[key] for key in ("schema_version", "scope", "offset_unit", "parsed")}
            resolved = request(client, "02-resolve", "/api/manuscripts/resolve-references", json=envelope(parsed))
            extracted = request(client, "03-extract", "/api/manuscripts/extract-claims", json=envelope(resolved))
            progress("extraction_counts", references=len(resolved["parsed"]["references"]),
                callouts=len(resolved["parsed"]["citation_callouts"]), claims=len(extracted["claims"]),
                attribution=dict(Counter(c["attribution_status"] for c in extracted["claims"])))
            # The job contract uses the domain manuscript's private provenance field.
            domain = dict(resolved["parsed"])
            domain["manuscript"] = {**domain["manuscript"], "content_locator": "benchmark:uploaded-pdf"}
            created = request(client, "04-create-job", "/api/verification/jobs",
                              json={"parsed": domain, "extraction": extracted})
            job_id = created["job_id"]
            progress("job_created", job_id=job_id, pairs=len(created["tasks"]))
            last, deadline = None, time.monotonic() + 3600
            while True:
                response = client.get(f"/api/verification/jobs/{job_id}")
                response.raise_for_status()
                view = response.json()
                states = dict(Counter(t["state"] for t in view["tasks"]))
                fingerprint = (view["status"], json.dumps(states, sort_keys=True))
                if fingerprint != last:
                    save("05-job-latest.json", view)
                    progress("job_progress", status=view["status"], states=states, revision=view["revision"])
                    last = fingerprint
                if view["status"] not in {"pending", "running"}:
                    save("06-job-final.json", view)
                    save("07-events.json", client.get(f"/api/verification/jobs/{job_id}/events").json())
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("Benchmark exceeded one-hour execution bound")
                time.sleep(2)
            progress("pipeline_finished", job_id=job_id, status=view["status"], states=states)
    except Exception as exc:
        progress("pipeline_failed", exception_type=type(exc).__name__)
        raise
    finally:
        OpenAICompatibleLLMProvider.generate = original_generate


if __name__ == "__main__":
    main()
