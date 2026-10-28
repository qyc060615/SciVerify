"""Rebuildable per-job literature directory; snapshots remain authoritative."""
import json
import re

from app.services.source_store import LocalSourceStore


def write_task_literature(snapshot, job_root):
    if not re.fullmatch(r'job_[0-9a-f]{32}', snapshot.job_id):
        raise ValueError('Invalid job ID')
    directory = job_root / snapshot.job_id
    target = directory / 'literature.json'
    if directory.is_symlink() or target.is_symlink():
        raise ValueError('Invalid task directory')
    references = {r.id: r for r in snapshot.parsed.references}
    records = []
    for task in snapshot.tasks:
        ref = references[task.reference_id]
        binding = task.source_binding
        # Expected hashes alone describe requested recovery, not acquired sources.
        version = binding.source_version if binding else None
        records.append({
            'reference_id': ref.id, 'title': ref.title, 'doi': binding.doi if binding else ref.doi,
            'claim_id': task.claim_id, 'processing_state': task.state.value,
            'source_version': version,
            'raw_content_sha256': version[7:] if version and version.startswith('sha256:') else None,
            'source_url': binding.provenance.source_url if binding and binding.provenance else None,
        })
    manifest = {'schema_version': 1, 'job_id': snapshot.job_id, 'snapshot_revision': snapshot.revision,
                'created_at': snapshot.created_at, 'updated_at': snapshot.updated_at,
                'manuscript_pdf_retained': False, 'references': records}
    LocalSourceStore._atomic_write(target, json.dumps(manifest, ensure_ascii=False).encode('utf8'))
