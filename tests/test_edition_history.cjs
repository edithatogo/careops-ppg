const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {webcrypto,createHash}=require('node:crypto');
const source=fs.readFileSync('tools/archive-capture/edition-history.js','utf8');
const sha=raw=>createHash('sha256').update(raw).digest('hex');
async function trial({complete=false,unknown=false,changedAtLock=false,currentLabel=null}={}){
 const root='/site/PPG Review Evidence/Templates/Native edition history qualification/';
 const originals=[Buffer.from('old edition'),Buffer.from('new edition')];
 let versions=complete?[...originals]:[unknown?Buffer.from('human edit'):originals[0]],checkout=2;
 const writes=[];
 const ctx=vm.createContext({crypto:webcrypto,URL,fetch:async(url,opt={})=>{
  const sourceIndex=url.includes('source1')?0:url.includes('source2')?1:-1;
  if(url.endsWith('/contextinfo'))return Response.json({FormDigestValue:'digest'});
  if(url.includes('/lists('))return Response.json({EnableVersioning:true,MajorVersionLimit:500,ForceCheckout:false,EnableModeration:false});
  if(sourceIndex>=0)return url.endsWith('/$value')?new Response(originals[sourceIndex]):Response.json({UniqueId:'source'+sourceIndex,ETag:'fixed',Length:String(originals[sourceIndex].length)});
  if(url.endsWith('/CheckOut()')){checkout=0;writes.push('checkout');if(changedAtLock)versions[versions.length-1]=Buffer.from('human edit');return new Response(null,{status:200});}
  if(url.includes('/CheckIn(')){checkout=2;writes.push('checkin');return new Response(null,{status:200});}
  if(opt.headers?.['X-HTTP-Method']==='PUT'){assert.equal(checkout,0);writes.push('content');versions.push(Buffer.from(opt.body));return new Response(null,{status:204});}
  if(url.endsWith('/$value')){const match=url.match(/Versions\((\d+)\)/);return new Response(versions[match?Number(match[1])-1:versions.length-1]);}
  if(url.includes('/Versions?'))return Response.json({value:versions.slice(0,-1).map((raw,i)=>({ID:i+1,VersionLabel:(i+1)+'.0',IsCurrentVersion:false}))});
  return Response.json({UniqueId:'target',ETag:'"file,1"',Length:'11',UIVersionLabel:currentLabel??versions.length+'.0',CheckOutType:checkout});
 }});
 vm.runInContext(source,ctx);
 const state={};await ctx.reconcileEditionHistory('https://example.invalid/site',{qualification:true,libraryId:'00000000-0000-0000-0000-000000000001',targetPath:root+'history.txt',editions:originals.map((raw,i)=>({sourcePath:root+'source'+(i+1)+'.txt',sourceEdition:(i+1)+'.0',order:i+1,orderEvidence:'explicit fixture order',bytes:raw.length,sha256:sha(raw)}))},state);
 return {state,writes,versions};
}
test('native append obtains lock before content and checks in; previous bytes remain downloadable',async()=>{
 const {state,writes}=await trial();assert.equal(state.state,'completed');assert.deepEqual(writes,['checkout','content','checkin']);assert.equal(state.versions.length,2);assert.equal(state.originalsPreserved,true);
});
test('complete native history is adopted with zero writes',async()=>{const {state,writes}=await trial({complete:true});assert.equal(state.state,'completed');assert.equal(state.writes,0);assert.deepEqual(writes,[])});
test('unknown existing content is preserved without checkout or overwrite',async()=>{const {state,writes}=await trial({unknown:true});assert.equal(state.state,'failed');assert.match(state.error,/Unknown or reordered/);assert.deepEqual(writes,[])});
test('change between inspection and checkout is held for recovery before content writes',async()=>{const {state,writes}=await trial({changedAtLock:true});assert.equal(state.state,'failed');assert.match(state.error,/changed before checkout/);assert.deepEqual(writes,['checkout']);assert.ok(state.checkedOutTarget)});

test('native version labels use numeric segments, preserving minor versions above nine',()=>{
 const ctx=vm.createContext({});vm.runInContext(source,ctx);
 assert.equal(JSON.stringify(['10.0','2.10','2.2'].sort(ctx.compareNativeVersionLabels)),JSON.stringify(['2.2','2.10','10.0']));
 assert.throws(()=>ctx.compareNativeVersionLabels('2.bad','2.1'),/Unknown native version/);
 assert.throws(()=>ctx.compareNativeVersionLabels('999999999999999999999','2.1'),/Unknown native version/);
});

test('unrecognised current native version holds before mutation',async()=>{
 const {state,writes}=await trial({complete:true,currentLabel:'unknown'});
 assert.equal(state.state,'failed');assert.match(state.error,/Unknown native version label/);assert.deepEqual(writes,[]);
});
