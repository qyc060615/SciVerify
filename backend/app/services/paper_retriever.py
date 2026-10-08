from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.schemas.citation import CitationMetadata
from app.schemas.paper import (
    PaperMetadata,
    PaperRetrievalStatus,
    PaperSource,
    RetrievePaperResponse,
)
from app.services.citation_resolver import (
    CitationNotFoundError,
    CitationResolverError,
    OPENALEX_API_URL,
    USER_AGENT,
    resolve_doi,
)
from app.services.document_parser import DocumentParseError, parse_document
from app.services.document_retriever import (
    DocumentRetrievalError,
    RetrievedDocument,
    retrieve_document,
)
from app.services.evidence_chunker import chunk_sections
from app.utils.doi import normalize_doi
from app.services.source_store import AcceptedSourceArtifact, LocalSourceStore
from app.services.full_text_qualifier import (
    discover_direct_full_text_links,
    is_full_text_document,
    normalize_candidate_url,
)

logger = logging.getLogger(__name__)

DocumentFormat = Literal["pdf", "html"]
MAX_SOURCE_CANDIDATE_VISITS = 24
MAX_SOURCE_FOLLOWUPS = 6

_PMC_ARTICLE_PATTERN = re.compile(
    r"(?:pmc\.ncbi\.nlm\.nih\.gov|ncbi\.nlm\.nih\.gov/pmc|europepmc\.org/pmc)/articles/(?:PMC)?(\d+)",
    re.IGNORECASE,
)
_KNOWN_OA_REPOSITORY_HOSTS = (
    "europepmc.org",
    "escholarship.org",
    "pubmedcentral.nih.gov",
    "ncbi.nlm.nih.gov/pmc",
    "pmc.ncbi.nlm.nih.gov",
)


class PaperNotFoundError(Exception):
    """Raised when a paper cannot be found."""


class PaperProviderError(Exception):
    """Raised when an external provider fails unexpectedly."""


class FullTextUnavailableError(Exception):
    """Raised when metadata exists but accessible full text is unavailable."""


class DocumentRetrievalFailure(PaperProviderError):
    """Raised when full-text download fails."""


@dataclass(frozen=True)
class FullTextCandidate:
    url: str
    format: DocumentFormat
    provider: str
    # Optional tag used internally for ranking; "repository" or "publisher"
    source_type: str = "unknown"


