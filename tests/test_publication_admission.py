"""Actual two-phase publisher admission preserves its existing guarded writers."""
import copy
import sys
from pathlib import Path
import unittest
from uuid import UUID
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools/lifecycle'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools/policy-editions'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bind_publication_admission import build
from build_prepared_binary_publication import build as publisher
from build_prepared_decision_outcome import digest
from build_operator_entry import _flatten
from test_prepared_binary_publication import fixture
from test_prepared_closure_check import Expressions


def configured():
    args=fixture();flow=publisher(*args);folder=args[2]['qualificationFolder']
    binding={'qualificationOnly':True,'approvedDefinitionSHA256':digest(flow['properties']['definition']),
        'requestedFolder':folder,'expectedFolder':{'UniqueId':str(UUID(int=8,version=4)),'ServerRelativeUrl':folder},
        'requestedReceipt':folder+'/FICTIONAL-proof.json','expectedReceipt':{'UniqueId':str(UUID(int=9,version=4)),
            'ETag':'"1"','ServerRelativeUrl':folder+'/FICTIONAL-proof.json'}}
    return flow,binding


class PublicationAdmissionTests(unittest.TestCase):
    def test_original_writers_triggers_and_connections_are_preserved_behind_admission(self):
        flow,binding=configured();before=copy.deepcopy(flow);out=build(flow,binding)
        old=_flatten(flow['properties']['definition']['actions']);new=_flatten(out['properties']['definition']['actions'])
        self.assertEqual(before,flow)
        for name in ['Copy_binary_absent_only','Create_binary_publication']:
            self.assertEqual(new[name],old[name])
        self.assertEqual(flow['properties']['definition']['triggers'],out['properties']['definition']['triggers'])
        self.assertEqual(flow['properties']['connectionReferences'],out['properties']['connectionReferences'])
        self.assertEqual(out['properties']['definition']['actions']['Resolve_context']['runAfter'],{'PA_Check_receipt':['Succeeded']})
        self.assertEqual(new['PA_Read_destination']['inputs']['parameters']['parameters/method'],'GET')

    def test_exact_native_folder_and_receipt_guard_predicates(self):
        flow,binding=configured();nodes=_flatten(build(flow,binding)['properties']['definition']['actions'])
        folder={**binding['expectedFolder'],'Exists':True};receipt=binding['expectedReceipt']
        ev=Expressions({'PA_Read_destination':folder,'PA_Read_receipt':receipt})
        self.assertTrue(ev.evaluate(nodes['PA_Verify_destination']['expression']))
        self.assertTrue(ev.evaluate(nodes['PA_Verify_receipt']['expression']))
        for field,value in [('UniqueId',str(UUID(int=11,version=4))),('ServerRelativeUrl','/wrong'),('Exists',False)]:
            with self.subTest(folder=field):
                self.assertFalse(Expressions({'PA_Read_destination':{**folder,field:value}}).evaluate(nodes['PA_Verify_destination']['expression']))
        for field,value in [('UniqueId',str(UUID(int=12,version=4))),('ETag','"2"'),('ServerRelativeUrl','/wrong')]:
            with self.subTest(receipt=field):
                self.assertFalse(Expressions({'PA_Read_receipt':{**receipt,field:value}}).evaluate(nodes['PA_Verify_receipt']['expression']))

    def test_copy_is_not_blocked_by_absent_receipt_qualification_but_recording_holds(self):
        flow,binding=configured();binding.update(requestedReceipt=None,expectedReceipt=None)
        nodes=_flatten(build(flow,binding)['properties']['definition']['actions'])
        self.assertNotIn('PA_Read_receipt',nodes)
        self.assertIn('PA_Held_issued_receipt_not_qualified',nodes)
        expression=nodes['PA_Check_receipt']['expression']
        self.assertFalse(Expressions(outputs={'Test_trigger':{'text':'Prepare binary copy'}}).evaluate(expression))
        self.assertTrue(Expressions(outputs={'Test_trigger':{'text':'Record publication'}}).evaluate(expression))
        self.assertFalse(nodes['PA_Copy_receipt_not_required']['inputs']['publicationAllowed'])

    def test_wrong_path_wildcard_stale_definition_or_double_binding_is_refused(self):
        flow,binding=configured()
        for key,value in [('requestedFolder','https://example.invalid/outside'),('requestedReceipt','/other-site/proof'),('approvedDefinitionSHA256','bad')]:
            changed=copy.deepcopy(binding);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):build(flow,changed)
        changed=copy.deepcopy(binding);changed['expectedReceipt']['ETag']='*'
        with self.assertRaises(ValueError):build(flow,changed)
        out=build(flow,binding);binding['approvedDefinitionSHA256']=digest(out['properties']['definition'])
        with self.assertRaises(ValueError):build(out,binding)

    def test_only_actual_404_is_classified_as_missing(self):
        flow,binding=configured();nodes=_flatten(build(flow,binding)['properties']['definition']['actions'])
        expression=nodes['PA_Receipt_read_failure']['expression']
        for status in [400,401,403,429,500]:
            with self.subTest(status=status):self.assertFalse(Expressions(outputs={'PA_Read_receipt':{'statusCode':status}}).evaluate(expression))
        self.assertTrue(Expressions(outputs={'PA_Read_receipt':{'statusCode':404}}).evaluate(expression))

    def test_independent_or_skipped_input_writer_cannot_escape_admission(self):
        for statuses in [None,['Skipped']]:
            flow,binding=configured()
            flow['properties']['definition']['actions']['Ensure_publication']['runAfter']=(
                {} if statuses is None else {'Validate_publication_input':statuses})
            binding['approvedDefinitionSHA256']=digest(flow['properties']['definition'])
            with self.subTest(statuses=statuses),self.assertRaises(ValueError):build(flow,binding)

    def test_switch_case_or_default_cannot_hide_native_io_outside_admission(self):
        for branch in ('case', 'default'):
            flow, binding = configured()
            writer = copy.deepcopy(_flatten(flow['properties']['definition']['actions'])['Copy_binary_absent_only'])
            writer['runAfter'] = {}
            unadmitted = {'type': 'Switch', 'expression': 'selected', 'runAfter': {}}
            group = {'Unadmitted_copy': writer}
            if branch == 'case':
                unadmitted['cases'] = {'Selected_case': {'case': 'selected', 'actions': group}}
            else:
                unadmitted['default'] = {'actions': group}
            flow['properties']['definition']['actions']['Unadmitted_switch'] = unadmitted
            binding['approvedDefinitionSHA256'] = digest(flow['properties']['definition'])
            with self.subTest(branch=branch), self.assertRaisesRegex(ValueError, 'dominate'):
                build(flow, binding)
