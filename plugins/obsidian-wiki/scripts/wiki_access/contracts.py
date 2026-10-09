"""The v1 wire contract. Configuration and source paths never enter requests."""
import datetime
import json

SCHEMA = 'wiki-access.v1'
QUERY_BYTES = 2048
SEARCH_BYTES = 8000
READ_BYTES = 24000
REQUEST_BYTES = 65536
STORE_BYTES = 128 * 1024 * 1024
WORKER_BYTES = 256 * 1024 * 1024
CODES = frozenset(('ok', 'empty', 'ambiguous', 'not_found', 'disabled',
    'index_unavailable', 'unsupported_schema', 'invalid_request',
    'unsupported_filter', 'generation_stale', 'source_unavailable',
    'permission_refused', 'budget_exhausted', 'invalid_receipt',
    'citation_unresolved', 'citation_not_read'))
FIELDS = {
    'search': ({'query'}, {'limit', 'filters'}),
    'resolve': ({'selector'}, set()),
    'get': ({'page_ids', 'generation'}, {'byte_budget'}),
    'verify_citations': ({'read_receipt', 'citations'}, set()),
    'status': (set(), set()),
    'refresh': (set(), set()),
    'check': (set(), set()),
}
FILTERS = {'category', 'tag', 'evidence_status', 'verification_status',
           'created_from', 'created_to', 'updated_from', 'updated_to'}


class Refusal(Exception):
    """A public error code only; never attach source input to an exception."""
    def __init__(self, code='invalid_request'):
        if code not in CODES:
            raise ValueError('unknown public code')
        self.code = code
        super().__init__(code)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refusal()
        result[key] = value
    return result


def decode(raw):
    if len(raw) > REQUEST_BYTES:
        raise Refusal('budget_exhausted')
    try:
        return json.loads(raw, object_pairs_hook=strict_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(Refusal()))
    except (ValueError, UnicodeError, RecursionError):
        raise Refusal() from None


def text(value, ceiling=2048):
    if not isinstance(value, str) or not value.strip():
        raise Refusal()
    try:
        if len(value.encode('utf-8')) > ceiling:
            raise Refusal()
    except UnicodeError:
        raise Refusal() from None
    if any(ord(c) < 32 for c in value):
        raise Refusal()
    return value


def integer(value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise Refusal()
    return value


def validate_request(request, *, admin=False):
    if type(request) is not dict:
        raise Refusal()
    if request.get('schema') != SCHEMA:
        raise Refusal('unsupported_schema')
    operation = request.get('operation')
    allowed = {'refresh', 'check'} if admin else set(FIELDS) - {'refresh', 'check'}
    if not isinstance(operation, str) or operation not in allowed:
        raise Refusal()
    required, optional = FIELDS[operation]
    keys = set(request) - {'schema', 'operation'}
    if not required <= keys or keys - required - optional:
        raise Refusal()
    result = dict(request)
    if operation == 'search':
        text(result['query'], QUERY_BYTES)
        result['limit'] = integer(result.get('limit', 5), 1, 10)
        filters = result.setdefault('filters', {})
        if type(filters) is not dict or set(filters) - FILTERS:
            raise Refusal('unsupported_filter')
        for key, value in filters.items():
            text(value, 256)
            if key.endswith(('_from', '_to')):
                try:
                    if datetime.date.fromisoformat(value).isoformat() != value:
                        raise ValueError()
                except ValueError:
                    raise Refusal('unsupported_filter') from None
        for field in ('created', 'updated'):
            if filters.get(field+'_from', '') > filters.get(field+'_to', '9999-12-31'):
                raise Refusal('unsupported_filter')
    elif operation == 'resolve':
        selector = result['selector']
        if type(selector) is not dict or set(selector) != {'kind', 'value'}:
            raise Refusal()
        if selector['kind'] not in ('path', 'title', 'alias'):
            raise Refusal()
        text(selector['value'])
    elif operation == 'get':
        ids = result['page_ids']
        if type(ids) is not list or not 1 <= len(ids) <= 5:
            raise Refusal()
        for page_id in ids:
            text(page_id, 128)
        if len(set(ids)) != len(ids):
            raise Refusal()
        text(result['generation'], 128)
        result['byte_budget'] = integer(result.get('byte_budget', READ_BYTES), 256, READ_BYTES)
    elif operation == 'verify_citations':
        text(result['read_receipt'], REQUEST_BYTES)
        citations = result['citations']
        if type(citations) is not list or not 1 <= len(citations) <= 100:
            raise Refusal()
        for citation in citations:
            if type(citation) is not dict or set(citation) != {'target', 'page_id', 'start', 'end', 'quote'}:
                raise Refusal()
            text(citation['target'])
            text(citation['page_id'], 128)
            text(citation['quote'], READ_BYTES)
            integer(citation['start'], 0, STORE_BYTES)
            integer(citation['end'], citation['start']+1, STORE_BYTES)
    return result


def response(operation, value, *, state='ok', generation=None):
    result = {'schema': SCHEMA, 'ok': True, 'operation': operation,
              'state': state, 'value': value}
    if generation is not None:
        result['generation'] = generation
    return result


def error(operation, code):
    return {'schema': SCHEMA, 'ok': False,
            'operation': operation if operation in FIELDS else 'unknown',
            'state': code, 'error': {'code': code}}
