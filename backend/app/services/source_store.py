"""Content-addressed, single-user local source artifacts; no domain/API bytes."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.schemas.paper import PaperMetadata, PaperSource, RetrievePaperResponse, PaperRetrievalStatus
from app.utils.doi import normalize_doi

logger = logging.getLogger(__name__)
_SHA = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class AcceptedSourceArtifact:
    doi: str
    raw_content_sha256: str
    format: Literal["pdf", "html"]
    content: bytes
    source_url: str | None
    provider: str
    origin: Literal["remote", "manual"]
    paper: PaperMetadata

    @classmethod
    def create(cls, *, doi, content, format, source_url, provider, origin, paper):
        return cls(normalize_doi(doi), hashlib.sha256(content).hexdigest(), format,
                   content, source_url, provider, origin, paper.model_copy(deep=True))

    def response(self, *, cache_hit=False, sections=None, chunks=None):
        return RetrievePaperResponse(
            status=PaperRetrievalStatus.SUCCESS, paper=self.paper.model_copy(deep=True),
            sections=sections or [], chunks=chunks or [],
            source=PaperSource(url=self.source_url, provider=self.provider,
                               raw_content_sha256=self.raw_content_sha256,
                               origin=self.origin, cache_hit=cache_hit),
        )


class LocalSourceStore:
    def __init__(self, root: str | Path | None = None):
        from app.config import source_cache_dir
        self.root = Path(root) if root is not None else source_cache_dir()

    def _lookup_path(self, doi):
        key = hashlib.sha256(normalize_doi(doi).encode()).hexdigest()
        return self.root / "doi" / (key + ".json")

    @staticmethod
    def _atomic_write(target: Path, content: bytes):
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".pending-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)

    def put(self, artifact: AcceptedSourceArtifact):
        if artifact.format not in {"pdf", "html"} or artifact.origin not in {"remote", "manual"}:
            raise ValueError("Invalid source artifact")
        if (not artifact.content or not _SHA.fullmatch(artifact.raw_content_sha256)
                or hashlib.sha256(artifact.content).hexdigest() != artifact.raw_content_sha256
                or normalize_doi(artifact.paper.doi) != artifact.doi):
            raise ValueError("Invalid source identity")
        directory = self.root / artifact.raw_content_sha256
        metadata = {
            "version": 1, "doi": artifact.doi,
            "raw_content_sha256": artifact.raw_content_sha256, "format": artifact.format,
            "source_url": artifact.source_url, "provider": artifact.provider,
            "origin": artifact.origin, "paper": artifact.paper.model_dump(mode="json"),
        }
        # Store metadata per DOI so identical bytes can safely have multiple aliases.
        key = self._lookup_path(artifact.doi).name
        self._atomic_write(directory / ("source." + artifact.format), artifact.content)
        self._atomic_write(directory / key, json.dumps(metadata).encode())
        # Publish the DOI pointer last; readers never see a partially written artifact.
        self._atomic_write(self._lookup_path(artifact.doi), json.dumps({
            "raw_content_sha256": artifact.raw_content_sha256,
        }).encode())

    def get(self, doi: str) -> AcceptedSourceArtifact | None:
        normalized = normalize_doi(doi)
        try:
            lookup = self._lookup_path(normalized)
            digest = json.loads(lookup.read_text())["raw_content_sha256"]
            if not isinstance(digest, str) or not _SHA.fullmatch(digest):
                return None
            directory = self.root / digest
            data = json.loads((directory / lookup.name).read_text())
            if (data["version"] != 1 or data["doi"] != normalized
                    or data["raw_content_sha256"] != digest
                    or data["format"] not in {"pdf", "html"}
                    or data["origin"] not in {"remote", "manual"}):
                return None
            content = (directory / ("source." + data["format"])).read_bytes()
            if not content or hashlib.sha256(content).hexdigest() != digest:
                return None
            paper = PaperMetadata.model_validate(data["paper"])
            if normalize_doi(paper.doi) != normalized:
                return None
            return AcceptedSourceArtifact(normalized, digest, data["format"], content,
                                          data["source_url"], data["provider"], data["origin"], paper)
        except (OSError, ValueError, KeyError, TypeError):
            return None
