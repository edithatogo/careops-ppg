"""Synthetic checks of revision binding, review holds and immutable receipts."""
import copy
import tempfile
from pathlib import Path
import unittest
from scripts.ppg_owner_master import prepare, review, record_decision, digest, write_once


class OwnerMasterTests(unittest.TestCase):
    def fixture(self):
        source, candidate = b'previous synthetic guide', b'new synthetic guide'
        job = {'documentUID': 'synthetic-guide', 'occurrenceUID': 'review-2',
               'requestUID': 'request-2', 'proposedEdition': '2-draft',
               'changeSummary': 'clarify safe invocation', 'scope': 'owner-approved-workbench',
               'contentOwnership': 'project-owned', 'planningReviewDate': '2027-01-01',
               'source': {'reference': 'https://example.invalid/guide.md', 'edition': '1',
                          'nativeId': 'synthetic-file', 'nativeVersion': '1.0',
                          'etag': '"1"', 'sha256': digest(source)}}
        manifest = prepare(job, source, candidate)
        findings = {'preparationSHA256': manifest['preparationSHA256'], 'checks': [
            {'area': area, 'response': 'no-issue-in-checked-scope', 'severity': 'none',
             'disposition': 'no-action', 'rationale': 'bounded synthetic check',
             'uncertainty': 'synthetic evidence only', 'evidence': [
                 {'reference': 'synthetic:guide', 'locator': 'line 1', 'sha256': digest(candidate)}]}
            for area in manifest['requiredReviewAreas']]}
        return job, source, candidate, manifest, findings

    def decision(self, report, candidate):
        return {'reviewSHA256': report['reviewSHA256'], 'candidateSHA256': digest(candidate),
                'scope': 'owner-approved-workbench', 'decision': 'accept',
                'userInstructionReference': 'synthetic:test-user-instruction',
                'recordedAt': '2026-10-28T01:00:00Z', 'effectiveDate': '2026-10-28',
                'rationale': 'synthetic test only'}

    def test_acceptance_is_bound_and_never_issues(self):
        _, _, raw, manifest, findings = self.fixture()
        report = review(manifest, raw, findings)
        self.assertIsNone(report['userAcceptance'])
        decision = record_decision(report, raw, self.decision(report, raw))
        self.assertFalse(decision['issued'])
        self.assertFalse(decision['officialCurrent'])
        self.assertFalse(decision['notificationsAllowed'])
        self.assertEqual(manifest['source']['edition'], '1')
        self.assertTrue(manifest['supersedes']['proposedOnly'])

    def test_source_and_candidate_drift_refused(self):
        job, source, raw, manifest, findings = self.fixture()
        with self.assertRaisesRegex(ValueError, 'source_bytes_changed'):
            prepare(job, source+b'edited', raw)
        with self.assertRaisesRegex(ValueError, 'candidate_revision_changed'):
            review(manifest, raw+b'edited', findings)
        report = review(manifest, raw, findings)
        with self.assertRaisesRegex(ValueError, 'candidate_revision_changed'):
            record_decision(report, raw+b'edited', self.decision(report, raw))

    def test_missing_duplicate_and_wrong_revision_review_refused(self):
        _, _, raw, manifest, findings = self.fixture()
        for change in ('missing', 'duplicate', 'wrong-preparation', 'missing-evidence'):
            altered = copy.deepcopy(findings)
            if change == 'missing': altered['checks'].pop()
            if change == 'duplicate': altered['checks'][0]['area'] = altered['checks'][1]['area']
            if change == 'wrong-preparation': altered['preparationSHA256'] = 'f'*64
            if change == 'missing-evidence': altered['checks'][0]['evidence'] = []
            with self.subTest(change=change), self.assertRaises(ValueError):
                review(manifest, raw, altered)

    def test_open_unknown_and_high_findings_hold_acceptance(self):
        for field, value in [('disposition', 'open'), ('response', 'needs-evidence'), ('severity', 'high')]:
            _, _, raw, manifest, findings = self.fixture()
            findings['checks'][0][field] = value
            report = review(manifest, raw, findings)
            self.assertEqual(report['state'], 'Needs evidence')
            with self.assertRaisesRegex(ValueError, 'unresolved_review_blockers'):
                record_decision(report, raw, self.decision(report, raw))
            decision = self.decision(report, raw); decision['decision'] = 'return'
            self.assertEqual(record_decision(report, raw, decision)['state'], 'Returned for revision')

    def test_decision_cannot_transfer_to_other_revision_or_review(self):
        _, _, raw, manifest, findings = self.fixture()
        report = review(manifest, raw, findings)
        for field in ('candidateSHA256', 'reviewSHA256', 'scope', 'userInstructionReference'):
            decision = self.decision(report, raw)
            decision[field] = ''
            with self.subTest(field=field), self.assertRaises(ValueError):
                record_decision(report, raw, decision)

    def test_dates_and_recorded_time_are_explicit_and_valid(self):
        job, source, raw, manifest, findings = self.fixture()
        for value in ('20270230', '2027-02-30', 'tomorrow'):
            altered = copy.deepcopy(job); altered['planningReviewDate'] = value
            with self.subTest(date=value), self.assertRaises(ValueError):
                prepare(altered, source, raw)
        job['planningReviewDate'] = None
        self.assertIsNone(prepare(job, source, raw)['planningReviewDate'])
        report = review(manifest, raw, findings)
        decision = self.decision(report, raw); decision['recordedAt'] = '2026-10-28T01:00:00'
        with self.assertRaisesRegex(ValueError, 'utc_recorded_time_required'):
            record_decision(report, raw, decision)

    def test_immutable_replay_and_changed_input_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'receipt.json'
            self.assertEqual(write_once(path, {'revision': 1}), 'created')
            self.assertEqual(write_once(path, {'revision': 1}), 'replay-preserved')
            with self.assertRaisesRegex(ValueError, 'existing_receipt_differs'):
                write_once(path, {'revision': 2})
            self.assertIn(b'1', path.read_bytes())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class OwnerGuideEntryTests(unittest.TestCase):
    def fixture(self):
        from tools.lifecycle.build_owner_guide_entry import build
        reference = {'properties': {'definition': {'parameters': {}, '$schema': 'synthetic',
            'contentVersion': '1.0.0.0', 'actions': {'existing': {'inputs': {
                'parameters': {'dataset': 'https://example.invalid/sites/workbench'}}}}},
            'connectionReferences': {'shared_sharepointonline': {'connectionName': 'synthetic-connection'}}}}
        binding = {'siteUrl': 'https://example.invalid/sites/workbench',
                   'documentUID': 'PPG-WORKBENCH-OPERATOR-GUIDE', 'proposedEdition': 'owner-1-draft',
                   'source': {'nativeId': '00000000-0000-4000-8000-000000000001',
                              'etag': '"1"', 'nativeVersion': '1.0', 'sha256': 'a'*64},
                   'candidateSHA256': 'b'*64}
        return build, reference, binding

    def test_manual_entry_is_read_only_and_keeps_connections(self):
        from scripts.check_email_safety import email_actions
        build, reference, binding = self.fixture()
        candidate = build(reference, binding)
        self.assertEqual(candidate['properties']['state'], 'Stopped')
        self.assertFalse(candidate['properties']['flowFailureAlertSubscribed'])
        self.assertEqual(email_actions(candidate), [])
        self.assertEqual(candidate['properties']['connectionReferences'], reference['properties']['connectionReferences'])
        definition = candidate['properties']['definition']
        self.assertEqual(definition['triggers']['manual']['kind'], 'Button')
        self.assertEqual(list(definition['triggers']), ['manual'])
        for action in ('Read_source', 'Read_source_after'):
            self.assertEqual(definition['actions'][action]['inputs']['parameters']['parameters/method'], 'GET')
            self.assertEqual(definition['actions'][action]['inputs']['retryPolicy'], {'type': 'none'})
        queue = definition['actions']['Verify_request_and_source']['actions']['Preparation_request']['inputs']
        self.assertTrue(queue['agentSessionRequired'])
        self.assertFalse(queue['approvalRecorded'])
        self.assertEqual(queue['nativeDataWrites'], 0)

    def test_site_credentials_and_malformed_targets_are_refused(self):
        build, reference, binding = self.fixture()
        for target in ('https:///sites/workbench',
                       'https://:secret@example.invalid/sites/workbench',
                       'https://user@example.invalid/sites/workbench',
                       'http://example.invalid/sites/workbench'):
            changed = copy.deepcopy(binding)
            changed['siteUrl'] = target
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'exact_https_site_required'):
                build(reference, changed)

    def test_binding_drift_rejected_without_mutating_reference(self):
        build, reference, binding = self.fixture()
        original = copy.deepcopy(reference)
        for field, value in [('documentUID', 'external-policy'), ('siteUrl', 'https://other.invalid')]:
            changed = copy.deepcopy(binding); changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build(reference, changed)
        self.assertEqual(reference, original)
        binding['source']['etag'] = '*'
        with self.assertRaisesRegex(ValueError, 'exact_source_token_required'):
            build(reference, binding)


