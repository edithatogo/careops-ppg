const test=require('node:test'),assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs');
const context=vm.createContext({});
for(const file of ['tools/lifecycle/validate.js','tools/policy-editions/evidence-guard.js','tools/policy-editions/relationship-bundle.js'])vm.runInContext(fs.readFileSync(file,'utf8'),context);
const check=context.validateReplacementEvidenceBundle;
const copy=x=>JSON.parse(JSON.stringify(x));
function fixture(){
 const publication=copy(require('../config/policy-edition-guard-fixtures.json').publication);
 const now=publication.observedAtUtc;
 const scope={CaseUID:'FICTIONAL-case',DocumentReference:publication.authorised.resourceReference,
  ReviewedVersionRef:publication.authorised.nativeVersionRef,DocumentSHA256:publication.authorised.sha256};
 const common={...scope,FictionalTest:true,ActorName:'FICTIONAL actor',OccurredOn:'2026-10-17T06:00:00Z',
  EvidenceReference:'fictional://evidence',ConditionsState:'None recorded',RecordState:'Recorded',Summary:'Fictional qualification only'};
 const ready={...common,EventUID:'ready',Finding:'Ready for decision',AssessorName:'FICTIONAL assessor',AssessedOn:common.OccurredOn,FindingSummary:'Fictional consistency only'};
 publication.decision={...common,...publication.decision,Stage:'Decision',DecisionOutcome:'Approved (recorded)',DecisionReference:'fictional://publication-decision',ReadinessEventUID:'ready'};
 publication.publication={...common,...publication.publication,Stage:'Publication'};
 const events=[{...common,EventUID:'offer',EventKind:'Ownership handoff',RecordState:'Proposed',FromRole:'FICTIONAL proposer',SubjectRole:'FICTIONAL owner'},
  {...common,EventUID:'accepted',EventKind:'Ownership handoff',RecordState:'Accepted',FromRole:'FICTIONAL proposer',SubjectRole:'FICTIONAL owner',ParentEventUID:'offer'},
  ready,copy(publication.decision),copy(publication.publication)];
 const subject={FictionalTest:true,DocumentUID:'fictional-policy-a',policyEdition:'1.0',resourceReference:'https://example.invalid/old-issued',nativeVersionRef:'1.0',sha256:'c'.repeat(64),downloadedSHA256:'c'.repeat(64)};
 const decision={...common,EventUID:'replace-purpose',Stage:'Decision',DecisionOutcome:'Approved (recorded)',DecisionReference:'fictional://replace'};
 const transition={mode:'fictional-qualification',operation:'replace',observedAtUtc:now,expectedETag:'"old"',observedETag:'"old"',subject,decision,
  route:copy(publication.route),replacementPublication:copy(publication),
  purposeEvidence:{FictionalTest:true,decisionEventUID:decision.EventUID,purpose:'replace',subject:copy(subject),replacement:copy(publication.published),reference:'fictional://replace-purpose'},
  effect:{FictionalTest:true,decisionEventUID:decision.EventUID,subject:copy(subject),replacement:copy(publication.published),historyRetained:true,receiptReference:'fictional://effect',readbackAtUtc:'2026-10-17T07:00:00Z',outcome:'replaced-in-active-projection',activeProjectionState:'superseded',activeProjectionEvidenceReference:'fictional://projection'}};
 events.push(copy(decision));
 const node=pin=>({...copy(pin),representationKind:'issued',issuedReceiptReference:'fictional://issued/'+pin.policyEdition});
 return {mode:'fictional-qualification',observedAtUtc:now,publication,transition,
  lifecycle:{operation:'record-publication',scope,observedAtUtc:now,expectedETag:'"case"',observedETag:'"case"',events,selected:{ownership:'accepted',readiness:'ready',decision:publication.decision.EventUID,publication:publication.publication.EventUID}},
  graph:{mode:'fictional-qualification',nodes:[node(subject),node(publication.published)],relationships:[],
   proposed:{FictionalTest:true,replacement:node(publication.published),replaced:node(subject),evidenceReference:'fictional://edge'},
   snapshot:{complete:true,hasNextLink:false,evidenceReference:'fictional://graph-snapshot',beforeToken:'"graph"',afterToken:'"graph"'}}};
}
test('one bound after-effect bundle composes all checks without enabling a writer',()=>{
 const f=fixture(),before=JSON.stringify(f),r=check(f);assert.equal(r.consistent,true,JSON.stringify(r.reasons));
 assert.deepEqual(Object.keys(r.checks),['lifecycle','publication','transition','graph']);assert.equal(JSON.stringify(f),before);
 for(const k of ['nativeWriterEnabled','controlledPublicationQualified','actorAuthorityQualified'])assert.equal(r[k],false);assert.equal(r.writesPerformed,0);
});
test('individually valid publication snapshots cannot be spliced through route or actor changes',()=>{
 for(const mutate of [f=>f.transition.replacementPublication.route.reference='fictional://other-route',f=>f.transition.replacementPublication.actorEvidence.signatureEvidenceReference='fictional://other-signature']){
  const f=fixture();mutate(f);const r=check(f);assert.equal(r.checks.transition.consistent,true);assert.ok(r.reasons.includes('bundle:transition-publication-mismatch'));
 }
});
test('lifecycle and publication events must refer to the same snapshots',()=>{
 for(const mutate of [f=>f.publication.decision.EventUID='other-decision',f=>f.publication.publication.EventUID='other-publication',f=>f.lifecycle.scope.DocumentReference='other-version']){
  const f=fixture();mutate(f);assert.equal(check(f).consistent,false);
 }
});
test('graph cannot target an unrelated but individually valid issued edition',()=>{
 const f=fixture(),other={...f.graph.nodes[0],policyEdition:'0.9',resourceReference:'https://example.invalid/other'};
 f.graph.nodes.push(other);f.graph.proposed.replaced=other;const r=check(f);assert.equal(r.checks.graph.consistent,true);assert.ok(r.reasons.includes('bundle:graph-transition-pin-mismatch'));
});
test('graph refusals propagate into the combined result',()=>{
 for(const [reason,mutate] of [['graph:self-link',f=>f.graph.proposed.replaced=f.graph.proposed.replacement],['graph:cycle',f=>f.graph.relationships.push({...f.graph.proposed,replacement:f.graph.proposed.replaced,replaced:f.graph.proposed.replacement})],['graph:unknown-target',f=>f.graph.nodes.pop()],['graph:archive-only-or-unissued',f=>f.graph.nodes[0].representationKind='archive-capture']]){
  const f=fixture();mutate(f);assert.ok(check(f).reasons.includes('graph:'+reason),reason);
 }
});
test('missing native snapshot evidence, stale case and unresolved findings all hold',()=>{
 for(const mutate of [f=>f.graph.snapshot.complete=false,f=>f.lifecycle.observedETag='"changed"',f=>f.lifecycle.events[2].Finding='Needs changes',f=>f.lifecycle.events[2].ConditionsState='Open',f=>f.transition.purposeEvidence.purpose='publish']){
  const f=fixture();mutate(f);assert.equal(check(f).consistent,false);
 }
});
test('observation and mode must agree; operational mode cannot enable this fictional contract',()=>{
 for(const mutate of [f=>f.observedAtUtc='2026-10-18T00:00:00Z',f=>f.mode='operational-evidence',f=>f.transition.operation='withdraw']){
  const f=fixture();mutate(f);assert.equal(check(f).consistent,false);assert.equal(check(f).nativeWriterEnabled,false);
 }
});
test('malformed envelopes fail without calling incompatible legacy contracts',()=>{
 for(const f of [null,[],{}, {...fixture(),publication:null}])assert.equal(check(f).consistent,false);
 const f=fixture();f.transition.replacementPublication.published=null;assert.equal(check(f).consistent,false);
});
test('shared JSON snapshot equivalence ignores object key order without ignoring evidence',()=>{
 const f=fixture();f.transition.replacementPublication=Object.fromEntries(Object.entries(f.transition.replacementPublication).reverse());assert.equal(check(f).consistent,true);
});

