'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {publishSources}=require('../tools/cited-evidence/publish-sources.cjs');
const {sha}=require('../tools/unattended-package/publish.cjs');
(async()=>{const root=await fs.mkdtemp(path.join(os.tmpdir(),'ppg-source-publication-'));
 try{await fs.mkdir(path.join(root,'sources'));const raw=Buffer.from('FICTIONAL source\n'),name='source-test-r1-edition-one.txt';
  await fs.writeFile(path.join(root,'sources',name),raw);
  const manifest={schemaVersion:1,kind:'cli-assistant-source-preparation-v1',preparationId:'source-test-r1',originalSourceWrites:false,wordBodyGenerationPerformed:false,conversationalRetrievalQualified:false,
   sources:[{sourceId:'edition-one',name,bytes:raw.length,sha256:sha(raw),expectedTextSHA256:sha(raw),authorityLabel:'captured-reference-unconfirmed'}]};
  await fs.writeFile(path.join(root,'manifest.json'),JSON.stringify(manifest));const store=new Map(),writes=[];
  const client={get:async name=>store.has(name)?{bytes:Buffer.from(store.get(name)),pin:{UniqueId:'fictional-uuid',ETag:'"1"',ServerRelativeUrl:'/sites/ppg/evidence/'+name}}:null,
   create:async(name,bytes)=>{if(store.has(name))throw Error('COLLISION');store.set(name,Buffer.from(bytes));writes.push(name);}};
  const journal=async()=>{};const r=await publishSources(root,client,journal);assert.equal(r.state,'published');assert.equal(r.originalSourceWrites,false);assert.equal(r.selected[0].sourceId,'edition-one');
  assert.deepEqual(writes,[name,'source-test-r1.sources.json']);assert.equal((await publishSources(root,client,journal)).state,'replayed');assert.equal(writes.length,2);
  store.delete('source-test-r1.sources.json');assert.equal((await publishSources(root,client,journal)).state,'published');assert.equal(writes.length,3);
  store.set(name,Buffer.from('human edit'));await assert.rejects(publishSources(root,client,journal),/REMOTE_REVISION_CONFLICT/);assert.equal(store.get(name).toString(),'human edit');
  await fs.writeFile(path.join(root,'sources',name),'changed');await assert.rejects(publishSources(root,client,journal),/PREPARED_SOURCE_CHANGED/);
  console.log('Passed source publication: exact copies, manifest-last commit, replay, partial recovery, edited-file preservation and local-integrity refusal.');
 }finally{await fs.rm(root,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1;});
