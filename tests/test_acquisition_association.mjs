import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {planAssociation,persistAssociation} from '../tools/source-integrity/association.mjs';
// Golden digests were produced by the existing Python handoff implementation
// from entirely fictional inputs; these expected values are not credentials.
function loadFixture(name){
 const {expectedReplaySHA256,expectedOccurrenceSHA256,...handoff}=JSON.parse(fs.readFileSync(new URL('./fixtures/'+name,import.meta.url)));
 return {...handoff,replayKey:expectedReplaySHA256,occurrenceKey:expectedOccurrenceSHA256};
}
const fixture=()=>loadFixture('fictional-acquisition-handoff.json');
const next=()=>loadFixture('fictional-acquisition-handoff-next-run.json');
function recordProof(h=fixture()){
 function canonical(v){return v&&typeof v==='object'?(Array.isArray(v)?'['+v.map(canonical).join(',')+']':'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}'):JSON.stringify(v);}
 return {selectedRecordJSON:Object.fromEntries(['publication','edition','capture'].map(k=>[h.selectedRecords[k].key,canonical(h.selectedRecords[k])]))};
}
function transport(){
 const store=new Map(),creates=[],events=[];let serial=0;
 const client={get:async name=>{const x=store.get(name);return x?{bytes:Buffer.from(x.bytes),pin:structuredClone(x.pin)}:null;},
  create:async(name,bytes)=>{creates.push(name);if(store.has(name)){const e=Error('conflict');e.status=409;throw e;}
   store.set(name,{bytes:Buffer.from(bytes),pin:{UniqueId:'fictional-'+(++serial),ETag:'"fixture-'+serial+',1"',UIVersionLabel:'1.0',Length:String(bytes.length),ServerRelativeUrl:'/sites/Fictional/Evidence/SourceReceipts/'+name}});}};
 return {store,creates,events,client,verifyBindings:async()=>recordProof(),journal:async event=>events.push(event)};
}
const run=(t,h=fixture(),extra={})=>persistAssociation({handoff:h,...t,...extra});
test('altered copied records cannot pass unchanged authoritative native JSON hashes',async()=>{
 for(const kind of ['publication','edition','capture']){
  const t=transport(),h=fixture();let reads=0;t.client.get=async()=>{reads++;return null;};
  h.selectedRecords[kind].title+=' altered without changing native hash';
  await assert.rejects(run(t,h),/NATIVE_RECORD_PAYLOAD_MISMATCH/);
  assert.equal(reads,0);assert.equal(t.creates.length,0);assert.equal(t.events.length,0);
 }
});
test('native record proof must supply exactly the three raw JSON snapshots with matching hashes',async()=>{
 const h=fixture(),key=h.binding.publicationKey;
 for(const proof of [undefined,{}, {selectedRecordJSON:{}},
  {selectedRecordJSON:{...recordProof().selectedRecordJSON,[key]:'{}'}},
  {selectedRecordJSON:{...recordProof().selectedRecordJSON,[key]:'x'.repeat(1024*1024+1)}}]){
  const t=transport();let reads=0;t.client.get=async()=>{reads++;return null;};
  await assert.rejects(run(t,h,{verifyBindings:async()=>proof}),/NATIVE_RECORD_/);
  assert.equal(reads,0);assert.equal(t.creates.length,0);assert.equal(t.events.length,0);
 }
});
test('native record JSON hashing preserves actual numeric and formatting representations',async()=>{
 const h=fixture();h.selectedRecords.publication.data.number=1;
 const proof=recordProof(h),key=h.binding.publicationKey;
 proof.selectedRecordJSON[key]=' \n'+proof.selectedRecordJSON[key].replace('"number":1','"number":1.0')+'\n';
 h.selectedRecordSHA256[key]=createHash('sha256').update(proof.selectedRecordJSON[key]).digest('hex');
 const t=transport();const result=await run(t,h,{verifyBindings:async()=>proof});
 assert.equal(result.created,3);assert.equal(result.associationCommitVerified,true);
});
test('persist verifies three immutable members; unchanged replay creates nothing',async()=>{
 const t=transport(),h=fixture(),before=JSON.stringify(h),first=await run(t,h);
 assert.equal(first.created,3);assert.equal(first.associationCommitVerified,true);
 assert.equal(first.catalogueRowsChanged,0);assert.equal(first.originalCapturesCreated,0);
 assert.equal(first.checkpointAdvanced,false);assert.equal(first.fullAcquisitionQualified,false);
 assert.equal(t.store.size,3);assert.equal(JSON.stringify(h),before);
 const replay=await run(t,h);assert.equal(replay.state,'replayed');assert.equal(replay.created,0);
 assert.deepEqual(replay.files,first.files);assert.equal(t.creates.length,3);
 assert.match(t.creates[2],/^source-commit-/);
});
test('another run keeps one capture claim and retains both occurrence/commit pairs',async()=>{
 const t=transport(),a=fixture(),b=next();assert.equal(a.replayKey,b.replayKey);assert.notEqual(a.occurrenceKey,b.occurrenceKey);
 await run(t,a);const result=await run(t,b);assert.equal(result.created,2);
 assert.equal(t.store.size,5);assert.equal([...t.store.keys()].filter(k=>k.startsWith('source-replay-')).length,1);
});
test('conflicting existing member prevents every mutation, including when commit conflicts',async()=>{
 for(let index=0;index<3;index++){
  const t=transport(),plan=planAssociation(fixture()),file=plan.files[index];await t.client.create(file.name,Buffer.from('HUMAN EDIT'));
  const count=t.creates.length;await assert.rejects(run(t),/NATIVE_READBACK_MISMATCH/);assert.equal(t.creates.length,count);
  assert.equal(t.store.get(file.name).bytes.toString(),'HUMAN EDIT');
 }
});
test('lost create response is not retried; explicit later reconciliation preserves the created file',async()=>{
 const t=transport(),real=t.client.create;let failed=false;
 t.client.create=async(name,data)=>{await real(name,data);if(!failed){failed=true;throw Error('fictional lost response');}};
 await assert.rejects(run(t),/CREATE_UNCERTAIN/);assert.equal(t.store.size,1);assert.equal(t.creates.length,1);
 assert.equal(t.events.some(e=>e.event==='association_complete'),false);
 const resumed=await run(t);assert.equal(resumed.created,2);assert.equal(t.store.size,3);assert.equal(t.creates.length,3);
});
test('current source guard refuses before first write and between partial members',async()=>{
 let calls=0;const t=transport();await assert.rejects(run(t,fixture(),{verifyBindings:async()=>{throw Error('SOURCE_CHANGED');}}),/SOURCE_CHANGED/);assert.equal(t.creates.length,0);
 await assert.rejects(run(t,fixture(),{verifyBindings:async()=>{if(++calls===3)throw Error('SOURCE_CHANGED');return recordProof();}}),/SOURCE_CHANGED/);
 assert.equal(t.store.size,1);assert.equal(t.events.some(e=>e.event==='association_complete'),false);
 const resumed=await run(t);assert.equal(resumed.created,2);assert.equal(t.store.size,3);
});
test('atomic create conflict between overlapping calls is visible; reconcile performs no duplicate create',async()=>{
 const t=transport(),real=t.client.create;let entrants=0,release;const barrier=new Promise(resolve=>release=resolve);
 t.client.create=async(name,data)=>{if(name.startsWith('source-replay-')){if(++entrants===2)release();await barrier;}return real(name,data);};
 const results=await Promise.allSettled([run(t),run(t)]);
 assert.equal(results.filter(r=>r.status==='fulfilled').length,1);const rejected=results.find(r=>r.status==='rejected');assert.match(rejected.reason.message,/CREATE_UNCERTAIN/);assert.equal(rejected.reason.status,409);
 assert.equal(t.store.size,3);const attempts=t.creates.length;const resumed=await run(t);
 assert.equal(resumed.created,0);assert.equal(t.creates.length,attempts);assert.equal(t.store.size,3);
});
test('same bytes with changed native pin are held and never overwritten',async()=>{
 const t=transport();await run(t);const get=t.client.get;let seen=0;
 t.client.get=async name=>{const value=await get(name);if(++seen>3)value.pin.ETag='"changed"';return value;};
 const attempts=t.creates.length;await assert.rejects(run(t),/NATIVE_PIN_CHANGED/);assert.equal(t.creates.length,attempts);
});
test('late change after commit prevents reporting completion',async()=>{
 const t=transport();let guards=0;
 const guarded=async()=>{if(++guards===5){const first=[...t.store.values()][0];first.bytes=Buffer.from('changed after commit');}return recordProof();};
 await assert.rejects(run(t,fixture(),{verifyBindings:guarded}),/READBACK_MISMATCH/);
 assert.equal(t.events.some(e=>e.event==='association_complete'),false);
});
test('held, altered-key or premature acceptance handoffs refuse before native reads',async()=>{
 for(const change of [{state:'held-locator-evidence'},{replayKey:'0'.repeat(64)},{occurrenceKey:'0'.repeat(64)},
  {nativeMutationAllowed:true},{providedEvidenceAuthenticated:true},{checkpointAllowed:true},{fullAcquisitionQualified:true},{clinicalApplicabilityAccepted:true}]){
  const t=transport();let reads=0;t.client.get=async()=>{reads++;return null;};
  await assert.rejects(run(t,{...fixture(),...change}),/ASSOCIATION_/);assert.equal(reads,0);assert.equal(t.creates.length,0);
 }
});
test('source/capture endpoint drift and receipt size bounds refuse preparation',()=>{
 let h=fixture();h.selectedRecords.capture.data.nativeURL='https://example.sharepoint.com/sites/Fictional/other.pdf';assert.throws(()=>planAssociation(h),/SELECTED_RECORDS/);
 h=fixture();h.selectedRecords.capture.data.humanNotes='x'.repeat(1024*1024);assert.throws(()=>planAssociation(h),/RECEIPT_LIMIT/);
});
test('missing qualified guard cannot use the injected native transport',async()=>{
 const t=transport();await assert.rejects(run(t,fixture(),{verifyBindings:null}),/QUALIFIED_TRANSPORT/);assert.equal(t.creates.length,0);
});
test('an unrelated HTTP 500 remains uncertain, with no blind retry or false commit',async()=>{
 const t=transport();let attempts=0;t.client.create=async()=>{attempts++;const e=Error('fictional server failure');e.status=500;throw e;};
 await assert.rejects(run(t),error=>error.message==='ASSOCIATION_CREATE_UNCERTAIN'&&error.status===500);
 assert.equal(attempts,1);assert.equal(t.store.size,0);assert.equal(t.events.some(e=>e.event==='association_complete'),false);
});

test('a commit with a missing member is held for recovery instead of recreated',async()=>{
 const t=transport();const result=await run(t);t.store.delete(result.files[0].name);
 const attempts=t.creates.length;await assert.rejects(run(t),/COMMITTED_SET_INCOMPLETE/);
 assert.equal(t.creates.length,attempts);assert.equal(t.store.size,2);
});
