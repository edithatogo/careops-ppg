'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto'),cp=require('node:child_process');
const {stripTypeScriptTypes}=require('node:module');
const source=fs.readFileSync('scripts/ppg_cloud_package.ts','utf8');
const ctx={};vm.createContext(ctx);vm.runInContext(stripTypeScriptTypes(source),ctx);
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const make=members=>({schemaVersion:1,jobId:'job-fictional-cloud-1',documentKind:'review-package',CaseUID:'fictional-case',sourceSnapshotRef:'fictional-v1',sourceSHA256:'a'.repeat(64),templateVersion:'fictional-template-v1',templateSHA256:'b'.repeat(64),outputRevision:'fictional-1',includedRecordIDs:['fictional-document'],createdAtUtc:'2026-10-16T00:00:00Z',members:members.map(m=>({path:m.path,sha256:hash(m.bytes),size:m.bytes.length,sourceReference:'fictional://selected',sourceVersionRef:'fixture-v1'}))});
const pack=(j,items)=>JSON.parse(ctx.packageJob(JSON.stringify(j),JSON.stringify(items.map(m=>({path:m.path,base64:m.bytes.toString('base64')})))));
const members=[{path:'attachments/Āta-whānau.txt',bytes:Buffer.from('Fictional text\nLine two\n')},{path:'attachments/binary.docx',bytes:Buffer.from([0,1,255,34,128,0])},{path:'empty.txt',bytes:Buffer.alloc(0)}];
for(const items of [[],members]){
 const job=make(items),first=pack(job,items),again=pack(job,items);
 assert.equal(JSON.stringify(ctx.main(null,JSON.stringify(job),JSON.stringify(items.map(m=>({path:m.path,base64:m.bytes.toString('base64')}))))),JSON.stringify(first));
 assert.equal(first.zipBase64,again.zipBase64);assert.equal(first.packageSHA256,hash(Buffer.from(first.zipBase64,'base64')));
 assert.equal(first.memberCount,items.length+1);assert.equal(first.sent,false);assert.equal(first.sourceWrites,false);
 const independent=cp.spawnSync('python3',['-c',`
import sys,json,base64,zipfile,io,hashlib
x=json.load(sys.stdin);raw=base64.b64decode(x['result']['zipBase64']);z=zipfile.ZipFile(io.BytesIO(raw))
assert z.testzip() is None
expected={m['path']:base64.b64decode(m['base64']) for m in x['members']}
assert set(z.namelist())==set(expected)|{'package-provenance.json'}
for name,data in expected.items():
 assert z.read(name)==data
 assert z.getinfo(name).compress_type==zipfile.ZIP_STORED
p=json.loads(z.read('package-provenance.json'))
assert p['job']==x['job'] and p['policyApproved'] is False
print('independent ZIP CRC, exact membership, bytes and provenance passed')
`],{input:JSON.stringify({result:first,job,members:items.map(m=>({path:m.path,base64:m.bytes.toString('base64')}))}),encoding:'utf8'});
 assert.equal(independent.status,0,independent.stderr);
}
for(const name of ['../escape','/absolute','a/../b','a\\b','a//b','a:stream','tail.','dir/space ','package-provenance.json']){
 const items=[{path:name,bytes:Buffer.from('x')}];assert.throws(()=>pack(make(items),items),/unsafe|collision/);
}
for(const names of [['A.txt','a.txt'],['é.txt','e\u0301.txt'],['a','a/b'],['a/b','A'],['package-provenance.json/child']]){
 const items=names.map(path=>({path,bytes:Buffer.from('x')}));assert.throws(()=>pack(make(items),items),/collision/);
}
const good=make(members);
const formatBytes=fs.readFileSync('templates/unattended-package/existing-artifacts-format.json');
const format=JSON.parse(formatBytes);
const existingItems=[{path:'sources/recorded.zip',bytes:Buffer.from('unchanged archive bytes')},
 {path:'drafts/existing.docx',bytes:Buffer.from([0,1,255,128,34])},
 {path:'selection/selection.json',bytes:Buffer.from('{"kind":"existing-case-artifact-selection"}')}];
