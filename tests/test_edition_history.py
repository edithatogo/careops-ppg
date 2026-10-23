import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('history', Path(__file__).resolve().parents[1] / 'scripts/ppg_edition_history.py')
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)
UID = '00000000-0000-4000-8000-000000000103'


def row(edition, sha):
    return dict(documentUID=UID, identityEvidence='verified exact source-header/catalogue receipt',
                sourceEdition=edition, sha256=sha * 64, sourcePath='/archive/a.pdf', bytes=10)


class HistoryPlanningTests(unittest.TestCase):
    def test_numeric_order_and_duplicate_occurrences(self):
        plan = history.plan_histories([row('10.0', 'b'), row('2.0', 'a'), row('2.0', 'a')])
        editions = plan['ready'][0]['editions']
        self.assertEqual([r['sourceEdition'] for r in editions], ['2.0', '10.0'])
        self.assertEqual(len(editions[0]['occurrences']), 2)

    def test_same_edition_different_bytes_are_held_without_dropping_captures(self):
        plan = history.plan_histories([row('2', 'a'), row('2.0', 'b')])
        self.assertFalse(plan['ready'])
        self.assertEqual(len(plan['unresolved'][0]['records']), 2)

    def test_filename_or_url_cannot_supply_identity(self):
        old, new = row('1', 'a'), row('2', 'b')
        old['documentUID'] = new['documentUID'] = None
        self.assertEqual(len(history.plan_histories([old, new])['unresolved']), 2)

    def test_singleton_is_not_a_history(self):
        plan = history.plan_histories([row('1', 'a')])
        self.assertFalse(plan['ready'])
        self.assertEqual(len(plan['singletons']), 1)

    def test_null_native_edition_or_hash_is_held_instead_of_crashing(self):
        for key in ('sourceEdition', 'sha256'):
            record = row('1', 'a')
            record[key] = None
            plan = history.plan_histories([record])
            self.assertFalse(plan['ready'])
            self.assertEqual(len(plan['unresolved']), 1)