def retrieve_paper(
    doi: str,
    client: httpx.Client | None = None,
) -> RetrievePaperResponse:
    """Retrieve paper metadata and, when available, parsed evidence chunks."""
    normalized = normalize_doi(doi)
    store = LocalSourceStore()
    artifact = store.get(normalized)
    if artifact is not None:
        try:
            sections = parse_document(artifact.content, artifact.format)
            if not is_full_text_document(artifact.content, artifact.format):
                logger.warning("source_cache_rejected doi=%s reason=not_full_text", normalized)
            else:
                chunks = chunk_sections(sections, artifact.paper.paper_id, artifact.source_url)
                if chunks:
                    logger.info("source_cache_hit doi=%s origin=%s", normalized, artifact.origin)
                    return artifact.response(cache_hit=True, sections=sections, chunks=chunks)
        except DocumentParseError:
            if not is_full_text_document(artifact.content, artifact.format):
                logger.warning("source_cache_rejected doi=%s reason=not_full_text", normalized)
    logger.info("source_cache_miss doi=%s", normalized)
    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=30.0,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )

    try:
        try:
            citation = resolve_doi(normalized, client=http_client)
        except CitationNotFoundError as exc:
            raise PaperNotFoundError(str(exc)) from exc
        except CitationResolverError as exc:
            raise PaperProviderError(str(exc)) from exc

        openalex_work: dict[str, Any] | None = None
        provider_error: PaperProviderError | None = None
        try:
            openalex_work = _fetch_openalex_work(normalized, http_client)
        except PaperProviderError as exc:
            provider_error = exc

        paper = _build_paper_metadata(citation, openalex_work)
        source = _build_source(citation, openalex_work)

        if provider_error is not None and openalex_work is None:
            return RetrievePaperResponse(
                status=PaperRetrievalStatus.METADATA_ONLY,
                paper=paper,
                sections=[],
                chunks=[],
                source=source,
            )

        openalex_candidates = (
            discover_full_text_candidates(openalex_work)
            if openalex_work is not None
            else []
        )

        # Phase 20: always query Europe PMC regardless of OpenAlex hits (PMC is authoritative)
        epmc_candidates = _discover_europe_pmc_candidates(normalized, http_client)

        # Phase 20: query Unpaywall for additional OA repository candidates
        unpaywall_candidates = _discover_unpaywall_candidates(normalized, http_client)

        # Phase 20: query Semantic Scholar for OA PDF candidates not already found
        s2_candidates = _discover_semantic_scholar_candidates(normalized, http_client)

        all_raw = epmc_candidates + openalex_candidates + unpaywall_candidates + s2_candidates
        candidates = _order_candidates(_dedupe_candidates(all_raw))
        logger.info(
            "Candidate discovery complete: doi=%s total=%d sources=epmc:%d openalex:%d unpaywall:%d s2:%d",
            normalized,
            len(candidates),
            len(epmc_candidates),
            len(openalex_candidates),
            len(unpaywall_candidates),
            len(s2_candidates),
        )

        if not candidates:
            paper.full_text_available = False
            return RetrievePaperResponse(
                status=PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE,
                paper=paper,
                sections=[],
                chunks=[],
                source=source,
            )

        last_detail: str | None = None
        pending = deque((candidate, 0) for candidate in candidates)
        visited: set[str] = set()
        followups = 0
        visits = 0
        while pending and visits < MAX_SOURCE_CANDIDATE_VISITS:
            candidate, depth = pending.popleft()
            candidate_url = normalize_candidate_url(candidate.url)
            if candidate_url is None or candidate_url in visited:
                continue
            visited.add(candidate_url)
            visits += 1
            logger.info(
                "Trying full-text candidate: url=%s format=%s provider=%s",
                candidate.url,
                candidate.format,
                candidate.provider,
            )
            paper.full_text_available = True
            paper.full_text_format = candidate.format
            paper.full_text_url = candidate.url

            try:
                document = retrieve_document(
                    candidate.url,
                    expected_format=candidate.format,
                    client=http_client,
                )
            except DocumentRetrievalError as exc:
                last_detail = str(exc)
                logger.warning(
                    "Full-text candidate rejected: url=%s reason=%s",
                    candidate.url,
                    last_detail,
                )
                continue

            # Redirect destinations also participate in loop/duplicate prevention.
            final_url = normalize_candidate_url(document.source_url)
            if final_url:
                visited.add(final_url)

            parse_failed = False
            try:
                sections = parse_document(
                    content=document.content,
                    doc_format=document.format,
                    text=document.text,
                )
            except DocumentParseError as exc:
                last_detail = exc.message
                logger.warning(
                    "Full-text candidate parsing failed: url=%s reason=%s",
                    candidate.url,
                    last_detail,
                )
                parse_failed = True

            if not is_full_text_document(document.content, document.format):
                last_detail = "The retrieved page is not a full-text scholarly article."
                logger.info("full_text_candidate_rejected url=%s reason=landing_or_abstract", document.source_url)
                if depth == 0:
                    direct = discover_direct_full_text_links(document.content, document.source_url)
                    new = []
                    queued = {normalize_candidate_url(item.url) for item, _depth in pending}
                    for link in direct:
                        if link.url in visited or followups >= MAX_SOURCE_FOLLOWUPS:
                            continue
                        # Promote an already-discovered URL instead of requesting it twice.
                        if link.url in queued:
                            pending = deque((item, level) for item, level in pending
                                            if normalize_candidate_url(item.url) != link.url)
                        new.append((FullTextCandidate(link.url, link.format, candidate.provider, candidate.source_type), 1))
                        followups += 1
                        logger.info("full_text_followup_discovered url=%s format=%s", link.url, link.format)
                    pending.extendleft(reversed(new))
                continue

            if parse_failed:
                continue
            chunks = chunk_sections(
                sections=sections,
                paper_id=paper.paper_id,
                source_url=document.source_url,
            )
            if not chunks:
                last_detail = "Paper retrieved but no evidence chunks were produced."
                logger.warning(
                    "Full-text candidate produced no chunks: url=%s",
                    candidate.url,
                )
                continue

            paper.full_text_format = document.format
            paper.full_text_url = document.source_url
            artifact = AcceptedSourceArtifact.create(
                doi=normalized, content=document.content, format=document.format,
                source_url=document.source_url, provider=candidate.provider,
                origin="remote", paper=paper,
            )
            try:
                store.put(artifact)
            except OSError:
                logger.warning("source_cache_write_failed doi=%s", normalized)
            return artifact.response(sections=sections, chunks=chunks)

        paper.full_text_available = False
        paper.full_text_format = candidates[0].format
        paper.full_text_url = candidates[0].url
        return RetrievePaperResponse(
            status=PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE,
            paper=paper,
            sections=[],
            chunks=[],
            source=source,
            detail=last_detail or "Full text is unavailable for evidence retrieval.",
        )
    finally:
        if owns_client:
            http_client.close()


