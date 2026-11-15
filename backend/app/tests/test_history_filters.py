"""Tests for verification history filter helpers mirrored in the frontend."""

from __future__ import annotations


def matches_history_search(record: dict, query: str) -> bool:
    normalized = query.strip().lower()
    if not normalized:
        return True

    haystack = " ".join(
        filter(
            None,
            [
                record.get("claim"),
                record.get("citation"),
                record.get("paperDoi"),
                record.get("paperTitle"),
                record.get("summary"),
            ],
        )
    ).lower()
    return normalized in haystack


def matches_verdict_filter(record: dict, verdict_filter: str) -> bool:
    return verdict_filter == "all" or record.get("verdict") == verdict_filter


def sort_history_records(records: list[dict], sort: str) -> list[dict]:
    reverse = sort == "newest"
    return sorted(records, key=lambda item: item["createdAt"], reverse=reverse)


def filter_history_records(
    records: list[dict],
    *,
    search: str,
    verdict_filter: str,
    sort: str,
) -> list[dict]:
    filtered = [
        record
        for record in records
        if matches_history_search(record, search)
        and matches_verdict_filter(record, verdict_filter)
    ]
    return sort_history_records(filtered, sort)


class TestHistoryFilters:
    SAMPLE = [
        {
            "id": "1",
            "claim": "Cas9 can be programmed with guide RNA",
            "citation": "10.1126/science.1225829",
            "paperDoi": "10.1126/science.1225829",
            "paperTitle": "A Programmable Dual-RNA-Guided DNA Endonuclease",
            "summary": "Programmable genome editing",
            "verdict": "OVERSTATED",
            "createdAt": "2026-08-13T10:00:00.000Z",
        },
        {
            "id": "2",
            "claim": "Accuracy improved by 40%",
            "citation": "10.1000/test",
            "paperDoi": "10.1000/test",
            "paperTitle": "Benchmark Paper",
            "summary": "Benchmark results",
            "verdict": "SUPPORTS",
            "createdAt": "2026-08-12T10:00:00.000Z",
        },
    ]

    def test_search_matches_claim_doi_and_title(self) -> None:
        assert matches_history_search(self.SAMPLE[0], "cas9")
        assert matches_history_search(self.SAMPLE[0], "10.1126/science.1225829")
        assert matches_history_search(self.SAMPLE[0], "programmable dual-rna")

    def test_verdict_filter(self) -> None:
        filtered = filter_history_records(
            self.SAMPLE,
            search="",
            verdict_filter="OVERSTATED",
            sort="newest",
        )
        assert len(filtered) == 1
        assert filtered[0]["id"] == "1"

    def test_sort_newest_and_oldest(self) -> None:
        newest = filter_history_records(
            self.SAMPLE,
            search="",
            verdict_filter="all",
            sort="newest",
        )
        oldest = filter_history_records(
            self.SAMPLE,
            search="",
            verdict_filter="all",
            sort="oldest",
        )
        assert newest[0]["id"] == "1"
        assert oldest[0]["id"] == "2"

    def test_empty_search_returns_all(self) -> None:
        filtered = filter_history_records(
            self.SAMPLE,
            search="   ",
            verdict_filter="all",
            sort="newest",
        )
        assert len(filtered) == 2
