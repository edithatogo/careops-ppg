import json
import unittest
from pathlib import Path
from scripts.ppg_review_criteria import records


class CriteriaSeeds(unittest.TestCase):
    def raw(self):
        return Path('config/review-intelligence/criteria-v1.json').read_bytes()

    def test_versioned_keys_and_separate_options(self):
        rows = records(self.raw())
        self.assertEqual(len(rows), 19)
        self.assertEqual(len({(r['list'], r['record'][r['key']]) for r in rows}), 19)
        self.assertTrue(all(r['record']['DefinitionStatus'] == 'draft-for-pilot' for r in rows))
        self.assertFalse(any('humanDecision' in r['record'] for r in rows))

    def test_changed_definition_changes_fingerprint_but_not_identity(self):
        before = records(self.raw())[0]['record']
        data = json.loads(self.raw());data['criteria'][0]['question'] += ' Clarify scope.'
        after = records(json.dumps(data).encode())[0]['record']
        self.assertEqual(before['CriterionKey'], after['CriterionKey'])
        self.assertNotEqual(before['DefinitionSHA256'], after['DefinitionSHA256'])
        # Native create-only exact readback must refuse this same-key drift.

    def test_ambiguous_or_mandatory_definitions_refused(self):
        for kind in ['duplicate', 'mandatory', 'status']:
            data = json.loads(self.raw())
            if kind == 'duplicate':data['criteria'].append(data['criteria'][0])
            elif kind == 'mandatory':data['criteria'][0]['mandatory'] = True
            else:data['status'] = 'approved'
            with self.assertRaises(ValueError):records(json.dumps(data).encode())