def _parsing_failure_response(
    *,
    paper: PaperMetadata,
    document: RetrievedDocument,
    full_text: FullTextCandidate,
    detail: str,
) -> RetrievePaperResponse:
    """Return a structured parsing-failure response after a successful download."""
    paper.full_text_available = True
    paper.full_text_format = full_text.format
    paper.full_text_url = full_text.url

    return RetrievePaperResponse(
        status=PaperRetrievalStatus.PARSING_FAILURE,
        paper=paper,
        sections=[],
        chunks=[],
        source=PaperSource(
            url=document.source_url,
            provider=full_text.provider,
        ),
        detail=detail,
    )


def discover_full_text(openalex_work: dict[str, Any]) -> FullTextCandidate | None:
    """Discover the best publicly accessible full-text source."""
    candidates = discover_full_text_candidates(openalex_work)
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.format == "pdf":
            return candidate
    return candidates[0]


def discover_full_text_candidates(openalex_work: dict[str, Any]) -> list[FullTextCandidate]:
    """Discover ordered publicly accessible full-text sources."""
    candidates: list[FullTextCandidate] = []
    open_access = openalex_work.get("open_access")
    work_is_oa = (
        isinstance(open_access, dict) and open_access.get("is_oa") is True
    )

    def _provider_from_url(url: str, default_provider: str) -> str:
        lowered = url.lower()
        if "pmc.ncbi.nlm.nih.gov" in lowered or "ncbi.nlm.nih.gov/pmc" in lowered:
            return "pmc"
        if "europepmc.org" in lowered:
            return "europepmc"
        return default_provider

    def add_candidate(url: str, doc_format: DocumentFormat, provider: str) -> None:
        normalized_url = url.strip()
        if normalized_url:
            candidates.append(
                FullTextCandidate(
                    url=normalized_url,
                    format=doc_format,
                    provider=_provider_from_url(normalized_url, provider),
                )
            )

    def add_location(location: dict[str, Any] | None, provider: str) -> None:
        if not isinstance(location, dict):
            return

        pdf_url = location.get("pdf_url")
        if isinstance(pdf_url, str) and pdf_url.strip():
            add_candidate(pdf_url, "pdf", provider)

        oa_url = location.get("oa_url")
        if isinstance(oa_url, str) and oa_url.strip():
            add_candidate(oa_url, _format_from_url(oa_url), provider)

        is_oa = location.get("is_oa")
        landing_page_url = location.get("landing_page_url")
        if isinstance(landing_page_url, str) and landing_page_url.strip():
            if is_oa is True or (
                work_is_oa and _is_known_oa_repository(landing_page_url)
            ):
                add_candidate(
                    landing_page_url,
                    _format_from_url(landing_page_url),
                    provider,
                )

    add_location(openalex_work.get("best_oa_location"), "openalex")
    add_location(openalex_work.get("primary_location"), "openalex")

    locations = openalex_work.get("locations")
    if isinstance(locations, list):
        for location in locations:
            if isinstance(location, dict):
                add_location(location, "openalex")

    if isinstance(open_access, dict):
        work_oa_url = open_access.get("oa_url")
        if isinstance(work_oa_url, str) and work_oa_url.strip():
            add_candidate(work_oa_url, _format_from_url(work_oa_url), "openalex")

    deduped = _dedupe_candidates(candidates)
    expanded = _expand_candidate_mirrors(deduped)
    return _order_candidates(_dedupe_candidates(expanded))


