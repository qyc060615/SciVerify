"""Offline contracts. All external probes use HTTP MockTransport."""
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.settings_catalog import SERVICES, validate_url
from app import settings_store as store
from app.services import settings_checks as checks


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('RESEARCHGUARD_SETTINGS_FILE', str(tmp_path / 'private-settings.bin'))
    monkeypatch.setenv('RESEARCHGUARD_SETTINGS_ENABLED', '1')
    for name in ('WEB_CONCURRENCY', 'UVICORN_WORKERS', 'RESEARCHGUARD_JOB_PROCESSES'):
        monkeypatch.setenv(name, '1')
    for spec in SERVICES:
        for f in spec['fields']:
            monkeypatch.setenv(f['env'], f['default'])
        if spec['secret_env']:
            monkeypatch.setenv(spec['secret_env'], 'fixture-secret-' + spec['id'])
    monkeypatch.setenv('LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('PAPERQA2_MODEL', 'openai/fixture-chat')
    monkeypatch.setenv('PAPERQA2_EMBEDDING_MODEL', 'openai/fixture-vector')
    monkeypatch.setenv('PAPERQA2_API_BASE', 'https://example.org/v1')
    monkeypatch.setenv('PAPERQA2_EMBEDDING_API_BASE', 'https://example.org/v1')
    monkeypatch.setattr(store, '_ACTIVE', store.environment_profiles())
    monkeypatch.setattr(checks, '_LAST', {})


@pytest.fixture
def api():
    with TestClient(app, base_url='http://127.0.0.1:8000') as client:
        yield client


def config(api):
    response = api.get('/api/settings')
    assert response.status_code == 200
    data = response.json()
    return data, {'X-Settings-Token': data['management_token']}


def row(data, id='llm'):
    return next(s for s in data['services'] if s['id'] == id)


def save(api, data, headers, id='llm', **changes):
    return api.put('/api/settings/connections/' + id, headers=headers,
                   json={'revision': data['revision'], 'values': row(data, id)['values'], **changes})


def test_status_and_configuration_never_expose_keys_or_probe_automatically(api, monkeypatch):
    monkeypatch.setattr(checks, 'probe', lambda *_: pytest.fail('Automatic external probe'))
    data, _ = config(api)
    assert len(data['services']) == 9
    assert all('fixture-secret' not in json.dumps(s) for s in data['services'])
    assert api.get('/api/settings').headers['cache-control'] == 'no-store'
    statuses = api.get('/api/settings/status').json()['services']
    assert statuses[0]['state'] == 'ok'
    assert all(r['state'] == 'unknown' for r in statuses[1:])


def test_save_is_persistent_redacted_and_never_hot_updates(api):
    data, headers = config(api)
    values = {**row(data)['values'], 'model': 'new-model'}
    before = dict(os.environ)
    response = save(api, data, headers, values=values, api_key='new-secret-value')
    assert response.status_code == 200
    assert row(response.json())['pending_restart'] is True
    assert row(response.json())['active_model'] != 'new-model'
    assert 'new-secret-value' not in response.text
    assert dict(os.environ) == before
    reopened, _ = config(api)
    assert row(reopened)['values']['model'] == 'new-model'
    if os.name == 'nt':
        assert b'new-secret-value' not in store.settings_path().read_bytes()
    else:
        assert store.settings_path().stat().st_mode & 0o077 == 0
    store.apply_saved_settings()  # Simulates the explicit next-startup boundary only.
    assert os.environ['LLM_API_KEY'] == 'new-secret-value'
    assert not row(store.public_settings())['pending_restart']


def test_blank_key_keeps_existing_clear_is_explicit_and_services_do_not_overwrite(api):
    data, headers = config(api)
    saved = save(api, data, headers, api_key='').json()
    assert row(saved)['has_key']
    assert store.effective(store.saved_profiles()[1], 'llm')['_key'] == 'fixture-secret-llm'
    embedding = save(api, saved, headers, 'embedding', api_key='embedding-replacement').json()
    assert store.effective(store.saved_profiles()[1], 'llm')['_key'] == 'fixture-secret-llm'
    cleared = save(api, embedding, headers, clear_api_key=True)
    assert cleared.status_code == 200
    assert not row(cleared.json())['has_key']
    assert store.effective(store.saved_profiles()[1], 'embedding')['_key'] == 'embedding-replacement'
    assert os.environ['LLM_API_KEY'] == 'fixture-secret-llm'


def test_shared_connection_reuses_key_and_url_without_copying_or_sharing_model(api):
    data, headers = config(api)
    values = {**row(data, 'paperqa')['values'], 'connection_source': 'llm'}
    saved = save(api, data, headers, 'paperqa', values=values).json()
    profiles = store.saved_profiles()[1]
    assert profiles['paperqa']['_key'] == ''
    shared = store.effective(profiles, 'paperqa')
    assert shared['_key'] == 'fixture-secret-llm'
    assert shared['model'] == 'openai/fixture-chat'
    assert row(saved, 'paperqa')['has_key']
    assert save(api, saved, headers, 'paperqa', api_key='duplicate').status_code == 400


def test_optimistic_revision_keeps_another_draft_from_overwriting(api):
    data, headers = config(api)
    assert save(api, data, headers).status_code == 200
    assert save(api, data, headers, api_key='must-not-save').status_code == 409
    assert store.effective(store.saved_profiles()[1], 'llm')['_key'] != 'must-not-save'


@pytest.mark.parametrize('headers', [
    {'Host': 'evil.example'}, {'Origin': 'https://evil.example'}, {'Origin': 'null'},
])
def test_host_and_origin_guards(api, headers):
    assert api.get('/api/settings', headers=headers).status_code == 403


def test_remote_peer_and_csrf_guard(api):
    data, headers = config(api)
    assert save(api, data, {}).status_code == 403
    with TestClient(app, base_url='http://127.0.0.1', client=('198.51.100.2', 123)) as remote:
        assert remote.get('/api/settings').status_code == 403
    assert save(api, data, headers).status_code == 200


def test_invalid_key_input_is_not_echoed(api):
    data, headers = config(api)
    response = save(api, data, headers, api_key='sensitive\nsecret')
    assert response.status_code == 400
    assert 'sensitive' not in response.text
    assert not store.settings_path().exists()


@pytest.mark.parametrize('url', ['http://example.org/v1', 'file:///tmp/key', 'https://user:secret@example.org', 'https://example.org?key=secret', 'https://192.168.1.1', 'https://example.internal', 'https://example.org#secret'])
def test_unsafe_probe_destinations_are_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url)


