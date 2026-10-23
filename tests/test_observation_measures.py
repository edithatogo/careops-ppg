"""Observation cohorts, missingness, matched tasks and no-overwrite contracts."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from ppg_observation_measures import observation_report, observation_csv


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.text=(ROOT/'templates/operator-usability/fictional-matched-observation.csv').read_text()
        self.rows=list(csv.DictReader(io.StringIO(self.text)))
        self.headers=list(self.rows[0])

    def report(self,rows=None):
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=self.headers)
        writer.writeheader();writer.writerows(self.rows if rows is None else rows)
        return observation_report(stream.getvalue())

    def test_legacy_example_preserves_existing_arithmetic(self):
        r=observation_report((ROOT/'templates/operator-usability/fictional-observation.csv').read_text())
        self.assertEqual(r['summary']['attemptedTasks'],5)
        self.assertEqual(r['summary']['handsOn']['sampleCount'],4)
        self.assertEqual(r['summary']['handsOn']['totalSeconds'],200)
        self.assertEqual(r['summary']['handsOn']['medianSeconds'],45)
        self.assertEqual(r['summary']['help']['yesCount'],2)
        self.assertEqual(r['summary']['help']['knownTaskCount'],5)
        self.assertEqual(r['comparisons'],{})
        self.assertEqual(r['benefitConclusion'],'Not measured')

    def test_template_and_header_only_are_not_zero_time(self):
        template=(ROOT/'templates/operator-usability/operator-observation.csv').read_text()
        for text in [template,template.splitlines()[0]+'\n']:
            r=observation_report(text)
            self.assertEqual(r['status'],'not-measured')
            self.assertEqual(r['summary']['attemptedTasks'],0)
            self.assertIsNone(r['summary']['handsOn']['medianSeconds'])
            self.assertEqual(r['comparisons'],{})

    def test_matched_tasks_separate_waits_counts_and_signed_differences(self):
        original=copy.deepcopy(self.rows);r=self.report()
        self.assertEqual(r['comparisons']['find-evidence']['medianBaselineMinusWorkbenchSeconds'],60)
        self.assertEqual(r['comparisons']['find-case']['medianBaselineMinusWorkbenchSeconds'],20)
        self.assertNotIn('prepare-package',r['comparisons'])
        self.assertIn('incomplete-or-untimed-task',[x['reason'] for x in r['comparisonExclusions']])
        self.assertEqual(r['summary']['handsOn']['sampleCount'],5)
        self.assertEqual(r['summary']['stageWait']['sampleCount'],4)
        self.assertEqual(r['summary']['help']['knownTaskCount'],5)
        self.assertEqual(r['summary']['help']['unknownTaskCount'],1)
        self.assertEqual(self.rows,original)
        self.rows[1]['durationSeconds']='100'
        self.assertEqual(self.report()['comparisons']['find-evidence']['medianBaselineMinusWorkbenchSeconds'],-10)

    def test_zero_duration_valid_missing_not_zero(self):
        self.rows[0]['durationSeconds']='0';self.rows[1]['durationSeconds']='0'
        self.assertEqual(self.report()['comparisons']['find-evidence']['medianBaselineMinusWorkbenchSeconds'],0)
        self.rows[1]['durationSeconds']='';self.rows[1]['exclusionReason']='Timing unavailable'
        r=self.report();self.assertNotIn('find-evidence',r['comparisons'])
        self.assertEqual(r['byMethodAndTask']['workbench/find-evidence']['handsOn']['completedMissingCount'],1)

    def test_match_identity_gaps_and_mismatches_do_not_compare(self):
        for key in ['inputRef','sourcePeriod','sourceVersion','taskVariant']:
            for value in ['','other']:
                rows=copy.deepcopy(self.rows);rows[1][key]=value
                self.assertNotIn('find-evidence',self.report(rows)['comparisons'])
        self.assertNotIn('find-evidence',self.report(self.rows[1:])['comparisons'])

    def test_duplicate_rows_methods_and_mixed_dataset_rejected(self):
        for rows in [self.rows+[self.rows[0]], self.rows+[{**self.rows[0],'walkthroughId':'another'}],
                     [{**self.rows[0],'datasetKind':'operational'},*self.rows[1:]]]:
            with self.assertRaises(ValueError):self.report(rows)

    def test_bad_numbers_timestamps_unknowns_and_missing_reasons_refused(self):
        for field,value in [('durationSeconds','NaN'),('durationSeconds','-1'),('durationSeconds','inf'),
                            ('durationSeconds','9'*400),('missingInputCount','1.5'),('correctionCount','-2'),
                            ('asOf','2026-10-18'),('asOf','invalid'),('helpRequired','maybe'),('method','estimate'),
                            ('outcome','approved'),('task','=arbitrary'),('datasetKind','unknown')]:
            rows=copy.deepcopy(self.rows);rows[0][field]=value
            with self.subTest(field=field,value=value):
                with self.assertRaises(ValueError):self.report(rows)
        self.rows[4]['exclusionReason']=''
        with self.assertRaises(ValueError):self.report()

    def test_aggregate_overflow_and_unobserved_measurements_refused(self):
        self.rows[0]['durationSeconds']='1'+'0'*308
        self.rows[1]['durationSeconds']='1'+'0'*308
        with self.assertRaises(ValueError):self.report()
        self.setUp();self.rows[0]['outcome']='not-observed'
        with self.assertRaises(ValueError):self.report()
        with self.assertRaises(ValueError):observation_report('task,task\nfind-case,find-case\n')

    def test_csv_output_never_contains_free_text_cells(self):
        self.rows[4]['exclusionReason']='=SUM(1,2)'
        self.rows[0]['inputRef']='=potential-formula'
        r=self.report();text=observation_csv(r)
        self.assertNotIn('potential-formula',text)
        self.assertNotIn('=SUM',text)
        self.assertIn('fictional',text)

    def test_cli_exact_input_hash_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'input.csv';raw=b'\xef\xbb\xbf'+self.text.replace('\n','\r\n').encode()
            source.write_bytes(raw);output=root/'report'
            args=[sys.executable,str(ROOT/'scripts/ppg_process_measures.py'),'--observations',str(source),'--output',str(output)]
            result=subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads((output/'observations.json').read_text())
            self.assertEqual(report['inputSHA256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(source.read_bytes(),raw)
            (output/'observations.json').write_text('Human edit')
            result=subprocess.run(args,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual((output/'observations.json').read_text(),'Human edit')


if __name__=='__main__':unittest.main()
