import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_identity_triage import inspect, proposal, transition
from ppg_identity_application import compile_application, verify_application

class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.a='00000000-0000-4000-8000-000000000001'
        self.b='00000000-0000-4000-8000-000000000002'
        self.ledger={'sourceSystemId':'fictional','aliases':[{'source':'fictional','alias':'A','DocumentUID':self.a}]}
        self.snapshot={'sourceSha256':'a'*64,'records':[
            {'sourceRow':2,'fields':{'sourceDocumentId':'A','sourceTitle':'existing'}},
            {'sourceRow':987,'fields':{'sourceDocumentId':'B','sourceTitle':'new'}}]}
        self.allowed={'sourceDocumentId','sourceTitle'}
        r=inspect(self.snapshot,'fictional',self.ledger,self.allowed)
        p=proposal(r,r['exceptions'][0]['exceptionKey'])
        p.update(resolution='request_new_uid',rationale='Fictional distinct source identity',evidenceReferences=['fictional://proof'])
        self.p=transition(p,'accepted','fictional://decision','Fictional operator')
        self.auth={'exceptionKey':self.p['exceptionKey'],'DocumentUID':self.b,'actor':'Fictional operator','evidenceReference':'fictional://new-identity-authorisation'}
    def compile(self):
        return compile_application(self.snapshot,self.ledger,self.allowed,[self.p],[self.auth])
    def test_explicit_new_identity_and_exact_verification(self):
        before=copy.deepcopy(self.ledger)
        pkg=self.compile()
        self.assertEqual(pkg['newUIDs'],[self.b])
        self.assertEqual(pkg['inputCount'],2)
        self.assertEqual(self.ledger,before)
        self.assertEqual(len(verify_application(pkg,self.snapshot,self.ledger,self.allowed)['operations']),2)
    def test_no_unattended_uid_creation(self):
        with self.assertRaisesRegex(ValueError,'explicit_new_identity'):
            compile_application(self.snapshot,self.ledger,self.allowed,[self.p],[])
        self.auth['DocumentUID']=self.a
        with self.assertRaisesRegex(ValueError,'new_uid_collision'): self.compile()
    def test_stale_source_contract_and_package_tampering(self):
        pkg=self.compile()
        changed=copy.deepcopy(self.snapshot);changed['sourceSha256']='b'*64
        with self.assertRaisesRegex(ValueError,'stale_or_conflicting'):
            verify_application(pkg,changed,self.ledger,self.allowed)
        changed=copy.deepcopy(self.ledger);changed['aliases'][0]['alias']='changed'
        with self.assertRaisesRegex(ValueError,'stale_or_conflicting'):
            verify_application(pkg,self.snapshot,changed,self.allowed)
        pkg['expectedUIDs']=[]
        with self.assertRaisesRegex(ValueError,'package_changed'):
            verify_application(pkg,self.snapshot,self.ledger,self.allowed)
    def test_fake_acceptance_duplicates_and_remaining_unknown_fail(self):
        self.p['history']=[]
        with self.assertRaisesRegex(ValueError,'recorded_operator'):self.compile()
        self.setUp()
        with self.assertRaisesRegex(ValueError,'duplicate_exception'):
            compile_application(self.snapshot,self.ledger,self.allowed,[self.p,self.p],[self.auth])
        self.snapshot['records'].append({'sourceRow':988,'fields':{'sourceDocumentId':'C','sourceTitle':'unknown'}})
        with self.assertRaisesRegex(ValueError,'leaves_identity_exceptions'):self.compile()
    def test_existing_alias_resolution_keeps_identity_count(self):
        self.snapshot['records']=self.snapshot['records'][1:]
        r=inspect(self.snapshot,'fictional',self.ledger,self.allowed)
        p=proposal(r,r['exceptions'][0]['exceptionKey'])
        p.update(resolution='existing_uid',existingUID=self.a,rationale='Fictional continuity',evidenceReferences=['fictional://proof'])
        p=transition(p,'accepted','fictional://decision','Fictional operator')
        pkg=compile_application(self.snapshot,self.ledger,self.allowed,[p],[])
        self.assertEqual(pkg['newUIDs'],[])
        self.assertEqual(pkg['expectedUIDs'],[self.a])
    def test_live_uid_collision_and_unowned_fields_fail(self):
        self.p.update(resolution='existing_uid',existingUID=self.a)
        with self.assertRaisesRegex(ValueError,'leaves_identity_exceptions'):
            compile_application(self.snapshot,self.ledger,self.allowed,[self.p],[])
        with self.assertRaisesRegex(ValueError,'source_field_contract_invalid'):
            compile_application(self.snapshot,self.ledger,self.allowed|{'localDecision'},[self.p],[])

