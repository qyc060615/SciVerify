import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.checkpoint import load_checkpoint, save_checkpoint
from app.evaluation.dataset_loader import BenchmarkCase
from app.evaluation.run import _run_live_evaluation, is_quota_failure, main
from app.schemas.verification import LiveFailureCategory, Verdict


# Helper to create a dummy BenchmarkCase
def make_case(case_id: str) -> BenchmarkCase:
    return BenchmarkCase(
        id=case_id,
        claim="Test claim",
        doi=f"10.1000/dummy.{case_id}",
        expected_verdict=Verdict.SUPPORTS,
        description="Generated for quota test",
        live_evaluable=True,
    )


# Mock LiveCaseResult similar to what evaluate_live_case returns
class DummyLiveResult:
    def __init__(self, case_id, status, failure_category=None, failure_reason=None):
        self.case_id = case_id
        self.status = status  # "evaluated", "failed", or "skipped"
        self.expected_verdict = Verdict.SUPPORTS
        self.actual_verdict = Verdict.SUPPORTS if status == "evaluated" else None
        self.confidence = 0.9 if status == "evaluated" else None
        self.failure_category = failure_category
        self.failure_reason = failure_reason
        self.retrieval_attempts = 1
        self.elapsed_seconds = 0.1


# ---------------------------------------------------------------------------
# Test 1 — Canonical quota checkpoint
# ---------------------------------------------------------------------------
def test_canonical_quota_checkpoint(tmp_path: Path):
    cases = [make_case("case_1")]
    side_effects = [
        (
            DummyLiveResult(
                cases[0].id,
                "failed",
                failure_category=LiveFailureCategory.LLM_QUOTA_EXCEEDED,
                failure_reason="LLM quota exhausted (daily token limit reached).",
            ),
            None,
        ),
    ]

    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()

    dummy_dataset = type("DummyDataset", (), {"cases": cases})
    with patch("app.evaluation.run.load_dataset", return_value=dummy_dataset), \
         patch("app.evaluation.live_diagnostics.evaluate_live_case", side_effect=side_effects):
        exit_code = _run_live_evaluation(
            dataset_path=Path("/dev/null"),
            skip_unhealthy=False,
            checkpoint_dir=checkpoint_dir,
            resume=False,
            quota_pause_seconds=0,
        )

    assert exit_code == 1
    checkpoint_path = checkpoint_dir / "live_checkpoint.json"
    assert checkpoint_path.exists()
    data = load_checkpoint(checkpoint_path)
    assert data["failed_cases"]["case_1"]["category"] == "LLM_QUOTA_EXCEEDED"
    assert "LLM quota exhausted" in data["failed_cases"]["case_1"]["reason"]


# ---------------------------------------------------------------------------
# Test 2 — Legacy checkpoint compatibility (retryable)
# ---------------------------------------------------------------------------
def test_legacy_checkpoint_compatibility():
    assert is_quota_failure("llm_failure", "LLM quota exhausted (daily token limit reached).") is True
    assert is_quota_failure("llm_failure", "tokens per day (TPD) limit reached") is True
    assert is_quota_failure("LLM_QUOTA_EXCEEDED", "quota error") is True
    assert is_quota_failure("llm_quota_exceeded", "quota error") is True


# ---------------------------------------------------------------------------
# Test 3 — Non-quota LLM failure (not retryable)
# ---------------------------------------------------------------------------
def test_non_quota_llm_failure_not_retryable():
    assert is_quota_failure("llm_failure", "Some unrelated provider failure") is False
    assert is_quota_failure("DOI_NOT_FOUND", "Paper not found") is False
    assert is_quota_failure("FULL_TEXT_UNAVAILABLE", "PDF missing") is False


# ---------------------------------------------------------------------------
# Test 4 — Successful quota retry clears failure and adds to completed
# ---------------------------------------------------------------------------
def test_successful_quota_retry_clears_failure(tmp_path: Path):
    cases = [make_case("case_1"), make_case("case_2")]
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()

    # Prepopulate checkpoint with case_1 as a legacy quota failure
    initial_checkpoint = {
        "run_id": "test-run-123",
        "completed_case_ids": [],
        "failed_cases": {
            "case_1": {
                "category": "llm_failure",
                "reason": "LLM quota exhausted (daily token limit reached).",
            },
        },
        "timestamp": "2026-08-15T00:00:00+00:00",
    }
    save_checkpoint(initial_checkpoint, checkpoint_dir / "live_checkpoint.json")

    # On resume, case_1 should be retried and succeed, and case_2 should succeed
    side_effects = [
        (DummyLiveResult("case_1", "evaluated"), MagicMock()),
        (DummyLiveResult("case_2", "evaluated"), MagicMock()),
    ]

    dummy_dataset = type("DummyDataset", (), {"cases": cases})
    with patch("app.evaluation.run.load_dataset", return_value=dummy_dataset), \
         patch("app.evaluation.live_diagnostics.evaluate_live_case", side_effect=side_effects) as mock_eval:
        exit_code = _run_live_evaluation(
            dataset_path=Path("/dev/null"),
            skip_unhealthy=False,
            checkpoint_dir=checkpoint_dir,
            resume=True,
            quota_pause_seconds=0,
        )

    assert exit_code == 0 or hasattr(exit_code, "aggregate")
    assert mock_eval.call_count == 2
    final_data = load_checkpoint(checkpoint_dir / "live_checkpoint.json")
    assert "case_1" in final_data["completed_case_ids"]
    assert "case_2" in final_data["completed_case_ids"]
    assert "case_1" not in final_data["failed_cases"]


