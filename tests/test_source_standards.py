from portable_standard_fixtures import frameworks, supplement
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.ppg_source_standards import reconcile


class SourceStandards(unittest.TestCase):
    def setUp(self):
        self.definitions = frameworks()
        self.raw = [{'sourceRow': n + 2, 'fields': {
            'sourceDocumentId': f'FICTIONAL-{n}', 'sourceStandard': v}}
            for n, v in enumerate([1, 6, 9, '2', False, ''])]
        self.candidate = {'sourceSha256': 'a' * 64, 'inputCount': 6,
            'allowed': ['sourceDocumentId'], 'exceptions': [], 'rawRecords': copy.deepcopy(self.raw),
            'operations': [{'sourceRow': r['sourceRow'], 'DocumentUID': f'fictional-{n}',
                'fields': {'sourceDocumentId': r['fields']['sourceDocumentId']}}
                for n, r in enumerate(self.raw)]}
        self.extracted = {'schemaVersion': 1, 'workbookSha256': 'a' * 64,
            'records': copy.deepcopy(self.raw), 'sheets': [
                {'name': 'STANDARDS TRACKING', 'cells': [
                    {'row': 6, 'column': 2, 'value': 1}, {'row': 6, 'column': 3, 'value': 2},
                    {'row': 20, 'column': 2, 'value': 'Grand Total'},
                    {'row': 20, 'column': 3, 'value': 7}]},
                {'name': 'OVERDUE BY STANDARD', 'cells': []}]}

    def run_reconcile(self):
        return reconcile(self.candidate, self.extracted, self.definitions)

    def test_complete_accounting_preserves_types_and_edition_unknown(self):
        result = self.run_reconcile()
        self.assertEqual(result['summary']['sourceRecordCount'], 6)
        self.assertEqual(result['summary']['candidateAssertions'], 2)
        self.assertEqual(result['summary']['unmappedAssertions'], 4)
        self.assertEqual([r['sourceStandard'] for r in result['assertions']], [1, 6, 9, '2', False, ''])
        for row in result['assertions']:
            self.assertIsNone(row['sourceEdition'])
            self.assertFalse(row['acceptedMapping'])
            self.assertFalse(row['establishesCompliance'])
        self.assertEqual(result['assertions'][1]['candidateRequirementIds'], ['fictional-framework-v1-6'])

    def test_explicit_framework_selection_is_required_and_never_guessed(self):
        for value in [None, 'wrong', 'fictional-draft']:
            self.definitions['sourceFrameworkEditionId'] = value
            with self.assertRaises(ValueError): self.run_reconcile()

    def test_cached_discrepancy_is_retained_without_correcting_input(self):
        before = copy.deepcopy((self.candidate, self.extracted, self.definitions))
        result = self.run_reconcile()
        self.assertEqual([r['difference'] for r in result['summary']['cachedTrackingDifferences']], [1, 1])
        self.assertEqual(before, (self.candidate, self.extracted, self.definitions))
        self.assertEqual(result, self.run_reconcile())

    def test_changed_workbook_or_raw_values_are_refused(self):
        self.extracted['workbookSha256'] = 'b' * 64
        with self.assertRaises(ValueError): self.run_reconcile()
        self.extracted['workbookSha256'] = 'a' * 64
        self.extracted['records'][0]['fields']['sourceStandard'] = 5
        with self.assertRaises(ValueError): self.run_reconcile()

    def test_partial_duplicate_or_misbound_identity_is_refused(self):
        original = copy.deepcopy(self.candidate)
        for change in ['missing', 'duplicate_uid', 'duplicate_row', 'wrong_document', 'exception']:
            self.candidate = copy.deepcopy(original)
            if change == 'missing': self.candidate['operations'].pop()
            if change == 'duplicate_uid': self.candidate['operations'][1]['DocumentUID'] = 'fictional-0'
            if change == 'duplicate_row': self.candidate['operations'][1]['sourceRow'] = 2
            if change == 'wrong_document': self.candidate['operations'][0]['fields']['sourceDocumentId'] = 'other'
            if change == 'exception': self.candidate['exceptions'] = ['unresolved']
            with self.assertRaises(ValueError, msg=change): self.run_reconcile()

    def test_draft_and_missing_sheet_are_not_substituted(self):
        self.definitions['frameworks'][0]['status'] = 'draft'
        with self.assertRaises(ValueError): self.run_reconcile()
        self.definitions['frameworks'][0]['status'] = 'published'
        self.extracted['sheets'].pop()
        with self.assertRaises(ValueError): self.run_reconcile()

    def test_cli_refuses_existing_output_before_reading_or_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'preserve.txt'
            marker.write_text('human evidence')
            result = subprocess.run([sys.executable, '-m', 'scripts.ppg_source_standards',
                '--candidate', 'missing', '--workbook', 'missing', '--definitions', 'missing', '--output', directory],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Output exists', result.stderr)
            self.assertEqual(marker.read_text(), 'human evidence')
