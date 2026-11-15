from __future__ import annotations

import json
from pathlib import Path

from app.schemas.verification import VerificationResponse


def default_results_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "evaluation" / "results"


def default_baseline_path() -> Path:
    return Path(__file__).resolve().parents[2] / "evaluation" / "baseline.json"


def load_verification_fixture(path: Path) -> VerificationResponse:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return VerificationResponse.model_validate(payload)


def load_case_fixture(fixtures_dir: Path, case_id: str) -> VerificationResponse:
    fixture_path = fixtures_dir / f"{case_id}.json"
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found for case '{case_id}': {fixture_path}")
    return load_verification_fixture(fixture_path)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
