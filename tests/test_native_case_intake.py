import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import unittest
import zipfile
import test_full_document as support


class CaseIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.FullDocumentTests.setUpClass()
        cls.template=support.FullDocumentTests.template
        cls.raw=support.FullDocumentTests.raw

    @classmethod
    def tearDownClass(cls):
        support.FullDocumentTests.tearDownClass()

    def fixture(self):
        site='https://example.sharepoint.com/sites/ppg'
        uid='11111111-1111-4111-8111-111111111111'
        doc='22222222-2222-4222-8222-222222222222'
        baseline=io.BytesIO()
        with zipfile.ZipFile(baseline,'w')as z:z.writestr('source.txt','retained fictional source')
        baseline=baseline.getvalue()
        def pin(role,raw,path):return {'role':role,'UniqueId':uid,'ETag':'"opaque-1"','Length':str(len(raw)),'UIVersionLabel':'1.0','ServerRelativeUrl':'/sites/ppg/'+path}
        bp=pin('selected-baseline',baseline,'baseline.zip');dp=pin('selected-draft',self.raw,'draft.docx')
        c={'Id':1,'CaseUID':uid,'Title':'Fictional Ω café 日本語','linkedDocumentUIDs':json.dumps([doc]),'sourceBaselineRef':site+'/baseline.zip','evidenceDraftLink':site+'/draft.docx','odata.etag':'"case-1"','OData__UIVersionString':'1.0'}
        rows=[{'Id':1,'DocumentUID':doc,'sourceDocumentId':'fictional-source','sourceSnapshotRef':c['sourceBaselineRef'],'rawSourceRecordRef':'retained-record','odata.etag':'"row-1"'}]
        h={'kind':'existing-case-artifact-selection','caseBinding':copy.deepcopy(c),'catalogueBinding':{'records':copy.deepcopy(rows)},'sources':[{'role':'recorded-baseline','sourceReference':c['sourceBaselineRef'],'nativePin':bp,'sha256':hashlib.sha256(baseline).hexdigest()}]}
        roles=['request','compiled-template','maintained-template','source-pack','source-job','source-receipt','engine','full-document-input']
        pins=[pin(r,b'x',r+'.json')for r in roles]+[bp,dp]
        r={'kind':'m365-case-intake-request-v1','requestItemId':9,'createdAtUtc':'2026-10-20T10:00:00Z','generationRunId':'fictional-run','existingClaimJson':'','templateVersion':'full-v1','template':self.template,'values':{'PPGCoverOutputRevision':'r1'},'pinsJson':json.dumps(pins),'intake':{'site':site,'mode':'catalogue-current','expectedCaseUID':uid,'case':c,'catalogue':rows,'baselinePin':bp,'draftPin':dp,'historicalSelection':h}}
        members=[{'path':p,'base64':base64.b64encode(raw).decode()}for p,raw in [('existing-pack.zip',baseline),('maintained-template.docx',self.raw),('evidence/selected-draft.docx',self.raw)]]
        return r,members

    def run_kernel(self,r,m):
        js="""const fs=require('node:fs'),vm=require('node:vm'),{stripTypeScriptTypes}=require('node:module');const c={};vm.createContext(c);vm.runInContext(stripTypeScriptTypes(fs.readFileSync('scripts/ppg_cloud_package.ts','utf8')),c);const x=JSON.parse(fs.readFileSync(0,'utf8'));try{process.stdout.write(c.nativeCaseIntake(JSON.stringify(x.r),JSON.stringify(x.m)));}catch(e){process.stderr.write(e.message);process.exit(1);}"""
        return subprocess.run(['node','--disable-warning=ExperimentalWarning','-e',js],input=json.dumps({'r':r,'m':m}).encode(),capture_output=True)

    def test_current_snapshot_and_explicit_historical_reconciliation(self):
        for mode in ['catalogue-current','recorded-baseline']:
            r,m=self.fixture();r['intake']['mode']=mode
            if mode=='recorded-baseline':r['intake']['catalogue'][0]['sourceSnapshotRef']='newer-capture.json'
            result=self.run_kernel(r,m);self.assertEqual(result.returncode,0,result.stderr.decode());out=json.loads(result.stdout)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(out['zipBase64'])))as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(z.read('evidence/selected-draft.docx'),self.raw)
                self.assertEqual(z.read('evidence/recorded-baseline.zip'),base64.b64decode(m[0]['base64']))
                selection=json.loads(z.read('selection/frozen-source-job.json'))['selection']
                self.assertEqual(selection['mode'],mode);self.assertFalse(selection['currentPolicyClaim']);self.assertFalse(selection['findingsInherited'])
                values=json.loads(json.loads(z.read('generation/request-snapshot.json'))['fullDocumentInputJson'])
                self.assertEqual(values['comparison_rows'],[]);self.assertEqual(values['consultation_rows'],[])
                self.assertIn('Unresolved',values['review_findings'])
            replay=copy.deepcopy(r);replay['generationRunId']='second-run';replay['existingClaimJson']=out['claimJson']
            result2=self.run_kernel(replay,m);self.assertEqual(result2.returncode,0,result2.stderr.decode())
            self.assertEqual(json.loads(result2.stdout)['zipBase64'],out['zipBase64'])
            replay['intake']['case']['Title']='Changed input'
            self.assertIn(b'new_revision',self.run_kernel(replay,m).stderr)

    def test_mismatch_and_historical_drift_refuse(self):
        for change in ['current-mismatch','historical-hash','historical-case','wrong-site','wrong-identity','duplicate-row','wrong-length']:
            r,m=self.fixture();x=r['intake']
            if change=='current-mismatch':x['catalogue'][0]['sourceSnapshotRef']='newer'
            elif change=='historical-hash':x['mode']='recorded-baseline';x['historicalSelection']['sources'][0]['sha256']='0'*64
            elif change=='historical-case':x['mode']='recorded-baseline';x['historicalSelection']['caseBinding']['odata.etag']='"old"'
            elif change=='wrong-site':x['case']['evidenceDraftLink']='https://other.example/draft.docx'
            elif change=='wrong-identity':x['expectedCaseUID']='other'
            elif change=='duplicate-row':x['catalogue']*=2
            elif change=='wrong-length':x['draftPin']['Length']='1'
            with self.subTest(change=change):self.assertNotEqual(self.run_kernel(r,m).returncode,0)

    def test_current_capture_json_keeps_original_bytes_and_correct_extension(self):
        r,m=self.fixture();x=r['intake'];raw=b'{"capture":"fictional current source","rows":[]}'
        x['case']['sourceBaselineRef']=x['case']['sourceBaselineRef'].replace('.zip','.json')
        x['catalogue'][0]['sourceSnapshotRef']=x['case']['sourceBaselineRef']
        x['baselinePin']['ServerRelativeUrl']=x['baselinePin']['ServerRelativeUrl'].replace('.zip','.json')
        x['baselinePin']['Length']=str(len(raw));m[0]['base64']=base64.b64encode(raw).decode()
        pins=json.loads(r['pinsJson']);pins[-2]=x['baselinePin'];r['pinsJson']=json.dumps(pins)
        result=self.run_kernel(r,m);self.assertEqual(result.returncode,0,result.stderr.decode())
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(json.loads(result.stdout)['zipBase64'])))as z:
            self.assertEqual(z.read('evidence/recorded-baseline.json'),raw)
        m[0]['base64']=base64.b64encode(b'not valid JSON').decode();x['baselinePin']['Length']='14'
        self.assertNotEqual(self.run_kernel(r,m).returncode,0)

    def initiated_fixture(self):
        r,m=self.fixture();x=r['intake'];c=x['case'];uid='LC-FICTIONAL-NEW-OCCURRENCE'
        c.update(CaseUID=uid,caseStatus='Initiated — FICTIONAL',linkedDocumentUIDs=json.dumps(['FICTIONAL-DOC-1']),sourceBaselineRef=x['site']+'/initiation.json',evidenceDraftLink=x['site']+'/original.txt')
        raw=b'FICTIONAL original source; no review findings';dp=x['draftPin'];dp.update(ServerRelativeUrl='/sites/ppg/original.txt',Length=str(len(raw)))
        request={'request':{'CaseUID':uid,'DocumentUID':'FICTIONAL-DOC-1','occurrenceReference':'fictional-occurrence-1','qualificationOnly':True,'realPolicyEffects':False,'DocumentReference':c['evidenceDraftLink'],'ReviewedVersionRef':'sharepoint:'+dp['UniqueId']+':'+dp['ETag'],'DocumentSHA256':hashlib.sha256(raw).hexdigest()}}
        baseline=json.dumps(request).encode();bp=x['baselinePin'];bp.update(ServerRelativeUrl='/sites/ppg/initiation.json',Length=str(len(baseline)))
        x.update(expectedCaseUID=uid,mode='fictional-initiated-source',catalogue=[],eventSets={k:{'value':[]}for k in ['assurance','consultation','readiness']})
        pins=json.loads(r['pinsJson']);pins[-2:]=[bp,dp];r['pinsJson']=json.dumps(pins)
        m[0]['base64']=base64.b64encode(baseline).decode();m[2]['base64']=base64.b64encode(raw).decode()
        return r,m,raw

    def test_initiated_contract_has_no_inherited_findings_and_keeps_text_extension(self):
        r,m,raw=self.initiated_fixture();result=self.run_kernel(r,m);self.assertEqual(result.returncode,0,result.stderr.decode())
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(json.loads(result.stdout)['zipBase64'])))as z:
            self.assertEqual(z.read('evidence/original-source.txt'),raw)
            values=json.loads(json.loads(z.read('generation/request-snapshot.json'))['fullDocumentInputJson'])
            self.assertIn('INITIATED FICTIONAL SOURCE ONLY',values['version']);self.assertIn('Unresolved',values['decision_evidence']);self.assertEqual(values['consultation_rows'],[])
        for change in ['events','continuation','status','wrong-source']:
            a,b,_=self.initiated_fixture()
            if change=='events':a['intake']['eventSets']['assurance']['value']=[{'CaseUID':a['intake']['case']['CaseUID']}]
            elif change=='continuation':a['intake']['eventSets']['readiness']['odata.nextLink']='more'
            elif change=='status':a['intake']['case']['caseStatus']='Review closed'
            elif change=='wrong-source':b[2]['base64']=base64.b64encode(b'altered original source').decode()
            with self.subTest(change=change):self.assertNotEqual(self.run_kernel(a,b).returncode,0)


if __name__=='__main__':unittest.main()