class AbsenceApplicationTests(unittest.TestCase):
    def setUp(self):
        ApplicationTests.setUp(self)
        self.snapshot['records'] = self.snapshot['records'][1:]
        self.ack = {'DocumentUID': self.a, 'sourceSha256': self.snapshot['sourceSha256'],
                    'baseContractHash': inspect(self.snapshot, 'fictional', self.ledger, self.allowed)['contractHash'],
                    'actor': 'Fictional operator', 'evidenceReference': 'fictional://archive-exact-alias',
                    'decisionEvidence': 'fictional://explicit-retention-decision', 'effect': 'retain_unchanged'}
    def test_explicit_absence_keeps_old_identity_and_complete_catalogue_set(self):
        pkg = compile_application(self.snapshot, self.ledger, self.allowed, [self.p], [self.auth], [self.ack])
        self.assertEqual(pkg['schemaVersion'], 2)
        self.assertEqual(pkg['expectedUIDs'], [self.a, self.b])
        self.assertEqual(pkg['activeUIDs'], [self.b])
        self.assertEqual(pkg['retainedAbsentUIDs'], [self.a])
        plan = verify_application(pkg, self.snapshot, self.ledger, self.allowed)
        self.assertEqual(plan['missingUIDs'], [self.a])
        self.assertEqual(plan['acknowledgedMissingUIDs'], [self.a])
        self.assertEqual(self.ledger['aliases'][0]['DocumentUID'], self.a)
        settled = inspect(self.snapshot, 'fictional', pkg['resultLedger'], self.allowed)
        self.assertEqual(settled['exceptions'], [])
        self.assertEqual(settled['acknowledgedMissingUIDs'], [self.a])
        self.assertEqual(settled['unacknowledgedMissingUIDs'], [])
        changed = {**self.snapshot, 'sourceSha256': 'b' * 64}
        stale = inspect(changed, 'fictional', pkg['resultLedger'], self.allowed)
        self.assertEqual(stale['acknowledgedMissingUIDs'], [])
        self.assertEqual(stale['unacknowledgedMissingUIDs'], [self.a])
    def test_absence_requires_exact_evidenced_source_bound_decision(self):
        for change in [{'sourceSha256': 'wrong'}, {'baseContractHash': 'wrong'},
                       {'effect': 'retire'}, {'decisionEvidence': ''}, {'actor': ''},
                       {'DocumentUID': self.b}]:
            ack = {**self.ack, **change}
            with self.assertRaises(ValueError):
                compile_application(self.snapshot, self.ledger, self.allowed, [self.p], [self.auth], [ack])
        with self.assertRaisesRegex(ValueError, 'invalid_absence_identity'):
            compile_application(self.snapshot, self.ledger, self.allowed, [self.p], [self.auth], [self.ack, self.ack])
    def test_outcome_requires_retained_readback_not_just_active_count(self):
        from ppg_identity_application import inspect_outcome
        pkg = compile_application(self.snapshot, self.ledger, self.allowed, [self.p], [self.auth], [self.ack])
        proof = {'status': 'completed', 'sourceSha256': pkg['sourceSha256'],
                 'lastIdentityApplicationHash': pkg['packageHash'], 'identityContractHash': pkg['resultContractHash'],
                 'identityLedger': pkg['resultLedger'], 'readbackCount': pkg['inputCount'], 'runId': 'fictional-run'}
        self.assertEqual(inspect_outcome(pkg, proof, proof)['status'], 'accepted')
        proof.update(retainedAbsentUIDs=pkg['retainedAbsentUIDs'], retainedAbsentReadbackCount=1,
                     retainedAbsentUnchanged=True, catalogueReadbackCount=2)
        self.assertEqual(inspect_outcome(pkg, proof, proof)['status'], 'verified')
        proof['retainedAbsentUnchanged'] = False
        self.assertEqual(inspect_outcome(pkg, proof, proof)['status'], 'accepted')
