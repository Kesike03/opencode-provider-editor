"""Provider metadata, validation and offline diagnostics."""
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import json
import re
from i18n import tr
from jsonc_editor import loads

PROVIDER_FIELDS = ('name', 'baseURL', 'headers')
MODEL_FIELDS = ('name', 'reasoning', 'tool_call', 'attachment', 'interleaved',
                'limit.context', 'limit.output', 'variants')
BOOL_FIELDS = ('reasoning', 'tool_call', 'attachment')
MISSING = object()
PROVIDER_ID = re.compile(r'[a-z0-9_-]+\Z')


def get_field(obj, field):
    for key in field.split('.'):
        if not isinstance(obj, dict) or key not in obj:
            return MISSING
        obj = obj[key]
    return obj


def validate_field(field, value):
    if field in ('name', 'baseURL') and not isinstance(value, str):
        raise ValueError(tr('core.string_required'))
    if field in BOOL_FIELDS and type(value) is not bool:
        raise ValueError(tr('core.bool_required'))
    if field.startswith('limit.') and (type(value) is not int or value <= 0):
        raise ValueError(tr('core.positive_int'))
    if field == 'interleaved':
        valid = type(value) is bool or (isinstance(value, str) and bool(value.strip()))
        valid = valid or (isinstance(value, dict) and set(value) == {'field'}
                          and isinstance(value['field'], str) and bool(value['field'].strip()))
        if not valid:
            raise ValueError(tr('core.interleaved_invalid'))
    if field == 'headers' and (not isinstance(value, dict) or any(not isinstance(v, str) for v in value.values())):
        raise ValueError(tr('core.headers_invalid'))
    if field == 'variants':
        if not isinstance(value, dict) or any(not isinstance(v, dict) for v in value.values()):
            raise ValueError(tr('core.variants_invalid'))
        for variant in value.values():
            if 'disabled' in variant and type(variant['disabled']) is not bool:
                raise ValueError(tr('core.variant_disabled_bool'))
    return value


def parse_field(field, text):
    if field in ('name', 'baseURL'):
        return validate_field(field, text)
    return validate_field(field, loads(text))


def mask(value):
    if not isinstance(value, str):
        return tr('core.malformed')
    prefix = value[:4] if len(value) > 4 else '•' * len(value)
    return tr('core.masked', prefix=prefix, length=len(value))


def _key_source(provider_id, provider, auth=None):
    options = provider.get('options', {})
    if 'apiKey' in options:
        key = options['apiKey']
        if isinstance(key, str) and ('{env:' in key or '{file:' in key):
            return 'reference', tr('core.key.reference', value=key)
        return 'inline', tr('core.key.inline', value=mask(key))
    record = (auth or {}).get(provider_id)
    if isinstance(record, dict):
        if record.get('type') == 'api' and 'key' in record:
            return 'auth_api', tr('core.key.auth_api', value=mask(record['key']))
        if record.get('type') == 'oauth':
            return 'auth_oauth', tr('core.key.auth_oauth')
        return 'auth_unknown', tr('core.key.auth_unknown')
    if auth is None:
        return 'unconfirmed', tr('core.key.unconfirmed')
    return 'missing', tr('core.key.missing')


def key_source(provider_id, provider, auth=None):
    return _key_source(provider_id, provider, auth)[1]


def build_provider(pid, name, base_url, api_key, model_ids, headers, native=False):
    if not PROVIDER_ID.fullmatch(pid):
        raise ValueError(tr('core.provider_id_invalid'))
    if not native and (not name.strip() or not base_url.strip()):
        raise ValueError(tr('core.custom_required'))
    if base_url and not valid_http_url(base_url):
        raise ValueError(tr('core.base_url_invalid'))
    if any(not isinstance(key, str) or not key.strip() or '#' in key for key in model_ids):
        raise ValueError(tr('core.model_id_invalid'))
    if len(model_ids) != len(set(model_ids)):
        raise ValueError(tr('core.model_id_duplicate'))
    if any(not valid_header(key, value) for key, value in headers.items()):
        raise ValueError(tr('core.header_invalid'))
    options = {}
    if base_url:
        options['baseURL'] = base_url
    if api_key:
        options['apiKey'] = api_key
    if headers:
        options['headers'] = headers
    provider = {} if native else {'npm': '@ai-sdk/openai-compatible'}
    if name:
        provider['name'] = name
    if options:
        provider['options'] = options
    if model_ids:
        provider['models'] = {mid: {} for mid in model_ids}
    return provider


def valid_http_url(value):
    try:
        parsed = urlparse(value)
        return (parsed.scheme in ('http', 'https') and bool(parsed.hostname)
                and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def valid_header(key, value):
    return (isinstance(key, str) and isinstance(value, str)
            and bool(re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key))
            and bool(value.strip()) and '\r' not in value and '\n' not in value)


