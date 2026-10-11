"""Complete authoritative projections; budget the entire buffered wire response."""
from .contracts import Refusal, encode, response
from . import policy


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
    if len(encode(result)) > request['byte_budget']:
        raise Refusal('budget_exhausted')
    for page in indexed:
        evidence = read_page(manager, page, pin.generation)
        omission = next(item for item in value['omitted'] if item['page_id'] == page['page_id'])
        value['omitted'].remove(omission); value['pages'].append(evidence)
        value['body_bytes'] += evidence['body_bytes']
        if len(encode(result)) > request['byte_budget']:
            value['pages'].pop(); value['body_bytes'] -= evidence['body_bytes']
            value['omitted'].append(omission)
    return result
