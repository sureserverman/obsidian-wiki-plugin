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