class NativeBuilderContractTests(unittest.TestCase):
    def test_python_package_is_consumed_and_rechecked_by_native_builder(self):
        import base64
        import hashlib
        import json
        import subprocess
        import shutil
        if not shutil.which('node'):
            self.skipTest('Existing Node runtime unavailable')
        root=Path(__file__).resolve().parents[1]
        probe="""const fs=require('fs'),vm=require('vm'),{stripTypeScriptTypes}=require('node:module');
const c={};vm.createContext(c);vm.runInContext(stripTypeScriptTypes(fs.readFileSync('scripts/ppg_candidate_builder.ts','utf8')),c);
console.log(vm.runInContext('JSON.stringify({headers:expectedHeaders,fields:fieldNames,allowed:allowedFields})',c));"""
        shape=json.loads(subprocess.check_output(['node','--disable-warning=ExperimentalWarning','-e',probe],cwd=root,text=True))
        self.assertEqual(json.loads((root/'config/identity-application-fields.json').read_text()),shape['allowed'])
        uid1='00000000-0000-4000-8000-000000000001';uid2='00000000-0000-4000-8000-000000000002'
        rows=[['']*25,['']*25]
        for i,row in enumerate(rows):row[1]='A' if i==0 else 'B';row[5]=45000;row[6]='Fictional '+str(i)
        raw=b'PK fictional isolated source';sha=hashlib.sha256(raw).hexdigest()
        snapshot={'sourceSha256':sha,'records':[]}
        for i,row in enumerate(rows):
            fields=dict(zip(shape['fields'],row))
            # Projected values are not used in identity fingerprints; full native
            # projection is performed by the existing builder after amendment.
            projected={k:None for k in shape['allowed']};projected['sourceDocumentId']=row[1]
            snapshot['records'].append({'sourceRow':i+2,'fields':fields,'projectedFields':projected})
        ledger={'sourceSystemId':'example-ppg-register','aliases':[{'source':'example-ppg-register','alias':'A','DocumentUID':uid1}]}
        report=inspect(snapshot,ledger['sourceSystemId'],ledger,set(shape['allowed']))
        p=proposal(report,report['exceptions'][0]['exceptionKey']);p.update(resolution='request_new_uid',rationale='Fictional distinct identity',evidenceReferences=['fictional://proof'])
        p=transition(p,'accepted','fictional://decision','Fictional operator')
        auth={'exceptionKey':p['exceptionKey'],'DocumentUID':uid2,'actor':'Fictional operator','evidenceReference':'fictional://new-id'}
        package=compile_application(snapshot,ledger,set(shape['allowed']),[p],[auth])
        absent_snapshot=copy.deepcopy(snapshot)
        absent_snapshot['records']=absent_snapshot['records'][1:]
        ack={'DocumentUID':uid1,'sourceSha256':sha,'baseContractHash':package['baseContractHash'],
             'actor':'Fictional operator','evidenceReference':'fictional://exact-archive-alias',
             'decisionEvidence':'fictional://retention-authorised','effect':'retain_unchanged'}
        absent_package=compile_application(absent_snapshot,ledger,set(shape['allowed']),[p],[auth],[ack])
        later_raw=b'PK later raw source'
        later_snapshot=copy.deepcopy(snapshot)
        later_snapshot['sourceSha256']=hashlib.sha256(later_raw).hexdigest()
        later_row=copy.deepcopy(rows[1]);later_row[1]='C';later_row[6]='Fictional later identity'
        projected={k:None for k in shape['allowed']};projected['sourceDocumentId']='C'
        later_snapshot['records'].append({'sourceRow':4,'fields':dict(zip(shape['fields'],later_row)),
                                          'projectedFields':projected})
        later_ledger=absent_package['resultLedger']
        later_report=inspect(later_snapshot,ledger['sourceSystemId'],later_ledger,set(shape['allowed']))
        later_proposal=proposal(later_report,later_report['exceptions'][0]['exceptionKey'])
        later_proposal.update(resolution='request_new_uid',rationale='Fictional later distinct identity',
                              evidenceReferences=['fictional://later-proof'])
        later_proposal=transition(later_proposal,'accepted','fictional://later-decision','Fictional operator')
        later_auth={'exceptionKey':later_proposal['exceptionKey'],'DocumentUID':'00000000-0000-4000-8000-000000000003',
                    'actor':'Fictional operator','evidenceReference':'fictional://later-new-id'}
        later_package=compile_application(later_snapshot,later_ledger,set(shape['allowed']),[later_proposal],[later_auth])
        fixture={'raw':base64.b64encode(raw).decode(),'ledger':{'sourceSystemId':ledger['sourceSystemId'],'aliases':[{'documentUID':uid1,'sourceDocumentId':'A'}]},'package':package,
                 'extraction':{'schemaVersion':1,'sheet':'Master Document Register','sheetNames':['Master Document Register'],'rowsIncludingHeader':3,'columns':25,'values':[shape['headers']]+rows,'dateFormats':[{'column':6,'formats':['mmm-yyyy','mmm-yyyy']}],'reviewTexts':['Mar-2023','Mar-2023']}}
        fixture['absentPackage']=absent_package
        fixture.update(laterPackage=later_package,laterRaw=base64.b64encode(later_raw).decode(),laterRow=later_row)
        code="""const fs=require('fs'),vm=require('vm'),{stripTypeScriptTypes}=require('node:module');
const c={};vm.createContext(c);vm.runInContext(stripTypeScriptTypes(fs.readFileSync('scripts/ppg_candidate_builder.ts','utf8')),c);
const f=JSON.parse(fs.readFileSync(0,'utf8'));
const run=(p=f.package,e=f.extraction)=>c.buildCandidate(e,f.raw,JSON.stringify(f.ledger),'2026-10-16T00:00:00Z','https://example.invalid/raw','https://example.invalid/records',JSON.stringify(p));
const held=c.buildCandidate(f.extraction,f.raw,JSON.stringify(f.ledger),'2026-10-16T00:00:00Z','https://example.invalid/raw','https://example.invalid/records');
if(held.candidate.exceptions.length!==1||held.candidate.operations.length!==1||held.candidate.inputCount!==2||held.candidate.rawRecords.length!==2)throw Error('unknown source not retained safely');
const r=run();if(r.candidate.inputCount!==2||r.candidate.contractHash!==f.package.resultContractHash||r.identityApplication.newUIDs.length!==1)throw Error('native contract mismatch');
let checks=2;
for(const mutate of [p=>p.expectedUIDs=[],p=>p.baseContractHash='x',p=>p.acceptedProposals[0].history=[]]){
 const p=JSON.parse(JSON.stringify(f.package));mutate(p);
 // Rehash malicious package to prove substantive validation, not only its envelope.
 const bare=JSON.parse(JSON.stringify(p));delete bare.packageHash;p.packageHash=c.identityHash(bare);
 let failed=false;try{run(p);}catch(e){failed=true;}if(!failed)throw Error('unsafe package accepted');checks++;
}
const changed=JSON.parse(JSON.stringify(f.extraction));changed.values[2][6]='Changed source evidence';
let failed=false;try{run(f.package,changed);}catch(e){failed=true;}if(!failed)throw Error('changed source accepted');
const absent=JSON.parse(JSON.stringify(f.extraction));absent.values.splice(1,1);absent.rowsIncludingHeader--;absent.reviewTexts.pop();absent.dateFormats[0].formats.pop();
const retained=run(f.absentPackage,absent);
if(retained.candidate.operations.length!==1||retained.candidate.missingUIDs.length!==1||retained.candidate.acknowledgedMissingUIDs.length!==1)throw Error('retained absence mismatch');
for(const mutate of [p=>p.absenceAcknowledgements[0].sourceSha256='wrong',p=>p.retainedAbsentUIDs=[],p=>p.activeUIDs=[],p=>p.absenceAcknowledgements[0].effect='retire']){
 const p=JSON.parse(JSON.stringify(f.absentPackage));mutate(p);const bare=JSON.parse(JSON.stringify(p));delete bare.packageHash;p.packageHash=c.identityHash(bare);
 let refused=false;try{run(p,absent);}catch(e){refused=true;}if(!refused)throw Error('unsafe absence accepted');
}
const settled=c.buildCandidate(absent,f.raw,JSON.stringify(retained.identityContract.ledger),'2026-10-16T00:00:00Z','https://example.invalid/raw','https://example.invalid/records');
if(settled.candidate.acknowledgedMissingUIDs.length!==1)throw Error('settled absence lost');
const returned=c.buildCandidate(f.extraction,Buffer.from('PK changed raw source').toString('base64'),JSON.stringify(retained.identityContract.ledger),'2026-10-16T00:00:00Z','https://example.invalid/raw','https://example.invalid/records');
if(returned.candidate.missingUIDs.length||returned.candidate.acknowledgedMissingUIDs.length||returned.identityContract.ledger.sourceAbsenceAcknowledgements.length!==1)throw Error('returned identity blocked or history erased');
const later=JSON.parse(JSON.stringify(f.extraction));later.values.push(f.laterRow);later.rowsIncludingHeader++;later.reviewTexts.push('Mar-2023');later.dateFormats[0].formats.push('mmm-yyyy');
const amended=c.buildCandidate(later,f.laterRaw,JSON.stringify(retained.identityContract.ledger),'2026-10-16T00:00:00Z','https://example.invalid/raw','https://example.invalid/records',JSON.stringify(f.laterPackage));
if(amended.candidate.operations.length!==3||amended.identityContract.ledger.sourceAbsenceAcknowledgements.length!==1)throw Error('later amendment lost historical evidence');
let refused=false;try{c.buildCandidate(absent,Buffer.from('PK changed raw source').toString('base64'),JSON.stringify(retained.identityContract.ledger),'2026-10-16T00:00:00Z','https://example.invalid/raw','https://example.invalid/records');}catch(e){refused=true;}if(!refused)throw Error('absence extended to changed source');
console.log(JSON.stringify({checks:checks+1}));"""
        result=subprocess.run(['node','--disable-warning=ExperimentalWarning','-e',code],cwd=root,input=json.dumps(fixture),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['checks'],6)

