from __future__ import annotations

import os
from typing import Any

import httpx

from app.schemas.citation import CitationMetadata
from app.utils.doi import InvalidDOIError, normalize_doi

DEFAULT_TIMEOUT = 10.0
CROSSREF_API_URL = os.getenv(
    "CROSSREF_API_URL", "https://api.crossref.org"
).rstrip("/")
OPENALEX_API_URL = os.getenv(
    "OPENALEX_API_URL", "https://api.openalex.org"
).rstrip("/")
SEMANTIC_SCHOLAR_API_URL = os.getenv(
    "SEMANTIC_SCHOLAR_API_URL", "https://api.semanticscholar.org"
).rstrip("/")
USER_AGENT = os.getenv(
    "CITATION_USER_AGENT",
    "SciVerify/0.1.0 (https://github.com/sciverify; citation-resolver)",
)


class CitationNotFoundError(Exception):
    """Raised when a DOI cannot be resolved by any provider."""


class CitationResolverError(Exception):
    """Raised when an external citation provider fails unexpectedly."""


def resolve_doi(
    doi: str,
    client: httpx.Client | None = None,
) -> CitationMetadata:
    """Resolve a DOI to normalized citation metadata."""
    normalized = normalize_doi(doi)
    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )

    try:
        crossref_error: Exception | None = None
        try:
            metadata = _resolve_from_crossref(normalized, http_client)
            if metadata is not None:
                return metadata
        except CitationResolverError as exc:
            crossref_error = exc

        openalex_error: Exception | None = None
        try:
            metadata = _resolve_from_openalex(normalized, http_client)
            if metadata is not None:
                return metadata
        except CitationNotFoundError:
            raise
        except CitationResolverError as exc:
            openalex_error = exc

        try:
            metadata = _resolve_from_semantic_scholar(normalized, http_client)
            if metadata is not None:
                return metadata
        except CitationNotFoundError:
            raise
        except CitationResolverError as exc:
            if crossref_error is not None and openalex_error is not None:
                raise CitationResolverError(
                    "Citation providers are temporarily unavailable."
                ) from exc
            raise

        raise CitationNotFoundError(f"Citation not found for DOI: {normalized}")
    finally:
        if owns_client:
            http_client.close()


