"""Recover missing reference locators from verified local bytes, without network I/O."""
import json
import re
from io import BytesIO

from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.researchguard.domain import ReferenceResolution
from app.researchguard.source_locator import SourceLocator
from app.schemas.paper import PaperMetadata
from app.services.source_store import LocalSourceStore


def local_reference_metadata(store):
    """Read current pointer metadata once per resolution request, not old versions."""
    records = []
    for kind in ('doi', 'url'):
        if (store.root / kind).is_symlink():
            continue
        try:
            pointers = sorted((store.root / kind).glob('*.json'))
        except OSError:
            continue
        for pointer in pointers:
            try:
                if pointer.is_symlink() or pointer.stat().st_size > 4096:
                    continue
                digest = json.loads(pointer.read_bytes())['raw_content_sha256']
                if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
                    continue
                directory = store.root / digest
                metadata = directory / pointer.name
                if directory.is_symlink() or metadata.is_symlink() or metadata.stat().st_size > 1024 * 1024:
                    continue
                data = json.loads(metadata.read_bytes())
                paper = PaperMetadata.model_validate(data['paper'])
                locator = SourceLocator.model_validate(data['locator']) if data.get('locator') else SourceLocator(kind='doi', value=data['doi'])
                if (data['format'] not in {'pdf', 'html'} or data['raw_content_sha256'] != digest or locator.kind != kind
                        or store._locator_path(locator) != pointer
                        or (directory / ('source.' + data['format'])).is_symlink()):
                    continue
                records.append((locator, digest, paper))
            except (OSError, ValueError, KeyError, TypeError, RecursionError):
                continue
    return records


def recover_local_reference(reference, store=None, records=None):
    from app.services.reference_resolver import _compact, _normal, _surname, is_public_http_url
    from app.services.source_confirmation import inspect_confirmation
    from app.services.source_identity import _title_relation, qualify_source_identity
    from app.services.document_parser import parse_document
    from app.services.document_parser import DocumentParseError
    from app.services.evidence_chunker import chunk_sections

    store = store or LocalSourceStore()
    names = {_surname(author) for author in reference.authors if _surname(author)}
    if not reference.title or not names:
        return None  # A similar title alone never authorizes a new binding.
    first = _surname(reference.authors[0])
    matches = {}
    doi_aliases = {}
    historical_matches = set()
    for locator, digest, paper in (records if records is not None else local_reference_metadata(store)):
        authors = {_surname(author) for author in paper.authors}
        generic_title = bool(re.match(r'(?i)^\s*arxiv\s*:', paper.title or ''))
        if (first not in authors or len(names & authors) < min(2, len(names))
                or (not generic_title and _title_relation(reference.title, paper.title) == 'conflict')
                or (locator.kind == 'url' and not is_public_http_url(locator.value))):
            continue
        try:
            # Existing reader validates the pointer, metadata identity and SHA-256.
            artifact = store.get_locator(locator)
            if (artifact is None or artifact.raw_content_sha256 != digest
                    or not artifact.paper.full_text_available
                    or artifact.paper.full_text_format != artifact.format):
                continue
            provenance = artifact.provenance
            if provenance and provenance.identity == 'IDENTITY_CONFLICT':
                continue
            historical = bool(provenance and provenance.identity == 'EXACT_IDENTITY'
                and _compact(provenance.original_citation or '') == _compact(reference.raw_text))
            if (reference.year is None or paper.year != reference.year) and not historical:
                continue
            proof = inspect_confirmation(artifact.content, artifact.format, reference, artifact.source_url)
            if proof['status'] != 'confirmed':
                continue
            if artifact.format == 'pdf':
                reader = PdfReader(BytesIO(artifact.content))
                header = re.split(r'(?im)^\s*(?:\d+[.)]?\s*)?(?:abstract|introduction|references|bibliography)\b',
                    reader.pages[0].extract_text() or '', maxsplit=1)[0][:6000]
            else:
                soup = BeautifulSoup(artifact.content, 'html.parser')
                header = ' '.join(str(node.get('content', '')) for node in soup.select('meta[name="citation_author"]'))
            document_names = set(re.findall(r'[^\W\d_]+', _normal(header)))
            if first not in document_names or len(names & document_names) < min(2, len(names)):
                continue
            if locator.kind == 'doi':
                if qualify_source_identity(artifact.content, artifact.format, paper).status == 'conflict':
                    continue
                printed = re.findall(r'(?i)arxiv\s*:\s*(\d{4}\.\d{4,5})', header)
                if locator.value.startswith('10.48550/arxiv.') and printed and locator.value.removeprefix('10.48550/arxiv.') not in printed:
                    continue
            sections = parse_document(artifact.content, artifact.format)
            if not chunk_sections(sections, paper.paper_id, artifact.source_url):
                continue
            # Historical association may disambiguate publication/preprint files,
            # but only after the current bytes independently pass title+authors.
            if provenance and _compact(provenance.original_citation or '') == _compact(reference.raw_text):
                historical_matches.add(digest)
            if locator.kind == 'doi':
                doi_aliases.setdefault(digest, set()).add(locator.value)
            # Multiple aliases of identical bytes are one local source. Distinct
            # matching files/versions remain ambiguous rather than picking first.
            if digest not in matches or locator.kind == 'doi':
                matches[digest] = (locator, paper, proof)
        except (OSError, ValueError, KeyError, TypeError, IndexError, PyPdfError, DocumentParseError):
            continue
    if not matches:
        return None
    if historical_matches:
        matches = {digest: match for digest, match in matches.items() if digest in historical_matches}
    if len(matches) > 1 or any(len(doi_aliases.get(digest, ())) > 1 for digest in matches):
        return ReferenceResolution(reference_id=reference.id, status='ambiguous',
            match_reason='LOCAL_CACHE_MULTIPLE_IDENTITIES', diagnostics=('LOCAL_CACHE_AMBIGUOUS',))
    digest, (locator, paper, proof) = next(iter(matches.items()))
    resolution = ReferenceResolution(reference_id=reference.id,
        status='resolved' if locator.kind == 'doi' else 'non_doi_source',
        resolved_doi=locator.value if locator.kind == 'doi' else None,
        source_url=locator.value if locator.kind == 'url' else None,
        source_type=locator.kind, matched_title=paper.title, provider='local_cache',
        match_reason='LOCAL_CACHE_DOCUMENT_VERIFIED', diagnostics=(
            'LOCAL_SOURCE_LOCATOR_RECOVERED', proof['reason'], 'LOCAL_DOCUMENT_AUTHORS_MATCH',
            'LOCAL_SOURCE_SHA256:' + digest, *(('LOCAL_HISTORICAL_CITATION_MATCH',) if digest in historical_matches else ())))
    restored = reference.model_copy(update={'doi': resolution.resolved_doi,
        'url': resolution.source_url if locator.kind == 'url' else reference.url, 'resolution': resolution})
    from app.services.source_preparation import prepare_reference
    checked = prepare_reference(restored, retrieve=False)
    if checked['state'] != 'available' or checked['raw_content_sha256'] != digest:
        return None
    return resolution
