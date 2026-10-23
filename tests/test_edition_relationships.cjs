const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm'), fs = require('node:fs');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync('tools/policy-editions/evidence-guard.js','utf8'),context);
const check = context.validateEditionRelationships;
function fixture() {
  const nodes = [1,2,3].map(n => ({FictionalTest:true,DocumentUID:'fictional-policy',policyEdition:String(n),
    resourceReference:'https://example.invalid/issued/'+n,nativeVersionRef:'1.0',sha256:String(n).repeat(64),
    downloadedSHA256:String(n).repeat(64),representationKind:'issued',issuedReceiptReference:'fictional://receipt/'+n}));
  const edge = (replacement,replaced) => ({FictionalTest:true,replacement,replaced,evidenceReference:'fictional://relationship'});
  return {mode:'fictional-qualification',nodes,relationships:[edge(nodes[1],nodes[0])],proposed:edge(nodes[2],nodes[1]),
    snapshot:{complete:true,hasNextLink:false,evidenceReference:'fictional://complete-graph',beforeToken:'"1"',afterToken:'"1"'}};
}
test('arbitrary issued chain and multiple predecessors are pure local consistency checks', () => {
  const f=fixture(), before=JSON.stringify(f); f.relationships.push({...f.proposed,replaced:f.nodes[0]});
  const r=check(f);assert.equal(r.consistent,true);assert.equal(r.nativeWriterEnabled,false);assert.equal(r.controlledPublicationQualified,false);
  assert.equal(r.writesPerformed,0);f.relationships.pop();assert.equal(JSON.stringify(f),before);
});
test('self link, indirect cycle, unknown target and archive-only targets hold', () => {
  for (const [reason,mutate] of [
    ['graph:self-link', f => f.proposed.replaced=f.proposed.replacement],
    ['graph:cycle', f => {f.proposed.replacement=f.nodes[0];f.proposed.replaced=f.nodes[1];}],
    ['graph:unknown-target', f => f.nodes.pop()],
    ['graph:archive-only-or-unissued', f => f.nodes[0].representationKind='archive-capture'],
    ['graph:archive-only-or-unissued', f => delete f.nodes[1].issuedReceiptReference],
  ]) { const f=fixture();mutate(f);assert.ok(check(f).reasons.includes(reason),reason); }
});
test('changed exact pins, duplicate identities/edges, incomplete and stale snapshots hold', () => {
  const mutations=[f=>f.proposed.replaced={...f.nodes[1],sha256:'f'.repeat(64)},
    f=>f.nodes.push({...f.nodes[0],nativeVersionRef:'2.0'}),f=>f.relationships.push(f.proposed),
    f=>f.snapshot.complete=false,f=>f.snapshot.hasNextLink=true,f=>f.snapshot.afterToken='"2"',
    f=>f.nodes[0].downloadedSHA256='f'.repeat(64),f=>f.nodes[0].FictionalTest=false];
  for(const mutate of mutations){const f=fixture();mutate(f);assert.equal(check(f).consistent,false);}
});
test('operational use and missing evidence never enable general native publication', () => {
  const f=fixture();f.mode='operational-evidence';assert.ok(check(f).reasons.includes('native-generalisation-unqualified'));
  assert.equal(check({}).consistent,false);assert.equal(check({}).nativeWriterEnabled,false);
});
test('malformed envelopes and whitespace wildcard tokens fail visibly without throwing',()=>{
 for(const value of [null,[],{snapshot:null},{nodes:null},{relationships:null},{proposed:null}]) assert.equal(check(value).consistent,false);
 const f=fixture();f.snapshot.beforeToken=f.snapshot.afterToken=' * ';assert.equal(check(f).consistent,false);
});
