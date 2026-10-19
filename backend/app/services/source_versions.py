"""Conservative retitled-preprint review, separate from exact DOI resolution.

Candidate metadata permits acquisition; only accepted full text can establish a
probable relationship. This never upgrades a probable version to exact identity.
"""
import re
from datetime import datetime
from io import BytesIO
from pypdf import PdfReader
from bs4 import BeautifulSoup

from app.services.reference_resolver import _surname, _normal


def document_version_date(content, doc_format):
    """Use this downloaded version's own date, never a related journal's date."""
    if doc_format == 'pdf':
        try:
            reader = PdfReader(BytesIO(content))
            text = (reader.pages[0].extract_text() or '') if reader.pages else ''
        except Exception:
            # Optional metadata extraction cannot replace the parser's acceptance
            # decision or break legacy parser/retriever injection contracts.
            return None
        match = re.search(r'this version posted\s+([A-Za-z]+\s+\d{1,2},?\s+20\d{2})', text, re.I)
        if match:
            try:
                return datetime.strptime(re.sub(r',\s*', ' ', match.group(1)), '%B %d %Y').date().isoformat()
            except ValueError:
                return None
    elif doc_format == 'html':
        soup = BeautifulSoup(content, 'html.parser')
        node = soup.select_one('meta[name="citation_publication_date"]')
        if node:
            match = re.match(r'(20\d{2})[-/](\d{1,2})[-/](\d{1,2})', str(node.get('content', '')))
            if match:
                try:
                    return datetime(*map(int, match.groups())).date().isoformat()
                except ValueError:
                    return None
    return None


def document_title(content, doc_format, expected=None):
    """Document-supplied title only; provider metadata is not a retrieved title."""
    if doc_format == 'html':
        soup = BeautifulSoup(content, 'html.parser')
        node = soup.select_one('meta[name="citation_title"]')
        if node and node.get('content'):
            return str(node['content']).strip()
        node = soup.select_one('article h1, main h1, h1')
        return node.get_text(' ', strip=True) if node else None
    try:
        reader = PdfReader(BytesIO(content))
        title = str((reader.metadata or {}).get('/Title', '')).strip()
        from app.services.source_identity import _words, _title_relation
        if (len(title) >= 12 and not re.search(r'(?i)\.docx?$|microsoft|untitled|^document$', title)
                and (not expected or _title_relation(expected, title) == 'match')):
            return title
        header = reader.pages[0].extract_text() or '' if reader.pages else ''
        if expected and _words(expected) in _words(header):
            return expected  # Verified in the downloaded page, not inferred from the provider.
    except Exception:
        pass
    return None


def _title_terms(title):
    # Function words only: no discipline-specific synonyms or required findings.
    return set(re.findall(r"[a-z0-9]+", _normal(title))) - {
        'a', 'an', 'the', 'of', 'and', 'in', 'to', 'for', 'with', 'on', 'by', 'from', 'using'}


def identity_conflict(expected, actual):
    """Comparable model identifiers and explicit changed object phrases.

    A missing identifier is unknown. Distinct identifiers in the same lexical
    family are contradictory; adding an identifier is not automatically conflict.
    """
    def identifiers(title):
        values = re.findall(r"\b[a-z][a-z0-9-]*\d[a-z0-9-]*\b", _normal(title))
        groups = {}
        for value in values:
            groups.setdefault(re.sub(r"\d+", '#', value), set()).add(value)
        return groups
    a, b = identifiers(expected), identifiers(actual)
    if any(a[k].isdisjoint(b[k]) for k in a.keys() & b.keys()):
        return 'KEY_IDENTIFIER_CONFLICT'
    # Compare explicitly stated objects, irrespective of the field of research.
    # Restrict to short terminal complements to avoid treating whole findings as entities.
    def objects(title):
        m = re.search(r"\b(?:in|on|for|using)\s+([^:;.]+)$", _normal(title))
        terms = _title_terms(m.group(1)) if m else set()
        return terms if 0 < len(terms) <= 3 else set()
    a, b = objects(expected), objects(actual)
    if a and b and a.isdisjoint(b):
        return 'EXPLICIT_OBJECT_CONFLICT'
    return None


