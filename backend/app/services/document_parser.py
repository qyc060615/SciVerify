from __future__ import annotations

import re
from io import BytesIO
from typing import Literal

from bs4 import BeautifulSoup, Tag
from pypdf import PdfReader

from app.schemas.paper import DocumentSection
from app.utils.evidence_text import normalize_evidence_text
from app.utils.text_cleaner import clean_section_text

DocumentFormat = Literal["pdf", "html"]

KNOWN_SECTIONS = {
    "abstract",
    "introduction",
    "background",
    "methods",
    "materials and methods",
    "methodology",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
    "limitations",
    "references",
    "acknowledgments",
    "acknowledgements",
}

SECTION_HEADING_PATTERN = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 ,/&-]{0,60})$"
)

_CHROME_SECTION_NAMES = {
    "permalink",
    "search",
    "search ncbi",
    "primary site navigation",
    "journal list",
    "user guide",
    "actions",
    "navigation",
    "menu",
    "footer",
    "cookie",
    "cookies",
    "related information",
    "cited by other articles",
    "links to ncbi databases",
}

_REPOSITORY_ROOT_SELECTORS = (
    "#mc",
    "#main-content",
    "article",
    "#article-container-1",
    ".article-page",
    ".article-body",
)

_REPOSITORY_REMOVE_SELECTORS = (
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "form",
    "#ncbi-header",
    "#ncbi-footer",
    ".usa-banner",
    ".permalink",
    "#article-header",
    ".sidebar",
    ".journal-actions",
    ".navigation",
    ".breadcrumb",
    ".article-glossary",
)


class DocumentParseError(Exception):
    """Raised when a document cannot be parsed."""

    def __init__(self, message: str, *, reason: str = "parse_error") -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason


def parse_document(
    content: bytes,
    doc_format: DocumentFormat,
    text: str | None = None,
) -> list[DocumentSection]:
    """Parse a PDF or HTML document into ordered sections."""
    if doc_format == "pdf":
        return parse_pdf(content)
    if doc_format == "html":
        return parse_html(text or content.decode("utf-8", errors="replace"))
    raise DocumentParseError(
        f"Unsupported document format: {doc_format}",
        reason="unsupported_format",
    )


def parse_pdf(content: bytes) -> list[DocumentSection]:
    if not content:
        raise DocumentParseError(
            "PDF document is empty.",
            reason="pdf_empty",
        )

    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise DocumentParseError(
            "Failed to read PDF document.",
            reason="pdf_read_error",
        ) from exc

    page_texts: list[str] = []
    for page in reader.pages:
        try:
            extracted = page.extract_text() or ""
        except Exception as exc:
            raise DocumentParseError(
                "Failed to extract text from PDF pages.",
                reason="pdf_extract_error",
            ) from exc
        if extracted.strip():
            page_texts.append(extracted)

    if not page_texts:
        raise DocumentParseError(
            "PDF document contains no extractable text.",
            reason="pdf_no_text",
        )

    combined = "\n\n".join(page_texts)
    sections = _split_text_into_sections(combined)
    if sections:
        return sections

    cleaned = clean_section_text(combined)
    return [
        DocumentSection(
            section_name="Body",
            text=cleaned,
            order=0,
        )
    ]


def parse_html(html: str) -> list[DocumentSection]:
    if not html or not html.strip():
        raise DocumentParseError(
            "HTML document is empty.",
            reason="html_empty",
        )

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        raise DocumentParseError(
            "Failed to parse HTML document.",
            reason="html_parse_error",
        ) from exc

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    is_repository = _is_repository_article_html(html, soup)
    root = _find_repository_article_root(soup) if is_repository else None
    if root is None:
        root = soup.body if isinstance(soup.body, Tag) else soup

    sections = _extract_sections_from_root(root, repository_mode=is_repository)
    if sections:
        return sections

    fallback_text = clean_section_text(root.get_text("\n", strip=True))
    if not fallback_text:
        raise DocumentParseError(
            "HTML document contains no extractable text.",
            reason="html_no_text",
        )

    return [DocumentSection(section_name="Body", text=fallback_text, order=0)]


def _is_repository_article_html(html: str, soup: BeautifulSoup) -> bool:
    lowered = html.lower()
    if "pmc.ncbi.nlm.nih.gov" in lowered or "ncbi.nlm.nih.gov/pmc" in lowered:
        return True
    if "europepmc.org" in lowered:
        return True

    meta = soup.find("meta", attrs={"name": "ncbi_db"})
    return isinstance(meta, Tag) and meta.get("content", "").lower() == "pmc"


