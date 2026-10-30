import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_product_installation import bind_document_generation
from ppg_installation_paths import bind_catalogue_inputs
import test_native_package_flow as native_tests

class CommissioningTests(unittest.TestCase):
 def fixture(self):
  flow,b=native_tests.NativeFlowTests().fixture();b['fullReview']={'enginePin':copy.deepcopy(b['enginePin']),'scriptGraphId':'full'};b['caseIntake']={'enginePin':copy.deepcopy(b['enginePin']),'scriptGraphId':'intake','reviewQueueListId':'33333333-3333-4333-8333-333333333333','catalogueListId':'44444444-4444-4444-8444-444444444444'};b['savedBodyFinalisation']=True
  s={'site':b['site'],'objects':{'review-evidence':{'id':b['libraryId'],'path':b['folder']},'review-queue':{'id':b['caseIntake']['reviewQueueListId']},'catalogue':{'id':b['caseIntake']['catalogueListId']}}}
  return flow,b,s
 def test_saved_body_is_bound_without_replacing_legacy_default(self):
  f,b,s=self.fixture();out=bind_document_generation(f,b,s);self.assertIn('Finalise_saved_body',out['properties']['definition']['actions']);self.assertEqual(out['properties']['state'],'Stopped');self.assertEqual(f['properties']['definition']['actions'],{})
 def test_cross_destination_inputs_and_legacy_body_refused(self):
  for change in ['site','folder','libraryId','catalogueListId','reviewQueueListId','savedBodyFinalisation']:
   f,b,s=self.fixture()
   if change in b['caseIntake']:b['caseIntake'][change]='55555555-5555-4555-8555-555555555555'
   else:b[change]=False if change=='savedBodyFinalisation' else 'wrong'
   with self.assertRaises(ValueError):bind_document_generation(f,b,s)
 def test_explicit_fixture_scope_preserves_unknown_identity_checks(self):
  a=lambda uri:{'inputs':{'parameters':{'parameters/uri':uri}}}
  d={'actions':{'Read_current':a('items?$top=2000'),'Scope':{'actions':{'Read_current_after':a('items?$top=2000')}},'Read_identity_application':a('/Evidence/identity-application.json'),'Other':a('items?$top=2000')}}
  uid='10000000-0000-4000-8000-000000000001';out=bind_catalogue_inputs(d,'reviewed-decisions.json',[uid]);self.assertIn("DocumentUID ne '"+uid+"'",str(out['actions']['Read_current']));self.assertEqual(out['actions']['Other'],d['actions']['Other']);self.assertIn('reviewed-decisions.json',str(out));self.assertNotIn('$filter',str(d))
  for filename,ids in [('../bad.json',[]),('ok.json',['bad']),('ok.json',[uid,uid])]:
   with self.assertRaises(ValueError):bind_catalogue_inputs(d,filename,ids)
  with self.assertRaises(ValueError):bind_catalogue_inputs(out,'reviewed-decisions.json',[uid])
