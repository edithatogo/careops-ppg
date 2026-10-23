import copy
import unittest
from scripts.ppg_portfolio_transfer import audit_transfer


class PortfolioTransfer(unittest.TestCase):
    def fixture(self):
        return dict(roles=[dict(roleId='old-role', title='Fictional old role'), dict(roleId='new-role', title='Fictional new role')],
            appointments=[dict(appointmentId='old-holder',roleId='old-role',holderId='fictional-one',appointmentKind='substantive',effectiveFrom='2026-01-01',status='accepted',evidenceRef='fictional://appointment'),
                          dict(appointmentId='new-holder',roleId='new-role',holderId='fictional-two',appointmentKind='substantive',effectiveFrom='2026-01-01',status='accepted',evidenceRef='fictional://appointment')],
            assignments=[dict(assignmentId='old',documentUID='fictional-document',roleId='old-role',responsibilityType='custodian',effectiveFrom='2026-01-01',effectiveUntil='2026-09-01',status='accepted',evidenceRef='fictional://assignment'),
                         dict(assignmentId='new',documentUID='fictional-document',roleId='new-role',responsibilityType='custodian',effectiveFrom='2026-09-01',status='accepted',evidenceRef='fictional://assignment')],
            handovers=[dict(handoverId='transfer',kind='portfolio_transfer',fromRoleId='old-role',toRoleId='new-role',documentUIDs=['fictional-document'],effectiveFrom='2026-09-01',status='accepted',acceptedBy='fictional-acceptor',acceptedAt='2026-08-30T00:00:00Z',evidenceRef='fictional://handover')],
            historicalDecisions=[dict(decisionId='fictional-past',actorId='fictional-one',roleId='old-role',appointmentId='old-holder')])

    def pairs(self):
        return [dict(fromAssignmentId='old',toAssignmentId='new')]

    def test_manual_transfer_preserves_inputs_actors_and_exact_replay(self):
        bundle=self.fixture();before=copy.deepcopy(bundle);result=audit_transfer(bundle,'transfer',self.pairs())
        self.assertEqual(result['before']['responsibilities'][0]['roleId'],'old-role')
        self.assertEqual(result['after']['responsibilities'][0]['roleId'],'new-role')
        self.assertEqual(result['historicalDecisions'],before['historicalDecisions'])
        self.assertEqual(bundle,before);self.assertEqual(result,audit_transfer(bundle,'transfer',self.pairs()))
        self.assertFalse(result['authorityVerified']);self.assertEqual(result['nativeWrites'],0)

    def test_incomplete_scope_duplicate_pair_and_ambiguous_destination_refused(self):
        for change in ['scope','missing','duplicate','overlap']:
            with self.subTest(change=change):
                bundle=self.fixture();pairs=self.pairs()
                if change=='scope':bundle['handovers'][0]['documentUIDs'].append('another-document')
                if change=='missing':pairs=[]
                if change=='duplicate':pairs+=self.pairs()
                if change=='overlap':
                    row=copy.deepcopy(bundle['assignments'][1]);row['assignmentId']='another-target';bundle['assignments'].append(row)
                with self.assertRaises(ValueError):audit_transfer(bundle,'transfer',pairs)

    def test_unclosed_source_gap_wrong_responsibility_and_unaccepted_evidence_refused(self):
        for field,value in [('effectiveUntil',None),('effectiveUntil','2026-08-31'),('responsibilityType','author'),('status','proposed'),('evidenceRef','')]:
            bundle=self.fixture();bundle['assignments'][0][field]=value
            with self.subTest(field=field,value=value):
                with self.assertRaises(ValueError):audit_transfer(bundle,'transfer',self.pairs())
        bundle=self.fixture();bundle['handovers'][0]['acceptedAt']='2026-08-30'
        with self.assertRaises(ValueError):audit_transfer(bundle,'transfer',self.pairs())

    def test_unpaired_active_source_responsibility_is_not_silently_omitted(self):
        bundle=self.fixture();extra=copy.deepcopy(bundle['assignments'][0]);extra.update(assignmentId='other-source',responsibilityType='author');bundle['assignments'].append(extra)
        with self.assertRaises(ValueError):audit_transfer(bundle,'transfer',self.pairs())

    def test_overlapping_accepted_transfer_assertions_are_not_arbitrarily_selected(self):
        bundle=self.fixture();other=copy.deepcopy(bundle['handovers'][0]);other['handoverId']='another-transfer';bundle['handovers'].append(other)
        with self.assertRaises(ValueError):audit_transfer(bundle,'transfer',self.pairs())
