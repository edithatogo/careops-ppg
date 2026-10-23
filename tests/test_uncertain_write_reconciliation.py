"""Incomplete or misattributed recovery evidence must never confirm a write."""
import copy
import hashlib
import unittest
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from reconcile_uncertain_write import classify


def fixture():
    before={'CaseUID':'LC-FICTIONAL-TEST','nextAction':'Before'}
    after={**before,'nextAction':'After','Id':1,'GUID':'native-row','Title':'Retained','evidenceDraftLink':'retained-link','OData__UIVersionString':'2.0'}
    expected={'CaseUID':before['CaseUID'],'before':before,'expectedCaseETag':'"old"','desiredNextAction':'After','sourceETag':'"source"','sourceSHA256':hashlib.sha256(b'source').hexdigest()}
    resource='/providers/test/environments/e/flows/f/runs/run1'
    return {'binding':{'qualificationOnly':True,'expectedRequest':expected,'caseItemId':1,'siteUrl':'https://example.invalid','caseUri':'items(1)','sourceUniqueId':'source'},
        'journal':{'request':copy.deepcopy(expected),'before':copy.deepcopy(before),'beforeETag':'"old"','preparedByRun':'run1'},
        'run':{'name':'run1','id':resource,'properties':{'status':'Succeeded'}},
        'action':{'name':'Conditional_case_write','runName':'run1','id':resource+'/actions/Conditional_case_write','properties':{'status':'Succeeded'}},
        'inputs':{'parameters':{'dataset':'https://example.invalid','parameters/uri':'items(1)','parameters/method':'POST','parameters/headers':{'X-HTTP-Method':'MERGE','IF-MATCH':'"old"'},'parameters/body':{'nextAction':'After'}}},
        'response':{'statusCode':204,'headers':{'ETag':'"new"'}},
        'observation':{'body':copy.deepcopy(after),'headers':{'ETag':'"new"'}},'current':copy.deepcopy(after),
        'history':{'value':[{**after,'IsCurrentVersion':True,'VersionLabel':'2.0','VersionId':2},{**after,**before,'IsCurrentVersion':False,'VersionLabel':'1.0','VersionId':1}]},
        'source':{'UniqueId':'source','ETag':'"source"'},'source_bytes':b'source'}


class ReconciliationTests(unittest.TestCase):
    def test_native_version_id_alias_preserves_exact_bound_identity(self):
        args=fixture()
        for before in [args['binding']['expectedRequest']['before'],
                       args['journal']['before'], args['journal']['request']['before']]:
            before['Id']=1
        for version in args['history']['value']:
            version['ID']=version.pop('Id')
        prior=copy.deepcopy(args)
        self.assertEqual(classify(**args)['classification'],'committed-no-resubmit')
        self.assertEqual(args,prior)
        for conflicting in [False,True]:
            changed=copy.deepcopy(args)
            changed['history']['value'][0]['ID']=2
            if conflicting:changed['history']['value'][0]['Id']=1
            result=classify(**changed)
            self.assertEqual(result['classification'],'held')
            self.assertIn('version-item-identity-mismatch',result['reasons'])

    def test_complete_attributable_write_is_committed_without_resubmission(self):
        args=fixture();prior=copy.deepcopy(args);result=classify(**args)
        self.assertEqual(result['classification'],'committed-no-resubmit')
        self.assertFalse(result['resubmitAllowed']);self.assertEqual(result['nativeWrites'],0)
        self.assertEqual(args,prior)

    def test_only_explicit_terminal_run_statuses_are_accepted(self):
        for status in ['Running','Waiting','Queued','Suspended','Unknown',None,'']:
            args=fixture();args['run']['properties']['status']=status
            result=classify(**args)
            self.assertEqual(result['classification'],'held',status)
            self.assertIn('run-not-terminal',result['reasons'])
        for status in ['Succeeded','Failed','Cancelled','Canceled','TimedOut']:
            args=fixture();args['run']['properties']['status']=status
            self.assertEqual(classify(**args)['classification'],'committed-no-resubmit')

    def test_exact_run_and_action_identity_required(self):
        for key,value in [('id','/other/runs/run1/actions/Conditional_case_write'),('id',fixture()['action']['id']+'-other'),('name','Other'),('runName','other')]:
            args=fixture();args['action'][key]=value
            self.assertIn('wrong-native-action',classify(**args)['reasons'])
        args=fixture();args['run']['id']+='/other'
        self.assertIn('wrong-native-action',classify(**args)['reasons'])

    def test_all_native_continuation_forms_hold_even_with_matching_visible_versions(self):
        for key in ['nextLink','@nextLink','odata.nextLink','@odata.nextLink','__next']:
            for nested in [False,True]:
                args=fixture()
                if nested:args['history']={'d':{'results':args['history']['value'],key:'https://example.invalid/next'}}
                else:args['history'][key]='https://example.invalid/next'
                result=classify(**args)
                self.assertEqual(result['classification'],'held')
                self.assertIn('incomplete-native-history',result['reasons'])


class ReconciliationOutputTests(unittest.TestCase):
    def test_cli_creates_a_new_result_and_refuses_existing_evidence_or_results(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);bundle={}
            for key,value in fixture().items():
                path=directory/(key+'.bin' if key=='source_bytes' else key+'.json')
                path.write_bytes(value if key=='source_bytes' else json.dumps(value).encode())
                bundle[key]=str(path)
            config=directory/'bundle.json';config.write_text(json.dumps(bundle))
            command=[sys.executable,str(Path(__file__).resolve().parents[1]/'tools/lifecycle/reconcile_uncertain_write.py'),'--bundle',str(config),'--output']
            result=directory/'result.json'
            first=subprocess.run(command+[str(result)],capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertEqual(json.loads(result.read_text())['classification'],'committed-no-resubmit')
            for target in [result,config,Path(bundle['journal']),Path(bundle['current'])]:
                original=target.read_bytes()
                refused=subprocess.run(command+[str(target)],capture_output=True,text=True)
                self.assertNotEqual(refused.returncode,0)
                self.assertEqual(target.read_bytes(),original)
