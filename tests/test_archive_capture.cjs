const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');
const source = fs.readFileSync('tools/archive-capture/apply-metadata.js', 'utf8');

async function trial({alreadySet = false, changedBytes = false, conflictingValue = false} = {}) {
  const original = Buffer.from('original');
  const sha = createHash('sha256').update(original).digest('hex');
  const fields = {PPGCaptureSHA256:sha, PPGCaptureKind:'Document'};
  const item = {Id:1, PPGCurrency:'Unconfirmed', PPGCaptureSHA256:alreadySet?sha:conflictingValue?'human value':null, PPGCaptureKind:alreadySet?'Document':null};
  const writes=[];
  const context = vm.createContext({crypto:webcrypto, fetch:async(url, options={})=>{
    if(url.endsWith('/contextinfo'))return Response.json({FormDigestValue:'digest'});
    if(options.headers?.['X-HTTP-Method']==='MERGE'){
      assert.equal(options.headers['IF-MATCH'],'"item,1"');
      const patch=JSON.parse(options.body);writes.push(patch);Object.assign(item,patch);
      return new Response(null,{status:204});
    }
    if(url.endsWith('/$value'))return new Response(changedBytes?Buffer.from('modified'):original);
    if(url.endsWith('/ListItemAllFields'))return Response.json(item,{headers:{ETag:'"item,1"'}});
    return Response.json({UniqueId:'native-id',Length:'8',ETag:'"file,1"',UIVersionLabel:'1.0'});
  }});
  vm.runInContext(source,context);
  const state={};
  await context.applyCaptureMetadata('/site','library',[{path:'/site/archive/a.pdf',uniqueId:'native-id',bytes:8,sha256:sha,fields}],state);
  return {state,writes,item};
}

test('changed original bytes refuse any metadata write', async()=>{
  const {state,writes}=await trial({changedBytes:true});
  assert.equal(state.state,'failed');assert.match(state.error,/Original bytes differ/);assert.equal(writes.length,0);
});
test('existing differing metadata preserves the human value', async()=>{
  const {state,writes,item}=await trial({conflictingValue:true});
  assert.equal(state.state,'failed');assert.equal(item.PPGCaptureSHA256,'human value');assert.equal(writes.length,0);
});
test('matching metadata reapplication does not create a version', async()=>{
  const {state,writes}=await trial({alreadySet:true});
  assert.equal(state.state,'completed');assert.equal(writes.length,0);assert.equal(state.receipts.length,1);
});
test('new metadata uses exact ETag and preserves business status', async()=>{
  const {state,writes,item}=await trial();
  assert.equal(state.state,'completed');assert.equal(writes.length,1);assert.equal(item.PPGCurrency,'Unconfirmed');
  assert.deepEqual(Object.keys(writes[0]).sort(),['PPGCaptureKind','PPGCaptureSHA256']);
});

async function editionTrial({catalogueDrift=false,manualEdit=false,alreadyLinked=false}={}) {
  const bytes=Buffer.from('original'),sha=createHash('sha256').update(bytes).digest('hex');
  const row={path:'/site/archive/a.pdf',sha256:sha,bytes:8,sourceAlias:'EXAMPLE-Proc-1-V2-01/26',sourceEdition:'2.0',existingDocumentUID:'11111111-1111-4111-8111-111111111111',catalogueItemId:7,headerTextSHA256:'header-proof'};
  const evidence=JSON.stringify({sourceAlias:row.sourceAlias,sourceEdition:row.sourceEdition,existingDocumentUID:row.existingDocumentUID,catalogueItemId:7,headerTextSHA256:row.headerTextSHA256,sourceSHA256:sha,method:'Fresh first-page Document Number and printed Version; exact unique native catalogue alias; not currency verification'});
  const item={Id:1,PPGCaptureSHA256:sha,PPGCurrency:'Unconfirmed',PPGDocumentUID:manualEdit?'human identity':alreadyLinked?row.existingDocumentUID:null,PPGPolicyEdition:alreadyLinked?'2.0':null,PPGCaptureEditionEvidence:alreadyLinked?evidence:null};
  const writes=[];
  const context=vm.createContext({crypto:webcrypto,fetch:async(url,opts={})=>{
    if(url.includes('/items?'))return Response.json({value:[{Id:7,sourceDocumentId:row.sourceAlias,DocumentUID:catalogueDrift?'changed':row.existingDocumentUID}]});
    if(url.endsWith('/contextinfo'))return Response.json({FormDigestValue:'digest'});
    if(opts.headers?.['X-HTTP-Method']==='MERGE'){assert.equal(opts.headers['IF-MATCH'],'"item,1"');const patch=JSON.parse(opts.body);writes.push(patch);Object.assign(item,patch);return new Response(null,{status:204})}
    if(url.endsWith('/$value'))return new Response(bytes);
    if(url.endsWith('/ListItemAllFields'))return Response.json(item,{headers:{ETag:'"item,1"'}});
    return Response.json({UniqueId:'native-id',Length:'8',UIVersionLabel:'2.0'});
  }});
  vm.runInContext(fs.readFileSync('tools/archive-capture/apply-edition-links.js','utf8'),context);
  const state={};await context.applyEditionLinks('/site','library','catalogue',[row],state);return{state,writes,item};
}

test('edition link refuses catalogue drift and existing human identity',async()=>{
  for(const options of [{catalogueDrift:true},{manualEdit:true}]){const {state,writes}=await editionTrial(options);assert.equal(state.state,'failed');assert.equal(writes.length,0)}
});
test('edition link writes only evidenced identity/edition and separate evidence',async()=>{
  const {state,writes,item}=await editionTrial();assert.equal(state.state,'completed');assert.deepEqual(Object.keys(writes[0]).sort(),['PPGCaptureEditionEvidence','PPGDocumentUID','PPGPolicyEdition']);assert.equal(item.PPGCurrency,'Unconfirmed');
});
test('exact edition link reapplication makes no native mutation',async()=>{
  const {state,writes}=await editionTrial({alreadyLinked:true});assert.equal(state.state,'completed');assert.equal(writes.length,0);
});
