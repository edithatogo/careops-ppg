import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('binary_publication', Path(__file__).parents[1] / 'tools/policy-editions/binary_publication.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class BinaryPublicationTests(unittest.TestCase):
    def setUp(self):
        # Synthetic local values only; never a created case, authorisation or native fixture.
        self.raw = b'PK\x03\x04\xff\x00\x80 binary package bytes\r\n'
        self.src = dict(UniqueId='11111111-1111-1111-1111-111111111111', ETag='"opaque-source-token"',
                        nativeVersion='2.0', Length=len(self.raw), DocumentReference='https://example.invalid/sites/test/prepared.docx')
        self.dst = dict(UniqueId='22222222-2222-2222-2222-222222222222', ETag='"opaque-issued-token"',
                        nativeVersion='1.0', Length=len(self.raw), DocumentReference='https://example.invalid/sites/test/isolated/FICTIONAL-issued.docx')
        self.scope = dict(CaseUID='LOCAL-UNIT-ONLY', DocumentReference=self.src['DocumentReference'],
                          ReviewedVersionRef='sharepoint:' + self.src['UniqueId'] + ':' + self.src['ETag'],
                          DocumentSHA256=hashlib.sha256(self.raw).hexdigest())
        self.reference = {'properties': {'state': 'Stopped', 'definition': {'actions': {'Historical': {'type': 'Compose', 'inputs': 'preserve'}}},
                            'connectionReferences': {'shared_sharepointonline': {'source': 'Embedded', 'connectionName': 'retained-reference'}}}}

    def proof(self):
        return m.verify_downloads(self.scope, self.src, self.src, self.dst, self.dst, self.raw, self.raw)

    def chain(self):
        ids = ['unit-committee', 'unit-officer', 'unit-coordinator', 'unit-final']
        rows = [dict(self.scope, EventUID=uid, Id=i+1, GUID='unit-row-'+str(i), **{'odata.etag': '"unit-token-'+str(i)+'"'},
                     Stage='Decision', RecordState='Recorded', FictionalTest=True, ConditionsState='None recorded',
                     DecisionOutcome='Approved (recorded)' if i == 3 else 'Endorsed (recorded)',
                     ParentEventUID=ids[i-1] if i else None, SupersedesEventUID=None,
                     DecisionReference='fictional://local-only/'+uid, ReadinessEventUID='unit-ready',
                     EvidenceReference='fictional://local-only/evidence', OccurredOn='retained-unit-occurrence')
                for i, uid in enumerate(ids)]
        return ids, rows

    def plan(self, rows=None, retained=None, publication=None):
        ids, default = self.chain()
        return m.event_plan(self.scope, default[-1], ids, {'value': default if rows is None else rows}, self.proof(),
                            publication or dict(EventUID='LC04-PUBLICATION-UNIT-ONLY', FictionalTest=True, OccurredOn='supplied-unit-occurrence'),
                            {'value': retained or []})

    def test_documented_body_free_copy_is_non_deployable_retry_none_and_preserves_reference(self):
        old = copy.deepcopy(self.reference)
        fragment = m.copy_fragment('https://example.invalid/sites/test', self.src,
                                  self.dst['DocumentReference'].replace('https://example.invalid', ''),
                                  '/sites/test/isolated', self.reference)
        self.assertFalse(fragment['deployable'])
        action = fragment['action']['inputs']
        self.assertEqual(action['retryPolicy'], {'type': 'none'})
        self.assertIn('bOverWrite=false', action['parameters']['parameters/uri'])
        self.assertNotIn('parameters/body', action['parameters'])
        self.assertNotIn('base64ToString', json.dumps(fragment))
        self.assertEqual(old, self.reference)

    def test_source_destination_and_existing_reference_boundaries(self):
        for path in ['/sites/test/isolated/real.docx', '/sites/test/isolated/FICTIONAL-../bad.docx',
                     '/sites/other/isolated/FICTIONAL-issued.docx', '/sites/test/isolated/FICTIONAL-%2e%2e.docx']:
            with self.assertRaises(ValueError):
                m.copy_fragment('https://example.invalid/sites/test', self.src, path, '/sites/test/isolated', self.reference)
        ref = copy.deepcopy(self.reference); ref['properties']['state'] = 'Started'
        with self.assertRaises(ValueError):
            m.copy_fragment('https://example.invalid/sites/test', self.src, '/sites/test/isolated/FICTIONAL-issued.docx', '/sites/test/isolated', ref)

    def test_copy_refuses_noncanonical_source_paths_before_creating_fragment(self):
        for path in ('/sites/test/../other/prepared.docx',
                     '/sites/test/folder\\prepared.docx'):
            source = dict(self.src, DocumentReference='https://example.invalid' + path)
            with self.subTest(path=path), self.assertRaises(ValueError):
                m.copy_fragment('https://example.invalid/sites/test', source,
                    '/sites/test/isolated/FICTIONAL-issued.docx', '/sites/test/isolated', self.reference)

    def test_copy_refuses_site_credentials_even_when_source_matches(self):
        site = 'https://user:password@example.invalid/sites/test'
        source = dict(self.src, DocumentReference=site + '/prepared.docx')
        with self.assertRaises(ValueError):
            m.copy_fragment(site, source, '/sites/test/isolated/FICTIONAL-issued.docx',
                '/sites/test/isolated', self.reference)

    def test_actual_binary_bytes_required_and_opaque_tokens_not_parsed(self):
        proof = self.proof()
        self.assertTrue(proof['independentByteParity'])
        self.assertFalse(proof['nativeBinaryTransportQualified'])
        self.assertEqual(proof['issued']['ETag'], self.dst['ETag'])
        for changed in [self.raw+b'x', self.raw.replace(b'\xff', b'?')]:
            with self.assertRaises(ValueError):
                m.verify_downloads(self.scope, self.src, self.src, self.dst, self.dst, self.raw, changed)
        with self.assertRaises(ValueError):
            m.verify_downloads(self.scope, self.src, self.src, self.dst, self.dst, self.raw.decode('latin1'), self.raw)

    def test_changed_human_edit_metadata_and_overlap_hold(self):
        for field, value in [('ETag', '"edited"'), ('nativeVersion', '2.0'), ('Length', 999)]:
            after = dict(self.dst, **{field: value})
            with self.assertRaises(ValueError):
                m.verify_downloads(self.scope, self.src, self.src, self.dst, after, self.raw, self.raw)
        with self.assertRaises(ValueError):
            m.verify_downloads(self.scope, self.src, self.src, self.src, self.src, self.raw, self.raw)

    def test_missing_deferred_open_ambiguous_and_superseding_authorisation_hold(self):
        _, rows = self.chain()
        for changed in [rows[:-1], rows+rows[-1:], rows+[dict(rows[-1], EventUID='unit-defer', DecisionOutcome='Deferred', ConditionsState='Open')],
                        rows+[dict(rows[-1], EventUID='unit-correct', SupersedesEventUID=rows[-1]['EventUID'])]]:
            with self.assertRaises(ValueError):
                self.plan(changed)
        for marker in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink'):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                m.complete({'value': rows, marker: 'more'})

    def test_publication_intent_requires_proof_and_retained_full_chain_then_exact_retry_zero(self):
        plan = self.plan()
        self.assertFalse(plan['deployable'])
        self.assertEqual(plan['nativeWrites'], 0)
        self.assertEqual(plan['createIntentCount'], 1)
        self.assertEqual(plan['payload']['DocumentReference'], self.scope['DocumentReference'])
        self.assertEqual(plan['payload']['PublicationURL'], self.dst['DocumentReference'])
        self.assertIn(self.dst['UniqueId'], plan['payload']['PublishedVersionRef'])
        prior = dict(plan['payload'], OccurredOn='original-retained-occurrence')
        retry = self.plan(retained=[prior])
        self.assertEqual(retry['createIntentCount'], 0)
        self.assertEqual(retry['payload']['OccurredOn'], 'original-retained-occurrence')
        with self.assertRaises(ValueError):
            self.plan(retained=[dict(prior, PublicationURL='changed')])

    def test_current_adverse_preparation_never_gets_writer(self):
        preparation = {'currentCase': {'currentPreparedScope': self.scope,
                        'retainedAdverseDecision': {'DecisionOutcome': 'Deferred', 'ConditionsState': 'Open'}}}
        result = m.assess_current_case(preparation)
        self.assertEqual(result['phase'], 'held')
        self.assertEqual(result['copyActions'], [])
        self.assertEqual(result['publicationActions'], [])
        self.assertEqual(result['nativeWrites'], 0)
        self.assertIn('adverse', result['reason'])

    def test_corrections_scope_overrides_and_native_record_identities_refused(self):
        for key, value in [('SupersedesEventUID', 'retained-event'), ('SupersedesEventUID', None),
                           ('Id', 12), ('GUID', 'pretend-native'), ('odata.etag', '"pretend"'),
                           ('ParentEventUID', 'override'), ('CaseUID', 'another-case')]:
            publication = dict(EventUID='LC04-PUBLICATION-UNIT-ONLY', FictionalTest=True,
                               OccurredOn='supplied-unit-occurrence', **{key: value})
            with self.assertRaisesRegex(ValueError, 'Only explicit publication inputs'):
                self.plan(publication=publication)

    def test_native_metadata_normalization_is_explicit_and_strict(self):
        raw = {'UniqueId': self.src['UniqueId'], 'ETag': self.src['ETag'], 'UIVersionLabel': '2.0',
               'Length': str(len(self.raw)), 'ServerRelativeUrl': '/sites/test/prepared.docx'}
        self.assertEqual(m.normalize_sharepoint_file(raw, 'https://example.invalid'), self.src)
        for invalid in [True, len(self.raw), ' 29', '2.9', '-1', '0']:
            with self.assertRaises(ValueError):
                m.normalize_sharepoint_file(dict(raw, Length=invalid), 'https://example.invalid')
        with self.assertRaises(ValueError):
            m.normalize_sharepoint_file(dict(raw, ETag='*'), 'https://example.invalid')


if __name__ == '__main__':
    unittest.main()
