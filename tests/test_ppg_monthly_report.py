"""Focused independent checks; native probes and real CSV verification supplement these."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('verify_monthly_report', Path(__file__).parents[1] / 'scripts/verify_monthly_report.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class MonthBoundaries(unittest.TestCase):
    def test_month_precision_and_year_rollover(self):
        cases = {'2026-09': 'Overdue', '2026-10': 'Due this month',
                 '2026-11': 'Due next three months', '2027-01': 'Due next three months',
                 '2027-02': 'Later'}
        for value, expected in cases.items():
            self.assertEqual(report.classify(value, '2026-10'), expected)

    def test_invalid_dates_are_visible_exceptions(self):
        for value in (None, '', '2026-1', '2026-13', '+123-01', '0000-01', '2026-10-01'):
            self.assertEqual(report.classify(value, '2026-10'), 'Date exception')

    def test_source_text_is_not_an_excel_formula(self):
        for value in ('=1+1', '+SUM(A1)', '-2+3', '@SUM(A1)', '\t@evil', '  =1+1'):
            self.assertEqual(report.safe_text(value), "'" + value)
        self.assertEqual(report.safe_text('ordinary text'), 'ordinary text')

    def test_missing_or_duplicate_records_cannot_pass(self):
        candidate = {'operations': [{'DocumentUID': 'a', 'fields': {'sourceNextReviewMonth': '2026-09'}}], 'rawRecords': [], 'inputCount': 1}
        with self.assertRaises(ValueError):
            report.verify(candidate, [])
        with self.assertRaises(ValueError):
            report.verify(candidate, [{'DocumentUID': 'a', 'Report month': '2026-10'}, {'DocumentUID': 'a', 'Report month': '2026-10'}])

    def test_all_later_is_valid_empty_report(self):
        candidate = {'operations': [{'DocumentUID': 'a', 'fields': {'sourceNextReviewMonth': '2027-02'}}],
                     'rawRecords': [], 'inputCount': 1}
        result = report.verify(candidate, [], '2026-10')
        self.assertEqual(result['rows'], 0)
        self.assertEqual(result['laterAccounted'], 1)


if __name__ == '__main__':
    unittest.main()
