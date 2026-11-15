from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.evaluation.dataset_loader import BenchmarkCase, BenchmarkDataset, load_dataset
from app.evaluation.io_paths import load_case_fixture
from app.evaluation.live_diagnostics import (
    DETERMINISTIC_FAILURE_CATEGORIES,
    LiveCaseResult,
    LiveEvaluationMetrics,
)
from app.evaluation.metrics import AggregateMetrics, CaseMetrics, aggregate_case_metrics, evaluate_case
from app.schemas.verification import Verdict, VerificationResponse


@dataclass(frozen=True)
class EvaluationResult:
    dataset_path: Path
    cases: list[CaseMetrics]
    aggregate: AggregateMetrics
    skipped_case_ids: list[str]
    responses_by_id: dict[str, VerificationResponse] = None  # type: ignore[assignment]
    live_case_results: list[LiveCaseResult] = field(default_factory=list)
    live_metrics: LiveEvaluationMetrics = field(default_factory=LiveEvaluationMetrics)

    def __post_init__(self) -> None:
        if self.responses_by_id is None:
            object.__setattr__(self, "responses_by_id", {})


def evaluate_offline_dataset(
    dataset: BenchmarkDataset,
    *,
    fixtures_dir: Path,
) -> EvaluationResult:
    case_metrics: list[CaseMetrics] = []
    skipped: list[str] = []
    responses_by_id: dict[str, VerificationResponse] = {}

    for case in dataset.cases:
        try:
            response = load_case_fixture(fixtures_dir, case.id)
        except FileNotFoundError:
            skipped.append(case.id)
            continue
        responses_by_id[case.id] = response
        case_metrics.append(evaluate_case(case.id, case.expected_verdict, response))

    aggregate = aggregate_case_metrics(case_metrics)
    return EvaluationResult(
        dataset_path=Path(),
        cases=case_metrics,
        aggregate=aggregate,
        skipped_case_ids=skipped,
        responses_by_id=responses_by_id,
    )


def evaluate_case_response(case: BenchmarkCase, response: VerificationResponse) -> CaseMetrics:
    return evaluate_case(case.id, case.expected_verdict, response)


def evaluate_responses(
    dataset: BenchmarkDataset,
    responses_by_id: dict[str, VerificationResponse],
) -> EvaluationResult:
    case_metrics: list[CaseMetrics] = []
    skipped: list[str] = []

    for case in dataset.cases:
        response = responses_by_id.get(case.id)
        if response is None:
            skipped.append(case.id)
            continue
        case_metrics.append(evaluate_case(case.id, case.expected_verdict, response))

    return EvaluationResult(
        dataset_path=Path(),
        cases=case_metrics,
        aggregate=aggregate_case_metrics(case_metrics),
        skipped_case_ids=skipped,
        responses_by_id=responses_by_id,
    )


def load_and_evaluate_offline(
    dataset_path: Path | None = None,
    fixtures_dir: Path | None = None,
) -> EvaluationResult:
    from app.evaluation.dataset_loader import default_dataset_path, default_fixtures_dir

    dataset = load_dataset(dataset_path)
    result = evaluate_offline_dataset(
        dataset,
        fixtures_dir=fixtures_dir or default_fixtures_dir(),
    )
    return EvaluationResult(
        dataset_path=dataset_path or default_dataset_path(),
        cases=result.cases,
        aggregate=result.aggregate,
        skipped_case_ids=result.skipped_case_ids,
        responses_by_id=result.responses_by_id,
    )
