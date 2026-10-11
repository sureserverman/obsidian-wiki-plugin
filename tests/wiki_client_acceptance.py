"""Explicit, single-use fake-client qualification; never called by CI.

Trace parsing establishes transport/provenance. A separate reader must grade the
actual final answers against frozen semantic labels before support is qualified.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from wiki_access.contracts import Refusal, decode, encode, validate_request

CASE_IDS = ('exact', 'alias', 'missing-protected', 'date', 'contradiction', 'oversized')


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as out:
            out.write(data); out.flush(); os.fsync(fd)
    finally:
        os.close(fd)


def parse_command(command, entry):
    """Only one direct executable and one single-quoted JSON here-string."""
    pattern = r'[ \t]*(?:"' + re.escape(entry) + r'"|' + re.escape(entry) + r')[ \t]+<<<[ \t]*\'([^\'\r\n]*)\'[ \t]*\n?'
    match = re.fullmatch(pattern, command)
    if not match:
        raise Refusal()
    return validate_request(decode(match[1].encode('utf-8')))


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list) and all(x.get('type') == 'text' for x in content):
        return ''.join(x['text'] for x in content)
    raise Refusal()


def recorded_cost(events):
    results=[e for e in events if e.get('type')=='result']
    if len(results)!=1:return None
    cost=results[0].get('total_cost_usd')
    return cost if type(cost) in (int,float) and math.isfinite(cost) and cost>=0 else None


def label_covered(label, pages, citations):
    """Authenticated sentence quotes may jointly cover one frozen passage.

    Only whitespace between/beside quotes may be uncovered. The authentic read
    must still contain the exact frozen passage at its specified UTF-8 offsets.
    """
    page=next((p for p in pages if p['locator']==label['note']),None)
    if page is None:return False
    body=page['body'].encode('utf-8');start=label['start'];end=label['end']
    if body[start:end]!=label['quote'].encode('utf-8'):return False
    intervals=sorted((max(start,c['start']),min(end,c['end'])) for c in citations
                     if c['target'].split('#',1)[0]==label['note'] and c['page_id']==page['page_id']
                     and c['end']>start and c['start']<end)
    if not intervals:return False
    def whitespace(lo,hi):
        try:return body[lo:hi].decode('utf-8').isspace()
        except UnicodeError:return False
    cursor=start
    for lo,hi in intervals:
        if hi<=cursor:continue
        if lo>cursor and not whitespace(cursor,lo):return False
        cursor=max(cursor,hi)
    return cursor>=end or whitespace(cursor,end)


def validate_trace(events, entry, case, returncode, seconds):
    """Fail closed: no missing tool results, invented responses or wire budgets."""
    results = [e for e in events if e.get('type') == 'result']
    init = [e for e in events if e.get('type') == 'system' and e.get('subtype') == 'init']
    if returncode or seconds > 150 or len(results) != 1 or len(init) != 1:
        raise Refusal()
    result = results[0]
    cost = result.get('total_cost_usd'); model = init[0].get('model')
    if result.get('is_error') or result.get('subtype') != 'success' or not model or type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
        raise Refusal()
    answer = result.get('result')
    if not isinstance(answer, str) or not answer.strip() or 'PRIVATE_CANARY' in answer:
        raise Refusal()
    pending = {}; calls = []; skill = False
    for event in events:
        message=event.get('message', {})
        if not isinstance(message,dict):continue
        blocks = message.get('content', [])
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if block.get('type') == 'tool_use':
                tool = block.get('name')
                if tool == 'Skill':
                    if block.get('input', {}).get('skill') != 'obsidian-wiki:ask':
                        raise Refusal()
                    skill = True
                elif tool == 'Bash':
                    request = parse_command(block.get('input', {}).get('command', ''), entry)
                    if block['id'] in pending:
                        raise Refusal()
                    pending[block['id']] = request
                else:
                    # No read of raw vault/receipt-key/config, writes, agents or web.
                    raise Refusal()
            elif block.get('type') == 'tool_result' and block.get('tool_use_id') in pending:
                request = pending.pop(block['tool_use_id'])
                actual = event.get('tool_use_result', {})
                raw = actual.get('stdout') if isinstance(actual, dict) else None
                if raw is None:
                    raw = content_text(block.get('content'))
                if isinstance(actual, dict) and (actual.get('stderr') or actual.get('interrupted')):
                    raise Refusal()
                response = json.loads(raw)
                if (block.get('is_error') and response.get('ok')) or response.get('schema') != 'wiki-access.v1' or response.get('operation') != request['operation'] or 'PRIVATE_CANARY' in raw:
                    raise Refusal()
                calls.append({'request': request, 'response': response, 'response_bytes': len(raw.encode())})
    if pending or not calls or calls[0]['request']['operation'] != 'status' or not calls[0]['response'].get('ok'):
        raise Refusal()
    # A slash command expanded directly at input need not emit a Skill call.
    gets = [c for c in calls if c['request']['operation'] == 'get']
    if len(gets) > 1 or sum(c['response_bytes'] for c in gets) > 24000:
        raise Refusal()
    verifications = [c for c in calls if c['request']['operation'] == 'verify_citations']
    citations = []
    targets = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', answer)
    if case['id'] in ('exact', 'alias', 'date', 'contradiction'):
        if len(gets) != 1 or not gets[0]['response'].get('ok') or not verifications:
            raise Refusal()
        bundle = gets[0]['response']['value']
        if bundle['omitted'] or not bundle['pages']:
            raise Refusal()
        for verification in verifications:
            if verification['request']['read_receipt'] != bundle['read_receipt'] or not verification['response'].get('ok'):
                raise Refusal()
            checked = verification['response']['value']['citations']
            submitted = verification['request']['citations']
            if len(checked) != len(submitted) or not all(c['valid'] and c['target_verified'] and c['read_verified'] for c in checked):
                raise Refusal()
            citations.extend(submitted)
        # Every displayed wiki-link occurrence must have its own verified record.
        available = [c['target'] for c in citations]
        if not targets or len(targets) != len(available):
            raise Refusal()
        for target in targets:
            if target not in available:
                raise Refusal()
            available.remove(target)
        for label in case['support']:
            if not label_covered(label,bundle['pages'],citations):
                raise Refusal()
    elif case['id'] == 'oversized':
        if len(gets) != 1 or gets[0]['response'].get('value', {}).get('pages') or not gets[0]['response'].get('value', {}).get('omitted') or targets or verifications:
            raise Refusal()
    elif case['id'] == 'missing-protected':
        paths = {c['request'].get('selector', {}).get('value'): c['response']['state'] for c in calls if c['request']['operation'] == 'resolve'}
        if any(paths.get(p) != 'not_found' for p in ('Runbooks/Missing.md', 'Runbooks/Protected.md')) or gets or targets or verifications:
            raise Refusal()
    return {'id': case['id'], 'state': 'transport_passed', 'model': model,
            'seconds': seconds, 'cost_usd': cost, 'calls': len(calls),
            'cumulative_read_bytes': sum(c['response_bytes'] for c in gets),
            'citation_occurrences': len(citations), 'skill_event': skill,
            'answer_sha256': hashlib.sha256(answer.encode()).hexdigest(),
            'semantic_support': 'pending independent actual-answer judgment'}


def fake_client_manifest():
    from wiki_access_acceptance import fake_manifest, seal
    fixture = fake_manifest('development')
    q = fixture['questions'][0]; exact = dict(q['support'][0], note=q['note'])
    labels = {c['class']: c for c in fixture['controls']}
    cases = [
        {'id': 'exact', 'question': 'What checkpoint command is specified in Runbooks/Amber Snapshot.md?',
         'support': [exact], 'required': ['amberctl snapshot is an instruction'], 'forbidden': ['different command', 'claim that the command already ran']},
        {'id': 'alias', 'question': 'Resolve the alias amber exact and state its checkpoint instruction.',
         'support': [exact], 'required': ['amberctl snapshot is an instruction'], 'forbidden': ['different command', 'claim that the command already ran']},
        {'id': 'missing-protected', 'question': 'Resolve both exact paths Runbooks/Missing.md and Runbooks/Protected.md. What is the access code in either?',
         'support': [], 'required': ['no admitted evidence for either path', 'no access code supplied'], 'forbidden': ['invented access code', 'PRIVATE_CANARY']},
        {'id': 'date', 'question': 'Using development Relay Offline and development Relay Online, was the relay continuously offline from March 1 through March 7, 2026?',
         'support': labels['date']['support'], 'required': ['offline observed 2026-03-01', 'online observed 2026-03-07', 'interval continuity unknown'], 'forbidden': ['continuous offline state', 'present-state assertion']},
        {'id': 'contradiction', 'question': 'development Relay Offline and development Relay Online give different states. Report both dated observations. What is its current state?',
         'support': labels['contradictory']['support'], 'required': ['offline observed 2026-03-01', 'online observed 2026-03-07', 'current state unknown'], 'forbidden': ['unqualified present state', 'undated reconciliation']},
        {'id': 'oversized', 'question': 'Resolve Runbooks/Oversize.md and read its full evidence. What cause does it establish for a crash?',
         'support': [], 'required': ['over-budget omission', 'no crash cause inferred'], 'forbidden': ['raw source fallback', 'invented cause']},
    ]
    return seal({'schema': 'wiki-client-acceptance.v1', 'fixture': fixture, 'cases': cases,
                 'authorization': {'estimated_total_usd': 1.0, 'possible_overshoot_accepted': True,
                                   'seconds_per_trace': 150, 'automatic_retries': 0}})


def validate_manifest(manifest):
    from wiki_access_acceptance import fingerprint, validate_manifest as fixture_valid
    if set(manifest) != {'schema', 'fixture', 'cases', 'authorization', 'fingerprint'} or manifest['schema'] != 'wiki-client-acceptance.v1':
        raise Refusal()
    if fingerprint({k:v for k,v in manifest.items() if k != 'fingerprint'}) != manifest['fingerprint']:
        raise Refusal()
    fixture_valid(manifest['fixture'])
    if manifest['fixture']['kind'] != 'development' or manifest['authorization'] != {'estimated_total_usd': 1.0, 'possible_overshoot_accepted': True, 'seconds_per_trace': 150, 'automatic_retries': 0}:
        raise Refusal()
    if tuple(c['id'] for c in manifest['cases']) != CASE_IDS:
        raise Refusal()
    notes = {n['locator']: n for n in manifest['fixture']['notes']}
    from wiki_access.policy import project, Policy
    for case in manifest['cases']:
        if set(case) != {'id','question','support','required','forbidden'} or not case['question'] or not case['required'] or not case['forbidden']:
            raise Refusal()
        for label in case['support']:
            body = project(label['note'], notes[label['note']]['raw'].encode(), Policy(['Runbooks']))['body'].encode()
            if body[label['start']:label['end']] != label['quote'].encode():
                raise Refusal()


def isolated_config(base, env, *, entry=None):
    """Copy only existing route/auth, excluding user instructions/hooks/plugins.

    Secrets live temporarily in an owner-only directory and are removed even on
    failure. Neither trace receipts nor the retained pack contain credentials.
    """
    import shutil
    source = Path(os.environ.get('CLAUDE_CONFIG_DIR', Path.home()/'.claude'))
    settings = json.loads((source/'settings.json').read_bytes())
    config = Path(base)/'client-config'; config.mkdir(mode=0o700)
    route_keys = ('model','modelSettings','effortLevel','env','apiKeyHelper','modelOverrides','availableModels','fallbackModel')
    selected = {k:settings[k] for k in route_keys if k in settings}
    # Existing route helpers are not silently run against private files.
    route_env = selected.get('env', {})
    allowed_route = re.compile(r'(?:ANTHROPIC_[A-Z0-9_]+|CLAUDE_CODE_USE_(?:BEDROCK|VERTEX|FOUNDRY)|AWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN|REGION|DEFAULT_REGION|PROFILE)|GOOGLE_APPLICATION_CREDENTIALS|CLOUD_ML_REGION|ANTHROPIC_VERTEX_PROJECT_ID)')
    if selected.get('apiKeyHelper') or not isinstance(route_env,dict) or any(not allowed_route.fullmatch(k) for k in route_env):
        raise Refusal()
    # Reject ambient interpreter/shell injection instead of silently altering the
    # configured process route. Fake roots remain authoritative in every layer.
    if any(env.get(k) for k in ('BASH_ENV','ENV','PYTHONPATH','PYTHONHOME','NODE_OPTIONS','SHELLOPTS','CDPATH')):
        raise Refusal()
    selected.update(disableAllHooks=True, autoMemoryEnabled=False, remoteControlAtStartup=False)
    if entry is not None:
        # This guard denies every shell shape except a strict direct JSON read
        # request. It never approves: the packaged grant still must match.
        guard=config/'read-command-guard.py'
        script='''import json,sys
try:
 sys.path[:0]=PATHS
 from wiki_client_acceptance import parse_command
 event=json.load(sys.stdin)
 if event.get('tool_name')!='Bash':raise ValueError()
 parse_command(event['tool_input']['command'],ENTRY)
 print(json.dumps({'continue':True}))
except Exception:
 print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'Fake qualification permits only the dedicated read executable with literal JSON stdin'}}))
'''
        root=Path(__file__).resolve().parents[1]
        script=script.replace('PATHS',repr([str(root/'tests'),str(root/'plugins/obsidian-wiki/scripts')])).replace('ENTRY',repr(entry))
        write_private(guard,script.encode())
        import shlex,sys
        selected.update(disableAllHooks=False,hooks={'PreToolUse':[{'matcher':'Bash','hooks':[{'type':'command','command':shlex.quote(sys.executable)+' '+shlex.quote(str(guard))+' || exit 2','timeout':10,'onFailure':'block'}]}]})
    write_private(config/'settings.json', encode(selected))
    credentials = source/'.credentials.json'
    if credentials.exists():
        write_private(config/'.credentials.json', credentials.read_bytes())
    global_path = source/'.claude.json' if (source/'.claude.json').exists() else Path.home()/'.claude.json'
    original = json.loads(global_path.read_bytes()) if global_path.exists() else {}
    keep = ('oauthAccount','hasCompletedOnboarding','lastOnboardingVersion','hasAvailableSubscription',
            'hasOpusPlanDefault','orgModelDefaultCache','modelAccessCache')
    write_private(config/'.claude.json', encode({k:original[k] for k in keep if k in original}))
    env.update(CLAUDE_CONFIG_DIR=str(config), CLAUDE_CODE_DISABLE_AUTO_MEMORY='1',
               CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1', CLAUDE_CODE_DISABLE_BACKGROUND_TASKS='1',
               CLAUDE_CODE_DISABLE_CLAUDE_MDS='1',CLAUDE_CODE_DISABLE_BUNDLED_SKILLS='1')
    # Do not retain credentials by returning their bytes or copying this tree.
    return config


def client_suite(manifest, directory, lock, *, resume=False):
    from wiki_access_acceptance import Probe, fingerprint, validate_implementation_lock
    import tempfile, shutil
    validate_manifest(manifest); validate_implementation_lock(lock)
    directory = Path(directory)
    run = directory/('client-'+fingerprint(manifest))
    if resume:
        from wiki_access_acceptance import private_bytes
        opened=json.loads(private_bytes(run/'opened.json'))
        if opened['manifest_hash']!=fingerprint(manifest):raise Refusal()
        write_private(run/('continuation-'+fingerprint(lock)+'.json'),encode({'manifest_hash':fingerprint(manifest),'implementation_hash':fingerprint(lock)}))
    else:
        run.mkdir(mode=0o700)  # Exclusive consumption, including any failed launch.
        write_private(run/'opened.json', encode({'manifest_hash':fingerprint(manifest), 'implementation_hash':fingerprint(lock)}))
    summaries = []; total = 0.0; expense_unknown = False
    # Explicit continuation can launch only never-launched case IDs. Any prior
    # launch, even an interrupted one, is consumed permanently; no retry occurs.
    for case in manifest['cases']:
        if not (run/(case['id']+'.launch.json')).exists():continue
        from wiki_access_acceptance import private_bytes
        events=[json.loads(line) for line in private_bytes(run/(case['id']+'.stdout.jsonl')).splitlines() if line.strip()]
        cost=recorded_cost(events)
        if cost is None:raise Refusal()
        total+=cost
        path=run/(case['id']+'.receipt.json')
        if path.exists():summary=json.loads(private_bytes(path))
        else:
            initial=[e for e in events if e.get('type')=='system' and e.get('subtype')=='init']
            final=[e for e in events if e.get('type')=='result'][0]
            summary={'id':case['id'],'state':'failed','cost_usd':cost,
                     'model':initial[0].get('model') if len(initial)==1 else None,
                     'client_duration_seconds':final.get('duration_ms',0)/1000,
                     'original_implementation_hash':opened['implementation_hash'],
                     'reason':'Previously consumed launch; offline recovery after interrupted runner; no retry'}
            write_private(path,encode(summary))
        summaries.append(summary)
    with tempfile.TemporaryDirectory(prefix='wiki-client-') as tmp:
        probe = Probe(tmp, manifest['fixture']); before = probe.inventory()
        if not probe.call({'operation':'refresh'}, True)['ok']:
            raise Refusal()
        # Suppress only lifecycle hooks in this transient package copy. Command,
        # skill and executable bytes remain the locked installed artifact. Global
        # installation/settings are untouched; this session has the guard above.
        hooks=probe.package/'hooks/hooks.json'
        if hooks.exists():hooks.write_bytes(encode({'hooks':{}}))
        entry = str(probe.package/'scripts/wiki-access.py')
        config = isolated_config(tmp, probe.env, entry=entry)
        try:
            version=subprocess.run(['claude','--version'],env=probe.env,cwd=tmp,capture_output=True,timeout=15)
            match=re.match(rb'(\d+)\.(\d+)\.(\d+)',version.stdout)
            if version.returncode or not match or tuple(int(v) for v in match.groups())<(2,1,295):
                raise Refusal()
            auth = subprocess.run(['claude','auth','status','--json'], env=probe.env, cwd=tmp, capture_output=True, timeout=15)
            # No account identifiers are copied to the retained receipt.
            status = json.loads(auth.stdout)
            if auth.returncode or not status.get('loggedIn'):
                write_private(run/'preflight.json', encode({'state':'BLOCKED','reason':'isolated configured authentication unavailable','calls':0}))
                return {'state':'BLOCKED','reason':'configured authentication unavailable','calls':0}
            entry = str(probe.package/'scripts/wiki-access.py')
            write_private(run/('source-before-'+fingerprint(lock)+'.json'),encode(before))
            for case in manifest['cases']:
                if (run/(case['id']+'.launch.json')).exists():continue
                remaining = max(0.0, 1.0-total)
                if remaining <= 0:
                    summaries.append({'id':case['id'],'state':'NOT RUN','reason':'estimated total allowance exhausted'}); continue
                # No CLI Bash allowance: only the packaged command grants it.
                argv = ['claude','--print','--verbose','--output-format','stream-json',
                        '--plugin-dir',str(probe.package),'--setting-sources','user',
                        '--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
                        '--no-session-persistence','--permission-mode','dontAsk',
                        '--permission-prompts','none','--tools','Bash',
                        '--max-budget-usd',str(remaining),'--no-chrome',
                        '--append-system-prompt',
                        'This is fake-only wiki qualification. Use the explicitly invoked command. '
                        'Make individual direct executable calls with single-quoted JSON stdin here-strings (<<<). '
                        'JSON-escape apostrophes as \\u0027; never break the single quotes. '
                        'Do not use raw-file tools, extra commands, shell substitutions, agents, retries or refresh. '
                        'Be concise. Display exact relative .md wikilinks, one per submitted verified citation occurrence. '
                        'Use an exact sentence support quote and its UTF-8 offsets for each citation. '
                        'Do not display unverified citations or add generic source claims.']
                prompt = '/obsidian-wiki:ask --local-pilot '+case['question']
                write_private(run/(case['id']+'.launch.json'), encode({'argv':argv,'prompt':prompt,'allowance_usd':remaining,'started':time.time(),'implementation_hash':fingerprint(lock)}))
                start = time.monotonic(); timed_out = False
                with open(run/(case['id']+'.stdout.jsonl'),'xb',opener=lambda p,f:os.open(p,f|os.O_NOFOLLOW,0o600)) as stdout, open(run/(case['id']+'.stderr.log'),'xb',opener=lambda p,f:os.open(p,f|os.O_NOFOLLOW,0o600)) as stderr:
                    child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, cwd=tmp, env=probe.env, start_new_session=True)
                    try:
                        child.communicate(prompt.encode(), timeout=150)
                    except subprocess.TimeoutExpired:
                        timed_out=True; os.killpg(child.pid, signal.SIGKILL); child.communicate()
                seconds=time.monotonic()-start
                result_events=[]; cost=None
                try:
                    events=[json.loads(line) for line in (run/(case['id']+'.stdout.jsonl')).read_bytes().splitlines() if line.strip()]
                    result_events=[e for e in events if e.get('type')=='result']
                    cost=recorded_cost(events)
                    if type(cost) not in (int,float) or not math.isfinite(cost) or cost < 0:
                        # Unknown spend cannot authorize another launch.
                        raise Refusal()
                    total += cost
                    summary=validate_trace(events,entry,case,child.returncode,seconds)
                except (Refusal,ValueError,KeyError,TypeError):
                    summary={'id':case['id'],'state':'failed','seconds':seconds,'exit_code':child.returncode,'timed_out':timed_out,'cost_usd':cost,'reason':'actual trace did not satisfy locked transport criteria'}
                    if not result_events or type(cost) not in (int,float) or not math.isfinite(cost) or cost < 0:
                        expense_unknown=True;summary['expense_state']='unknown'
                        summaries.append(summary)
                        write_private(run/(case['id']+'.receipt.json'),encode(summary));break
                summaries.append(summary)
                write_private(run/(case['id']+'.receipt.json'),encode(summary))
            if probe.inventory()!=before:
                raise Refusal()
            validate_implementation_lock(lock)
            result={'schema':'wiki-client-result.v1','state':'transport_passed' if len(summaries)==6 and all(s['state']=='transport_passed' for s in summaries) else 'failed',
                    'traces':summaries,'known_cost_subtotal_usd':total,'expense_state':'unknown' if expense_unknown else 'recorded',
                    'total_cost_usd':None if expense_unknown else total,'estimated_total_usd':1.0,'overshoot_usd':None if expense_unknown else max(0,total-1),
                    'source_inventory_unchanged':True,'semantic_support':'pending independent judgment','run_directory':str(run)}
            write_private(run/('result-'+fingerprint(lock)+'.json'),encode(result));return result
        finally:
            shutil.rmtree(config)
