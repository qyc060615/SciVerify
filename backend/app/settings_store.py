"""Local settings overlay. Save stages changes; only process startup applies them."""
import copy
import ctypes
import hashlib
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from urllib.parse import urlsplit, urlunsplit

from app.settings_catalog import SERVICES, CATALOG, validate_values

_LOCK = RLock()
_ACTIVE = None


class SettingsError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def settings_path():
    return Path(os.getenv('RESEARCHGUARD_SETTINGS_FILE') or Path(__file__).resolve().parents[1] / '.researchguard-settings.bin')


def _dpapi(content, encrypt):
    """Windows current-user DPAPI; ciphertext is bound to the current OS user."""
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(content)
    source = Blob(len(content), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    function = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise SettingsError('The OS could not protect or unlock saved API settings.', 503)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def _read():
    path = settings_path()
    try:
        if path.is_symlink():
            raise SettingsError('The settings storage is not a regular private file.', 503)
        if not path.exists():
            return {'version': 1, 'revision': 0, 'services': {}}
        if path.stat().st_size > 128 * 1024:
            raise ValueError()
        content = path.read_bytes()
        if os.name == 'nt' and content.startswith(b'W1'):
            raw = _dpapi(content[2:], False)
        elif os.name != 'nt' and content.startswith(b'U1') and not path.stat().st_mode & 0o077:
            raw = content[2:]
        else:
            raise ValueError()
        value = json.loads(raw)
        if (value.get('version') != 1 or type(value.get('revision')) is not int or value['revision'] < 0
                or not isinstance(value.get('services'), dict) or not value['services'].keys() <= CATALOG.keys()):
            raise ValueError()
        for id, profile in value['services'].items():
            validate_values(CATALOG[id], {k: v for k, v in profile.items() if k != '_key'})
            if not isinstance(profile.get('_key', ''), str):
                raise ValueError()
        return value
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        if isinstance(exc, SettingsError):
            raise
        raise SettingsError('Saved API settings could not be read. The existing file was left untouched.', 503) from None


def _write(value):
    path = settings_path()
    if path.is_symlink():
        raise SettingsError('The settings storage is not a regular private file.', 503)
    raw = json.dumps(value, ensure_ascii=False).encode('utf8')
    content = b'W1' + _dpapi(raw, True) if os.name == 'nt' else b'U1' + raw
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.researchguard-settings-', dir=path.parent)
    try:
        os.chmod(name, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def environment_profiles():
    result = {}
    for spec in SERVICES:
        values = {f['name']: os.getenv(f['env'], f['default']) for f in spec['fields']}
        if spec['secret_env']:
            values.update(connection_source='self', _key=os.getenv(spec['secret_env'], ''))
        result[spec['id']] = values
    # Recognize the existing interpolated LLM key without duplicating it.
    for id in ['paperqa', 'embedding']:
        row, llm = result[id], result['llm']
        if row['_key'] and row['_key'] == llm['_key'] and row['base_url'] == llm['base_url']:
            row.update(connection_source='llm', _key='')
    return result


def effective(profiles, id):
    result = copy.deepcopy(profiles[id])
    source = result.get('connection_source', 'self')
    if source != 'self':
        shared = effective(profiles, source)
        result.update(base_url=shared['base_url'], _key=shared.get('_key', ''))
    return result


def apply_saved_settings():
    """Called only at startup, never by Save/Test routes."""
    global _ACTIVE
    with _LOCK:
        profiles = environment_profiles()
        stored = _read()['services']
        profiles.update(stored)
        def overridden(id):
            source = profiles[id].get('connection_source', 'self')
            return id in stored or source != 'self' and overridden(source)
        for spec in SERVICES:
            if not overridden(spec['id']):
                continue
            row = effective(profiles, spec['id'])
            for f in spec['fields']:
                os.environ[f['env']] = row[f['name']]
            if spec['secret_env']:
                os.environ[spec['secret_env']] = row.get('_key', '')
        _ACTIVE = copy.deepcopy(profiles)


def active_profiles():
    return copy.deepcopy(_ACTIVE if _ACTIVE is not None else environment_profiles())


def saved_profiles():
    stored = _read()
    profiles = active_profiles()
    profiles.update(stored['services'])
    return stored, profiles


def fingerprint(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()


def _public_url(value):
    if not value:
        return value
    try:
        p = urlsplit(value)
        host = p.hostname or ''
        if ':' in host:
            host = '[' + host + ']'
        return urlunsplit((p.scheme, host + (':' + str(p.port) if p.port else ''), p.path, '', ''))
    except ValueError:
        return ''


def public_settings():
    with _LOCK:
        stored, saved = saved_profiles()
        active = active_profiles()
        rows = []
        for spec in SERVICES:
            id = spec['id']
            row = effective(saved, id)
            current = effective(active, id)
            rows.append({
                'id': id, 'label': spec['label'], 'purpose': spec['purpose'],
                'fields': [{k: v for k, v in f.items() if k not in {'env', 'default'}} for f in spec['fields']],
                'values': {k: _public_url(v) if k.endswith('base_url') else v for k, v in saved[id].items() if k != '_key'},
                'has_key': bool(row.get('_key')), 'has_own_key': bool(saved[id].get('_key')),
                'supports_key': bool(spec['secret_env']), 'share_options': spec['share_options'],
                'paid_test': spec['paid_test'], 'pending_restart': row != current,
                'active_model': current.get('model'), 'active_base_url': _public_url(current.get('base_url')),
                'active_has_key': bool(current.get('_key')),
            })
        return {'revision': stored['revision'], 'services': rows, 'restart_required': any(r['pending_restart'] for r in rows)}


def candidate(id, values, key=None, clear=False, *, profiles=None):
    if id not in CATALOG:
        raise SettingsError('Unknown API service.', 404)
    profiles = copy.deepcopy(profiles if profiles is not None else saved_profiles()[1])
    spec = CATALOG[id]
    try:
        row = validate_values(spec, values)
        if type(clear) is not bool or key is not None and (not isinstance(key, str) or len(key) > 8192 or any(ord(c) < 32 or ord(c) > 126 for c in key)):
            raise ValueError('Invalid key input.')
        if not spec['secret_env'] and (key or clear):
            raise ValueError('This service does not use an API key.')
        if key and clear:
            raise ValueError('Choose either replacing or clearing a key.')
        if spec['secret_env']:
            row['_key'] = '' if clear else key.strip() if key and key.strip() else profiles[id].get('_key', '')
            if row['connection_source'] != 'self':
                if key or clear:
                    raise ValueError('Edit the shared connection to change its key.')
                row['_key'] = ''
        profiles[id] = row
        return profiles
    except ValueError as exc:
        raise SettingsError(str(exc)) from None


def save_connection(id, values, key, clear, revision):
    with _LOCK:
        stored, profiles = saved_profiles()
        if type(revision) is not int or revision != stored['revision']:
            raise SettingsError('Settings changed elsewhere. Reload before saving; your draft has been kept.', 409)
        profiles = candidate(id, values, key, clear, profiles=profiles)
        stored['services'][id] = profiles[id]
        stored['revision'] += 1
        try:
            _write(stored)
        except OSError:
            raise SettingsError('The API settings could not be saved. Check local storage permissions.', 503) from None
        return public_settings()
