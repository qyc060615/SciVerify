"""Direct document evidence confirms work identity, independently of version dates."""
from io import BytesIO
import re
import unicodedata
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from pypdf import PdfReader


def compact(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value).casefold() if c.isalnum())


def surname(value):
    words = re.findall(r'[^\W\d_]+', unicodedata.normalize('NFKD', value).casefold())
    return words[-1] if words else ''


def inspect_confirmation(content, doc_format, reference, final_url=None):
    """Only the title area supplies evidence; bibliography/body matches cannot confirm."""
    from app.services.source_locator import citation_title, citation_arxiv
    from app.services.source_identity import _title_relation
    expected = citation_title(reference)
    actual_title = None
    if doc_format == 'pdf':
        reader = PdfReader(BytesIO(content))
        first = (reader.pages[0].extract_text() or '') if reader.pages else ''
        header = re.split(r'(?im)^\s*(?:\d+[.)]?\s*)?(?:abstract|introduction|references|bibliography)\b', first, maxsplit=1)[0][:4000]
        metadata = str((reader.metadata or {}).get('/Title', '')).strip()
        if metadata and not re.search(r'(?i)^arxiv:|microsoft|untitled|\.docx?$', metadata):
            actual_title = metadata
        # A cover with a separate title, named author, institution and date is
        # positive evidence of the actual work, even with empty PDF metadata.
        blocks = [b.strip() for b in re.split(r'\n\s*\n', first.strip()) if b.strip()]
        if (len(blocks) >= 3 and len(blocks[0].split()) >= 5
                and 2 <= len(blocks[1].split()) <= 7
                and re.search(r'(?i)universit|universidad|college|institute', first)
                and re.search(r'(?m)^\s*(?:19|20)\d{2}\s*$', first)):
            cover_title = ' '.join(blocks[0].split())
            if _title_relation(expected, cover_title) == 'conflict':
                return dict(status='conflict', reason='DOCUMENT_COVER_TITLE_CONFLICT', title=cover_title)
            actual_title = cover_title
    else:
        soup = BeautifulSoup(content, 'html.parser')
        node = soup.select_one('meta[name="citation_title"]')
        heading = soup.select_one('article h1, main h1, h1')
        actual_title = str(node.get('content', '')) if node else heading.get_text(' ', strip=True) if heading else None
        author_nodes = soup.select('meta[name="citation_author"]')
        header = (actual_title or '') + '\n' + '\n'.join(str(n.get('content', '')) for n in author_nodes)
    arxiv_id = citation_arxiv(reference.raw_text)
    printed_ids = re.findall(r'(?i)arxiv\s*:\s*(\d{4}\.\d{4,5})', header)
    if arxiv_id and printed_ids and re.sub(r'v\d+$', '', arxiv_id) not in printed_ids:
        return dict(status='conflict', reason='DOCUMENT_ARXIV_IDENTIFIER_CONFLICT', title=actual_title)
    target = compact(expected or '')
    if actual_title and _title_relation(expected, actual_title) == 'conflict':
        # Generic extraction strings are not authoritative article titles.
        # Existing source identity owns metadata-title DOI/conflict checks.
        actual_title = None
    lines = [line.strip() for line in header.splitlines() if line.strip()]
    standalone = bool(target and any(target == compact(' '.join(lines[start:end]))
        for start in range(min(8, len(lines))) for end in range(start + 1, min(start + 6, len(lines)) + 1)))
    metadata_match = bool(actual_title and _title_relation(expected, actual_title) == 'match')
    long_title = bool(expected and len(expected.split()) >= 6 and len(target) >= 20 and target in compact(header))
    if standalone or metadata_match or long_title:
        return dict(status='confirmed', reason='DOCUMENT_TITLE_DIRECT_MATCH', title=expected)
    # A shortened citation title needs authors to corroborate the fuller title.
    names = {surname(a) for a in reference.authors if surname(a)}
    header_names = {surname(w) for w in header.split()}
    author_matches = len(names & header_names)
    terms = set(re.findall(r'[^\W\d_]+', unicodedata.normalize('NFKD', expected or '').casefold())) - {'a', 'an', 'the', 'of', 'and', 'in', 'to', 'for', 'with', 'on', 'by', 'from', 'using'}
    header_terms = set(re.findall(r'[^\W\d_]+', unicodedata.normalize('NFKD', header).casefold()))
    if len(terms) >= 3 and terms <= header_terms and author_matches >= 2:
        return dict(status='confirmed', reason='DOCUMENT_TITLE_AND_AUTHORS_MATCH', title=actual_title)
    arxiv = citation_arxiv(reference.raw_text)
    if arxiv and final_url:
        parsed = urlsplit(final_url)
        found = re.search(r'/(?:pdf|abs)/(\d{4}\.\d{4,5})', parsed.path)
        original = re.sub(r'v\d+$', '', arxiv)
        printed = re.findall(r'(?i)arxiv\s*:\s*(\d{4}\.\d{4,5})', header)
        if printed and original not in printed:
            return dict(status='conflict', reason='DOCUMENT_ARXIV_IDENTIFIER_CONFLICT', title=actual_title)
        if parsed.hostname in {'arxiv.org', 'www.arxiv.org', 'export.arxiv.org'} and found and found.group(1) == original:
            return dict(status='confirmed', reason='EXPLICIT_CITED_ARXIV_MATCH', title=actual_title)
    return dict(status='uncertain', reason='DIRECT_DOCUMENT_IDENTITY_INSUFFICIENT', title=actual_title)


