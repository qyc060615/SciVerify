"""Explicit bounded probes. A status refresh never performs model inference."""
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from urllib.parse import urlsplit

import httpx

from app.settings_catalog import CATALOG, SERVICES, loopback, validate_url
from app.settings_store import active_profiles, effective, fingerprint
from app.services.public_http import PublicHTTPTransport

class CheckFailure(ValueError):
    pass


_LAST = {}
_LOCK = Lock()


def client_for(base_url):
    if loopback(urlsplit(base_url).hostname):
        return httpx.Client(timeout=httpx.Timeout(8, connect=3), trust_env=False, follow_redirects=False)
    return httpx.Client(transport=PublicHTTPTransport(), timeout=httpx.Timeout(8, connect=3), trust_env=False, follow_redirects=False)


def _request(client, method, url, **kwargs):
    deadline = time.monotonic() + 12
    with client.stream(method, url, **kwargs) as response:
        if response.status_code in {401, 403}:
            raise CheckFailure('Authentication or access was rejected.')
        if response.status_code == 429:
            raise CheckFailure('The provider is rate limited. Try later.')
        if not 200 <= response.status_code < 300:
            raise CheckFailure('The service returned HTTP ' + str(response.status_code) + '.')
        content = bytearray()
        for chunk in response.iter_bytes():
            if time.monotonic() > deadline:
                raise CheckFailure('The service check timed out.')
            if len(content) + len(chunk) > 2 * 1024 * 1024:
                raise CheckFailure('The test response was too large.')
            content.extend(chunk)
        try:
            return json.loads(content)
        except (ValueError, UnicodeError):
            raise CheckFailure('The service returned an unexpected response.') from None


def _reachable(client, url):
    # Read headers only. TLS verification and the public transport's SSRF checks
    # remain enabled; any final HTTP response proves endpoint reachability.
    if urlsplit(url).scheme != 'https':
        raise CheckFailure('A secure HTTPS endpoint is required.')
    with client.stream('GET', url) as response:
        if not 200 <= response.status_code <= 599:
            raise CheckFailure('No valid HTTP response was received.')


def probe(id, row):
    """Return semantic check descriptions only, never provider bodies or exception text."""
    spec = CATALOG[id]
    scope = 'One small model request.' if spec['paid_test'] else 'Service API response; not an end-to-end verification.'
    def result(state, message):
        return {'id': id, 'state': state, 'message': message, 'scope': scope}
    if spec['paid_test']:
        if id == 'llm' and row.get('provider') in {'none', '', 'disabled'}:
            return result('unknown', 'LLM provider is disabled.')
        if id != 'llm' and not row.get('model', '').startswith('openai/'):
            return result('unknown', 'This probe supports openai/ compatible LiteLLM models only. Existing native provider configuration is preserved.')
        if not row.get('base_url') or not row.get('model'):
            return result('unknown', 'Set a Base URL and Model ID before testing.')
    try:
        base = validate_url(row['base_url'])
        if id in {'openalex', 'semantic_scholar'} and (urlsplit(base).scheme != 'https' or loopback(urlsplit(base).hostname)):
            raise CheckFailure('A public HTTPS endpoint is required.')
        with client_for(base) as client:
            headers = {'Accept': 'application/json'}
            if row.get('_key'):
                headers['Authorization'] = 'Bearer ' + row['_key']
            if spec['paid_test']:
                model = row['model'] if id == 'llm' else row['model'].removeprefix('openai/')
                if id == 'embedding':
                    data = _request(client, 'POST', base + '/embeddings', headers=headers,
                                    json={'model': model, 'input': ['Connection test']})
                    vector = data.get('data', [{}])[0].get('embedding')
                    if not isinstance(vector, list) or not vector or not all(type(x) in {int, float} and math.isfinite(x) for x in vector):
                        raise CheckFailure('The service did not return a valid embedding vector.')
                    scope = 'One embedding request returned a nonempty numeric vector.'
                else:
                    data = _request(client, 'POST', base + '/chat/completions', headers=headers,
                                    json={'model': model, 'messages': [{'role': 'user', 'content': 'Reply OK.'}], 'max_tokens': 16})
                    message = data.get('choices', [{}])[0].get('message', {})
                    if not any(isinstance(value, str) and value.strip() for value in (message.get('content'), message.get('reasoning_content'))):
                        raise CheckFailure('The model returned no text. The test token budget may be too small for this model.')
                    scope = 'One chat completion returned text; scientific correctness was not tested.'
            elif id == 'grobid':
                data = _request(client, 'GET', base + '/api/isalive')
                if data is not True:
                    raise CheckFailure('GROBID did not report ready.')
                scope = '/api/isalive returned true; no PDF was parsed.'
            elif id == 'crossref':
                data = _request(client, 'GET', base + '/works', params={'rows': 1}, headers={'User-Agent': row['user_agent']})
                if not isinstance(data.get('message', {}).get('items'), list):
                    raise CheckFailure('Crossref metadata response was not recognized.')
            elif id in {'openalex', 'semantic_scholar'}:
                _reachable(client, base)
                scope = 'HTTPS reachability only; not API readiness or search success.'
                return result('ok', 'Reachable')
            elif id == 'europe_pmc':
                data = _request(client, 'GET', base + '/search', params={'query': 'EXT_ID:23925245', 'format': 'json', 'pageSize': 1})
                if 'resultList' not in data:
                    raise CheckFailure('Europe PMC metadata response was not recognized.')
            elif id == 'unpaywall':
                data = _request(client, 'GET', base + '/10.1038/nature12373', params={'email': row['email']})
                if not data.get('doi'):
                    raise CheckFailure('Unpaywall metadata response was not recognized.')
        return result('ok', 'Connection successful')
    except CheckFailure as exc:
        return result('failed', str(exc))
    except ValueError:
        return result('failed', 'Could not validate the configured endpoint or response.')
    except (httpx.HTTPError, httpx.InvalidURL, OSError):
        return result('failed', 'Could not connect securely. Check the URL, network and service availability.')
    except (KeyError, IndexError, TypeError, AttributeError):
        return result('failed', 'The service returned an unexpected response.')


def remember_result(id, row, result):
    with _LOCK:
        _LAST[id] = (fingerprint(row), result)


def system_status(refresh=False):
    profiles = active_profiles()
    if refresh:
        def check(spec):
            if not spec['paid_test']:
                row = effective(profiles, spec['id'])
                remember_result(spec['id'], row, probe(spec['id'], row))
        with ThreadPoolExecutor(max_workers=3) as executor:
            list(executor.map(check, SERVICES))
    rows = [{'id': 'backend', 'label': 'FastAPI Backend', 'state': 'ok', 'message': 'This settings API responded.', 'scope': 'Backend HTTP response only.'}]
    with _LOCK:
        for spec in SERVICES:
            id = spec['id']
            cached = _LAST.get(id)
            result = cached[1] if cached and cached[0] == fingerprint(effective(profiles, id)) else {
                'state': 'unknown', 'message': 'Not checked for the active configuration.',
                'scope': 'Use Test Connection in API for a model test.' if spec['paid_test'] else 'Press Refresh to check.'}
            rows.append({'id': id, 'label': spec['label'], **result})
    return {'services': rows}
