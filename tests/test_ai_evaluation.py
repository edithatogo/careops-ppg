import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_ai_evaluation import evaluate


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.case = {'caseId': 'test', 'question': 'Is authority known?',
                     'selectedSources': [], 'expectedSources': {}, 'expectedStatus': 'unknown',
                     'reviewCriteria': ['Leave unsupported authority unknown.']}
        self.pack = {'cases': [self.case]}
        self.run = dict(caseId='test', question=self.case['question'], runtime='test-runtime',
                        model='test-model', configurationRevision='fixture-v1', executedAtUtc='2026-10-16T00:00:00Z',
                        rawResponseEvidence='private/raw', retrievalEvidence='private/read',
                        actionAuditEvidence='private/audit', allowedPrefix='https://example.test/evidence',
                        sources=[], observedActions=[], answer=dict(status='unknown', claims=[],
                        actionsPerformed=[], policyApproved=False))

    def test_missing_is_not_pass(self):
        result = evaluate(self.pack, [])
        self.assertEqual(result['counts']['not-run'], 1)
        self.assertFalse(result['evaluationComplete'])

    def test_mechanical_pass_needs_review(self):
        self.assertEqual(evaluate(self.pack, [self.run])['cases'][0]['state'], 'awaiting-human-review')

    def test_bound_review_and_changed_answer(self):
        fingerprint = evaluate(self.pack, [self.run])['cases'][0]['subjectSha256']
        self.run['humanReview'] = dict(result='pass', reviewer='fixture reviewer',
            reviewedAtUtc='2026-10-16T01:00:00Z', evidence='private/review',
            findings='Fixture only; no operational evaluation claimed.', subjectSha256=fingerprint)
        result = evaluate(self.pack, [self.run])
        self.assertTrue(result['evaluationComplete'])
        self.assertFalse(result['promotionReady'])
        self.run['answer']['explanation'] = 'changed'
        self.assertFalse(evaluate(self.pack, [self.run])['evaluationComplete'])

    def test_wrong_status_and_actions_fail(self):
        self.run['answer']['status'] = 'refused'
        self.run['observedActions'] = ['write']
        self.assertEqual(evaluate(self.pack, [self.run])['cases'][0]['state'], 'failed')

    def test_scope_and_missing_proof_fail(self):
        self.run['sources'] = [{'sourceId': 'extra', 'status': 'denied'}]
        del self.run['runtime']
        result = evaluate(self.pack, [self.run])['cases'][0]
        self.assertIn('selected_scope_mismatch', result['issues'])
        self.assertIn('missing_run_evidence:runtime', result['issues'])

    def test_failed_review_is_failed(self):
        self.run['humanReview'] = {'result': 'fail'}
        self.assertEqual(evaluate(self.pack, [self.run])['cases'][0]['state'], 'failed')

    def test_runtime_change_invalidates_review(self):
        fingerprint = evaluate(self.pack, [self.run])['cases'][0]['subjectSha256']
        self.run['model'] = 'different-model'
        self.assertNotEqual(evaluate(self.pack, [self.run])['cases'][0]['subjectSha256'], fingerprint)

    def reviewed_run(self):
        run = copy.deepcopy(self.run)
        fingerprint = evaluate(self.pack, [run])['cases'][0]['subjectSha256']
        run['humanReview'] = dict(result='pass', reviewer='fixture',
            reviewedAtUtc='2026-10-16T01:00:00Z', evidence='private/review',
            findings='Fixture', subjectSha256=fingerprint)
        return run

    def test_mixed_configuration_rejected(self):
        for field in ('runtime', 'model', 'configurationRevision'):
            with self.subTest(field=field):
                case = dict(self.case, caseId='second')
                first = self.reviewed_run()
                second = dict(first, caseId='second')
                second[field] = 'different'
                with self.assertRaisesRegex(ValueError, 'same runtime'):
                    evaluate({'cases': [self.case, case]}, [first, second])

    def test_invalid_execution_times_fail(self):
        for value in ('not-a-date', '2026-10-16', '2026-10-16T00:00:00',
                      '2026-10-16T10:00:00+10:00', '2026-02-30T00:00:00Z'):
            with self.subTest(value=value):
                run = self.reviewed_run()
                run['executedAtUtc'] = value
                row = evaluate(self.pack, [run])['cases'][0]
                self.assertIn('invalid_utc_time:executedAtUtc', row['issues'])
                self.assertEqual(row['state'], 'failed')

    def test_invalid_review_times_fail(self):
        for value in ('not-a-date', '2026-10-16T01:00:00', '2026-10-16T11:00:00+10:00'):
            with self.subTest(value=value):
                run = self.reviewed_run()
                run['humanReview']['reviewedAtUtc'] = value
                self.assertIn('invalid_utc_time:reviewedAtUtc',
                    evaluate(self.pack, [run])['cases'][0]['issues'])

    def test_review_cannot_precede_run(self):
        run = self.reviewed_run()
        run['humanReview']['reviewedAtUtc'] = '2026-10-15T23:59:59Z'
        self.assertIn('review_precedes_execution', evaluate(self.pack, [run])['cases'][0]['issues'])

    def test_utc_offsets_and_configuration_report(self):
        run = self.reviewed_run()
        run['humanReview']['reviewedAtUtc'] = '2026-10-16T01:00:00+00:00'
        result = evaluate(self.pack, [run])
        self.assertTrue(result['evaluationComplete'])
        self.assertEqual(result['configuration'], dict(runtime='test-runtime', model='test-model',
                                                     configurationRevision='fixture-v1'))

    def test_configuration_revision_required(self):
        del self.run['configurationRevision']
        self.assertIn('missing_run_evidence:configurationRevision',
                      evaluate(self.pack, [self.run])['cases'][0]['issues'])

    def test_case_contract_requires_source_expectations_and_review_criteria(self):
        for field in ('expectedSources', 'reviewCriteria'):
            with self.subTest(field=field):
                pack = copy.deepcopy(self.pack)
                del pack['cases'][0][field]
                with self.assertRaises(KeyError):
                    evaluate(pack, [])
        for criteria in ([], [''], 'not a checklist'):
            case = dict(self.case, reviewCriteria=criteria)
            with self.assertRaises(ValueError):
                evaluate({'cases': [case]}, [])
        case = dict(self.case, selectedSources=['missing-expectation'])
        with self.assertRaisesRegex(ValueError, 'exactly cover'):
            evaluate({'cases': [case]}, [])

    def test_fixed_pack_matches_fictional_corpus_and_exposes_rubrics(self):
        root = Path(__file__).resolve().parents[1]
        pack = json.loads((root/'templates/cited-evidence/evaluation-cases.json').read_text())
        corpus = json.loads((root/'templates/cited-evidence/corpus.json').read_text())
        result = evaluate(pack, [])
        self.assertEqual(result['counts']['not-run'], 12)
        self.assertFalse(result['evaluationComplete'])
        for source in corpus['sources']:
            actual = hashlib.sha256((root/'templates/cited-evidence'/source['file']).read_bytes()).hexdigest()
            self.assertEqual(actual, source['sha256'])
            for case in pack['cases']:
                expected = case['expectedSources'].get(source['sourceId'])
                if expected:
                    self.assertEqual(expected['sha256'], actual)
                    self.assertEqual(expected['authorityLabel'], source['authorityLabel'])
        self.assertTrue(all(row['reviewCriteria'] for row in result['cases']))

    def test_wrong_source_status_cannot_pass_with_matching_review(self):
        case = dict(self.case, selectedSources=['denied'], expectedSources={'denied': {'status': 'denied'}})
        run = copy.deepcopy(self.run)
        run['sources'] = [{'sourceId': 'denied', 'status': 'invented-state'}]
        result = evaluate({'cases': [case]}, [run])
        run['humanReview'] = dict(result='pass', reviewer='fixture',
            reviewedAtUtc='2026-10-16T01:00:00Z', evidence='private/review', findings='Fixture',
            subjectSha256=result['cases'][0]['subjectSha256'])
        result = evaluate({'cases': [case]}, [run])
        self.assertIn('expected_source_mismatch:denied:status', result['cases'][0]['issues'])
        self.assertFalse(result['cases'][0]['mechanicallyValid'])
        self.assertFalse(result['evaluationComplete'])

    def test_self_consistent_wrong_content_and_authority_fail(self):
        source = dict(nativeUniqueId='11111111-1111-4111-8111-111111111111',sourceId='selected', status='retrieved', text='Fictional original',
            sha256=hashlib.sha256(b'Fictional original').hexdigest(),
            authorityLabel='captured-reference-unconfirmed', nativeVersionRef='1.0',
            retrievedAtUtc='2026-10-16T00:00:00Z', canonicalUrl='https://example.test/evidence/selected.txt')
        case = dict(self.case, selectedSources=['selected'], expectedSources={'selected': {
            k: source[k] for k in ('status', 'sha256', 'authorityLabel')}})
        for mutate, issue in (
            (lambda s: s.update(text='Different content', sha256=hashlib.sha256(b'Different content').hexdigest()), 'sha256'),
            (lambda s: s.update(authorityLabel='operative'), 'authorityLabel'),
            (lambda s: s.update(retrievedAtUtc='yesterday'), 'time'),
            (lambda s: s.update(nativeVersionRef=1), 'version')):
            with self.subTest(issue=issue):
                run = copy.deepcopy(self.run)
                run['sources'] = [copy.deepcopy(source)]
                mutate(run['sources'][0])
                row = evaluate({'cases': [case]}, [run])['cases'][0]
                self.assertEqual(row['state'], 'failed')
                self.assertFalse(row['mechanicallyValid'])
                self.assertTrue(any(issue in x for x in row['issues']))

    def test_rubric_change_invalidates_review(self):
        run = self.reviewed_run()
        pack = copy.deepcopy(self.pack)
        pack['cases'][0]['reviewCriteria'].append('New independent source-review criterion.')
        self.assertFalse(evaluate(pack, [run])['evaluationComplete'])

    def test_cli_empty_and_invalid_inputs_have_distinct_exits(self):
        import tempfile
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, 'scripts/ppg_ai_evaluation.py', '--runs']
        result = subprocess.run(command + ['templates/ai-evaluation/empty-runs.json'], cwd=root,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['counts']['not-run'], 12)
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory)/'invalid.json'
            bad.write_text('{invalid')
            result = subprocess.run(command + [str(bad)], cwd=root, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Invalid evaluation input', result.stderr)

    def test_all_twelve_cases_are_evaluable_with_explicit_test_receipts(self):
        # Software fixtures only: these are not actual model outputs or human reviews.
        root = Path(__file__).resolve().parents[1]
        pack = json.loads((root/'templates/cited-evidence/evaluation-cases.json').read_text())
        corpus = json.loads((root/'templates/cited-evidence/corpus.json').read_text())
        text_by_id = {s['sourceId']: (root/'templates/cited-evidence'/s['file']).read_text()
                      for s in corpus['sources']}
        runs = []
        for case in pack['cases']:
            run = copy.deepcopy(self.run)
            run.update(caseId=case['caseId'], question=case['question'])
            run['sources'] = []
            claims = []
            for uid, expected in case['expectedSources'].items():
                source = dict(expected, sourceId=uid)
                if source['status'] == 'retrieved':
                    source.update(nativeUniqueId='11111111-1111-4111-8111-111111111111',text=text_by_id[uid], nativeVersionRef='fictional-test-version',
                        retrievedAtUtc='2026-10-16T00:00:00Z',
                        canonicalUrl='https://example.test/evidence/' + uid + '.txt')
                    if case['expectedStatus'] in {'supported', 'conflict'}:
                        cite = {k: source[k] for k in ('sourceId', 'canonicalUrl', 'nativeVersionRef',
                                                      'sha256', 'authorityLabel')}
                        cite.update(startLine=3, endLine=3, quote=source['text'].splitlines()[2])
                        claims.append(dict(claimId=uid, text=cite['quote'], citations=[cite],
                                           assertsCurrentAuthority=False))
                run['sources'].append(source)
            run['answer'].update(status=case['expectedStatus'], claims=claims)
            runs.append(run)
        report = evaluate(pack, runs)
        self.assertEqual(report['counts']['awaiting-human-review'], 12)
        for run, row in zip(runs, report['cases']):
            run['humanReview'] = dict(result='pass', reviewer='software-fixture-only',
                reviewedAtUtc='2026-10-16T01:00:00Z', evidence='fictional://test-only',
                findings='Unit test of evaluator state transitions; no AI evaluation claimed.',
                subjectSha256=row['subjectSha256'])
        report = evaluate(pack, runs)
        self.assertEqual(report['counts']['reviewed-pass'], 12)
        self.assertTrue(report['evaluationComplete'])
        self.assertFalse(report['promotionReady'])

    def test_duplicates_rejected(self):
        with self.assertRaises(ValueError):
            evaluate(self.pack, [self.run, copy.deepcopy(self.run)])


if __name__ == '__main__':
    unittest.main()
