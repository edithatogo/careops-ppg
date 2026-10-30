import json,tempfile,unittest
from pathlib import Path
from scripts.ppg_office_bindings import bind
from scripts.ppg_office_runtime import build
from scripts.ppg_installation_paths import bind_paths
class OfficeInstallation(unittest.TestCase):
 def test_nested_branches_preserve_inputs_and_identity(self):
  action={'type':'OpenApiConnection','inputs':{'host':{'operationId':'RunScriptProdV2'},'parameters':{'ScriptParameters/jobJson':'@original'}}}
  d={'actions':{'Compose':{'type':'Compose','inputs':'text'},'Choice':{'else':{'actions':{'Run_existing_cover_script':action}}}}};b=dict(source='s',drive='d',file='f',scriptSource='s',scriptDrive='d',scriptId='i')
  out,used=bind(d,{'cover':b});p=out['actions']['Choice']['else']['actions']['Run_existing_cover_script']['inputs']['parameters'];self.assertEqual(p,{**b,'ScriptParameters/jobJson':'@original'});self.assertEqual(used,['cover']);self.assertNotIn('file',action['inputs']['parameters'])
 def test_paths_rebind_complete_components_only(self):
  c={'objects':[{'key':'evidence','title':'PPG Review Evidence','baseTemplate':101}]};o={'evidence':{'path':'/sites/example/PPG Review Evidence - Isolated'}};site='https://example.sharepoint.com/sites/example';d={'folder':'/PPG Review Evidence','expression':"@concat('"+site+"/PPG Review Evidence/item')",'already':'/sites/example/PPG Review Evidence - Isolated/item'}
  out=bind_paths(d,site,o,c);self.assertEqual(out['folder'],'/PPG Review Evidence - Isolated');self.assertIn('Evidence - Isolated/item',out['expression']);self.assertEqual(out['already'],d['already']);self.assertEqual(bind_paths(out,site,o,c),out)
 def test_materialised_profiles_and_custom_source_identity(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'.local/assets';m=build(p,'fictional-source');self.assertEqual(len(m['profiles']),7);self.assertEqual(len(m['assets']),13);j=json.loads((p/'ppg-catalogue.osts').read_text());self.assertIn('ledger.sourceSystemId !== "fictional-source"',j['body']);self.assertNotIn('example-ppg-register',j['body'])