def transport(monkeypatch, handler):
    monkeypatch.setattr(checks, 'client_for', lambda _: httpx.Client(transport=httpx.MockTransport(handler)))


def test_paid_test_requires_explicit_opt_in_and_does_not_save(api, monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        assert request.headers['authorization'] == 'Bearer fixture-secret-llm'
        assert json.loads(request.content)['max_tokens'] == 16
        return httpx.Response(200, json={'choices': [{'message': {'content': 'OK'}}]})
    transport(monkeypatch, handler)
    data, headers = config(api)
    body = {'values': row(data)['values']}
    assert api.post('/api/settings/connections/llm/test', headers=headers, json=body).status_code == 400
    assert not requests
    response = api.post('/api/settings/connections/llm/test', headers=headers, json={**body, 'allow_paid': True})
    assert response.json()['state'] == 'ok'
    assert len(requests) == 1 and not store.settings_path().exists()
    assert api.get('/api/settings/status').json()['services'][1]['state'] == 'ok'


@pytest.mark.parametrize('status,body,expected', [(401, {'error': 'fixture-secret-llm'}, 'failed'), (429, {}, 'failed'), (200, {'data': [{'embedding': [0.1, 0.2]}]}, 'ok'), (200, {'data': []}, 'failed')])
def test_embedding_success_and_sanitized_failures(api, monkeypatch, status, body, expected):
    transport(monkeypatch, lambda _: httpx.Response(status, json=body))
    data, headers = config(api)
    response = api.post('/api/settings/connections/embedding/test', headers=headers,
                        json={'values': row(data, 'embedding')['values'], 'allow_paid': True})
    assert response.json()['state'] == expected
    assert 'fixture-secret' not in response.text


def test_refresh_checks_only_free_services_and_uses_active_configuration(api, monkeypatch):
    tested = []
    def probe(id, profile):
        tested.append(id)
        return {'id': id, 'state': 'ok', 'message': 'Offline fixture', 'scope': 'Mock only'}
    monkeypatch.setattr(checks, 'probe', probe)
    _, headers = config(api)
    assert api.post('/api/settings/status/refresh', headers=headers, json={}).status_code == 200
    assert set(tested) == {'grobid', 'crossref', 'openalex', 'semantic_scholar', 'europe_pmc', 'unpaywall'}


def test_bad_saved_file_is_not_replaced(api):
    path = store.settings_path()
    path.write_bytes(b'corrupted')
    assert api.get('/api/settings').status_code == 503
    assert path.read_bytes() == b'corrupted'


def test_public_endpoint_values_strip_url_credentials_and_query(api, monkeypatch):
    active = store.active_profiles()
    active['llm']['base_url'] = 'https://user:private@example.org/v1?api_key=hidden'
    monkeypatch.setattr(store, '_ACTIVE', active)
    response = api.get('/api/settings')
    assert response.status_code == 200
    assert 'private' not in response.text and 'hidden' not in response.text


@pytest.mark.parametrize('id,payload', [
    ('grobid', True), ('crossref', {'message': {'items': []}}), ('openalex', {'results': []}),
    ('semantic_scholar', {'title': 'Fixture paper'}), ('europe_pmc', {'resultList': {'result': []}}),
    ('unpaywall', {'doi': '10.1038/nature12373'}),
])
def test_each_public_service_probe_checks_its_actual_response_schema(api, monkeypatch, id, payload):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload)
    transport(monkeypatch, handler)
    data, headers = config(api)
    response = api.post('/api/settings/connections/' + id + '/test', headers=headers,
                        json={'values': row(data, id)['values']})
    assert response.status_code == 200 and response.json()['state'] == 'ok'
    assert len(requests) == (2 if id == 'semantic_scholar' else 1)


