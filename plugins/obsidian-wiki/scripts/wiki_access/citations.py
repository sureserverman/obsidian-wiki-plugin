"""Read-bound UTF-8 provenance only. A structural verdict certifies no facts."""
import time
from .contracts import Refusal, response
from .evidence import descriptor, read_page, renderable_locator, verify_receipt


def source_spans(page, start, end):
    result=[]; cursor=start
    for span in page['mapping']:
        lo=max(start,span['start']); hi=min(end,span['end'])
        if lo >= hi: continue
        if lo != cursor: raise Refusal('citation_not_read')
        source=span['source_start']+lo-span['start']
        result.append({'source_start':source,'source_end':source+hi-lo})
        cursor=hi
    if cursor != end: raise Refusal('citation_not_read')
    return result


def occurrence(page, citation, index):
    denied={'occurrence':index,'valid':False,'target_verified':False,
            'read_verified':False,'code':'citation_unresolved'}
    if page is None:
        return dict(denied,code='citation_not_read')
    target=citation['target']; locator,mark,fragment=target.partition('#')
    if (locator != page['locator'] or not renderable_locator(locator)
            or any(c in fragment for c in '#|:%[]<>\r\n') or (mark and not fragment)):
        return denied
    start,end=citation['start'],citation['end']; body=page['body'].encode('utf-8')
    if end > len(body) or body[start:end] != citation['quote'].encode('utf-8'):
        return dict(denied,code='citation_not_read')
    try: spans=source_spans(page,start,end)
    except Refusal: return dict(denied,code='citation_not_read')
    normalized=locator; anchor_state='page'
    if mark:
        if fragment.startswith('^'):
            matches=[b for b in page['anchors']['blocks'] if b['name']==fragment[1:] and b['unique']]
            if len(matches)!=1:return denied
            anchor=matches[0]
            if not anchor['start'] <= start < end <= anchor['end']:return dict(denied,code='citation_not_read')
            normalized=anchor['target'];anchor_state='block'
        else:
            matches=[h for h in page['anchors']['headings'] if h['name']==fragment]
            if not matches:return denied
            if len(matches)!=1 or not matches[0]['unique']:
                anchor_state='downgraded_to_page'
            else:
                anchor=matches[0]
                if not anchor['start'] <= start < end <= anchor['end']:return dict(denied,code='citation_not_read')
                normalized=anchor['target'];anchor_state='heading'
    return {'occurrence':index,'valid':True,'target_verified':True,'read_verified':True,
            'code':'ok','target':normalized,
            'page_id':page['page_id'],'start':start,'end':end,
            'source_spans':spans,'anchor_state':anchor_state}


def verify(manager, db, pin, request):
    payload=verify_receipt(manager,pin,request['read_receipt'])
    pages={}
    for signed in payload['pages']:
        indexed=db.page(signed['page_id'])
        if indexed is None:raise Refusal('invalid_receipt')
        page=read_page(manager,indexed,pin.generation)
        if descriptor(page)!=signed:raise Refusal('invalid_receipt')
        pages[page['page_id']]=page
    checks=[occurrence(pages.get(c['page_id']),c,i) for i,c in enumerate(request['citations'])]
    return response('verify_citations',{'verification':'structural_only','verified_at':int(time.time()),
                    'citations':checks},generation=pin.generation)