def _format_from_url(url: str) -> DocumentFormat:
    return "pdf" if url.lower().endswith(".pdf") else "html"


def _is_known_oa_repository(url: str) -> bool:
    lowered = url.lower()
    return any(host in lowered for host in _KNOWN_OA_REPOSITORY_HOSTS)


def _dedupe_candidates(candidates: list[FullTextCandidate]) -> list[FullTextCandidate]:
    deduped: list[FullTextCandidate] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        if candidate.url in seen_urls:
            continue
        seen_urls.add(candidate.url)
        deduped.append(candidate)
    return deduped


def _candidate_priority(candidate: FullTextCandidate) -> tuple[int, int]:
    """Return sort key for candidate full-text sources.

    Phase 20 — Universal Legal Retrieval tier ordering:
    Tier 0: PMC PDF (pmc.ncbi.nlm.nih.gov — direct, open, authoritative)
    Tier 1: Europe PMC HTML / PMC HTML (europepmc.org, ncbi.nlm.nih.gov/pmc — open)
    Tier 2: OA repository PDF (arXiv, Unpaywall repository, institutional repos)
    Tier 3: OA repository HTML
    Tier 4: Semantic Scholar OA PDF (mixed OA sources)
    Tier 5: Publisher OA PDF (only legitimate open-access publisher URLs)
    Tier 6: Publisher OA HTML / landing pages
    """
    url_lower = candidate.url.lower()
    is_pmc = (
        candidate.provider == "pmc"
        or "pmc.ncbi.nlm.nih.gov" in url_lower
        or "ncbi.nlm.nih.gov/pmc" in url_lower
    )
    is_europe_pmc = candidate.provider == "europepmc" or "europepmc.org" in url_lower
    is_unpaywall_repo = candidate.provider == "unpaywall" and candidate.source_type == "repository"
    is_s2 = candidate.provider == "semanticscholar"
    is_repo = (
        _is_known_oa_repository(candidate.url)
        or "arxiv.org" in url_lower
        or is_unpaywall_repo
    )

    if is_pmc and candidate.format == "pdf":
        return (0, 0)
    if is_pmc:
        return (1, 0)
    if is_europe_pmc:
        return (1, 1)
    if is_repo and candidate.format == "pdf":
        return (2, 0)
    if is_repo:
        return (2, 1)
    if is_s2 and candidate.format == "pdf":
        return (4, 0)
    if is_s2:
        return (4, 1)
    if candidate.format == "pdf":
        return (5, 0)
    return (6, 0)


def _order_candidates(candidates: list[FullTextCandidate]) -> list[FullTextCandidate]:
    return sorted(candidates, key=_candidate_priority)


def _pmc_pdf_url_from_html(url: str) -> str | None:
    match = _PMC_ARTICLE_PATTERN.search(url)
    if match is None:
        return None
    pmc_id = match.group(1)
    normalized_id = pmc_id if pmc_id.upper().startswith("PMC") else f"PMC{pmc_id}"
    return f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized_id}/pdf/"


