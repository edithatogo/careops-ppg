import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('edition_receipts', Path(__file__).parents[1] / 'tools/policy-editions/build_edition_receipts.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EditionReceiptTests(unittest.TestCase):
    def fixture(self):
        old = dict(DocumentReference='https://example.invalid/old', ReviewedVersionRef='old-version', DocumentSHA256='a' * 64)
        new = dict(DocumentReference='https://example.invalid/new', ReviewedVersionRef='new-version', DocumentSHA256='b' * 64)
        common = dict(Stage='Decision', RecordState='Recorded', DecisionOutcome='Approved (recorded)', ConditionsState='None recorded', FictionalTest=True)
        replace = dict(common, EventUID='fictional-replace', NextAction=json.dumps(dict(purpose='replace', retainedSubject=old, replacement=new)))
        withdraw = dict(common, EventUID='fictional-withdraw', NextAction=json.dumps(dict(purpose='withdraw', retainedSubject=old, issuedReference='https://example.invalid/issued')))
        publication = dict(new, EventUID='fictional-publication', Stage='Publication', RecordState='Recorded', ParentEventUID=replace['EventUID'], FictionalTest=True)
        request = dict(FictionalTest=True, requestId='fictional-edition-request', site='https://example.invalid/site', qualificationFolder='/qualification', filePins=[dict(uid=str(i), etag='"1"', text='fictional', sha256=hashlib.sha256(b'fictional').hexdigest()) for i in range(4)], events=[replace, withdraw, publication, dict(publication, EventUID='fictional-old-publication')], receipts=[])
        for op in ['replace', 'withdraw']:
            body = dict(FictionalTest=True, operation=op, scope='isolated-fictional-projection-only', historyRetained=True, decisionEventUID='fictional-' + op, subjectScope=old)
            if op == 'replace':
                body.update(replacementScope=new, publicationEventUID=publication['EventUID'])
            else:
                body['issuedReference'] = 'https://example.invalid/issued'
            request['receipts'].append(dict(name='FICTIONAL-LC04-' + op + '.json', request=body))
        reference = {'properties': {'definition': {}, 'connectionReferences': {'shared_sharepointonline': {'source': 'Embedded'}}}}
        return request, reference

    def test_native_profile_preserves_sources_and_creates_absent_only(self):
        result = mod.build(*self.fixture())
        encoded = json.dumps(result)
        self.assertEqual(result['properties']['state'], 'Stopped')
        self.assertIn('overwrite=false', encoded)
        self.assertNotIn('overwrite=true', encoded)
        self.assertNotIn('parameters/method": "DELETE', encoded)
        self.assertNotIn('parameters/method": "PATCH', encoded)
        self.assertIn('EvidenceChanged', encoded)
        self.assertIn('ReceiptConflict', encoded)

    def test_large_frozen_contract_is_split_without_dropping_checks(self):
        r, ref = self.fixture()
        for event in r['events']:
            event['Summary'] = 'Fictional evidence ' * 150
        result = mod.build(r, ref)
        expressions = []
        def walk(value):
            if isinstance(value, dict):
                if value.get('type') == 'If':
                    expressions.append(value['expression'])
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(result)
        self.assertGreater(len(expressions), 6)
        self.assertTrue(all(len(expr) <= 6000 for expr in expressions))
        self.assertEqual(json.dumps(result).count("?['Summary']"), 4)

    def test_wrong_or_absent_decision_refuses(self):
        r, ref = self.fixture()
        r['receipts'][0]['request']['decisionEventUID'] = 'missing'
        with self.assertRaises(ValueError):
            mod.build(r, ref)

    def test_publication_approval_cannot_supply_withdrawal_purpose(self):
        r, ref = self.fixture()
        r['events'][1]['NextAction'] = json.dumps({'purpose': 'publish'})
        with self.assertRaises(ValueError):
            mod.build(r, ref)

    def test_changed_bytes_or_wildcard_token_refuse(self):
        for change in ['text', 'etag']:
            r, ref = self.fixture()
            r['filePins'][0][change] = '*' if change == 'etag' else 'changed'
            with self.assertRaises(ValueError):
                mod.build(r, ref)

    def test_wrong_revision_publication_refuses(self):
        r, ref = self.fixture()
        r['events'][2]['DocumentSHA256'] = 'c' * 64
        with self.assertRaises(ValueError):
            mod.build(r, ref)


if __name__ == '__main__':
    unittest.main()
