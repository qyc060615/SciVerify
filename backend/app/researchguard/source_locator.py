"""Locator identity is independent of download location and content version."""
import hashlib
import ipaddress
import re
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator




def canonical_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 4000 or re.search(r'[\s\\\x00-\x1f\x7f]', value):
        raise ValueError('SOURCE_URL_INVALID')
    p = urlsplit(value)
    host_name = (p.hostname or '').rstrip('.').lower()
    if (p.scheme not in {'http', 'https'} or not host_name or p.username is not None or p.password is not None
            or p.port not in (None, 80, 443) or host_name == 'localhost'
            or host_name.endswith(('.localhost', '.local', '.internal')) or '%' in host_name):
        raise ValueError('SOURCE_URL_INVALID')
    try:
        ip = ipaddress.ip_address(host_name)
    except ValueError:
        if re.fullmatch(r'[\d.]+', host_name):
            raise ValueError('SOURCE_URL_INVALID') from None
    else:
        if not ip.is_global or (getattr(ip, 'ipv4_mapped', None) and not ip.ipv4_mapped.is_global):
            raise ValueError('SOURCE_URL_INVALID')
    host = host_name.encode('idna').decode('ascii').lower()
    host = '[' + host + ']' if ':' in host else host
    port = p.port
    netloc = host if port is None or (p.scheme, port) in {('https', 443), ('http', 80)} else f'{host}:{port}'
    return urlunsplit((p.scheme, netloc, p.path or '/', p.query, ''))


class SourceLocator(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    kind: Literal['doi', 'url']
    value: str

    @model_validator(mode='after')
    def canonical(self):
        normal = self.value.strip()
        if self.kind == 'doi':
            normal = re.sub(r'^doi:\s*|^https?://(?:dx\.)?doi\.org/\s*', '', normal, flags=re.I).strip().rstrip('.,;').lower()
            if not re.fullmatch(r'10\.\d{4,9}/\S+', normal):
                raise ValueError('DOI_INVALID')
        else:
            normal = canonical_url(normal)
        if normal != self.value:
            object.__setattr__(self, 'value', normal)
        return self

    @property
    def key(self) -> str:
        # Preserve existing DOI cache, source/evidence identities and expectation keys.
        return self.value if self.kind == 'doi' else 'url:' + hashlib.sha256(self.value.encode()).hexdigest()


class SourceProvenance(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    original_citation: str | None = None
    matched_doi: str | None = None
    source_url: str | None = None
    final_url: str | None = None
    retrieved_at: str | None = None
    retrieved_title: str | None = None
    publication_date: str | None = None
    retrieved_version: str | None = None
    identity: Literal['EXACT_IDENTITY', 'PROBABLE_SAME_WORK', 'IDENTITY_UNCERTAIN', 'IDENTITY_CONFLICT']
    document_kind: Literal['ARTICLE_FULL_TEXT', 'INSTITUTIONAL_DOCUMENT', 'LANDING_PAGE', 'ABSTRACT_ONLY', 'UNAVAILABLE']
    match_evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    identity_confidence: float | None = Field(default=None, ge=0, le=1)
