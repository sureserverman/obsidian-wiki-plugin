"""Hermetic fake-only pilot checks; a missing family must never pass."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/obsidian-wiki/scripts'))
# runpy-based discovery does not set Python's script-directory import path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from wiki_access import contracts


class ContractCases(unittest.TestCase):
    def test_strict_operation_shapes(self):
        good = {'schema': contracts.SCHEMA, 'operation': 'search', 'query': 'amber'}
        self.assertEqual(contracts.validate_request(good)['limit'], 5)
        bad = [dict(good, schema='v2'), dict(good, path='/etc/passwd'),
               dict(good, limit=True), dict(good, query='\ud800'), dict(good, limit=11), dict(good, query=''),
               dict(good, filters={'sql': 'x'}), dict(good, filters={'created_from': 'yesterday'}),
               {'schema': contracts.SCHEMA, 'operation': 'refresh'},
               {'schema': contracts.SCHEMA, 'operation': 'get', 'page_ids': [], 'generation': 'g'}]
        for request in bad:
            with self.subTest(request=request), self.assertRaises(contracts.Refusal):
                contracts.validate_request(request)

    def test_public_envelopes_reject_unknown_and_nonscalar_context(self):
        for operation, state in (('unlisted', 'ok'), ('search', 'unlisted'), ([], 'ok')):
            with self.subTest(operation=operation, state=state), self.assertRaises(contracts.Refusal):
                contracts.response(operation, {}, state=state)
        for operation, code in (([], 'invalid_request'), ('search', {'private-path': '/raw/CANARY'}),
                                ('search', 'unlisted'), ('search', 'ok')):
            with self.subTest(operation=operation, code=code), self.assertRaises(contracts.Refusal):
                contracts.error(operation, code)
        self.assertEqual(contracts.error('unlisted', 'invalid_request')['operation'], 'unknown')

    def test_read_budget_and_exact_selector(self):
        request = {'schema': contracts.SCHEMA, 'operation': 'get', 'page_ids': ['opaque'], 'generation': 'g'}
        self.assertEqual(contracts.validate_request(request)['byte_budget'], 24000)
        for mode in ('path', 'title', 'alias'):
            self.assertEqual(contracts.validate_request({'schema': contracts.SCHEMA,
                'operation': 'resolve', 'selector': {'kind': mode, 'value': 'Amber'}})['selector']['kind'], mode)
        with self.assertRaises(contracts.Refusal):
            contracts.validate_request(dict(request, byte_budget=24001))

    def test_bounded_error_has_no_private_context(self):
        result = contracts.error('search', 'source_unavailable')
        self.assertLess(len(contracts.encode(result)), 256)
        self.assertNotIn('path', result['error'])



class PolicyCases(unittest.TestCase):
    def project(self, body='## Steps\nUse amberctl — 😀.\n', fm=''):
        from wiki_access.policy import Policy, project
        raw = ('---\ntitle: "Amber"\ncreated: 2026-01-01\nupdated: 2026-02-01\n'
               'aliases: ["Golden, note", amber]\ntags:\n  - ops\n' + fm + '---\n' + body).encode()
        return raw, project('Runbooks/Amber.md', raw, Policy(['Runbooks']))

    def test_safe_projection_preserves_byte_maps(self):
        raw, page = self.project()
        self.assertEqual(page['metadata']['aliases'], ['Golden, note', 'amber'])
        for span in page['mapping']:
            self.assertEqual(raw[span['source_start']:span['source_end']],
                page['body'].encode()[span['start']:span['end']])
        self.assertEqual(page['metadata']['created'], '2026-01-01')

    def test_supported_category_and_record_class_matrix(self):
        from wiki_access.policy import Policy, project, CATEGORIES, PUBLISHED_TYPES, PUBLISHED_STATUSES
        policy = Policy(list(CATEGORIES))
        for category in CATEGORIES:
            page = project(category+'/Fixture.md', b'---\ntitle: Fixture\ncreated: 2026-01-01\n---\nSafe.\n', policy)
            self.assertEqual(page['metadata']['category'], category)
        for record in PUBLISHED_TYPES:
            self.project(fm='type: '+record+'\n')
        for status in PUBLISHED_STATUSES:
            self.project(fm='status: "'+status+'"\n')
        for classification in ('raw', 'original', 'draft', 'identity', 'unknown'):
            with self.subTest(classification=classification), self.assertRaises(contracts.Refusal):
                self.project(fm='type: '+classification+'\n')
        for status in ('private', 'protected', 'unreviewed', 'pending'):
            with self.subTest(status=status), self.assertRaises(contracts.Refusal):
                self.project(fm='status: '+status+'\n')

    def test_provenance_and_locator_fields_are_omitted(self):
        raw, page = self.project('## Steps\nSafe.\n## Source provenance\nraw/CANARY.md\n## Next\nSafe again.\n',
                                'sources: ["raw/CANARY.md"]\nsource-id: CANARY\n')
        self.assertNotIn('CANARY', contracts.encode(page).decode())
        self.assertEqual(len(page['omissions']), 2)
        self.assertIn('Safe again.', page['body'])

    def test_unsafe_and_unsupported_shapes_refuse_without_values(self):
        bad = ['title: duplicate\n', 'sensitivity: private\n', 'unknown: CANARY\n',
               'status: draft\n', 'type: raw\n', 'status: pending\n',
               'evidence-status: observed\nevidence_status: inferred\n',
               'title: \"\\ud800\"\n', 'tags: {a: b}\n', 'title: &anchor bad\n',
               'aliases: [unfinished\n', 'updated: yesterday\n', 'tags:\n    nested: value\n', "language: '\n",
               'aliases: [\"\\ud800\"]\n',
               'verification_status: approved\nverification-status: protected\n']
        for fm in bad:
            with self.subTest(fm=fm), self.assertRaises(contracts.Refusal) as exc:
                self.project(fm=fm)
            self.assertNotIn('CANARY', str(exc.exception))
        for body in ('raw/CANARY.md', '[[protected/CANARY]]', 'identity-map: CANARY',
                     'protected_locator_ref: CANARY', '<!-- PRIVATE -->',
                     '{\"protected_locator_ref\":\"CANARY\"}',
                     '{\"participant_id\":\"CANARY\"}',
                     'participant_id = CANARY', '| participant_id | CANARY |',
                     '| protected_locator_ref | CANARY |'):
            with self.subTest(body=body), self.assertRaises(contracts.Refusal):
                self.project(body=body)

    def test_unicode_line_separators_cannot_split_guarded_tokens(self):
        # str.splitlines breaks on all of these; the bytes still reach the body.
        for sep in ('\x0b', '\x0c', '\x1c', '\x1d', '\x1e', '\x85', ' ', ' ', '\r'):
            for body in ('raw'+sep+'/CANARY.md\n', '<!--'+sep+'private CANARY -->\n'):
                with self.subTest(sep=repr(sep), body=repr(body)), self.assertRaises(contracts.Refusal):
                    self.project(body=body)
        raw, page = self.project(body='Intro\x0cmore text\n## Next\nSafe.\n')
        self.assertIn('\x0cmore text', page['body'])
        for span in page['mapping']:
            self.assertEqual(raw[span['source_start']:span['source_end']],
                             page['body'].encode()[span['start']:span['end']])

    def test_deny_path_classes_and_allow_explicit_portfolio(self):
        from wiki_access.policy import Policy
        policy = Policy(['Runbooks'], ['Portfolio/ai-tools/amber/integration.md'])
        for path in ('raw/X.md', 'Runbooks/../X.md', '/Runbooks/X.md',
                     'Runbooks/sub/X.md', '.secret/X.md', 'Runbooks/.X.md',
                     'Runbooks/identity-map.md', 'Portfolio/ai-tools/other/integration.md'):
            with self.subTest(path=path):
                self.assertFalse(policy.permits(path))
        self.assertTrue(policy.permits('Runbooks/Amber.md'))
        self.assertTrue(policy.permits('Portfolio/ai-tools/amber/integration.md'))

    def test_opted_in_integration_schema_maps_project_and_edges(self):
        from wiki_access.policy import Policy, project
        locator = 'Portfolio/ai-tools/amber/integration.md'
        policy = Policy(['Runbooks'], [locator])
        raws = [b'---\nproject: amber\ndepends_on: []\nimpacts: []\n---\nSafe body.\n',
                b'---\nproject: amber\ndepends_on:\n  - target: "[[tools/worker]]"\n    why: "Worker isolation"\nimpacts: []\n---\nSafe body.\n']
        for raw in raws:
            page = project(locator, raw, policy)
            self.assertEqual(page['metadata']['title'], 'Integration: amber')
            self.assertNotIn('depends_on', page['metadata'])
            for span in page['mapping']:
                self.assertEqual(raw[span['source_start']:span['source_end']],
                                 page['body'].encode()[span['start']:span['end']])
        for suffix in ('  - target: worker\n', '  - target: worker\n    why: okay\n    why: duplicate\n',
                       '  - target: worker\n    sql: forbidden\n'):
            raw = ('---\nproject: amber\ndepends_on:\n'+suffix+'---\nSafe.').encode()
            with self.assertRaises(contracts.Refusal):
                project(locator, raw, policy)

    def test_safe_open_refuses_symlinks_and_race(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access.policy import safe_read
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp); (root/'Runbooks').mkdir()
            (root/'Runbooks/A.md').write_text('safe')
            (root/'Runbooks/link.md').symlink_to('A.md')
            (root/'Alias').symlink_to('Runbooks', target_is_directory=True)
            self.assertEqual(safe_read(root, 'Runbooks/A.md'), b'safe')
            for path in ('Runbooks/link.md', 'Alias/A.md', '../outside'):
                with self.subTest(path=path), self.assertRaises(contracts.Refusal):
                    safe_read(root, path)
            import os
            original = os.read
            def mutate(fd, size):
                data = original(fd, size)
                (root/'Runbooks/A.md').write_text('changed')
                return data
            with patch('wiki_access.policy.os.read', side_effect=mutate):
                with self.assertRaises(contracts.Refusal):
                    safe_read(root, 'Runbooks/A.md')

    def test_ancestor_replacement_during_read_refuses_detached_bytes(self):
        import tempfile, os
        from unittest.mock import patch
        from wiki_access.policy import safe_read
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp); (root/'Runbooks').mkdir()
            (root/'Runbooks/A.md').write_text('old content')
            original = os.read; changed = False
            def mutate(fd, size):
                nonlocal changed
                data = original(fd, size)
                if not changed:
                    changed = True
                    (root/'Runbooks').rename(root/'Detached')
                    (root/'Runbooks').mkdir()
                    (root/'Runbooks/A.md').write_text('replacement')
                return data
            with patch('wiki_access.policy.os.read', side_effect=mutate):
                with self.assertRaises(contracts.Refusal):
                    safe_read(root, 'Runbooks/A.md')


class WorkloadCases(unittest.TestCase):
    def test_frozen_balanced_independent_workload(self):
        import wiki_access_acceptance as acceptance
        dev = acceptance.fake_manifest('development')
        locked = acceptance.fake_manifest('acceptance')
        self.assertEqual(acceptance.validate_manifest(locked, development=dev),
                         dict.fromkeys(acceptance.CLASSES, 5))
        self.assertEqual(len(locked['controls']), 6)

    def test_implementation_lock_refuses_changed_or_missing_code(self):
        import tempfile
        import wiki_access_acceptance as a
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)/'example.py'; path.write_text('version = 1')
            lock = a.implementation_lock([path]); a.validate_implementation_lock(lock)
            path.write_text('version = 2')
            with self.assertRaises(contracts.Refusal):
                a.validate_implementation_lock(lock)
            path.unlink()
            with self.assertRaises(contracts.Refusal):
                a.validate_implementation_lock(lock)

    def test_corrupt_empty_duplicate_overlap_and_incomplete_labels_refuse(self):
        import copy
        import wiki_access_acceptance as a
        base = a.fake_manifest('acceptance'); dev = a.fake_manifest('development')
        corruptions = [lambda m: m['questions'].clear(),
                       lambda m: m['questions'].append(copy.deepcopy(m['questions'][0])),
                       lambda m: m['questions'][0]['support'].clear(),
                       lambda m: m['questions'][0]['support'][0].update(end=999999),
                       lambda m: m['notes'][0].update(raw='tampered'),
                       lambda m: m['notes'][0].update(topic=dev['notes'][0]['topic']),
                       lambda m: m['controls'].clear()]
        for corrupt in corruptions:
            m = copy.deepcopy(base); corrupt(m); m.pop('fingerprint'); m=a.seal(m)
            with self.subTest(corrupt=corrupt), self.assertRaises(contracts.Refusal):
                a.validate_manifest(m, development=dev)
        base['questions'][0]['query'] = 'changed after freeze'
        with self.assertRaises(contracts.Refusal):
            a.validate_manifest(base)

    def test_review_control_labels_and_date_omissions_refuse(self):
        import copy
        import wiki_access_acceptance as a
        base = a.fake_manifest('acceptance')
        cases = [lambda m: m['controls'][3]['required'].clear(),
                 lambda m: m['controls'][4]['support'].pop(),
                 lambda m: m['controls'][3]['support'][0].update(event_date={'date': '2026-03-01'}),
                 lambda m: m['controls'][2].update(query=None, expected='abstain', required=[], forbidden=[]),
                 lambda m: m['questions'][3]['support'][0].update(event_date=None),
                 lambda m: m['controls'][3]['support'][0].update(quote=23),
                 lambda m: m['controls'].__setitem__(0, None),
                 lambda m: m['questions'][0].update(id=''),
                 lambda m: m['controls'][3]['support'].append(copy.deepcopy(m['controls'][3]['support'][0]))]
        for mutate in cases:
            manifest = copy.deepcopy(base); mutate(manifest); manifest.pop('fingerprint')
            manifest = a.seal(manifest)
            with self.subTest(mutate=mutate), self.assertRaises(contracts.Refusal):
                a.validate_manifest(manifest)

    def test_normalized_question_duplicates_and_development_overlap_refuse(self):
        import copy
        import wiki_access_acceptance as a
        dev = a.fake_manifest('development'); base = a.fake_manifest('acceptance')
        for query in ('  '+base['questions'][0]['query'].upper()+'  ', dev['questions'][0]['query']):
            manifest = copy.deepcopy(base); manifest['questions'][1]['query'] = query
            manifest.pop('fingerprint'); manifest = a.seal(manifest)
            with self.subTest(query=query), self.assertRaises(contracts.Refusal):
                a.validate_manifest(manifest, development=dev)


class Stage1IntegrationCases(unittest.TestCase):
    def test_whole_public_fixture_inventory_has_mapped_evidence(self):
        import wiki_access_acceptance as a
        from wiki_access.policy import project, Policy
        manifest = a.fake_manifest('acceptance')
        a.validate_manifest(manifest, development=a.fake_manifest('development'))
        for note in manifest['notes']:
            page = project(note['locator'], note['raw'].encode(), Policy(['Runbooks']))
            self.assertNotIn('PRIVATE_CANARY', contracts.encode(page).decode())
            for span in page['mapping']:
                self.assertEqual(note['raw'].encode()[span['source_start']:span['source_end']],
                                 page['body'].encode()[span['start']:span['end']])
        for locator in ('raw/PRIVATE_CANARY.md', 'Runbooks/identity-map.md'):
            with self.assertRaises(contracts.Refusal) as exc:
                project(locator, manifest['notes'][0]['raw'].encode(), Policy(['Runbooks']))
            self.assertNotIn('PRIVATE_CANARY', contracts.encode(contracts.error('get', exc.exception.code)).decode())

class StoreCases(unittest.TestCase):
    def test_section_maps_weighted_or_and_distinct_page_ranking(self):
        import tempfile
        from wiki_access import store
        from wiki_access.policy import Policy, project
        policy = Policy(['Runbooks'])
        pages = [project('Runbooks/'+name+'.md', ('---\ntitle: '+name+'\ncreated: 2026-01-01\n---\n'+body).encode(), policy)
                 for name, body in [('Amber', '# Amber\nUse amberctl --check 😀.\n## Next\namberctl again.\n'),
                                    ('Other', '# Other\nGolden fallback.\n')]]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)/'index.sqlite'
            store.build(path, pages, 'a'*64)
            with store.Store(path, 'a'*64) as db:
                hits = db.search('amberctl golden', 5, {})
                self.assertEqual(len(hits), 2)
                self.assertEqual(len({h['page_id'] for h in hits}), 2)
                self.assertEqual(db.resolve('title', 'Amber')[0]['locator'], 'Runbooks/Amber.md')
                self.assertEqual(db.resolve('alias', 'unknown'), [])
                for row in db.sections():
                    page = db.page(row['page_id'])
                    self.assertEqual(page['body'].encode()[row['start']:row['end']].decode(), row['body'])
                    self.assertTrue(row['mapping'])
                self.assertEqual(db.metadata()['recipe'], store.RECIPE)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_sections_use_policy_line_and_heading_rules(self):
        from wiki_access import store
        from wiki_access.policy import Policy, project
        body = 'Intro\x0c# Not a heading\n```\n# Fenced\n```\n## Real\nText.\n'
        page = project('Runbooks/A.md', ('---\ntitle: A\ncreated: 2026-01-01\n---\n'+body).encode(), Policy(['Runbooks']))
        rows = list(store.section_rows(page))
        self.assertEqual([row['heading'] for row in rows], ['', 'Real'])
        self.assertEqual(''.join(row['body'] for row in rows), page['body'])

    def test_literal_query_refuses_operators_and_binds_sql(self):
        from wiki_access import store
        for query in ('AND OR NOT NEAR', '"*"', '   ', 'the is a', 'x '*65):
            with self.subTest(query=query), self.assertRaises(contracts.Refusal):
                store.terms(query)
        self.assertEqual(store.terms('amberctl --check Русский 😀'), ['amberctl', '--check', 'Русский'])
        self.assertIn('"DROP"', store.expression("amber'; DROP TABLE pages; --"))

    def test_integrity_schema_runtime_and_malformed_maps_refuse(self):
        import tempfile, sqlite3, copy
        from unittest.mock import patch
        from wiki_access import store
        from wiki_access.policy import Policy, project
        page = project('Runbooks/A.md', b'---\ntitle: A\ncreated: 2026-01-01\n---\nSafe.\n', Policy(['Runbooks']))
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)/'index.sqlite'
            bad = copy.deepcopy(page); bad['mapping'][0]['end'] += 1
            with self.assertRaises(contracts.Refusal): store.build(path, [bad], 'b'*64)
            self.assertFalse(path.exists())
            store.build(path, [page], 'b'*64)
            with sqlite3.connect(path) as db: db.execute("UPDATE meta SET value='unknown' WHERE key='schema'")
            with self.assertRaises(contracts.Refusal): store.Store(path, 'b'*64)
            path.write_bytes(b'corrupt')
            with self.assertRaises(contracts.Refusal): store.Store(path, 'b'*64)
        with patch('wiki_access.store.sqlite3.connect', side_effect=sqlite3.OperationalError()):
            with self.assertRaises(contracts.Refusal): store.capability()

    def test_missing_schema_and_every_malformed_record_shape_refuse(self):
        import tempfile, sqlite3, copy
        from wiki_access import store
        from wiki_access.policy import Policy, project
        page = project('Runbooks/A.md', b'---\ntitle: A\ncreated: 2026-01-01\n---\nSafe.\n', Policy(['Runbooks']))
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)/'index.sqlite'
            for mutate in (lambda p: p.pop('omissions'), lambda p: p.update(body=4),
                           lambda p: p.update(mapping=[['start','end','source_start','source_end']]),
                           lambda p: p.update(omissions=[{}])):
                bad = copy.deepcopy(page); mutate(bad)
                with self.assertRaises(contracts.Refusal): store.build(path, [bad], 'b'*64)
                self.assertFalse(path.exists())
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
                db.executemany('INSERT INTO meta VALUES (?,?)', [('schema', store.SCHEMA), ('recipe', store.RECIPE), ('generation','b'*64)])
            with self.assertRaises(contracts.Refusal): store.Store(path, 'b'*64)

    def test_weight_order_source_maps_and_executed_literal_sql(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access import store
        from wiki_access.policy import Policy, project
        originals = [('Runbooks/Title.md', b'---\ntitle: weighttoken\ncreated: 2026-01-01\n---\n# Step\nsharedtoken plain.\n## Sources\nraw/PRIVATE_CANARY.md\n## Next\nsharedtoken.\n'),
                     ('Runbooks/Body.md', b'---\ntitle: other\ncreated: 2026-01-01\n---\n# Step\nsharedtoken weighttoken.\n')]
        pages = [project(locator, raw, Policy(['Runbooks'])) for locator, raw in originals]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)/'index.sqlite'; store.build(path, pages, 'c'*64)
            before = path.read_bytes()
            with store.Store(path, 'c'*64) as db:
                self.assertEqual(db.search('weighttoken', 5, {})[0]['locator'], 'Runbooks/Title.md')
                self.assertEqual(db.search('sharedtoken', 5, {}), db.search('sharedtoken', 5, {}))
                db.search("sharedtoken'; DROP TABLE pages; --", 5, {})
                self.assertEqual(len(db.resolve('title', 'other')), 1)
                for row in db.sections():
                    page = db.page(row['page_id']); raw = dict(originals)[page['locator']]
                    for span in row['mapping']:
                        self.assertEqual(raw[span['source_start']:span['source_end']],
                                         page['body'].encode()[span['start']:span['end']])
            self.assertEqual(path.read_bytes(), before)
        with patch('wiki_access.store.sys.version_info', (3, 11)):
            with self.assertRaises(contracts.Refusal): store.capability()


    def test_sqlite_build_leaf_replacement_never_writes_a_source(self):
        import tempfile,sqlite3,os
        from unittest.mock import patch
        from wiki_access import store
        from wiki_access.policy import Policy,project
        page=project('Runbooks/A.md',b'---\ntitle: A\ncreated: 2026-01-01\n---\nSafe.\n',Policy(['Runbooks']))
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'index.sqlite'; source=pathlib.Path(tmp)/'source'; source.write_bytes(b''); source.chmod(0o600)
            original=sqlite3.connect
            def mutate(*args,**kwargs):
                if path.exists() and path.stat().st_size==0:
                    path.unlink(); os.link(source,path)
                return original(*args,**kwargs)
            with patch('wiki_access.store.sqlite3.connect',side_effect=mutate):
                with self.assertRaises(contracts.Refusal): store.build(path,[page],'d'*64)
            self.assertEqual(source.read_bytes(),b'')


class GenerationCases(unittest.TestCase):
    def fixture(self, tmp):
        from wiki_access.policy import Policy
        root = pathlib.Path(tmp)/'vault'; root.mkdir(); (root/'Runbooks').mkdir()
        (root/'Runbooks/A.md').write_text('---\ntitle: Amber\ncreated: 2026-01-01\n---\n# Steps\nUse amberctl.\n')
        return root, pathlib.Path(tmp)/'state', Policy(['Runbooks'])

    def test_whole_inventory_mutations_refuse_old_generation(self):
        import tempfile
        from wiki_access.generation import Manager
        for mutation in ('add', 'edit', 'delete', 'rename', 'reclassify', 'policy'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root, state, policy = self.fixture(tmp); manager = Manager(root, state, policy)
                manager.refresh()
                with manager.pin() as pin:
                    pin.check()
                    note = root/'Runbooks/A.md'
                    if mutation == 'add': (root/'Runbooks/B.md').write_bytes(note.read_bytes())
                    elif mutation == 'edit': note.write_text(note.read_text()+'changed')
                    elif mutation == 'delete': note.unlink()
                    elif mutation == 'rename': note.rename(root/'Runbooks/B.md')
                    elif mutation == 'reclassify': note.write_text(note.read_text().replace('created:', 'sensitivity: private\ncreated:'))
                    else:
                        from wiki_access.policy import Policy
                        pin.manager.policy = Policy(['Runbooks', 'Patterns'])
                    with self.assertRaises(contracts.Refusal): pin.check()

    def test_local_private_creation_and_corrupt_pointer_refuse(self):
        import tempfile, os
        from unittest.mock import patch
        from wiki_access.generation import Manager
        with tempfile.TemporaryDirectory() as tmp:
            root, state, policy = self.fixture(tmp)
            with patch('wiki_access.generation.filesystem', return_value='nfs4'):
                with self.assertRaises(contracts.Refusal): Manager(root, state, policy).refresh()
            with self.assertRaises(contracts.Refusal): Manager(root, root/'state', policy).refresh()
            alias = pathlib.Path(tmp)/'link'; alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises(contracts.Refusal): Manager(alias, state, policy).refresh()
            manager = Manager(root, state, policy); manager.refresh()
            for directory, dirs, files in os.walk(state):
                self.assertEqual(pathlib.Path(directory).stat().st_mode & 0o777, 0o700)
                for name in files: self.assertEqual((pathlib.Path(directory)/name).stat().st_mode & 0o777, 0o600)
            (state/'current.json').write_text('{"generation":"../../vault"}')
            with self.assertRaises(contracts.Refusal):
                with manager.pin(): pass

    def test_pinned_reader_retention_and_interrupted_refresh(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access.generation import Manager
        with tempfile.TemporaryDirectory() as tmp:
            root, state, policy = self.fixture(tmp); manager = Manager(root, state, policy)
            first = manager.refresh()['generation']
            with manager.pin() as pin:
                note = root/'Runbooks/A.md'; note.write_text(note.read_text()+'new')
                second = manager.refresh()['generation']
                self.assertNotEqual(first, second)
                self.assertTrue((state/'generations'/first).exists())
                with self.assertRaises(contracts.Refusal): pin.check()
            manager.refresh()
            self.assertFalse((state/'generations'/first).exists())
            pointer = (state/'current.json').read_bytes()
            note.write_text(note.read_text()+'next')
            with patch('wiki_access.generation.os.replace', side_effect=OSError()):
                with self.assertRaises(contracts.Refusal): manager.refresh()
            self.assertEqual((state/'current.json').read_bytes(), pointer)
            with self.assertRaises(contracts.Refusal):
                with manager.pin() as pin: pin.check()

    def test_manifest_tamper_symlinks_and_disappearing_source_refuse(self):
        import tempfile, json
        from wiki_access.generation import Manager
        for mutation in ('manifest', 'leaf', 'ancestor', 'missing'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root, state, policy = self.fixture(tmp); manager = Manager(root, state, policy)
                generation = manager.refresh()['generation']
                if mutation == 'manifest': (state/'generations'/generation/'manifest.json').write_text('{}')
                elif mutation == 'leaf':
                    note = root/'Runbooks/A.md'; note.rename(root/'Runbooks/B.md'); note.symlink_to('B.md')
                elif mutation == 'ancestor':
                    (root/'Runbooks').rename(root/'Other'); (root/'Runbooks').symlink_to('Other', target_is_directory=True)
                else: root.rename(pathlib.Path(tmp)/'missing')
                with self.assertRaises(contracts.Refusal):
                    with manager.pin() as pin: pin.check()

    def test_absent_configured_portfolio_note_does_not_block_reads(self):
        import tempfile
        from wiki_access.generation import Manager
        from wiki_access.policy import Policy
        locator = 'Portfolio/ai-tools/amber/integration.md'
        with tempfile.TemporaryDirectory() as tmp:
            root, state, _ = self.fixture(tmp)
            manager = Manager(root, state, Policy(['Runbooks'], [locator]))
            self.assertEqual(manager.refresh()['pages'], 1)
            with manager.pin() as pin:
                pin.check()
                # The note appearing later is a change the old generation must not hide.
                note = root/locator; note.parent.mkdir(parents=True)
                note.write_text('---\nproject: amber\ndepends_on: []\nimpacts: []\n---\nSafe body.\n')
                with self.assertRaises(contracts.Refusal): pin.check()
            self.assertEqual(manager.refresh()['pages'], 2)
            note.unlink()
            self.assertEqual(manager.refresh()['pages'], 1)
            # A present-but-unreadable entry still refuses instead of being skipped.
            note.symlink_to(root/'Runbooks/A.md')
            with self.assertRaises(contracts.Refusal): manager.refresh()

    def test_absent_portfolio_note_appearing_mid_scan_is_stale(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access import generation
        from wiki_access.policy import Policy, safe_read
        locator = 'Portfolio/ai-tools/amber/integration.md'
        with tempfile.TemporaryDirectory() as tmp:
            root, _, _ = self.fixture(tmp)
            def read(base, name):
                result = safe_read(base, name)
                note = root/locator
                if not note.exists():
                    note.parent.mkdir(parents=True); note.write_text('---\nproject: amber\n---\n')
                return result
            # Sorted order reads Portfolio/ first, so it is absent; Runbooks/A.md adds it.
            with patch.object(generation.source_policy, 'safe_read', read), self.assertRaises(contracts.Refusal) as exc:
                generation.snapshot(root, Policy(['Runbooks'], [locator]))
            self.assertEqual(exc.exception.code, 'generation_stale')

    def test_large_inventory_and_mid_scan_addition(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access import generation
        with tempfile.TemporaryDirectory() as tmp:
            root,state,policy=self.fixture(tmp)
            for i in range(410): (root/'Runbooks'/('Fixture'+str(i)+'.md')).write_bytes((root/'Runbooks/A.md').read_bytes())
            manager=generation.Manager(root,state,policy); gen=manager.refresh()['generation']
            self.assertGreater((state/'generations'/gen/'manifest.json').stat().st_size,65536)
            with manager.pin() as pin: pin.check()
            original=generation.source_policy.safe_read; added=False
            def mutate(*args):
                nonlocal added
                raw=original(*args)
                if not added: (root/'Runbooks/New.md').write_bytes(raw); added=True
                return raw
            with patch('wiki_access.generation.source_policy.safe_read',side_effect=mutate):
                with self.assertRaises(contracts.Refusal):
                    with manager.pin() as pin: pin.check()

    def test_state_path_swap_never_writes_to_source(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access import generation
        with tempfile.TemporaryDirectory() as tmp:
            root,state,policy=self.fixture(tmp); manager=generation.Manager(root,state,policy)
            original=generation.write_private_at; swapped=False
            def mutate(parent,name,raw):
                nonlocal swapped
                if name.startswith('pointer-') and not swapped:
                    state.rename(pathlib.Path(tmp)/'detached-state'); state.symlink_to(root,target_is_directory=True); swapped=True
                return original(parent,name,raw)
            before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch('wiki_access.generation.write_private_at',side_effect=mutate):
                with self.assertRaises(contracts.Refusal): manager.refresh()
            self.assertEqual(before,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_hardlinks_nested_mounts_and_replaced_lock_refuse(self):
        import tempfile,os
        from unittest.mock import patch
        from wiki_access import generation
        with tempfile.TemporaryDirectory() as tmp:
            root,state,policy=self.fixture(tmp); manager=generation.Manager(root,state,policy); manager.refresh()
            real=generation.filesystem
            with patch('wiki_access.generation.filesystem',side_effect=lambda p: 'nfs4' if p.name=='generations' else real(p)):
                with self.assertRaises(contracts.Refusal):
                    with manager.pin(): pass
            note=root/'Runbooks/A.md'; note.chmod(0o600); (state/'refresh.lock').unlink(); os.link(note,state/'refresh.lock')
            with self.assertRaises(contracts.Refusal): manager.refresh()
            (state/'refresh.lock').unlink()
            with self.assertRaises(contracts.Refusal):
                with manager.lock(exclusive=True,create=True):
                    (state/'refresh.lock').rename(state/'refresh.old')
                    (state/'refresh.lock').write_bytes(b''); (state/'refresh.lock').chmod(0o600)


    def test_fifo_state_files_refuse_without_blocking(self):
        import tempfile,os
        from wiki_access.generation import Manager
        for filename in ('refresh.lock','index.sqlite'):
            with self.subTest(filename=filename),tempfile.TemporaryDirectory() as tmp:
                root,state,policy=self.fixture(tmp); manager=Manager(root,state,policy); gen=manager.refresh()['generation']
                path=state/'refresh.lock' if filename=='refresh.lock' else state/'generations'/gen/filename
                path.unlink(); os.mkfifo(path,0o600)
                with self.assertRaises(contracts.Refusal):
                    with manager.pin(): pass


    def test_failed_refresh_keeps_total_storage_within_budget(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access import generation
        with tempfile.TemporaryDirectory() as tmp:
            root,state,policy=self.fixture(tmp); manager=generation.Manager(root,state,policy); manager.refresh()
            active=manager.storage_size(); pointer=(state/'current.json').read_bytes()
            note=root/'Runbooks/A.md'; note.write_text(note.read_text()+'changed')
            with patch('wiki_access.generation.STORE_BYTES',active+100):
                with self.assertRaises(contracts.Refusal) as caught: manager.refresh()
                self.assertEqual(caught.exception.code,'budget_exhausted')
                self.assertLessEqual(manager.storage_size(),active+100)
            self.assertEqual((state/'current.json').read_bytes(),pointer)
            self.assertEqual(len(list((state/'generations').iterdir())),1)

    def test_refresh_sqlite_leaf_injection_preserves_every_source_file(self):
        import tempfile,sqlite3,os
        from unittest.mock import patch
        from wiki_access.generation import Manager
        with tempfile.TemporaryDirectory() as tmp:
            root,state,policy=self.fixture(tmp); source=root/'untouched'; source.write_bytes(b''); source.chmod(0o600)
            before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            original=sqlite3.connect; injected=False
            def mutate(*args,**kwargs):
                nonlocal injected
                for path in (state/'generations').glob('staging-*/index.sqlite'):
                    if not injected:
                        path.unlink(); os.link(source,path); injected=True
                return original(*args,**kwargs)
            with patch('wiki_access.store.sqlite3.connect',side_effect=mutate):
                with self.assertRaises(contracts.Refusal): Manager(root,state,policy).refresh()
            self.assertTrue(injected)
            self.assertEqual(before,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()})


class LookupCases(unittest.TestCase):
    def test_unique_path_title_alias_and_ambiguity_are_explicit(self):
        import tempfile
        from wiki_access.generation import Manager
        from wiki_access.service import Service
        from wiki_access.policy import Policy
        with tempfile.TemporaryDirectory() as tmp:
            root, state, _ = GenerationCases().fixture(tmp)
            (root/'Runbooks/A.md').write_text('---\ntitle: Amber\ncreated: 2026-01-01\naliases: [Golden]\ntags: [ops]\n---\n## Steps\nUse amberctl --check Русский.\n')
            manager = Manager(root,state,Policy(['Runbooks'])); manager.refresh(); service = Service(manager)
            for kind, value in [('path','Runbooks/A.md'),('title','amber'),('alias','golden')]:
                result = service.handle({'schema':contracts.SCHEMA,'operation':'resolve','selector':{'kind':kind,'value':value}})
                self.assertEqual(result['state'], 'ok'); self.assertEqual(len(result['value']['pages']),1)
            (root/'Runbooks/B.md').write_bytes((root/'Runbooks/A.md').read_bytes()); manager.refresh()
            result = service.handle({'schema':contracts.SCHEMA,'operation':'resolve','selector':{'kind':'title','value':'Amber'}})
            self.assertEqual(result['state'],'ambiguous'); self.assertEqual(len(result['value']['pages']),2)

    def test_ranked_literal_unicode_filters_and_verified_empty(self):
        import tempfile
        from wiki_access.generation import Manager
        from wiki_access.service import Service
        with tempfile.TemporaryDirectory() as tmp:
            root,state,policy=GenerationCases().fixture(tmp)
            note=root/'Runbooks/A.md'; note.write_text(note.read_text().replace('---\n# Steps','aliases: [Golden]\ntags: [ops]\nupdated: 2026-02-01\nevidence-status: observed\n---\n# Steps')+'Русский --check.\n')
            manager=Manager(root,state,policy); manager.refresh(); service=Service(manager)
            for query in ('amberctl --check', 'Русский', 'Golden'):
                result=service.handle({'schema':contracts.SCHEMA,'operation':'search','query':query,'filters':{'tag':'ops','created_from':'2026-01-01'}})
                self.assertEqual(result['state'],'ok'); self.assertEqual(len(result['value']['pages']),1)
                self.assertNotIn('read_receipt',contracts.encode(result).decode())
            result=service.handle({'schema':contracts.SCHEMA,'operation':'search','query':'unknownphrase'})
            self.assertEqual(result['state'],'empty')
            self.assertEqual(service.handle({'schema':contracts.SCHEMA,'operation':'search','query':'amberctl','filters':{'verification_status':'verified'}})['state'],'unsupported_filter')
            self.assertLessEqual(len(contracts.encode(service.handle({'schema':contracts.SCHEMA,'operation':'status'}))),8000)

    def test_post_search_drift_discards_all_buffered_metadata(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access.generation import Manager
        from wiki_access.service import Service
        from wiki_access.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            root,state,policy=GenerationCases().fixture(tmp); manager=Manager(root,state,policy); manager.refresh(); service=Service(manager)
            original=Store.search
            def mutate(db,*args):
                result=original(db,*args); (root/'Runbooks/A.md').unlink(); return result
            with patch.object(Store,'search',mutate):
                result=service.handle({'schema':contracts.SCHEMA,'operation':'search','query':'amberctl'})
            self.assertFalse(result['ok']); self.assertNotIn('Amber',contracts.encode(result).decode())
            for op in ('search','resolve','status'):
                req={'schema':contracts.SCHEMA,'operation':op}
                if op=='search': req['query']='amberctl'
                elif op=='resolve': req['selector']={'kind':'title','value':'Amber'}
                self.assertFalse(service.handle(req)['ok'])
            with self.assertRaises(contracts.Refusal): Service(None)

    def test_lookup_runs_pin_check_and_one_final_guard(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access.generation import Manager, Pinned
        from wiki_access.service import Service
        with tempfile.TemporaryDirectory() as tmp:
            root,state,policy=GenerationCases().fixture(tmp); manager=Manager(root,state,policy); manager.refresh(); service=Service(manager)
            original=Pinned.check; calls=[]
            def counted(pin):
                calls.append(pin.generation); return original(pin)
            with patch.object(Pinned,'check',counted):
                result=service.handle({'schema':contracts.SCHEMA,'operation':'search','query':'amberctl'})
            self.assertTrue(result['ok'])
            # One full check inside Manager.pin() plus the post-lookup disclosure guard.
            self.assertEqual(len(calls),2)


class Stage2IntegrationCases(unittest.TestCase):
    def test_complete_fake_inventory_and_content_operation_guard_matrix(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access.generation import Manager, Pinned
        from wiki_access.service import Service
        import wiki_access_acceptance as a
        from wiki_access.policy import Policy
        # Development fixtures only: the independent acceptance set stays unopened.
        manifest=a.fake_manifest('development')
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)/'vault'; (root/'Runbooks').mkdir(parents=True)
            for note in manifest['notes']:
                (root/note['locator']).write_text(note['raw'])
            denied=root/'Runbooks/Denied.md'; denied.write_text('---\ntitle: PRIVATE_CANARY\ncreated: 2026-01-01\nsensitivity: private\n---\nPRIVATE_CANARY\n')
            manager=Manager(root,pathlib.Path(tmp)/'state',Policy(['Runbooks'])); manager.refresh(); service=Service(manager)
            for op in ('resolve','search','status'):
                request={'schema':contracts.SCHEMA,'operation':op}
                if op=='resolve': request['selector']={'kind':'title','value':'PRIVATE_CANARY'}
                if op=='search': request['query']='PRIVATE_CANARY'
                response=service.handle(request)
                self.assertTrue(response['ok']); self.assertNotIn('PRIVATE_CANARY',contracts.encode(response).decode())
                with patch.object(Pinned,'check',side_effect=contracts.Refusal('generation_stale')):
                    response=service.handle(request)
                    self.assertFalse(response['ok']); self.assertNotIn('value',response)
            for note in manifest['notes']:
                response=service.handle({'schema':contracts.SCHEMA,'operation':'resolve','selector':{'kind':'path','value':note['locator']}})
                self.assertEqual(response['state'],'ok')
            denied.write_text(denied.read_text().replace('sensitivity: private\n',''))
            self.assertEqual(service.handle({'schema':contracts.SCHEMA,'operation':'status'})['state'],'generation_stale')

    def test_refresh_rename_and_reclassification_while_lookup_is_pinned(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access.generation import Manager
        from wiki_access.service import Service
        from wiki_access.store import Store
        for mutation in ('rename','reclassify','refresh'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                root,state,policy=GenerationCases().fixture(tmp); manager=Manager(root,state,policy); manager.refresh()
                original=Store.resolve
                def mutate(db,*args):
                    result=original(db,*args); note=root/'Runbooks/A.md'
                    if mutation=='rename': note.rename(root/'Runbooks/B.md')
                    elif mutation=='reclassify': note.write_text(note.read_text().replace('created:','sensitivity: private\ncreated:'))
                    else: note.write_text(note.read_text()+'new')
                    manager.refresh(); return result
                with patch.object(Store,'resolve',mutate):
                    result=Service(manager).handle({'schema':contracts.SCHEMA,'operation':'resolve','selector':{'kind':'title','value':'Amber'}})
                self.assertFalse(result['ok']); self.assertNotIn('value',result)

    def test_negative_control_detects_missing_guard_and_checks_disclosure_budget(self):
        import tempfile,json
        from unittest.mock import patch
        from wiki_access.generation import Manager,Pinned
        from wiki_access.service import Service
        from wiki_access.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            root,state,policy=GenerationCases().fixture(tmp); manager=Manager(root,state,policy); manager.refresh()
            original=Store.search
            def mutate(db,*args):
                result=original(db,*args); (root/'Runbooks/A.md').unlink(); return result
            # Deliberately defective boundary: the gate assertion must detect it.
            with patch.object(Store,'search',mutate),patch.object(Pinned,'check',return_value=None):
                vulnerable=Service(manager).handle({'schema':contracts.SCHEMA,'operation':'search','query':'amberctl'})
            with self.assertRaises(AssertionError): self.assertFalse(vulnerable['ok'])
            raw='---\ntitle: Amber\ncreated: 2026-01-01\naliases: '+json.dumps(['alias'+str(i)+'a'*1600 for i in range(6)])+'\n---\nSafe amberctl.\n'
            (root/'Runbooks/A.md').write_text(raw); manager.refresh()
            result=Service(manager).handle({'schema':contracts.SCHEMA,'operation':'search','query':'amberctl'})
            self.assertEqual(result['state'],'budget_exhausted'); self.assertLessEqual(len(contracts.encode(result)),8000)


class ReadCases(unittest.TestCase):
    def fixture(self, tmp, bodies=None):
        from wiki_access.generation import Manager
        from wiki_access.service import Service
        root, state, policy = GenerationCases().fixture(tmp)
        if bodies:
            for i, body in enumerate(bodies):
                (root/'Runbooks'/f'{i}.md').write_bytes(
                    ('---\r\ntitle: Note '+str(i)+'\r\ncreated: 2026-01-01\r\n'
                     'updated: 2026-02-01\r\n---\r\n'+body).encode())
            (root/'Runbooks/A.md').unlink()
        manager = Manager(root, state, policy); manager.refresh()
        service = Service(manager)
        found = service.handle({'schema':contracts.SCHEMA, 'operation':'search', 'query':'Note Amber', 'limit':10})
        return root, manager, service, found

    def get(self, service, found, budget=24000, ids=None):
        return service.handle({'schema':contracts.SCHEMA, 'operation':'get',
            'generation':found['generation'], 'page_ids':ids or [p['page_id'] for p in found['value']['pages']],
            'byte_budget':budget})

    def test_one_to_five_complete_mapped_multibyte_crlf_projections(self):
        import tempfile
        bodies = ['## Steps\r\nРусский 😀 '+str(i)+'\r\n```md\r\n# Fake\r\n```\r\n'
                  '## Source provenance\r\nraw/PRIVATE_CANARY\r\n## End\r\nDone.\r\n' for i in range(5)]
        with tempfile.TemporaryDirectory() as tmp:
            root, manager, service, found = self.fixture(tmp, bodies)
            for count in range(1,6):
                result = self.get(service, found, ids=[p['page_id'] for p in found['value']['pages'][:count]])
                self.assertTrue(result['ok'], result)
                self.assertEqual(len(result['value']['pages']), count)
                self.assertLessEqual(len(contracts.encode(result)),24000)
                self.assertNotIn('PRIVATE_CANARY',contracts.encode(result).decode())
                for page in result['value']['pages']:
                    self.assertTrue(page['complete'])
                    raw = (root/page['locator']).read_bytes(); body = page['body'].encode()
                    self.assertIn('Русский 😀',page['body']); self.assertIn('# Fake',page['body'])
                    self.assertEqual(page['body_bytes'],len(body))
                    self.assertEqual(page['metadata']['updated'],'2026-02-01')
                    for span in page['mapping']:
                        self.assertEqual(body[span['start']:span['end']],raw[span['source_start']:span['source_end']])

    def test_exact_serialized_budget_and_oversize_omission(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root, manager, service, found = self.fixture(tmp,['😀'*7000,'Small complete.'])
            result = self.get(service,found)
            self.assertTrue(result['ok'],result)
            self.assertEqual(len(result['value']['pages']),1)
            self.assertEqual(result['value']['pages'][0]['body'],'Small complete.')
            self.assertEqual(result['value']['omitted'][0]['reason'],'over_budget')
            self.assertLessEqual(len(contracts.encode(result)),24000)
            omitted_id=result['value']['omitted'][0]['page_id']
            self.assertNotIn(omitted_id,[p['page_id'] for p in result['value']['pages']])
            # Small response budgets may refuse even the omission envelope.
            result=self.get(service,found,256)
            self.assertLessEqual(len(contracts.encode(result)),256)
            self.assertNotIn('body',contracts.encode(result).decode())

    def test_unknown_mixed_and_stale_ids_refuse_entire_bundle(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root, manager, service, found=self.fixture(tmp)
            good=found['value']['pages'][0]['page_id']
            self.assertTrue(self.get(service,found)['ok'])
            result=self.get(service,found,ids=[good,'unknown'])
            self.assertEqual(result['state'],'invalid_request'); self.assertNotIn('value',result)
            (root/'Runbooks/A.md').write_text((root/'Runbooks/A.md').read_text()+'changed')
            self.assertEqual(self.get(service,found)['state'],'generation_stale')
            manager.refresh()
            self.assertFalse(self.get(service,found)['ok'])

    def test_source_change_after_get_discards_buffered_evidence(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access import evidence
        with tempfile.TemporaryDirectory() as tmp:
            root, manager, service, found=self.fixture(tmp)
            original=evidence.read_page
            def mutate(*args):
                value=original(*args)
                (root/'Runbooks/A.md').unlink()
                return value
            with patch.object(evidence,'read_page',mutate):
                result=self.get(service,found)
            self.assertFalse(result['ok']); self.assertNotIn('value',result)


class ReceiptCases(unittest.TestCase):
    def test_rotation_during_verification_or_after_signing_discards_provenance(self):
        import tempfile
        from unittest.mock import patch
        from wiki_access import evidence
        from wiki_access.generation import Pinned
        with tempfile.TemporaryDirectory() as tmp:
            root,manager,service,found=ReadCases().fixture(tmp)
            token=ReadCases().get(service,found)['value']['read_receipt']
            with manager.pin() as pin:
                original=Pinned.check
                def rotate(p):
                    manager.rotate_receipt_key(); return original(p)
                with patch.object(Pinned,'check',rotate),self.assertRaises(contracts.Refusal):
                    evidence.verify_receipt(manager,pin,token)
            original=evidence.seal
            def rotate_after_seal(*args):
                original(*args); manager.rotate_receipt_key()
            with patch.object(evidence,'seal',rotate_after_seal):
                result=ReadCases().get(service,found)
            self.assertEqual(result['state'],'invalid_receipt'); self.assertNotIn('value',result)

    def test_actual_bundle_binding_tampering_expiry_and_discovery_refusal(self):
        import tempfile, copy
        from unittest.mock import patch
        from wiki_access import evidence
        with tempfile.TemporaryDirectory() as tmp:
            root, manager, service, found=ReadCases().fixture(tmp)
            result=ReadCases().get(service,found)
            token=result['value']['read_receipt']
            self.assertIsInstance(token,str)
            with manager.pin() as pin:
                payload=evidence.verify_receipt(manager,pin,token)
                self.assertEqual(payload['response_bytes'],len(contracts.encode(result)))
                self.assertEqual(payload['body_bytes'],result['value']['body_bytes'])
                self.assertEqual(payload['pages'],[evidence.descriptor(p) for p in result['value']['pages']])
                for bad in (token[:-1]+('0' if token[-1]!='0' else '1'), contracts.encode(found).decode(), 'invalid'):
                    with self.subTest(bad=bad[:20]),self.assertRaises(contracts.Refusal) as exc:
                        evidence.verify_receipt(manager,pin,bad)
                    self.assertEqual(exc.exception.code,'invalid_receipt')
                for stamp in (payload['issued']-1,payload['expires'],payload['expires']+1):
                    with patch.object(evidence.time,'time',return_value=stamp),self.assertRaises(contracts.Refusal):
                        evidence.verify_receipt(manager,pin,token)
                modified=copy.deepcopy(result['value']['pages'][0]); modified['body']+='fabricated'
                self.assertNotEqual(evidence.descriptor(modified),payload['pages'][0])

    def test_private_first_write_rotation_and_no_key_disclosure(self):
        import tempfile,os
        from wiki_access import evidence
        with tempfile.TemporaryDirectory() as tmp:
            root,manager,service,found=ReadCases().fixture(tmp)
            key=manager.state/'receipt-key'
            self.assertEqual(key.stat().st_mode & 0o777,0o600)
            self.assertEqual(len(key.read_bytes()),32)
            result=ReadCases().get(service,found); token=result['value']['read_receipt']; old=key.read_bytes()
            manager.rotate_receipt_key()
            self.assertNotEqual(old,key.read_bytes())
            with manager.pin() as pin,self.assertRaises(contracts.Refusal):
                evidence.verify_receipt(manager,pin,token)
            self.assertNotIn(old.hex(),contracts.encode(result).decode())
            os.chmod(key,0o644)
            result=ReadCases().get(service,found)
            self.assertFalse(result['ok']); self.assertNotIn('value',result)
            key.unlink(); key.symlink_to(root/'Runbooks/A.md')
            before=(root/'Runbooks/A.md').read_bytes()
            with self.assertRaises(contracts.Refusal):manager.refresh()
            self.assertEqual((root/'Runbooks/A.md').read_bytes(),before)

    def test_omitted_notes_have_no_receipt_descriptors_and_full_wire_cap(self):
        import tempfile
        from wiki_access import evidence
        with tempfile.TemporaryDirectory() as tmp:
            root,manager,service,found=ReadCases().fixture(tmp,['😀'*7000,'Small complete.'])
            result=ReadCases().get(service,found)
            with manager.pin() as pin:
                payload=evidence.verify_receipt(manager,pin,result['value']['read_receipt'])
                self.assertEqual([p['page_id'] for p in payload['pages']],
                                 [p['page_id'] for p in result['value']['pages']])
                self.assertEqual(payload['response_bytes'],len(contracts.encode(result)))
            omitted=result['value']['omitted'][0]['page_id']
            alone=ReadCases().get(service,found,ids=[omitted])
            self.assertIsNone(alone['value']['read_receipt'])
            exact=ReadCases().get(service,found,budget=len(contracts.encode(result)))
            self.assertEqual(len(exact['value']['pages']),1)
            self.assertLessEqual(len(contracts.encode(exact)),len(contracts.encode(result)))

    def test_revoked_and_mixed_generation_receipts_refuse(self):
        import tempfile
        from wiki_access import evidence
        with tempfile.TemporaryDirectory() as tmp:
            root,manager,service,found=ReadCases().fixture(tmp)
            token=ReadCases().get(service,found)['value']['read_receipt']
            (root/'Runbooks/A.md').write_text((root/'Runbooks/A.md').read_text()+'Changed.')
            manager.refresh()
            with manager.pin() as pin,self.assertRaises(contracts.Refusal):
                evidence.verify_receipt(manager,pin,token)


class CitationCases(unittest.TestCase):
    def test_anchor_contexts_never_certify_another_item_code_or_comment(self):
        import tempfile
        bodies=[('- First evidence. ^first\n- Second evidence. ^second\n','First evidence.','#^second',False),
                ('- First evidence. ^first\n- Second evidence. ^second\n','Second evidence.','#^second',True),
                ('    Code evidence. ^fake\n','Code evidence.','#^fake',False),
                ('> ```\n> Code evidence. ^fake\n> ```\n','Code evidence.','#^fake',False),
                ('<!--\n## Fake\nSecret evidence. ^secret\n-->\n','Secret evidence.','#Fake',False),
                ('<!--\n## Fake\nSecret evidence. ^secret\n-->\n','Secret evidence.','#^secret',False),
                ('<!-- first --> <!-- second\n## Fake\nHidden evidence. ^fake\n-->\n','Hidden evidence.','#Fake',False),
                ('<!-- first --> <!-- second\n## Fake\nHidden evidence. ^fake\n-->\n','Hidden evidence.','#^fake',False),
                ('<pre></pre><pre>\n## Fake\nHidden evidence. ^fake\n</pre>\n','Hidden evidence.','#Fake',False),
                ('<pre></pre><pre>\n## Fake\nHidden evidence. ^fake\n</pre>\n','Hidden evidence.','#^fake',False),
                ('<!-- first --> <!-- second -->\n## Visible\nVisible evidence. ^visible\n','Visible evidence.','#Visible',True),
                ('<!-- closed --> <pre>\n## Fake\nHidden evidence. ^fake\n</pre>\n','Hidden evidence.','#Fake',False),
                ('<!-- closed --> <pre>\n## Fake\nHidden evidence. ^fake\n</pre>\n','Hidden evidence.','#^fake',False),
                ('<pre></pre>\n## Later\nLater evidence. ^later\n','Later evidence.','#Later',False),
                ('> <!--\n## Fake\nHidden evidence. ^fake\n-->\n','Hidden evidence.','#Fake',False),
                ('<!-- first <!-- ignored opener -->\n## Visible\nVisible evidence. ^visible\n','Visible evidence.','#^visible',True),
                ('%%\n## Fake\nSecret evidence. ^secret\n%%\n','Secret evidence.','#Fake',False),
                ('%%\n## Fake\nSecret evidence. ^secret\n%%\n','Secret evidence.','#^secret',False),
                ('<pre>\n## Fake\nCode evidence. ^fake\n</pre>\n','Code evidence.','#Fake',False),
                ('$$\nMath evidence. ^fake\n$$\n','Math evidence.','#^fake',False),
                ('> Quote evidence.\n\n^quote\n\n','Quote evidence.','#^quote',False)]
        for body,quote,suffix,valid in bodies:
            with self.subTest(suffix=suffix,body=body),tempfile.TemporaryDirectory() as tmp:
                root,manager,service,found=ReadCases().fixture(tmp,[body]);bundle=ReadCases().get(service,found);page=bundle['value']['pages'][0]
                check=self.verify(service,bundle,[self.citation(page,quote,page['locator']+suffix)])['value']['citations'][0]
                self.assertEqual(check['valid'],valid)
                if not valid and quote not in ('First evidence.',):
                    self.assertNotIn(page['locator']+suffix,page['citation_targets'])

    def citation(self,page,quote,target=None):
        raw=page['body'].encode(); start=raw.index(quote.encode())
        return {'target':target or page['locator'], 'page_id':page['page_id'],
                'start':start, 'end':start+len(quote.encode()), 'quote':quote}

    def verify(self,service,bundle,citations):
        return service.handle({'schema':contracts.SCHEMA,'operation':'verify_citations',
            'read_receipt':bundle['value']['read_receipt'],'citations':citations})

    def test_every_occurrence_is_mapped_utf8_and_structural_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root,manager,service,found=ReadCases().fixture(tmp,['## Steps\nРусский 😀 observed on 2026-01-01.\n## Later\nUnknown interval.\n'])
            bundle=ReadCases().get(service,found); page=bundle['value']['pages'][0]
            good=self.citation(page,'Русский 😀',page['locator']+'#Steps')
            bad=dict(good,end=good['end']-1)
            result=self.verify(service,bundle,[good,good,bad])
            self.assertTrue(result['ok'],result)
            checks=result['value']['citations'];self.assertEqual(len(checks),3)
            self.assertEqual([c['valid'] for c in checks],[True,True,False])
            self.assertEqual(result['value']['verification'],'structural_only')
            self.assertIsInstance(result['value']['verified_at'],int)
            self.assertTrue(checks[0]['target_verified']);self.assertTrue(checks[0]['read_verified'])
            self.assertNotIn('fact_verified',contracts.encode(result).decode())
            shifted=dict(good,start=good['start']+1)
            self.assertFalse(self.verify(service,bundle,[shifted])['value']['citations'][0]['valid'])
            multiline=self.citation(page,page['body'])
            self.assertTrue(self.verify(service,bundle,[multiline])['value']['citations'][0]['valid'])
            for control in ('\x00','\x01'):
                self.assertEqual(self.verify(service,bundle,[dict(good,quote=good['quote']+control)])['state'],'invalid_request')

    def test_real_headings_fences_duplicate_headings_and_safe_blocks(self):
        import tempfile
        body=('## Same\nFirst.\n## Same\nSecond.\n## Unique\nSupported claim. ^ev-a123\n\n'
              '```md\n## Fake\nHidden. ^fake-block\n```\n')
        with tempfile.TemporaryDirectory() as tmp:
            root,manager,service,found=ReadCases().fixture(tmp,[body]);bundle=ReadCases().get(service,found);page=bundle['value']['pages'][0]
            targets=page['citation_targets']
            self.assertIn(page['locator']+'#Unique',targets)
            self.assertIn(page['locator']+'#^ev-a123',targets)
            self.assertNotIn(page['locator']+'#Fake',targets)
            citations=[self.citation(page,'First.',page['locator']+'#Same'),
                       self.citation(page,'Supported claim.',page['locator']+'#^ev-a123'),
                       self.citation(page,'Hidden.',page['locator']+'#Fake'),
                       self.citation(page,'Hidden.',page['locator']+'#^fake-block'),
                       self.citation(page,'First.',page['locator']+'#Unique'),
                       self.citation(page,'First.',page['locator']+'#^ev-a123')]
            checks=self.verify(service,bundle,citations)['value']['citations']
            self.assertEqual([c['valid'] for c in checks],[True,True,False,False,False,False])
            self.assertEqual(checks[0]['target'],page['locator'])
            self.assertEqual(checks[0]['anchor_state'],'downgraded_to_page')

    def test_unread_invented_escaped_raw_targets_and_source_drift_refuse(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root,manager,service,found=ReadCases().fixture(tmp,['Read evidence.','Unread evidence.'])
            bundle=ReadCases().get(service,found,ids=[found['value']['pages'][0]['page_id']]);page=bundle['value']['pages'][0]
            quote=page['body'];good=self.citation(page,quote)
            bads=[dict(good,target=t) for t in ('A.md','../Runbooks/A.md','/Runbooks/A.md','raw/PRIVATE_CANARY.md',
                'Runbooks/Unknown.md',page['locator']+'#Invented',page['locator']+'#^unknown',page['locator']+'|Alias')]
            bads.append(dict(good,page_id=found['value']['pages'][1]['page_id']))
            result=self.verify(service,bundle,bads)
            self.assertTrue(result['ok']);self.assertTrue(all(not c['valid'] for c in result['value']['citations']))
            self.assertNotIn('PRIVATE_CANARY',contracts.encode(result).decode())
            (root/page['locator']).write_text((root/page['locator']).read_text()+'Changed.')
            result=self.verify(service,bundle,[good]);self.assertFalse(result['ok']);self.assertNotIn('value',result)

    def test_duplicate_basename_and_hidden_source_heading_cannot_misbind(self):
        import tempfile
        from wiki_access.generation import Manager
        from wiki_access.policy import Policy
        from wiki_access.service import Service
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)/'vault';(root/'Runbooks').mkdir(parents=True);(root/'Patterns').mkdir()
            raw='---\ntitle: Amber\ncreated: 2026-01-01\n---\n## Steps\nVisible.\n## Source provenance\n### Steps\nraw/CANARY\n'
            for category in ('Runbooks','Patterns'):(root/category/'A.md').write_text(raw)
            manager=Manager(root,pathlib.Path(tmp)/'state',Policy(['Runbooks','Patterns']));manager.refresh();service=Service(manager)
            found=service.handle({'schema':contracts.SCHEMA,'operation':'resolve','selector':{'kind':'path','value':'Runbooks/A.md'}})
            bundle=ReadCases().get(service,found);page=bundle['value']['pages'][0]
            checks=self.verify(service,bundle,[self.citation(page,'Visible.',page['locator']+'#Steps'),
                self.citation(page,'Visible.','Patterns/A.md'),self.citation(page,'Visible.','A.md')])['value']['citations']
            self.assertEqual([c['valid'] for c in checks],[True,False,False]);self.assertEqual(checks[0]['target'],page['locator'])


class CliCases(unittest.TestCase):
    def test_configuration_change_after_buffering_discards_response(self):
        import tempfile,io,json
        from unittest.mock import patch
        from wiki_access import cli
        with tempfile.TemporaryDirectory() as tmp:
            root,env,config=self.fixture(tmp);self.call(env,{'operation':'refresh'},True)
            original=cli.configured_service
            def changed(*args):
                service=original(*args);handle=service.handle
                def mutate(request):
                    result=handle(request)
                    value=json.loads(config.read_text());value['enabled']=False;config.write_text(json.dumps(value))
                    return result
                service.handle=mutate
                return service
            class Stream:
                def __init__(self,raw=b''):self.buffer=io.BytesIO(raw)
            output=Stream()
            with patch.dict(__import__('os').environ,env,clear=True),patch.object(cli.sys,'argv',['wiki-access.py']),\
                 patch.object(cli.sys,'stdin',Stream(contracts.encode({'schema':contracts.SCHEMA,'operation':'status'}))),\
                 patch.object(cli.sys,'stdout',output),patch.object(cli,'configured_service',changed):
                status=cli.main()
            result=contracts.decode(output.buffer.getvalue())
            self.assertEqual(status,4);self.assertFalse(result['ok']);self.assertNotIn('value',result)

    def fixture(self,tmp):
        import os,json
        root,state,policy=GenerationCases().fixture(tmp)
        config=pathlib.Path(tmp)/'config';(config/'obsidian-wiki').mkdir(parents=True)
        path=config/'obsidian-wiki/wiki-access.json'
        path.write_text(json.dumps({'schema':'wiki-access-config.v1','enabled':True,'categories':['Runbooks'],'portfolio':[]}));path.chmod(0o600)
        env=os.environ.copy();env.update(OBSIDIAN_VAULT_PATH=str(root),XDG_CONFIG_HOME=str(config),XDG_STATE_HOME=str(pathlib.Path(tmp)/'local-state'))
        return root,env,path

    def call(self,env,request,admin=False,args=(),raw=None,script=None):
        import subprocess
        entry=script or ROOT/'plugins/obsidian-wiki/scripts'/('wiki-access-admin.py' if admin else 'wiki-access.py')
        p=subprocess.run([str(entry),*args],input=raw if raw is not None else contracts.encode(dict(schema=contracts.SCHEMA,**request)),
                         env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
        self.assertEqual(p.stderr,b'')
        value=contracts.decode(p.stdout);self.assertEqual(value['schema'],contracts.SCHEMA)
        self.assertEqual(p.returncode,0 if value['ok'] else __import__('wiki_access.cli',fromlist=['exit_code']).exit_code(value))
        return p,value

    def test_subprocess_json_refresh_resolve_get_and_separation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root,env,config=self.fixture(tmp)
            p,result=self.call(env,{'operation':'refresh'},admin=True);self.assertTrue(result['ok'],result)
            p,found=self.call(env,{'operation':'resolve','selector':{'kind':'title','value':'Amber'}})
            self.assertEqual(found['state'],'ok')
            p,bundle=self.call(env,{'operation':'get','page_ids':[found['value']['pages'][0]['page_id']], 'generation':found['generation']})
            self.assertTrue(bundle['ok']);self.assertEqual(len(p.stdout),len(contracts.encode(bundle)))
            self.assertLessEqual(len(p.stdout),24000)
            for request,admin in (({'operation':'refresh'},False),({'operation':'check'},False),({'operation':'search','query':'Amber'},True),
                                  ({'operation':'status','config':'/PRIVATE_CANARY'},False),({'operation':'get','path':'/PRIVATE_CANARY'},False)):
                p,result=self.call(env,request,admin)
                self.assertFalse(result['ok']);self.assertNotIn('PRIVATE_CANARY',p.stdout.decode())
            p,check=self.call(env,{'operation':'check'},admin=True);self.assertTrue(check['ok']);self.assertIn('pages',check['value'])
            self.call(env,{'operation':'refresh'},admin=True,args=['--rotate-receipt-key'])

    def test_malformed_size_bounds_shell_payload_and_sanitized_errors(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root,env,config=self.fixture(tmp);self.call(env,{'operation':'refresh'},True)
            canary=pathlib.Path(tmp)/'PRIVATE_CANARY'
            query='$(touch '+str(canary)+') `touch '+str(canary)+'`'
            p,result=self.call(env,{'operation':'search','query':query})
            self.assertFalse(canary.exists());self.assertNotIn(str(root),p.stdout.decode())
            for raw in (b'{broken',b'[]',b'{"schema":"wiki-access.v1","schema":"bad"}',b'\xff',b'x'*65537,
                        b'{"schema":"wiki-access.v1","operation":'+b'['*2000+b'0'+b']'*2000+b'}'):
                p,result=self.call(env,{},raw=raw)
                self.assertFalse(result['ok']);self.assertLess(len(p.stdout),256)
            p,result=self.call(env,{'operation':'status'},args=['--source','/PRIVATE_CANARY'])
            self.assertEqual(result['state'],'invalid_request');self.assertNotIn('PRIVATE_CANARY',p.stdout.decode())

    def test_disabled_unavailable_corrupt_and_revoked_storage(self):
        import tempfile,json
        with tempfile.TemporaryDirectory() as tmp:
            root,env,config=self.fixture(tmp)
            p,result=self.call(env,{'operation':'status'});self.assertFalse(result['ok'])
            self.call(env,{'operation':'refresh'},True)
            db=next(pathlib.Path(env['XDG_STATE_HOME']).rglob('index.sqlite'));db.write_bytes(b'CORRUPT_PRIVATE_CANARY')
            p,result=self.call(env,{'operation':'status'});self.assertFalse(result['ok']);self.assertNotIn('PRIVATE_CANARY',p.stdout.decode())
            value=json.loads(config.read_text());value['enabled']=False;config.write_text(json.dumps(value))
            p,result=self.call(env,{'operation':'status'});self.assertEqual(result['state'],'disabled')
            config.unlink()
            p,result=self.call(env,{'operation':'status'});self.assertEqual(result['state'],'disabled')

    def test_config_paths_never_enter_requests_and_unsafe_config_refuses(self):
        import tempfile,os
        with tempfile.TemporaryDirectory() as tmp:
            root,env,config=self.fixture(tmp)
            before={p:p.read_bytes() for p in root.rglob('*.md')}
            env['XDG_STATE_HOME']=str(root)
            p,result=self.call(env,{'operation':'refresh'},True);self.assertEqual(result['state'],'permission_refused')
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*.md')})
            config.chmod(0o644)
            p,result=self.call(env,{'operation':'status'});self.assertEqual(result['state'],'permission_refused')


class Stage3IntegrationCases(unittest.TestCase):
    def test_actual_subprocess_full_development_corpus_read_cite_and_lifecycle(self):
        import tempfile
        import wiki_access_acceptance as a
        with tempfile.TemporaryDirectory() as tmp:
            cli=CliCases();root,env,config=cli.fixture(tmp)
            (root/'Runbooks/A.md').unlink()
            manifest=a.fake_manifest('development')
            for note in manifest['notes']:(root/note['locator']).write_text(note['raw'])
            self.assertTrue(cli.call(env,{'operation':'refresh'},True)[1]['ok'])
            ranked=cli.call(env,{'operation':'search','query':manifest['notes'][0]['raw'].split('title: ',1)[1].split('\n',1)[0]})[1]
            self.assertEqual(ranked['state'],'ok',ranked)
            chosen=ranked['value']['pages'][0]
            ranked_bundle=cli.call(env,{'operation':'get','generation':ranked['generation'],'page_ids':[chosen['page_id']]})[1]
            ranked_page=ranked_bundle['value']['pages'][0]
            ranked_verified=cli.call(env,{'operation':'verify_citations','read_receipt':ranked_bundle['value']['read_receipt'],
                'citations':[CitationCases().citation(ranked_page,ranked_page['body'])]})[1]
            self.assertTrue(ranked_verified['value']['citations'][0]['valid'])
            for note in manifest['notes']:
                found=cli.call(env,{'operation':'resolve','selector':{'kind':'path','value':note['locator']}})[1]
                page_id=found['value']['pages'][0]['page_id']
                bundle=cli.call(env,{'operation':'get','generation':found['generation'],'page_ids':[page_id]})[1]
                self.assertTrue(bundle['ok']);page=bundle['value']['pages'][0]
                citation=CitationCases().citation(page,page['body'])
                checked=cli.call(env,{'operation':'verify_citations','read_receipt':bundle['value']['read_receipt'],'citations':[citation,citation]})[1]
                self.assertTrue(checked['ok'],checked)
                self.assertTrue(all(c['valid'] for c in checked['value']['citations']))
                self.assertEqual(len(checked['value']['citations']),2)
                self.assertEqual(checked['value']['verification'],'structural_only')
            old_request={'operation':'verify_citations','read_receipt':bundle['value']['read_receipt'],'citations':[citation]}
            for mutation in ('edit','rename','delete','reclassify','add'):
                source=root/note['locator'];original=source.read_bytes()
                if mutation=='edit':source.write_bytes(original+b'Changed.')
                elif mutation=='rename':source.rename(root/'Runbooks/Renamed.md')
                elif mutation=='delete':source.unlink()
                elif mutation=='reclassify':source.write_bytes(original.replace(b'created:',b'sensitivity: private\ncreated:'))
                else:(root/'Runbooks/Added.md').write_bytes(original)
                result=cli.call(env,old_request)[1];self.assertFalse(result['ok']);self.assertNotIn('value',result)
                if mutation=='rename':(root/'Runbooks/Renamed.md').rename(source)
                elif mutation=='add':(root/'Runbooks/Added.md').unlink()
                else:source.write_bytes(original)


class AdapterCases(unittest.TestCase):
    def test_inline_read_contract_examples_execute_the_complete_installed_flow(self):
        import json,re,tempfile,subprocess
        command=(ROOT/'plugins/obsidian-wiki/commands/ask.md').read_text()
        examples=[contracts.decode(s.encode()) for s in re.findall(r'```json\n(.*?)\n```',command,re.S)]
        self.assertEqual({r['operation'] for r in examples},
                         set(contracts.FIELDS)-{'refresh','check'})
        self.assertEqual({r['selector']['kind'] for r in examples if r['operation']=='resolve'},
                         {'path','title','alias'})
        for request in examples:contracts.validate_request(request)
        with tempfile.TemporaryDirectory() as tmp:
            cli=CliCases();root,env,config=cli.fixture(tmp)
            installed=PackagingCases().installed(tmp)
            (root/'Runbooks/Example.md').write_text('---\ntitle: Example\ncreated: 2026-01-01\naliases: ["example alias"]\n---\nExample.')
            self.assertTrue(cli.call(env,{'operation':'refresh'},True,script=installed/'scripts/wiki-access-admin.py')[1]['ok'])
            generation=None;page_id=None;receipt=None
            for template in examples:
                request=json.loads(json.dumps(template).replace('GENERATION_FROM_RESPONSE',generation or 'unavailable')
                                   .replace('PAGE_ID_FROM_RESPONSE',page_id or 'unavailable')
                                   .replace('READ_RECEIPT_FROM_GET',receipt or 'unavailable'))
                payload=contracts.encode(request).decode().replace("'",r'\u0027')
                entry=str(installed/'scripts/wiki-access.py')
                shell='"'+entry+'" <<<\''+payload+"'"
                p=subprocess.run(['bash','--noprofile','--norc','-c',shell],env=env,capture_output=True,timeout=10)
                self.assertEqual(p.returncode,0,p.stderr)
                response=contracts.decode(p.stdout);self.assertTrue(response['ok'],response)
                generation=response.get('generation',generation)
                if request['operation'] in ('resolve','search'):
                    self.assertEqual(response['state'],'ok');self.assertEqual(len(response['value']['pages']),1)
                    page_id=response['value']['pages'][0]['page_id']
                elif request['operation']=='get':
                    self.assertEqual(response['value']['pages'][0]['body'],'Example.')
                    receipt=response['value']['read_receipt']
                elif request['operation']=='verify_citations':
                    self.assertTrue(all(c['valid'] and c['target_verified'] and c['read_verified']
                                        for c in response['value']['citations']))

    def test_command_is_only_scoped_entry_and_no_natural_language_shell(self):
        import subprocess
        command=(ROOT/'plugins/obsidian-wiki/commands/ask.md').read_text()
        skill=(ROOT/'plugins/obsidian-wiki/skills/legacy-ask/SKILL.md').read_text()
        grant=next(x for x in command.splitlines() if x.startswith('allowed-tools:'))
        self.assertEqual(grant,'allowed-tools: Read, Glob, Grep, Write, Bash(${CLAUDE_PLUGIN_ROOT}/scripts/wiki-access.py *)')
        self.assertNotIn('Bash',next(x for x in skill.splitlines() if x.startswith('allowed-tools:')))
        self.assertIn('once per',command);self.assertIn('every citation occurrence',command)
        self.assertIn('ordinary route remains the default',command)
        self.assertIn('oversized index is unsupported',skill)
        self.assertIn('File-back stays optional and separately confirmed',command)
        self.assertIn('ask remains read-only even after draft confirmation',skill)
        self.assertIn('immediately before **every mutation**',skill)
        self.assertIn('changed base hash blocks the write',skill)
        self.assertIn('disable-model-invocation: true',command)
        self.assertIn('name: legacy-ask',skill)
        self.assertFalse((ROOT/'plugins/obsidian-wiki/skills/ask').exists())
        subprocess.run(['bash','tests/test_bash_grants_scoped.sh'],cwd=ROOT,check=True,capture_output=True)

    def test_single_bundle_budget_refuses_admin_and_has_no_source_fallback(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cli=CliCases();root,env,config=cli.fixture(tmp)
            (root/'Runbooks/Large.md').write_text('---\ntitle: Large\ncreated: 2026-01-01\n---\n'+'x'*25000)
            self.assertTrue(cli.call(env,{'operation':'refresh'},True)[1]['ok'])
            ids=[];generation=None
            for locator in ('Runbooks/A.md','Runbooks/Large.md'):
                found=cli.call(env,{'operation':'resolve','selector':{'kind':'path','value':locator}})[1]
                ids.append(found['value']['pages'][0]['page_id']);generation=found['generation']
            process,bundle=cli.call(env,{'operation':'get','page_ids':ids,'generation':generation,'byte_budget':24000})
            self.assertTrue(bundle['ok'],bundle);self.assertLessEqual(len(process.stdout),24000)
            self.assertEqual(len(bundle['value']['pages']),1);self.assertEqual(bundle['value']['omitted'][0]['reason'],'over_budget')
            self.assertFalse(cli.call(env,{'operation':'refresh'})[1]['ok'])
            (root/'Runbooks/A.md').write_text('---\ntitle: A\ncreated: 2026-01-01\nsensitivity: private\n---\nPRIVATE_CANARY')
            process,refused=cli.call(env,{'operation':'get','page_ids':ids,'generation':generation})
            self.assertFalse(refused['ok']);self.assertNotIn('value',refused);self.assertNotIn(b'PRIVATE_CANARY',process.stdout)


class PackagingCases(unittest.TestCase):
    def installed(self,tmp):
        import shutil
        dest=pathlib.Path(tmp)/'installed-plugin'
        shutil.copytree(ROOT/'plugins/obsidian-wiki',dest,ignore=shutil.ignore_patterns('__pycache__'))
        return dest

    def test_installed_layout_stdlib_executables_and_all_modules(self):
        import os,tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dest=self.installed(tmp);cli=CliCases();root,env,config=cli.fixture(tmp)
            env={k:env[k] for k in ('PATH','OBSIDIAN_VAULT_PATH','XDG_CONFIG_HOME','XDG_STATE_HOME')}
            env['HOME']=tmp
            for name in ('wiki-access.py','wiki-access-admin.py'):
                self.assertTrue(os.access(dest/'scripts'/name,os.X_OK))
            modules=list((dest/'scripts/wiki_access').glob('*.py'));self.assertGreaterEqual(len(modules),8)
            for path in modules:compile(path.read_bytes(),str(path),'exec')
            self.assertTrue(cli.call(env,{'operation':'refresh'},True,script=dest/'scripts/wiki-access-admin.py')[1]['ok'])
            self.assertTrue(cli.call(env,{'operation':'check'},True,script=dest/'scripts/wiki-access-admin.py')[1]['ok'])
            found=cli.call(env,{'operation':'resolve','selector':{'kind':'title','value':'Amber'}},script=dest/'scripts/wiki-access.py')[1]
            self.assertEqual(found['state'],'ok',found)

    def test_recursive_python_coverage_without_package_writes(self):
        import subprocess
        paths=sorted((ROOT/'plugins').rglob('*.py'))
        self.assertTrue(any(p.parent.name=='wiki_access' for p in paths))
        before={p:p.stat().st_mtime_ns for p in paths}
        subprocess.run(['bash','tests/test_python_syntax.sh'],cwd=ROOT,check=True,capture_output=True)
        self.assertEqual(before,{p:p.stat().st_mtime_ns for p in paths})
        self.assertIn('bash tests/test_python_syntax.sh',(ROOT/'.github/workflows/tests.yml').read_text())

    def test_documents_operator_and_distinct_cursor_boundary(self):
        docs=(ROOT/'plugins/obsidian-wiki/scripts/README.md').read_text()
        self.assertIn('Refresh explicitly',docs);self.assertIn('128 MiB',docs)
        self.assertIn('Exit 0',docs);self.assertIn('5 invalid receipt',docs)
        cursor=(ROOT/'ports/cursor/README.md').read_text()
        self.assertIn('Neither that adapter nor its',cursor)
        self.assertIn('no pilot permission, model, recall or lifecycle claim',cursor)


class Stage4IntegrationCases(unittest.TestCase):
    def test_installed_operator_adapter_read_verify_rotation_and_revocation(self):
        import tempfile,json
        with tempfile.TemporaryDirectory() as tmp:
            dest=PackagingCases().installed(tmp);cli=CliCases();root,env,config=cli.fixture(tmp)
            read=dest/'scripts/wiki-access.py';admin=dest/'scripts/wiki-access-admin.py'
            def call(req,administrative=False):return cli.call(env,req,administrative,script=admin if administrative else read)
            before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.md')}
            self.assertIn(call({'operation':'status'})[1]['state'],('index_unavailable','source_unavailable'))
            self.assertTrue(call({'operation':'refresh'},True)[1]['ok'])
            found=call({'operation':'search','query':'Amber'})[1]
            page_id=found['value']['pages'][0]['page_id']
            process,bundle=call({'operation':'get','page_ids':[page_id],'generation':found['generation'],'byte_budget':24000})
            self.assertLessEqual(len(process.stdout),24000);page=bundle['value']['pages'][0]
            citation=CitationCases().citation(page,page['body'])
            request={'operation':'verify_citations','read_receipt':bundle['value']['read_receipt'],'citations':[citation,citation]}
            self.assertTrue(all(c['valid'] for c in call(request)[1]['value']['citations']))
            self.assertFalse(call({'operation':'refresh'})[1]['ok'])
            cli.call(env,{'operation':'refresh'},True,args=['--rotate-receipt-key'],script=admin)
            self.assertEqual(call(request)[1]['state'],'invalid_receipt')
            self.assertEqual(before,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*.md')})
            (root/'Runbooks/A.md').write_text('---\ntitle: Amber\ncreated: 2026-01-01\nsensitivity: private\n---\nPRIVATE_CANARY')
            process,refused=call({'operation':'get','page_ids':[page_id],'generation':found['generation']})
            self.assertFalse(refused['ok']);self.assertNotIn('value',refused);self.assertNotIn(b'PRIVATE_CANARY',process.stdout)
            value=json.loads(config.read_text());value['enabled']=False;config.write_text(json.dumps(value))
            self.assertEqual(call({'operation':'status'})[1]['state'],'disabled')


class AcceptanceRunnerCases(unittest.TestCase):
    def test_client_support_labels_allow_separately_verified_sentences_without_missing_content(self):
        import tempfile,json,re,copy
        import wiki_access_acceptance as a
        import wiki_client_acceptance as c
        with tempfile.TemporaryDirectory() as tmp:
            manifest=c.fake_client_manifest();probe=a.Probe(tmp,manifest['fixture'])
            probe.call({'operation':'refresh'},True);probe.events=[]
            probe.call({'operation':'status'})
            case=next(x for x in manifest['cases'] if x['id']=='date')
            _,bundle,_=probe.evidence(case['support'])
            probe.events=[e for e in probe.events if e['request']['operation']!='verify_citations']
            pages={p['locator']:p for p in bundle['value']['pages']};citations=[]
            for label in case['support']:
                page=pages[label['note']];cursor=label['start']
                for quote in re.split(r'(?<=\.) ',label['quote']):
                    start=page['body'].encode().index(quote.encode(),cursor);end=start+len(quote.encode())
                    citations.append({'target':label['note'],'page_id':page['page_id'],'start':start,'end':end,'quote':quote})
                    cursor=end
            self.assertEqual(len(citations),3)
            before_verify=copy.deepcopy(probe.events)
            entry=str(probe.package/'scripts/wiki-access.py')
            def trace(records):
                probe.events=copy.deepcopy(before_verify)
                verified=probe.call({'operation':'verify_citations','read_receipt':bundle['value']['read_receipt'],'citations':records})
                self.assertTrue(all(x['valid'] for x in verified['value']['citations']))
                events=[{'type':'system','subtype':'init','model':'mock-parser-only'}]
                for i,event in enumerate(probe.events):
                    command='"'+entry+'" <<<\''+contracts.encode(event['request']).decode().replace("'",r'\u0027')+"'"
                    events.append({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Bash','id':str(i),'input':{'command':command}}]}})
                    raw=contracts.encode(event['response']).decode()
                    events.append({'type':'user','tool_use_result':{'stdout':raw,'stderr':'','interrupted':False},'message':{'content':[{'type':'tool_result','tool_use_id':str(i),'content':raw}]}})
                events.append({'type':'result','subtype':'success','is_error':False,'result':' '.join('[['+r['target']+']]' for r in records),'total_cost_usd':.1})
                return events
            good=trace(citations)
            self.assertEqual(c.validate_trace(good,entry,case,0,1)['citation_occurrences'],3)
            # Every submitted quote remains authentic in these controls. Missing
            # a sentence/word must still fail required-label coverage.
            with self.assertRaises(contracts.Refusal):c.validate_trace(trace(citations[:-1]),entry,case,0,1)
            missing_word=copy.deepcopy(citations);missing_word[-1]['start']+=3;missing_word[-1]['quote']=missing_word[-1]['quote'][3:]
            with self.assertRaises(contracts.Refusal):c.validate_trace(trace(missing_word),entry,case,0,1)
            wrong_label=copy.deepcopy(case);wrong_label['support'][1]['quote']='Invented interval observation.'
            with self.assertRaises(contracts.Refusal):c.validate_trace(good,entry,wrong_label,0,1)

    def test_client_trace_requires_actual_tools_cost_model_and_single_bundle(self):
        import wiki_client_acceptance as c
        entry='/tmp/installed-plugin/scripts/wiki-access.py'
        command='"'+entry+'" <<<\'{"schema":"wiki-access.v1","operation":"status"}\''
        self.assertEqual(c.parse_command(command,entry)['operation'],'status')
        for bad in (command+'\nwhoami', command+'; whoami', command+' | cat',
                    command+' > /tmp/leak', command.replace(entry,'python3 '+entry),
                    command.replace("<<<'",'<<<"'), command.replace("<<<'",'<<<$\''),
                    '"'+entry+'" <<\'REQUEST\'\n{"schema":"wiki-access.v1","operation":"status"}\nREQUEST',
                    command.replace('"status"','"refresh"'),
                    command.replace('"status"','"status","operation":"status"'),
                    command.replace('"status"','"sta\ntus"')):
            with self.assertRaises(contracts.Refusal):c.parse_command(bad,entry)
        with self.assertRaises(contracts.Refusal):c.validate_trace([],entry,{'id':'exact'},0,1)
        self.assertIsNone(c.recorded_cost([]))
        self.assertIsNone(c.recorded_cost([{'type':'result','total_cost_usd':.8},{'type':'result','total_cost_usd':0}]))
        self.assertIsNone(c.recorded_cost([{'type':'result','total_cost_usd':float('nan')}]))
        self.assertEqual(c.recorded_cost([{'type':'result','total_cost_usd':.8}]),.8)

    def test_literal_here_string_preserves_json_without_shell_expansion(self):
        import tempfile, json, subprocess
        import wiki_access_acceptance as a
        import wiki_client_acceptance as c
        with tempfile.TemporaryDirectory() as tmp:
            probe=a.Probe(tmp,a.fake_manifest('development'))
            probe.call({'operation':'refresh'},True)
            sentinel=pathlib.Path(tmp)/'expanded'
            request={'schema':'wiki-access.v1','operation':'search',
                     'query':"owner's $(touch "+str(sentinel)+") `touch "+str(sentinel)+"` $HOME",'limit':5,'filters':{}}
            payload=json.dumps(request).replace("'",r'\u0027')
            entry=str(probe.package/'scripts/wiki-access.py')
            command='"'+entry+'" <<<\''+payload+"'"
            self.assertEqual(c.parse_command(command,entry),contracts.validate_request(request))
            p=subprocess.run(['bash','--noprofile','--norc','-c',command],env=probe.env,capture_output=True,timeout=10)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertTrue(json.loads(p.stdout)['ok'])
            self.assertFalse(sentinel.exists())
            with self.assertRaises(contracts.Refusal):
                c.parse_command(command.replace(r'\u0027',"'"),entry)

    def test_client_config_cannot_override_fake_source_or_inject_shell_startup(self):
        import tempfile, json, os
        from unittest.mock import patch
        import wiki_client_acceptance as c
        with tempfile.TemporaryDirectory() as tmp:
            source=pathlib.Path(tmp)/'source'; source.mkdir()
            for key in ('OBSIDIAN_VAULT_PATH','XDG_CONFIG_HOME','XDG_STATE_HOME','BASH_ENV','PYTHONPATH','CLAUDE_CONFIG_DIR'):
                (source/'settings.json').write_text(json.dumps({'model':'opus','env':{key:'/PRIVATE_REAL_VAULT'}}))
                dest=pathlib.Path(tmp)/key; dest.mkdir()
                with patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':str(source)}):
                    with self.assertRaises(contracts.Refusal):c.isolated_config(dest,{'OBSIDIAN_VAULT_PATH':'/tmp/fake'})
            (source/'settings.json').write_text(json.dumps({'model':'opus'}))
            dest=pathlib.Path(tmp)/'ambient';dest.mkdir()
            with patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':str(source)}):
                with self.assertRaises(contracts.Refusal):c.isolated_config(dest,{'BASH_ENV':'/PRIVATE_REAL_VAULT'})

    def test_client_guard_denies_raw_reads_and_secrets_without_approving_grant(self):
        import tempfile,os,json,subprocess
        from unittest.mock import patch
        import wiki_client_acceptance as c
        with tempfile.TemporaryDirectory() as tmp:
            source=pathlib.Path(tmp)/'source';source.mkdir();(source/'settings.json').write_text('{"model":"opus"}')
            dest=pathlib.Path(tmp)/'dest';dest.mkdir()
            entry='/tmp/installed-plugin/scripts/wiki-access.py'
            with patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':str(source)}):config=c.isolated_config(dest,{},entry=entry)
            for command in ('cat /PRIVATE_REAL_VAULT/note.md','cat client-config/.credentials.json','echo "$ANTHROPIC_API_KEY"','env',entry+' --unsafe'):
                p=subprocess.run([sys.executable,str(config/'read-command-guard.py')],input=json.dumps({'tool_name':'Bash','tool_input':{'command':command}}).encode(),capture_output=True,timeout=10)
                self.assertEqual(json.loads(p.stdout)['hookSpecificOutput']['permissionDecision'],'deny')
            command='"'+entry+'" <<<\'{"schema":"wiki-access.v1","operation":"status"}\''
            p=subprocess.run([sys.executable,str(config/'read-command-guard.py')],input=json.dumps({'tool_name':'Bash','tool_input':{'command':command}}).encode(),capture_output=True,timeout=10)
            self.assertEqual(json.loads(p.stdout),{'continue':True})
            guard=config/'read-command-guard.py'
            guard.write_text(guard.read_text().replace('from wiki_client_acceptance import','from missing_guard_module import'))
            p=subprocess.run([sys.executable,str(guard)],input=b'{"tool_name":"Bash","tool_input":{"command":"cat private.md"}}',capture_output=True,timeout=10)
            self.assertEqual(json.loads(p.stdout)['hookSpecificOutput']['permissionDecision'],'deny')
            hook=json.loads((config/'settings.json').read_bytes())['hooks']['PreToolUse'][0]['hooks'][0]
            self.assertEqual(hook['onFailure'],'block')
            self.assertTrue(hook['command'].endswith(' || exit 2'))

    def test_client_parser_binds_actual_cli_responses_and_rejects_extra_reads(self):
        import tempfile,copy
        import wiki_access_acceptance as a
        import wiki_client_acceptance as c
        with tempfile.TemporaryDirectory() as tmp:
            manifest=c.fake_client_manifest();probe=a.Probe(tmp,manifest['fixture'])
            probe.call({'operation':'refresh'},True);probe.events=[]
            probe.call({'operation':'status'})
            case=manifest['cases'][0];probe.evidence(case['support'])
            entry=str(probe.package/'scripts/wiki-access.py')
            events=[{'type':'system','subtype':'init','model':'mock-parser-only'},
                    {'type':'system','subtype':'permission_denied','message':'Non-object client stream notice'}]
            for i,event in enumerate(probe.events):
                command='"'+entry+'" <<<\''+contracts.encode(event['request']).decode().replace("'",r"\u0027")+"'"
                events.append({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Bash','id':str(i),'input':{'command':command}}]}})
                raw=contracts.encode(event['response']).decode()
                events.append({'type':'user','tool_use_result':{'stdout':raw,'stderr':'','interrupted':False},'message':{'content':[{'type':'tool_result','tool_use_id':str(i),'content':raw}]}})
            events.append({'type':'result','subtype':'success','is_error':False,'result':'[[Runbooks/Amber Snapshot.md]] [[Runbooks/Amber Snapshot.md]]','total_cost_usd':0.1})
            self.assertEqual(c.validate_trace(events,entry,case,0,1)['citation_occurrences'],2)
            get_index=next(i for i,e in enumerate(events) if e.get('type')=='assistant' and '"get"' in e['message']['content'][0]['input']['command'])
            duplicate=copy.deepcopy(events[get_index:get_index+2]);duplicate[0]['message']['content'][0]['id']='extra';duplicate[1]['message']['content'][0]['tool_use_id']='extra'
            with self.assertRaises(contracts.Refusal):c.validate_trace(events[:-1]+duplicate+events[-1:],entry,case,0,1)
            corrupt=copy.deepcopy(events);corrupt[-1]['result']='[[Runbooks/Amber Snapshot.md]]'
            with self.assertRaises(contracts.Refusal):c.validate_trace(corrupt,entry,case,0,1)

    def test_private_source_runner_never_mutates_source_and_refuses_frozen_hash_drift(self):
        import tempfile,os
        from unittest.mock import patch
        import wiki_access_acceptance as a
        import wiki_private_acceptance as p
        with tempfile.TemporaryDirectory() as tmp:
            source=pathlib.Path(tmp)/'source';source.mkdir()
            fixture=a.fake_manifest('acceptance')
            for note in fixture['notes']:
                dest=source/note['locator'];dest.parent.mkdir(exist_ok=True);dest.write_text(note['raw'])
            # This page is eligible but outside the frozen question set. Its
            # shared title/alias must be included in the exact-match oracle.
            (source/'Runbooks/Additional Match.md').write_text(fixture['notes'][0]['raw'])
            before={str(f.relative_to(source)):f.read_bytes() for f in source.rglob('*.md')}
            manifest=a.seal({'schema':'wiki-private-acceptance.v1','source':str(source),'policy':{'categories':['Runbooks'],'portfolio':[]},'workload':fixture})
            with patch.dict(os.environ,{'OBSIDIAN_VAULT_PATH':str(source)}):
                result=p.private_suite(manifest,a.fake_manifest('development'),trace=pathlib.Path(tmp)/'private-trace.json')
                self.assertEqual(result['state'],'passed');self.assertEqual(sum(v['total'] for v in result['recall_at_5'].values()),20)
                self.assertEqual(before,{str(f.relative_to(source)):f.read_bytes() for f in source.rglob('*.md')})
                original=a.Probe.call
                def corrupt_resolution(probe,request,*args,**kwargs):
                    response=original(probe,request,*args,**kwargs)
                    if request['operation']=='resolve' and request['selector']['kind']!='path':
                        response['value']['pages'].append({'locator':'Runbooks/Unrelated.md'})
                        response['state']='ambiguous'
                    return response
                with patch.object(a.Probe,'call',corrupt_resolution):
                    corrupted=p.private_suite(manifest,a.fake_manifest('development'),trace=pathlib.Path(tmp)/'corrupt-trace.json')
                self.assertEqual(corrupted['state'],'failed')
                self.assertIn('exact_resolution',corrupted['failed_criteria'])
                self.assertEqual(corrupted['exact'],{'passed':20,'total':60})
                (source/fixture['notes'][0]['locator']).write_text('Changed frozen source.')
                with self.assertRaises(contracts.Refusal):p.private_suite(manifest,a.fake_manifest('development'),trace=pathlib.Path(tmp)/'unused.json')

    def test_fixture_runner_has_actual_denominators_and_installed_events(self):
        import tempfile,json
        import wiki_access_acceptance as a
        with tempfile.TemporaryDirectory() as tmp:
            trace=pathlib.Path(tmp)/'trace.json'
            result=a.fixture_suite(a.fake_manifest('development'),trace=trace)
            self.assertEqual(result['total'],4);self.assertEqual(result['hits'],4)
            self.assertEqual(result['exact'],{'passed':12,'total':12})
            self.assertEqual(set(result['controls']),set(a.CONTROL_CLASSES))
            self.assertGreater(result['citation_occurrences'],0);self.assertFalse(result['independent'])
            events=json.loads(trace.read_bytes())['events']
            self.assertTrue(any(e['request']['operation']=='get' for e in events))
            self.assertTrue(all('installed-plugin/scripts/wiki-access' in e['executable'] for e in events))
            self.assertLessEqual(result['max_read_response_bytes'],24000)
            self.assertLessEqual(result['peak_child_rss_kib'],256*1024)

    def test_multiple_same_note_support_spans_and_private_trace_creation(self):
        import tempfile,os,json
        import wiki_access_acceptance as a
        with tempfile.TemporaryDirectory() as tmp:
            manifest=a.fake_manifest('development')
            manifest['questions'][0]['support'].append(manifest['questions'][0]['support'][0].copy())
            manifest=a.seal({k:v for k,v in manifest.items() if k!='fingerprint'})
            trace=pathlib.Path(tmp)/'trace.json'
            old=os.umask(0)
            try:result=a.fixture_suite(manifest,trace=trace)
            finally:os.umask(old)
            self.assertEqual(result['citation_occurrences'],20)
            self.assertEqual(trace.stat().st_mode & 0o777,0o600)
            events=json.loads(trace.read_bytes())['events']
            gets=[e['request'] for e in events if e['request']['operation']=='get']
            self.assertTrue(all(len(r['page_ids'])==len(set(r['page_ids'])) for r in gets))

    def test_optional_aliases_and_multiple_ambiguous_aliases_are_scored(self):
        import wiki_access_acceptance as a
        manifest=a.fake_manifest('development')
        note=manifest['notes'][0]
        note['raw']=note['raw'].replace('aliases: ["amber exact"]\n','')
        note['hash']=__import__('hashlib').sha256(note['raw'].encode()).hexdigest()
        for note in manifest['notes'][1:3]:
            note['raw']=note['raw'].replace('aliases: [','aliases: ["'+('Shared-Alias' if note is manifest['notes'][1] else 'shared-alias')+'", ')
            note['hash']=__import__('hashlib').sha256(note['raw'].encode()).hexdigest()
        manifest=a.seal({k:v for k,v in manifest.items() if k!='fingerprint'})
        result=a.fixture_suite(manifest)
        self.assertEqual(result['exact'],{'passed':13,'total':13})

    def test_independent_run_consumption_and_private_inputs(self):
        import tempfile,os
        import wiki_access_acceptance as a
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'data.json';path.write_bytes(b'{}');path.chmod(0o600)
            self.assertEqual(a.private_bytes(path),b'{}')
            a.claim_independent_run(tmp,b'{}',{'code':'hash'})
            with self.assertRaises(FileExistsError):a.claim_independent_run(tmp,b'{ }',{'new-code':'different-hash'})
            path.chmod(0o644)
            with self.assertRaises(contracts.Refusal):a.private_bytes(path)
            link=pathlib.Path(tmp)/'link';link.symlink_to(path)
            with self.assertRaises(OSError):a.private_bytes(link)
            fifo=pathlib.Path(tmp)/'fifo';os.mkfifo(fifo,0o600)
            with self.assertRaises(contracts.Refusal):a.private_bytes(fifo)

    def test_incomplete_lock_and_scripted_client_claims_cannot_pass(self):
        import tempfile,json,subprocess
        import wiki_access_acceptance as a
        with tempfile.TemporaryDirectory() as tmp:
            manifest=pathlib.Path(tmp)/'fake-client.json';manifest.write_text(json.dumps({'answer':'invented supported answer','passed':True}))
            from unittest.mock import patch
            from types import SimpleNamespace
            # CI never invokes a real client/private suite, even its preflight.
            with patch.object(subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=b'--max-budget-usd')):
                result=a.client_preflight()
            self.assertEqual(result['state'],'BLOCKED')
            self.assertEqual(result['calls'],0);self.assertFalse(result['claim_support_verified'])
            lock=pathlib.Path(tmp)/'lock.json';lock.write_text('{}')
            p=subprocess.run([sys.executable,str(ROOT/'tests/wiki_access_acceptance.py'),'--suite','fixtures','--manifest',str(manifest),'--development',str(manifest),'--implementation-lock',str(lock)],capture_output=True,timeout=20)
            self.assertNotEqual(p.returncode,0);self.assertEqual(json.loads(p.stdout)['state'],'failed')


def main():
    names = sys.argv[1:]
    if not names:
        names = [n for n, value in globals().items() if isinstance(value, type)
                 and issubclass(value, unittest.TestCase)]
    suite = unittest.TestSuite()
    for name in names:
        cls = globals().get(name)
        if not isinstance(cls, type) or not issubclass(cls, unittest.TestCase):
            sys.exit('unknown test family: ' + name)
        group = unittest.defaultTestLoader.loadTestsFromTestCase(cls)
        if not group.countTestCases():
            sys.exit('empty test family: ' + name)
        suite.addTests(group)
    if not suite.countTestCases():
        sys.exit('empty suite')
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())


if __name__ == '__main__':
    main()
