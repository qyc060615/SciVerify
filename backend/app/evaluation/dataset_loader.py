from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator, ValidationError

from app.schemas.verification import Verdict
from app.utils.doi import InvalidDOIError, normalize_doi

VALID_VERDICTS = {verdict.value for verdict in Verdict}

# Known placeholder DOI patterns that should not be used for live evaluation
PLACEHOLDER_DOI_PATTERNS = [
    "10.1000/example",
    "10.1000/benchmark",
    "10.1000/placeholder",
    "10.1000/fake",
    "10.1000/test",
]


def is_placeholder_doi(doi: str) -> bool:
    """Check if a DOI matches known placeholder patterns."""
    normalized_doi = doi.lower().strip()
    return any(pattern in normalized_doi for pattern in PLACEHOLDER_DOI_PATTERNS)


class BenchmarkCase(BaseModel):
    id: str
    claim: str
    doi: str
    expected_verdict: Verdict
    description: str
    expected_traceability_statuses: list[str] | None = None
    expected_min_evidence_count: int | None = None
    live_evaluable: bool | None = Field(default=None)

    @field_validator("id", "claim", "description")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Field must not be empty.")
        return value.strip()

    @field_validator("doi")
    @classmethod
    def validate_doi(cls, value: str) -> str:
        try:
            return normalize_doi(value)
        except InvalidDOIError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def set_default_live_evaluable(self) -> "BenchmarkCase":
        """Automatically determine live evaluable status based on DOI if not explicitly set."""
        if self.live_evaluable is None:
            self.live_evaluable = not is_placeholder_doi(self.doi)
        return self


class BenchmarkDataset(BaseModel):
    cases: list[BenchmarkCase] = Field(default_factory=list)


class DatasetValidationError(ValueError):
    """Raised when a benchmark dataset fails validation."""


def default_dataset_path() -> Path:
    return Path(__file__).resolve().parents[2] / "evaluation" / "dataset.json"


def default_fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "evaluation" / "fixtures"


def load_dataset(path: Path | None = None) -> BenchmarkDataset:
    dataset_path = path or default_dataset_path()
    if not dataset_path.exists():
        raise DatasetValidationError(f"Dataset not found: {dataset_path}")

    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetValidationError(f"Invalid JSON in dataset: {dataset_path}") from exc

    return validate_dataset_payload(payload)


def validate_dataset_payload(payload: Any) -> BenchmarkDataset:
    if not isinstance(payload, dict):
        raise DatasetValidationError("Dataset root must be a JSON object.")

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise DatasetValidationError("Dataset must contain a 'cases' array.")

    cases: list[BenchmarkCase] = []
    seen_ids: set[str] = set()

    for index, raw_case in enumerate(raw_cases):
        try:
            case = BenchmarkCase.model_validate(raw_case)
        except ValidationError as exc:
            raise DatasetValidationError(
                f"Invalid benchmark case at index {index}: {exc}"
            ) from exc

        if case.id in seen_ids:
            raise DatasetValidationError(f"Duplicate benchmark case id: {case.id}")
        seen_ids.add(case.id)
        cases.append(case)

    if not cases:
        raise DatasetValidationError("Dataset must contain at least one case.")

    return BenchmarkDataset(cases=cases)


def validate_live_eligibility(dataset: BenchmarkDataset) -> list[str]:
    """
    Validate dataset for live evaluation and report placeholder DOIs.
    
    Returns a list of warning messages for cases that are not live-eligible.
    """
    warnings: list[str] = []
    
    for case in dataset.cases:
        if not case.live_evaluable:
            if is_placeholder_doi(case.doi):
                warnings.append(
                    f"Case {case.id} has a placeholder/non-live DOI ({case.doi}) and will not be used for live evaluation."
                )
            else:
                warnings.append(
                    f"Case {case.id} is marked as not live-evaluable and will be skipped during live evaluation."
                )
    
    return warnings