# ---------------------------------------------------------------------------
# Test 5 — Repeated quota failure updates category and aborts cleanly
# ---------------------------------------------------------------------------
def test_repeated_quota_failure_updates_category_and_aborts(tmp_path: Path):
    cases = [make_case("case_1")]
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()

    # Prepopulate checkpoint with case_1 as legacy quota failure
    initial_checkpoint = {
        "run_id": "test-run-123",
        "completed_case_ids": [],
        "failed_cases": {
            "case_1": {
                "category": "llm_failure",
                "reason": "LLM quota exhausted (daily token limit reached).",
            },
        },
        "timestamp": "2026-08-15T00:00:00+00:00",
    }
    save_checkpoint(initial_checkpoint, checkpoint_dir / "live_checkpoint.json")

    # On retry, case_1 encounters quota exhaustion again
    side_effects = [
        (
            DummyLiveResult(
                "case_1",
                "failed",
                failure_category=LiveFailureCategory.LLM_QUOTA_EXCEEDED,
                failure_reason="LLM quota exhausted (daily token limit reached).",
            ),
            None,
        ),
    ]

    dummy_dataset = type("DummyDataset", (), {"cases": cases})
    with patch("app.evaluation.run.load_dataset", return_value=dummy_dataset), \
         patch("app.evaluation.live_diagnostics.evaluate_live_case", side_effect=side_effects):
        exit_code = _run_live_evaluation(
            dataset_path=Path("/dev/null"),
            skip_unhealthy=False,
            checkpoint_dir=checkpoint_dir,
            resume=True,
            quota_pause_seconds=0,
        )

    assert exit_code == 1
    final_data = load_checkpoint(checkpoint_dir / "live_checkpoint.json")
    assert "case_1" not in final_data["completed_case_ids"]
    assert final_data["failed_cases"]["case_1"]["category"] == "LLM_QUOTA_EXCEEDED"


# ---------------------------------------------------------------------------
# Test 6 — Existing Phase 17 checkpoint structure detects 15 retryable cases
# ---------------------------------------------------------------------------
def test_phase17_checkpoint_detection():
    phase17_failed_cases = {
        f"case_{i}": {
            "category": "llm_failure",
            "reason": "LLM quota exhausted (daily token limit reached).",
        }
        for i in range(15)
    }
    for case_id, info in phase17_failed_cases.items():
        assert is_quota_failure(info["category"], info["reason"]) is True


# ---------------------------------------------------------------------------
# Test 7 — Completed cases skipped and non-quota failures skipped
# ---------------------------------------------------------------------------
def test_completed_and_non_quota_failures_skipped(tmp_path: Path):
    cases = [make_case("case_1"), make_case("case_2"), make_case("case_3")]
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()

    initial_checkpoint = {
        "run_id": "test-run-123",
        "completed_case_ids": ["case_1"],
        "failed_cases": {
            "case_2": {
                "category": "DOI_NOT_FOUND",
                "reason": "DOI could not be resolved",
            },
        },
        "timestamp": "2026-08-15T00:00:00+00:00",
    }
    save_checkpoint(initial_checkpoint, checkpoint_dir / "live_checkpoint.json")

    # Only case_3 should be evaluated
    side_effects = [
        (DummyLiveResult("case_3", "evaluated"), MagicMock()),
    ]

    dummy_dataset = type("DummyDataset", (), {"cases": cases})
    with patch("app.evaluation.run.load_dataset", return_value=dummy_dataset), \
         patch("app.evaluation.live_diagnostics.evaluate_live_case", side_effect=side_effects) as mock_eval:
        exit_code = _run_live_evaluation(
            dataset_path=Path("/dev/null"),
            skip_unhealthy=False,
            checkpoint_dir=checkpoint_dir,
            resume=True,
            quota_pause_seconds=0,
        )

    assert exit_code == 0
    assert mock_eval.call_count == 1
    final_data = load_checkpoint(checkpoint_dir / "live_checkpoint.json")
    assert set(final_data["completed_case_ids"]) == {"case_1", "case_3"}
    assert "case_2" in final_data["failed_cases"]


# ---------------------------------------------------------------------------
# Test 8 — --resume-live alias CLI compatibility
# ---------------------------------------------------------------------------
def test_resume_live_cli_alias():
    with patch("app.evaluation.run._run_live_evaluation", return_value=0) as mock_live:
        exit_code = main(["--live", "--resume-live"])
        assert exit_code == 0
        _, kwargs = mock_live.call_args
        assert kwargs["resume"] is True
