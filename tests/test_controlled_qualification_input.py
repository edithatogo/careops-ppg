import copy
import unittest
from build_controlled_qualification_input import build, digest
from test_prepared_closure_check import Expressions


def fixture():
    refs={'shared_sharepointonline':{'connectionName':'qualified-existing'}}
    source={'properties':{'connectionReferences':refs,'definition':{'triggers':{'manual':{
        'type':'Request','kind':'Button','inputs':{'schema':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}},
        'runtimeConfiguration':{'concurrency':{'runs':1}}}},'actions':{
        'Validate':{'type':'Compose','inputs':"@triggerBody()?['text']",'runAfter':{}},
        'Write':{'type':'OpenApiConnection','inputs':{'host':{'connectionName':'shared_sharepointonline'},
            'parameters':{'dataset':'https://example.sharepoint.com/site','parameters/method':'POST',
                          'parameters/uri':'items','parameters/body':"@triggerBody()?['text_6']"},
            'retryPolicy':{'type':'none'}},'runAfter':{'Validate':['Succeeded']}}}}}}
    target={'properties':{'state':'Stopped','isManaged':False,'connectionReferences':copy.deepcopy(refs),
                          'definition':{'triggers':copy.deepcopy(source['properties']['definition']['triggers']),'actions':{}}}}
    binding={'qualificationOnly':True,'siteUrl':'https://example.sharepoint.com/site',
             'approvedSourceDefinitionSHA256':digest(source['properties']['definition']),
             'approvedStoppedTargetDefinitionSHA256':digest(target['properties']['definition']),
             'fixtureCaseUID':'LC-FICTIONAL-OP-OCC-ADVERSE',
             'expectedInput':{'text':'Check context','text_6':'LC-FICTIONAL-OP-OCC-ADVERSE'},
             'controlFile':{'UniqueId':'00000000-0000-4000-8000-000000000001','ETag':'"1"'}}
    return source,target,binding


class ControlledQualificationTests(unittest.TestCase):
    def test_preserves_original_logic_and_gates_all_roots_without_new_writer(self):
        args=fixture();prior=copy.deepcopy(args);out=build(*args);self.assertEqual(args,prior)
        a=out['properties']['definition']['actions'];self.assertEqual(len(a),7)
        self.assertEqual(a['Validate']['inputs'],"@outputs('Qualification_input')?['text']")
        self.assertEqual(a['Validate']['runAfter'],{'Qualification_input_guard':['Succeeded']})
        expected=copy.deepcopy(args[0]['properties']['definition']['actions']['Write'])
        expected['inputs']['parameters']['parameters/body']="@outputs('Qualification_input')?['text_6']"
        self.assertEqual(a['Write'],expected)
        self.assertEqual(out['properties']['state'],'Stopped')
        for name in ['Qualification_control_before','Qualification_control_content','Qualification_control_after']:
            self.assertEqual(a[name]['inputs']['parameters']['parameters/method'],'GET')

    def test_exact_control_identity_token_and_object_are_required(self):
        s,t,b=fixture();a=build(s,t,b)['properties']['definition']['actions'];expr=a['Qualification_input_guard']['expression']
        def evaluate(before,after,payload):
            return Expressions({'Qualification_control_before':before,'Qualification_control_after':after},
                               {'Qualification_input':payload}).evaluate(expr)
        pin=b['controlFile'];self.assertTrue(evaluate(pin,pin,b['expectedInput']))
        for changed in [{**pin,'ETag':'"2"'},{**pin,'UniqueId':'different'}]:
            self.assertFalse(evaluate(changed,pin,b['expectedInput']))
            self.assertFalse(evaluate(pin,changed,b['expectedInput']))
        self.assertFalse(evaluate(pin,pin,{**b['expectedInput'],'text':'Different'}))
        self.assertFalse(evaluate(pin,pin,{**b['expectedInput'],'pass':True}))
        self.assertEqual(a['Qualification_input_guard']['else']['actions']['Qualification_refuse_changed_input']['type'],'Terminate')

    def test_rejects_unbound_targets_and_other_case_inputs(self):
        for change in ['source','target','started','managed','other-case','unqualified','wildcard']:
            s,t,b=fixture()
            if change=='source':b['approvedSourceDefinitionSHA256']='wrong'
            if change=='target':b['approvedStoppedTargetDefinitionSHA256']='wrong'
            if change=='started':t['properties']['state']='Started'
            if change=='managed':t['properties']['isManaged']=True
            if change=='other-case':b['expectedInput']['text_6']='LC-FICTIONAL-OP-OTHER'
            if change=='unqualified':b['qualificationOnly']=False
            if change=='wildcard':b['controlFile']['ETag']='*'
            with self.assertRaises(ValueError,msg=change):build(s,t,b)

    def test_only_matching_initiation_occurrence_can_replace_case_reference(self):
        s,t,b=fixture();b['expectedInput']={'text':'LC02-OP-ADVERSE','text_1':'OCC-ADVERSE','text_5':'Initiate review'}
        build(s,t,b)
        b['expectedInput']['text_1']='OCC-OTHER'
        with self.assertRaises(ValueError):build(s,t,b)

    def test_site_and_original_schema_remain_bound(self):
        s,t,b=fixture();b['siteUrl']='https://contoso.sharepoint.com/site'
        with self.assertRaises(ValueError):build(s,t,b)
        s,t,b=fixture();b['expectedInput'].pop('text')
        with self.assertRaises(ValueError):build(s,t,b)