def _pmc_html_url_from_pmc_url(url: str) -> str | None:
    match = _PMC_ARTICLE_PATTERN.search(url)
    if match is None:
        return None
    pmc_id = match.group(1)
    normalized_id = pmc_id if pmc_id.upper().startswith("PMC") else f"PMC{pmc_id}"
    return f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized_id}/"


def _europe_pmc_url_from_pmc_html(url: str) -> str | None:
    match = _PMC_ARTICLE_PATTERN.search(url)
    if match is None:
        return None
    pmc_id = match.group(1)
    normalized_id = pmc_id if pmc_id.upper().startswith("PMC") else f"PMC{pmc_id}"
    return f"https://europepmc.org/articles/{normalized_id}"


def _expand_candidate_mirrors(
    candidates: list[FullTextCandidate],
) -> list[FullTextCandidate]:
    expanded: list[FullTextCandidate] = []
    for candidate in candidates:
        if "pmc" not in candidate.url.lower():
            expanded.append(candidate)
            continue

        match = _PMC_ARTICLE_PATTERN.search(candidate.url)
        if match is not None:
            pmc_id = match.group(1)
            normalized_id = pmc_id if pmc_id.upper().startswith("PMC") else f"PMC{pmc_id}"
            pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized_id}/pdf/"
            html_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized_id}/"
            epmc_url = f"https://europepmc.org/articles/{normalized_id}"

            if not any(c.url == pdf_url for c in expanded):
                expanded.append(
                    FullTextCandidate(
                        url=pdf_url,
                        format="pdf",
                        provider="pmc",
                        source_type="repository",
                    )
                )
            if not any(c.url == html_url for c in expanded):
                expanded.append(
                    FullTextCandidate(
                        url=html_url,
                        format="html",
                        provider="pmc",
                        source_type="repository",
                    )
                )
            if not any(c.url == epmc_url for c in expanded):
                expanded.append(
                    FullTextCandidate(
                        url=epmc_url,
                        format="html",
                        provider="europepmc",
                        source_type="repository",
                    )
                )
        else:
            expanded.append(candidate)
    return expanded


def _discover_europe_pmc_candidates(
    doi: str,
    client: httpx.Client,
) -> list[FullTextCandidate]:
    """Query Europe PMC REST API by DOI to discover PMC/Europe PMC full-text mirrors.

    Returns PMC PDF (Tier 0), PMC HTML (Tier 1), and Europe PMC HTML (Tier 1)
    candidates when the paper has a PMCID record, which indicates it is freely
    available via NIH Open Access policy. Never bypasses paywalls or anti-bot protections.
    """
    url = (
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query=DOI:{doi}&format=json"
    )
    try:
        response = client.get(url, timeout=10.0)
        if response.status_code != 200:
            return []
        data = response.json()
        results = data.get("resultList", {}).get("result", [])
        if not results:
            return []
        pmcid = results[0].get("pmcid")
        if not pmcid or not isinstance(pmcid, str):
            return []
        normalized_id = pmcid.strip()
        if not normalized_id.upper().startswith("PMC"):
            normalized_id = f"PMC{normalized_id}"
        logger.debug("Europe PMC discovery found PMCID=%s for doi=%s", normalized_id, doi)
        return [
            FullTextCandidate(
                url=f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized_id}/pdf/",
                format="pdf",
                provider="pmc",
                source_type="repository",
            ),
            FullTextCandidate(
                url=f"https://pmc.ncbi.nlm.nih.gov/articles/{normalized_id}/",
                format="html",
                provider="pmc",
                source_type="repository",
            ),
            FullTextCandidate(
                url=f"https://europepmc.org/articles/{normalized_id}",
                format="html",
                provider="europepmc",
                source_type="repository",
            ),
        ]
    except Exception as exc:
        logger.debug("Europe PMC candidate discovery failed: doi=%s reason=%s", doi, exc)
        return []


