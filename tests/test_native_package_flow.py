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
 def test_full_route_keeps_legacy_engine_and_pin_fingerprint(self):
  import copy
  old,b=self.fixture();legacy=build_flow(old,b)['properties']['definition']['actions'];fullpin=copy.deepcopy(b['enginePin']);fullpin['UniqueId']='33333333-3333-4333-8333-333333333333'
  b['fullReview']={'enginePin':fullpin,'scriptGraphId':'fictional-full-script'}
  x=build_flow(old,b);a=x['properties']['definition']['actions']
  self.assertEqual(a['Pin_sets']['inputs']['legacy'],legacy['Input_pins']['inputs'])
  self.assertEqual(a['Receipt_shapes']['inputs']['legacy'],legacy['Expected_receipt']['inputs'])
  self.assertEqual(len(a['Pin_sets']['inputs']['full']),8)
  self.assertEqual('fictional-full-script',a['Select_document_script']['actions']['Run_full_review_script']['inputs']['parameters']['scriptId'])
  self.assertEqual('fictional-script',a['Select_document_script']['else']['actions']['Run_existing_cover_script']['inputs']['parameters']['scriptId'])
  for suffix in ['','_before_write','_before_receipt']:
   self.assertIn(fullpin['UniqueId'],a['Read_engine_pin'+suffix]['inputs']['parameters']['parameters/uri'])
   self.assertIn('Read_full_input_pin'+suffix,a)
  # Every top-level dependency resolves; no cycle was introduced by insertion.
  visited=set()
  def visit(name,stack):
   self.assertNotIn(name,stack);self.assertIn(name,a)
   if name in visited:return
   for prev in a[name].get('runAfter',{}):visit(prev,stack+[name])
   visited.add(name)
  for name in a:visit(name,[])
  self.assertEqual(a['Request_ID'],legacy['Request_ID'])
  self.assertEqual(a['Ensure_cover'],legacy['Ensure_cover'])
  self.assertEqual(a['Require_unchanged_outputs'],legacy['Require_unchanged_outputs'])

 def test_case_intake_is_explicit_read_only_and_rechecked_before_writers(self):
  import copy
  old,b=self.fixture();b['fullReview']={'enginePin':copy.deepcopy(b['enginePin']),'scriptGraphId':'full'}
  before=build_flow(old,b)['properties']['definition']['actions']
  b['caseIntake']={'enginePin':copy.deepcopy(b['enginePin']),'scriptGraphId':'intake','reviewQueueListId':'33333333-3333-4333-8333-333333333333','catalogueListId':'44444444-4444-4444-8444-444444444444'}
  a=build_flow(old,b)['properties']['definition']['actions']
  for key in ['Request_ID','Ensure_cover','Ensure_pack','Require_unchanged_outputs','Require_saved_bytes']:
   self.assertEqual(a[key],before[key])
  for suffix in ['','_before_write','_before_receipt']:
   sets=a['Intake_pin_sets'+suffix]['inputs'];self.assertEqual(len(sets['extra']),2)
   self.assertEqual(a['Pin_sets'+suffix]['inputs'],before['Pin_sets'+suffix]['inputs'])
  for suffix in ['_before_write','_before_receipt']:
   self.assertIn('Intake_unchanged'+suffix,a['Recheck_case_intake'+suffix]['actions'])
  for name,action in self.actions(a['Read_case_intake']['actions']):
   if action.get('type')=='OpenApiConnection':
    p=action['inputs']['parameters']
    self.assertIn(action['inputs']['host']['operationId'],['HttpRequest','GetFileContentByPath'])
    if 'parameters/method'in p:self.assertEqual(p['parameters/method'],'GET')
  visited=set()
  def visit(name,stack):
   self.assertNotIn(name,stack);self.assertIn(name,a)
   if name in visited:return
   for prev in a[name].get('runAfter',{}):visit(prev,stack+[name])
   visited.add(name)
  for name in a:visit(name,[])

if __name__=='__main__':unittest.main()
