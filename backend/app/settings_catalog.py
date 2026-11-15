"""Only real integrations used by the current pipeline. No model-role rewiring."""
from urllib.parse import urlsplit
import ipaddress
import re


def field(name, label, env, default='', kind='text', options=None):
    return dict(name=name, label=label, env=env, default=default, kind=kind, options=options or [])


def service(id, label, purpose, fields, secret=None, shares=(), paid=False):
    return dict(id=id, label=label, purpose=purpose, fields=fields, secret_env=secret,
                share_options=list(shares), paid_test=paid)


SERVICES = [
    service('llm', 'LLM Provider', 'Shared by Claim Extraction, Verification and all three Agents. Validator is deterministic.', [
        field('provider', 'Provider protocol', 'LLM_PROVIDER', 'none', 'select', ['none', 'openai', 'openai-compatible', 'compatible', 'groq', 'groq-compatible']),
        field('base_url', 'Base URL', 'LLM_BASE_URL', 'https://api.openai.com/v1', 'url'),
        field('model', 'Model ID', 'LLM_MODEL', 'gpt-4o-mini'),
        field('timeout', 'Request timeout (seconds)', 'LLM_REQUEST_TIMEOUT', '60', 'number'),
    ], 'LLM_API_KEY', paid=True),
    service('paperqa', 'PaperQA2 Model', 'Evidence summarization via LiteLLM; use a provider-qualified Model ID such as openai/your-model.', [
        field('base_url', 'Base URL', 'PAPERQA2_API_BASE', '', 'url'),
        field('model', 'Provider-qualified Model ID', 'PAPERQA2_MODEL'),
        field('timeout', 'Request timeout (seconds)', 'PAPERQA2_REQUEST_TIMEOUT', '60', 'number'),
    ], 'PAPERQA2_API_KEY', ['llm'], True),
    service('embedding', 'Embedding Provider', 'PaperQA2 vector embeddings; batch size must respect your provider limit.', [
        field('base_url', 'Base URL', 'PAPERQA2_EMBEDDING_API_BASE', '', 'url'),
        field('model', 'Provider-qualified Model ID', 'PAPERQA2_EMBEDDING_MODEL'),
        field('batch_size', 'Embedding batch size', 'PAPERQA2_EMBEDDING_BATCH_SIZE', '10', 'number'),
    ], 'PAPERQA2_EMBEDDING_API_KEY', ['llm', 'paperqa'], True),
    service('grobid', 'GROBID Parser', 'Manuscript PDF parsing. The connection test checks /api/isalive, not PDF parsing.', [
        field('base_url', 'Base URL', 'GROBID_BASE_URL', 'http://127.0.0.1:8070', 'url'),
    ]),
    service('crossref', 'Crossref', 'DOI metadata and reference resolution. Public API; no key is used by this project.', [
        field('base_url', 'Base URL', 'CROSSREF_API_URL', 'https://api.crossref.org', 'url'),
        field('user_agent', 'User agent', 'CITATION_USER_AGENT', 'SciVerify/0.1.0 (https://github.com/sciverify; citation-resolver)'),
    ]),
    service('openalex', 'OpenAlex', 'Reference metadata search and DOI/full-text discovery. Optional key is currently used by reference metadata search only.', [
        field('base_url', 'Base URL', 'OPENALEX_API_URL', 'https://api.openalex.org', 'url'),
    ], 'OPENALEX_API_KEY'),
    service('semantic_scholar', 'Semantic Scholar', 'Legacy DOI resolver and Graph full-text discovery use separate endpoints. Current consumers do not send an API key.', [
        field('base_url', 'Legacy resolver Base URL', 'SEMANTIC_SCHOLAR_API_URL', 'https://api.semanticscholar.org', 'url'),
        field('retrieval_base_url', 'Graph discovery Base URL', 'SEMANTIC_SCHOLAR_RETRIEVAL_URL', 'https://api.semanticscholar.org/graph/v1', 'url'),
    ]),
    service('europe_pmc', 'Europe PMC', 'Public full-text discovery API. No API key.', [
        field('base_url', 'REST Base URL', 'EUROPEPMC_API_URL', 'https://www.ebi.ac.uk/europepmc/webservices/rest', 'url'),
    ]),
    service('unpaywall', 'Unpaywall', 'Open-access location discovery. Contact email is sent to Unpaywall; no API key.', [
        field('base_url', 'Base URL', 'UNPAYWALL_API_URL', 'https://api.unpaywall.org/v2', 'url'),
        field('email', 'Contact email', 'UNPAYWALL_EMAIL', 'team@sciverify.local'),
    ]),
]
CATALOG = {s['id']: s for s in SERVICES}


def loopback(host):
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host or '').is_loopback
    except ValueError:
        return False


def validate_url(value):
    """No URL-embedded credentials, query secrets, redirects or private destinations."""
    try:
        parsed = urlsplit(value)
        if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or any(c.isspace() for c in value) or '\\' in value):
            raise ValueError()
        port = parsed.port
        if loopback(parsed.hostname):
            if parsed.scheme not in {'http', 'https'}:
                raise ValueError()
        else:
            if parsed.scheme != 'https' or port not in {None, 443}:
                raise ValueError()
            # DNS answers are additionally checked and pinned by PublicHTTPTransport.
            from app.researchguard.source_locator import canonical_url
            canonical_url(value)
    except (ValueError, TypeError):
        raise ValueError('Use an HTTPS public endpoint or an HTTP(S) loopback endpoint without credentials, query or fragment.') from None
    return value.rstrip('/')


def validate_values(spec, values):
    if not isinstance(values, dict) or set(values) != {f['name'] for f in spec['fields']} | ({'connection_source'} if spec['secret_env'] else set()):
        raise ValueError('Submit all fields for this service only.')
    result = {}
    for f in spec['fields']:
        value = values[f['name']]
        if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
            raise ValueError('A field contains invalid text.')
        value = value.strip()
        if f['kind'] == 'url' and value:
            value = validate_url(value)
        if f['kind'] == 'select' and value not in f['options']:
            raise ValueError('Select a supported provider protocol.')
        if f['kind'] == 'number':
            if not value.isdecimal() or not 1 <= int(value) <= (300 if f['name'] == 'timeout' else 1024):
                raise ValueError('Enter a valid positive numeric limit.')
        if f['name'] == 'email' and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid contact email.')
        if f['name'] in {'base_url', 'retrieval_base_url'} and not value:
            # LiteLLM can choose a native endpoint when API base is omitted.
            if spec['id'] not in {'paperqa', 'embedding'}:
                raise ValueError('Base URL is required.')
        if f['name'] == 'model' and not value:
            raise ValueError('Model ID is required.')
        result[f['name']] = value
    if spec['secret_env']:
        source = values['connection_source']
        if source not in ['self', *spec['share_options']]:
            raise ValueError('Select a supported shared connection.')
        result['connection_source'] = source
    return result