def _find_repository_article_root(soup: BeautifulSoup) -> Tag | None:
    for selector in _REPOSITORY_ROOT_SELECTORS:
        match = soup.select_one(selector)
        if isinstance(match, Tag):
            root = match
            break
    else:
        root = soup.body if isinstance(soup.body, Tag) else soup

    if not isinstance(root, Tag):
        return None

    for selector in _REPOSITORY_REMOVE_SELECTORS:
        for element in root.select(selector):
            element.decompose()

    return root


def _extract_sections_from_root(root: Tag, *, repository_mode: bool) -> list[DocumentSection]:
    sections: list[DocumentSection] = []
    current_name = "Body"
    current_parts: list[str] = []
    order = 0
    seen_section_text: set[str] = set()

    def flush_section() -> None:
        nonlocal order
        text = clean_section_text("\n\n".join(current_parts))
        if not text:
            current_parts.clear()
            return

        normalized = normalize_evidence_text(text)
        if normalized in seen_section_text:
            current_parts.clear()
            return

        seen_section_text.add(normalized)
        sections.append(
            DocumentSection(
                section_name=current_name,
                text=text,
                order=order,
            )
        )
        order += 1
        current_parts.clear()

    block_tags = ["h1", "h2", "h3", "h4", "p", "li"]
    if not repository_mode:
        block_tags.extend(["section", "article"])

    skip_section = False

    for element in root.find_all(block_tags):
        if _is_chrome_element(element):
            continue

        name = element.name
        if name in {"h1", "h2", "h3", "h4"}:
            heading = element.get_text(" ", strip=True)
            if heading and _is_chrome_heading(heading):
                flush_section()
                skip_section = True
                continue
            if heading:
                flush_section()
                skip_section = False
                current_name = _normalize_section_name(heading)
            continue

        if skip_section:
            continue

        text = element.get_text("\n", strip=True)
        if text and not _is_chrome_text(text):
            current_parts.append(text)

    flush_section()
    return sections


def _is_chrome_element(element: Tag) -> bool:
    for parent in element.parents:
        if not isinstance(parent, Tag):
            continue
        parent_id = (parent.get("id") or "").lower()
        parent_class = " ".join(parent.get("class") or []).lower()
        if any(token in parent_id for token in ("header", "footer", "nav", "menu", "sidebar")):
            return True
        if any(token in parent_class for token in ("header", "footer", "nav", "menu", "sidebar", "permalink")):
            return True
    return False


def _is_chrome_heading(heading: str) -> bool:
    normalized = re.sub(r"\s+", " ", heading.strip()).casefold()
    if normalized in _CHROME_SECTION_NAMES:
        return True
    return normalized.startswith("search ") or normalized.endswith(" navigation")


def _is_chrome_text(text: str) -> bool:
    normalized = normalize_evidence_text(text)
    if not normalized:
        return True
    if normalized in _CHROME_SECTION_NAMES:
        return True
    chrome_prefixes = (
        "checking your browser",
        "search ncbi",
        "primary site navigation",
        "logged in as",
    )
    return any(normalized.startswith(prefix) for prefix in chrome_prefixes)


def _split_text_into_sections(text: str) -> list[DocumentSection]:
    lines = text.splitlines()
    sections: list[DocumentSection] = []
    current_name = "Body"
    current_lines: list[str] = []
    order = 0

    def flush_section() -> None:
        nonlocal order
        section_text = clean_section_text("\n".join(current_lines))
        if section_text:
            sections.append(
                DocumentSection(
                    section_name=current_name,
                    text=section_text,
                    order=order,
                )
            )
            order += 1
        current_lines.clear()

    for line in lines:
        candidate = line.strip()
        if _looks_like_section_heading(candidate):
            flush_section()
            current_name = _normalize_section_name(candidate)
            continue
        current_lines.append(line)

    flush_section()
    return sections


def _looks_like_section_heading(line: str) -> bool:
    if not line or len(line) > 80:
        return False
    if not SECTION_HEADING_PATTERN.match(line):
        return False
    normalized = _normalize_section_name(line).lower()
    if normalized in KNOWN_SECTIONS:
        return True
    words = normalized.split()
    return len(words) <= 6 and normalized.replace(" ", "").isalpha()


def _normalize_section_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip())
    if not cleaned:
        return "Unknown"
    lower = cleaned.lower()
    if lower in KNOWN_SECTIONS:
        return cleaned.title() if lower == "abstract" else cleaned
    if _is_chrome_heading(cleaned):
        return "Body"
    return cleaned
