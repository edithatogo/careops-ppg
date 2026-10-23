const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ctx = vm.createContext({});
vm.runInContext(fs.readFileSync('tools/lifecycle/validate.js', 'utf8'), ctx);
const check = ctx.validateLifecycleEvidence;
const transition = ctx.validateLifecycleTransition;
function fixture() {
  const scope = {CaseUID:'fictional-case', DocumentReference:'fictional-document', ReviewedVersionRef:'1.0', DocumentSHA256:'a'.repeat(64)};
  const common = {...scope, ActorName:'Fictional actor', OccurredOn:'2026-10-17T00:00:00Z', EvidenceReference:'fictional-evidence', ConditionsState:'None recorded', RecordState:'Recorded',Summary:'Fictional rationale',FindingSummary:'Fictional rationale'};
  const events = [
    {...common, EventUID:'r', Finding:'Ready for decision', AssessorName:'Fictional assessor', AssessedOn:'2026-10-17T00:00:00Z'},
    {...common, EventUID:'d', Stage:'Decision', DecisionOutcome:'Approved (recorded)', DecisionReference:'fictional-decision', ReadinessEventUID:'r'},
    {...common, EventUID:'p', Stage:'Publication', PublicationURL:'https://example.invalid/fictional', PublishedVersionRef:'1.0', ParentEventUID:'d'},
    {...common, EventUID:'i', Stage:'Implementation', ImplementationActions:'fictional action', ParentEventUID:'p'},
    {...common, EventUID:'v', Stage:'Verification', VerificationMethod:'fictional check', VerificationResult:'Verified (recorded)', ParentEventUID:'i'}
  ];
  return {scope, observedAtUtc:'2026-10-17T01:00:00Z', expectedETag:'etag-1', observedETag:'etag-1', events, selected:{readiness:'r',decision:'d',publication:'p',implementation:'i',verification:'v'}};
}
test('existing event field mappings support a consistent chain without mutations or authorisation result',()=>{
 const f=fixture(), before=JSON.stringify(f), r=check(f);assert.equal(r.consistent,true);assert.equal(r.writesPerformed,0);assert.equal(JSON.stringify(f),before);assert.equal(r.policyApproved,undefined);
});
test('changed case or document version prevents reliance on prior findings',()=>{
 for(const mutate of [f=>f.observedETag='etag-2',f=>f.events[0].ReviewedVersionRef='2.0',f=>f.events[0].DocumentSHA256='b'.repeat(64)]){const f=fixture();mutate(f);assert.equal(check(f).consistent,false);}
});
test('endorsement, rejection, deferral and unresolved conditions never pass approval evidence',()=>{
 for(const outcome of ['Endorsed (recorded)','Rejected','Deferred']){const f=fixture();f.events[1].DecisionOutcome=outcome;assert.equal(check(f).consistent,false);}
 const f=fixture();f.events[1].ConditionsState='Open';assert.equal(check(f).consistent,false);
});
test('duplicate identities, superseded events and cross-case parents fail closed',()=>{
 for(const mutate of [f=>f.events.push({...f.events[0]}),f=>f.events.push({EventUID:'later',SupersedesEventUID:'d'}),f=>f.events[1].CaseUID='another-case',f=>f.events[2].ParentEventUID='wrong']){const f=fixture();mutate(f);assert.equal(check(f).consistent,false);}
});
test('missing parent selections cannot be satisfied by an unselected event',()=>{const f=fixture();delete f.selected.decision;assert.equal(check(f).consistent,false);});
test('ownership acceptance requires exact matching proposal and human evidence',()=>{
 const f=fixture(), common={...f.events[1],EventKind:'Ownership handoff',FromRole:'Fictional sender',SubjectRole:'Fictional owner'};
 f.events=[{...common,EventUID:'offer',RecordState:'Proposed'},{...common,EventUID:'accept',RecordState:'Accepted',ParentEventUID:'offer'}];f.selected={ownership:'accept'};
 assert.equal(check(f).consistent,true);f.events[0].SubjectRole='different';assert.equal(check(f).consistent,false);
});
test('empty and unknown selections do not pass',()=>{for(const selected of [{},{invented:'d'}]){const f=fixture();f.selected=selected;assert.equal(check(f).consistent,false);}});

test('future or calendar-invalid evidence and missing rationale fail',()=>{for(const mutate of [f=>f.events[1].OccurredOn='2026-10-18T00:00:00Z',f=>f.events[0].AssessedOn='2026-02-30T00:00:00Z',f=>delete f.events[0].FindingSummary,f=>delete f.observedAtUtc]){const f=fixture();mutate(f);assert.equal(check(f).consistent,false);}});
test('operation gate rejects omitted prerequisites and unknown operations',()=>{const f=fixture();f.operation='record-publication';f.selected={readiness:'r',decision:'d',publication:'p'};assert.equal(transition(f).consistent,false);f.operation='invented';assert.equal(transition(f).consistent,false);});
test('complete closure requires exact accepted ownership alongside whole evidence chain',()=>{const f=fixture();const c={...f.events[1],EventKind:'Ownership handoff',FromRole:'Fictional sender',SubjectRole:'Fictional owner'};f.events.push({...c,EventUID:'offer',RecordState:'Proposed'},{...c,EventUID:'accept',RecordState:'Accepted',ParentEventUID:'offer'});f.selected.ownership='accept';f.operation='close-review';assert.equal(transition(f).consistent,true);delete f.selected.verification;assert.equal(transition(f).consistent,false);});

test('wildcard case tokens cannot disable concurrency protection',()=>{const f=fixture();f.expectedETag=f.observedETag='*';assert.equal(check(f).consistent,false);});
test('dependent events cannot predate their selected parent evidence',()=>{for(const index of [1,2,3,4]){const f=fixture();f.events[index].OccurredOn='2026-10-16T00:00:00Z';assert.equal(check(f).consistent,false);}});

test('failed or inconclusive verification cannot advance even after conditions are marked resolved',()=>{
 for(const result of ['Failed','Inconclusive']){
  const f=fixture();
  f.events[4].VerificationResult=result;
  f.events[4].ConditionsState='Resolved';
  assert.equal(check(f).consistent,false);
  const ownership={...f.events[1],EventKind:'Ownership handoff',FromRole:'Fictional sender',SubjectRole:'Fictional owner'};
  f.events.push({...ownership,EventUID:'offer',RecordState:'Proposed'},{...ownership,EventUID:'accept',RecordState:'Accepted',ParentEventUID:'offer'});
  f.selected.ownership='accept';f.operation='close-review';
  assert.equal(transition(f).consistent,false);
 }
});

test('readiness finding, condition and decision combinations cannot promote a held assessment',()=>{
 const findings=['Not assessed','Needs changes','Ready for decision','Not applicable'];
 const conditions=['Unknown','None recorded','Open','Resolved'];
 const outcomes=['Unknown','Endorsed (recorded)','Approved (recorded)','Rejected','Deferred'];
 for(const finding of findings) for(const condition of conditions) for(const outcome of outcomes){
  const f=fixture();f.events[0].Finding=finding;f.events[0].ConditionsState=condition;f.events[1].DecisionOutcome=outcome;
  const expected=finding==='Ready for decision' && ['None recorded','Resolved'].includes(condition) && outcome==='Approved (recorded)';
  assert.equal(check(f).consistent,expected,JSON.stringify({finding,condition,outcome}));
 }
});
