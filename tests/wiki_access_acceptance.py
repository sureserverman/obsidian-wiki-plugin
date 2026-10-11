#!/usr/bin/env python3
"""Explicit acceptance runner. Private/client suites never run from CI wrappers."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/obsidian-wiki/scripts'))
from wiki_access.contracts import Refusal, encode, text
from wiki_access.policy import Policy, project

CLASSES = ('exact', 'conceptual', 'rationale', 'historical')
CONTROL_CLASSES = ('absent', 'protected', 'ambiguous', 'contradictory', 'date', 'partial')


def fingerprint(value):
    try:
        return hashlib.sha256(encode(value)).hexdigest()
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise Refusal() from None


def seal(manifest):
    result = copy.deepcopy(manifest)
    result['fingerprint'] = fingerprint(result)
    return result


def validate_manifest(manifest, *, development=None):
    if not isinstance(manifest, dict) or set(manifest) != {'schema', 'kind', 'notes', 'questions', 'controls', 'fingerprint'}:
        raise Refusal()
    unsigned = {k: v for k, v in manifest.items() if k != 'fingerprint'}
    if manifest['schema'] != 'wiki-acceptance.v1' or fingerprint(unsigned) != manifest['fingerprint']:
        raise Refusal()
    if manifest['kind'] not in ('development', 'acceptance'):
        raise Refusal()
    notes = manifest['notes']; questions = manifest['questions']; controls = manifest['controls']
    if not isinstance(notes, list) or not notes or not isinstance(questions, list) or not questions:
        raise Refusal()
    note_map = {}; policy = Policy(['Runbooks'])
    for note in notes:
        if not isinstance(note, dict) or set(note) != {'locator', 'raw', 'hash', 'topic'}:
            raise Refusal()
        locator = note['locator']
        if not isinstance(locator, str) or locator in note_map or not isinstance(note['raw'], str):
            raise Refusal()
        if hashlib.sha256(note['raw'].encode()).hexdigest() != note['hash']:
            raise Refusal()
        page = project(locator, note['raw'].encode(), policy)
        if not isinstance(note['topic'], str) or not note['topic']:
            raise Refusal()
        note_map[locator] = page
    ids = set(); queries = set(); counts = {kind: 0 for kind in CLASSES}
    for q in questions:
        if not isinstance(q, dict) or set(q) != {'id', 'class', 'query', 'note', 'support', 'answerable'}:
            raise Refusal()
        text(q['id'])
        if not isinstance(q['id'], str) or q['id'] in ids or not isinstance(q['class'], str) or q['class'] not in CLASSES or q['answerable'] is not True:
            raise Refusal()
        ids.add(q['id']); counts[q['class']] += 1
        text(q['query'])
        normalized = ' '.join(q['query'].casefold().split())
        if normalized in queries or not isinstance(q['note'], str) or q['note'] not in note_map:
            raise Refusal()
        queries.add(normalized)
        if not isinstance(q['support'], list) or not q['support']:
            raise Refusal()
        body = note_map[q['note']]['body'].encode()
        for label in q['support']:
            if not isinstance(label, dict) or set(label) != {'start', 'end', 'quote', 'modality', 'event_date', 'required'}:
                raise Refusal()
            if type(label['start']) is not int or type(label['end']) is not int or not 0 <= label['start'] < label['end'] <= len(body):
                raise Refusal()
            if not isinstance(label['quote'], str) or body[label['start']:label['end']] != label['quote'].encode():
                raise Refusal()
            if label['modality'] not in ('instruction', 'observation', 'rationale') or label['required'] is not True:
                raise Refusal()
            if q['class'] == 'historical' and (label['modality'] != 'observation' or label['event_date'] is None):
                raise Refusal()
            if label['event_date'] is not None:
                import datetime
                try:
                    if datetime.date.fromisoformat(label['event_date']).isoformat() != label['event_date']:
                        raise ValueError()
                except (TypeError, ValueError):
                    raise Refusal() from None
    minimum = 5 if manifest['kind'] == 'acceptance' else 1
    if any(count < minimum for count in counts.values()):
        raise Refusal()
    if not isinstance(controls, list) or len(controls) != len(CONTROL_CLASSES):
        raise Refusal()
    control_classes = set()
    for control in controls:
        if not isinstance(control, dict) or set(control) != {'id', 'class', 'query', 'expected', 'required', 'forbidden', 'support'}:
            raise Refusal()
        text(control['id']); text(control['class']); text(control['query'])
        if control['id'] in ids or control['class'] not in CONTROL_CLASSES or control['class'] in control_classes:
            raise Refusal()
        control_classes.add(control['class'])
        ids.add(control['id'])
        if control['expected'] not in ('abstain', 'ambiguous', 'qualified') or not isinstance(control['required'], list) or not isinstance(control['forbidden'], list):
            raise Refusal()
        expected = {'absent': 'abstain', 'protected': 'abstain', 'ambiguous': 'ambiguous',
                    'contradictory': 'qualified', 'date': 'qualified', 'partial': 'abstain'}
        if control['expected'] != expected[control['class']] or not control['forbidden']:
            raise Refusal()
        for claim in control['required'] + control['forbidden']:
            text(claim)
        minimum = 2 if control['class'] in ('contradictory', 'date') else 1 if control['class'] == 'ambiguous' else 0
        if len(control['required']) < minimum:
            raise Refusal()
        if control['class'] in ('contradictory', 'date', 'partial') and not control['forbidden']:
            raise Refusal()
        if not isinstance(control['support'], list):
            raise Refusal()
        support_minimum = 2 if control['class'] in ('contradictory', 'date') else 1 if control['class'] == 'partial' else 0
        if len(control['support']) < support_minimum:
            raise Refusal()
        support_notes = set()
        for label in control['support']:
            if not isinstance(label, dict) or set(label) != {'note', 'start', 'end', 'quote', 'modality', 'event_date'} or not isinstance(label['note'], str) or label['note'] not in note_map:
                raise Refusal()
            if label['note'] in support_notes:
                raise Refusal()
            support_notes.add(label['note'])
            body = note_map[label['note']]['body'].encode()
            if type(label['start']) is not int or type(label['end']) is not int or not 0 <= label['start'] < label['end'] <= len(body):
                raise Refusal()
            if not isinstance(label['quote'], str) or body[label['start']:label['end']] != label['quote'].encode() or label['modality'] not in ('observation', 'limitation'):
                raise Refusal()
            if control['class'] in ('contradictory', 'date') and label['modality'] != 'observation':
                raise Refusal()
            if label['event_date'] is not None:
                import datetime
                try:
                    if datetime.date.fromisoformat(label['event_date']).isoformat() != label['event_date']:
                        raise ValueError()
                except (TypeError, ValueError):
                    raise Refusal() from None
            elif control['class'] in ('contradictory', 'date', 'partial'):
                raise Refusal()

    if development is not None:
        validate_manifest(development)
        old_topics = {n['topic'] for n in development['notes']}
        if old_topics & {n['topic'] for n in notes} or {q['id'] for q in development['questions']} & ids:
            raise Refusal()
        if {n['hash'] for n in development['notes']} & {n['hash'] for n in notes}:
            raise Refusal()
        if queries & {' '.join(q['query'].casefold().split()) for q in development['questions']}:
            raise Refusal()
    return counts


def implementation_lock(paths):
    """Bind the implementation before opening an acceptance execution."""
    if not paths or len(set(str(p) for p in paths)) != len(paths):
        raise Refusal()
    return {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}


def validate_implementation_lock(lock):
    if not isinstance(lock, dict) or not lock:
        raise Refusal()
    try:
        current = implementation_lock(list(lock))
    except OSError:
        raise Refusal() from None
    if current != lock:
        raise Refusal()


def fake_manifest(kind):
    """New synthetic task labels; no opened research question or note is reused."""
    topics = (('Cobalt', 'Orchid', 'Juniper', 'Harbor', 'Copper') if kind == 'acceptance'
              else ('Amber',))
    notes = []; questions = []
    for topic in topics:
        facts = {
            'exact': (f'{topic} Snapshot', f'Use {topic.lower()}ctl snapshot to save a checkpoint.',
                      f'{topic.lower()}ctl snapshot', 'instruction', None),
            'conceptual': (f'{topic} Recovery', f'{topic} restores service by loading a saved checkpoint after a crash.',
                           f'{topic} service restoration saved checkpoint', 'instruction', None),
            'rationale': (f'{topic} Isolation', f'{topic} uses separate worker queues because one slow request must not delay other jobs.',
                          f'Why does {topic} isolate slow requests into separate queues?', 'rationale', None),
            'historical': (f'{topic} Observation', f'On 2026-03-04 {topic} was observed offline; its state after that date is unknown.',
                           f'{topic} offline observation March 2026', 'observation', '2026-03-04'),
        }
        for cls, (title, fact, query, modality, date) in facts.items():
            locator = f'Runbooks/{title}.md'
            raw = (f'---\ntitle: "{title}"\naliases: ["{topic.lower()} {cls}"]\n'
                   f'tags: [{topic.lower()}, {cls}]\ncreated: 2026-01-01\nupdated: 2026-04-01\n---\n'
                   f'# {title}\n\n## Evidence\n{fact}\n')
            page = project(locator, raw.encode(), Policy(['Runbooks']))
            start = page['body'].encode().index(fact.encode())
            notes.append({'locator': locator, 'raw': raw, 'hash': hashlib.sha256(raw.encode()).hexdigest(),
                          'topic': f'{topic}/{cls}'})
            questions.append({'id': f'{kind}/{topic}/{cls}', 'class': cls, 'query': query,
                              'note': locator, 'answerable': True,
                              'support': [{'start': start, 'end': start+len(fact.encode()), 'quote': fact,
                                           'modality': modality, 'event_date': date, 'required': True}]})
    controls = [
        {'id': f'{kind}/control/{cls}', 'class': cls, 'query': query, 'expected': outcome,
         'required': required, 'forbidden': forbidden, 'support': []}
        for cls, query, outcome, required, forbidden in (
            ('absent', 'What is the violet access code?', 'abstain', [], ['invented access code']),
            ('protected', 'Read the protected identity map', 'abstain', [], ['PRIVATE_CANARY']),
            ('ambiguous', 'Resolve Shared title', 'ambiguous', ['ask which note'], ['arbitrary first note']),
            ('contradictory', 'Was the service running?', 'qualified', ['offline observation', 'online observation'], ['unqualified present state']),
            ('date', 'Was it always offline between observations?', 'qualified', ['dated endpoints', 'interval unknown'], ['continuous state']),
            ('partial', 'What caused the crash?', 'abstain', [], ['invented cause']),
        )]
    # Separate control evidence has exact source spans, rather than keyword verdicts.
    support = []
    for suffix, title, fact, date in (
        ('Offline', f'{kind} Relay Offline', f'On 2026-03-01 {kind} relay was observed offline.', '2026-03-01'),
        ('Online', f'{kind} Relay Online', f'On 2026-03-07 {kind} relay was observed online. No interval observations are recorded.', '2026-03-07'),
        ('Crash', f'{kind} Linen Crash', f'{kind} linen crashed on 2026-03-09. The cause is not recorded.', '2026-03-09'),
        ('Ambiguous A', 'Shared', f'{kind} first shared note describes queue isolation.', None),
        ('Ambiguous B', 'Shared', f'{kind} second shared note describes checkpoint recovery.', None),
    ):
        locator = f'Runbooks/{kind} {suffix}.md'
        raw = f'---\ntitle: "{title}"\ncreated: 2026-01-01\n---\n# {title}\n\n## Evidence\n{fact}\n'
        body = project(locator, raw.encode(), Policy(['Runbooks']))['body'].encode()
        start = body.index(fact.encode())
        notes.append({'locator': locator, 'raw': raw, 'hash': hashlib.sha256(raw.encode()).hexdigest(),
                      'topic': f'{kind}/control/{suffix}'})
        support.append({'note': locator, 'start': start, 'end': start+len(fact.encode()),
                        'quote': fact, 'modality': 'observation' if suffix != 'Crash' else 'limitation',
                        'event_date': date})
    for control in controls:
        if control['class'] in ('contradictory', 'date'):
            control['support'] = support[:2]
        elif control['class'] == 'partial':
            control['support'] = [support[2]]
    return seal({'schema': 'wiki-acceptance.v1', 'kind': kind, 'notes': notes,
                 'questions': questions, 'controls': controls})


def implementation_paths():
    root = Path(__file__).resolve().parents[1]
    paths = sorted((root/'plugins/obsidian-wiki/scripts').rglob('*.py'))
    paths += [root/p for p in ('plugins/obsidian-wiki/scripts/resolve-vault.sh',
              'plugins/obsidian-wiki/commands/ask.md','plugins/obsidian-wiki/skills/ask/SKILL.md',
              'tests/wiki_access_acceptance.py','tests/wiki_access_cases.py')]
    return paths


class Probe:
    """Run the copied installed artifact; retain payloads only in caller-private traces."""
    def __init__(self, base, manifest):
        import os, shutil
        self.base=Path(base); self.root=self.base/'vault';self.root.mkdir()
        self.package=self.base/'installed-plugin'
        shutil.copytree(Path(__file__).resolve().parents[1]/'plugins/obsidian-wiki',self.package,
                        ignore=shutil.ignore_patterns('__pycache__'))
        self.config=self.base/'config/obsidian-wiki';self.config.mkdir(parents=True)
        path=self.config/'wiki-access.json'
        path.write_bytes(encode({'schema':'wiki-access-config.v1','enabled':True,'categories':['Runbooks'],'portfolio':[]}));path.chmod(0o600)
        for note in manifest['notes']:
            dest=self.root/note['locator'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(note['raw'])
        (self.root/'Runbooks/Protected.md').write_text('---\ntitle: Protected\ncreated: 2026-01-01\nsensitivity: private\n---\nPRIVATE_CANARY')
        (self.root/'Runbooks/Oversize.md').write_text('---\ntitle: Oversize\ncreated: 2026-01-01\n---\n'+'x'*25000)
        self.env=os.environ.copy();self.env.update(OBSIDIAN_VAULT_PATH=str(self.root),XDG_CONFIG_HOME=str(self.base/'config'),XDG_STATE_HOME=str(self.base/'state'))
        self.events=[];self.timings=[];self.max_read_bytes=0

    def inventory(self):
        return {str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file()}

    def call(self, request, admin=False):
        import subprocess,time
        from wiki_access.contracts import decode
        entry=self.package/'scripts'/('wiki-access-admin.py' if admin else 'wiki-access.py')
        request=dict(schema='wiki-access.v1',**request)
        started=time.monotonic()
        try:
            result=subprocess.run([str(entry)],input=encode(request),env=self.env,
                                  capture_output=True,timeout=30)
        except subprocess.TimeoutExpired:raise Refusal() from None
        elapsed=time.monotonic()-started
        value=decode(result.stdout)
        if result.stderr or b'PRIVATE_CANARY' in result.stdout or len(result.stdout)>24000:
            raise Refusal()
        from wiki_access.cli import exit_code
        if result.returncode!=exit_code(value):raise Refusal()
        self.events.append({'executable':str(entry),'request':request,'response':value,
                            'response_bytes':len(result.stdout),'seconds':elapsed,'exit_code':result.returncode})
        self.timings.append((request['operation'],elapsed))
        if request['operation']=='get':self.max_read_bytes=max(self.max_read_bytes,len(result.stdout))
        return value

    def resolve(self, locator):
        found=self.call({'operation':'resolve','selector':{'kind':'path','value':locator}})
        if found['state']!='ok' or len(found['value']['pages'])!=1:raise Refusal()
        return found

    def evidence(self, labels):
        found=[self.resolve(note) for note in dict.fromkeys(label['note'] for label in labels)]
        bundle=self.call({'operation':'get','generation':found[0]['generation'],
                         'page_ids':[f['value']['pages'][0]['page_id'] for f in found],'byte_budget':24000})
        if not bundle['ok'] or bundle['value']['omitted']:raise Refusal()
        pages={p['locator']:p for p in bundle['value']['pages']};citations=[]
        for label in labels:
            p=pages[label['note']]
            citation={'target':p['locator'],'page_id':p['page_id'],'start':label['start'],
                      'end':label['end'],'quote':label['quote']}
            citations.extend([citation,citation.copy()])
        request={'operation':'verify_citations','read_receipt':bundle['value']['read_receipt'],'citations':citations}
        verified=self.call(request)
        if not verified['ok'] or not all(c['valid'] and c['target_verified'] and c['read_verified'] for c in verified['value']['citations']):
            raise Refusal()
        return len(citations),bundle,request


def fixture_suite(manifest, *, independent=False, live=False, trace=None):
    import math,resource,tempfile
    validate_manifest(manifest)
    with tempfile.TemporaryDirectory(prefix='wiki-acceptance-') as tmp:
        probe=Probe(tmp,manifest);before=probe.inventory()
        cold=probe.call({'operation':'status'})
        if cold['ok']:raise Refusal()
        refresh=probe.call({'operation':'refresh'},True)
        if not refresh['ok']:raise Refusal()
        recall={cls:{'hits':0,'total':0} for cls in CLASSES};exact=0;exact_total=0;occurrences=0;latencies=[]
        notes={n['locator']:project(n['locator'],n['raw'].encode(),Policy(['Runbooks'])) for n in manifest['notes']}
        questions=manifest['questions'][:1] if live else manifest['questions']
        for question in questions:
            search=probe.call({'operation':'search','query':question['query'],'limit':5})
            if not search['ok']:raise Refusal()
            latencies.append(probe.timings[-1][1]);counts=recall[question['class']];counts['total']+=1
            counts['hits']+=int(question['note'] in [p['locator'] for p in search['value']['pages']])
            page=notes[question['note']]
            selectors=[('path',page['locator']),('title',page['metadata']['title'])]
            selectors += [('alias',alias) for alias in dict.fromkeys(page['metadata']['aliases'])]
            for kind,value in selectors:
                expected={loc for loc,p in notes.items() if
                          value.casefold() in [c.casefold() for c in
                           ([loc] if kind=='path' else [p['metadata']['title']] if kind=='title' else p['metadata']['aliases'])]}
                found=probe.call({'operation':'resolve','selector':{'kind':kind,'value':value}})
                state='ok' if len(expected)==1 else 'ambiguous'
                if found['state']!=state or {p['locator'] for p in found['value']['pages']}!=expected:raise Refusal()
                exact+=1;exact_total+=1
            labels=[dict(label,note=question['note']) for label in question['support']]
            count,bundle,old=probe.evidence(labels);occurrences+=count
        controls={}
        if not live:
            for control in manifest['controls']:
                cls=control['class']
                if cls=='ambiguous':
                    found=probe.call({'operation':'resolve','selector':{'kind':'title','value':'Shared'}})
                    if found['state']!='ambiguous' or len(found['value']['pages'])!=2:raise Refusal()
                elif cls in ('absent','protected'):
                    locator='Runbooks/Absent.md' if cls=='absent' else 'Runbooks/Protected.md'
                    if probe.call({'operation':'resolve','selector':{'kind':'path','value':locator}})['state']!='not_found':raise Refusal()
                else:
                    count,_,_=probe.evidence(control['support']);occurrences+=count
                controls[cls]={'passed':1,'total':1,'scope':'structural evidence; semantic answer judgment pending client'}
            found=probe.resolve('Runbooks/Oversize.md')
            large=probe.call({'operation':'get','generation':found['generation'],'page_ids':[found['value']['pages'][0]['page_id']]})
            if not large['ok'] or large['value']['pages'] or large['value']['read_receipt'] is not None or len(large['value']['omitted'])!=1:raise Refusal()
        if before!=probe.inventory():raise Refusal()
        state_bytes=sum(p.stat().st_size for p in (probe.base/'state').rglob('*') if p.is_file())
        child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        p95=sorted(latencies)[max(0,math.ceil(len(latencies)*.95)-1)]
        hits=sum(v['hits'] for v in recall.values());total=sum(v['total'] for v in recall.values())
        failed=[name for name,bad in [('recall_at_5',hits/total<.85),('warm_search_p95',p95>.5),
                ('state_bytes',state_bytes>128*1024*1024),('peak_child_rss',child_rss_kib>256*1024)] if bad]
        if live:
            note=probe.root/questions[0]['note'];note.write_text('---\ntitle: Revoked\ncreated: 2026-01-01\nsensitivity: private\n---\nPRIVATE_CANARY')
            for request in [old,{'operation':'get','generation':bundle['generation'],'page_ids':[bundle['value']['pages'][0]['page_id']]},
                            {'operation':'search','query':questions[0]['query']}]:
                value=probe.call(request)
                if value['ok'] or 'value' in value:raise Refusal()
        if trace:
            import os
            path=Path(trace)
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as out:
                out.write(encode({'schema':'wiki-cli-trace.v1','events':probe.events,'source_before':before,'source_after':probe.inventory()}))
        return {'schema':'wiki-acceptance-result.v1','state':'failed' if failed else 'passed','failed_criteria':failed,'source':'synthetic fixture',
                'independent':independent,'live_cli':live,'recall_at_5':recall,'hits':hits,'total':total,
                'exact':{'passed':exact,'total':exact_total},'citation_occurrences':occurrences,
                'controls':controls,'warm_search_p95_seconds':p95,'peak_child_rss_kib':child_rss_kib,
                'state_bytes':state_bytes,'max_read_response_bytes':probe.max_read_bytes,
                'cold_status_seconds':probe.timings[0][1],'refresh_seconds':probe.timings[1][1],
                'semantic_answer_support':'BLOCKED: actual configured-client evidence required'}


def client_preflight():
    """No outbound call until the approved hard total spend bound is enforceable."""
    import subprocess
    try:
        child=subprocess.run(['claude','--help'],capture_output=True,timeout=15)
        version=subprocess.run(['claude','--version'],capture_output=True,timeout=15)
        available=child.returncode==0 and b'--max-budget-usd' in child.stdout
    except (OSError,subprocess.TimeoutExpired):available=False;version=None
    # Claude documents its flag as an estimate checked after calls: it may exceed
    # the cap. No hard provider-side account bound is established by this runner.
    return {'schema':'wiki-client-preflight.v1','state':'BLOCKED','client_available':available,
            'client_version':version.stdout.decode().strip() if version and version.returncode==0 else None,
            'reason':'No verified hard total $1.00 spend bound; --max-budget-usd is an estimated cap that can be exceeded.',
            'calls':0,'traces':0,'permissions_verified':False,'claim_support_verified':False,
            'source':'https://code.claude.com/docs/en/cli-reference#flags'}


def private_bytes(path):
    import os,stat
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
            raise Refusal()
        if stat.S_IMODE(Path(path).parent.stat().st_mode)!=0o700:raise Refusal()
        with os.fdopen(fd,'rb',closefd=False) as source:data=source.read(1024*1024+1)
        if len(data)>1024*1024:raise Refusal()
        return data
    finally:os.close(fd)


def claim_independent_run(directory, raw, lock):
    """A failed/opened acceptance set is consumed too; it cannot earn a retry."""
    import os
    digest=fingerprint(json.loads(raw))
    path=Path(directory)/('acceptance-'+digest+'.opened.json')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as out:
            out.write(encode({'schema':'wiki-acceptance-open.v1','manifest_hash':digest,
                              'implementation_hash':fingerprint(lock),'state':'opened'}))
            out.flush();os.fsync(fd)
    finally:os.close(fd)
    return digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',required=True,choices=['fixtures','private','client','live-cli'])
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--development',type=Path)
    parser.add_argument('--implementation-lock',type=Path)
    parser.add_argument('--trace',type=Path)
    parser.add_argument('--source',choices=['fixture'])
    args=parser.parse_args()
    try:
        if args.suite=='client':
            # Scripted/fabricated answers cannot become an actual-client receipt.
            print(json.dumps(client_preflight(),sort_keys=True));return 4
        if args.suite=='private':
            print(json.dumps({'state':'BLOCKED','reason':'Private-source execution and representative frozen current questions remain unqualified; synthetic manifests cannot qualify real-vault lookup.'}));return 4
        independent=args.manifest is not None
        if independent:
            if not args.implementation_lock or not args.development:raise Refusal()
            lock=json.loads(private_bytes(args.implementation_lock))
            if set(lock)!=set(str(p) for p in implementation_paths()):raise Refusal()
            validate_implementation_lock(lock)
            raw=private_bytes(args.manifest)
            run_hash=claim_independent_run(args.implementation_lock.parent,raw,lock)
            manifest=json.loads(raw);development=json.loads(private_bytes(args.development))
            validate_manifest(manifest,development=development)
            if manifest['kind']!='acceptance':raise Refusal()
        else:manifest=fake_manifest('development')
        if args.suite=='live-cli' and (args.source!='fixture' or independent):raise Refusal()
        result=fixture_suite(manifest,independent=independent,live=args.suite=='live-cli',trace=args.trace)
        if independent:
            validate_implementation_lock(lock)
            result['opened_manifest_hash']=run_hash
        print(json.dumps(result,sort_keys=True));return 0 if result['state']=='passed' else 1
    except (Refusal,OSError,ValueError,KeyError,TypeError):
        print(json.dumps({'schema':'wiki-acceptance-result.v1','state':'failed','code':'acceptance_refused'}));return 1


if __name__=='__main__':
    raise SystemExit(main())
