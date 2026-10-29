"""Ranked acquisition opportunities, separate from bibliographic confirmation."""
import re
from app.researchguard.source_locator import SourceLocator

MAX_REFERENCE_ATTEMPTS = 4


def citation_arxiv(raw):
    match = re.search(r'(?:arxiv\s*:\s*|abs/|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})(v\d+)?', raw, re.I)
    return ''.join(filter(None, match.groups())) if match else None


def citation_title(reference):
    """A search hint only; never overwrite the parsed citation fields."""
    if reference.title:
        return reference.title
    parts = re.split(r'\.\s+', reference.raw_text)
    for part in parts[1:]:
        if len(part.strip()) >= 12 and not re.match(r'(?i)arxiv|CoRR|https?://|\d{4}', part.strip()):
            return part.strip().rstrip('.')[:2000]
    return None


def reference_candidates(reference):
    from app.services.reference_resolver import discover_url
    records, seen = [], set()
    def add(kind, value, priority, provider, title=None, authors=(), years=(), evidence=(), diagnostics=(), urls=()):
        if not value:
            return
        try:
            locator = SourceLocator(kind=kind, value=value)
            key = locator.key
            invalid = None
        except ValueError:
            locator, key, invalid = None, kind + ':' + value, 'SOURCE_IDENTITY_OR_URL_INVALID'
        if key in seen:
            existing = next(r for r in records if r['_key'] == key)
            existing['urls'] = list(dict.fromkeys((*existing['urls'], *urls)))
            return
        seen.add(key)
        records.append(dict(_key=key, locator=locator.model_dump() if locator else None,
            doi=locator.value if locator and kind == 'doi' else None,
            url=value if kind == 'url' else 'https://doi.org/' + value,
            urls=list(urls), title=title or citation_title(reference), authors=list(authors), years=list(years),
            provider=provider, priority=priority, evidence=list(evidence), diagnostics=list(diagnostics),
            state='rejected' if invalid else 'candidate_found', reason=invalid,
            attempted=False, full_text_obtained=False, raw_content_sha256=None))
    resolution = reference.resolution
    original = resolution.original_doi if resolution else reference.doi
    if original:
        add('doi', original, 0, 'original', authors=reference.authors)
    arxiv = citation_arxiv(reference.raw_text)
    if arxiv:
        add('doi', '10.48550/arxiv.' + re.sub(r'v\d+$', '', arxiv), 0, 'original_arxiv',
            evidence=('EXPLICIT_CITED_ARXIV',), urls=('https://arxiv.org/pdf/' + arxiv,))
        add('url', 'https://arxiv.org/pdf/' + arxiv, 1, 'original_arxiv', evidence=('EXPLICIT_CITED_ARXIV',))
    for url in (discover_url(reference.raw_text), reference.url, resolution.source_url if resolution else None):
        add('url', url, 0, 'original_url', authors=reference.authors)
    if reference.doi and reference.doi != original:
        add('doi', reference.doi, 2, resolution.provider if resolution else 'resolved')
    if resolution:
        for c in sorted(resolution.candidates, key=lambda c: -c.match_confidence):
            diagnostic = (c.rejection_reason,) if c.rejection_reason else ()
            if c.doi:
                add('doi', c.doi, 3, c.provider, c.title, c.authors, c.years, c.evidence, diagnostic, c.urls)
            for url in c.urls:
                add('url', url, 3, c.provider, c.title, c.authors, c.years, c.evidence, diagnostic)
    records.sort(key=lambda r: r['priority'])
    for r in records:
        r.pop('_key')
    return records


def reference_locators(reference):
    return tuple(SourceLocator.model_validate(r['locator']) for r in reference_candidates(reference) if r['locator'])


def reference_locator(reference) -> SourceLocator | None:
    locators = reference_locators(reference)
    if not locators and reference.doi:
        raise ValueError('DOI_INVALID')
    return locators[0] if locators else None