class NativeRequestTests(unittest.TestCase):
    fixture = OwnerMasterTests.fixture
    def test_native_request_bound_and_changed_purpose_cannot_replace_receipt(self):
        from scripts.ppg_owner_master import consume_request
        job, source, candidate, _, _ = self.fixture()
        job['requestUID'] = 'GUIDE-test-1'
        native = {k: job[k] for k in ('documentUID', 'occurrenceUID', 'requestUID',
                                     'proposedEdition', 'scope', 'source', 'planningReviewDate')}
        native.update(kind='owner-guide-preparation-request', candidateSHA256=digest(candidate),
                      purpose='first purpose', nativeDataWrites=0, approvalRecorded=False,
                      issued=False, notificationsAllowed=False, agentSessionRequired=True)
        original = consume_request(native, job, source, candidate)
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp)/'preparation.json'
            write_once(receipt, original)
            native['purpose'] = 'changed purpose'
            changed = consume_request(native, job, source, candidate)
            with self.assertRaisesRegex(ValueError, 'existing_receipt_differs'):
                write_once(receipt, changed)
        for field, value in [('issued', True), ('notificationsAllowed', True),
                             ('candidateSHA256', 'a'*64), ('occurrenceUID', 'different'),
                             ('planningReviewDate', '2027-12-31')]:
            changed = copy.deepcopy(native); changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                consume_request(changed, job, source, candidate)


if __name__ == '__main__':
    unittest.main()
