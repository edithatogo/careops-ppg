import copy
import csv
import io
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_process_measures import measure,render,csv_report
ROOT=Path(__file__).resolve().parents[1]

class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.bundle=json.loads((ROOT/'templates/process-reporting/input.json').read_text())

    def test_explicit_pairs_and_calendar_basis(self):
        original=copy.deepcopy(self.bundle)
        r=measure(self.bundle)
        self.assertEqual(r['durations']['readiness-to-decision']['sampleCount'],2)
        self.assertEqual(r['durations']['readiness-to-decision']['caseCount'],1)
        self.assertEqual(r['durations']['readiness-to-decision']['medianCalendarDays'],1.5)
        self.assertEqual(r['durations']['decision-to-publication']['medianCalendarDays'],2)
        self.assertEqual(r['durations']['implementation-to-verification']['medianCalendarDays'],2)
        self.assertEqual(r['cases'][0]['ageCalendarDays'],15)
        self.assertEqual(self.bundle,original)
        self.assertIn('[FICTIONAL EXAMPLE]',render(r))

    def test_empty_history_is_not_zero(self):
        for key in ('assurance','readiness'):
            self.bundle['sources'][key].update(items=[],itemCount=0)
        r=measure(self.bundle)
        self.assertTrue(all(v['status']=='not-measurable' and v['medianCalendarDays'] is None for v in r['durations'].values()))
        self.assertEqual(r['summary']['casesWithValidatedHistory'],0)
        self.assertIn('Not measurable',render(r))

    def test_pending_date_not_overdue_and_csv_denominator(self):
        self.bundle['sources']['cases']['items'][0]['targetDate']='To be agreed, no date assigned'
        r=measure(self.bundle)
        self.assertEqual(r['summary']['unconfirmedTarget'],1)
        rows=list(csv.DictReader(io.StringIO(csv_report(r))))
        self.assertEqual(next(x for x in rows if x['measure']=='pastTarget')['denominator'],'0')

    def test_version_mismatch_excluded(self):
        self.bundle['sources']['assurance']['items'][2]['ReviewedVersionRef']='v2'
        r=measure(self.bundle)
        self.assertEqual(r['durations']['decision-to-publication']['sampleCount'],0)
        self.assertTrue(any('version_mismatch:ParentEventUID' in x.get('details',[]) for x in r['exclusions']))

    def test_negative_future_and_missing_dates(self):
        for datevalue in ['2026-09-01','2027-01-01',None]:
            b=copy.deepcopy(self.bundle);b['sources']['assurance']['items'][2]['OccurredOn']=datevalue
            r=measure(b)
            self.assertEqual(r['durations']['decision-to-publication']['sampleCount'],0)

    def test_pending_and_not_applicable_do_not_complete(self):
        for state in ['Pending evidence','Not applicable']:
            b=copy.deepcopy(self.bundle);b['sources']['assurance']['items'][2]['RecordState']=state
            self.assertEqual(measure(b)['durations']['decision-to-publication']['sampleCount'],0)

    def test_fictional_not_in_operational_measures(self):
        self.bundle['datasetKind']='operational';r=measure(self.bundle)
        self.assertEqual(r['summary']['recordedCases'],0)
        self.assertEqual(len(r['exclusions']),7)

    def test_partial_duplicate_and_unqualified_export_rejected(self):
        for change in ['partial','duplicate','count']:
            b=copy.deepcopy(self.bundle);s=b['sources']['cases']
            if change=='partial':s['nextLink']='more'
            elif change=='duplicate':s['items']*=2;s['itemCount']=2
            else:s['itemCount']=2
            with self.assertRaises(ValueError):measure(b)

    def test_invalid_parent_not_counted(self):
        self.bundle['sources']['assurance']['items'][1]['EvidenceReference']=''
        r=measure(self.bundle)
        self.assertEqual(r['durations']['decision-to-publication']['sampleCount'],0)

    def test_html_escapes_untrusted_role(self):
        self.bundle['sources']['cases']['items'][0]['accountableRole']='<script>alert(1)</script>'
        self.assertNotIn('<script>',render(measure(self.bundle)))

    def test_unrepeated_capture_rejected(self):
        self.bundle['sources']['cases']['repeatReadVerified']=False
        with self.assertRaises(ValueError):measure(self.bundle)

    def test_same_day_is_measurable_zero(self):
        self.bundle['sources']['assurance']['items'][2]['OccurredOn']='2026-10-03'
        r=measure(self.bundle)['durations']['decision-to-publication']
        self.assertEqual(r['sampleCount'],1)
        self.assertEqual(r['medianCalendarDays'],0)
        self.assertEqual(r['status'],'measured-recorded-pairs')

if __name__=='__main__':unittest.main()
