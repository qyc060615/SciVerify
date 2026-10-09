from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import find_dotenv, load_dotenv

    # 1. Try explicit backend directory .env (parent of app package)
    backend_env = Path(__file__).resolve().parent.parent / ".env"
    if backend_env.exists():
        load_dotenv(dotenv_path=backend_env, override=True)
    else:
        # 2. Try find_dotenv or default search
        found_env = find_dotenv(usecwd=True)
        if found_env:
            load_dotenv(dotenv_path=found_env, override=True)
        else:
            load_dotenv(override=True)
except ImportError:
    pass

PAPER_REQUEST_TIMEOUT = float(os.getenv("PAPER_REQUEST_TIMEOUT", "30"))
MAX_DOCUMENT_SIZE = int(os.getenv("MAX_DOCUMENT_SIZE", str(20 * 1024 * 1024)))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
EVIDENCE_TOP_K = int(os.getenv("EVIDENCE_TOP_K", "5"))
EVIDENCE_MIN_RELEVANCE = float(os.getenv("EVIDENCE_MIN_RELEVANCE", "0.05"))
EVIDENCE_DIVERSITY_THRESHOLD = float(os.getenv("EVIDENCE_DIVERSITY_THRESHOLD", "0.75"))
EVIDENCE_MAX_PER_SECTION = int(os.getenv("EVIDENCE_MAX_PER_SECTION", "2"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", "60"))


class EvidenceEngineConfigurationError(ValueError):
    """Invalid evidence engine configuration, never a semantic verdict."""


def get_evidence_engine() -> str:
    engine = os.getenv("RESEARCHGUARD_EVIDENCE_ENGINE", "lexical").strip().lower()
    if engine not in {"lexical", "paperqa2"}:
        raise EvidenceEngineConfigurationError("RESEARCHGUARD_EVIDENCE_ENGINE must be lexical or paperqa2.")
    return engine


# M2 local demo source lifecycle; evaluated at use time for isolated tests.
def source_cache_dir() -> Path:
    return Path(os.getenv("RESEARCHGUARD_SOURCE_CACHE_DIR") or
                Path(__file__).resolve().parent.parent / "data/researchguard/sources")


def source_max_size() -> int:
    value = int(os.getenv("RESEARCHGUARD_SOURCE_MAX_SIZE", str(20 * 1024 * 1024)))
    if value <= 0:
        raise ValueError("Source size limit must be positive")
    return value


def paperqa_cache_size() -> int:
    value = int(os.getenv("RESEARCHGUARD_PAPERQA_CACHE_SIZE", "8"))
    if value < 0:
        raise ValueError("PaperQA cache size must be nonnegative")
    return value


def manuscript_max_size() -> int:
    value = int(os.getenv("RESEARCHGUARD_MANUSCRIPT_MAX_SIZE", str(20 * 1024 * 1024)))
    if value <= 0:
        raise ValueError("Manuscript size limit must be positive")
    return value


def grobid_settings() -> dict:
    """Read at use time: no network, no startup dependency on GROBID."""
    return {
        "base_url": os.getenv("GROBID_BASE_URL", "http://127.0.0.1:8070").strip().rstrip("/"),
        "connect_timeout": float(os.getenv("GROBID_CONNECT_TIMEOUT", "5")),
        "read_timeout": float(os.getenv("GROBID_READ_TIMEOUT", "180")),
        "total_timeout": float(os.getenv("GROBID_TOTAL_TIMEOUT", "240")),
        "max_tei_size": int(os.getenv("GROBID_MAX_TEI_SIZE", str(20 * 1024 * 1024))),
    }
