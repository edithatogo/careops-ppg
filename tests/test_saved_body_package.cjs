const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const {stripTypeScriptTypes}=require('node:module');
const context=vm.createContext({});vm.runInContext(stripTypeScriptTypes(fs.readFileSync('scripts/ppg_cloud_package.ts','utf8')),context);
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function fixture(){
 const generated=Buffer.from('PK\x03\x04generated fictional DOCX'),saved=Buffer.from('PK\x03\x04SharePoint rewritten fictional DOCX'),source=Buffer.from('fictional source');
 const documentPath='document/PPG-review-DRAFT.docx';
 const job={schemaVersion:1,jobId:'job-fictional-saved-1',documentKind:'full-review-and-existing-package',CaseUID:'fictional-case',sourceSnapshotRef:'fictional-v1',sourceSHA256:hash(source),templateVersion:'fictional-template-v1',templateSHA256:'b'.repeat(64),outputRevision:'saved-1',includedRecordIDs:['fictional-document'],createdAtUtc:'2026-10-23T00:00:00Z',members:[
 {path:documentPath,sha256:hash(generated),size:generated.length,sourceReference:'fictional://template',sourceVersionRef:'1'},
 {path:'sources/source.txt',sha256:hash(source),size:source.length,sourceReference:'fictional://source',sourceVersionRef:'1'}]};
 const generatedJobJson=JSON.stringify(job),generatedClaimJson=JSON.stringify({kind:'PPG-native-package-claim-v1',jobId:job.jobId,jobSHA256:hash(generatedJobJson),requestSHA256:'c'.repeat(64),createdAtUtc:job.createdAtUtc,generationRunId:'fictional-run-1'});
 const pin={UniqueId:'11111111-1111-4111-8111-111111111111',ETag:'"2"',Length:String(saved.length),UIVersionLabel:'1.0',ServerRelativeUrl:'/sites/fictional/Packages/'+job.jobId+'.docx'};
 return {request:{kind:'m365-saved-body-package-v1',generatedJobJson,generatedClaimJson,savedPinBefore:{...pin},savedPinAfter:{...pin},documentPath,savedBodyBase64:saved.toString('base64'),existingSavedClaimJson:''},members:[{path:'sources/source.txt',base64:source.toString('base64')}],saved,generated};
}
const run=f=>context.main(null,JSON.stringify(f.request),JSON.stringify(f.members));
test('saved bytes replace only generated document and bind distinct generated/saved provenance',()=>{
 const f=fixture(),before=JSON.stringify(f),r=run(f),job=JSON.parse(r.jobJson),claim=JSON.parse(r.claimJson);
 assert.equal(r.coverSHA256,hash(f.saved));assert.equal(claim.generatedDocumentSHA256,hash(f.generated));
 assert.equal(job.members[0].sha256,hash(f.saved));assert.equal(job.members[0].sourceReference,f.request.savedPinBefore.ServerRelativeUrl);
 assert.equal(r.wordGenerationPerformed,false);assert.equal(r.sourceWrites,false);assert.equal(r.sent,false);assert.equal(JSON.stringify(f),before);
 const zip=Buffer.from(r.zipBase64,'base64');assert.ok(zip.includes(f.saved));assert.equal(zip.includes(f.generated),false);
});
test('unchanged frozen saved claim replays exact ZIP and receipt without new timestamps',()=>{
 const f=fixture(),first=run(f);f.request.existingSavedClaimJson=first.claimJson;const second=run(f);
 assert.equal(first.zipBase64,second.zipBase64);assert.equal(first.claimJson,second.claimJson);assert.equal(first.jobSHA256,second.jobSHA256);
});
test('edit, changed source, stale pin, missing claim state and wrong output identity refuse',()=>{
 for(const mutate of [
 f=>{f.request.savedBodyBase64=Buffer.from('PK\x03\x04edited').toString('base64');f.request.savedPinBefore.Length=f.request.savedPinAfter.Length='10';},
 f=>f.members[0].base64=Buffer.from('different source').toString('base64'),
 f=>f.request.savedPinAfter.ETag='"3"',f=>delete f.request.existingSavedClaimJson,
 f=>{f.request.savedPinBefore.ServerRelativeUrl=f.request.savedPinAfter.ServerRelativeUrl='/sites/fictional/other.docx';},
 f=>f.request.generatedClaimJson=f.request.generatedClaimJson.replace('fictional-saved-1','wrong-job'),
 f=>f.members.push({path:f.request.documentPath,base64:f.request.savedBodyBase64})]){
 const f=fixture();f.request.existingSavedClaimJson=run(f).claimJson;mutate(f);assert.throws(()=>run(f));
 }
});
test('partial-effect recovery preserves saved claim; changed same-length bytes and ETags refuse',()=>{
 const f=fixture(),first=run(f);f.request.existingSavedClaimJson=first.claimJson;
 // Simulate package creation not yet happening: finalisation reproduces the
 // complete frozen result without consulting or overwriting a native package.
 assert.equal(run(f).zipBase64,first.zipBase64);
 const edited=Buffer.from(f.saved);edited[edited.length-1]^=1;
 f.request.savedBodyBase64=edited.toString('base64');assert.throws(()=>run(f),/saved_output_edited/);
 f.request.savedBodyBase64=f.saved.toString('base64');
 f.request.savedPinBefore.ETag=f.request.savedPinAfter.ETag='"3"';assert.throws(()=>run(f),/saved_output_edited/);
});
