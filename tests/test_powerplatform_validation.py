"""Structural failures must be caught before packaging or native writes."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('assurance_under_test', Path(__file__).parents[1]/'scripts/powerplatform_validation.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def definition(actions=None):
    return {'triggers': {'manual': {'type': 'Request'}}, 'actions': actions or {'start': {'type': 'Compose', 'inputs': 'fictional'}}}


class ValidationTests(unittest.TestCase):
    def codes(self, value):
        return {c['check'] for c in v.validate_flow(value)['checks'] if c['outcome'] == 'fail'}

    def test_positive_envelopes_and_preservation(self):
        raw = definition({'loop': {'type':'Foreach','foreach':'@createArray(1)', 'actions': {'one': {'type':'Compose','inputs':1}, 'two': {'type':'Compose','inputs':2,'runAfter':{'one':['Succeeded']}}}}})
        raw['futureMetadata']={'keep':[1,2,3]}
        for value in (raw, {'definition':raw}, {'properties':{'definition':raw}}):
            before=copy.deepcopy(value)
            a=v.validate_flow(value)
            self.assertEqual(a['status'],'PASS')
            self.assertFalse(a['deploymentReady'])
            self.assertEqual(a,v.validate_flow(value))
            self.assertEqual(value,before)

    def test_cross_scope_self_status_and_cycle(self):
        fixtures=[({'one':{'type':'Compose','runAfter':{'absent':['Succeeded']}}}, 'non_sibling_dependency'),
                  ({'one':{'type':'Compose','runAfter':{'one':['Succeeded']}}}, 'self_dependency'),
                  ({'one':{'type':'Compose','runAfter':{'two':['Success']}},'two':{'type':'Compose'}},'invalid_dependency_status'),
                  ({'one':{'type':'Compose','runAfter':{'two':['Succeeded']}},'two':{'type':'Compose','runAfter':{'one':['Failed']}}},'dependency_cycle'),
                  ({'parent':{'type':'Scope','actions':{'child':{'type':'Compose','runAfter':{'outside':['Succeeded']}}}},'outside':{'type':'Compose'}},'non_sibling_dependency')]
        for actions, code in fixtures:
            with self.subTest(code=code): self.assertIn(code,self.codes(definition(actions)))

    def test_all_nested_branch_types(self):
        for action in [ {'type':'If','expression':True,'actions':{},'else':{'actions':{'bad':{'type':'Compose','runAfter':{'missing':['Failed']}}}}},
                        {'type':'Switch','expression':'x','cases':{'x':{'case':'x','actions':{'bad':{'type':'Compose','runAfter':{'missing':['Failed']}}}}},'default':{'actions':{}}},
                        {'type':'Until','expression':True,'actions':{'bad':{'type':'Compose','runAfter':{'missing':['TimedOut']}}}}]:
            self.assertIn('non_sibling_dependency',self.codes(definition({'branch':action})))

    def test_literal_payload_not_executable_or_parameter_call(self):
        raw=definition({'one':{'type':'Compose','inputs':{'type':'Scope','actions':{'invalid':None},'example':"parameters('absent')"}},'two':{'type':'Compose','inputs':"@concat('parameters(''literal'')', 'ok')"}})
        self.assertEqual(self.codes(raw),set())
        raw['actions']['two']['inputs']="@parameters('absent')"
        self.assertIn('undeclared_parameter',self.codes(raw))
        raw['parameters']={'absent':{'type':'String'}}
        self.assertEqual(self.codes(raw),set())

    def test_interpolation_checks_only_executable_segments(self):
        literal = ["@{triggerBody()?['name']} parameters('example')",
                   "text parameters('example') @{triggerBody()?['name']}",
                   "@@{parameters('example')}",
                   "@{concat('}', 'parameters(''example'')')} suffix",
                   "@concat('@{parameters(''example'')}', 'ok')"]
        for value in literal:
            with self.subTest(value=value):
                self.assertEqual(self.codes(definition({'one':{'type':'Compose','inputs':value}})),set())
        for value in ["prefix @{parameters('missing')} suffix",
                      "@{triggerBody()} @{parameters('missing')}",
                      "@@literal @{parameters('missing')}",
                      "@{concat('}', parameters('missing'))}"]:
            with self.subTest(value=value):
                self.assertIn('undeclared_parameter',self.codes(definition({'one':{'type':'Compose','inputs':value}})))

    def test_trigger_conditions_require_declared_parameters(self):
        raw=definition()
        raw['triggers']['manual']['conditions']=[{'expression':"@equals(parameters('CaptureEnabled'), true)"}]
        self.assertIn('undeclared_parameter',self.codes(raw))
        raw['parameters']={'CaptureEnabled':{'type':'Bool'}}
        self.assertEqual(self.codes(raw),set())

    def test_binding_resolution_and_redaction(self):
        data={'properties':{'definition':definition({'secret-label':{'type':'OpenApiConnection','inputs':{'host':{'connectionName':'unbound'},'parameters':{'private':'private-value'}}}}),'connectionReferences':{}}}
        result=v.validate_flow(data)
        self.assertIn('unbound_connector_host',self.codes(data))
        self.assertNotIn('secret-label',json.dumps(result)); self.assertNotIn('private-value',json.dumps(result))

    def test_duplicate_json_and_nonfinite_rejected(self):
        for raw in ['{"x":1,"x":2}', '{"a":{"x":1,"x":2}}','{"x":NaN}','{"x":Infinity}']:
            with self.assertRaises(ValueError): v.loads(raw)

    def test_malformed_graphs_do_not_pass(self):
        for raw in [None,[],{'properties':[]},definition({'x':None}),definition({'x':{'type':'Scope','actions':[]}}),definition({'x':{'type':'If','actions':{},'else':[]}})]:
            self.assertEqual(v.validate_flow(raw)['status'],'FAIL')

    def test_external_dependency_drift_and_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'script.ts').write_text('fictional')
            entry={'role':'office-script','path':'script.ts','sha256':v.hashlib.sha256(b'fictional').hexdigest()}
            self.assertEqual(v.dependency_checks([entry],root)[0]['outcome'],'pass')
            (root/'script.ts').write_text('changed')
            self.assertEqual(v.dependency_checks([entry],root)[0]['outcome'],'fail')
            entry['path']='../escape'
            self.assertEqual(v.dependency_checks([entry],root)[0]['outcome'],'fail')

    def test_package_membership_and_customization(self):
        identity='00000000-0000-4000-8000-000000000001'
        name=f'Workflows/Fictional-{identity}.json'
        members={'solution.xml':f'<ImportExportXml><SolutionManifest><RootComponents><RootComponent type="29" id="{{{identity}}}"/></RootComponents></SolutionManifest></ImportExportXml>',
                 'customizations.xml':f'<ImportExportXml><Workflows><Workflow WorkflowId="{{{identity}}}"/></Workflows></ImportExportXml>',name:json.dumps({'properties':{'definition':definition(),'connectionReferences':{}}})}
        self.assertEqual(v.validate_members(members)['status'],'PASS')
        members['customizations.xml']=members['customizations.xml'].replace(identity,'00000000-0000-4000-8000-000000000002')
        self.assertEqual(v.validate_members(members)['status'],'FAIL')
        del members[name]
        self.assertEqual(v.validate_members(members)['status'],'FAIL')

    def test_scaffold_is_not_deployment(self):
        result=v.validate_members({'solution.xml':'<Root/>','customizations.xml':'<Root/>'})
        self.assertEqual(result['status'],'PASS'); self.assertFalse(result['deploymentReady'])
        self.assertIn('empty_scaffold_not_deployable',{c['check'] for c in result['checks']})

    def test_deployment_settings_completeness(self):
        members={'customizations.xml':'<Root><connectionreference connectionreferencelogicalname="test_sp"/><environmentvariabledefinition schemaname="test_site"/></Root>'}
        valid={'ConnectionReferences':[{'LogicalName':'test_sp','ConnectionId':'fictional-connection'}],'EnvironmentVariables':[{'SchemaName':'test_site','Value':'fictional-site'}]}
        self.assertFalse(any(c['outcome']=='fail' for c in v.deployment_settings_checks(valid,members)))
        valid['ConnectionReferences'][0]['ConnectionId']=''
        self.assertTrue(any(c['check']=='deployment_settings_value_missing' for c in v.deployment_settings_checks(valid,members)))
        self.assertTrue(any(c['outcome']=='fail' for c in v.deployment_settings_checks({},members)))

    def test_profile_hash_drift_refused(self):
        from unittest.mock import patch
        with patch.object(v,'PROFILE_SHA256','incorrect'):
            self.assertEqual(v.validate_flow(definition())['status'],'FAIL')

    def test_null_reference_envelope_fails_and_map_handles_direct_bindings(self):
        value={'properties':{'definition':definition(),'connectionReferences':None}}
        self.assertEqual(v.validate_flow(value)['status'],'FAIL')
        value['properties']['connectionReferences']={'sp':{'connection':'opaque-direct-reference'}}
        self.assertIsNone(v.component_map(value)['connectionReferences'][0]['logicalName'])
