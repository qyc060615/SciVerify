from __future__ import annotations

from pathlib import Path
from typing import Any

from app.evaluation.evaluator import EvaluationResult
from app.evaluation.failure_analysis import FailureCategory, analyze_failures
from app.evaluation.metrics import AggregateMetrics, CaseMetrics
from app.evaluation.regression import RegressionComparison, aggregate_to_baseline_payload


def build_report_payload(
    result: EvaluationResult,
    *,
    regression: RegressionComparison | None = None,
) -> dict[str, Any]:
    aggregate = result.aggregate
    failure_summary = analyze_failures(result.cases, result.responses_by_id)

    payload = {
        "dataset_path": str(result.dataset_path) if result.dataset_path else None,
        "cases_evaluated": aggregate.case_count,
        "skipped_case_ids": result.skipped_case_ids,
        "verdict_accuracy": aggregate.verdict_accuracy,
        "per_verdict_accuracy": aggregate.per_verdict_accuracy,
        "confusion_matrix": aggregate.confusion_matrix,
        "incorrect_case_ids": aggregate.incorrect_case_ids,
        "evidence": {
            "average_count": aggregate.average_evidence_count,
            "average_relevance": aggregate.average_relevance,
            "average_claim_overlap": aggregate.average_claim_overlap,
            "average_duplicate_rate": aggregate.average_duplicate_rate,
            "average_coverage_rate": aggregate.average_evidence_coverage_rate,
        },
        "traceability": {
            "completeness": aggregate.traceability_completeness,
            "average_overall_coverage": aggregate.average_overall_coverage,
            "average_link_rate": aggregate.average_traceability_link_rate,
            "supported_segment_rate": aggregate.segment_percentage("SUPPORTED"),
            "partial_segment_rate": aggregate.segment_percentage("PARTIALLY_SUPPORTED"),
            "unsupported_segment_rate": aggregate.segment_percentage("UNSUPPORTED"),
            "contradicted_segment_rate": aggregate.segment_percentage("CONTRADICTED"),
        },
        "validation": {
            "override_rate": aggregate.validation_override_rate,
            "warning_rate": aggregate.validation_warning_rate,
        },
        "agent_agreement": {
            "agreement_rate": aggregate.agent_agreement_rate,
            "true_count": aggregate.agent_agreement_true_count,
            "false_count": aggregate.agent_agreement_false_count,
            "missing_count": aggregate.agent_agreement_missing_count,
        },
        "confidence": {
            "average": aggregate.average_confidence,
            "correct_average": aggregate.average_correct_confidence,
            "incorrect_average": aggregate.average_incorrect_confidence,
            "minimum": aggregate.minimum_confidence,
            "maximum": aggregate.maximum_confidence,
            "average_error": aggregate.average_confidence_error,
            "risk_rate": aggregate.confidence_risk_rate,
            "note": "Confidence error is a simple diagnostic, not formal calibration.",
        },
        "robustness": {
            "average_evidence_coverage_rate": aggregate.average_evidence_coverage_rate,
            "average_traceability_link_rate": aggregate.average_traceability_link_rate,
            "confidence_risk_rate": aggregate.confidence_risk_rate,
            "unsupported_claim_detection_rate": aggregate.unsupported_claim_detection_rate,
        },
        "failure_analysis": {
            "total_failures": failure_summary.total_failures,
            "category_counts": dict(failure_summary.category_counts),
            "worst_cases": failure_summary.worst_cases,
        },
        "regression": {
            "passed": regression.passed if regression else None,
            "findings": [
                {
                    "metric": finding.metric,
                    "baseline": finding.baseline,
                    "current": finding.current,
                    "tolerance": finding.tolerance,
                    "message": finding.message,
                }
                for finding in (regression.findings if regression else [])
            ],
        },
        "cases": [_case_payload(case) for case in result.cases],
    }

    # Add live evaluation diagnostics if present
    if result.live_case_results:
        payload["live_evaluation"] = _build_live_diagnostics_payload(result.live_case_results, result.live_metrics)

    return payload


