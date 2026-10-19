import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_native_package_flow import build_flow

class NativeFlowTests(unittest.TestCase):
 def fixture(self):
  refs={k:{'id':'/providers/Microsoft.PowerApps/apis/'+k,'connectionName':'fictional-'+k,'source':'Invoker'} for k in ['shared_sharepointonline','shared_excelonlinebusiness']}
  old={'properties':{'definition':{'actions':{},'triggers':{},'parameters':{}},'connectionReferences':refs,'displayName':'Fictional'}}
  pin={'UniqueId':'11111111-1111-4111-8111-111111111111','ETag':'"1"','Length':'100','UIVersionLabel':'1.0','ServerRelativeUrl':'/sites/fictional/Evidence/kernel.osts'}
  binding={'site':'https://example.sharepoint.com/sites/fictional','sitePath':'/sites/fictional','folder':'/sites/fictional/Evidence/Packages','libraryId':'22222222-2222-4222-8222-222222222222','requestItemId':7,'enginePin':pin,'scriptGraphId':'fictional-script','runScriptAction':{'type':'OpenApiConnection','inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_excelonlinebusiness','connectionName':'shared_excelonlinebusiness','operationId':'RunScriptProdV2'},'parameters':{}}}}
  return old,binding
 def actions(self,group):
  for name,a in group.items():
   yield name,a
   yield from self.actions(a.get('actions',{}));yield from self.actions(a.get('else',{}).get('actions',{}))
 def test_native_intake_and_no_source_writers(self):
  old,b=self.fixture();x=build_flow(old,b);d=x['properties']['definition'];self.assertEqual(d['triggers']['manual']['runtimeConfiguration']['concurrency']['runs'],1)
  self.assertEqual(d['triggers']['manual']['inputs']['schema']['properties']['requestItemId']['type'],'string');self.assertIn('empty(trim',d['actions']['Request_ID']['inputs']);self.assertEqual(x['properties']['state'],'Stopped');self.assertEqual(old['properties']['definition']['actions'],{})
  actions=dict(self.actions(d['actions']));script=actions['Run_script_from_SharePoint_library']['inputs']['parameters'];self.assertEqual(set(k for k in script if k.startswith('ScriptParameters/')),{'ScriptParameters/jobJson','ScriptParameters/membersJson'})
  self.assertIn('Native_request',script['ScriptParameters/jobJson']);self.assertNotIn('expectedSHA256',script)
  for name,a in actions.items():
   inputs=a.get('inputs',{})
   if not isinstance(inputs,dict):continue
   host=inputs.get('host',{});op=host.get('operationId');p=inputs.get('parameters',{})
   self.assertNotIn(op,['UpdateFile','PatchItem','PostItem','DeleteFile','DeleteItem'])
   if op=='HttpRequest' and p.get('parameters/method')!='GET':
    self.assertIn('overwrite=false',p['parameters/uri']);self.assertEqual(inputs['retryPolicy'],{'type':'none'})
   if op=='MoveFileAsync':self.assertEqual(p['parameters/nameConflictBehavior'],0)
  self.assertIn('existing-frozen-package',str(actions['Expected_receipt']['inputs']))
 def test_stage_uses_bound_folder_and_critical_guards(self):
  old,b=self.fixture();a=build_flow(old,b)['properties']['definition']['actions'];stage=a['Ensure_cover']['actions']['Create_cover']['inputs']['parameters']['folderPath'];self.assertTrue(stage.startswith('/Evidence/Packages/'))
  for name in ['Require_claim_readable','Require_unchanged_outputs','Require_pins_before_write','Require_pins_before_receipt','Require_saved_bytes','Require_saved_claim','Require_final_pair']:self.assertIn(name,a)
  self.assertIn('Read_claim',str(a['Native_request']));self.assertIn('existingClaimJson',str(a['Native_request']));self.assertIn('utcNow',str(a['Native_request']))
 def test_pdf_failure_is_separate_and_replay_checks_saved_identity(self):
  old,b=self.fixture();b['pdfConnection']={'id':'/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness','connectionName':'fictional-existing','source':'Embedded'}
  x=build_flow(old,b);a=x['properties']['definition']['actions'];pdf=a['Optional_PDF'];self.assertEqual(pdf['runAfter'],{'Core_complete':['Succeeded']})
  self.assertEqual(a['PDF_outcome']['runAfter'],{'Optional_PDF':['Succeeded','Failed','TimedOut']})
  branch=pdf['actions']['Create_or_reuse_PDF'];fresh=branch['actions'];reuse=branch['else']['actions']
  self.assertEqual(fresh['Convert_cover']['inputs']['retryPolicy']['count'],2)
  self.assertIn('overwrite=false',fresh['Commit_PDF_receipt']['inputs']['parameters']['parameters/uri'])
  self.assertIn('PPG_PDF_EDITED_OR_INPUT_CHANGED',str(reuse))
  self.assertNotIn('CreateFile',str(reuse));self.assertNotIn('ConvertFile',str(reuse))
  self.assertIn('overwrite=false',str(a['Record_PDF_failure']));self.assertNotIn('Terminate',str(pdf));self.assertIn('Request_property_pin',str(a['Require_pins_before_write']))
  self.assertNotIn('odata.id',str(a['Request_property_pin']))
 def test_unsafe_binding_refused(self):
  old,b=self.fixture();b['folder']='/sites/fictional/../escape'
  with self.assertRaises(ValueError):build_flow(old,b)

if __name__=='__main__':unittest.main()
