/* Pure evidence checks for reuse by native orchestration. No I/O or state changes.
   A passing result is evidence consistency, never authority or permission to act. */
function validateLifecycleEvidence({scope, expectedETag, observedETag, observedAtUtc, events, selected}) {
  const reasons = [];
  const nonblank = v => typeof v === 'string' && v.trim().length > 0;
  const keys = ['CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256'];
  if (!scope || keys.some(k => !nonblank(scope[k])) ||
      !/^[a-f0-9]{64}$/i.test(scope.DocumentSHA256 || '')) reasons.push('invalid-scope');
  if (!nonblank(expectedETag) || expectedETag.trim() === '*' || expectedETag !== observedETag) reasons.push('stale-case');
  if (!Array.isArray(events) || !selected || typeof selected !== 'object' || Array.isArray(selected)) {
    return {consistent:false, reasons:[...reasons, 'invalid-input'], writesPerformed:0};
  }
  const byId = new Map();
  for (const e of events) {
    if (!e || !nonblank(e.EventUID) || byId.has(e.EventUID)) reasons.push('ambiguous-event-identity');
    else byId.set(e.EventUID, e);
  }
  const superseded = new Set(events.filter(e => e && nonblank(e.SupersedesEventUID)).map(e => e.SupersedesEventUID));
  const found = {};
  const definitions = {
    ownership: e => e.EventKind === 'Ownership handoff' && e.RecordState === 'Accepted' && nonblank(e.FromRole) && nonblank(e.SubjectRole),
    readiness: e => e.Finding === 'Ready for decision',
    decision: e => e.Stage === 'Decision' && e.RecordState === 'Recorded' && e.DecisionOutcome === 'Approved (recorded)' && nonblank(e.DecisionReference),
    publication: e => e.Stage === 'Publication' && e.RecordState === 'Recorded' && nonblank(e.PublicationURL) && nonblank(e.PublishedVersionRef),
    implementation: e => e.Stage === 'Implementation' && e.RecordState === 'Recorded' && nonblank(e.ImplementationActions),
    verification: e => e.Stage === 'Verification' && e.RecordState === 'Recorded' && e.VerificationResult === 'Verified (recorded)' && nonblank(e.VerificationMethod)
  };
  const sameScope = e => scope && keys.every(k => e[k] === scope[k]);
  const time = v => nonblank(v) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString().slice(0,19) === v.slice(0,19);
  if (!time(observedAtUtc)) reasons.push('invalid-observation-time');
  for (const [kind, id] of Object.entries(selected)) {
    if (!Object.hasOwn(definitions, kind)) { reasons.push('unsupported-selection'); continue; }
    const e = byId.get(id);
    if (!e) { reasons.push(kind + ':missing'); continue; }
    found[kind] = e;
    if (!sameScope(e)) reasons.push(kind + ':wrong-version');
    if (superseded.has(id)) reasons.push(kind + ':superseded');
    if (!definitions[kind](e)) reasons.push(kind + ':incomplete-state');
    if (!nonblank(e[kind === 'readiness' ? 'AssessorName' : 'ActorName']) || !time(e[kind === 'readiness' ? 'AssessedOn' : 'OccurredOn']) || !nonblank(e.EvidenceReference)) reasons.push(kind + ':missing-human-evidence');
    const occurred = e[kind === 'readiness' ? 'AssessedOn' : 'OccurredOn'];
    if (time(occurred) && time(observedAtUtc) && Date.parse(occurred) > Date.parse(observedAtUtc)) reasons.push(kind + ':future-evidence');
    if (!nonblank(e[kind === 'readiness' ? 'FindingSummary' : 'Summary'])) reasons.push(kind + ':missing-rationale');
    if (!['None recorded', 'Resolved'].includes(e.ConditionsState)) reasons.push(kind + ':conditions-unresolved');
  }
  if (Object.keys(selected).length === 0) reasons.push('no-selected-evidence');
  for (const [child, parent, field] of [
    ['decision','readiness','ReadinessEventUID'],
    ['publication','decision','ParentEventUID'],
    ['verification','implementation','ParentEventUID']
  ]) {
    if (found[child] && (!found[parent] || found[child][field] !== found[parent].EventUID)) reasons.push(child + ':invalid-parent');
    if (found[child] && found[parent]) {
      const parentTime = found[parent][parent === 'readiness' ? 'AssessedOn' : 'OccurredOn'];
      if (time(found[child].OccurredOn) && time(parentTime) && Date.parse(found[child].OccurredOn) < Date.parse(parentTime)) reasons.push(child + ':predates-parent');
    }
  }
  if (found.implementation && !['decision', 'publication'].some(k => found[k] && found.implementation.ParentEventUID === found[k].EventUID)) reasons.push('implementation:invalid-parent');
  if (found.implementation) {
    const parent = ['decision', 'publication'].map(k => found[k]).find(e => e && found.implementation.ParentEventUID === e.EventUID);
    if (parent && time(parent.OccurredOn) && time(found.implementation.OccurredOn) && Date.parse(found.implementation.OccurredOn) < Date.parse(parent.OccurredOn)) reasons.push('implementation:predates-parent');
  }
  if (found.ownership) {
    const proposal = byId.get(found.ownership.ParentEventUID);
    if (!proposal || !sameScope(proposal) || proposal.EventKind !== 'Ownership handoff' ||
        proposal.RecordState !== 'Proposed' || proposal.FromRole !== found.ownership.FromRole ||
        proposal.SubjectRole !== found.ownership.SubjectRole || superseded.has(proposal.EventUID)) reasons.push('ownership:invalid-proposal');
    if (proposal && time(proposal.OccurredOn) && time(found.ownership.OccurredOn) && Date.parse(found.ownership.OccurredOn) < Date.parse(proposal.OccurredOn)) reasons.push('ownership:predates-proposal');
  }
  return {consistent:reasons.length === 0, reasons:[...new Set(reasons)], writesPerformed:0};
}
/* Technical prerequisite sets for explicit operations, not native CaseStatus values.
   Policy routes, actor authority and side effects remain the native caller's job. */
function validateLifecycleTransition(input) {
  const requirements = {
    'accept-ownership':['ownership'],
    'submit-for-decision':['ownership','readiness'],
    'record-decision':['ownership','readiness','decision'],
    'record-publication':['ownership','readiness','decision','publication'],
    'record-implementation':['ownership','readiness','decision','implementation'],
    'record-verification':['ownership','readiness','decision','implementation','verification'],
    'close-review':['ownership','readiness','decision','publication','implementation','verification']
  };
  const result = validateLifecycleEvidence(input);
  const required = Object.hasOwn(requirements, input.operation) ? requirements[input.operation] : null;
  if (!required) result.reasons.push('unsupported-operation');
  else for (const kind of required) if (!Object.hasOwn(input.selected || {}, kind)) result.reasons.push(kind + ':required');
  result.consistent = result.reasons.length === 0;
  return result;
}
if (typeof module !== 'undefined') module.exports = {validateLifecycleEvidence, validateLifecycleTransition};
