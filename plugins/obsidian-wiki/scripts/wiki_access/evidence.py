"""Complete authoritative projections; budget the entire buffered wire response."""
import base64
import hashlib
import hmac
import time

from .contracts import Refusal, READ_BYTES, decode, encode, response
from . import policy

RECEIPT_VERSION = 'wiki-read-receipt.v1'
RECEIPT_DOMAIN = b'obsidian-wiki/read-bundle/v1\x00'
RECEIPT_SECONDS = 900


def descriptor(page):
    return {'page_id':page['page_id'], 'locator':page['locator'],
            'source_hash':page['source_hash'], 'projection_hash':page['projection_hash'],
            'body_bytes':page['body_bytes'], 'read_spans':page['read_spans'],
            'evidence_hash':policy.digest(encode(page))}


def token_for(payload, key):
    raw = encode(payload)
    signature = hmac.new(key, RECEIPT_DOMAIN+raw, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(raw).decode('ascii')+'.'+signature


def seal(result, key, issued):
    value = result['value']
    if not value['pages']:
        value['read_receipt'] = None
        return
    payload = {'schema':RECEIPT_VERSION, 'generation':result['generation'],
               'issued':issued, 'expires':issued+RECEIPT_SECONDS,
               'body_bytes':value['body_bytes'], 'response_bytes':0,
               'pages':[descriptor(page) for page in value['pages']]}
    # A receipt includes the full response byte count. Iterate only its digit width;
    # the HMAC's width is constant, so the fixed point takes at most four encodes.
    for _ in range(8):
        value['read_receipt'] = token_for(payload, key)
        size = len(encode(result))
        if size == payload['response_bytes']: return
        payload['response_bytes'] = size
    raise Refusal('budget_exhausted')


def verify_receipt(manager, pin, token):
    """Authenticate stateless provenance. Current source checks remain mandatory."""
    try:
        if type(token) is not str or len(token) > READ_BYTES: raise ValueError()
        encoded, signature = token.split('.')
        raw = base64.b64decode(encoded, altchars=b'-_', validate=True)
        if base64.urlsafe_b64encode(raw).decode('ascii') != encoded: raise ValueError()
        key = manager.receipt_key()
        expected = hmac.new(key, RECEIPT_DOMAIN+raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,expected): raise ValueError()
        payload = decode(raw)
        if (type(payload) is not dict or set(payload) != {'schema','generation','issued','expires','body_bytes','response_bytes','pages'}
                or payload['schema'] != RECEIPT_VERSION or encode(payload) != raw
                or payload['generation'] != pin.generation
                or type(payload['issued']) is not int or type(payload['expires']) is not int
                or payload['expires'] != payload['issued']+RECEIPT_SECONDS
                or not payload['issued'] <= time.time() < payload['expires']
                or type(payload['response_bytes']) is not int or not 0 < payload['response_bytes'] <= READ_BYTES
                or type(payload['body_bytes']) is not int or not 0 <= payload['body_bytes'] < READ_BYTES
                or type(payload['pages']) is not list or not 1 <= len(payload['pages']) <= 5):
            raise ValueError()
        ids = set(); total = 0
        for page in payload['pages']:
            if (type(page) is not dict or set(page) != {'page_id','locator','source_hash','projection_hash','body_bytes','read_spans','evidence_hash'}
                    or type(page['page_id']) is not str or page['page_id'] in ids
                    or type(page['body_bytes']) is not int or not 0 <= page['body_bytes'] < READ_BYTES
                    or page['read_spans'] != [{'start':0,'end':page['body_bytes']}]
                    or any(type(page[k]) is not str for k in ('locator','source_hash','projection_hash','evidence_hash'))):
                raise ValueError()
            ids.add(page['page_id']); total += page['body_bytes']
        if total != payload['body_bytes']: raise ValueError()
        pin.check()
        if not hmac.compare_digest(key,manager.receipt_key()): raise ValueError()
        return payload
    except (Refusal, ValueError, TypeError, UnicodeError, KeyError, OSError):
        raise Refusal('invalid_receipt') from None


def read_page(manager, indexed, generation):
    raw = policy.safe_read(manager.root, indexed['locator'])
    page = policy.project(indexed['locator'], raw, manager.policy)
    # Hashing, projection and maps all describe these same authoritative bytes.
    for key, value in page.items():
        if indexed[key] != value:
            raise Refusal('generation_stale')
    return dict(page, page_id=indexed['page_id'], generation=generation,
                complete=True, body_bytes=len(page['body'].encode('utf-8')),
                read_spans=[{'start':0, 'end':len(page['body'].encode('utf-8'))}],
                citation_targets=[page['locator']])


def bundle(manager, db, pin, request):
    if request['generation'] != pin.generation:
        raise Refusal('generation_stale')
    # Resolve all IDs before doing a single content read or disclosing a partial set.
    indexed = [db.page(page_id) for page_id in request['page_ids']]
    if any(page is None for page in indexed):
        raise Refusal('invalid_request')
    admitted = {p['locator']:p for p in pin.manifest['snapshot']['inventory'] if p['eligible']}
    for page in indexed:
        record = admitted.get(page['locator'])
        if not record or any(page[k] != record[k] for k in ('source_hash','projection_hash')):
            raise Refusal('index_unavailable')
    value = {'pages':[], 'omitted':[{'page_id':p['page_id'], 'reason':'over_budget'} for p in indexed],
             'body_bytes':0, 'read_receipt':None}
    result = response('get', value, generation=pin.generation)
    key = manager.receipt_key(); issued = int(time.time())
    if len(encode(result)) > request['byte_budget']:
        raise Refusal('budget_exhausted')
    for page in indexed:
        evidence = read_page(manager, page, pin.generation)
        omission = next(item for item in value['omitted'] if item['page_id'] == page['page_id'])
        value['omitted'].remove(omission); value['pages'].append(evidence)
        value['body_bytes'] += evidence['body_bytes']
        seal(result, key, issued)
        if len(encode(result)) > request['byte_budget']:
            value['pages'].pop(); value['body_bytes'] -= evidence['body_bytes']
            value['omitted'].append(omission)
            seal(result, key, issued)
    return result
