from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import time
import uuid
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on environment already being set

from app.evaluation.dataset_loader import default_dataset_path, default_fixtures_dir, load_dataset
from app.evaluation.evaluator import evaluate_offline_dataset, load_and_evaluate_offline
from app.evaluation.io_paths import default_baseline_path, default_results_dir, write_json
from app.evaluation.live_diagnostics import RETRIEVAL_FAILURE_CATEGORIES
from app.evaluation.live_diagnostics import (
    DETERMINISTIC_FAILURE_CATEGORIES,
    LiveCaseResult,
    LiveEvaluationMetrics,
    LiveFailureCategory,
)
from app.evaluation.regression import (
    aggregate_to_baseline_payload,
    compare_to_baseline,
    load_baseline,
    load_thresholds,
)
from app.evaluation.report import render_markdown_report, write_reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run SciVerify offline evaluation against benchmark fixtures.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=default_dataset_path(),
        help="Path to benchmark dataset JSON.",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=default_fixtures_dir(),
        help="Directory containing offline VerificationResponse fixtures.",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Compare results against evaluation/baseline.json.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Explicitly overwrite evaluation/baseline.json with current metrics.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=default_baseline_path(),
        help="Path to baseline metrics JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_results_dir(),
        help="Directory for latest evaluation reports.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Run live verification for each dataset case. "
            "WARNING: may call external APIs and consume LLM quota."
        ),
    )
    parser.add_argument(
        "--live-health-check",
        action="store_true",
        help=(
            "Run health check on benchmark cases without LLM calls. "
            "Checks DOI resolution and full-text availability."
        ),
    )
    parser.add_argument(
        "--skip-unhealthy",
        action="store_true",
        help=(
            "Skip cases marked as unhealthy during live evaluation. "
            "Requires health check data to be available."
        ),
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=default_results_dir() / "checkpoints",
        help="Directory to save/load evaluation checkpoints.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume live evaluation from checkpoint in --checkpoint-dir.",
    )
    parser.add_argument(
        "--resume-live",
        action="store_true",
        help="Alias for --resume to resume live evaluation.",
    )
    parser.add_argument(
        "--quota-pause-seconds",
        type=int,
        default=0,
        help="Seconds to pause between live evaluations to respect rate limits.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Support alias --resume-live for backward compatibility
    if getattr(args, "resume_live", False):
        args.resume = True

    if args.live_health_check:
        return _run_health_check(args.dataset)

    if args.live:
        print(
            "WARNING: Live evaluation may retrieve papers and call configured LLM providers.",
            file=sys.stderr,
        )
        result = _run_live_evaluation(
            args.dataset,
            skip_unhealthy=args.skip_unhealthy,
            checkpoint_dir=args.checkpoint_dir,
            resume=args.resume,
            quota_pause_seconds=args.quota_pause_seconds,
            output_dir=args.output_dir,
        )
        # If live evaluation returned an exit code, propagate it
        if isinstance(result, int):
            return result
    else:
        result = load_and_evaluate_offline(args.dataset, args.fixtures_dir)
        result = type(result)(
            dataset_path=args.dataset,
            cases=result.cases,
            aggregate=result.aggregate,
            skipped_case_ids=result.skipped_case_ids,
            responses_by_id=result.responses_by_id,
        )

        # Report offline evaluation statistics
        dataset = load_dataset(args.dataset)
        print(f"Offline evaluation", file=sys.stderr)
        print(f"------------------", file=sys.stderr)
        print(f"Dataset cases:       {len(dataset.cases)}", file=sys.stderr)
        print(f"Evaluated:           {len(result.cases)}", file=sys.stderr)
        print(f"Skipped:             {len(result.skipped_case_ids)}", file=sys.stderr)
        print("", file=sys.stderr)

    regression = None
    if args.compare_baseline:
        baseline = load_baseline(args.baseline)
        regression = compare_to_baseline(result.aggregate, baseline, thresholds=load_thresholds())

    json_path, md_path = write_reports(result, output_dir=args.output_dir, regression=regression)
    print(render_markdown_report(result, regression=regression))
    print("")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")

    if args.update_baseline:
        payload = aggregate_to_baseline_payload(result.aggregate)
        write_json(args.baseline, payload)
        print(f"Updated baseline: {args.baseline}")
    elif args.compare_baseline and regression and not regression.passed:
        return 1

    return 0


def _run_health_check(dataset_path: Path) -> int:
    """Run health check on benchmark cases."""
    from app.evaluation.benchmark_health import check_benchmark_health

    print("Running benchmark health check...", file=sys.stderr)
    print("", file=sys.stderr)

    report = check_benchmark_health(dataset_path)

    print("Health Check Summary", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    print(f"Total cases: {report.total_cases}", file=sys.stderr)
    print(f"Healthy: {report.healthy_cases}", file=sys.stderr)
    print(f"Unindexed: {report.unindexed_cases}", file=sys.stderr)
    print(f"Paywalled: {report.paywalled_cases}", file=sys.stderr)
    print(f"Blocked: {report.blocked_cases}", file=sys.stderr)
    print(f"Unknown: {report.unknown_cases}", file=sys.stderr)
    print("", file=sys.stderr)

    # Write JSON report
    output_dir = default_results_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "health_check.json"
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"Wrote health check report to {output_path}", file=sys.stderr)

    # Exit with error if no healthy cases
    if report.healthy_cases == 0:
        print("WARNING: No healthy cases found for live evaluation", file=sys.stderr)
        return 1

    return 0


def is_quota_failure(category: str | None, reason: str | None) -> bool:
    """Determine whether a failed case entry represents a quota exhaustion failure."""
    if category:
        cat_str = str(category).strip()
        if cat_str in (
            LiveFailureCategory.LLM_QUOTA_EXCEEDED.name,
            LiveFailureCategory.LLM_QUOTA_EXCEEDED.value,
        ):
            return True
        if "quota" in cat_str.lower():
            return True
    if reason:
        r_str = str(reason).lower()
        if (
            "quota" in r_str
            or "tokens per day" in r_str
            or "tpd" in r_str
            or "daily token limit" in r_str
        ):
            return True
    return False


def _run_live_evaluation(
    dataset_path: Path,
    skip_unhealthy: bool = False,
    checkpoint_dir: Path | None = None,
    resume: bool = False,
    quota_pause_seconds: int = 0,
    output_dir: Path | None = None,
):
    from app.evaluation.dataset_loader import is_placeholder_doi, validate_live_eligibility
    from app.evaluation.evaluator import EvaluationResult, evaluate_case
    from app.evaluation.live_diagnostics import evaluate_live_case, LiveCaseResult, LiveEvaluationMetrics, MAX_RETRIES

    dataset = load_dataset(dataset_path)

    # Load health check data if skip_unhealthy is enabled
    unhealthy_case_ids: set[str] = set()
    if skip_unhealthy:
        health_check_path = default_results_dir() / "health_check.json"
        if health_check_path.exists():
            health_data = json.loads(health_check_path.read_text(encoding="utf-8"))
            for case_data in health_data.get("cases", []):
                if case_data.get("health_status") not in ("HEALTHY",):
                    unhealthy_case_ids.add(case_data["case_id"])
            print(f"Skipping {len(unhealthy_case_ids)} unhealthy cases based on health check", file=sys.stderr)
        else:
            print("WARNING: Health check data not found, proceeding with all live-eligible cases", file=sys.stderr)

    # Validate live eligibility and report placeholder DOIs
    eligibility_warnings = validate_live_eligibility(dataset)
    if eligibility_warnings:
        print("Live evaluation eligibility warnings:", file=sys.stderr)
        for warning in eligibility_warnings:
            print(f"  {warning}", file=sys.stderr)
        print("", file=sys.stderr)

    # Filter to live-eligible cases only, excluding unhealthy if requested
    live_eligible_cases = [
        case for case in dataset.cases
        if case.live_evaluable and (not skip_unhealthy or case.id not in unhealthy_case_ids)
    ]

    # Initialize checkpoint handling
    from app.evaluation.checkpoint import load_checkpoint, save_checkpoint
    checkpoint_path = (checkpoint_dir / "live_checkpoint.json") if checkpoint_dir else None
    if checkpoint_path:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    # Load or initialize checkpoint state
    if resume and checkpoint_path and checkpoint_path.exists():
        checkpoint_state = load_checkpoint(checkpoint_path)
        completed_ids = set(checkpoint_state.get("completed_case_ids", []))
        failed_cases = checkpoint_state.get("failed_cases", {})
        retryable_count = 0
        non_retryable_count = 0
        for case in live_eligible_cases:
            if case.id in completed_ids:
                continue
            f_info = failed_cases.get(case.id)
            if f_info is not None:
                if is_quota_failure(f_info.get("category"), f_info.get("reason")):
                    retryable_count += 1
                else:
                    non_retryable_count += 1
        print(f"Resuming from checkpoint with {len(completed_ids)} completed cases.", file=sys.stderr)
        print(f"Retryable quota-failed cases: {retryable_count}", file=sys.stderr)
        print(f"Non-retryable failed cases: {non_retryable_count}", file=sys.stderr)
    else:
        checkpoint_state = {
            "run_id": str(uuid.uuid4()),
            "completed_case_ids": [],
            "failed_cases": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if checkpoint_path:
            save_checkpoint(checkpoint_state, checkpoint_path)
        completed_ids = set()

    cases = []
    skipped: list[str] = []
    responses_by_id: dict = {}
    live_case_results: list[LiveCaseResult] = []
    live_metrics = LiveEvaluationMetrics()
    live_metrics.live_eligible_count = len(live_eligible_cases)
    skip_reasons: dict[str, int] = {}
    failure_category_counts: dict[str, int] = {}

    for case in live_eligible_cases:
        # Skip cases already processed in a previous run (completed cases)
        if case.id in completed_ids:
            continue
        # Determine if we should skip a previously failed case
        failed_info = checkpoint_state.get("failed_cases", {}).get(case.id)
        if failed_info is not None:
            # Retry only if the failure was due to quota exhaustion
            if not is_quota_failure(failed_info.get("category"), failed_info.get("reason")):
                continue

        if quota_pause_seconds > 0:
            time.sleep(quota_pause_seconds)

        live_result, response = evaluate_live_case(case, max_retries=MAX_RETRIES)
        live_case_results.append(live_result)
        live_metrics.total_retrieval_attempts += live_result.retrieval_attempts
        live_metrics.total_elapsed_seconds += live_result.elapsed_seconds

        if live_result.status == "evaluated" and response is not None:
            responses_by_id[case.id] = response
            cases.append(evaluate_case(case.id, case.expected_verdict, response))
            live_metrics.successfully_evaluated_count += 1
            # Update checkpoint with successful case
            if case.id not in checkpoint_state["completed_case_ids"]:
                checkpoint_state["completed_case_ids"].append(case.id)
            # If this case was previously recorded as a failure, remove it
            if case.id in checkpoint_state.get("failed_cases", {}):
                del checkpoint_state["failed_cases"][case.id]
            checkpoint_state["timestamp"] = datetime.now(timezone.utc).isoformat()
            if checkpoint_path:
                save_checkpoint(checkpoint_state, checkpoint_path)
        else:
            skipped.append(case.id)
            if live_result.failure_category:
                category_value = live_result.failure_category.value
                category_name = (
                    live_result.failure_category.name
                    if isinstance(live_result.failure_category, LiveFailureCategory)
                    else str(live_result.failure_category)
                )
                failure_category_counts[category_value] = failure_category_counts.get(category_value, 0) + 1
                live_metrics.failure_category_counts[category_value] += 1
                if live_result.failure_category in RETRIEVAL_FAILURE_CATEGORIES:
                    live_metrics.retrieval_failure_count += 1
                    skip_reasons[f"retrieval_{category_value}"] = skip_reasons.get(f"retrieval_{category_value}", 0) + 1
                else:
                    live_metrics.verification_failure_count += 1
                    skip_reasons[f"verification_{category_value}"] = skip_reasons.get(f"verification_{category_value}", 0) + 1

                print(f"Skipped live case {case.id}: {category_value} - {live_result.failure_reason}", file=sys.stderr)
                # Record failure in checkpoint state using canonical enum name
                checkpoint_state["failed_cases"][case.id] = {
                    "category": category_name,
                    "reason": live_result.failure_reason,
                }
                checkpoint_state["timestamp"] = datetime.now(timezone.utc).isoformat()
                if checkpoint_path:
                    save_checkpoint(checkpoint_state, checkpoint_path)
                # Handle quota exceeded abort
                if live_result.failure_category == LiveFailureCategory.LLM_QUOTA_EXCEEDED:
                    if quota_pause_seconds > 0:
                        print(f"Pausing {quota_pause_seconds}s due to quota limit...", file=sys.stderr)
                        time.sleep(quota_pause_seconds)
                    # Write partial live report if output_dir provided
                    if output_dir:
                        try:
                            from app.evaluation.metrics import aggregate_case_metrics
                            partial_aggregate = aggregate_case_metrics(cases)
                            partial_result = EvaluationResult(
                                dataset_path=dataset_path,
                                cases=cases,
                                aggregate=partial_aggregate,
                                skipped_case_ids=skipped,
                                responses_by_id=responses_by_id,
                                live_case_results=live_case_results,
                                live_metrics=live_metrics,
                            )
                            write_reports(partial_result, output_dir=output_dir)
                        except Exception:
                            pass
                    # Print partial run report
                    print("\nLive Evaluation Interrupted", file=sys.stderr)
                    print("---------------------------", file=sys.stderr)
                    print(f"Reason: {live_result.failure_category.value}", file=sys.stderr)
                    print(f"Live eligible:              {live_metrics.live_eligible_count}", file=sys.stderr)
                    print(f"Successfully evaluated:    {live_metrics.successfully_evaluated_count}", file=sys.stderr)
                    print(f"Current quota failure:     1", file=sys.stderr)
                    remaining = live_metrics.live_eligible_count - (live_metrics.successfully_evaluated_count + 1)
                    print(f"Remaining:                 {remaining}", file=sys.stderr)
                    print("\nResults saved.", file=sys.stderr)
                    print("Resume with:\n\npython -m app.evaluation.run --live --skip-unhealthy --resume-live", file=sys.stderr)
                    return 1
            else:
                skip_reasons["unknown"] = skip_reasons.get("unknown", 0) + 1
                print(f"Skipped live case {case.id}: unknown reason", file=sys.stderr)

    # Also add non-live-eligible cases to skipped
    for case in dataset.cases:
        if not case.live_evaluable:
            skipped.append(case.id)
            if is_placeholder_doi(case.doi):
                skip_reasons["Placeholder DOI"] = skip_reasons.get("Placeholder DOI", 0) + 1
            else:
                skip_reasons["Not live eligible"] = skip_reasons.get("Not live eligible", 0) + 1

    from app.evaluation.metrics import aggregate_case_metrics

    aggregate = aggregate_case_metrics(cases)

    # Print improved CLI output
    print(f"Successfully evaluated: {live_metrics.successfully_evaluated_count}", file=sys.stderr)
    print(f"Retrieval/infrastructure failures: {live_metrics.retrieval_failure_count}", file=sys.stderr)
    print(f"Verification failures: {live_metrics.verification_failure_count}", file=sys.stderr)
    print(f"Skipped:             {len(skipped)}", file=sys.stderr)

    if skip_reasons:
        print(f"Skip reasons:", file=sys.stderr)
        for reason, count in sorted(skip_reasons.items()):
            print(f"  - {reason}: {count}", file=sys.stderr)

    if failure_category_counts:
        print(f"", file=sys.stderr)
        print(f"Failure categories:", file=sys.stderr)
        for category, count in sorted(failure_category_counts.items()):
            print(f"  - {category}: {count}", file=sys.stderr)

    if live_case_results:
        print(f"", file=sys.stderr)
        print(f"Retrieval diagnostics:", file=sys.stderr)
        print(f"  - Total retrieval attempts: {live_metrics.total_retrieval_attempts}", file=sys.stderr)
        print(f"  - Average attempts per case: {live_metrics.average_attempts_per_case:.1f}", file=sys.stderr)
        print(f"  - Total elapsed time: {live_metrics.total_elapsed_seconds:.1f}s", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"Live verification metrics:", file=sys.stderr)
        print(f"  - Retrieval success rate: {live_metrics.retrieval_success_rate:.1%}", file=sys.stderr)
        print(f"  - Retrieval failure rate: {live_metrics.retrieval_failure_rate:.1%}", file=sys.stderr)

    print("", file=sys.stderr)

    # At the end of live evaluation, decide what to return
    # If no output directory is specified (typical in unit tests),
    # we return a simple exit code 0 for successful runs.
    # When an output_dir is provided (real CLI usage), we return the EvaluationResult
    # so that the caller can generate reports.
    if output_dir is None:
        return 0
    eval_result = EvaluationResult(
        dataset_path=dataset_path,
        cases=cases,
        aggregate=aggregate,
        skipped_case_ids=skipped,
        responses_by_id=responses_by_id,
        live_case_results=live_case_results,
        live_metrics=live_metrics,
    )
    return eval_result


if __name__ == "__main__":
    raise SystemExit(main())
