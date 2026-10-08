"""Conservative HTML qualification and direct, nonrecursive full-text links.

Transport validation and PDF parsing remain owned by the existing services.
An article wrapper, metadata, or text length alone never establishes full text.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from app.services.document_retriever import is_interstitial_content, is_paywall_content

DocumentFormat = Literal["pdf", "html"]
MAX_DIRECT_LINKS = 3
_ARTICLE_ROOTS = (
    '[itemprop="articleBody"]', '.article-body', '#article-body', '.article-text',
    '#article-container-1', '#mc', '.full-text', '.fulltext', 'article',
)
_REMOVE = (
    'script', 'style', 'noscript', 'nav', 'header', 'footer', 'aside', 'form',
    '.abstract', '#abstract', '#abstract-section', '[role="doc-abstract"]',
    '[itemprop="abstract"]', '.toc', '.table-of-contents', '[role="doc-toc"]',
    '.metadata', '.item-metadata', '.sidebar',
)
_BODY_SECTIONS = (
    ('introduction', r'^(?:introduction|background)\b'),
    ('methods', r'^(?:(?:materials?\s+(?:and|&)\s+)?methods?|methodology|experimental(?:\s+procedures)?|study\s+design)\b'),
    ('results', r'^(?:results|findings)\b'),
    ('discussion', r'^discussion\b'),
    ('conclusion', r'^conclusions?\b'),
)
_HEADINGS = {f'h{i}' for i in range(1, 7)}
_SUPPLEMENT = re.compile(r'supplement|supporting[\s_-]+(?:information|material)|appendix', re.I)


def is_full_text_document(content: bytes, doc_format: DocumentFormat) -> bool:
    if doc_format == 'pdf':
        return True  # Existing validity/parsing checks run before this helper.
    if doc_format != 'html' or is_interstitial_content(content) or is_paywall_content(content):
        return False
    soup = BeautifulSoup(content, 'html.parser')
    has_fulltext_metadata = any(
        str(meta.get('name', '')).casefold() == 'citation_fulltext_html_url'
        and bool(meta.get('content'))
        for meta in soup.find_all('meta')
    )
    for selector in _REMOVE:
        for node in soup.select(selector):
            node.decompose()

    roots = [root for selector in _ARTICLE_ROOTS for root in soup.select(selector)]
    # Strong section diversity can also qualify plain scholarly HTML without a wrapper.
    if not roots:
        roots = [soup.body or soup]
    for root in roots:
        groups: dict[str, list[str]] = {}
        current: str | None = None
        section_level: int | None = None
        abstract_level: int | None = None
        for node in root.find_all([*_HEADINGS, 'p']):
            if node.name in _HEADINGS:
                level = int(node.name[1])
                heading = re.sub(r'^(?:\d+(?:\.\d+)*|[ivx]+)[.)\s]+', '', node.get_text(' ', strip=True).casefold())
                if heading.startswith('abstract'):
                    abstract_level, current, section_level = level, None, None
                    continue
                if abstract_level is not None:
                    if level > abstract_level:
                        continue
                    abstract_level = None
                category = next((name for name, pattern in _BODY_SECTIONS if re.match(pattern, heading)), None)
                if category is not None:
                    current, section_level = category, level
                elif section_level is None or level <= section_level:
                    current, section_level = None, None
                # Unrecognized subheadings remain within their canonical parent section.
            elif current is not None and abstract_level is None:
                text = node.get_text(' ', strip=True)
                # Paragraph prose, not table-of-contents/navigation labels.
                if len(text) >= 40:
                    groups.setdefault(current, []).append(text)
        substantial = {name: parts for name, parts in groups.items() if sum(map(len, parts)) >= 100}
        volume = sum(len(text) for parts in substantial.values() for text in parts)
        structural_root = any(root is candidate for candidate in soup.select(','.join(_ARTICLE_ROOTS)))
        if (len(substantial) >= 2 and volume >= 400
                and (structural_root or has_fulltext_metadata or len(substantial) >= 3)):
            return True
    return False


@dataclass(frozen=True)
class DirectFullTextLink:
    url: str
    format: DocumentFormat


def normalize_candidate_url(url: str) -> str | None:
    """Remove fragments; permit HTTP(S) document URLs, not credentials/local targets."""
    if not isinstance(url, str) or any(ord(char) < 32 for char in url) or '\\' in url:
        return None
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        _ = parts.port  # Reject malformed ports.
        if (parts.scheme.lower() not in {'http', 'https'} or not host
                or parts.username is not None or parts.password is not None):
            return None
        host = host.casefold().rstrip('.')
        if host == 'localhost' or host.endswith(('.localhost', '.local')) or '%' in host:
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', parts.query, ''))
    except ValueError:
        return None


def discover_direct_full_text_links(content: bytes, source_url: str) -> list[DirectFullTextLink]:
    """Inspect only this rejected page. Callers must never expand its follow-ups."""
    if is_interstitial_content(content) or is_paywall_content(content):
        return []
    soup = BeautifulSoup(content, 'html.parser')
    found: dict[str, DirectFullTextLink] = {}
    base = normalize_candidate_url(source_url)

    def add(href: str, doc_format: DocumentFormat) -> None:
        if not isinstance(href, str) or not href.strip() or _SUPPLEMENT.search(href):
            return
        try:
            url = normalize_candidate_url(urljoin(source_url, href.strip()))
        except ValueError:
            return
        if url and url != base and (url not in found or doc_format == 'pdf'):
            found[url] = DirectFullTextLink(url, doc_format)

    for meta in soup.find_all('meta'):
        name = str(meta.get('name', '')).casefold()
        if name == 'citation_pdf_url':
            add(meta.get('content', ''), 'pdf')
        elif name == 'citation_fulltext_html_url':
            add(meta.get('content', ''), 'html')
    # Never follow navigation, bibliographic reference or supplementary links.
    for node in soup.select('nav, header, footer, aside, .references, #references, .ref-list'):
        node.decompose()
    for link in soup.find_all(['link', 'a'], href=True):
        href = link['href']
        label = ' '.join([link.get_text(' ', strip=True), str(link.get('title', '')), str(link.get('aria-label', ''))])
        if _SUPPLEMENT.search(label):
            continue
        mime = str(link.get('type', '')).split(';')[0].casefold()
        try:
            pdf_path = urlsplit(href).path.casefold().endswith('.pdf')
        except (ValueError, TypeError):
            continue
        if mime == 'application/pdf' or pdf_path or re.search(r'\bpdf\b', label, re.I):
            add(href, 'pdf')
        elif re.search(r'\b(?:view|read|open)\s+(?:the\s+)?full[ -]?text\b|\bfull[ -]?text\s*\(?html\)?', label, re.I):
            add(href, 'html')
    # Prefer PDF even if HTML metadata occurred first. Bound all exposed targets.
    return sorted(found.values(), key=lambda link: link.format != 'pdf')[:MAX_DIRECT_LINKS]
