import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_identity_triage import inspect, proposal, validate


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.uid = '12345678-1234-4234-9234-123456789abc'
        self.ledger = {'sourceSystemId': 'fictional', 'aliases': [
            {'source': 'fictional', 'alias': 'known-v1', 'DocumentUID': self.uid}]}
        self.snapshot = {'sourceSha256': 'a'*64, 'records': [
            {'sourceRow': 2, 'fields': {'sourceDocumentId': 'known-v1'}},
            {'sourceRow': 987, 'fields': {'sourceDocumentId': 'unrecognised-v2'}}]}
        self.report = inspect(self.snapshot, 'fictional', self.ledger, {'sourceDocumentId'})

    def test_unknown_preserves_inputs_and_does_not_guess(self):
        before = copy.deepcopy(self.snapshot)
        self.assertEqual(self.report['exceptions'][0]['code'], 'unknown_alias')
        self.assertEqual(self.report['exceptions'][0]['candidateUIDs'], [])
        self.assertEqual(self.snapshot, before)
        self.assertFalse(self.report['writesPermitted'])

    def test_missing_only_snapshot_is_visible_without_retirement(self):
        from ppg_identity_triage import render
        missing='00000000-0000-4000-8000-000000000002'
        self.ledger['aliases'].append({'source':'fictional','alias':'absent','DocumentUID':missing})
        self.snapshot['records']=self.snapshot['records'][:1]
        report=inspect(self.snapshot,'fictional',self.ledger,{'sourceDocumentId'})
        self.assertEqual(report['exceptions'],[])
        output=render(report)
        self.assertIn(missing,output)
        self.assertIn('Investigate missing records',output)

    def test_proposal_and_stale_rejection(self):
        p = proposal(self.report, self.report['exceptions'][0]['exceptionKey'])
        self.assertTrue(validate(p, self.report, self.ledger)['validForReview'])
        p['sourceSha256'] = 'b'*64
        self.assertIn('stale_or_conflicting_sourceSha256', validate(p, self.report, self.ledger)['issues'])

    def test_acceptance_cannot_bypass_identity_or_evidence(self):
        p = proposal(self.report, self.report['exceptions'][0]['exceptionKey'])
        p['status'] = 'accepted'
        self.assertFalse(validate(p, self.report, self.ledger)['validForReview'])
        p.update(resolution='existing_uid', existingUID=self.uid, rationale='Fictional evidence',
                 evidenceReferences=['fictional-record'], decisionEvidence='fictional-decision')
        result = validate(p, self.report, self.ledger)
        self.assertTrue(result['validForReview'])
        self.assertFalse(result['applyAvailable'])
        self.assertFalse(result['writesPermitted'])
        changed = copy.deepcopy(self.ledger)
        changed['aliases'][0]['alias'] = 'different'
        self.assertIn('ledger_changed', validate(p, self.report, changed)['issues'])

    def test_duplicate_identity_is_separate_exception(self):
        self.snapshot['records'][1]['fields']['sourceDocumentId'] = 'known-v1'
        r = inspect(self.snapshot, 'fictional', self.ledger, {'sourceDocumentId'})
        self.assertEqual(r['exceptions'][0]['code'], 'duplicate_identity')

