from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from app.evaluation.dataset_loader import load_dataset
from app.services.citation_resolver import (
    CitationNotFoundError,
    CitationResolverError,
    OPENALEX_API_URL,
    resolve_doi,
)
from app.services.paper_retriever import discover_full_text_candidates

logger = logging.getLogger(__name__)


class LiveHealthStatus(str, Enum):
    """Health status of a benchmark case for live evaluation."""
    HEALTHY = "HEALTHY"
    UNINDEXED = "UNINDEXED"
    PAYWALLED = "PAYWALLED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass
class CaseHealthCheck:
    """Health check result for a single benchmark case."""
    case_id: str
    doi: str
    health_status: LiveHealthStatus
    doi_resolved: bool
    doi_provider: str | None
    full_text_candidates: int
    accessible_candidates: int
    details: list[str] = field(default_factory=list)


@dataclass
class BenchmarkHealthReport:
    """Health check report for the entire benchmark dataset."""
    total_cases: int
    healthy_cases: int
    unindexed_cases: int
    paywalled_cases: int
    blocked_cases: int
    unknown_cases: int
    case_results: list[CaseHealthCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total_cases": self.total_cases,
                "healthy_cases": self.healthy_cases,
                "unindexed_cases": self.unindexed_cases,
                "paywalled_cases": self.paywalled_cases,
                "blocked_cases": self.blocked_cases,
                "unknown_cases": self.unknown_cases,
            },
            "cases": [
                {
                    "case_id": r.case_id,
                    "doi": r.doi,
                    "health_status": r.health_status.value,
                    "doi_resolved": r.doi_resolved,
                    "doi_provider": r.doi_provider,
                    "full_text_candidates": r.full_text_candidates,
                    "accessible_candidates": r.accessible_candidates,
                    "details": r.details,
                }
                for r in self.case_results
            ],
        }


def check_benchmark_health(dataset_path: Path | None = None) -> BenchmarkHealthReport:
    """Run health check on all benchmark cases."""
    from app.evaluation.dataset_loader import default_dataset_path

    dataset = load_dataset(dataset_path or default_dataset_path())
    
    report = BenchmarkHealthReport(
        total_cases=len(dataset.cases),
        healthy_cases=0,
        unindexed_cases=0,
        paywalled_cases=0,
        blocked_cases=0,
        unknown_cases=0,
    )

    http_client = httpx.Client(timeout=30.0, headers={"User-Agent": "SciVerify/0.1.0"})

    try:
        for case in dataset.cases:
            case_result = _check_case_health(case, http_client)
            report.case_results.append(case_result)

            # Update summary counts
            if case_result.health_status == LiveHealthStatus.HEALTHY:
                report.healthy_cases += 1
            elif case_result.health_status == LiveHealthStatus.UNINDEXED:
                report.unindexed_cases += 1
            elif case_result.health_status == LiveHealthStatus.PAYWALLED:
                report.paywalled_cases += 1
            elif case_result.health_status == LiveHealthStatus.BLOCKED:
                report.blocked_cases += 1
            else:
                report.unknown_cases += 1
    finally:
        http_client.close()

    return report


