"""Actual DOCX structure/schema checks for the native full-review kernel."""
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_full_document import compile_template, SCALARS, GROUPS, W


class FullDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.p = Path(cls.tmp.name)
        cls.dll = 'tools/native-document-template/bin/Debug/net10.0/TemplateBuilder.dll'
        subprocess.run(['dotnet', 'build', '--no-restore'], check=True, capture_output=True, cwd='tools/native-document-template')
        source = Path('templates/review-package.md')
        subprocess.run(['dotnet', 'exec', cls.dll, str(source), hashlib.sha256(source.read_bytes()).hexdigest(), str(cls.p/'template.docx')], check=True, capture_output=True)
        cls.raw = (cls.p/'template.docx').read_bytes()
        cls.template = compile_template(cls.raw)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def render(self, data):
        script = """const fs=require('node:fs'),vm=require('node:vm'),{stripTypeScriptTypes}=require('node:module');
const c={};vm.createContext(c);vm.runInContext(stripTypeScriptTypes(fs.readFileSync('scripts/ppg_cloud_package.ts','utf8')),c);
try {process.stdout.write(Buffer.from(c.fullDocumentBytes(fs.readFileSync(0,'utf8'))));} catch(e) {process.stderr.write(e.message);process.exit(1);}"""
        return subprocess.run(['node', '--disable-warning=ExperimentalWarning', '-e', script], input=json.dumps(data).encode(), capture_output=True)

    def values(self, count):
        v = {k: 'Unresolved — no human finding recorded' for k in SCALARS}
        v.update(case_title='Fictional Ω café 日本語 '+('long title ' * 20), CaseUID='fictional-case', source_snapshot='fictional-source', version='DRAFT-r1', documentKind='policy-review-package', sourceSHA256='a'*64, templateVersion='full-v1', outputRevision='r1', includedRecordIDs=['fictional-1'], OptionalContent='', source_manifest='First line\nhttps://example.org/evidence?x=1&y=2; version 2.0\n2026-10-20')
        v.update({k: [{f: f+' '+str(i)+' Ω\nsecond line' for f in fs} for i in range(count)] for k, fs in GROUPS.items()})
        return v

    def test_zero_one_many_and_preserved_parts(self):
        for count in [0, 1, 3, 50]:
            with self.subTest(count=count):
                v = self.values(count)
                result = self.render({'template': self.template, 'input': v})
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                output = self.p/f'output-{count}.docx'
                output.write_bytes(result.stdout)
                with zipfile.ZipFile(io.BytesIO(result.stdout)) as z, zipfile.ZipFile(io.BytesIO(self.raw)) as original:
                    self.assertIsNone(z.testzip())
                    self.assertEqual(z.namelist(), original.namelist())
                    for name in z.namelist():
                        if name != 'word/document.xml':
                            self.assertEqual(z.read(name), original.read(name))
                    xml = z.read('word/document.xml')
                    root = ET.fromstring(xml)
                    text = ''.join(root.itertext())
                    self.assertIn(v['case_title'], text)
                    self.assertIn('2026-10-20', text)
                    self.assertNotIn('PPG_VALUE:', text)
                    self.assertIn('DRAFT', text)
                    self.assertEqual(len(list(root.iter('{'+W+'}text'))),0)
                    self.assertGreater(len(list(root.iter('{'+W+'}richText'))),0)
                    self.assertEqual(sum(1 for x in root.iter('{'+W+'}tag') if x.get('{'+W+'}val') == 'ComparisonSource'), count)
                    ids = [x.get('{'+W+'}val') for x in root.iter('{'+W+'}id')]
                    self.assertEqual(len(ids), len(set(ids)))
                    links = list(root.iter('{'+W+'}fldSimple'))
                    self.assertEqual(len(links), 1)
                    self.assertIn('https://example.org/evidence?x=1&y=2', links[0].get('{'+W+'}instr'))
                    self.assertNotIn('y=2;', links[0].get('{'+W+'}instr'))
                check = subprocess.run(['dotnet','exec',self.dll,'validate-docx',str(output)], capture_output=True)
                self.assertEqual(check.returncode, 0, check.stdout.decode()+check.stderr.decode())

    def test_reject_invalid_shape_text_and_bounds(self):
        for mutate in [lambda v: v.update(consultation_rows=[{}]), lambda v: v.update(OptionalContent='bad\x00'), lambda v: v.update(comparison_rows=self.values(1)['comparison_rows']*51), lambda v: v.update(CaseUID=''), lambda v: v.update(extra='unsupported')]:
            v=self.values(1);mutate(v)
            self.assertNotEqual(self.render({'template':self.template,'input':v}).returncode,0)

    def test_reject_populated_template(self):
        with zipfile.ZipFile(io.BytesIO(self.raw)) as z:
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as changed:
                for name in z.namelist():
                    raw=z.read(name)
                    if name=='word/document.xml':raw=raw.replace(b'[CaseUID]',b'already populated')
                    changed.writestr(name,raw)
        with self.assertRaisesRegex(ValueError,'blank_full_template'):
            compile_template(out.getvalue())

    def test_native_full_request_replay_and_revision_guard(self):
        script = """const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto'),{stripTypeScriptTypes}=require('node:module');
const c={};vm.createContext(c);vm.runInContext(stripTypeScriptTypes(fs.readFileSync('scripts/ppg_cloud_package.ts','utf8')),c);
const data=JSON.parse(fs.readFileSync(0,'utf8')),h=b=>crypto.createHash('sha256').update(b).digest('hex');
const sourceJob={schemaVersion:1,jobId:'job-frozen-full-test',documentKind:'frozen-fictional',CaseUID:data.input.CaseUID,sourceSnapshotRef:'fictional-source',sourceSHA256:'a'.repeat(64),templateVersion:'source-v1',templateSHA256:'b'.repeat(64),outputRevision:'source-r1',includedRecordIDs:data.input.includedRecordIDs,createdAtUtc:'2026-10-20T00:00:00Z',members:[]};
const sourceJobJson=JSON.stringify(sourceJob),sourceResult=JSON.parse(c.packageJob(sourceJobJson,'[]')),source=Buffer.from(sourceResult.zipBase64,'base64');
data.input.sourceSHA256=h(source);const roles=['request','compiled-template','maintained-template','source-pack','source-job','source-receipt','engine','full-document-input'];
const pins=roles.map((role,i)=>({role,UniqueId:'fictional-'+i,ETag:'"1"',Length:'123',UIVersionLabel:'1.0',ServerRelativeUrl:'/fictional/'+role}));
const request={kind:'m365-full-review-request-v1',generationRunId:'fictional-run-1',requestItemId:7,createdAtUtc:'2026-10-20T01:00:00Z',existingClaimJson:'',templateVersion:data.input.templateVersion,template:data.template,values:{PPGCoverCaseUID:data.input.CaseUID,PPGCoverOutputRevision:data.input.outputRevision},fullDocumentInputJson:JSON.stringify(data.input),sourceJobJson,sourceReceiptJson:JSON.stringify({jobSHA256:sourceResult.jobSHA256,package:{sha256:h(source),UniqueId:'fictional-3',ETag:'"1"',Length:String(source.length)}}),sourcePin:{UniqueId:'fictional-3',ETag:'"1"',Length:String(source.length),ServerRelativeUrl:'/fictional/source.zip'},pinsJson:JSON.stringify(pins)};
const members=JSON.stringify([{path:'existing-pack.zip',base64:source.toString('base64')},{path:'maintained-template.docx',base64:data.raw}]),run=r=>c.main(null,JSON.stringify(r),members),first=run(request);
assert.equal(first.generationRoute,'standard-office-script-full-review-v1');assert.equal(first.wordGenerationPerformed,true);
request.existingClaimJson=first.claimJson;request.createdAtUtc='2026-10-20T02:00:00Z';request.generationRunId='fictional-run-2';assert.equal(JSON.stringify(run(request)),JSON.stringify(first));
data.input.case_title='Changed title';request.fullDocumentInputJson=JSON.stringify(data.input);assert.throws(()=>run(request),/new_revision/);
data.input.CaseUID='wrong-case';request.fullDocumentInputJson=JSON.stringify(data.input);assert.throws(()=>run(request),/identity_mismatch/);
console.log('Full native request, source binding, immutable replay and changed input guards pass');"""
        result=subprocess.run(['node','--disable-warning=ExperimentalWarning','-e',script],input=json.dumps({'template':self.template,'input':self.values(3),'raw':base64.b64encode(self.raw).decode()}).encode(),capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode())


if __name__ == '__main__':
    unittest.main()
