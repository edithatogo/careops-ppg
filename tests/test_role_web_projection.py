import copy
import json
from pathlib import Path
import subprocess
import unittest
from scripts.ppg_role_projection import project, from_native
from tests import test_role_projection


class RoleWebProjection(unittest.TestCase):
    def invoke(self, requests):
        value = subprocess.run(['node','tools/roles/test_projection.mjs'], input=json.dumps(requests),
                               capture_output=True, text=True, check=True)
        return json.loads(value.stdout)
    def test_succession_overlap_vacancy_scope_and_history_match_existing_projection(self):
        base = test_role_projection.RoleProjection().fixture()
        cases = [(base,'2026-05-31'),(base,'2026-06-01')]
        overlap = copy.deepcopy(base);overlap['appointments'][0]['effectiveUntil']=None
        cases.append((overlap,'2026-06-01'))
        vacant = copy.deepcopy(base);vacant['appointments'][1].update(appointmentKind='vacant',holderId=None)
        cases.append((vacant,'2026-06-01'))
        missing = copy.deepcopy(base);missing['appointments']=[];cases.append((missing,'2026-06-01'))
        delegated = copy.deepcopy(base);delegated['appointments'][1].update(appointmentKind='delegated',
            delegationScope={'documentUIDs':['fictional-doc'],'responsibilityTypes':['executive_accountability']},authorityEvidence='fictional://authority')
        cases.append((delegated,'2026-06-01'))
        wrong = copy.deepcopy(delegated);wrong['appointments'][1]['delegationScope']['documentUIDs']=['other'];cases.append((wrong,'2026-06-01'))
        unaccepted = copy.deepcopy(base);unaccepted['assignments'][0]['status']='proposed';cases.append((unaccepted,'2026-06-01'))
        actual = self.invoke([dict(model=m,asOf=d) for m,d in cases])
        self.assertEqual(actual,[dict(ok=True,value=project(m,d)) for m,d in cases])
    def test_invalid_dates_references_delegation_and_partial_exports_refuse(self):
        base=test_role_projection.RoleProjection().fixture();cases=[]
        for day in ['2026-02-29','2026-13-01','0000-01-01','20261020','2026-W43-2']:
            cases.append(dict(model=base,asOf=day))
        invalid=copy.deepcopy(base);invalid['appointments'][1]['roleId']='unknown';cases.append(dict(model=invalid,asOf='2026-10-20'))
        invalid=copy.deepcopy(base);invalid['appointments'][1]['appointmentKind']='delegated';cases.append(dict(model=invalid,asOf='2026-10-20'))
        native={k:{'value':[]} for k in ['roles','assignments','appointments','handovers']};native['roles']['odata.nextLink']='fictional-next';cases.append(dict(native=native,asOf='2026-10-20'))
        self.assertEqual(self.invoke(cases),[dict(ok=False) for _ in cases])
    def test_accepted_handover_actor_and_evidence_are_preserved(self):
        base=test_role_projection.RoleProjection().fixture();base['handovers']=[dict(handoverId='h',kind='succession',fromRoleId='executive',toRoleId='executive',fromAppointmentId='a1',toAppointmentId='a2',documentUIDs=['fictional-doc'],effectiveFrom='2026-06-01',status='accepted',acceptedBy='fictional-two',acceptedAt='2026-06-01T00:00:00Z',evidenceRef='fictional://handover')]
        self.assertEqual(self.invoke([dict(model=base,asOf='2026-10-20')]),[dict(ok=True,value=project(base,'2026-10-20'))])
        invalid=copy.deepcopy(base);invalid['handovers'][0]['evidenceRef']=''
        self.assertEqual(self.invoke([dict(model=invalid,asOf='2026-10-20')]),[dict(ok=False)])
    def test_native_main_has_stable_keys_exact_source_hash_and_no_workbook_effects(self):
        import hashlib
        native = {k:{'value':[]} for k in ['roles','assignments','appointments','handovers']}
        request = dict(kind='ppg-role-projection-v1',native=native,asOf='2026-10-20',scriptSHA256='a'*64,roleContractSHA256='b'*64)
        result = self.invoke([dict(operation='main',request=request),dict(operation='main',request=request)])
        self.assertEqual(result[0], result[1])
        self.assertTrue(result[0]['ok'])
        output = result[0]['value']
        self.assertEqual(output['manifest']['sourceSha256'],hashlib.sha256(output['sourceJson'].encode()).hexdigest())
        self.assertEqual(output['records'],[])
        self.assertFalse(output['manifest']['sourceModified'] or output['manifest']['grantsAccess'])
        request['scriptSHA256']='not-a-hash'
        self.assertEqual(self.invoke([dict(operation='main',request=request)]),[dict(ok=False)])
