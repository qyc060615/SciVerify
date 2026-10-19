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


def _subjects(title):
    # Product identifiers are hard constraints, not a fuzzy title contribution.
    return set(re.findall(r'\b(?:[a-z]{2,}\d{2,}[a-z]*\d*|[a-z]+-\d{3,}[a-z]*)\b', _normal(title)))


def _title_terms(title):
    text = _normal(title)
    text = re.sub(r'\b(?:elicits?|induces?|th1)\b', ' ', text)
    return set(re.findall(r'[a-z0-9]+', text)) - {'a', 'an', 'the', 'of', 'and', 'in', 'to', 'type'}


def _population(title):
    if re.search(r'\b(?:mice|mouse|murine|non-human|nonhuman|macaques?|monkeys?)\b', title, re.I):
        return 'animal'
    if re.search(r'\b(?:humans?|adults?|patients?|participants?)\b', title, re.I):
        return 'human'
    return None


def probable_candidate(reference):
    resolution = reference.resolution
    if not resolution or not re.search(r'\bpreprint\b', reference.raw_text, re.I):
        return None
    eligible = {}
    original = {_surname(a) for a in reference.authors if _surname(a)}
    for c in resolution.candidates:
        if c.publication_type != 'preprint' or not original or c.rejection_reason not in {
                None, 'TITLE_MISMATCH', 'INSUFFICIENT_IDENTITY_EVIDENCE', 'VERSION_UNCERTAIN'}:
            continue
        found = {_surname(a) for a in c.authors}
        if len(original & found) < 2 or _surname(reference.authors[0]) not in found:
            continue
        if _subjects(reference.title or '') != _subjects(c.title):
            continue
        if _population(reference.title or '') and _population(c.title) != _population(reference.title):
            continue
        a, b = _title_terms(reference.title or ''), _title_terms(c.title)
        if len(a) < 6 or len(a & b) / max(len(a), len(b), 1) < .8:
            continue
        if reference.year and c.years and min(abs(reference.year - y) for y in c.years) > 1:
            continue
        eligible[c.doi] = c
    return next(iter(eligible.values())) if len(eligible) == 1 else None


def review_version(reference, response):
    candidate = probable_candidate(reference)
    if candidate is None or response.paper.doi != candidate.doi:
        return None
    if response.source.identity_status != 'confirmed':
        return None
    if _subjects(response.paper.title or '') != _subjects(reference.title or ''):
        return None
    authors = {_surname(a) for a in response.paper.authors}
    if len(authors & {_surname(a) for a in reference.authors}) < 2:
        return None
    body = _normal(' '.join(s.text for s in response.sections
                            if not s.section_name.lower().startswith(('references', 'bibliography'))))
    terms = _title_terms(reference.title or '')
    body_terms = set(re.findall(r'[a-z0-9]+', body))
    # Full-text subject AND core finding anchors, not only a search title/abstract.
    if len(terms & body_terms) / max(len(terms), 1) < .8 or len(body) < 3000:
        return None
    if not re.search(r'participants|subjects|healthy (?:adults|men|volunteers)|clinical trial', body):
        return None
    if not re.search(r'\b(?:results|findings|responses|elicited|induced)\b', body):
        return None
    warnings = ['RETITLED_PREPRINT', 'VERSION_RELATIONSHIP_UNCONFIRMED']
    if not reference.year:
        warnings.append('ORIGINAL_CITATION_DATE_UNKNOWN')
    elif response.paper.year and response.paper.year > reference.year:
        warnings.append('RETRIEVED_VERSION_POSTDATES_CITATION')
    return {
        'identity': 'PROBABLE_SAME_WORK',
        'identity_confidence': min(.9, candidate.match_confidence),
        'match_evidence': ('FIRST_AUTHOR_AND_MULTIPLE_AUTHORS_MATCH', 'PRODUCT_IDENTIFIERS_MATCH',
                           'RESEARCH_SUBJECT_AND_CORE_FINDINGS_IN_FULL_TEXT',
                           'HUMAN_STUDY_POPULATION_IN_FULL_TEXT', 'MATCHED_DOI_CONFIRMED_IN_SOURCE',
                           'PREPRINT_PUBLICATION_TYPE', 'PUBLICATION_DATE:' + str(response.paper.publication_date)),
        'warnings': tuple(warnings),
    }