class GuidedResolutionTests(unittest.TestCase):
    def setUp(self):
        from ppg_source_sync import prepare
        self.uid1 = '00000000-0000-4000-8000-000000000001'
        self.uid2 = '00000000-0000-4000-8000-000000000002'
        self.ledger = {'sourceSystemId': 'fictional', 'aliases': [
            {'source': 'fictional', 'alias': 'A', 'DocumentUID': self.uid1},
            {'source': 'fictional', 'alias': 'B', 'DocumentUID': self.uid2}]}
        self.allowed = {'sourceDocumentId', 'sourceTitle'}
        self.snapshot = {'sourceSha256': 'b'*64, 'records': [
            {'sourceRow': 2, 'fields': {'sourceDocumentId': 'A', 'sourceTitle': 'first'}},
            {'sourceRow': 987, 'fields': {'sourceDocumentId': 'B-revised', 'sourceTitle': '<script>bad()</script>'}}]}
        self.report = inspect(self.snapshot, 'fictional', self.ledger, self.allowed)
        self.p = proposal(self.report, self.report['exceptions'][0]['exceptionKey'])
        self.p.update(resolution='existing_uid', existingUID=self.uid2,
                      rationale='Fictional authoritative continuity evidence', evidenceReferences=['fictional://identity-proof'])

    def accepted(self):
        from ppg_identity_triage import transition
        return transition(self.p, 'accepted', 'fictional://operator-decision', 'Fictional operator')

    def test_missing_uid_is_an_unselected_investigation_lead(self):
        self.assertEqual(self.report['exceptions'][0]['candidateUIDs'], [self.uid2])
        self.assertIsNone(proposal(self.report, self.p['exceptionKey'])['existingUID'])

    def test_stage_is_pure_and_existing_planner_rejects_collision(self):
        from ppg_identity_triage import stage_amendment
        before = copy.deepcopy(self.ledger)
        staged = stage_amendment(self.accepted(), self.snapshot, self.ledger, self.allowed)
        self.assertEqual(self.ledger, before)
        self.assertFalse(staged['writesPermitted'])
        self.assertEqual(staged['stagedPlan']['exceptions'], [])
        p = self.accepted(); p['existingUID'] = self.uid1
        with self.assertRaisesRegex(ValueError, 'uid_collision'):
            stage_amendment(p, self.snapshot, self.ledger, self.allowed)
        stale = copy.deepcopy(self.snapshot); stale['sourceSha256'] = 'c'*64
        with self.assertRaisesRegex(ValueError, 'stale_or_conflicting_sourceSha256'):
            stage_amendment(self.accepted(), stale, self.ledger, self.allowed)

    def test_replay_staged_alias_fails_closed(self):
        from ppg_identity_triage import stage_amendment
        accepted = self.accepted()
        staged = stage_amendment(accepted, self.snapshot, self.ledger, self.allowed)
        with self.assertRaises(ValueError):
            stage_amendment(accepted, self.snapshot, staged['stagedLedger'], self.allowed)

    def test_new_uid_request_is_explicitly_unapplied(self):
        from ppg_identity_triage import stage_amendment
        p = self.accepted(); p.update(resolution='request_new_uid', existingUID=None)
        result = stage_amendment(p, self.snapshot, self.ledger, self.allowed)
        self.assertNotIn('stagedPlan', result)
        self.assertIn('explicit_new_identity_authorisation', result['blockedReason'])

    def test_invalid_transitions_and_malformed_evidence(self):
        from ppg_identity_triage import transition
        with self.assertRaisesRegex(ValueError, 'invalid_transition'):
            transition(self.accepted(), 'verified', 'fictional', 'operator')
        p = self.accepted(); p['evidenceReferences'] = 'not-an-array'
        self.assertFalse(validate(p, self.report, self.ledger)['validForReview'])
        p = self.accepted(); p['status'] = 'verified'
        self.assertIn('application_evidence_required', validate(p, self.report, self.ledger)['issues'])

    def test_html_escapes_source_content(self):
        from ppg_identity_triage import render
        out = render(self.report)
        self.assertNotIn('<script>', out)
        self.assertIn('&lt;script&gt;', out)
        self.assertIn(self.p['exceptionKey'], out)

    def test_supported_reconciler_readback_replay_local_edits_and_failure(self):
        import tempfile
        from ppg_identity_triage import stage_amendment
        from ppg_source_sync import prepare, reconcile, SyncError
        class Target:
            def __init__(self, uids):
                self.items = {u: {'localDecision': 'pending'} for u in uids}
                self.fail = None
                self.bad = False
            def read(self, uid):
                return copy.deepcopy(self.items[uid]), 'fictional-etag'
            def patch(self, uid, fields, etag):
                if uid == self.fail:
                    raise RuntimeError('fictional-write-failure')
                assert set(fields) <= {'sourceDocumentId', 'sourceTitle'}
                self.items[uid].update(fields)
                if self.bad:
                    self.items[uid]['sourceTitle'] = 'wrong'
        target = Target([self.uid1, self.uid2])
        original = copy.deepcopy(self.snapshot)
        original['records'][1]['fields']['sourceDocumentId'] = 'B'
        original['sourceSha256'] = 'a'*64
        with tempfile.TemporaryDirectory() as td:
            state = Path(td)
            reconcile(prepare(original, 'fictional', self.ledger['aliases'], self.allowed), target, state)
            checkpoint = (state/'last-successful.json').read_bytes()
            staged = stage_amendment(self.accepted(), self.snapshot, self.ledger, self.allowed)
            target.items[self.uid1]['localDecision'] = 'operator edit'
            target.fail = self.uid2
            with self.assertRaises(RuntimeError):
                reconcile(staged['stagedPlan'], target, state)
            self.assertEqual((state/'last-successful.json').read_bytes(), checkpoint)
            target.fail = None; target.bad = True
            with self.assertRaises(SyncError):
                reconcile(staged['stagedPlan'], target, state)
            self.assertEqual((state/'last-successful.json').read_bytes(), checkpoint)
            target.bad = False
            result = reconcile(staged['stagedPlan'], target, state)
            self.assertEqual(result['readbackCount'], 2)
            self.assertEqual(target.items[self.uid1]['localDecision'], 'operator edit')
            self.assertEqual(reconcile(staged['stagedPlan'], target, state)['writeCount'], 0)

    def test_multiple_leads_are_not_automatically_resolved(self):
        third = '00000000-0000-4000-8000-000000000003'
        self.ledger['aliases'].append({'source': 'fictional', 'alias': 'C', 'DocumentUID': third})
        report = inspect(self.snapshot, 'fictional', self.ledger, self.allowed)
        self.assertEqual(report['exceptions'][0]['candidateUIDs'], [self.uid2, third])
        self.assertEqual(proposal(report, report['exceptions'][0]['exceptionKey'])['resolution'], 'unresolved')

    def test_duplicate_exception_key_and_alias_contract_rejected(self):
        duplicated = copy.deepcopy(self.snapshot['records'][1]); duplicated['sourceRow'] = 988
        self.snapshot['records'].append(duplicated)
        report = inspect(self.snapshot, 'fictional', self.ledger, self.allowed)
        with self.assertRaisesRegex(ValueError, 'ambiguous_exception_key'):
            proposal(report, report['exceptions'][0]['exceptionKey'])
        self.ledger['aliases'].append(copy.deepcopy(self.ledger['aliases'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate_alias_contract'):
            inspect(self.snapshot, 'fictional', self.ledger, self.allowed)


if __name__ == '__main__':
    unittest.main()
