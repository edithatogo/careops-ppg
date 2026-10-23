import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('assurance_report',Path(__file__).resolve().parents[1]/'scripts/ppg_assurance_report.py')
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)


class AssuranceReport(unittest.TestCase):
    def test_actual_single_step_receipt_exit_status(self):
        for key in ('event', 'state'):
            for code, expected in ((0, 'successful'), (7, 'incomplete'), (None, 'incomplete')):
                with self.subTest(key=key, code=code), tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / 'attempt.jsonl'
                    path.write_text(json.dumps({key: 'command-exited', 'exitCode': code}) + '\n')
                    self.assertEqual(report.inspect_input(path)['outcome'], expected)

    def test_plan_requires_all_stages_not_just_last_completed_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plan.jsonl'
            header = {'event': 'created', 'planSHA256': 'a' * 64, 'totalSteps': 2}
            stages = [{'event': event, 'index': index} for index in range(2)
                      for event in ('started', 'completed')]
            for count, expected in ((0, 'incomplete'), (2, 'incomplete'), (3, 'incomplete'), (4, 'successful')):
                path.write_text(''.join(json.dumps(x) + '\n' for x in [header, *stages[:count]]))
                self.assertEqual(report.inspect_input(path)['outcome'], expected)
            for invalid in (None, 0, True, '2'):
                path.write_text(''.join(json.dumps(x) + '\n' for x in [{**header, 'totalSteps': invalid}, *stages]))
                self.assertEqual(report.inspect_input(path)['outcome'], 'incomplete')
            path.write_text(''.join(json.dumps(x) + '\n' for x in [header, *stages, {'event': 'refused'}]))
            self.assertEqual(report.inspect_input(path)['outcome'], 'refused')

    def test_success_refusal_and_incomplete_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            success=root/'success.jsonl'
            success.write_text('\n'.join(json.dumps(x) for x in [
                {'event':'prepared'}, {'event':'verified'}, {'event':'complete','state':'published'}
            ])+'\n')
            refused=root/'refused.jsonl'
            refused.write_text(json.dumps({'event':'failed','code':'REMOTE_REVISION_CONFLICT','reconcileBeforeRetry':True})+'\n')
            incomplete=root/'incomplete.jsonl'
            incomplete.write_text(json.dumps({'event':'started','step':'lookup'})+'\n')
            outcomes=[report.inspect_input(p)['outcome'] for p in (success,refused,incomplete)]
            self.assertEqual(outcomes,['successful','refused','incomplete'])

    def test_technical_flags_do_not_become_human_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'evaluation.json'
            path.write_text(json.dumps({
                'kind':'source-evaluation','status':'EVIDENCE PREPARATION ONLY / AUTHORITY UNCONFIRMED',
                'deterministicChecksPassed':True,'sourcePreparationQualified':True,
                'conversationalRetrievalQualified':False,'semanticReviewPerformed':False,
            }))
            item=report.inspect_input(path)
            self.assertEqual(item['outcome'],'successful')
            self.assertEqual(item['technicalQualification'],'partial')
            self.assertEqual(item['humanAcceptance'],'not assessed by CLI receipts')

    def test_report_counts_outcomes_and_excludes_receipt_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); success=root/'success.json'; refused=root/'refused.json'
            success.write_text(json.dumps({'status':'supported','secretQuote':'private clinical text'}))
            refused.write_text(json.dumps({'status':'NOT SELECTED','code':'SOURCE_REVISION_CONFLICT'}))
            text=report.build_report([success,refused])
            self.assertIn('| Successful | 1 |',text)
            self.assertIn('| Refused | 1 |',text)
            self.assertIn('not assessed',text)
            self.assertNotIn('private clinical text',text)
            self.assertIn(str(success),text)

    def test_completed_report_does_not_inherit_negative_check_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'evaluation.json'
            path.write_text(json.dumps({'status':'supported','checks':[{'status':'refused','passed':True}]}))
            self.assertEqual(report.inspect_input(path)['outcome'],'successful')

    def test_cli_creates_private_report_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'receipt.jsonl'; output=Path(tmp)/'status.md'
            source.write_text(json.dumps({'event':'complete'})+'\n')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(report.main(['--input',str(source),'--output',str(output)]),0)
            self.assertEqual(output.stat().st_mode & 0o777,0o600)
            self.assertIn('Human acceptance: **not assessed**',output.read_text())
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(report.main(['--input',str(source),'--output',str(output)]),1)

    def test_invalid_or_oversized_receipts_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); malformed=root/'bad.jsonl'; malformed.write_text('{oops}\n')
            with self.assertRaises(json.JSONDecodeError): report.inspect_input(malformed)
            oversized=root/'large.json'; oversized.write_bytes(b' '*(report.MAX_FILE_BYTES+1))
            with self.assertRaisesRegex(ValueError,'exceeds'):
                report.inspect_input(oversized)


if __name__=='__main__': unittest.main()