_UNPAYWALL_EMAIL = "team@sciverify.local"
_KNOWN_REPOSITORY_HOSTS = (
    "arxiv.org",
    "biorxiv.org",
    "medrxiv.org",
    "europepmc.org",
    "ncbi.nlm.nih.gov/pmc",
    "pmc.ncbi.nlm.nih.gov",
    "pubmedcentral.nih.gov",
    "escholarship.org",
    "repository.",
    "zenodo.org",
    "figshare.com",
    "osf.io",
    "ssrn.com",
    "researchgate.net",
    "academia.edu",
    "institutional",
)


def _is_repository_url(url: str) -> bool:
    """Return True if a URL appears to be from an OA repository (not a publisher)."""
    lower = url.lower()
    return any(host in lower for host in _KNOWN_REPOSITORY_HOSTS)


def _discover_unpaywall_candidates(
    doi: str,
    client: httpx.Client,
) -> list[FullTextCandidate]:
    """Query Unpaywall API for open-access PDF/HTML locations.

    Tier 2: Repository PDFs (arXiv, institutional, Zenodo, bioRxiv, etc.)
    Tier 3: Repository HTML
    Tier 5: Publisher OA PDFs (only if legitimately open access)
    Never includes paywalled or subscription-required content.
    """
    url = f"https://api.unpaywall.org/v2/{doi}?email={_UNPAYWALL_EMAIL}"
    candidates: list[FullTextCandidate] = []
    try:
        response = client.get(url, timeout=10.0)
        if response.status_code != 200:
            logger.debug("Unpaywall returned %d for doi=%s", response.status_code, doi)
            return []
        data = response.json()
        if not data.get("is_oa"):
            logger.debug("Unpaywall: doi=%s is not open-access", doi)
            return []
        oa_locations: list[dict[str, Any]] = data.get("oa_locations") or []
        for loc in oa_locations:
            if not isinstance(loc, dict):
                continue
            host_type = loc.get("host_type", "unknown")
            pdf_url = loc.get("url_for_pdf")
            landing_url = loc.get("url")

            # Only accept PDFs from Unpaywall (landing pages are too risky)
            if isinstance(pdf_url, str) and pdf_url.strip():
                source_type = "repository" if host_type == "repository" else "publisher"
                candidates.append(
                    FullTextCandidate(
                        url=pdf_url.strip(),
                        format="pdf",
                        provider="unpaywall",
                        source_type=source_type,
                    )
                )
            elif isinstance(landing_url, str) and landing_url.strip() and host_type == "repository":
                # Accept HTML landing pages only from known OA repositories
                candidates.append(
                    FullTextCandidate(
                        url=landing_url.strip(),
                        format=_format_from_url(landing_url),
                        provider="unpaywall",
                        source_type="repository",
                    )
                )
        logger.debug("Unpaywall discovery: doi=%s candidates=%d", doi, len(candidates))
        return candidates
    except Exception as exc:
        logger.debug("Unpaywall candidate discovery failed: doi=%s reason=%s", doi, exc)
        return []


def _discover_semantic_scholar_candidates(
    doi: str,
    client: httpx.Client,
) -> list[FullTextCandidate]:
    """Query Semantic Scholar for an open-access PDF URL.

    Tier 4: Semantic Scholar OA PDF (mixed OA provenance).
    Only returns PDF candidates; landing pages from S2 are not used.
    Never bypasses paywalls or access controls.
    """
    url = (
        f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
        f"?fields=openAccessPdf,isOpenAccess"
    )
    try:
        response = client.get(url, timeout=10.0)
        if response.status_code != 200:
            logger.debug("Semantic Scholar returned %d for doi=%s", response.status_code, doi)
            return []
        data = response.json()
        if not data.get("isOpenAccess"):
            return []
        oa_pdf = data.get("openAccessPdf")
        if not isinstance(oa_pdf, dict):
            return []
        pdf_url = oa_pdf.get("url")
        if not isinstance(pdf_url, str) or not pdf_url.strip():
            return []
        logger.debug("Semantic Scholar OA PDF: doi=%s url=%s", doi, pdf_url)
        return [
            FullTextCandidate(
                url=pdf_url.strip(),
                format="pdf",
                provider="semanticscholar",
                source_type="repository" if _is_repository_url(pdf_url) else "publisher",
            )
        ]
    except Exception as exc:
        logger.debug("Semantic Scholar discovery failed: doi=%s reason=%s", doi, exc)
        return []


