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
