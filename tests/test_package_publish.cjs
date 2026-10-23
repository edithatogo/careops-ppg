'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {run}=require('../tools/unattended-package/run.cjs');
const {publish,sha}=require('../tools/unattended-package/publish.cjs');
const {prepare}=require('../tools/unattended-package/prepare-selected.cjs');
(async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'ppg-publish-'));
 try{
  const input=path.join(root,'in'),output=path.join(root,'out');await fs.mkdir(input);await fs.mkdir(output);
  const bytes=Buffer.from('Fictional draft — untouched\n'),job={schemaVersion:1,jobId:'job-cli-proof',metadata:{caseUID:'fictional-case',title:'CLI qualification',version:'DRAFT-1',sourceBaseline:'fictional frozen snapshot'},attachments:[{path:'draft.md',role:'draft',sha256:sha(bytes)}]};
  const jobFile=path.join(root,'job.json');await fs.writeFile(jobFile,JSON.stringify(job));await fs.writeFile(path.join(input,'draft.md'),bytes);await run(jobFile,input,output);
  const dir=path.join(output,job.jobId),store=new Map(),events=[],writes=[];
  const client={get:async name=>store.has(name)?{bytes:Buffer.from(store.get(name)),pin:{name,version:'1.0'}}:null,
   create:async(name,value)=>{if(store.has(name))throw Error('COLLISION');store.set(name,Buffer.from(value));writes.push(name);}};
  const journal=async e=>events.push(e);
  assert.equal((await publish(dir,client,journal)).state,'published');assert.deepEqual(writes,[job.jobId+'.zip',job.jobId+'.receipt.json']);
  assert.equal((await publish(dir,client,journal)).state,'replayed');assert.equal(writes.length,2);
  const receiptName=job.jobId+'.receipt.json',zipName=job.jobId+'.zip';store.delete(receiptName);
  assert.equal((await publish(dir,client,journal)).state,'published');assert.equal(writes.length,3);assert.equal(writes[2],receiptName);
  store.set(zipName,Buffer.from('human edit'));await assert.rejects(publish(dir,client,journal),/REMOTE_REVISION_CONFLICT/);assert.equal(store.get(zipName).toString(),'human edit');assert.equal(writes.length,3);
  // A conflicting receipt is refused before package creation.
  store.delete(zipName);store.set(receiptName,Buffer.from('edited receipt'));await assert.rejects(publish(dir,client,journal),/REMOTE_REVISION_CONFLICT/);assert.equal(writes.length,3);
  store.clear();let attempts=0;
  const uncertain={...client,create:async(name,value)=>{attempts++;store.set(name,Buffer.from(value));throw Error('TRANSPORT_LOST');}};
  await assert.rejects(publish(dir,uncertain,journal),/TRANSPORT_LOST/);assert.equal(attempts,1);
  assert.equal((await publish(dir,client,journal)).state,'published');assert.equal(attempts,1);
  // Publication never rewrites an input/template; byte identity is retained.
  assert.deepEqual(await fs.readFile(path.join(input,'draft.md')),bytes);
  const original=await fs.readFile(path.join(dir,'package.zip'));await fs.writeFile(path.join(dir,'package.zip'),'tampered');
  await assert.rejects(publish(dir,client,journal),/LOCAL_PACKAGE_CONTRACT_INVALID/);await fs.writeFile(path.join(dir,'package.zip'),original);
  let gets=0;const changing={...client,get:async name=>{const r=await client.get(name);if(++gets===3)r.pin.version='2.0';return r;}};
  await assert.rejects(publish(dir,changing,journal),/REMOTE_PIN_CHANGED/);
  const selection={schemaVersion:1,kind:'existing-case-artifact-selection',sourceWrites:false,caseWrites:false,wordGenerationPerformed:false,
   caseBinding:{CaseUID:'fictional-case',sourceBaselineRef:'frozen-baseline'},catalogueBinding:{records:[{DocumentUID:'fictional-record',sourceSnapshotRef:'frozen-baseline'}]},
   authoringProvenance:{status:'unknown',generationReceipt:null},sources:[]};
  for(const [name,role] of [['baseline.zip','recorded-baseline'],['draft.docx','existing-manual-draft']]){
   await fs.writeFile(path.join(input,name),bytes);selection.sources.push({file:name,role,bytes:bytes.length,sha256:sha(bytes),sourceReference:'fictional source',zipCRCVerified:true,nativePin:{UniqueId:'fictional-file',ETag:'"1"',UIVersionLabel:'1.0',Length:String(bytes.length)}});
  }
  const selectedFile=path.join(input,'selection.json'),metadataFile=path.join(root,'metadata.json'),preparedJob=path.join(root,'prepared.json');
  await fs.writeFile(selectedFile,JSON.stringify(selection));await fs.writeFile(metadataFile,JSON.stringify({...job.metadata,sourceBaseline:'wrong'}));
  await assert.rejects(prepare(selectedFile,metadataFile,preparedJob,'job-selected'),/RECORDED_METADATA_BINDING_MISMATCH/);
  await fs.writeFile(metadataFile,JSON.stringify({...job.metadata,sourceBaseline:'frozen-baseline'}));
  assert.equal((await prepare(selectedFile,metadataFile,preparedJob,'job-selected')).selectedRecords,1);
  assert.equal((await run(preparedJob,input,output)).state,'generated');
  await assert.rejects(prepare(selectedFile,metadataFile,preparedJob,'job-selected'),/EEXIST/);
  await fs.writeFile(path.join(input,'draft.docx'),'changed');await assert.rejects(prepare(selectedFile,metadataFile,path.join(root,'new.json'),'job-selected-new'),/FROZEN_SOURCE_CHANGED/);
  console.log('Passed package publication: create-only receipt-last order, replay, partial recovery, edit/conflict refusal, uncertain-write reconciliation and input preservation.');
 }finally{await fs.rm(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