const existingJob=make(existingItems);
existingJob.schemaVersion=2;existingJob.provenanceMode='existing-artifacts';
existingJob.documentKind=format.documentKind;
delete existingJob.templateVersion;delete existingJob.templateSHA256;
existingJob.assemblyTemplateVersion=format.assemblyTemplateVersion;
existingJob.assemblyTemplateSHA256=hash(formatBytes);
existingJob.authoringProvenance={status:'unknown',generationReceipt:null};
existingJob.members.forEach((m,i)=>m.role=format.archive.requiredMemberRoles[i]);
const existingResult=pack(existingJob,existingItems);
assert.equal(existingResult.schemaVersion,2);assert.equal(existingResult.wordGenerationPerformed,false);
const existingReadback=cp.spawnSync('python3',['-c',`
import sys,json,base64,zipfile,io
x=json.load(sys.stdin);z=zipfile.ZipFile(io.BytesIO(base64.b64decode(x['result']['zipBase64'])))
assert z.testzip() is None
for m in x['members']: assert z.read(m['path']) == base64.b64decode(m['base64'])
p=json.loads(z.read('package-provenance.json'))
assert p['schemaVersion']==2 and p['wordGenerationPerformed'] is False
assert p['job']['authoringProvenance']=={'status':'unknown','generationReceipt':None}
assert p['job']['assemblyTemplateSHA256']==x['formatSHA256']
assert 'templateVersion' not in p['job'] and 'templateSHA256' not in p['job']
assert p['policyApproved'] is False
`],{input:JSON.stringify({result:existingResult,formatSHA256:hash(formatBytes),
 members:existingItems.map(m=>({path:m.path,base64:m.bytes.toString('base64')}))}),encoding:'utf8'});
assert.equal(existingReadback.status,0,existingReadback.stderr);
for(const mutate of [j=>delete j.assemblyTemplateVersion,j=>delete j.assemblyTemplateSHA256,
 j=>j.assemblyTemplateSHA256='0'.repeat(64),j=>j.provenanceMode='word-generation',
 j=>j.templateVersion='invented',j=>j.templateSHA256='a'.repeat(64),
 j=>j.upstreamGeneration={runID:'invented'},j=>j.authoringProvenance.generationReceipt='invented',
 j=>j.authoringProvenance.status='known',j=>j.authoringProvenance.templateVersion='invented',
 j=>delete j.authoringProvenance,j=>j.members[0].role='existing-manual-draft']){
 const job=structuredClone(existingJob);mutate(job);assert.throws(()=>pack(job,existingItems),
 /assembly_template_unqualified|ambiguous_provenance_mode|historical_authoring_provenance_invalid|existing_artifact_members_invalid/);
}
const mixedLegacy=structuredClone(good);mixedLegacy.assemblyTemplateVersion=format.assemblyTemplateVersion;
assert.throws(()=>pack(mixedLegacy,members),/ambiguous_provenance_mode/);
for(const mutate of [j=>j.members[0].sha256='0'.repeat(64),j=>j.members[0].size++,j=>j.members.pop(),j=>j.members[0].sourceVersionRef='',j=>j.sourceSHA256='',j=>j.outputRevision='',j=>j.createdAtUtc='2026-02-30T00:00:00Z']){
 const job=structuredClone(good);mutate(job);assert.throws(()=>pack(job,members));
}
for(const value of ['A','Z===','!!!!','Zh==','Zm9=']){
 const items=[{path:'a',bytes:Buffer.from('f')}],job=make(items);
 assert.throws(()=>ctx.packageJob(JSON.stringify(job),JSON.stringify([{path:'a',base64:value}])),/base64/);
}
assert.throws(()=>ctx.packageJob('x'.repeat(4000001),'[]'),/request_limit/);
const escaped=make([]);escaped.sourceSnapshotRef='"'.repeat(1000000);
assert.throws(()=>ctx.packageJob(JSON.stringify(escaped),'[]'),/request_limit/);
const large=[{path:'large',bytes:Buffer.alloc(2000001)}];assert.throws(()=>pack(make(large),large),/member_contract_invalid/);
const nearLimit=[{path:'near-limit',bytes:Buffer.alloc(1999500)}];
assert.throws(()=>pack(make(nearLimit),nearLimit),/complete_package_oversize/);
const acceptedLarge=[{path:'large.bin',bytes:Buffer.alloc(1995000,0xa5)}];
const acceptedLargeResult=pack(make(acceptedLarge),acceptedLarge);
assert.equal(acceptedLargeResult.packageSHA256,hash(Buffer.from(acceptedLargeResult.zipBase64,'base64')));
const largeReadback=cp.spawnSync('python3',['-c',`
import sys,json,base64,zipfile,io
r=json.load(sys.stdin);z=zipfile.ZipFile(io.BytesIO(base64.b64decode(r['zipBase64'])))
assert z.testzip() is None
assert z.read('large.bin') == bytes([0xa5])*1995000
assert set(z.namelist()) == {'large.bin','package-provenance.json'}
assert json.loads(z.read('package-provenance.json'))['status'] == 'DRAFT / HUMAN CHECK REQUIRED'
`],{input:JSON.stringify(acceptedLargeResult),encoding:'utf8'});
assert.equal(largeReadback.status,0,largeReadback.stderr);
console.log('Passed: deterministic cloud ZIP, independent CRC/membership/byte/hash readback, empty/multiple/Unicode/binary members, malformed content, path/collision, identity, UTC and bounded envelopes. Native Office Script execution not claimed.');
// Cover envelope uses the existing two-parameter native connector contract.
assert.throws(()=>ctx.main(null,JSON.stringify({kind:'standard-cover-input-v1',jobJson:JSON.stringify(good),coverJson:'{}'}),'[]'),/cover_contract/);
