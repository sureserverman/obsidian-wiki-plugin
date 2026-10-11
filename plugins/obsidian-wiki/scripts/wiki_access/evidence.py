"""Complete authoritative projections; budget the entire buffered wire response."""
import base64
import hashlib
import hmac
import re
import time

from .contracts import Refusal, READ_BYTES, decode, encode, response
from . import policy

RECEIPT_VERSION = 'wiki-read-receipt.v1'
RECEIPT_DOMAIN = b'obsidian-wiki/read-bundle/v1\x00'
RECEIPT_SECONDS = 900


def renderable_locator(locator):
    return not any(c in locator for c in '#|^:%[]<>\r\n')


def anchor_inventory(raw, body, locator):
    """Count identities in authoritative content, expose only projected anchors."""
    def scan(text):
        heads=[]; blocks=[]; fence=None; offset=0; paragraph=0
        html_comment=False; percent_comment=False; uncertain_html=False; math=False; list_context=False
        for line in text.splitlines(keepends=True):
            end=offset+len(line.encode('utf-8'))
            # This deliberately supports a small rendered-anchor subset. Code,
            # comments and uncertain structured blocks cannot manufacture anchors.
            if fence is not None:
                _,fence=policy.heading(line,fence); paragraph=end; offset=end; continue
            comment_line=html_comment or '<!--' in line or percent_comment or '%%' in line
            # Delimiter order matters: one line can close a comment and open
            # another. HTML comments do not nest; an opener inside one is inert.
            for delimiter in re.finditer(r'<!--|-->',line):
                if delimiter[0]=='<!--' and not html_comment:html_comment=True
                elif delimiter[0]=='-->' and html_comment:html_comment=False
            if line.count('%%') % 2:percent_comment=not percent_comment
            # Also catch a tag following a closed comment on this same line.
            # Seeing a tag even within a comment is conservatively uncertain.
            if re.search(r'<(?:/?[A-Za-z]|\?|!(?!--))',line):uncertain_html=True
            if comment_line:
                paragraph=end; offset=end; continue
            # Generic HTML rendering is outside the declared subset. Once tags
            # occur, refuse later anchors rather than guessing nesting, attributes,
            # same-line transitions or Markdown inside HTML. Page evidence remains.
            if uncertain_html or re.match(r'^(?: {4}|\t| {0,3}>)',line):
                paragraph=end; offset=end; continue
            if line.strip()=='$$':math=not math;paragraph=end;offset=end;continue
            if math:paragraph=end;offset=end;continue
            head,fence=policy.heading(line,fence)
            if fence is not None:
                paragraph=end;offset=end;continue
            if head:
                heads.append({'name':head[1], 'level':head[0], 'start':offset})
                paragraph=end;list_context=False
            item=bool(re.match(r'^ {0,3}(?:[-+*]|[0-9]+[.)])[ \t]+\S',line))
            if item:paragraph=offset;list_context=True
            if not head and (not list_context or item):
                block=re.search(r'(?:^|\s)\^([A-Za-z0-9-]{1,128})[ \t]*\r?\n?$',line)
                # Standalone IDs on structured blocks are outside this subset;
                # page citations still verify the exact read quote.
                if block and line[:block.start()].strip():
                    blocks.append({'name':block[1], 'start':paragraph, 'end':end})
            if not line.strip() or re.fullmatch(r'[ \t]*[-=*]{3,}[ \t]*\r?\n?',line):
                paragraph=end;list_context=False
            offset=end
        for i, head in enumerate(heads):
            head['end']=next((h['start'] for h in heads[i+1:] if h['level'] <= head['level']),offset)
        return heads,blocks
    source_heads,source_blocks=scan(raw.decode('utf-8'))
    heads,blocks=scan(body)
    safe=renderable_locator(locator)
    targets=[locator] if safe else []
    for head in heads:
        unique=sum(h['name'].casefold()==head['name'].casefold() for h in source_heads)==1
        renderable=bool(re.fullmatch(r"[\w .,'()–—-]+",head['name']))
        head['unique']=unique and renderable and safe
        head['target']=locator+'#'+head['name'] if head['unique'] else locator
        if head['unique']: targets.append(head['target'])
    for block in blocks:
        block['unique']=safe and sum(b['name']==block['name'] for b in source_blocks)==1
        block['target']=locator+'#^'+block['name']
        if block['unique']:targets.append(block['target'])
    return {'headings':heads,'blocks':blocks},list(dict.fromkeys(targets))


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
    anchors,targets=anchor_inventory(raw,page['body'],page['locator'])
    return dict(page, page_id=indexed['page_id'], generation=generation,
                complete=True, body_bytes=len(page['body'].encode('utf-8')),
                read_spans=[{'start':0, 'end':len(page['body'].encode('utf-8'))}],
                anchors=anchors, citation_targets=targets)


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
