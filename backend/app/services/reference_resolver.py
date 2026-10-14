"""Bounded bibliographic identity enrichment, before M3B. No source downloads/LLM.

URLs are discovered only; this module never requests a user-supplied URL.
Resolution confidence describes identity matching, never scientific support.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlsplit

import httpx

from app.researchguard.domain import ParsedManuscript, Reference, ReferenceCandidate, ReferenceResolution
from app.services.citation_context import validate_input
from app.services.citation_resolver import (
    CROSSREF_API_URL, OPENALEX_API_URL, USER_AGENT,
    _extract_crossref_authors, _extract_openalex_authors, _first_str, _year_from_date_parts,
)
from app.utils.doi import InvalidDOIError, normalize_doi

MAX_REFERENCES = 100
MAX_CANDIDATES = 10
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT = 10.0
TOTAL_TIMEOUT = 180.0
CONCURRENCY = 2
OFFICIAL_HOSTS = ("who.int", "cdc.gov", "fda.gov", "jhu.edu")
OFFICIAL_NAMES = re.compile(r"\b(?:world health organi[sz]ation|centers for disease control|food and drug administration|johns hopkins)\b", re.I)
PREPRINT = re.compile(r"\b(?:preprint|bioRxiv|medRxiv|arXiv)\b", re.I)


class ResolutionInputError(ValueError):
    pass


class ProviderError(Exception):
    def __init__(self, code):
        self.code = code


def discover_url(raw_text: str) -> str | None:
    # PDF references often put a typeset URL (including spaces) in parentheses.
    # Strip whitespace only within that explicit URL boundary; do not repair prose.
    match = re.search(r"\((https?://[^)]+)\)", raw_text, re.I)
    if match:
        return re.sub(r"\s+", "", match.group(1)).rstrip(".,;")
    match = re.search(r"https?://[^\s<>\"']+", raw_text, re.I)
    return match.group().rstrip(".,;)") if match else None


def is_public_http_url(value: str | None) -> bool:
    """Syntactic discovery gate, not authorization to fetch (no DNS or I/O)."""
    if not value or len(value) > 4000 or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        return False
    try:
        url = urlsplit(value)
        host = (url.hostname or "").rstrip(".").lower()
        if url.scheme not in {"http", "https"} or not host or url.username or url.password:
            return False
        if url.port not in {None, 80, 443}:
            return False
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            address = ipaddress.ip_address(host)
            return address.is_global and not (getattr(address, "ipv4_mapped", None) and not address.ipv4_mapped.is_global)
        except ValueError:
            return bool(re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host)) and not re.fullmatch(r"[\d.]+", host)
    except ValueError:
        return False


def _normal(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value).casefold() if not unicodedata.combining(c))


def _compact(value: str) -> str:
    return "".join(c for c in _normal(value) if c.isalnum())


def _surname(name: str) -> str:
    words = re.findall(r"[^\W\d_]+", _normal(name))
    words = [w for w in words if w not in {"jr", "sr", "ii", "iii", "iv"}]
    return words[-1] if words else ""


def _journal_matches(original: str | None, candidate: str | None) -> bool:
    if not original or not candidate:
        return False
    a, b = _compact(original), _compact(candidate)
    if a == b:
        return True
    def initials(text):
        return "".join(w[0] for w in re.findall(r"\w+", _normal(text)) if w not in {"of", "the", "and"})
    return len(initials(original)) >= 2 and initials(original) == initials(candidate)


def match_candidate(reference: Reference, candidate: ReferenceCandidate) -> ReferenceCandidate:
    a, b = _compact(reference.title or ""), _compact(candidate.title)
    similarity = SequenceMatcher(None, a, b, autojunk=False).ratio()
    evidence = [f"TITLE_SIMILARITY:{similarity:.4f}"]
    reason = None
    if not a or similarity < .985 or (len(a) < 40 and a != b):
        reason = "TITLE_MISMATCH"
    # A changed vaccine/dose/year identifier must not disappear in a fuzzy score.
    if re.findall(r"\d+", a) != re.findall(r"\d+", b):
        reason = reason or "TITLE_IDENTIFIER_CONFLICT"
    authors_known = bool(reference.authors and candidate.authors)
    author_matches = 0
    if authors_known:
        original = [_surname(n) for n in reference.authors if _surname(n)]
        found = {_surname(n) for n in candidate.authors}
        author_matches = sum(n in found for n in original)
        if not original or original[0] not in found or author_matches < min(2, len(original)):
            reason = reason or "AUTHOR_CONFLICT"
        else:
            evidence.append(f"AUTHOR_MATCHES:{author_matches}")
    else:
        evidence.append("AUTHORS_UNKNOWN")
    journal_match = _journal_matches(reference.journal, candidate.journal)
    if journal_match:
        evidence.append("JOURNAL_MATCH")
    year_match = reference.year is not None and reference.year in candidate.years
    if year_match:
        evidence.append("YEAR_MATCH")
    elif reference.year is not None and candidate.years:
        offset = min(abs(reference.year - y) for y in candidate.years)
        if offset == 1 and author_matches >= 2 and journal_match:
            evidence.append("YEAR_OFFSET_1_VERSION_CHECK")
        else:
            reason = reason or "YEAR_CONFLICT"
    else:
        evidence.append("YEAR_UNKNOWN")
    cited_preprint = bool(PREPRINT.search(reference.raw_text + " " + (reference.journal or "")))
    candidate_preprint = candidate.publication_type == "preprint"
    if cited_preprint and not candidate_preprint:
        reason = reason or "VERSION_UNCERTAIN"
    elif not cited_preprint and candidate_preprint and reference.journal:
        reason = reason or "PUBLICATION_TYPE_CONFLICT"
    elif reference.journal and candidate.publication_type in {"book", "book-chapter", "dataset", "dissertation", "monograph", "report"}:
        reason = reason or "PUBLICATION_TYPE_CONFLICT"
    if cited_preprint and candidate_preprint:
        evidence.append("PREPRINT_TYPE_MATCH")
    if a != b and not (author_matches >= 2 and year_match):
        reason = reason or "INSUFFICIENT_IDENTITY_EVIDENCE"
    if not authors_known and not (a == b and year_match and journal_match):
        reason = reason or "INSUFFICIENT_IDENTITY_EVIDENCE"
    if reference.year is None and not (a == b and author_matches >= 2):
        reason = reason or "INSUFFICIENT_IDENTITY_EVIDENCE"
    confidence = min(.99, .90 * similarity + .04 * bool(author_matches) + .03 * year_match + .02 * journal_match)
    return candidate.model_copy(update={"match_confidence": confidence, "evidence": tuple(evidence), "rejection_reason": reason})


def _crossref_candidates(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("message"), dict):
        raise ProviderError("CROSSREF_INVALID_RESPONSE")
    items = payload["message"].get("items")
    if not isinstance(items, list):
        raise ProviderError("CROSSREF_INVALID_RESPONSE")
    result = []
    for item in items[:MAX_CANDIDATES]:
        if not isinstance(item, dict):
            continue
        try:
            doi = normalize_doi(_first_str(item.get("DOI")) or "")
        except InvalidDOIError:
            continue
        title = _first_str(item.get("title"))
        if not title:
            continue
        years = tuple(sorted({y for k in ("published-print", "published-online", "issued", "published", "posted")
                              if (y := _year_from_date_parts(item.get(k))) is not None}))
        work_type = _first_str(item.get("type"))
        if work_type == "posted-content" and item.get("subtype") == "preprint":
            work_type = "preprint"
        relations = item.get("relation", {})
        result.append(ReferenceCandidate(doi=doi, title=title[:2000], authors=tuple(_extract_crossref_authors(item.get("author"))[:100]),
            years=years, journal=_first_str(item.get("container-title")), publication_type=work_type, provider="crossref",
            relations=tuple(sorted(relations)) if isinstance(relations, dict) else ()))
    return result


def _openalex_candidates(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ProviderError("OPENALEX_INVALID_RESPONSE")
    result = []
    for item in payload["results"][:MAX_CANDIDATES]:
        if not isinstance(item, dict):
            continue
        try:
            doi = normalize_doi(_first_str(item.get("doi")) or "")
        except InvalidDOIError:
            continue
        title = _first_str(item.get("display_name"))
        if not title:
            continue
        location = item.get("primary_location") or {}
        source = location.get("source") or {} if isinstance(location, dict) else {}
        journal = _first_str(source.get("display_name")) if isinstance(source, dict) else None
        year = item.get("publication_year")
        result.append(ReferenceCandidate(doi=doi, title=title[:2000], authors=tuple(_extract_openalex_authors(item.get("authorships"))[:100]),
            years=(year,) if type(year) is int else (), journal=journal, publication_type=_first_str(item.get("type")), provider="openalex"))
    return result


async def search_reference_by_metadata(reference, provider, client, limited):
    if provider in limited:
        raise ProviderError(provider.upper() + "_RATE_LIMIT")
    if provider == "crossref":
        query = " ".join(filter(None, (reference.title, " ".join(reference.authors[:3]), str(reference.year) if reference.year else None)))
        url, params = CROSSREF_API_URL + "/works", {"query.bibliographic": query, "rows": MAX_CANDIDATES}
        headers = {}
    else:
        url, params = OPENALEX_API_URL + "/works", {"search": reference.title, "per_page": MAX_CANDIDATES}
        key = os.getenv("OPENALEX_API_KEY", "").strip()
        headers = {"Authorization": "Bearer " + key} if key else {}
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            async with client.stream("GET", url, params=params, headers=headers, timeout=REQUEST_TIMEOUT, follow_redirects=False) as response:
                if response.status_code == 429:
                    limited.add(provider)
                    raise ProviderError(provider.upper() + "_RATE_LIMIT")
                if response.status_code != 200:
                    raise ProviderError(provider.upper() + "_HTTP_ERROR")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise ProviderError(provider.upper() + "_RESPONSE_TOO_LARGE")
                    content.extend(chunk)
                payload = json.loads(content)
    except (httpx.TimeoutException, TimeoutError):
        raise ProviderError(provider.upper() + "_TIMEOUT") from None
    except httpx.HTTPError:
        raise ProviderError(provider.upper() + "_NETWORK_ERROR") from None
    except (ValueError, UnicodeError, RecursionError):
        raise ProviderError(provider.upper() + "_INVALID_JSON") from None
    return (_crossref_candidates if provider == "crossref" else _openalex_candidates)(payload)


def _select(reference, candidates, diagnostics, successful_providers):
    # Deduplicate identities, not provider hits. Keep rejected candidates visible.
    accepted = {}
    for c in candidates:
        if c.rejection_reason is None:
            accepted.setdefault(c.doi, c)
    version_uncertain = any(c.rejection_reason == "VERSION_UNCERTAIN" for c in candidates)
    # A cited preprint can later be retitled. Shared authors are a reason to
    # flag version uncertainty, never permission to accept a different title.
    cited_preprint = bool(PREPRINT.search(reference.raw_text + " " + (reference.journal or "")))
    version_uncertain = version_uncertain or (cited_preprint and any(
        c.publication_type == "preprint" and any(e.startswith("AUTHOR_MATCHES:") for e in c.evidence)
        for c in candidates))
    if len(accepted) == 1:
        c = next(iter(accepted.values()))
        return ReferenceResolution(reference_id=reference.id, original_doi=None, status="resolved", resolved_doi=c.doi,
            matched_title=c.title, provider=c.provider, source_type="doi", match_reason="IDENTITY_MATCHED",
            match_confidence=c.match_confidence, diagnostics=tuple(diagnostics), candidates=tuple(candidates))
    if accepted or version_uncertain:
        status, reason = "ambiguous", "MULTIPLE_IDENTITIES" if accepted else "VERSION_UNCERTAIN"
        if version_uncertain:
            diagnostics = [*diagnostics, "PREPRINT_VERSION_UNCERTAIN"]
    elif not successful_providers:
        status, reason = "provider_error", "PROVIDERS_UNAVAILABLE"
    elif any(d.endswith(("_TIMEOUT", "_HTTP_ERROR", "_NETWORK_ERROR", "_RATE_LIMIT", "_INVALID_JSON", "_INVALID_RESPONSE", "_RESPONSE_TOO_LARGE")) for d in diagnostics):
        status, reason = "provider_error", "SEARCH_INCOMPLETE"
    else:
        status, reason = "not_found", "NO_RELIABLE_MATCH"
    return ReferenceResolution(reference_id=reference.id, status=status, match_reason=reason,
        diagnostics=tuple(diagnostics), candidates=tuple(candidates))


async def _resolve(reference, client, limited):
    raw_url = discover_url(reference.raw_text)
    url = raw_url or reference.url
    diagnostics = []
    if raw_url and reference.url and raw_url != reference.url:
        diagnostics.append("URL_FIELDS_DISAGREE_RAW_PREFERRED")
    if url and not is_public_http_url(url):
        diagnostics.append("URL_INVALID_OR_PRIVATE")
        url = None
    if reference.doi:
        try:
            doi = normalize_doi(reference.doi)
        except InvalidDOIError:
            return ReferenceResolution(reference_id=reference.id, original_doi=reference.doi, status="metadata_insufficient",
                match_reason="ORIGINAL_DOI_INVALID", diagnostics=tuple(diagnostics))
        return ReferenceResolution(reference_id=reference.id, original_doi=reference.doi, resolved_doi=doi, status="resolved",
            provider="original", source_type="doi", source_url=url, match_reason="ORIGINAL_DOI_PRESERVED",
            diagnostics=tuple(diagnostics))
    host = (urlsplit(url).hostname or "").lower() if url else ""
    official = any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS) or bool(OFFICIAL_NAMES.search(reference.raw_text))
    # A merged M3A bibliography entry can contain the following web reference.
    # Structured article authors+journal take precedence over trailing URLs.
    article = bool(reference.authors and reference.journal)
    if official and not article or url and not reference.authors and not reference.journal:
        return ReferenceResolution(reference_id=reference.id, status="non_doi_source", source_type="url", source_url=url,
            match_reason="URL_ONLY_RETRIEVAL_NOT_SUPPORTED", diagnostics=tuple(diagnostics + ["DISCOVERED_ONLY"] + ([] if url else ["URL_MISSING"])))
    if not reference.title or len(_compact(reference.title)) < 12:
        return ReferenceResolution(reference_id=reference.id, status="metadata_insufficient", source_url=url,
            match_reason="TITLE_MISSING_OR_TOO_SHORT", diagnostics=tuple(diagnostics))
    if article and official:
        diagnostics.append("POSSIBLE_MERGED_WEB_REFERENCE")
    candidates, successful = [], 0
    for provider in ("crossref", "openalex"):
        try:
            found = await search_reference_by_metadata(reference, provider, client, limited)
            successful += 1
            candidates.extend(match_candidate(reference, c) for c in found)
        except ProviderError as exc:
            diagnostics.append(exc.code)
        selection = _select(reference, candidates, diagnostics, successful)
        if selection.status == "resolved":
            return selection
    return _select(reference, candidates, diagnostics, successful)


async def resolve_reference(reference: Reference, *, client: httpx.AsyncClient | None = None) -> ReferenceResolution:
    if client is not None:
        return await _resolve(reference, client, set())
    async with httpx.AsyncClient(headers={"Accept": "application/json", "User-Agent": USER_AGENT}, trust_env=False) as owned:
        return await _resolve(reference, owned, set())


async def resolve_references(parsed: ParsedManuscript, *, client: httpx.AsyncClient | None = None) -> ParsedManuscript:
    parsed = validate_input(parsed)
    if len(parsed.references) > MAX_REFERENCES:
        raise ResolutionInputError("REFERENCE_LIMIT_EXCEEDED")
    if any(r.resolution is not None for r in parsed.references):
        # Resolve original input only. Client-supplied diagnostics are not proof.
        raise ResolutionInputError("REFERENCES_ALREADY_ENRICHED")
    for r in parsed.references:
        if (len(r.raw_text) > 12000 or len(r.title or "") > 2000 or len(r.authors) > 100
                or any(len(a) > 200 for a in r.authors) or len(r.journal or "") > 2000):
            raise ResolutionInputError("REFERENCE_METADATA_TOO_LARGE")
    async def run(http):
        semaphore, limited, memo = asyncio.Semaphore(CONCURRENCY), set(), {}
        async def one(reference):
            async with semaphore:
                return await _resolve(reference, http, limited)
        tasks = []
        for r in parsed.references:
            key = (r.doi, r.title, r.authors, r.year, r.journal, r.raw_text, r.url)
            if key not in memo:
                memo[key] = asyncio.create_task(one(r))
            tasks.append(memo[key])
        pending = set()
        try:
            if tasks:
                _, pending = await asyncio.wait(set(tasks), timeout=TOTAL_TIMEOUT)
        except BaseException:
            for task in set(tasks):
                task.cancel()
            await asyncio.gather(*set(tasks), return_exceptions=True)
            raise
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        references = []
        for r, task in zip(parsed.references, tasks):
            result = (ReferenceResolution(reference_id=r.id, status="provider_error", match_reason="REQUEST_DEADLINE",
                diagnostics=("TOTAL_TIMEOUT",)) if task.cancelled() else task.result().model_copy(update={"reference_id": r.id}))
            doi = result.resolved_doi if result.status == "resolved" else r.doi
            references.append(r.model_copy(update={"doi": doi, "resolution": result}))
        enriched = ParsedManuscript.model_validate(parsed.model_copy(update={"references": tuple(references)}).model_dump())
        if len(enriched.model_dump_json().encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ResolutionInputError("ENRICHED_MANUSCRIPT_TOO_LARGE")
        return enriched
    if client is not None:
        return await run(client)
    async with httpx.AsyncClient(headers={"Accept": "application/json", "User-Agent": USER_AGENT}, trust_env=False,
                                limits=httpx.Limits(max_connections=CONCURRENCY)) as owned:
        return await run(owned)