def render_markdown_report(
    result: EvaluationResult,
    *,
    regression: RegressionComparison | None = None,
) -> str:
    aggregate = result.aggregate
    failure_summary = analyze_failures(result.cases, result.responses_by_id)
    lines = [
        "SciVerify Evaluation",
        "====================",
        "",
        f"Cases: {aggregate.case_count}",
        f"Verdict Accuracy: {aggregate.verdict_accuracy:.1%}",
        "",
        "Per-Verdict Accuracy:",
    ]

    for verdict, accuracy in sorted(aggregate.per_verdict_accuracy.items()):
        lines.append(f"- {verdict}: {accuracy:.1%}")

    lines.extend(
        [
            "",
            "Evidence:",
            f"- Average evidence count: {aggregate.average_evidence_count:.1f}",
            f"- Average relevance: {aggregate.average_relevance:.2f}",
            f"- Average claim overlap: {aggregate.average_claim_overlap:.2f}",
            f"- Duplicate rate: {aggregate.average_duplicate_rate:.1%}",
            f"- Evidence coverage rate: {aggregate.average_evidence_coverage_rate:.1%}",
            "",
            "Traceability:",
            f"- Completeness: {aggregate.traceability_completeness:.1%}",
            f"- Coverage: {aggregate.average_overall_coverage:.1%}",
            f"- Link rate: {aggregate.average_traceability_link_rate:.1%}",
            f"- Supported segments: {aggregate.segment_percentage('SUPPORTED'):.1%}",
            f"- Partial segments: {aggregate.segment_percentage('PARTIALLY_SUPPORTED'):.1%}",
            f"- Unsupported segments: {aggregate.segment_percentage('UNSUPPORTED'):.1%}",
            f"- Contradicted segments: {aggregate.segment_percentage('CONTRADICTED'):.1%}",
            "",
            "Validation:",
            f"- Override rate: {aggregate.validation_override_rate:.1%}",
            f"- Warning rate: {aggregate.validation_warning_rate:.1%}",
            "",
            "Agent Agreement:",
        ]
    )

    agreement_rate = aggregate.agent_agreement_rate
    lines.append(
        f"- Agreement: {agreement_rate:.1%}" if agreement_rate is not None else "- Agreement: n/a"
    )

    unsupported_rate = aggregate.unsupported_claim_detection_rate
    lines.extend(
        [
            "",
            "Confidence:",
            f"- Correct verdict avg: {_fmt(aggregate.average_correct_confidence)}",
            f"- Incorrect verdict avg: {_fmt(aggregate.average_incorrect_confidence)}",
            f"- Average confidence error: {_fmt(aggregate.average_confidence_error)}",
            f"- Confidence risk rate: {aggregate.confidence_risk_rate:.1%}",
            "",
            "Robustness:",
            f"- Unsupported-claim detection: "
            f"{unsupported_rate:.1%}" if unsupported_rate is not None else "- Unsupported-claim detection: n/a",
            "",
            "Failure analysis:",
        ]
    )

    if failure_summary.total_failures == 0:
        lines.append("- No failures detected")
    else:
        for category in FailureCategory:
            count = failure_summary.category_counts.get(category.value, 0)
            if count:
                label = category.value.replace("_", " ").title()
                lines.append(f"- {label}: {count}")

    lines.extend(["", "Worst-performing cases:"])
    if not failure_summary.worst_cases:
        lines.append("- None")
    else:
        for entry in failure_summary.worst_cases[:10]:
            categories = ", ".join(entry["failure_categories"])
            lines.append(
                f"- {entry['case_id']}: expected={entry['expected_verdict']}, "
                f"actual={entry['actual_verdict']}, confidence={_fmt(entry.get('confidence'))}, "
                f"evidence_coverage={entry['evidence_coverage']:.1%}, "
                f"traceability_coverage={_fmt_pct(entry.get('traceability_coverage'))}, "
                f"failures=[{categories}]"
            )

    lines.extend(
        [
            "",
            "Regression:",
            "PASS" if regression is None or regression.passed else "FAIL",
            "",
        ]
    )

    if regression and regression.findings:
        lines.append("Regression findings:")
        for finding in regression.findings:
            lines.append(
                f"- {finding.message}: baseline={finding.baseline:.3f}, "
                f"current={finding.current:.3f}, tolerance={finding.tolerance:.3f}"
            )
        lines.append("")

    if aggregate.incorrect_case_ids:
        lines.append("Incorrect verdict cases:")
        for case_id in aggregate.incorrect_case_ids:
            lines.append(f"- {case_id}")
        lines.append("")

    if result.skipped_case_ids:
        lines.append("Skipped cases (missing fixtures/responses):")
        for case_id in result.skipped_case_ids:
            lines.append(f"- {case_id}")
        lines.append("")

    # Add live evaluation diagnostics if present
    if result.live_case_results:
        lines.extend([
            "",
            "Live Evaluation Diagnostics:",
            "",
        ])

        # Use live_metrics if available
        if result.live_metrics and result.live_metrics.live_eligible_count > 0:
            live_metrics = result.live_metrics
            lines.append(f"Live eligible: {live_metrics.live_eligible_count}")
            lines.append(f"Successfully evaluated: {live_metrics.successfully_evaluated_count}")
            lines.append(f"Retrieval/infrastructure failures: {live_metrics.retrieval_failure_count}")
            lines.append(f"Verification failures: {live_metrics.verification_failure_count}")
            lines.append("")

            if live_metrics.failure_category_counts:
                lines.append("Failure categories:")
                for category, count in sorted(live_metrics.failure_category_counts.items()):
                    lines.append(f"- {category}: {count}")
                lines.append("")

            lines.append("Retrieval diagnostics:")
            lines.append(f"- Total retrieval attempts: {live_metrics.total_retrieval_attempts}")
            lines.append(f"- Average attempts per case: {live_metrics.average_attempts_per_case:.1f}")
            lines.append(f"- Total elapsed time: {live_metrics.total_elapsed_seconds:.1f}s")
            lines.append("")

            lines.append("Live verification metrics:")
            lines.append(f"- Retrieval success rate: {_fmt_pct(live_metrics.retrieval_success_rate)}")
            lines.append(f"- Retrieval failure rate: {_fmt_pct(live_metrics.retrieval_failure_rate)}")
            lines.append("")
        else:
            # Fallback to computed values
            failure_category_counts: dict[str, int] = {}
            total_retrieval_attempts = 0
            total_elapsed_time = 0.0
            evaluated_count = 0
            failed_count = 0
            skipped_count = 0

            for live_result in result.live_case_results:
                total_retrieval_attempts += live_result.retrieval_attempts
                total_elapsed_time += live_result.elapsed_seconds

                if live_result.status == "evaluated":
                    evaluated_count += 1
                elif live_result.status == "failed":
                    failed_count += 1
                else:
                    skipped_count += 1

                if live_result.failure_category:
                    category_name = live_result.failure_category.value
                    failure_category_counts[category_name] = failure_category_counts.get(category_name, 0) + 1

            lines.append(f"Total cases: {len(result.live_case_results)}")
            lines.append(f"Evaluated: {evaluated_count}")
            lines.append(f"Failed: {failed_count}")
            lines.append(f"Skipped: {skipped_count}")
            lines.append("")

            if failure_category_counts:
                lines.append("Failure categories:")
                for category, count in sorted(failure_category_counts.items()):
                    lines.append(f"- {category}: {count}")
                lines.append("")

            avg_attempts = total_retrieval_attempts / len(result.live_case_results) if result.live_case_results else 0
            lines.append("Retrieval diagnostics:")
            lines.append(f"- Total retrieval attempts: {total_retrieval_attempts}")
            lines.append(f"- Average attempts per case: {avg_attempts:.1f}")
            lines.append(f"- Total elapsed time: {total_elapsed_time:.1f}s")
            lines.append("")

        lines.append("Live Case Results:")
        for r in result.live_case_results:
            if r.status == "evaluated":
                verdict_str = r.actual_verdict.value if r.actual_verdict else "n/a"
                lines.append(
                    f"- {r.case_id}: evaluated | verdict={verdict_str} "
                    f"| confidence={_fmt(r.confidence)} | attempts={r.retrieval_attempts} | time={r.elapsed_seconds:.1f}s"
                )
            elif r.status == "skipped":
                cat = r.failure_category.value if r.failure_category else "unknown"
                lines.append(
                    f"- {r.case_id}: skipped ({cat}) | reason={r.failure_reason or 'n/a'} | attempts={r.retrieval_attempts}"
                )
            else:
                cat = r.failure_category.value if r.failure_category else "unknown"
                lines.append(
                    f"- {r.case_id}: failed ({cat}) | reason={r.failure_reason or 'n/a'} | attempts={r.retrieval_attempts}"
                )
        lines.append("")

    lines.append("Confusion matrix:")
    for expected, actuals in aggregate.confusion_matrix.items():
        for actual, count in actuals.items():
            lines.append(f"- {expected} -> {actual}: {count}")

    return "\n".join(lines)


