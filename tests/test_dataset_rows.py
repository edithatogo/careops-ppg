import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_dataset_rows import reconcile

class ReconciliationTests(unittest.TestCase):
    def run_plan(self, rows, existing=(), total=None):
        return reconcile({'success': True, 'result': {'records': rows, 'total': len(rows) if total is None else total}}, existing, namespace='hospital', key_fields=['FacilityCode'], fields=['FacilityCode', 'Value'])

    def test_replay_changes_and_human_fields(self):
        rows = [{'FacilityCode': '00123', 'Value': None}]
        created = self.run_plan(rows)[0][0]['fields']
        old = dict(created, ID=9, Notes='Human note')
        self.assertEqual(self.run_plan(rows, [old]), [])
        changed = self.run_plan([dict(rows[0], Value='NA')], [old])[0][0]
        self.assertEqual(changed['fields'], {'Value': 'NA'})
        self.assertEqual(old['Notes'], 'Human note')
        self.assertEqual(self.run_plan([], [old])[0][0]['fields'], {'SourcePresent': False})

    def test_invalid_source_never_produces_removals(self):
        for rows, total in [([{'FacilityCode': '', 'Value': 0}], 1), ([{'FacilityCode': '01', 'Value': 0}], 2), ([{'FacilityCode': '01', 'Value': 0}] * 2, 2)]:
            with self.assertRaises(ValueError):
                self.run_plan(rows, total=total)

    def test_bounded_batches(self):
        batches = self.run_plan([{'FacilityCode': str(i), 'Value': i} for i in range(41)])
        self.assertEqual(list(map(len, batches)), [20, 20, 1])
