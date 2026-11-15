"""
Phase 19 deterministic tests: retrieval URL capture in evaluate_live_case.

Tests:
- candidate_urls is empty when DOI resolution fails before HTTP retrieval.
- The retrieve_document monkey-patch is always cleaned up (success & exception).
- LiveCaseResult stores candidate_urls as a frozen list and defaults to [].
- _build_live_diagnostics_payload includes candidate_urls in each case_result entry.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.dataset_loader import BenchmarkCase
from app.evaluation.live_diagnostics import (
    evaluate_live_case,
    LiveCaseResult,
    MAX_RETRIES,
)
from app.schemas.verification import LiveFailureCategory, Verdict, VerificationStatus
from app.services.paper_retriever import PaperNotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_case(
    case_id: str = "case-url-test",
    doi: str = "10.1234/test.2024.001",
) -> BenchmarkCase:
    return BenchmarkCase(
        id=case_id,
        claim="The treatment improved outcomes.",
        doi=doi,
        expected_verdict=Verdict.SUPPORTS,
        description="URL-capture test case",
        live_evaluable=True,
    )


def _success_response() -> MagicMock:
    resp = MagicMock()
    resp.status = VerificationStatus.SUCCESS
    resp.verdict = Verdict.SUPPORTS
    resp.confidence = 0.85
    resp.evidence = []
    resp.paper = MagicMock()
    resp.paper.paper_id = "10.1234/test.2024.001"
    resp.claim_traceability = MagicMock()
    resp.claim_traceability.segments = []
    resp.claim_traceability.overall_coverage = 0.0
    resp.validation_warnings = None
    resp.agent_agreement = True
    return resp


# ---------------------------------------------------------------------------
# URL capture tests
# ---------------------------------------------------------------------------

class TestCandidateUrlCapture:
    """Tests that candidate_urls is populated / clean across different outcomes."""

    def test_urls_empty_on_doi_not_found(self) -> None:
        """candidate_urls is empty when DOI resolution fails before HTTP retrieval."""
        case = _make_case()

        with patch(
            "app.evaluation.live_diagnostics.analyze_verification",
            side_effect=PaperNotFoundError("DOI not found"),
        ):
            live_result, response = evaluate_live_case(case, max_retries=MAX_RETRIES)

        assert live_result.status == "skipped"
        assert live_result.failure_category == LiveFailureCategory.DOI_NOT_FOUND
        assert live_result.candidate_urls == []
        assert response is None

    def test_original_retrieve_document_restored_after_success(self) -> None:
        """The monkey-patch on retrieve_document is removed after a successful call."""
        import app.services.paper_retriever as pr_mod

        original_fn = pr_mod.retrieve_document
        case = _make_case()
        resp = _success_response()

        with patch("app.evaluation.live_diagnostics.analyze_verification", return_value=resp):
            evaluate_live_case(case, max_retries=MAX_RETRIES)

        assert pr_mod.retrieve_document is original_fn

    def test_original_retrieve_document_restored_after_exception(self) -> None:
        """The monkey-patch is cleaned up even when an exception is raised."""
        import app.services.paper_retriever as pr_mod

        original_fn = pr_mod.retrieve_document
        case = _make_case()

        with patch(
            "app.evaluation.live_diagnostics.analyze_verification",
            side_effect=PaperNotFoundError("boom"),
        ):
            evaluate_live_case(case, max_retries=MAX_RETRIES)

        assert pr_mod.retrieve_document is original_fn

    def test_candidate_urls_is_list_of_strings(self) -> None:
        """candidate_urls is always a list of strings (never None)."""
        case = _make_case()
        resp = _success_response()

        with patch("app.evaluation.live_diagnostics.analyze_verification", return_value=resp):
            live_result, _ = evaluate_live_case(case, max_retries=MAX_RETRIES)

        assert isinstance(live_result.candidate_urls, list)
        assert all(isinstance(u, str) for u in live_result.candidate_urls)


# ---------------------------------------------------------------------------
# LiveCaseResult round-trip tests
# ---------------------------------------------------------------------------

class TestLiveCaseResultRoundTrip:
    """Tests that candidate_urls survives dataclass construction."""

    def test_candidate_urls_stored_correctly(self) -> None:
        result = LiveCaseResult(
            case_id="r1",
            status="evaluated",
            expected_verdict=Verdict.SUPPORTS,
            actual_verdict=Verdict.SUPPORTS,
            confidence=0.9,
            failure_category=None,
            failure_reason=None,
            retrieval_attempts=2,
            elapsed_seconds=1.5,
            candidate_urls=["https://example.com/a.pdf", "https://example.com/b.pdf"],
            retrieval_elapsed_ms=1500,
        )
        assert result.candidate_urls == [
            "https://example.com/a.pdf",
            "https://example.com/b.pdf",
        ]

    def test_candidate_urls_defaults_to_empty(self) -> None:
        result = LiveCaseResult(
            case_id="r2",
            status="skipped",
            expected_verdict=Verdict.CONTRADICTS,
            actual_verdict=None,
            confidence=None,
            failure_category=LiveFailureCategory.DOI_NOT_FOUND,
            failure_reason="not found",
            retrieval_attempts=1,
            elapsed_seconds=0.1,
        )
        assert result.candidate_urls == []

    def test_candidate_urls_immutable_after_construction(self) -> None:
        """LiveCaseResult is frozen; candidate_urls cannot be replaced."""
        result = LiveCaseResult(
            case_id="r3",
            status="evaluated",
            expected_verdict=Verdict.SUPPORTS,
            actual_verdict=Verdict.SUPPORTS,
            confidence=0.7,
            failure_category=None,
            failure_reason=None,
            retrieval_attempts=1,
            elapsed_seconds=0.5,
            candidate_urls=["https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/"],
        )
        with pytest.raises((AttributeError, TypeError)):
            result.candidate_urls = []  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Report payload tests
# ---------------------------------------------------------------------------

class TestReportPayloadIncludesCandidateUrls:
    """Verify that _build_live_diagnostics_payload exposes candidate_urls per case."""

    def _make_live_result(self, urls: list[str]) -> LiveCaseResult:
        return LiveCaseResult(
            case_id="rep-001",
            status="evaluated",
            expected_verdict=Verdict.SUPPORTS,
            actual_verdict=Verdict.SUPPORTS,
            confidence=0.88,
            failure_category=None,
            failure_reason=None,
            retrieval_attempts=1,
            elapsed_seconds=2.0,
            candidate_urls=urls,
            retrieval_elapsed_ms=2000,
        )

    def test_candidate_urls_in_json_payload(self) -> None:
        """The JSON report payload for a live case includes candidate_urls."""
        from app.evaluation.report import _build_live_diagnostics_payload

        live_result = self._make_live_result(
            ["https://pmc.ncbi.nlm.nih.gov/articles/PMC9999/pdf/"]
        )
        payload = _build_live_diagnostics_payload([live_result], None)

        case_entry = next(
            (c for c in payload.get("case_results", []) if c.get("case_id") == "rep-001"),
            None,
        )
        assert case_entry is not None, "case_entry not found in payload"
        assert "candidate_urls" in case_entry, "candidate_urls missing from case payload"
        assert case_entry["candidate_urls"] == [
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC9999/pdf/"
        ]

    def test_empty_candidate_urls_included(self) -> None:
        """An empty candidate_urls list is still present in the payload."""
        from app.evaluation.report import _build_live_diagnostics_payload

        live_result = self._make_live_result([])
        payload = _build_live_diagnostics_payload([live_result], None)

        case_entry = next(
            (c for c in payload.get("case_results", []) if c.get("case_id") == "rep-001"),
            None,
        )
        assert case_entry is not None
        assert "candidate_urls" in case_entry
        assert case_entry["candidate_urls"] == []