class NativeInputTests(unittest.TestCase):
    def test_native_candidate_and_checkpoint_use_active_contract(self):
        from ppg_identity_triage import normalise_inputs
        candidate={'sourceSha256':'a'*64,'rawRecords':[{'sourceRow':2,'fields':{'sourceDocumentId':'A'}}]}
        checkpoint={'status':'completed','identityLedger':{'sourceSystemId':'fictional','aliases':[{'documentUID':'00000000-0000-4000-8000-000000000001','sourceDocumentId':'A'}]}}
        before=copy.deepcopy(checkpoint)
        snapshot,ledger=normalise_inputs(candidate,checkpoint)
        self.assertEqual(snapshot['records'],candidate['rawRecords'])
        self.assertEqual(ledger['aliases'][0]['alias'],'A')
        self.assertEqual(checkpoint,before)
        checkpoint['status']='failed'
        with self.assertRaisesRegex(ValueError,'completed_active_contract_required'):
            normalise_inputs(candidate,checkpoint)

class OutcomeTests(unittest.TestCase):
    setUp = ApplicationTests.setUp
    compile = ApplicationTests.compile
    def proof(self, package):
        return {'status':'completed','sourceSha256':package['sourceSha256'],
                'lastIdentityApplicationHash':package['packageHash'],
                'identityContractHash':package['resultContractHash'],
                'identityLedger':package['resultLedger'], 'readbackCount':package['inputCount'],
                'runId':'fictional-native-run'}
    def test_verified_requires_native_readback_and_exact_checkpoint(self):
        from ppg_identity_application import inspect_outcome
        pkg=self.compile();proof=self.proof(pkg)
        result=inspect_outcome(pkg,proof,copy.deepcopy(proof))
        self.assertEqual(result['status'],'verified')
        self.assertTrue(result['applicationVerified'])
        self.assertFalse(result['policyApproved'])
        old=copy.deepcopy(proof);old['runId']='earlier-run'
        result=inspect_outcome(pkg,proof,old)
        self.assertEqual(result['status'],'applied')
        self.assertFalse(result['applicationVerified'])
    def test_failed_incomplete_stale_or_forged_evidence_never_verifies(self):
        from ppg_identity_application import inspect_outcome
        pkg=self.compile();proof=self.proof(pkg)
        for key,value in [('status','failed_partial_or_unverified'),('readbackCount',0),('sourceSha256','b'*64),('lastIdentityApplicationHash','c'*64),('identityLedger',{})]:
            bad=copy.deepcopy(proof);bad[key]=value
            self.assertEqual(inspect_outcome(pkg,bad,proof)['status'],'accepted')
        pkg['newUIDs']=[]
        with self.assertRaisesRegex(ValueError,'package_changed'):inspect_outcome(pkg,proof,proof)

if __name__=='__main__':unittest.main()