def models_endpoint(base_url):
    if not valid_http_url(base_url):
        raise ValueError(tr('core.endpoint_invalid'))
    url = base_url.rstrip('/')
    return url if urlparse(url).path.endswith('/models') else url + '/models'


def fetch_model_ids(base_url, api_key='', headers=None):
    url = models_endpoint(base_url)
    if '{env:' in api_key or '{file:' in api_key:
        raise ValueError(tr('core.api_key_reference'))
    if '\r' in api_key or '\n' in api_key:
        raise ValueError(tr('core.api_key_newline'))
    request_headers = {'Accept': 'application/json'}
    if api_key:
        request_headers['Authorization'] = 'Bearer ' + api_key
    for key, value in (headers or {}).items():
        if not valid_header(key, value):
            raise ValueError(tr('core.header_invalid'))
        if key.lower() == 'authorization':
            request_headers.pop('Authorization', None)
        request_headers[key] = value
    request = Request(url, headers=request_headers)
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
    except Exception as exc:
        from urllib.error import HTTPError, URLError
        if isinstance(exc, HTTPError):
            raise ValueError(tr('core.http_error', code=exc.code)) from exc
        if isinstance(exc, (URLError, TimeoutError, OSError)):
            raise ValueError(tr('core.connection_error')) from exc
        raise
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError(tr('core.response_too_large'))
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError(tr('core.invalid_json')) from exc
    items = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError(tr('core.data_missing'))
    ids = list(dict.fromkeys(item['id'] for item in items
                             if isinstance(item, dict) and isinstance(item.get('id'), str) and item['id'].strip()))
    if not ids:
        raise ValueError(tr('core.no_model_ids'))
    return ids


def diagnose(data, auth=None):
    results = []
    def add(level, location, message):
        results.append((level, location, message))
    providers = data.get('provider', {})
    if not providers:
        add('info', 'provider', tr('diag.no_providers'))
    for pid, provider in providers.items():
        options = provider.get('options', {})
        url = options.get('baseURL')
        if not url:
            add('info', pid, tr('diag.no_base_url'))
        elif not isinstance(url, str) or (not url.startswith(('{env:', '{file:')) and (urlparse(url).scheme not in ('http', 'https') or not urlparse(url).netloc)):
            add('warning', pid, tr('diag.bad_base_url'))
        for field in PROVIDER_FIELDS:
            val = get_field(provider if field == 'name' else options, field)
            if val is not MISSING:
                try:
                    validate_field(field, val)
                except ValueError as exc:
                    add('error', pid + '/' + field, str(exc))
        if 'headers' in provider:
            add('warning', pid, tr('diag.top_headers'))
        if not provider.get('npm'):
            add('info', pid, tr('diag.no_npm'))
        if pid in data.get('disabled_providers', []):
            add('warning', pid, tr('diag.disabled'))
        enabled = data.get('enabled_providers')
        if isinstance(enabled, list) and pid not in enabled:
            add('warning', pid, tr('diag.not_enabled'))
        if _key_source(pid, provider, auth)[0] in ('reference', 'unconfirmed', 'missing'):
            add('info', pid, tr('diag.key_unconfirmed'))
        models = provider.get('models', {})
        if not models:
            add('info', pid, tr('diag.no_models'))
        for mid, model in models.items():
            loc = pid + '/' + mid
            for field in MODEL_FIELDS:
                val = get_field(model, field)
                if val is not MISSING:
                    try:
                        validate_field(field, val)
                    except ValueError as exc:
                        add('error', loc + '/' + field, str(exc))
            if 'reasoning' not in model:
                add('info', loc, tr('diag.no_reasoning'))
            if model.get('reasoning') is True:
                add('info', loc, tr('diag.reasoning_declared'))
            if model.get('interleaved') and model.get('reasoning') is False:
                add('warning', loc, tr('diag.interleaved_false'))
            limits = model.get('limit', {})
            for field in ('context', 'output'):
                if field not in limits:
                    add('warning' if 'limit' in model else 'info', loc, tr('diag.no_limit', field=field))
            context, output = limits.get('context'), limits.get('output')
            if type(context) is int and type(output) is int and output > context:
                add('warning', loc, tr('diag.output_gt_context'))
            if mid in provider.get('blacklist', []):
                add('warning', loc, tr('diag.blacklist'))
            if isinstance(provider.get('whitelist'), list) and mid not in provider['whitelist']:
                add('warning', loc, tr('diag.whitelist'))
    add('note', tr('diag.permissions_location'), tr('diag.permissions'))
    return results