def candidate_evidence(reference, candidate):
    if identity_conflict(reference.title or '', candidate.title):
        return None
    a, b = _title_terms(reference.title or ''), _title_terms(candidate.title)
    shared = a & b
    if len(shared) < 3 or len(shared) / max(len(a), len(b), 1) < .55:
        return None
    original = {_surname(n) for n in reference.authors if _surname(n)}
    found = {_surname(n) for n in candidate.authors if _surname(n)}
    if original and found and not original & found:
        return None
    evidence = ['RELATED_TITLE_TERMS']
    if original & found:
        evidence.append('AUTHOR_OVERLAP')
        if _surname(reference.authors[0]) in found:
            evidence.append('FIRST_AUTHOR_MATCH')
    else:
        evidence.append('AUTHORS_UNKNOWN')
    if reference.year and candidate.years:
        if min(abs(reference.year - y) for y in candidate.years) <= 1:
            evidence.append('COMPATIBLE_YEAR')
        else:
            evidence.append('VERSION_DATE_DIFFERS')
    else:
        evidence.append('YEAR_UNKNOWN')
    identifiers = set(re.findall(r"\b[a-z][a-z0-9-]*\d[a-z0-9-]*\b", _normal(reference.title or '')))
    if identifiers & set(re.findall(r"\b[a-z][a-z0-9-]*\d[a-z0-9-]*\b", _normal(candidate.title))):
        evidence.append('SHARED_KEY_IDENTIFIER')
    if candidate.relations:
        evidence.append('PROVIDER_VERSION_RELATION_REQUIRES_REVIEW')
    # Title similarity alone never establishes an acquisition relationship.
    if not original & found and 'SHARED_KEY_IDENTIFIER' not in evidence:
        return None
    return tuple(evidence)


def probable_candidate(reference):
    resolution = reference.resolution
    if not resolution or not re.search(r'\b(?:preprint|arxiv|biorxiv|medrxiv)\b',
                                        reference.raw_text + ' ' + (reference.journal or ''), re.I):
        return None
    eligible = {}
    for c in resolution.candidates:
        if c.publication_type != 'preprint':
            continue
        if candidate_evidence(reference, c):
            eligible.setdefault(c.doi, c)
    return next(iter(eligible.values())) if len(eligible) == 1 else None


def review_version(reference, response, *, citing_publication_date=None):
    candidate = probable_candidate(reference)
    if candidate is None or response.paper.doi != candidate.doi:
        return None
    if response.source.identity_status == 'conflict':
        return {'identity': 'IDENTITY_CONFLICT', 'match_evidence': ('CANDIDATE_SOURCE_CONFLICT',), 'warnings': ()}
    conflict = identity_conflict(reference.title or '', response.paper.title or '')
    if conflict:
        return {'identity': 'IDENTITY_CONFLICT', 'match_evidence': (conflict,), 'warnings': ()}
    evidence = list(candidate_evidence(reference, candidate) or ())
    original = {_surname(a) for a in reference.authors if _surname(a)}
    actual = {_surname(a) for a in response.paper.authors if _surname(a)}
    if original and actual and not original & actual:
        return {'identity': 'IDENTITY_CONFLICT', 'match_evidence': ('RETRIEVED_AUTHORS_CONFLICT',), 'warnings': ()}
    body = _normal(' '.join(s.text for s in response.sections
                            if not s.section_name.lower().startswith(('references', 'bibliography', 'abstract'))))
    terms = _title_terms(reference.title or '')
    body_terms = set(re.findall(r'[a-z0-9]+', body))
    if len(body) < 1000 or len(terms & body_terms) / max(len(terms), 1) < .55:
        return None
    evidence.append('RELATED_TERMS_IN_SUBSTANTIVE_FULL_TEXT')
    supported = (bool(original & actual) and response.source.identity_status == 'confirmed'
                 and 'VERSION_DATE_DIFFERS' not in evidence)
    identity = 'PROBABLE_SAME_WORK' if supported else 'IDENTITY_UNCERTAIN'
    warnings = ['VERSION_RELATIONSHIP_UNCONFIRMED']
    if _normal(reference.title or '') != _normal(candidate.title):
        warnings.insert(0, 'RETITLED_PREPRINT')
    if not original or not actual:
        warnings.append('AUTHORS_UNCONFIRMED')
    if identity == 'IDENTITY_UNCERTAIN':
        warnings.append('SOURCE_IDENTITY_UNCERTAIN')
    if not reference.year:
        warnings.append('ORIGINAL_CITATION_DATE_UNKNOWN')
    elif response.paper.publication_date and response.paper.publication_date[:4].isdigit() and int(response.paper.publication_date[:4]) > reference.year:
        warnings.append('RETRIEVED_VERSION_POSTDATES_CITATION')
    if citing_publication_date and response.paper.publication_date:
        try:
            if datetime.fromisoformat(response.paper.publication_date) > datetime.fromisoformat(citing_publication_date):
                warnings.append('RETRIEVED_VERSION_POSTDATES_CITING_MANUSCRIPT')
        except ValueError:
            warnings.append('VERSION_DATE_COMPARISON_UNAVAILABLE')
    if response.source.identity_status == 'confirmed':
        evidence.append('CANDIDATE_IDENTITY_CONFIRMED_IN_SOURCE')
    return {'identity': identity, 'identity_confidence': min(.9, candidate.match_confidence),
            'match_evidence': tuple(evidence), 'warnings': tuple(warnings)}
