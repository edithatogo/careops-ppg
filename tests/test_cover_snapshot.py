import sys,unittest,json,subprocess,io,zipfile,base64,hashlib
from xml.etree import ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_cover_snapshot import compile_cover,inspect_snapshot
from test_sharepoint_cover import fixture

class SnapshotTests(unittest.TestCase):
 def execute(self,manifest):
  result=subprocess.run(['node','-e',"const fs=require('fs'),vm=require('vm'),{stripTypeScriptTypes}=require('node:module');const c={};vm.createContext(c);vm.runInContext(stripTypeScriptTypes(fs.readFileSync('scripts/ppg_cloud_package.ts','utf8')),c);try {process.stdout.write(JSON.stringify(c.coverBytes(fs.readFileSync(0,'utf8'))));}catch(e){console.error(e.message);process.exit(1)}"],input=json.dumps(manifest),text=True,capture_output=True)
  return result
 def prepare(self):
  raw,values=fixture(False);source=zipfile.ZipFile(io.BytesIO(raw));out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:
   for n in source.namelist():
    data=source.read(n)
    if n=='word/document.xml':data=data.replace(b'<w:body>',b'<w:body><w:p><w:r><w:t>DRAFT</w:t></w:r></w:p>')
    if n=='customXml/item1.xml':
     props=ET.fromstring(data)
     for node in props.find('documentManagement'):node.text=None
     data=ET.tostring(props)
    z.writestr(n,data)
   z.writestr('[Content_Types].xml','<Types/>');z.writestr('_rels/.rels','<Relationships/>')
  values['PPGCoverTitle']='Māori café < & > '+ 'long '*30
  return out.getvalue(),values
 def test_persisted_unicode_and_detached_snapshot(self):
  raw,values=self.prepare();manifest=compile_cover(raw,values);r=self.execute(manifest);self.assertEqual(r.returncode,0,r.stderr)
  generated=bytes(json.loads(r.stdout));report=inspect_snapshot(generated,values)
  self.assertTrue(report['packageEligible']);self.assertEqual(self.execute(manifest).stdout,r.stdout)
  with zipfile.ZipFile(io.BytesIO(raw)) as source,zipfile.ZipFile(io.BytesIO(generated)) as output:
   self.assertEqual(output.testzip(),None)
   for name in source.namelist():
    if name!='word/document.xml':self.assertEqual(source.read(name),output.read(name))
 def test_native_envelope_packages_exact_snapshot_and_evidence(self):
  raw,values=self.prepare();manifest=compile_cover(raw,values);cover=bytes(json.loads(self.execute(manifest).stdout));h=lambda b:hashlib.sha256(b).hexdigest()
  cj=json.dumps(manifest);values['PPGCoverCaseUID']=manifest['values']['PPGCoverCaseUID'];evidence=b'UNCHANGED evidence \x00\xff'
  job={'schemaVersion':1,'jobId':'job-cover-test','documentKind':'fictional-cover-pack','CaseUID':values['PPGCoverCaseUID'],'sourceSnapshotRef':'fictional-v1','sourceSHA256':h(evidence),'templateVersion':'cover-v1','templateSHA256':h(raw),'outputRevision':values['PPGCoverOutputRevision'],'includedRecordIDs':['fictional-doc'],'createdAtUtc':'2026-10-19T00:00:00Z','coverSnapshot':{'route':'standard-office-script-fixed-cover-v1','manifestSHA256':h(cj.encode()),'templateSHA256':h(raw),'path':'cover.docx'},'members':[{'path':n,'sha256':h(b),'size':len(b),'sourceReference':'fictional://source','sourceVersionRef':'v1'} for n,b in [('cover.docx',cover),('evidence.bin',evidence)]]}
  payload={'jobJson':json.dumps({'kind':'standard-cover-input-v1','jobJson':json.dumps(job),'coverJson':cj}),'membersJson':json.dumps([{'path':'evidence.bin','base64':base64.b64encode(evidence).decode()}])}
  code="const fs=require('fs'),vm=require('vm'),{stripTypeScriptTypes}=require('node:module');const c={};vm.createContext(c);vm.runInContext(stripTypeScriptTypes(fs.readFileSync('scripts/ppg_cloud_package.ts','utf8')),c);const p=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(c.main(null,p.jobJson,p.membersJson)));"
  r=subprocess.run(['node','-e',code],input=json.dumps(payload),text=True,capture_output=True);self.assertEqual(r.returncode,0,r.stderr);result=json.loads(r.stdout)
  self.assertTrue(result['wordGenerationPerformed']);self.assertEqual(result['coverSHA256'],h(cover))
  with zipfile.ZipFile(io.BytesIO(base64.b64decode(result['zipBase64']))) as z:
   self.assertIsNone(z.testzip());self.assertEqual(z.read('cover.docx'),cover);self.assertEqual(z.read('evidence.bin'),evidence)
  job['members'][0]['sha256']='0'*64;payload['jobJson']=json.dumps({'kind':'standard-cover-input-v1','jobJson':json.dumps(job),'coverJson':cj});r=subprocess.run(['node','-e',code],input=json.dumps(payload),text=True,capture_output=True);self.assertNotEqual(r.returncode,0)
 def test_changed_template_and_invalid_date_refused(self):
  raw,values=self.prepare();manifest=compile_cover(raw,values);manifest['parts'][0]['sha256']='0'*64
  self.assertNotEqual(self.execute(manifest).returncode,0)
  manifest=compile_cover(raw,values);manifest['values']['PPGCoverReviewDate']='2026-02-30'
  self.assertNotEqual(self.execute(manifest).returncode,0)
 def test_populated_hidden_properties_cannot_be_used_as_blank_template(self):
  raw,values=fixture(False)
  with self.assertRaisesRegex(ValueError,'blank_template_properties_required'):compile_cover(raw,values)
 def test_human_output_cannot_be_used_as_template(self):
  raw,values=self.prepare();m=compile_cover(raw,values);r=self.execute(m)
  with self.assertRaises(ValueError):compile_cover(bytes(json.loads(r.stdout)),values)

if __name__=='__main__':unittest.main()
