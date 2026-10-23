const test = require('node:test');
const assert = require('node:assert/strict');
const ctx = require('node:vm').createContext({});
require('node:vm').runInContext(require('node:fs').readFileSync('tools/policy-editions/evidence-guard.js','utf8'),ctx);
const check = ctx.validateEditionEvidence;
const fixture = require('../config/policy-edition-guard-fixtures.json').publication;
const copy = () => structuredClone(fixture);
const fails = (edit, reason) => { const f=copy(); edit(f); assert.ok(check(f).reasons.includes(reason)); };
test('fictional minor edition and different native version labels are valid evidence',()=>{
  const f=copy(), before=JSON.stringify(f), r=check(f);
  assert.equal(r.consistent,true); assert.equal(r.writesPerformed,0);
  assert.equal(r.qualificationScope,'fictional-evidence-consistency-only');
  assert.equal(JSON.stringify(f),before);
});
test('changed approved bytes hold publication',()=>fails(f=>f.published.sha256='c'.repeat(64),'publication:bytes-changed'));
test('decision pins exact native revision',()=>fails(f=>f.decision.ReviewedVersionRef='5.0','decision:revision-mismatch'));
test('URL alone is not native readback',()=>fails(f=>delete f.published.downloadedSHA256,'publication:native-readback-missing'));
test('entered actor name cannot replace responder evidence',()=>fails(f=>{f.decision.ActorName='Someone';delete f.actorEvidence.signatureEvidenceReference;},'responder-evidence-missing'));
test('fictional qualification cannot silently consume real records',()=>fails(f=>delete f.published.FictionalTest,'fixture-boundary-missing'));
test('operational mode holds unconfirmed route and destination',()=>{
  const f=copy();f.mode='operational-evidence'; const r=check(f);
  assert.ok(r.reasons.includes('route-authority-unconfirmed'));
  assert.ok(r.reasons.includes('publication:destination-unconfirmed'));
});
test('replacement graph permits multiple predecessors and rejects cycles',()=>{
  const f=copy();const a=f.authorised,b={...a,policyEdition:'1.0',sha256:'d'.repeat(64)},c={...a,DocumentUID:'fictional-policy-b',sha256:'e'.repeat(64)};
  const edge=(x,y)=>({replacement:x,replaced:y,FictionalTest:true,evidenceReference:'fictional-replacement'});
  f.replacements=[edge(a,b),edge(a,c)];assert.equal(check(f).consistent,true);
  f.replacements.push(edge(b,a));assert.ok(check(f).reasons.includes('replacement:cycle'));
});
test('self replacement and incomplete identity fail',()=>{
  fails(f=>f.replacements=[{replacement:f.authorised,replaced:f.authorised,FictionalTest:true,evidenceReference:'fixture'}],'replacement:self-reference');
  fails(f=>f.replacements=[{}],'replacement:incomplete');
});
test('future or malformed native observation fails',()=>{
  fails(f=>f.published.readbackAtUtc='2026-10-18T00:00:00Z','publication:native-readback-missing');
  fails(f=>f.observedAtUtc='2026-02-30T00:00:00Z','invalid-observation-time');
});
