"""Read-only inventory of existing source artifacts; never retrieve or mutate sources."""
import hashlib
import json
import re
from urllib.parse import urlsplit

from app.schemas.paper import PaperMetadata
from app.services.source_store import LocalSourceStore
from app.services.verification_job_store import LocalJobStore, JobError
from app.researchguard.source_locator import SourceLocator
from app.utils.doi import normalize_doi

_SHA = re.compile(r'^[0-9a-f]{64}$')


def _safe_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {'https', 'http'} and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return None


def _availability(path, digest):
    if path.is_symlink():
        return 'unavailable'
    try:
        hasher = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                hasher.update(chunk)
        return 'available' if hasher.hexdigest() == digest else 'corrupt'
    except FileNotFoundError:
        return 'missing'
    except OSError:
        return 'unavailable'


def list_literature(source_store=None, job_store=None):
    store = source_store or LocalSourceStore()
    rows, warnings = {}, set()
    # Scan version directories, not just the latest DOI/URL pointers.
    # An absent directory is a valid empty workspace; access errors reach the route.
    try:
        directories = list(store.root.iterdir())
    except FileNotFoundError:
        directories = []
    for directory in sorted(directories):
        if not _SHA.fullmatch(directory.name) or directory.is_symlink() or not directory.is_dir():
            continue
        digest = directory.name
        for path in sorted(directory.glob('*.json')):
            try:
                if path.is_symlink() or path.stat().st_size > 1024 * 1024:
                    raise ValueError()
                data = json.loads(path.read_bytes())
                if (data['version'] not in {1, 2} or data['raw_content_sha256'] != digest
                        or data['format'] not in {'pdf', 'html'} or data['origin'] not in {'manual', 'remote'}):
                    raise ValueError()
                paper = PaperMetadata.model_validate(data['paper'])
                doi = normalize_doi(data['doi']) if data['doi'] else None
                if paper.doi != doi:
                    raise ValueError()
                locator = SourceLocator.model_validate(data['locator']) if data.get('locator') else SourceLocator(kind='doi', value=doi)
                if (locator.kind == 'doi' and locator.value != doi
                        or locator.kind == 'url' and (doi is not None or paper.paper_id != locator.key)):
                    raise ValueError()
                key = digest + ':' + locator.key
                rows[key] = {
                    'id': key, 'title': paper.title or None, 'doi': doi,
                    'literature_type': 'Reference', 'format': data['format'],
                    'source_type': ('Uploaded PDF' if data['origin'] == 'manual' and data['format'] == 'pdf'
                                    else 'Retrieved HTML' if data['origin'] == 'remote' and data['format'] == 'html' else 'Other'),
                    'availability': _availability(directory / ('source.' + data['format']), digest),
                    'raw_content_sha256': digest, 'source_url': _safe_url(data.get('source_url')),
                    'related_job_ids': [],
                }
            except (OSError, ValueError, KeyError, TypeError, RecursionError):
                warnings.add('Some source records could not be read and were skipped.')
    # Read validated snapshots only to attach exact version associations, never to invent files.
    jobs = job_store or LocalJobStore()
    try:
        ids = jobs.list_job_ids()
    except (JobError, OSError):
        ids = []
        warnings.add('Related tasks could not be read.')
    for job_id in ids:
        try:
            snapshot = jobs.load(job_id)
            for task in snapshot.tasks:
                binding = task.source_binding
                if not binding or not binding.source_version:
                    continue
                locator = binding.locator or SourceLocator(kind='doi', value=binding.doi)
                row = rows.get(binding.source_version.removeprefix('sha256:') + ':' + locator.key)
                if row is not None and job_id not in row['related_job_ids']:
                    row['related_job_ids'].append(job_id)
        except (JobError, ValueError, OSError):
            warnings.add('Some related tasks could not be read.')
    return {'records': sorted(rows.values(), key=lambda r: ((r['title'] or '').casefold(), r['id'])),
            'warnings': sorted(warnings)}
