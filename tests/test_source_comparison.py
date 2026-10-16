import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_source_sync import prepare
from ppg_source_comparison import compare, render

UID = '11111111-1111-4111-8111-111111111111'

class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {'sourceSha256': 'a' * 64, 'records': [
            {'sourceRow': 1, 'fields': {'sourceDocumentId': 'A', 'sourceTitle': 'Old', 'sourceComments': None}}]}
        self.aliases = [{'source': 'register', 'alias': 'A', 'DocumentUID': UID}]
        self.baseline = self.plan(self.snapshot)
        self.cases = [{'CaseUID': 'case-1', 'linkedDocumentUIDs': [UID], 'nextAction': 'Retain human work'}]

    def plan(self, snapshot):
        return prepare(snapshot, 'register', self.aliases, {'sourceDocumentId', 'sourceTitle'})

    def test_change_and_preserve_inputs(self):
        s = copy.deepcopy(self.snapshot)
        s['records'][0]['fields']['sourceTitle'] = '<script>alert(1)</script>'
        inputs = copy.deepcopy((self.baseline, s, self.cases))
        r = compare(self.baseline, self.plan(s), self.cases)
        self.assertEqual(r['affectedCases'][0]['CaseUID'], 'case-1')
        self.assertEqual(r['changes'][0]['fields'][0]['before'], 'Old')
        self.assertNotIn('<script>', render(r))
        self.assertEqual(inputs, (self.baseline, s, self.cases))
        self.assertFalse(r['checkpointAdvanced'])

    def test_row_move_is_not_content_change(self):
        s = copy.deepcopy(self.snapshot)
        s['records'][0]['sourceRow'] = 8
        self.assertEqual(compare(self.baseline, self.plan(s), self.cases)['changes'], [])

    def test_missing_not_retired(self):
        s = copy.deepcopy(self.snapshot)
        s['records'] = []
        r = compare(self.baseline, self.plan(s), self.cases)
        self.assertEqual(r['changes'][0]['kind'], 'missing-source-exception')
        self.assertEqual(r['coverage'], 'partial')
        self.assertIn('held', r['status'])

    def test_unknown_alias_never_inferred(self):
        s = copy.deepcopy(self.snapshot)
        s['records'][0]['fields']['sourceDocumentId'] = 'A-v2'
        r = compare(self.baseline, self.plan(s), self.cases)
        self.assertEqual(r['identityExceptions'][0]['code'], 'unknown_alias')
        self.assertEqual(r['coverage'], 'partial')

    def test_bad_links_are_unknown(self):
        self.cases[0]['linkedDocumentUIDs'] = 'not a UUID list'
        r = compare(self.baseline, self.baseline, self.cases)
        self.assertEqual(len(r['unresolvedCases']), 1)
        self.assertEqual(r['coverage'], 'partial')

    def test_raw_unprojected_field_and_missing_null(self):
        s = copy.deepcopy(self.snapshot)
        del s['records'][0]['fields']['sourceComments']
        r = compare(self.baseline, self.plan(s), self.cases)
        self.assertFalse(r['changes'][0]['fields'][0]['afterPresent'])

    def test_duplicate_or_wrong_source_rejected(self):
        bad = copy.deepcopy(self.baseline)
        bad['operations'] *= 2
        with self.assertRaises(ValueError):
            compare(self.baseline, bad, self.cases)
        bad = copy.deepcopy(self.baseline)
        bad['source'] = 'other'
        with self.assertRaises(ValueError):
            compare(self.baseline, bad, self.cases)

if __name__ == '__main__':
    unittest.main()
