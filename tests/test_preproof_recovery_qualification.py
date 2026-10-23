"""New isolated fixtures reuse LC02 journals/classifier, never repeat a write."""
import copy
import hashlib
import json
import unittest
from build_recovery_qualification import build
from build_operator_entry import _flatten
from build_selected_event_routes import audit_actions
from test_prepared_closure_check import Expressions


def fixture(legacy=False):
    site='https://example.sharepoint.com/site'
    uri="_api/web/lists(guid'00000000-0000-4000-8000-000000000001')/items(2)"
    source='FICTIONAL recovery source'
    expected={'CaseUID':'LC-FICTIONAL-WB05-01','requestId':'LC02-RECOVERY-WB05-01',
        'caseItemId':2,'sourceUniqueId':'00000000-0000-4000-8000-000000000002',
        'expectedCaseETag':'"before"','sourceETag':'"source"',
        'sourceSHA256':hashlib.sha256(source.encode()).hexdigest(),
        'before':{'CaseUID':'LC-FICTIONAL-WB05-01','nextAction':'FICTIONAL before'},
        'desiredNextAction':'FICTIONAL after'}
    reference={'name':'00000000-0000-4000-8000-000000000003','properties':{'state':'Stopped',
        'connectionReferences':{'shared_sharepointonline':{'connectionName':'fictional-existing'}},
        'definition':{'triggers':{'manual':{'type':'Request','kind':'Button',
            'runtimeConfiguration':{'concurrency':{'runs':1}}}},'actions':{'Read_case':{
                'type':'OpenApiConnection','inputs':{'parameters':{'dataset':site,
                    'parameters/uri':uri,'parameters/method':'GET'}},'runAfter':{}}}}}}
    binding={'qualificationOnly':True,'siteUrl':site,'caseUri':uri,'caseItemId':2,
        'sourceUniqueId':expected['sourceUniqueId'],'expectedRequest':expected,
        'isolatedFixture':True,'referenceFlowName':reference['name'],
        'approvedReferenceDefinitionSHA256':hashlib.sha256(json.dumps(reference['properties']['definition'],sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    if legacy:
        expected.update(CaseUID='LC-FICTIONAL-20261017-01',requestId='LC02-RECOVERY-20261018-01')
        expected['before']['CaseUID']=expected['CaseUID']
        for key in ['isolatedFixture','referenceFlowName','approvedReferenceDefinitionSHA256']:binding.pop(key)
    return expected,reference,source,binding


class PreproofRecoveryQualificationTests(unittest.TestCase):
    def test_fault_after_merge_prevents_after_observation_or_proof_and_keeps_writers(self):
        expected,reference,source,binding=fixture();before=copy.deepcopy((expected,reference,binding))
        fault=build(expected,reference,source,False,binding,preproof_fault=True)
        clean=build(expected,reference,source,False,binding)
        self.assertEqual((expected,reference,binding),before)
        nodes=_flatten(fault['properties']['definition']['actions']);normal=_flatten(clean['properties']['definition']['actions'])
        self.assertEqual(nodes['Preproof_intentional_stop']['runAfter'],{'Conditional_case_write':['Succeeded']})
        self.assertEqual(nodes['Preproof_intentional_stop']['type'],'Terminate')
        self.assertEqual(nodes['Read_after_write']['runAfter'],{'Preproof_intentional_stop':['Succeeded']})
        writers=lambda graph:{n:a for n,a in graph.items() if a.get('type')=='OpenApiConnection'
            and a['inputs']['parameters']['parameters/method']!='GET'}
        self.assertEqual(writers(nodes),writers(normal))
        self.assertEqual(set(writers(nodes)),{'Write_journal','Conditional_case_write','Write_after_proof','Commit_receipt'})
        for action in writers(nodes).values():self.assertEqual(action['inputs']['retryPolicy'],{'type':'none'})
        params=nodes['Conditional_case_write']['inputs']['parameters']
        self.assertEqual(json.loads(params['parameters/body']),{'nextAction':expected['desiredNextAction']})
        self.assertEqual(params['parameters/headers']['IF-MATCH'],expected['expectedCaseETag'])
        self.assertEqual(fault['properties']['state'],'Stopped')
        self.assertLessEqual(audit_actions(fault['properties']['definition'])['maximumActionDepth'],8)

    def test_changed_etag_after_fault_skips_mutation_in_clean_replay(self):
        expected,reference,source,binding=fixture();nodes=_flatten(build(expected,reference,source,False,binding)['properties']['definition']['actions'])
        outputs={'Expected_request':expected,'Observed_before':expected['before'],'Read_case':{'headers':{'ETag':expected['expectedCaseETag']}}}
        expression=nodes['Mutate_only_before']['expression']
        self.assertTrue(Expressions(outputs=outputs).evaluate(expression))
        outputs['Read_case']['headers']['ETag']='"after"'
        outputs['Observed_before']={**expected['before'],'nextAction':expected['desiredNextAction']}
        self.assertFalse(Expressions(outputs=outputs).evaluate(expression))
        self.assertEqual(nodes['Mutate_only_before']['else']['actions'],{})
        self.assertEqual(nodes['Read_after_proof']['runAfter'],{'Mutate_only_before':['Succeeded']})
        self.assertNotIn('Conditional_case_write',_flatten(nodes['Verify_recovery']['actions']))
        self.assertNotIn('Write_after_proof',_flatten(nodes['Verify_recovery']['actions']))

    def test_unique_fixture_paths_do_not_touch_legacy_control_or_evidence(self):
        expected,reference,source,binding=fixture();nodes=_flatten(build(expected,reference,source,False,binding)['properties']['definition']['actions'])
        for name in ['Read_control','Write_journal','Read_journal','Read_after_proof','Write_after_proof','Commit_receipt']:
            uri=nodes[name]['inputs']['parameters']['parameters/uri']
            self.assertIn(expected['requestId'],uri)
            self.assertNotIn('/LC02-recovery-',uri)
        for changed in ['REAL-CASE','LC-FICTIONAL-20261017-01']:
            bad=copy.deepcopy(expected);bad['CaseUID']=changed;b=copy.deepcopy(binding);b['expectedRequest']=bad
            with self.assertRaises(ValueError):build(bad,reference,source,False,b,preproof_fault=True)

    def test_stale_reference_source_mismatch_and_ambiguous_fault_points_refuse(self):
        for mutate in [lambda e,r,b:r['properties'].update(state='Started'),
                       lambda e,r,b:b.update(approvedReferenceDefinitionSHA256='0'*64),
                       lambda e,r,b:b.update(referenceFlowName='other'),
                       lambda e,r,b:e.update(sourceSHA256='0'*64),
                       lambda e,r,b:b.update(caseUri="_api/web/lists(guid'00000000-0000-4000-8000-000000000099')/items(2)")]:
            e,r,s,b=fixture();mutate(e,r,b)
            with self.assertRaises(ValueError):build(e,r,s,False,b,preproof_fault=True)
        e,r,s,b=fixture()
        with self.assertRaises(ValueError):build(e,r,s,True,b,preproof_fault=True)
        e,r,s,b=fixture(True)
        with self.assertRaises(ValueError):build(e,r,s,False,b,preproof_fault=True)

    def test_legacy_control_and_afterproof_fault_contract_remain_unchanged(self):
        e,r,s,b=fixture(True);result=build(e,r,s,True,b);nodes=_flatten(result['properties']['definition']['actions'])
        self.assertNotIn('Preproof_intentional_stop',nodes)
        self.assertNotIn('state',result['properties'])
        self.assertIn('LC02-recovery-control.json',nodes['Read_control']['inputs']['parameters']['parameters/uri'])
        self.assertEqual(nodes['Fault_probe']['runAfter'],{'Write_after_proof':['Succeeded']})
        self.assertEqual(nodes['Fault_probe']['expression'],'@true')

    def test_cli_preserves_source_bytes_and_refuses_existing_inputs_or_candidates(self):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);e,r,s,b=fixture()
            s='FICTIONAL source\r\nretained line\r\n';e['sourceSHA256']=hashlib.sha256(s.encode()).hexdigest()
            inputs={'request':e,'reference-flow':r,'binding':b}
            command=[sys.executable,str(Path(__file__).resolve().parents[1]/'tools/lifecycle/build_recovery_qualification.py')]
            for key,value in inputs.items():
                path=root/(key+'.json');path.write_text(json.dumps(value));command += ['--'+key,str(path)]
            source=root/'source.txt';source.write_bytes(s.encode());command += ['--source-text',str(source),'--preproof-fault','--output']
            target=root/'candidate.json'
            first=subprocess.run(command+[str(target)],capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            candidate=json.loads(target.read_bytes());nodes=_flatten(candidate['properties']['definition']['actions'])
            self.assertIn(s,nodes['Source_guard']['expression'])
            for path in [target,source,root/'request.json',root/'binding.json',root/'reference-flow.json']:
                before=path.read_bytes();refused=subprocess.run(command+[str(path)],capture_output=True,text=True)
                self.assertNotEqual(refused.returncode,0)
                self.assertEqual(path.read_bytes(),before)
