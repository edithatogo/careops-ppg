const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const fields=require('../config/policy-edition-fields.json');
const views=require('../config/policy-edition-views.json');
const source=fs.readFileSync('tools/policy-editions/maintain.js','utf8');
const binding={base:'/teams/Fictional',libraryId:'00000000-0000-0000-0000-000000000001',fieldConfig:fields,viewConfig:views};
function audit(fetch){return vm.runInNewContext(source+';maintainPolicyEditions',{fetch,URL});}
test('unsafe site bindings are refused before any native read',async()=>{
  for(const base of [null,'//example.invalid','/','/teams/Fictional/','/teams/Fictional/../Other','/teams/%2e%2e/Other','/teams/Fictional?other=1','/teams/Fictional#fragment','/teams\\Other','/teams/ Fictional']){
    let calls=0;const run=audit(async()=>{calls++;throw Error('must not fetch');});
    await assert.rejects(()=>run({...binding,base}),/Unqualified binding/);assert.equal(calls,0);
  }
});
test('a malformed library identity is refused before any native read',async()=>{
  for(const libraryId of ['-'.repeat(36),'a'.repeat(36),null]){
    let calls=0;const run=audit(async()=>{calls++;throw Error('must not fetch');});
    await assert.rejects(()=>run({...binding,libraryId}),/Unqualified binding/);assert.equal(calls,0);
  }
});
test('qualified bindings use a read-only request and preserve a native access refusal',async()=>{
  const calls=[];const run=audit(async(url,options)=>{calls.push({url,options});return {ok:false,status:403};});
  await assert.rejects(()=>run(binding),/403/);assert.equal(calls.length,1);
  assert.ok(calls[0].url.startsWith(binding.base+"/_api/web/lists(guid'"+binding.libraryId+"')"));
  assert.equal(calls[0].options.method,'GET');assert.equal(calls[0].options.body,undefined);
});
test('truncated field inventories stop before adopting apparently matching first-page fields',async()=>{
  for(const key of ['@odata.nextLink','odata.nextLink','nextLink']){
    const calls=[];const run=audit(async(url,options)=>{
      calls.push(options);return {ok:true,json:async()=>calls.length===1?{EnableVersioning:true}:{value:[],[key]:'fictional://next'}};
    });
    await assert.rejects(()=>run(binding),/Incomplete.*native collection/);assert.equal(calls.length,2);
    assert.ok(calls.every(x=>x.method==='GET'&&x.body===undefined));
  }
});
test('legacy continuation and a saturated native page also stop read-only',async()=>{
  for(const page of [{value:[],d:{__next:'fictional://next'}},{value:Array.from({length:5000},()=>({}))}]){
    let calls=0;const run=audit(async()=>({ok:true,json:async()=>++calls===1?{EnableVersioning:true}:page}));
    await assert.rejects(()=>run(binding),/Incomplete.*native collection/);assert.equal(calls,2);
  }
});
