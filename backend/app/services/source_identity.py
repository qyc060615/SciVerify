"""Article identity qualification; bibliography DOIs never establish identity."""
from dataclasses import dataclass
from difflib import SequenceMatcher
from io import BytesIO
import json
import re
import unicodedata

from bs4 import BeautifulSoup
from pypdf import PdfReader
from app.utils.doi import normalize_doi

_DOI = re.compile(r"10\.\d{4,9}/[^\s<>\"]+", re.I)
_BODY = re.compile(r"(?im)^\s*(?:\d+(?:\.\d+)*[.)]?\s*)?(?:introduction|background|(?:materials and )?methods|results|discussion|conclusions?)\b")
_BOUNDARY = re.compile(r"(?im)^\s*(?:\d+(?:\.\d+)*[.)]?\s*)?(?:abstract|introduction|background|methods|results|discussion|references|bibliography)\b")


@dataclass(frozen=True)
class SourceIdentity:
    status: str
    reason: str


def _words(value):
    return ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', value).casefold()))


def _doi(value):
    if not isinstance(value, str):
        return None
    match = _DOI.search(value)
    if not match:
        return None
    try:
        return normalize_doi(match.group().rstrip(').,;]}'))
    except ValueError:
        return None


def _title_relation(expected, actual):
    a, b = _words((expected or '')[:2000]), _words((actual or '')[:2000])
    if not a or not b:
        return 'uncertain'
    if a == b or SequenceMatcher(None, a, b).ratio() >= .9:
        return 'match'
    # Subtitle/punctuation variants are compatible, generic/short titles inconclusive.
    if min(len(a.split()), len(b.split())) >= 6 and (a in b or b in a):
        return 'match'
    if min(len(a.split()), len(b.split())) < 4:
        return 'uncertain'
    overlap = len(set(a.split()) & set(b.split())) / min(len(set(a.split())), len(set(b.split())))
    return 'conflict' if overlap < .4 else 'uncertain'


def _structured_articles(value):
    if isinstance(value, list):
        for item in value:
            yield from _structured_articles(item)
    elif isinstance(value, dict):
        types = value.get('@type', [])
        types = [types] if isinstance(types, str) else types
        if isinstance(types, list) and any(t in {'ScholarlyArticle', 'MedicalScholarlyArticle', 'Article'} for t in types):
            yield value
        # Do not descend into citations/references or arbitrary nested article records.
        yield from _structured_articles(value.get('@graph', []))
        main = value.get('mainEntity')
        if isinstance(main, (dict, list)):
            yield from _structured_articles(main)


def qualify_source_identity(content, doc_format, paper):
    dois, titles = set(), []
    if doc_format == 'html':
        soup = BeautifulSoup(content, 'html.parser')
        head = soup.head or soup
        for node in head.select('.references, #references, .ref-list, [role="doc-bibliography"]'):
            node.decompose()
        for meta in head.find_all('meta'):
            name = str(meta.get('name', '')).casefold()
            value = str(meta.get('content', ''))
            if name in {'citation_doi', 'dc.identifier', 'dc.identifier.doi', 'dcterms.identifier'}:
                doi = _doi(value)
                if doi:
                    dois.add(doi)
            elif name in {'citation_title', 'dc.title', 'dcterms.title'}:
                titles.append(value)
        for script in head.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.get_text())
            except (ValueError, TypeError):
                continue
            for article in _structured_articles(data):
                identifiers = article.get('identifier', [])
                identifiers = identifiers if isinstance(identifiers, list) else [identifiers]
                for value in [article.get('doi'), *identifiers]:
                    if isinstance(value, dict):
                        prop = str(value.get('propertyID', '')).casefold()
                        value = value.get('value') if prop in {'doi', 'https://doi.org', 'http://doi.org'} else None
                    doi = _doi(value)
                    if doi:
                        dois.add(doi)
                title = article.get('headline') or article.get('name')
                if isinstance(title, str):
                    titles.append(title)
    elif doc_format == 'pdf':
        try:
            reader = PdfReader(BytesIO(content))
            metadata = reader.metadata or {}
            pages = [page.extract_text() or '' for page in reader.pages]
            text = '\n'.join(pages)
            if (len(pages) == 1
                    and re.search(r'(?im)^\s*abstract\s*:?[ \t]*$', text) and not _BODY.search(text)):
                return SourceIdentity('conflict', 'ABSTRACT_ONLY_PDF')
            # Apply the same direct-document checks before accepting a cached
            # artifact, so a known wrong cover also triggers normal remote fallback.
            from types import SimpleNamespace
            from app.services.source_confirmation import inspect_confirmation
            proof = inspect_confirmation(content, 'pdf', SimpleNamespace(title=paper.title,
                authors=tuple(paper.authors), year=paper.year, raw_text=paper.title or ''))
            if proof['status'] == 'conflict':
                return SourceIdentity('conflict', proof['reason'])
            if proof['status'] == 'confirmed' and paper.title:
                titles.append(paper.title)
            header = _BOUNDARY.split(pages[0] if pages else '')[0][:4000]
            # Some preprint footers extract the adjacent label without a space:
            # "...20245175doi:". Separate only that numeric-DOI/label boundary;
            # never fuzzy-match a different DOI or use bibliography identifiers.
            header = re.sub(r'(?<=\d)doi:(?=\s|$)', ' doi:', header, flags=re.I)
            for value in [header, *(str(metadata.get(k, '')) for k in ('/DOI', '/doi', '/Subject', '/Keywords'))]:
                dois.update(filter(None, (_doi(m.group()) for m in _DOI.finditer(value))))
            title = metadata.get('/Title')
            if isinstance(title, str) and not re.search(r'(?i)\.docx?$|microsoft|untitled|^document$', title):
                titles.append(title)
            # Exact title in the pre-body header is a useful DOI-free fallback.
            if _words(paper.title or '') and _words(paper.title) in _words(header):
                titles.append(paper.title)
        except Exception:
            # Transport/parser owns malformed PDF rejection. Do not turn absence into conflict.
            return SourceIdentity('uncertain', 'PDF_IDENTITY_UNAVAILABLE')
    target = normalize_doi(paper.doi)
    relations = [_title_relation(paper.title, title) for title in titles]
    if dois and dois != {target}:
        # A matching document title can explain an arXiv/formal-publication DOI
        # difference, but it cannot establish an exact identity or version.
        if ('match' in relations and 'conflict' not in relations
                and (target.startswith('10.48550/arxiv.') or all(d.startswith('10.48550/arxiv.') for d in dois))):
            return SourceIdentity('uncertain', 'RELATED_VERSION_DOI_UNCONFIRMED')
        return SourceIdentity('conflict', 'ARTICLE_DOI_CONFLICT')
    if 'conflict' in relations:
        return SourceIdentity('conflict', 'ARTICLE_TITLE_CONFLICT')
    if dois == {target}:
        return SourceIdentity('confirmed', 'ARTICLE_DOI_MATCH')
    if 'match' in relations:
        return SourceIdentity('confirmed', 'ARTICLE_TITLE_MATCH')
    # Preserve the bounded legal OA candidate policy when no authoritative identity
    # is exposed. Explicit uncertainty is retained in response/evidence provenance.
    return SourceIdentity('uncertain', 'ARTICLE_IDENTITY_INSUFFICIENT')
