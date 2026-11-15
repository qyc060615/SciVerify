import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.paper import PaperMetadata
from app.services.source_store import AcceptedSourceArtifact, LocalSourceStore
from app.services.verification_job_store import LocalJobStore
from app.services.literature_repository import list_literature
from app.tests.test_verification_job_store import snapshot
from app.services.verification_jobs import evolve
from app.services.verification_job_models import JobState


def artifact(store, content=b'<html>real source</html>', format='html', origin='remote'):
    paper = PaperMetadata(paper_id='10.1234/test', doi='10.1234/test', title='Stored literature title')
    value = AcceptedSourceArtifact.create(doi=paper.doi, content=content, format=format,
        source_url='https://example.org/paper' if origin == 'remote' else None,
        provider='fixture', origin=origin, paper=paper)
    store.put(value)
    return value


def test_inventory_reads_all_versions_and_refreshes_actual_availability(tmp_path):
    store, jobs = LocalSourceStore(tmp_path / 'sources'), LocalJobStore(tmp_path / 'jobs')
    first = artifact(store)
    second = artifact(store, b'%PDF-fixture', 'pdf', 'manual')
    result = list_literature(store, jobs)
    assert len(result['records']) == 2
    assert {r['source_type'] for r in result['records']} == {'Retrieved HTML', 'Uploaded PDF'}
    assert all(r['availability'] == 'available' for r in result['records'])
    (store.root / first.raw_content_sha256 / 'source.html').unlink()
    (store.root / second.raw_content_sha256 / 'source.pdf').write_bytes(b'changed')
    assert {r['availability'] for r in list_literature(store, jobs)['records']} == {'missing', 'corrupt'}
    assert str(tmp_path) not in json.dumps(result)


def test_bad_metadata_is_skipped_and_doi_pointers_do_not_create_files(tmp_path):
    store = LocalSourceStore(tmp_path / 'sources')
    store.root.mkdir()
    (store.root / ('a' * 64)).mkdir()
    (store.root / ('a' * 64) / 'bad.json').write_text('{}')
    result = list_literature(store, LocalJobStore(tmp_path / 'jobs'))
    assert result['records'] == [] and result['warnings']


def test_empty_store_and_source_links_are_safe(tmp_path):
    store, jobs = LocalSourceStore(tmp_path / 'sources'), LocalJobStore(tmp_path / 'jobs')
    assert list_literature(store, jobs) == {'records': [], 'warnings': []}
    value = artifact(store)
    meta = next((store.root / value.raw_content_sha256).glob('*.json'))
    data = json.loads(meta.read_bytes())
    data['source_url'] = 'file:///private/secret'
    meta.write_text(json.dumps(data))
    assert list_literature(store, jobs)['records'][0]['source_url'] is None


def test_task_association_requires_matching_hash_and_locator(tmp_path):
    store = LocalSourceStore(tmp_path / 'sources')
    old = artifact(store)
    new = artifact(store, b'<html>new version</html>')
    binding = SimpleNamespace(source_version='sha256:' + old.raw_content_sha256, locator=None, doi=old.doi)
    class Jobs:
        def list_job_ids(self): return ['job_' + 'a' * 32]
        def load(self, _): return SimpleNamespace(tasks=[SimpleNamespace(source_binding=binding)])
    rows = list_literature(store, Jobs())['records']
    assert next(r for r in rows if r['raw_content_sha256'] == old.raw_content_sha256)['related_job_ids']
    assert not next(r for r in rows if r['raw_content_sha256'] == new.raw_content_sha256)['related_job_ids']


def test_per_task_manifest_tracks_revision_without_claiming_pdf_storage(tmp_path):
    store, original = LocalJobStore(tmp_path / 'jobs'), snapshot()
    store.create(original)
    path = store.root / original.job_id / 'literature.json'
    manifest = json.loads(path.read_bytes())
    assert manifest['snapshot_revision'] == 0
    assert manifest['manuscript_pdf_retained'] is False
    assert all(r['raw_content_sha256'] is None for r in manifest['references'])
    store.commit(evolve(original, 'job_started', JobState.RUNNING), expected_revision=0)
    assert json.loads(path.read_bytes())['snapshot_revision'] == 1
    assert store.load(original.job_id).revision == 1


def test_manifest_failure_does_not_fail_committed_job(tmp_path, monkeypatch):
    import app.services.task_literature as module
    def fail(*_): raise OSError('disk unavailable')
    monkeypatch.setattr(module, 'write_task_literature', fail)
    store, original = LocalJobStore(tmp_path / 'jobs'), snapshot()
    assert store.create(original) == original
    assert store.load(original.job_id) == original


def test_api_inventory_and_local_only_access(tmp_path, monkeypatch):
    monkeypatch.setenv('RESEARCHGUARD_SOURCE_CACHE_DIR', str(tmp_path / 'sources'))
    value = artifact(LocalSourceStore())
    with TestClient(app) as client:
        response = client.get('/api/repository')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert response.json()['records'][0]['raw_content_sha256'] == value.raw_content_sha256
    with TestClient(app, client=('198.51.100.2', 1234)) as client:
        assert client.get('/api/repository').status_code == 403


def test_api_storage_failure_is_explicit_and_hides_path(monkeypatch):
    import app.api.routes.repository as module
    def fail(): raise PermissionError('/private/secret')
    monkeypatch.setattr(module, 'list_literature', fail)
    with TestClient(app) as client:
        response = client.get('/api/repository')
        assert response.status_code == 503
        assert '/private/secret' not in response.text