def test_test_of_pending_model_cannot_mark_active_model_as_passed(api, monkeypatch):
    transport(monkeypatch, lambda _: httpx.Response(200, json={'choices': [{'message': {'content': 'OK'}}]}))
    data, headers = config(api)
    values = {**row(data)['values'], 'model': 'pending-model'}
    response = api.post('/api/settings/connections/llm/test', headers=headers, json={'values': values, 'allow_paid': True})
    assert response.json()['state'] == 'ok'
    assert api.get('/api/settings/status').json()['services'][1]['state'] == 'unknown'


def test_native_litellm_model_is_preserved_and_never_falsely_tested(api, monkeypatch):
    transport(monkeypatch, lambda _: pytest.fail('Unsupported native provider must not be called'))
    data, headers = config(api)
    values = {**row(data, 'paperqa')['values'], 'model': 'anthropic/example-native'}
    response = api.post('/api/settings/connections/paperqa/test', headers=headers, json={'values': values, 'allow_paid': True})
    assert response.json()['state'] == 'unknown'
    assert not store.settings_path().exists()


def test_transport_failure_never_returns_exception_secrets(api, monkeypatch):
    def handler(_): raise httpx.ConnectError('fixture-secret-llm')
    transport(monkeypatch, handler)
    data, headers = config(api)
    response = api.post('/api/settings/connections/grobid/test', headers=headers, json={'values': row(data, 'grobid')['values']})
    assert response.json()['state'] == 'failed'
    assert 'fixture-secret' not in response.text


@pytest.mark.parametrize('headers', [{'X-Forwarded-For': '198.51.100.2'}, {'Forwarded': 'for=198.51.100.2'}, {'Host': '127.0.0.1:invalid'}])
def test_forwarded_or_malformed_hosts_are_not_local_administration(api, headers):
    assert api.get('/api/settings', headers=headers).status_code == 403


def test_non_text_model_payload_cannot_report_success(api, monkeypatch):
    transport(monkeypatch, lambda _: httpx.Response(200, json={'choices': [{'message': {'content': {'unexpected': True}}}]}))
    data, headers = config(api)
    response = api.post('/api/settings/connections/llm/test', headers=headers, json={'values': row(data)['values'], 'allow_paid': True})
    assert response.json()['state'] == 'failed'