test('full selected records and purpose decisions cannot be replaced by matching-ID fragments',()=>{
 for(const [reason,mutate] of [
  ['bundle:publication-decision-mismatch',f=>f.publication.decision.ActorName='FICTIONAL different actor'],
  ['bundle:publication-event-mismatch',f=>f.publication.publication.ConditionsNotes='changed snapshot'],
  ['bundle:purpose-decision-snapshot-mismatch',f=>f.lifecycle.events=f.lifecycle.events.filter(e=>e.EventUID!==f.transition.decision.EventUID)],
  ['bundle:purpose-decision-snapshot-mismatch',f=>f.transition.decision.CaseUID='unrelated-case']]){
  const f=fixture();mutate(f);assert.ok(check(f).reasons.includes(reason),reason);
 }
});

const proposalCheck=context.validateReplacementProposalBundle;
function proposalFixture(){const f=fixture();delete f.transition.effect;return f;}
test('proposal uses genuine existing evidence without requiring or inventing a future effect',()=>{
 const f=proposalFixture(),before=JSON.stringify(f),r=proposalCheck(f);assert.equal(r.consistent,true,JSON.stringify(r.reasons));
 assert.equal(JSON.stringify(f),before);assert.equal(r.nativeWriterEnabled,false);assert.equal(r.controlledPublicationQualified,false);assert.equal(r.writesPerformed,0);
 assert.equal(check(f).consistent,false); // Post-effect contract still requires actual readback.
});
test('effect receipts cannot be smuggled into a before-write proposal',()=>{
 const f=fixture();assert.ok(proposalCheck(f).reasons.includes('transition:proposal:unexpected-effect'));
});
test('purpose, chronology, whitespace wildcard and stale subject guards precede proposed effects',()=>{
 for(const mutate of [f=>f.transition.purposeEvidence.purpose='publish',f=>f.transition.decision.OccurredOn='2026-10-18T00:00:00Z',f=>f.transition.expectedETag=f.transition.observedETag=' * ',f=>f.transition.observedETag='changed']){
  const f=proposalFixture();mutate(f);assert.equal(proposalCheck(f).consistent,false);
 }
});
test('proposal propagates all graph refusals with no native writer qualification',()=>{
 for(const mutate of [f=>f.graph.proposed.replaced=f.graph.proposed.replacement,f=>f.graph.relationships.push({...f.graph.proposed,replacement:f.graph.proposed.replaced,replaced:f.graph.proposed.replacement}),f=>f.graph.nodes.pop(),f=>f.graph.nodes[0].representationKind='archive-capture',f=>f.graph.snapshot.hasNextLink=true]){
  const f=proposalFixture();mutate(f);const r=proposalCheck(f);assert.equal(r.consistent,false);assert.equal(r.nativeWriterEnabled,false);
 }
});
test('proposal requires exact shared snapshots and all lifecycle prerequisites',()=>{
 for(const mutate of [f=>f.transition.replacementPublication.route.reference='fictional://other',f=>f.lifecycle.selected.ownership='absent',f=>f.publication.publication.EventUID='unrelated',f=>f.mode='operational-evidence']){
  const f=proposalFixture();mutate(f);assert.equal(proposalCheck(f).consistent,false);
 }
});
test('malformed proposal evidence holds visibly without exception',()=>{
 for(const f of [null,[],{}, {...proposalFixture(),transition:null}])assert.equal(proposalCheck(f).consistent,false);
 const f=proposalFixture();f.transition.replacementPublication.actorEvidence=null;assert.equal(proposalCheck(f).consistent,false);
});
