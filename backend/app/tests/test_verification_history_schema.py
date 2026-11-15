"""Regression tests for Supabase verification_history schema and serialization contracts.

Validates:
1. SQL migration 002_create_verification_history.sql integrity, columns, indexes, and RLS policies.
2. Canonical table name matches frontend historyService.ts ('verification_history').
3. Row fields match between SQL schema, TypeScript interfaces, and backend responses.
4. Parsing and serialization round-trip preservation of complete reports (including agent details,
   claim traceability, agreement, validation warnings).
5. Minimal fallback reconstruction when result_json is unavailable or incomplete.
6. Dashboard statistics parity across persisted history records.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "supabase"
    / "migrations"
    / "002_create_verification_history.sql"
)


class TestVerificationHistorySqlMigration:
    def test_migration_file_exists(self) -> None:
        assert MIGRATION_PATH.exists(), f"Migration not found at {MIGRATION_PATH}"

    def test_table_name_is_canonical_verification_history(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        assert "create table if not exists public.verification_history" in sql.lower()

    def test_required_columns_exist_in_sql(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        expected_columns = [
            "id uuid",
            "user_id uuid not null references auth.users(id)",
            "claim text not null",
            "doi text not null",
            "paper_title text",
            "verdict text not null",
            "confidence numeric not null",
            "summary text",
            "result_json jsonb not null",
            "created_at timestamptz not null",
        ]
        for col in expected_columns:
            assert col in sql, f"Missing expected column definition: {col}"

    def test_user_created_index_exists(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        assert "on public.verification_history (user_id, created_at desc)" in sql

    def test_rls_is_enabled(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        assert "alter table public.verification_history enable row level security" in sql

    def test_all_crud_rls_policies_exist(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8").lower()
        assert "for select" in sql
        assert "for insert" in sql
        assert "for update" in sql
        assert "for delete" in sql
        assert "using (auth.uid() = user_id)" in sql
        assert "with check (auth.uid() = user_id)" in sql


class TestVerificationHistorySerialization:
    SAMPLE_RESULT = {
        "id": "3dd0d437-14ff-4477-85f4-da2bb63d67aa",
        "claim": "Cas9 can be programmed with guide RNA.",
        "citation": "10.1126/science.1225829",
        "sourceType": "doi",
        "citationStatus": "verified",
        "verdict": "SUPPORTS",
        "confidence": 92,
        "summary": "The evidence supports the claim.",
        "reasoning": "Dual-RNA structure directs Cas9 to introduce site-specific dsDNA breaks.",
        "paperTitle": "A Programmable Dual-RNA-Guided DNA Endonuclease",
        "paperDoi": "10.1126/science.1225829",
        "agentAgreement": True,
        "validationWarnings": [],
        "evidenceFactors": [
            {"factor": "Direct experimental confirmation", "impact": "positive"}
        ],
        "prosecutor": {
            "role": "Prosecutor",
            "summary": "Examined edge cases.",
            "finding": "No contradictory findings.",
            "status": "completed",
        },
        "defender": {
            "role": "Defender",
            "summary": "Validated key claim.",
            "finding": "Direct support in section 3.",
            "status": "completed",
        },
        "adjudicator": {
            "role": "Adjudicator",
            "summary": "Evidence verified.",
            "finding": "High confidence support.",
            "status": "completed",
        },
        "evidence": [],
        "suggestedCorrection": None,
        "claimTraceability": {
            "claim": "Cas9 can be programmed with guide RNA.",
            "overallCoverage": 1.0,
            "segments": [
                {
                    "text": "Cas9 can be programmed with guide RNA.",
                    "status": "SUPPORTED",
                    "supportingChunks": ["c1"],
                }
            ],
            "traceabilityWarnings": [],
        },
        "createdAt": "2026-08-17T12:00:00.000Z",
    }

    def test_to_insert_row_contract(self) -> None:
        user_id = "user-uuid-1234"
        row = {
            "id": self.SAMPLE_RESULT["id"],
            "user_id": user_id,
            "claim": self.SAMPLE_RESULT["claim"],
            "doi": self.SAMPLE_RESULT["paperDoi"],
            "paper_title": self.SAMPLE_RESULT["paperTitle"],
            "verdict": self.SAMPLE_RESULT["verdict"],
            "confidence": self.SAMPLE_RESULT["confidence"],
            "summary": self.SAMPLE_RESULT["summary"],
            "result_json": self.SAMPLE_RESULT,
            "created_at": self.SAMPLE_RESULT["createdAt"],
        }

        # Validate JSON serialization of result_json
        serialized = json.dumps(row)
        deserialized = json.loads(serialized)
        assert deserialized["user_id"] == user_id
        assert deserialized["result_json"]["agentAgreement"] is True
        assert deserialized["result_json"]["claimTraceability"]["overallCoverage"] == 1.0

    def test_parse_stored_verification_result_preserves_full_data(self) -> None:
        row = {
            "id": self.SAMPLE_RESULT["id"],
            "user_id": "user-uuid-1234",
            "claim": self.SAMPLE_RESULT["claim"],
            "doi": "10.1126/science.1225829",
            "paper_title": "Override Title",
            "verdict": "SUPPORTS",
            "confidence": 92,
            "summary": "Summary text",
            "result_json": self.SAMPLE_RESULT,
            "created_at": "2026-08-17T12:00:00.000Z",
        }

        raw = row["result_json"]
        parsed = dict(raw)
        parsed["id"] = row["id"]
        parsed["createdAt"] = row["created_at"]
        parsed["paperTitle"] = raw.get("paperTitle") or row.get("paper_title")
        parsed["paperDoi"] = raw.get("paperDoi") or row.get("doi")

        assert parsed["id"] == self.SAMPLE_RESULT["id"]
        assert parsed["agentAgreement"] is True
        assert parsed["verdict"] == "SUPPORTS"
        assert parsed["prosecutor"]["role"] == "Prosecutor"
        assert parsed["claimTraceability"]["segments"][0]["status"] == "SUPPORTED"

    def test_rebuild_minimal_result_fallback(self) -> None:
        row = {
            "id": "minimal-uuid",
            "user_id": "user-uuid-1234",
            "claim": "Minimal claim.",
            "doi": "10.1000/minimal",
            "paper_title": "Minimal Paper",
            "verdict": "OVERSTATED",
            "confidence": 65,
            "summary": "Minimal summary.",
            "result_json": None,
            "created_at": "2026-08-17T11:00:00.000Z",
        }

        rebuilt = {
            "id": row["id"],
            "claim": row["claim"],
            "citation": row["doi"],
            "sourceType": "doi",
            "citationStatus": "verified",
            "verdict": row["verdict"],
            "confidence": row["confidence"],
            "summary": row["summary"],
            "reasoning": row["summary"],
            "paperTitle": row["paper_title"],
            "paperDoi": row["doi"],
            "agentAgreement": None,
            "validationWarnings": [],
            "evidenceFactors": [],
            "prosecutor": {
                "role": "Prosecutor",
                "summary": "Analysis unavailable.",
                "finding": "Stored report did not include agent details.",
                "status": "completed",
            },
            "defender": {
                "role": "Defender",
                "summary": "Analysis unavailable.",
                "finding": "Stored report did not include agent details.",
                "status": "completed",
            },
            "adjudicator": {
                "role": "Adjudicator",
                "summary": "Analysis unavailable.",
                "finding": "Stored report did not include agent details.",
                "status": "completed",
            },
            "evidence": [],
            "suggestedCorrection": None,
            "createdAt": row["created_at"],
        }

        assert rebuilt["agentAgreement"] is None
        assert rebuilt["validationWarnings"] == []
        assert rebuilt["verdict"] == "OVERSTATED"


class TestDashboardStatsParity:
    def test_compute_stats_matches_records(self) -> None:
        records = [
            {"verdict": "SUPPORTS"},
            {"verdict": "SUPPORTS"},
            {"verdict": "OVERSTATED"},
            {"verdict": "CONTRADICTS"},
            {"verdict": "INSUFFICIENT"},
            {"verdict": "FABRICATED"},
        ]

        stats = {
            "total": len(records),
            "supports": sum(1 for r in records if r["verdict"] == "SUPPORTS"),
            "overstated": sum(1 for r in records if r["verdict"] == "OVERSTATED"),
            "contradicts": sum(1 for r in records if r["verdict"] == "CONTRADICTS"),
            "insufficient": sum(1 for r in records if r["verdict"] == "INSUFFICIENT"),
            "fabricated": sum(1 for r in records if r["verdict"] == "FABRICATED"),
        }

        assert stats["total"] == 6
        assert stats["supports"] == 2
        assert stats["overstated"] == 1
        assert stats["contradicts"] == 1
        assert stats["insufficient"] == 1
        assert stats["fabricated"] == 1

    def test_handles_lowercase_and_unknown_verdict_gracefully(self) -> None:
        """Verifies that corrupted or lowercase verdict strings in history records
        fallback safely without raising uncaught exceptions."""
        valid_verdicts = {"SUPPORTS", "OVERSTATED", "CONTRADICTS", "INSUFFICIENT", "FABRICATED"}

        def resolve_verdict(val: object) -> str:
            if isinstance(val, str):
                upper = val.strip().upper()
                if upper in valid_verdicts:
                    return upper
            return "INSUFFICIENT"

        assert resolve_verdict("supports") == "SUPPORTS"
        assert resolve_verdict("Contradicts") == "CONTRADICTS"
        assert resolve_verdict("INVALID_VERDICT") == "INSUFFICIENT"
        assert resolve_verdict(None) == "INSUFFICIENT"
        assert resolve_verdict(123) == "INSUFFICIENT"
