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
from app.researchguard.source_locator import SourceLocator, SourceProvenance

logger = logging.getLogger(__name__)
_SHA = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class AcceptedSourceArtifact:
    doi: str | None
    raw_content_sha256: str
    format: Literal["pdf", "html"]
    content: bytes
    source_url: str | None
    provider: str
    origin: Literal["remote", "manual"]
    paper: PaperMetadata
    locator: SourceLocator | None = None
    provenance: SourceProvenance | None = None

    @classmethod
    def create(cls, *, doi=None, content, format, source_url, provider, origin, paper,
               locator=None, provenance=None):
        normalized = normalize_doi(doi) if doi else None
        locator = SourceLocator.model_validate(locator) if locator is not None else None
        if normalized is None and (locator is None or locator.kind != 'url'):
            raise ValueError('Artifact needs a DOI or URL locator')
        return cls(normalized, hashlib.sha256(content).hexdigest(), format,
                   content, source_url, provider, origin, paper.model_copy(deep=True), locator, provenance)

    @property
    def source_locator(self):
        return self.locator or SourceLocator(kind='doi', value=self.doi)

    def response(self, *, cache_hit=False, sections=None, chunks=None):
        return RetrievePaperResponse(
            status=PaperRetrievalStatus.SUCCESS, paper=self.paper.model_copy(deep=True),
            sections=sections or [], chunks=chunks or [],
            source=PaperSource(url=self.source_url, provider=self.provider,
                               raw_content_sha256=self.raw_content_sha256,
                               origin=self.origin, cache_hit=cache_hit,
                               locator=self.locator, provenance=self.provenance,
                               identity_status=('confirmed' if self.provenance and self.provenance.identity == 'EXACT_IDENTITY'
                                                else 'uncertain')),
        )


