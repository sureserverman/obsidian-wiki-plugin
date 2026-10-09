#!/usr/bin/env python3
"""Explicit acceptance runner. Private/client suites never run from CI wrappers."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/obsidian-wiki/scripts'))
from wiki_access.contracts import Refusal, encode
from wiki_access.policy import Policy, project

CLASSES = ('exact', 'conceptual', 'rationale', 'historical')
CONTROL_CLASSES = ('absent', 'protected', 'ambiguous', 'contradictory', 'date', 'partial')


def fingerprint(value):
    return hashlib.sha256(encode(value)).hexdigest()


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
    ids = set(); counts = {kind: 0 for kind in CLASSES}
    for q in questions:
        if not isinstance(q, dict) or set(q) != {'id', 'class', 'query', 'note', 'support', 'answerable'}:
            raise Refusal()
        if not isinstance(q['id'], str) or q['id'] in ids or q['class'] not in CLASSES or q['answerable'] is not True:
            raise Refusal()
        ids.add(q['id']); counts[q['class']] += 1
        if not isinstance(q['query'], str) or not q['query'].strip() or q['note'] not in note_map:
            raise Refusal()
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
            if label['event_date'] is not None:
                import datetime
                try:
                    datetime.date.fromisoformat(label['event_date'])
                except (TypeError, ValueError):
                    raise Refusal() from None
    minimum = 5 if manifest['kind'] == 'acceptance' else 1
    if any(count < minimum for count in counts.values()):
        raise Refusal()
    if not isinstance(controls, list) or {c.get('class') for c in controls if isinstance(c, dict)} != set(CONTROL_CLASSES):
        raise Refusal()
    for control in controls:
        if set(control) != {'id', 'class', 'query', 'expected', 'required', 'forbidden', 'support'} or control['id'] in ids:
            raise Refusal()
        ids.add(control['id'])
        if control['expected'] not in ('abstain', 'ambiguous', 'qualified') or not isinstance(control['required'], list) or not isinstance(control['forbidden'], list):
            raise Refusal()
        if control['class'] in ('contradictory', 'date', 'partial') and not control['forbidden']:
            raise Refusal()
        if not isinstance(control['support'], list):
            raise Refusal()
        if control['class'] in ('contradictory', 'date', 'partial') and not control['support']:
            raise Refusal()
        for label in control['support']:
            if set(label) != {'note', 'start', 'end', 'quote', 'modality', 'event_date'} or label['note'] not in note_map:
                raise Refusal()
            body = note_map[label['note']]['body'].encode()
            if type(label['start']) is not int or type(label['end']) is not int or not 0 <= label['start'] < label['end'] <= len(body):
                raise Refusal()
            if body[label['start']:label['end']] != label['quote'].encode() or label['modality'] not in ('observation', 'limitation'):
                raise Refusal()

    if development is not None:
        validate_manifest(development)
        old_topics = {n['topic'] for n in development['notes']}
        if old_topics & {n['topic'] for n in notes} or {q['id'] for q in development['questions']} & ids:
            raise Refusal()
        if {n['hash'] for n in development['notes']} & {n['hash'] for n in notes}:
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', required=True, choices=['fixtures', 'private', 'client', 'live-cli'])
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--source', choices=['fixture'])
    args = parser.parse_args()
    # Later stages implement these actual execution paths. Missing proof refuses.
    raise SystemExit('acceptance execution unavailable: core implementation pending')


if __name__ == '__main__':
    main()
