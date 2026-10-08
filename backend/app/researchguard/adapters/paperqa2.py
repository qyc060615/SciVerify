"""paper-qa==2026.8.12 boundary: one accepted source, evidence only.

No aadd_url, metadata inference, agents, paper search, or final answer generation.
A bounded process-local source index cache reuses embeddings; queries stay fresh.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import weakref
from collections import OrderedDict

import math
import os
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..domain import AtomicClaim, EvidenceChunk, RetrievalStatus, SourceDocument

PAPERQA2_VERSION = "2026.8.12"
logger = logging.getLogger(__name__)
# Each event loop owns its locks and indexes; backend lifespan uses one loop.
# Explicit cache clearing at application shutdown releases indexes and loop locks.
_INDEX_CACHES = weakref.WeakKeyDictionary()


def clear_index_cache():
    _INDEX_CACHES.clear()


def _loop_cache():
    loop = asyncio.get_running_loop()
    if loop not in _INDEX_CACHES:
        _INDEX_CACHES[loop] = (OrderedDict(), asyncio.Lock())
    return _INDEX_CACHES[loop]



class PaperQA2RetrievalError(RuntimeError):
    """Safe application error code; never expose provider bodies/source text."""


@dataclass(frozen=True)
class PaperQA2Config:
    model: str
    embedding_model: str
    candidate_k: int = 10
    max_concurrent_requests: int = 4
    timeout: float = 60.0
    api_key: str | None = field(default=None, repr=False)
    api_base: str | None = None
    embedding_api_key: str | None = field(default=None, repr=False)
    embedding_api_base: str | None = None
    embedding_batch_size: int = 10

    def __post_init__(self) -> None:
        if type(self.embedding_batch_size) is not int or self.embedding_batch_size <= 0:
            raise PaperQA2RetrievalError("paperqa2_configuration: embedding batch size must be a positive integer.")
        if not self.model.strip() or not self.embedding_model.strip():
            raise PaperQA2RetrievalError("paperqa2_configuration: set PAPERQA2_MODEL and PAPERQA2_EMBEDDING_MODEL.")
        if self.candidate_k <= 0 or self.max_concurrent_requests <= 0 or not math.isfinite(self.timeout) or self.timeout <= 0:
            raise PaperQA2RetrievalError("paperqa2_configuration: candidate count, concurrency and timeout must be positive.")

    @classmethod
    def from_environment(cls) -> PaperQA2Config:
        try:
            return cls(
                model=os.getenv("PAPERQA2_MODEL", "").strip(),
                embedding_model=os.getenv("PAPERQA2_EMBEDDING_MODEL", "").strip(),
                candidate_k=int(os.getenv("PAPERQA2_EVIDENCE_CANDIDATES", "10")),
                max_concurrent_requests=int(os.getenv("PAPERQA2_MAX_CONCURRENT_REQUESTS", "4")),
                timeout=float(os.getenv("PAPERQA2_REQUEST_TIMEOUT", "60")),
                api_key=os.getenv("PAPERQA2_API_KEY") or None,
                api_base=os.getenv("PAPERQA2_API_BASE") or None,
                embedding_api_key=os.getenv("PAPERQA2_EMBEDDING_API_KEY") or None,
                embedding_api_base=os.getenv("PAPERQA2_EMBEDDING_API_BASE") or None,
                embedding_batch_size=int(os.getenv("PAPERQA2_EMBEDDING_BATCH_SIZE", "10")),
            )
        except ValueError as exc:
            raise PaperQA2RetrievalError("paperqa2_configuration: invalid numeric setting.") from exc

    def make_settings(self, top_k: int):
        # Imports are lazy: lexical requests don't import PaperQA2 or LiteLLM.
        from paperqa import Settings

        params: dict[str, Any] = {"model": self.model, "timeout": self.timeout}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.api_base:
            params["api_base"] = self.api_base
        embedding_config: dict[str, Any] = {"timeout": self.timeout}
        if self.embedding_api_key:
            embedding_config["api_key"] = self.embedding_api_key
        if self.embedding_api_base:
            embedding_config["api_base"] = self.embedding_api_base
        return Settings(
            llm=self.model, summary_llm=self.model, embedding=self.embedding_model,
            summary_llm_config={"model_list": [{"model_name": self.model, "litellm_params": params}]},
            embedding_config={"batch_size": self.embedding_batch_size, "kwargs": embedding_config},
            verbosity=0,
            parsing={"defer_embedding": False},
            answer={
                "evidence_k": max(top_k, self.candidate_k),
                "evidence_retrieval": True, "evidence_skip_summary": False,
                "evidence_text_only_fallback": False,
                "max_concurrent_requests": self.max_concurrent_requests,
            },
            prompts={"use_json": True},
        )


class _StrictSummaryModel:
    """Prevent PaperQA2's context-failure swallowing and content-bearing logs.

    The pinned core retries/drops malformed summaries and some provider failures.
    Validate/translate before that handler so failures remain explicit.
    """

    def __init__(self, model: Any) -> None:
        self.model = model

    async def call_single(self, **kwargs):
        from paperqa.core import llm_parse_json

        try:
            result = await self.model.call_single(**kwargs)
        except Exception as exc:
            raise PaperQA2RetrievalError("paperqa2_summary_failed") from exc
        try:
            data = llm_parse_json(result.text or "")
            score = data["relevance_score"]
            if not isinstance(data["summary"], str) or isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 10:
                raise ValueError("Invalid summary/score")
        except (ValueError, KeyError, TypeError) as exc:
            raise PaperQA2RetrievalError("paperqa2_invalid_summary") from exc
        return result


class PaperQA2EvidenceRetriever:
    def __init__(
        self, chunks: Sequence[EvidenceChunk], config: PaperQA2Config, *,
        embedding_model: Any = None, summary_model: Any = None,
    ) -> None:
        self.chunks = tuple(chunks)
        self.config = config
        self.embedding_model = embedding_model
        self.summary_model = summary_model

    async def retrieve(
        self, claim: AtomicClaim, source_document: SourceDocument, top_k: int
    ) -> list[EvidenceChunk]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if source_document.retrieval_status != RetrievalStatus.AVAILABLE:
            raise PaperQA2RetrievalError("paperqa2_source_unavailable")
        if not self.chunks or any(c.source_document_id != source_document.id for c in self.chunks):
            raise PaperQA2RetrievalError("paperqa2_source_mismatch")
        if source_document.reference_id not in claim.reference_ids:
            raise PaperQA2RetrievalError("paperqa2_reference_mismatch")
        originals = {c.id: c for c in self.chunks}
        if len(originals) != len(self.chunks):
            raise PaperQA2RetrievalError("paperqa2_duplicate_chunk_identity")
        try:
            from anyio import to_thread
            docs, doc, texts, settings, embedding, summary = await to_thread.run_sync(
                self._prepare, source_document, top_k
            )
            docs, query_lock = await self._indexed_docs(source_document, docs, doc, texts, settings, embedding)
            async with query_lock:
                session = await docs.aget_evidence(
                    claim.text, settings=settings, embedding_model=embedding,
                    summary_llm_model=_StrictSummaryModel(summary),
                )
            # aget_evidence returns an unordered set-derived list. Sort by its
            # relevance score, with a deterministic canonical-ID tie break.
            mapped = [self._map_context(c, source_document, originals) for c in session.contexts]
            mapped.sort(key=lambda c: (-c.retrieval_score, c.id))
            selected: list[EvidenceChunk] = []
            seen: set[str] = set()
            for chunk in mapped:
                if chunk.id not in seen:
                    selected.append(chunk)
                    seen.add(chunk.id)
                if len(selected) == top_k:
                    break
            return selected
        except PaperQA2RetrievalError:
            raise
        except ImportError as exc:
            raise PaperQA2RetrievalError("paperqa2_dependency_unavailable") from exc
        except Exception as exc:
            raise PaperQA2RetrievalError("paperqa2_retrieval_failed") from exc

    async def _indexed_docs(self, source, docs, doc, texts, settings, embedding):
        from app.config import paperqa_cache_size
        limit = paperqa_cache_size()
        # Parsed fingerprint includes every mapped field affecting index/source identity.
        payload = [c.model_dump(exclude={"retrieval_score", "metadata"}) for c in self.chunks]
        key_payload = {
            "source": source.model_dump(), "chunks": payload, "version": PAPERQA2_VERSION,
            "embedding_model": self.config.embedding_model,
            "embedding_api_base": self.config.embedding_api_base,
            "embedding_timeout": self.config.timeout,
            # Credentials never appear in logs; changing accounts invalidates the entry.
            "credential_fingerprint": hashlib.sha256((self.config.embedding_api_key or "").encode()).hexdigest(),
            "defer_embedding": False,
        }
        key = hashlib.sha256(json.dumps(key_payload, sort_keys=True).encode()).hexdigest()
        # Injected deterministic/custom embedding objects must not share incompatible indexes.
        if self.embedding_model is not None:
            key = (key, id(self.embedding_model))
        async def build():
            added = await docs.aadd_texts(texts, doc, settings=settings, embedding_model=embedding)
            if not added or set(docs.docs) != {source.id}:
                raise PaperQA2RetrievalError("paperqa2_index_source_mismatch")
            return docs
        cache, lock = _loop_cache()
        async with lock:
            while len(cache) > limit:
                cache.popitem(last=False)
            if limit and key in cache:
                cached, _embedding_owner, query_lock = cache[key]
                cache.move_to_end(key)
                logger.info("paperqa_index_cache_hit source=%s", source.id)
                return cached, query_lock
            logger.info("paperqa_index_cache_miss source=%s", source.id)
            indexed = await build()
            query_lock = asyncio.Lock()
            if limit:
                # Keep injected embedding alive to avoid Python object-id reuse.
                cache[key] = (indexed, self.embedding_model, query_lock)
                while len(cache) > limit:
                    cache.popitem(last=False)
            return indexed, query_lock

    def _prepare(self, source_document: SourceDocument, top_k: int):
        from importlib.metadata import version
        from paperqa import Docs
        from paperqa.types import Doc, Text

        if version("paper-qa") != PAPERQA2_VERSION:
            raise PaperQA2RetrievalError("paperqa2_version_mismatch")
        settings = self.config.make_settings(top_k)
        embedding = self.embedding_model if self.embedding_model is not None else settings.get_embedding_model()
        summary = self.summary_model if self.summary_model is not None else settings.get_summary_llm()
        doc = Doc(
            docname=source_document.id, dockey=source_document.id,
            citation=source_document.title or source_document.doi or source_document.id,
            content_hash=source_document.content_hash,
        )
        texts = [Text(
            text=c.text, name=c.id, doc=doc, source_chunk_id=c.id,
            source_document_id=c.source_document_id, source_page=c.page,
            source_section=c.section, source_url=c.source_url,
        ) for c in self.chunks]
        docs = Docs()
        return docs, doc, texts, settings, embedding, summary

    @staticmethod
    def _map_context(context: Any, source: SourceDocument, originals: dict[str, EvidenceChunk]) -> EvidenceChunk:
        text = context.text
        original = originals.get(text.name)
        if original is None or str(text.doc.dockey) != source.id or text.text != original.text:
            raise PaperQA2RetrievalError("paperqa2_context_source_mismatch")
        score = float(context.score)
        if not math.isfinite(score) or not 0 <= score <= 10:
            raise PaperQA2RetrievalError("paperqa2_invalid_score")
        return original.model_copy(update={
            "retrieval_score": score,
            "metadata": {**original.metadata,
                "paperqa_docname": text.doc.docname,
                "paperqa_text_name": text.name,
                "paperqa_context_id": str(context.id),
                "paperqa_context_summary": context.context,
                "paperqa_score": score,
                "paperqa_version": PAPERQA2_VERSION,
            },
        })