class LocalSourceStore:
    def __init__(self, root: str | Path | None = None):
        from app.config import source_cache_dir
        self.root = Path(root) if root is not None else source_cache_dir()

    def _lookup_path(self, doi):
        key = hashlib.sha256(normalize_doi(doi).encode()).hexdigest()
        return self.root / "doi" / (key + ".json")

    def _locator_path(self, locator):
        if locator.kind == 'doi':
            return self._lookup_path(locator.value)
        key = hashlib.sha256(locator.value.encode()).hexdigest()
        return self.root / 'url' / ('url-' + key + '.json')

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
                or artifact.paper.doi != artifact.doi):
            raise ValueError("Invalid source identity")
        locator = artifact.source_locator
        if (locator.kind == 'doi' and normalize_doi(artifact.paper.doi) != locator.value
                or locator.kind == 'url' and (artifact.doi is not None or artifact.paper.paper_id != locator.key)):
            raise ValueError('Invalid artifact locator')
        directory = self.root / artifact.raw_content_sha256
        metadata = {
            "version": 1, "doi": artifact.doi,
            "raw_content_sha256": artifact.raw_content_sha256, "format": artifact.format,
            "source_url": artifact.source_url, "provider": artifact.provider,
            "origin": artifact.origin, "paper": artifact.paper.model_dump(mode="json"),
        }
        # Store metadata per DOI so identical bytes can safely have multiple aliases.
        if artifact.locator or artifact.provenance:
            metadata.update(version=2, locator=locator.model_dump(mode='json'),
                            provenance=artifact.provenance.model_dump(mode='json') if artifact.provenance else None)
        key = self._locator_path(locator).name
        raw = directory / ('source.' + artifact.format)
        if raw.exists() and raw.read_bytes() != artifact.content:
            # Only repair bytes that fail their own content-addressed identity.
            # The incoming content was hash-verified above; healthy versions stay immutable.
            if hashlib.sha256(raw.read_bytes()).hexdigest() == artifact.raw_content_sha256:
                raise ValueError('Immutable source content conflict')
            logger.warning('source_cache_repair hash=%s', artifact.raw_content_sha256)
        self._atomic_write(directory / ("source." + artifact.format), artifact.content)
        if not (directory / key).exists():
            self._atomic_write(directory / key, json.dumps(metadata).encode())
        # Publish the DOI pointer last; readers never see a partially written artifact.
        self._atomic_write(self._locator_path(locator), json.dumps({
            "raw_content_sha256": artifact.raw_content_sha256,
        }).encode())

    def get(self, doi: str) -> AcceptedSourceArtifact | None:
        return self._get_locator(SourceLocator(kind='doi', value=doi))

    def get_locator(self, locator: SourceLocator) -> AcceptedSourceArtifact | None:
        # Retain the original DOI-store extension/injection boundary.
        return self.get(locator.value) if locator.kind == 'doi' else self._get_locator(locator)

    def _get_locator(self, locator: SourceLocator) -> AcceptedSourceArtifact | None:
        normalized = locator.value if locator.kind == 'doi' else None
        try:
            lookup = self._locator_path(locator)
            digest = json.loads(lookup.read_text())["raw_content_sha256"]
            if not isinstance(digest, str) or not _SHA.fullmatch(digest):
                return None
            directory = self.root / digest
            data = json.loads((directory / lookup.name).read_text())
            if (data["version"] not in {1, 2} or data["doi"] != normalized
                    or data["raw_content_sha256"] != digest
                    or data["format"] not in {"pdf", "html"}
                    or data["origin"] not in {"remote", "manual"}):
                return None
            content = (directory / ("source." + data["format"])).read_bytes()
            if not content or hashlib.sha256(content).hexdigest() != digest:
                return None
            paper = PaperMetadata.model_validate(data["paper"])
            if (normalize_doi(paper.doi) if paper.doi else None) != normalized:
                return None
            stored_locator = SourceLocator.model_validate(data['locator']) if data['version'] == 2 else None
            if (stored_locator or SourceLocator(kind='doi', value=normalized)) != locator:
                return None
            if locator.kind == 'url' and paper.paper_id != locator.key:
                return None
            provenance = SourceProvenance.model_validate(data['provenance']) if data.get('provenance') else None
            if provenance and provenance.retrieved_version not in {None, 'sha256:' + digest}:
                return None
            return AcceptedSourceArtifact(normalized, digest, data["format"], content,
                                          data["source_url"], data["provider"], data["origin"], paper,
                                          stored_locator, provenance)
        except (OSError, ValueError, KeyError, TypeError):
            return None


class SourceDurabilityError(ValueError):
    """Safe, retryable source preparation error, never a semantic verdict."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def verify_source_durability(response, store, *, allow_legacy=False):
    """Require a rereadable raw artifact before a durable job invokes its verifier."""
    digest = response.source.raw_content_sha256
    if not digest:
        if allow_legacy:
            return
        raise SourceDurabilityError("SOURCE_DURABILITY_HASH_REQUIRED")
    if not isinstance(digest, str) or not _SHA.fullmatch(digest):
        raise SourceDurabilityError("SOURCE_DURABILITY_MISMATCH")
    locator = response.source.locator or SourceLocator(kind='doi', value=response.paper.doi)
    try:
        artifact = store.get_locator(locator)
    except OSError:
        raise SourceDurabilityError("SOURCE_DURABILITY_UNAVAILABLE") from None
    if artifact is None:
        raise SourceDurabilityError("SOURCE_DURABILITY_UNAVAILABLE")
    if (artifact.source_locator != locator or artifact.paper.doi != response.paper.doi
            or artifact.paper.paper_id != response.paper.paper_id
            or artifact.raw_content_sha256 != digest
            or hashlib.sha256(artifact.content).hexdigest() != digest
            or artifact.origin != response.source.origin
            or (response.paper.full_text_format is not None
                and artifact.format != response.paper.full_text_format)):
        raise SourceDurabilityError("SOURCE_DURABILITY_MISMATCH")