def _check_case_health(case, http_client: httpx.Client) -> CaseHealthCheck:
    """Check health of a single benchmark case."""
    details: list[str] = []
    doi_resolved = False
    doi_provider = None
    full_text_candidates = 0
    accessible_candidates = 0

    # Step 1: Check DOI resolution
    try:
        citation = resolve_doi(case.doi, client=http_client)
        doi_resolved = True
        doi_provider = citation.source
        details.append(f"DOI resolved via {citation.source}")
    except CitationNotFoundError:
        details.append("DOI not found in Crossref or OpenAlex")
        return CaseHealthCheck(
            case_id=case.id,
            doi=case.doi,
            health_status=LiveHealthStatus.UNINDEXED,
            doi_resolved=False,
            doi_provider=None,
            full_text_candidates=0,
            accessible_candidates=0,
            details=details,
        )
    except CitationResolverError as exc:
        details.append(f"DOI resolution failed: {exc}")
        return CaseHealthCheck(
            case_id=case.id,
            doi=case.doi,
            health_status=LiveHealthStatus.UNKNOWN,
            doi_resolved=False,
            doi_provider=None,
            full_text_candidates=0,
            accessible_candidates=0,
            details=details,
        )

    # Step 2: Check full-text availability via OpenAlex
    try:
        openalex_url = f"{OPENALEX_API_URL}/works/https://doi.org/{case.doi}"
        response = http_client.get(openalex_url)
        if response.status_code == 200:
            openalex_work = response.json()
            candidates = discover_full_text_candidates(openalex_work)
            full_text_candidates = len(candidates)
            details.append(f"Found {full_text_candidates} full-text candidates via OpenAlex")

            # Step 3: Check if candidates are from known OA repositories
            known_oa_providers = {
                "pmc", "pubmed central", "europe pmc", "arxiv", "biorxiv", "medrxiv"
            }
            for candidate in candidates:
                provider_lower = candidate.provider.lower()
                if any(oa in provider_lower for oa in known_oa_providers):
                    accessible_candidates += 1
                    details.append(f"Accessible candidate from {candidate.provider}")

            if accessible_candidates > 0:
                details.append(f"Case appears healthy with {accessible_candidates} accessible candidates")
                return CaseHealthCheck(
                    case_id=case.id,
                    doi=case.doi,
                    health_status=LiveHealthStatus.HEALTHY,
                    doi_resolved=doi_resolved,
                    doi_provider=doi_provider,
                    full_text_candidates=full_text_candidates,
                    accessible_candidates=accessible_candidates,
                    details=details,
                )
            elif full_text_candidates > 0:
                details.append("Candidates exist but may be paywalled")
                return CaseHealthCheck(
                    case_id=case.id,
                    doi=case.doi,
                    health_status=LiveHealthStatus.PAYWALLED,
                    doi_resolved=doi_resolved,
                    doi_provider=doi_provider,
                    full_text_candidates=full_text_candidates,
                    accessible_candidates=accessible_candidates,
                    details=details,
                )
            else:
                details.append("No full-text candidates found")
                return CaseHealthCheck(
                    case_id=case.id,
                    doi=case.doi,
                    health_status=LiveHealthStatus.PAYWALLED,
                    doi_resolved=doi_resolved,
                    doi_provider=doi_provider,
                    full_text_candidates=0,
                    accessible_candidates=0,
                    details=details,
                )
        else:
            details.append(f"OpenAlex returned status {response.status_code}")
            return CaseHealthCheck(
                case_id=case.id,
                doi=case.doi,
                health_status=LiveHealthStatus.UNKNOWN,
                doi_resolved=doi_resolved,
                doi_provider=doi_provider,
                full_text_candidates=0,
                accessible_candidates=0,
                details=details,
            )
    except Exception as exc:
        details.append(f"Full-text discovery failed: {exc}")
        return CaseHealthCheck(
            case_id=case.id,
            doi=case.doi,
            health_status=LiveHealthStatus.UNKNOWN,
            doi_resolved=doi_resolved,
            doi_provider=doi_provider,
            full_text_candidates=0,
            accessible_candidates=0,
            details=details,
        )


def main():
    """Run health check and print results."""
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    report = check_benchmark_health()

    print("Benchmark Health Check Report")
    print("=" * 50)
    print(f"Total cases: {report.total_cases}")
    print(f"Healthy: {report.healthy_cases}")
    print(f"Unindexed: {report.unindexed_cases}")
    print(f"Paywalled: {report.paywalled_cases}")
    print(f"Blocked: {report.blocked_cases}")
    print(f"Unknown: {report.unknown_cases}")
    print()

    for result in report.case_results:
        print(f"{result.case_id}: {result.health_status.value}")
        for detail in result.details:
            print(f"  - {detail}")
        print()

    # Write JSON report
    output_path = Path(__file__).resolve().parents[2] / "evaluation" / "results" / "health_check.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(f"Wrote health check report to {output_path}")

    # Exit with error if no healthy cases
    if report.healthy_cases == 0:
        print("WARNING: No healthy cases found for live evaluation", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