def write_reports(
    result: EvaluationResult,
    *,
    output_dir: Path,
    regression: RegressionComparison | None = None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_report_payload(result, regression=regression)
    json_path = output_dir / "latest.json"
    md_path = output_dir / "latest.md"
    json_path.write_text(
        __import__("json").dumps(payload, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown_report(result, regression=regression), encoding="utf-8")
    return json_path, md_path


def _case_payload(case: CaseMetrics) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "expected_verdict": case.expected_verdict.value,
        "actual_verdict": case.actual_verdict.value if case.actual_verdict else None,
        "verdict_correct": case.verdict_correct,
        "evidence_count": case.evidence_count,
        "duplicate_rate": case.duplicate_rate,
        "average_relevance": case.average_relevance,
        "average_claim_overlap": case.average_claim_overlap,
        "evidence_coverage_rate": case.evidence_coverage_rate,
        "traceability_link_rate": case.traceability_link_rate,
        "overall_coverage": case.overall_coverage,
        "confidence_risk": case.confidence_risk,
        "unsupported_claim_detected": case.unsupported_claim_detected,
        "validation_warning_count": case.validation_warning_count,
        "verdict_changed": case.verdict_changed,
        "agent_agreement": case.agent_agreement,
        "confidence": case.confidence,
        "confidence_error": case.confidence_error,
    }


def _fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def _fmt_pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


def _build_live_diagnostics_payload(live_results: list, live_metrics) -> dict[str, Any]:
    """Build the live evaluation diagnostics section of the report payload."""
    from app.evaluation.evaluator import LiveCaseResult

    failure_category_counts: dict[str, int] = {}
    total_retrieval_attempts = 0
    total_elapsed_time = 0.0
    evaluated_count = 0
    failed_count = 0
    skipped_count = 0

    for result in live_results:
        total_retrieval_attempts += result.retrieval_attempts
        total_elapsed_time += result.elapsed_seconds

        if result.status == "evaluated":
            evaluated_count += 1
        elif result.status == "failed":
            failed_count += 1
        else:
            skipped_count += 1

        if result.failure_category:
            category_name = result.failure_category.value
            failure_category_counts[category_name] = failure_category_counts.get(category_name, 0) + 1

    avg_attempts = total_retrieval_attempts / len(live_results) if live_results else 0

    # Use live_metrics if available, otherwise fall back to computed values
    if live_metrics and live_metrics.live_eligible_count > 0:
        live_eligible_count = live_metrics.live_eligible_count
        successfully_evaluated_count = live_metrics.successfully_evaluated_count
        retrieval_failure_count = live_metrics.retrieval_failure_count
        verification_failure_count = live_metrics.verification_failure_count
        retrieval_success_rate = live_metrics.retrieval_success_rate
        retrieval_failure_rate = live_metrics.retrieval_failure_rate
        total_retrieval_attempts = live_metrics.total_retrieval_attempts
        total_elapsed_time = live_metrics.total_elapsed_seconds
        avg_attempts = live_metrics.average_attempts_per_case
        failure_category_counts = dict(live_metrics.failure_category_counts)
    else:
        live_eligible_count = len(live_results)
        successfully_evaluated_count = evaluated_count
        retrieval_failure_count = 0
        verification_failure_count = 0
        retrieval_success_rate = 0.0
        retrieval_failure_rate = 0.0

    return {
        "live_eligible_count": live_eligible_count,
        "successfully_evaluated_count": successfully_evaluated_count,
        "retrieval_failure_count": retrieval_failure_count,
        "verification_failure_count": verification_failure_count,
        "total_cases": len(live_results),
        "evaluated_count": evaluated_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "failure_category_counts": failure_category_counts,
        "retrieval_success_rate": retrieval_success_rate,
        "retrieval_failure_rate": retrieval_failure_rate,
        "retrieval_diagnostics": {
            "total_retrieval_attempts": total_retrieval_attempts,
            "average_attempts_per_case": avg_attempts,
            "total_elapsed_time": total_elapsed_time,
        },
        "case_results": [
            {
                "case_id": r.case_id,
                "status": r.status,
                "expected_verdict": r.expected_verdict.value,
                "actual_verdict": r.actual_verdict.value if r.actual_verdict else None,
                "confidence": r.confidence,
                "failure_category": r.failure_category.value if r.failure_category else None,
                "failure_reason": r.failure_reason,
                "retrieval_attempts": r.retrieval_attempts,
                "elapsed_seconds": r.elapsed_seconds,
                "candidate_urls": r.candidate_urls,
                "retrieval_elapsed_ms": r.retrieval_elapsed_ms,
            }
            for r in live_results
        ],
    }