def apply_confirmation(reference, response, locator, *, store=None):
    """Recheck actual persisted bytes; never promote a rejected candidate."""
    from app.schemas.paper import PaperRetrievalStatus
    from app.researchguard.source_locator import SourceProvenance
    from app.services.source_store import LocalSourceStore
    if response.status != PaperRetrievalStatus.SUCCESS or response.source.identity_status == 'conflict':
        return response
    artifact = (store or LocalSourceStore()).get_locator(locator)
    if artifact is None:
        return response  # Legacy injected responses are not document evidence.
    evidence = inspect_confirmation(artifact.content, artifact.format, reference, artifact.source_url)
    response = response.model_copy(deep=True)
    previous = response.source.provenance
    if evidence['status'] == 'conflict':
        response.status = PaperRetrievalStatus.FULL_TEXT_UNAVAILABLE
        response.chunks = []
        response.detail = 'SOURCE_IDENTITY_CONFLICT'
        response.source.identity_status = 'conflict'
        identity = 'IDENTITY_CONFLICT'
    elif evidence['status'] == 'confirmed':
        response.source.identity_status = 'confirmed'
        identity = 'EXACT_IDENTITY'
    else:
        return response
    warnings = list(previous.warnings if previous else ())
    if identity == 'EXACT_IDENTITY':
        warnings = [w for w in warnings if w != 'SOURCE_IDENTITY_UNCERTAIN']
        if evidence['reason'] in {'DOCUMENT_TITLE_DIRECT_MATCH', 'DOCUMENT_TITLE_AND_AUTHORS_MATCH'}:
            warnings = [w for w in warnings if w not in {'DOCUMENT_TITLE_UNCONFIRMED', 'RETRIEVED_TITLE_UNCONFIRMED'}]
    warnings.append('HISTORICAL_VERSION_UNCONFIRMED')
    if not reference.authors:
        warnings.append('AUTHORS_UNCONFIRMED')
    if previous:
        response.source.provenance = previous.model_copy(update=dict(identity=identity,
            retrieved_title=evidence['title'] or previous.retrieved_title,
            match_evidence=tuple(dict.fromkeys((*previous.match_evidence, evidence['reason']))),
            warnings=tuple(dict.fromkeys(warnings))))
    else:
        response.source.provenance = SourceProvenance(original_citation=reference.raw_text,
            identity=identity, document_kind='ARTICLE_FULL_TEXT', retrieved_title=evidence['title'],
            match_evidence=(evidence['reason'],), warnings=tuple(dict.fromkeys(warnings)))
    return response