def _fetch_openalex_work(doi: str, client: httpx.Client) -> dict[str, Any]:
    url = f"{OPENALEX_API_URL}/works/https://doi.org/{doi}"
    try:
        response = client.get(url)
    except httpx.TimeoutException as exc:
        raise PaperProviderError("OpenAlex request timed out.") from exc
    except httpx.RequestError as exc:
        raise PaperProviderError("OpenAlex request failed.") from exc

    if response.status_code == 404:
        raise PaperNotFoundError(f"Paper not found for DOI: {doi}")

    if response.status_code >= 500:
        raise PaperProviderError("OpenAlex service is unavailable.")

    if response.status_code >= 400:
        raise PaperProviderError("OpenAlex rejected the request.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise PaperProviderError("OpenAlex returned invalid JSON.") from exc

    if not isinstance(payload, dict) or not payload.get("id"):
        raise PaperProviderError("OpenAlex returned an unexpected response.")

    return payload


def _build_paper_metadata(
    citation: CitationMetadata,
    openalex_work: dict[str, Any] | None,
) -> PaperMetadata:
    abstract = None
    publication_date = None
    open_access = None
    source_url = citation.url

    if openalex_work is not None:
        abstract = _extract_openalex_abstract(openalex_work)
        publication_date = openalex_work.get("publication_date")
        if not isinstance(publication_date, str):
            publication_date = None

        open_access_info = openalex_work.get("open_access")
        if isinstance(open_access_info, dict):
            open_access = open_access_info.get("is_oa")

        primary_location = openalex_work.get("primary_location")
        if isinstance(primary_location, dict):
            landing_page = primary_location.get("landing_page_url")
            if isinstance(landing_page, str) and landing_page.strip():
                source_url = landing_page.strip()

    return PaperMetadata(
        paper_id=citation.doi,
        doi=citation.doi,
        title=citation.title,
        authors=citation.authors,
        abstract=abstract,
        journal=citation.journal,
        publisher=citation.publisher,
        publication_date=publication_date,
        year=citation.year,
        url=citation.url,
        source_url=source_url,
        open_access=open_access if isinstance(open_access, bool) else None,
        full_text_available=False,
        full_text_format=None,
        full_text_url=None,
    )


def _build_source(
    citation: CitationMetadata,
    openalex_work: dict[str, Any] | None,
) -> PaperSource:
    if openalex_work is not None:
        openalex_id = openalex_work.get("id")
        if isinstance(openalex_id, str) and openalex_id.strip():
            return PaperSource(url=openalex_id.strip(), provider="openalex")
    return PaperSource(url=citation.url, provider=citation.source)


def _extract_openalex_abstract(work: dict[str, Any]) -> str | None:
    abstract = work.get("abstract")
    if isinstance(abstract, str) and abstract.strip():
        return abstract.strip()

    inverted_index = work.get("abstract_inverted_index")
    if not isinstance(inverted_index, dict):
        return None

    max_index = -1
    for positions in inverted_index.values():
        if isinstance(positions, list) and positions:
            max_index = max(max_index, max(pos for pos in positions if isinstance(pos, int)))

    if max_index < 0:
        return None

    words = [""] * (max_index + 1)
    for word, positions in inverted_index.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and 0 <= position <= max_index:
                words[position] = word

    reconstructed = " ".join(word for word in words if word).strip()
    return reconstructed or None


__all__ = [
    "DocumentRetrievalFailure",
    "FullTextCandidate",
    "FullTextUnavailableError",
    "PaperNotFoundError",
    "PaperProviderError",
    "discover_full_text",
    "discover_full_text_candidates",
    "_discover_europe_pmc_candidates",
    "_discover_unpaywall_candidates",
    "_discover_semantic_scholar_candidates",
    "retrieve_paper",
]