def _resolve_from_crossref(
    doi: str,
    client: httpx.Client,
) -> CitationMetadata | None:
    url = f"{CROSSREF_API_URL}/works/{doi}"
    try:
        response = client.get(url)
    except httpx.TimeoutException as exc:
        raise CitationResolverError("Crossref request timed out.") from exc
    except httpx.RequestError as exc:
        raise CitationResolverError("Crossref request failed.") from exc

    if response.status_code == 404:
        return None

    if response.status_code >= 500:
        raise CitationResolverError("Crossref service is unavailable.")

    if response.status_code >= 400:
        raise CitationResolverError("Crossref rejected the request.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise CitationResolverError("Crossref returned invalid JSON.") from exc

    message = payload.get("message")
    if not isinstance(message, dict):
        raise CitationResolverError("Crossref returned an unexpected response.")

    return _map_crossref_message(message, doi)


def _resolve_from_openalex(
    doi: str,
    client: httpx.Client,
) -> CitationMetadata | None:
    url = f"{OPENALEX_API_URL}/works/https://doi.org/{doi}"
    try:
        response = client.get(url)
    except httpx.TimeoutException as exc:
        raise CitationResolverError("OpenAlex request timed out.") from exc
    except httpx.RequestError as exc:
        raise CitationResolverError("OpenAlex request failed.") from exc

    if response.status_code == 404:
        return None

    if response.status_code >= 500:
        raise CitationResolverError("OpenAlex service is unavailable.")

    if response.status_code >= 400:
        raise CitationResolverError("OpenAlex rejected the request.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise CitationResolverError("OpenAlex returned invalid JSON.") from exc

    if not isinstance(payload, dict) or not payload.get("id"):
        return None

    return _map_openalex_work(payload, doi)


def _resolve_from_semantic_scholar(
    doi: str,
    client: httpx.Client,
) -> CitationMetadata | None:
    url = f"{SEMANTIC_SCHOLAR_API_URL}/paper/DOI:{doi}"
    try:
        response = client.get(url)
    except httpx.TimeoutException as exc:
        raise CitationResolverError("Semantic Scholar request timed out.") from exc
    except httpx.RequestError as exc:
        raise CitationResolverError("Semantic Scholar request failed.") from exc

    if response.status_code == 404:
        return None

    if response.status_code >= 500:
        raise CitationResolverError("Semantic Scholar service is unavailable.")

    if response.status_code >= 400:
        raise CitationResolverError("Semantic Scholar rejected the request.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise CitationResolverError("Semantic Scholar returned invalid JSON.") from exc

    if not isinstance(payload, dict):
        return None

    return _map_semantic_scholar_paper(payload, doi)


def _map_crossref_message(message: dict[str, Any], doi: str) -> CitationMetadata | None:
    resolved_doi = _first_str(message.get("DOI")) or doi
    title = _first_str(message.get("title"))
    authors = _extract_crossref_authors(message.get("author"))
    journal = _first_str(message.get("container-title"))
    publisher = _first_str(message.get("publisher"))
    year = _extract_year(message)
    url = _first_str(message.get("URL")) or f"https://doi.org/{resolved_doi}"
    work_type = _first_str(message.get("type"))

    if not any([title, authors, journal, publisher, year]):
        return None

    return CitationMetadata(
        doi=resolved_doi.lower(),
        title=title,
        authors=authors,
        journal=journal,
        publisher=publisher,
        year=year,
        url=url,
        source="crossref",
        type=work_type,
    )


def _map_openalex_work(work: dict[str, Any], doi: str) -> CitationMetadata | None:
    title = work.get("display_name")
    if isinstance(title, str):
        title = title.strip() or None
    else:
        title = None

    authors = _extract_openalex_authors(work.get("authorships"))
    journal = None
    publisher = None
    primary_location = work.get("primary_location")
    if isinstance(primary_location, dict):
        source = primary_location.get("source")
        if isinstance(source, dict):
            journal = source.get("display_name")
            publisher = source.get("host_organization_name")

    year = work.get("publication_year")
    if not isinstance(year, int):
        year = None

    openalex_doi = work.get("doi")
    resolved_doi = doi
    if isinstance(openalex_doi, str) and openalex_doi.strip():
        resolved_doi = openalex_doi.removeprefix("https://doi.org/").lower()

    url = work.get("id") if isinstance(work.get("id"), str) else None
    if not url:
        url = f"https://doi.org/{resolved_doi}"

    work_type = work.get("type")
    if not isinstance(work_type, str):
        work_type = None

    if not any([title, authors, journal, publisher, year]):
        return None

    return CitationMetadata(
        doi=resolved_doi.lower(),
        title=title,
        authors=authors,
        journal=journal if isinstance(journal, str) else None,
        publisher=publisher if isinstance(publisher, str) else None,
        year=year,
        url=url,
        source="openalex",
        type=work_type,
    )


def _map_semantic_scholar_paper(paper: dict[str, Any], doi: str) -> CitationMetadata | None:
    title = paper.get("title")
    if isinstance(title, str):
        title = title.strip() or None
    else:
        title = None

    authors = _extract_semantic_scholar_authors(paper.get("authors"))
    journal = paper.get("venue")
    if isinstance(journal, str):
        journal = journal.strip() or None
    else:
        journal = None

    year = paper.get("year")
    if not isinstance(year, int):
        year = None

    paper_doi = paper.get("externalIds", {}).get("DOI")
    resolved_doi = doi
    if isinstance(paper_doi, str) and paper_doi.strip():
        resolved_doi = paper_doi.lower()

    url = paper.get("url") if isinstance(paper.get("url"), str) else None
    if not url:
        url = f"https://doi.org/{resolved_doi}"

    work_type = paper.get("publicationTypes")
    if isinstance(work_type, list) and work_type:
        work_type = work_type[0] if isinstance(work_type[0], str) else None
    else:
        work_type = None

    if not any([title, authors, journal, year]):
        return None

    return CitationMetadata(
        doi=resolved_doi.lower(),
        title=title,
        authors=authors,
        journal=journal,
        publisher=None,
        year=year,
        url=url,
        source="semantic_scholar",
        type=work_type,
    )


def _extract_semantic_scholar_authors(raw_authors: Any) -> list[str]:
    if not isinstance(raw_authors, list):
        return []

    authors: list[str] = []
    for author in raw_authors:
        if not isinstance(author, dict):
            continue
        given = author.get("given")
        family = author.get("family")
        name_parts = [
            part.strip()
            for part in [given, family]
            if isinstance(part, str) and part.strip()
        ]
        if name_parts:
            authors.append(" ".join(name_parts))
    return authors


def _extract_crossref_authors(raw_authors: Any) -> list[str]:
    if not isinstance(raw_authors, list):
        return []

    authors: list[str] = []
    for author in raw_authors:
        if not isinstance(author, dict):
            continue
        given = author.get("given")
        family = author.get("family")
        name_parts = [
            part.strip()
            for part in [given, family]
            if isinstance(part, str) and part.strip()
        ]
        if name_parts:
            authors.append(" ".join(name_parts))
    return authors


def _extract_openalex_authors(raw_authorships: Any) -> list[str]:
    if not isinstance(raw_authorships, list):
        return []

    authors: list[str] = []
    for authorship in raw_authorships:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author")
        if isinstance(author, dict):
            display_name = author.get("display_name")
            if isinstance(display_name, str) and display_name.strip():
                authors.append(display_name.strip())
    return authors


def _extract_year(message: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "created", "issued"):
        year = _year_from_date_parts(message.get(key))
        if year is not None:
            return year
    return None


def _year_from_date_parts(raw_value: Any) -> int | None:
    if not isinstance(raw_value, dict):
        return None
    date_parts = raw_value.get("date-parts")
    if not isinstance(date_parts, list) or not date_parts:
        return None
    first_part = date_parts[0]
    if not isinstance(first_part, list) or not first_part:
        return None
    year = first_part[0]
    return year if isinstance(year, int) else None


def _first_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
    return None
