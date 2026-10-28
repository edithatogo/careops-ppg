/* Compose existing read-only proposal and after-effect evidence checks.
   Neither result is a native writer, approval or authority grant. */
// Load after lifecycle/validate.js and evidence-guard.js in the same script
// context, as for the existing pure guards. No new runtime or module loader.
const replacementLifecycleCheck = validateLifecycleTransition;
const replacementEditionChecks = {validateEditionEvidence, validateEditionTransitionEvidence, validateEditionTransitionProposal, validateEditionRelationships};

function validateReplacementBundle(input, phase) {
  const reasons = [];
  const object = value => value && typeof value === 'object' && !Array.isArray(value);
  const result = checks => ({consistent:reasons.length === 0, reasons:[...new Set(reasons)], checks,
    qualificationScope:phase === 'proposal' ? 'fictional-replacement-proposal-consistency-only' : 'fictional-replacement-bundle-consistency-only',
    nativeWriterEnabled:false, controlledPublicationQualified:false, actorAuthorityQualified:false,
    writesPerformed:0});
  if (!object(input) || !['lifecycle','publication','transition','graph'].every(k => object(input[k]))) {
    reasons.push('bundle:missing-evidence'); return result({});
  }
  const {lifecycle, publication, transition, graph} = input;
  if (input.mode !== 'fictional-qualification' ||
      [publication,transition,graph].some(value => value.mode !== input.mode)) reasons.push('bundle:mode-mismatch');
  if (lifecycle.operation !== 'record-publication' || transition.operation !== 'replace') reasons.push('bundle:unsupported-operation');
  // Reject malformed records before calling legacy checks, whose input contract
  // assumes object-shaped selected events and pins.
  if (!Array.isArray(lifecycle.events) || lifecycle.events.some(e => !object(e)) ||
      !object(lifecycle.selected) || !object(lifecycle.scope) ||
      !['edition','authorised','published','route','decision','publication','actorEvidence'].every(k => object(publication[k])) ||
      !['subject','decision','purposeEvidence','route','replacementPublication',...(phase === 'effect' ? ['effect'] : [])].every(k => object(transition[k])) ||
      !['edition','authorised','published','route','decision','publication','actorEvidence'].every(k => object(transition.replacementPublication[k]))) {
    reasons.push('bundle:malformed-evidence'); return result({});
  }
  const checks = {
    lifecycle:replacementLifecycleCheck(lifecycle),
    publication:replacementEditionChecks.validateEditionEvidence(publication),
    transition:phase === 'proposal' ? replacementEditionChecks.validateEditionTransitionProposal(transition) : replacementEditionChecks.validateEditionTransitionEvidence(transition),
    graph:replacementEditionChecks.validateEditionRelationships(graph)
  };
  for (const [name,check] of Object.entries(checks)) reasons.push(...check.reasons.map(reason => name+':'+reason));
  const equalFields = (a,b,fields) => object(a) && object(b) && fields.every(k => a[k] !== undefined && a[k] === b[k]);
  const pinFields = ['DocumentUID','policyEdition','resourceReference','nativeVersionRef','sha256'];
  const authorised = publication.authorised, issued = publication.published;
  const scope = lifecycle.scope;
  if (scope.DocumentReference !== authorised.resourceReference || scope.ReviewedVersionRef !== authorised.nativeVersionRef ||
      scope.DocumentSHA256 !== authorised.sha256) reasons.push('bundle:lifecycle-publication-scope-mismatch');
  const decision = lifecycle.events.find(e => e.EventUID === lifecycle.selected.decision);
  const publishedEvent = lifecycle.events.find(e => e.EventUID === lifecycle.selected.publication);
  // Require one shared publication snapshot, including route and actor evidence.
  // Independently passing checks over different snapshots cannot be spliced.
  const equalEvidence = (left,right) => {
    const pairs = [[left,right]];
    for (let i=0; i<pairs.length; i++) {
      if (i >= 100000) return false;
      const [a,b] = pairs[i];
      if (a === b) continue;
      if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false;
      if (Array.isArray(a) && a.length !== b.length) return false;
      const ak = Object.keys(a).sort(), bk = Object.keys(b).sort();
      if (ak.length !== bk.length || ak.some((key,index) => key !== bk[index])) return false;
      for (const key of ak) pairs.push([a[key],b[key]]);
    }
    return true;
  };
  if (!equalEvidence(decision,publication.decision)) reasons.push('bundle:publication-decision-mismatch');
  if (!equalEvidence(publishedEvent,publication.publication)) reasons.push('bundle:publication-event-mismatch');
  const purposeDecision = lifecycle.events.find(e => e.EventUID === transition.decision.EventUID);
  if (!purposeDecision || !equalEvidence(purposeDecision,transition.decision) ||
      !equalFields(purposeDecision,scope,['CaseUID','DocumentReference','ReviewedVersionRef','DocumentSHA256'])) reasons.push('bundle:purpose-decision-snapshot-mismatch');
  if (!equalEvidence(transition.replacementPublication,publication)) reasons.push('bundle:transition-publication-mismatch');
  if (!equalFields(graph.proposed?.replacement,issued,pinFields) ||
      !equalFields(graph.proposed?.replaced,transition.subject,pinFields)) reasons.push('bundle:graph-transition-pin-mismatch');
  if ([lifecycle,publication,transition].some(value => value.observedAtUtc !== input.observedAtUtc)) reasons.push('bundle:observation-mismatch');
  return result(checks);
}
function validateReplacementEvidenceBundle(input = {}) { return validateReplacementBundle(input,'effect'); }
function validateReplacementProposalBundle(input = {}) { return validateReplacementBundle(input,'proposal'); }
if (typeof module !== 'undefined') module.exports = {validateReplacementEvidenceBundle,validateReplacementProposalBundle};
