from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.benchmark_health import (
    CaseHealthCheck,
    check_benchmark_health,
    LiveHealthStatus,
)


class TestBenchmarkHealthCheck:
    def test_health_status_enum(self) -> None:
        """Test that health status enum has expected values."""
        assert LiveHealthStatus.HEALTHY.value == "HEALTHY"
        assert LiveHealthStatus.UNINDEXED.value == "UNINDEXED"
        assert LiveHealthStatus.PAYWALLED.value == "PAYWALLED"
        assert LiveHealthStatus.BLOCKED.value == "BLOCKED"
        assert LiveHealthStatus.UNKNOWN.value == "UNKNOWN"

    def test_case_health_check_structure(self) -> None:
        """Test that CaseHealthCheck has all required fields."""
        result = CaseHealthCheck(
            case_id="test-001",
            doi="10.1126/science.1225829",
            health_status=LiveHealthStatus.HEALTHY,
            doi_resolved=True,
            doi_provider="crossref",
            full_text_candidates=2,
            accessible_candidates=1,
            details=["DOI resolved via crossref"],
        )
        assert result.case_id == "test-001"
        assert result.health_status == LiveHealthStatus.HEALTHY
        assert result.doi_resolved is True

    def test_paywall_detection(self) -> None:
        """Test that paywall detection is implemented in document retriever."""
        from app.services.document_retriever import PaywallError, is_paywall_content

        # Test paywall content detection
        assert is_paywall_content(b"Subscription required to access")
        assert is_paywall_content(b"Purchase access to read")
        assert not is_paywall_content(b"Normal content")

        # Test PaywallError exception
        error = PaywallError("This content is behind a paywall")
        assert isinstance(error, Exception)
