"""Explicit model-free current-source qualification; no writes to source notes."""
import math
from pathlib import Path
import resource
import tempfile
import time

from wiki_access.contracts import Refusal, encode
from wiki_access.generation import snapshot
from wiki_access.policy import Policy, project


def private_suite(manifest, development, *, trace):
    from wiki_access_acceptance import Probe, fingerprint, validate_manifest
    from wiki_client_acceptance import write_private
    from wiki_access.cli import resolve_source
    if set(manifest) != {'schema','source','policy','workload','fingerprint'} or manifest['schema'] != 'wiki-private-acceptance.v1':
        raise Refusal()
    if manifest['fingerprint'] != fingerprint({k:v for k,v in manifest.items() if k!='fingerprint'}):
        raise Refusal()
    if manifest['source'] != resolve_source() or set(manifest['policy']) != {'categories','portfolio'}:
        raise Refusal()
    policy=Policy(manifest['policy']['categories'],manifest['policy']['portfolio'])
    workload=manifest['workload'];counts=validate_manifest(workload,development=development,policy=policy,control_checks=False)
    if workload['kind']!='acceptance':raise Refusal()
    # Raw input and support remain private. Project each selected policy explicitly;
    # the real-source snapshot must match every frozen source and projection hash.
    expected={n['locator']:project(n['locator'],n['raw'].encode(),policy) for n in workload['notes']}
    with tempfile.TemporaryDirectory(prefix='wiki-private-') as tmp:
        probe=Probe(tmp,None,source=manifest['source'],policy=manifest['policy'])
        started=time.monotonic();before,source_pages=snapshot(probe.root,policy);scan=time.monotonic()-started
        current={n['locator']:n for n in before['inventory'] if n['eligible']}
        for locator,page in expected.items():
            if locator not in current or current[locator]['source_hash']!=page['source_hash'] or current[locator]['projection_hash']!=page['projection_hash']:
                raise Refusal()
        cold=probe.call({'operation':'status'})
        if cold['ok'] or not probe.call({'operation':'refresh'},True)['ok']:raise Refusal()
        hits={kind:0 for kind in counts};samples=[];exact=0;exact_total=0;citations=0
        for question in workload['questions']:
            response=probe.call({'operation':'search','query':question['query'],'limit':5})
            samples.append(probe.timings[-1][1])
            hits[question['class']]+=int(question['note'] in [p['locator'] for p in response.get('value',{}).get('pages',[])])
            page=expected[question['note']]
            for kind,value in [('path',question['note']),('title',page['metadata']['title'])]+[('alias',a) for a in page['metadata'].get('aliases',[])]:
                response=probe.call({'operation':'resolve','selector':{'kind':kind,'value':value}})
                # Resolution is judged against all eligible pages in the source,
                # not only the frozen questions; ambiguous matches are explicit.
                matches=[]
                for candidate in source_pages:
                    choices=([candidate['locator']] if kind=='path' else
                             [candidate['metadata']['title']] if kind=='title' else candidate['metadata'].get('aliases',[]))
                    if value.casefold() in [choice.casefold() for choice in choices]:matches.append(candidate['locator'])
                matches.sort()
                state='not_found' if not matches else 'ok' if len(matches)==1 else 'ambiguous'
                locators=[p['locator'] for p in response.get('value',{}).get('pages',[])]
                exact+=int(response['ok'] and locators==matches and response['state']==state);exact_total+=1
            number,_,_=probe.evidence([dict(label,note=question['note']) for label in question['support']]);citations+=number
        after=probe.inventory()
        if before!=after:raise Refusal()
        p95=sorted(samples)[math.ceil(.95*len(samples))-1]
        state_bytes=sum(p.stat().st_size for p in (probe.base/'state').rglob('*') if p.is_file())
        rss=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        failed=[]
        if sum(hits.values())/sum(counts.values())<.85:failed.append('recall_at_5')
        if exact!=exact_total:failed.append('exact_resolution')
        if p95>.5:failed.append('warm_search_p95')
        if rss>256*1024:failed.append('peak_child_rss')
        if state_bytes>128*1024*1024:failed.append('state_bytes')
        if probe.max_read_bytes>24000:failed.append('read_budget')
        write_private(trace,encode({'schema':'wiki-private-trace.v1','events':probe.events,'source_before':before,'source_after':after}))
        return {'schema':'wiki-private-result.v1','state':'failed' if failed else 'passed','source':'current configured source, model-free',
                'failed_criteria':failed,'recall_at_5':{k:{'hits':hits[k],'total':counts[k]} for k in counts},
                'exact':{'passed':exact,'total':exact_total},'citation_occurrences':citations,
                'initial_scan_seconds':scan,'cold_status_seconds':probe.timings[0][1],'refresh_seconds':probe.timings[1][1],
                'warm_search_p95_seconds':p95,'max_read_response_bytes':probe.max_read_bytes,'state_bytes':state_bytes,
                'peak_child_rss_kib':rss,'source_inventory_unchanged':True,
                'visibility':'Host observations; no instantaneous distributed NFS snapshot claim',
                'owner_usefulness':'pending separate assessment'}
