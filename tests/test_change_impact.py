import copy
import json
import unittest
from pathlib import Path
from scripts.ppg_change_impact import validate, render


class ChangeImpactTest(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(Path('config/change-impact-register.json').read_text())
        self.record = dict(Title='Fictional <draft>', ChangeKey='fictional:1:2', DocumentUID='fictional', FromEdition='1', ProposedEdition='draft2', SourceEvidence='fictional-source', ReviewTriggers={'results':['Scheduled review']}, ChangeMagnitude='No change', Urgency='Routine', RecordState='Draft', Rationale='Reviewed; no changes proposed', UnresolvedQuestions='Authority not verified')

    def test_no_change_and_multiple_triggers_are_independent(self):
        self.record['ReviewTriggers']['results'].append('Feedback')
        self.assertEqual(validate(self.record, self.contract)['ChangeMagnitude'], 'No change')
        self.record['Urgency'] = 'Major'
        with self.assertRaises(ValueError): validate(self.record, self.contract)

    def test_required_identity_and_unknown_choices_refused(self):
        for key in ('ChangeKey', 'FromEdition', 'SourceEvidence'):
            record = copy.deepcopy(self.record); record[key] = ''
            with self.assertRaises(ValueError): validate(record, self.contract)
        self.record['ReviewTriggers'] = {'results': ['Invented']}
        with self.assertRaises(ValueError): validate(self.record, self.contract)

    def test_decision_and_effective_date_not_manufactured(self):
        self.record['RecordState'] = 'Decision recorded'
        with self.assertRaises(ValueError): validate(self.record, self.contract)
        self.record['DecisionEvidence'] = 'fictional-decision'
        self.record['EffectiveDate'] = '2026-10-21T00:00:00Z'
        with self.assertRaises(ValueError): validate(self.record, self.contract)

    def test_snapshot_escapes_and_preserves_input(self):
        original = copy.deepcopy(self.record)
        output = render(self.record, self.contract, '1.0')
        self.assertIn('&lt;draft&gt;', output)
        self.assertIn('does not approve', output)
        self.assertNotIn('<h3>ChangeKey</h3>', output)
        self.record['MajorChanges'] = 'First; Second'
        self.assertIn('<li>First</li><li>Second</li>', render(self.record, self.contract, '1.0'))
        self.record.pop('MajorChanges')
        self.assertEqual(self.record, original)
        with self.assertRaises(ValueError): render(self.record, self.contract, '')


if __name__ == '__main__': unittest.main()
