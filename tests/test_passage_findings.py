import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from scripts.ppg_passage_findings import build, save


class PassageFindings(unittest.TestCase):
    def setUp(self):
        self.raw = b'fictional retained source'
        self.sha = hashlib.sha256(self.raw).hexdigest()
        self.prep = dict(subject={'documentVersion': 'requested-current'}, catalogueCount=2,
                         reviewChecklist=[{'criterionId': 'quality'}], decisionOptions=['minor_revision'],
                         comparisonMatrix=[{'comparisonState': 'not_compared'}]*2)
        self.inventory = dict(sourceSha256=self.sha, sourceAuthority='unverified historical draft',
                              elements=[dict(sourceLocator='body#1', text='Monthly reporting and annual review.')])
        self.finding = dict(findingId='f1', criterionId='quality', claimType='inference',
                            suggestedAction='minor_revision', statement='Clarify distinct intervals',
                            benefit='Clearer work allocation', effort='low', dependencies='Current source',
                            uncertainty='Current applicability unknown', citations=[dict(
                                sourceSha256=self.sha, locator='body#1', quote='Monthly reporting')])

    def test_retains_whole_preparation_and_does_not_promote_authority(self):
        before = copy.deepcopy((self.prep, self.inventory, self.finding))
        r = build(self.prep, self.inventory, self.raw, [self.finding])
        self.assertEqual(r['preparation'], self.prep)
        self.assertEqual(r['findings'][0]['scope'], 'historical_inspection_only')
        self.assertFalse(r['policyApproved'])
        self.assertEqual(before, (self.prep, self.inventory, self.finding))

    def test_rejects_changed_bytes_locator_quote_and_decision(self):
        for field, value in [('locator', 'missing'), ('quote', 'fabricated'), ('sourceSha256', '0'*64)]:
            f = copy.deepcopy(self.finding); f['citations'][0][field] = value
            with self.assertRaises(ValueError):
                build(self.prep, self.inventory, self.raw, [f])
        with self.assertRaises(ValueError):
            build(self.prep, self.inventory, b'changed', [self.finding])
        with self.assertRaises(ValueError):
            build(self.prep, self.inventory, self.raw, [dict(self.finding, humanDecision='approved')])

    def test_retry_never_overwrites_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'pack'
            save(self.prep, self.inventory, self.raw, [self.finding], p)
            (p/'README.md').write_text('Human edit')
            with self.assertRaises(FileExistsError):
                save(self.prep, self.inventory, self.raw, [self.finding], p)
            self.assertEqual((p/'README.md').read_text(), 'Human edit')
