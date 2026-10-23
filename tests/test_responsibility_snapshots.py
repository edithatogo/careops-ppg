import copy
import json
import unittest
from scripts.ppg_responsibility_snapshots import snapshots


class ResponsibilitySnapshots(unittest.TestCase):
    def fixture(self):
        return dict(roles={'value':[dict(RoleKey='r',Title='Fictional role',HolderKind='person')]},
            assignments={'value':[dict(AssignmentKey='a',DocumentUID='d',RoleKey='r',ResponsibilityType='custodian',EffectiveFrom='2026-01-01',ReviewState='Accepted',EvidenceRef='fictional assignment')]},
            appointments={'value':[
                dict(AppointmentKey='p1',RoleKey='r',HolderKey='old',AppointmentKind='substantive',EffectiveFrom='2026-01-01',EffectiveUntil='2026-06-01',ReviewState='Accepted',EvidenceRef='fictional appointment'),
                dict(AppointmentKey='p2',RoleKey='r',HolderKey='new',AppointmentKind='acting',EffectiveFrom='2026-06-01',ReviewState='Accepted',EvidenceRef='fictional appointment')]},
            handovers={'value':[]},historicalDecisions=[dict(actor='old',decision='fictional past event')])

    def test_dated_holder_changes_without_rewriting_history_and_repeat_keys(self):
        source=self.fixture();raw=json.dumps(source).encode()
        a=snapshots(raw,'2026-05-31');b=snapshots(raw,'2026-06-01')
        self.assertEqual(a['records'][0]['record']['HolderKey'],'old')
        self.assertEqual(b['records'][0]['record']['HolderKey'],'new')
        self.assertEqual(a['projection']['historicalDecisions'],b['projection']['historicalDecisions'])
        self.assertNotEqual(a['manifest']['runKey'],b['manifest']['runKey'])
        self.assertEqual(a,snapshots(raw,'2026-05-31'))
        self.assertFalse(a['manifest']['grantsAccess'])
        self.assertEqual(json.loads(raw),source)

    def test_partial_export_and_missing_handover_inventory_refused(self):
        source=self.fixture();source['appointments']['@odata.nextLink']='next'
        with self.assertRaises(ValueError):snapshots(json.dumps(source).encode(),'2026-06-01')
        source=self.fixture();del source['handovers']
        with self.assertRaises(ValueError):snapshots(json.dumps(source).encode(),'2026-06-01')

    def test_overlap_is_visible_without_selecting_holder(self):
        source=self.fixture();source['appointments']['value'][0]['EffectiveUntil']=None
        row=snapshots(json.dumps(source).encode(),'2026-06-01')['records'][0]['record']
        self.assertEqual(row['ResolutionState'],'ambiguous');self.assertIsNone(row['HolderKey'])

    def test_changed_source_creates_distinct_run_and_preserves_prior_output(self):
        source=self.fixture();first=snapshots(json.dumps(source).encode(),'2026-06-01')
        preserved=copy.deepcopy(first)
        source['appointments']['value'][1]['HolderKey']='corrected-fictional-holder'
        second=snapshots(json.dumps(source).encode(),'2026-06-01')
        self.assertNotEqual(first['manifest']['runKey'],second['manifest']['runKey'])
        self.assertEqual(first,preserved)
        self.assertEqual(first['projection']['historicalDecisions'],second['projection']['historicalDecisions'])
        self.assertFalse(json.loads(second['records'][0]['record']['Projection'])['grantsClinicalAuthority'])
