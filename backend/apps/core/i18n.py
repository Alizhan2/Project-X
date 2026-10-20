"""Small explicit message catalog; never translate machine-readable identifiers or stored snapshots."""
import json
import re
from contextvars import ContextVar
from pathlib import Path

from django.utils.cache import patch_vary_headers
from django.utils.translation.trans_real import parse_accept_lang_header

CATALOG = json.loads((Path(__file__).parent / 'locales' / 'messages.json').read_text())
_language = ContextVar('doedu_language', default='en')


def language():
    return _language.get()


def negotiate(header):
    for code, quality in parse_accept_lang_header(header):
        base = code.split('-')[0]
        if quality > 0 and base in ('en', 'ru', 'kk'):
            return base
    return 'en'


_PATTERNS = []
for _source in CATALOG:
    _keys = re.findall(r'\{(\w+)\}', _source)
    if _keys:
        _parts = re.split(r'(\{\w+\})', _source)
        _pattern = ''.join('(.+?)' if re.fullmatch(r'\{\w+\}', part) else re.escape(part) for part in _parts)
        _PATTERNS.append((_source, _keys, re.compile('^' + _pattern + '$', re.S)))

_PATTERNS.sort(key=lambda entry: len(re.sub(r'\{\w+\}', '', entry[0])), reverse=True)

def tr(source, *values, lang=None, _depth=0):
    lang = lang or language()
    if lang not in ('ru', 'kk'):
        lang = 'en'
    key, params = source, {str(i): str(v) for i, v in enumerate(values)}
    if source not in CATALOG and _depth < 4:
        for candidate, names, pattern in _PATTERNS:
            match = pattern.fullmatch(source)
            if match:
                key = candidate
                params = {name: tr(value, lang=lang, _depth=_depth + 1) for name, value in zip(names, match.groups())}
                break
    result = CATALOG.get(key, {}).get(lang, key)
    return re.sub(r'\{(\w+)\}', lambda m: params.get(m[1], m[0]), result)


# These are presentation fields. Everything else, including reference/status/code/mode,
# stays byte-for-byte compatible with the API contract and booking snapshots.
DISPLAY_FIELDS = {'detail', 'message', 'notice', 'title', 'body', 'cancellation_policy', 'policy_name', 'reason_text', 'warning', 'simulated_notice', 'status_label', 'failure_reason', 'reason'}
PROTECTED_FIELDS = {'code', 'status', 'kind', 'mode', 'reference', 'request_id', 'currency', 'id', 'note'}


def localize_payload(value, errors=False, display=False):
    if isinstance(value, dict):
        return {key: (item if key in PROTECTED_FIELDS else localize_payload(item, errors, display or key in DISPLAY_FIELDS))
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [localize_payload(item, errors, display) for item in value]
    if isinstance(value, str) and (display or errors):
        return tr(value)
    return value


class LanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        selected = negotiate(request.headers.get('Accept-Language', ''))
        request.LANGUAGE_CODE = selected
        token = _language.set(selected)
        try:
            response = self.get_response(request)
            # Django renders DRF responses before returning through middleware. JSON-only
            # translation preserves error envelopes; binary downloads use tr during generation.
            if request.path.startswith('/api/') and response.get('Content-Type', '').startswith('application/json'):
                data = json.loads(response.content)
                response.content = json.dumps(localize_payload(data, response.status_code >= 400), ensure_ascii=False).encode()
                if response.has_header('Content-Length'):
                    response['Content-Length'] = str(len(response.content))
            response['Content-Language'] = selected
            patch_vary_headers(response, ['Accept-Language'])
            return response
        finally:
            _language.reset(token)


def place_name(name):
    return CATALOG.get('place:' + name, {}).get(language(), name)
