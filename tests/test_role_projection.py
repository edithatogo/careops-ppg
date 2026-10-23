import copy
import unittest
from scripts.ppg_role_projection import project, from_native


class RoleProjection(unittest.TestCase):
    def fixture(self):
        return dict(roles=[dict(roleId='executive', title='Fictional executive')],
                    assignments=[dict(assignmentId='r1', documentUID='fictional-doc', roleId='executive',
                                      responsibilityType='executive_accountability', effectiveFrom='2026-01-01',
                                      effectiveUntil=None, status='accepted', evidenceRef='fictional://assignment')],
                    appointments=[dict(appointmentId='a1', roleId='executive', holderId='fictional-one',
                                       appointmentKind='substantive', effectiveFrom='2026-01-01', effectiveUntil='2026-06-01',
                                       status='accepted', evidenceRef='fictional://appointment'),
                                  dict(appointmentId='a2', roleId='executive', holderId='fictional-two',
                                       appointmentKind='acting', effectiveFrom='2026-06-01', effectiveUntil=None,
                                       status='accepted', evidenceRef='fictional://handover')],
                    historicalDecisions=[dict(decisionId='d1', actorId='fictional-one', appointmentId='a1',
                                              roleId='executive', decidedAt='2026-05-01', decision='fictional-only')])

    def test_current_holder_changes_history_does_not(self):
        data = self.fixture(); before = copy.deepcopy(data)
        old = project(data, '2026-05-31'); new = project(data, '2026-06-01')
        self.assertEqual(old['responsibilities'][0]['resolution']['holderId'], 'fictional-one')
        self.assertEqual(new['responsibilities'][0]['resolution']['holderId'], 'fictional-two')
        self.assertEqual(new['historicalDecisions'], before['historicalDecisions'])
        self.assertEqual(data, before)
        self.assertFalse(new['accessModified'])

    def test_overlap_and_unaccepted_assignment_are_visible(self):
        data = self.fixture(); data['appointments'][0]['effectiveUntil'] = None
        self.assertEqual(project(data, '2026-06-01')['responsibilities'][0]['resolution']['state'], 'ambiguous')
        data['assignments'][0]['status'] = 'proposed'
        self.assertEqual(project(data, '2026-06-01')['responsibilities'][0]['resolution']['state'], 'unconfirmed_assignment')

    def test_invalid_delegation_and_vacancy_refused(self):
        data = self.fixture(); data['appointments'][1]['appointmentKind'] = 'delegated'
        with self.assertRaises(ValueError): project(data, '2026-06-01')
        data['appointments'][1].update(delegationScope={'documentUIDs':['fictional-doc'], 'responsibilityTypes':['executive_accountability']}, authorityEvidence='fictional://authority')
        self.assertEqual(project(data, '2026-06-01')['responsibilities'][0]['resolution']['state'], 'resolved')
        data['appointments'][1]['delegationScope']['documentUIDs'] = ['other']
        self.assertEqual(project(data, '2026-06-01')['responsibilities'][0]['resolution']['state'], 'delegation_scope_unconfirmed')
        data['appointments'][1]['appointmentKind'] = 'vacant'
        with self.assertRaises(ValueError): project(data, '2026-06-01')

    def test_handover_requires_evidence_and_distinct_transfer_roles(self):
        data = self.fixture()
        data['handovers'] = [dict(handoverId='h', kind='succession', fromRoleId='executive',
                                  toRoleId='executive', fromAppointmentId='a1', toAppointmentId='a2',
                                  documentUIDs=['fictional-doc'], effectiveFrom='2026-06-01',
                                  status='accepted', acceptedBy='fictional-two',
                                  acceptedAt='2026-06-01T00:00:00Z', evidenceRef='fictional://handover')]
        self.assertEqual(project(data, '2026-06-01')['handovers'], data['handovers'])
        data['handovers'][0]['evidenceRef'] = ''
        with self.assertRaises(ValueError): project(data, '2026-06-01')
        data['handovers'][0]['evidenceRef'] = 'fictional://handover'
        data['handovers'][0]['kind'] = 'portfolio_transfer'
        with self.assertRaises(ValueError): project(data, '2026-06-01')

    def test_partial_native_export_refused(self):
        native = dict(roles={'value': [], 'odata.nextLink': 'fictional-next'}, assignments={'value': []}, appointments={'value': []})
        with self.assertRaises(ValueError): from_native(native)
        del native['roles']['odata.nextLink']
        self.assertEqual(from_native(native)['roles'], [])

    def test_noncanonical_and_invalid_dates_are_refused_everywhere(self):
        from scripts.ppg_review_intelligence import resolve_role
        for bad in ['20260601', '2026-W23-1', '2026-02-29', '2026-06-01T00:00:00Z',
                    '2026-6-01', ' 2026-06-01', '２０２６-０６-０１', None, False, 0]:
            with self.subTest(value=bad):
                with self.assertRaises(ValueError): project(self.fixture(), bad)
                with self.assertRaises(ValueError): resolve_role(self.fixture()['appointments'], 'executive', bad)
                for collection in ['assignments', 'appointments']:
                    for field in ['effectiveFrom', 'effectiveUntil']:
                        # None is the supported open-ended interval representation.
                        if bad is None and field == 'effectiveUntil':
                            continue
                        data=self.fixture();data[collection][0][field]=bad
                        with self.assertRaises(ValueError): project(data, '2026-06-01')
                data=self.fixture()
                data['handovers']=[dict(handoverId='h', kind='succession', fromRoleId='executive',
                    toRoleId='executive', fromAppointmentId='a1', toAppointmentId='a2',
                    documentUIDs=['fictional-doc'], effectiveFrom=bad, status='proposed')]
                with self.assertRaises(ValueError): project(data, '2026-06-01')

    def test_valid_leap_day_and_exclusive_boundary_preserve_history(self):
        data=self.fixture();data['appointments'][0]['effectiveFrom']='2024-02-29'
        data['assignments'][0]['effectiveFrom']='2024-02-29'
        before=copy.deepcopy(data)
        self.assertEqual(project(data, '2024-02-29')['responsibilities'][0]['resolution']['holderId'], 'fictional-one')
        self.assertEqual(project(data, '2026-06-01')['responsibilities'][0]['resolution']['holderId'], 'fictional-two')
        self.assertEqual(data, before)


    def test_overlap_never_selects_delegation_scope_or_changes_exception_by_order(self):
        data=self.fixture(); data['appointments'][0]['effectiveUntil']=None
        delegated=data['appointments'][1]
        delegated.update(appointmentKind='delegated',
                         delegationScope={'documentUIDs':['other-document'],
                                          'responsibilityTypes':['executive_accountability']},
                         authorityEvidence='fictional://delegation')
        original=copy.deepcopy(data)
        for appointments in [data['appointments'], list(reversed(data['appointments']))]:
            candidate=copy.deepcopy(data);candidate['appointments']=appointments
            row=project(candidate,'2026-06-01')['responsibilities'][0]
            self.assertEqual(row['resolution']['state'],'ambiguous')
            self.assertIsNone(row['resolution']['holderId'])
            self.assertIsNone(row['delegationScope'])
            self.assertEqual(set(row['resolution']['appointmentIds']),{'a1','a2'})
            self.assertFalse(row['grantsClinicalAuthority'])
        self.assertEqual(data,original)


    def test_missing_holder_is_unconfirmed_and_explicit_vacancy_preserves_history(self):
        data=self.fixture();data['appointments'][1]['holderId']=None
        self.assertEqual(project(data,'2026-06-01')['responsibilities'][0]['resolution']['state'],'unconfirmed')
        data['appointments'][1]['appointmentKind']='vacant';before=copy.deepcopy(data)
        result=project(data,'2026-06-01')
        self.assertEqual(result['responsibilities'][0]['resolution']['state'],'vacant')
        self.assertEqual(result['historicalDecisions'],before['historicalDecisions'])
        self.assertEqual(data,before)


if __name__ == '__main__': unittest.main()
