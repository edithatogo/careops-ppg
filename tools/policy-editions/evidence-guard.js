/* Pure companion to lifecycle/validate.js. No authority decision or native writes. */
function validateEditionEvidence(input = {}) {
  const reasons = [];
  const text = v => typeof v === 'string' && v.trim().length > 0;
  const sha = v => /^[a-f0-9]{64}$/i.test(v || '');
  const time = v => text(v) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString().slice(0,19) === v.slice(0,19);
  const {edition = {}, authorised = {}, published = {}, route = {}, decision = {}, publication = {}, actorEvidence = {}, replacements = []} = input;
  const fixture = input.mode === 'fictional-qualification';
  if (!['fictional-qualification','operational-evidence'].includes(input.mode)) reasons.push('invalid-mode');
  if (!time(input.observedAtUtc)) reasons.push('invalid-observation-time');
  if (!text(edition.PPGDocumentUID) || !text(edition.PPGPolicyEdition)) reasons.push('edition-identity-missing');
  if (!text(route.reference) || !text(route.revision) || !sha(route.sourceSHA256) || !text(route.category) || !text(route.requiredRole)) reasons.push('route-evidence-missing');
  if (!fixture && route.currentAuthorityConfirmed !== true) reasons.push('route-authority-unconfirmed');
  if (fixture && [edition, authorised, published, route, decision, publication, actorEvidence].some(v => v.FictionalTest !== true)) reasons.push('fixture-boundary-missing');
  if (actorEvidence.role !== route.requiredRole || actorEvidence.decisionEventUID !== decision.EventUID || !text(actorEvidence.responderIdentity) || !text(actorEvidence.signatureEvidenceReference) || !text(actorEvidence.roleEvidenceReference)) reasons.push('responder-evidence-missing');
  for (const [label, pin] of [['authorised',authorised],['published',published]]) {
    if (pin.DocumentUID !== edition.PPGDocumentUID || pin.policyEdition !== edition.PPGPolicyEdition || !text(pin.resourceReference) || !text(pin.nativeVersionRef) || !sha(pin.sha256)) reasons.push(label + ':invalid-pin');
  }
  if (decision.ReviewedVersionRef !== authorised.nativeVersionRef || decision.DocumentSHA256 !== authorised.sha256 || decision.DocumentReference !== authorised.resourceReference || !text(decision.EventUID)) reasons.push('decision:revision-mismatch');
  if (published.sha256 !== authorised.sha256) reasons.push('publication:bytes-changed');
  if (!text(publication.EventUID) || publication.ParentEventUID !== decision.EventUID || publication.PublicationURL !== published.resourceReference || publication.PublishedVersionRef !== published.nativeVersionRef) reasons.push('publication:receipt-mismatch');
  if (published.downloadedSHA256 !== published.sha256 || !text(published.receiptReference) || !time(published.readbackAtUtc) || (time(published.readbackAtUtc) && time(input.observedAtUtc) && Date.parse(published.readbackAtUtc) > Date.parse(input.observedAtUtc))) reasons.push('publication:native-readback-missing');
  if (!fixture && (published.authoritativeDestinationConfirmed !== true || !text(published.destinationEvidenceReference))) reasons.push('publication:destination-unconfirmed');
  // Edges supplement the existing single URL field; they never retire catalogue rows.
  const adjacency = new Map();
  const node = p => p && text(p.DocumentUID) && text(p.policyEdition) && sha(p.sha256) ? JSON.stringify([p.DocumentUID,p.policyEdition,p.sha256]) : null;
  const seen = new Set();
  if (!Array.isArray(replacements)) reasons.push('invalid-replacements');
  else for (const edge of replacements) {
    const from = node(edge && edge.replacement), to = node(edge && edge.replaced);
    if (!from || !to || !text(edge.evidenceReference) || (fixture && edge.FictionalTest !== true)) { reasons.push('replacement:incomplete'); continue; }
    if (from === to) reasons.push('replacement:self-reference');
    const key = JSON.stringify([from,to]);
    if (seen.has(key)) reasons.push('replacement:duplicate');
    seen.add(key);
    if (!adjacency.has(from)) adjacency.set(from,[]);
    adjacency.get(from).push(to);
  }
  // Iterative traversal keeps a long retained history independent of stack depth.
  const indegree = new Map();
  for (const [from, targets] of adjacency) {
    if (!indegree.has(from)) indegree.set(from, 0);
    for (const to of targets) indegree.set(to, (indegree.get(to) || 0) + 1);
  }
  const queue = [...indegree].filter(([, degree]) => degree === 0).map(([pin]) => pin);
  for (let i = 0; i < queue.length; i++) for (const to of adjacency.get(queue[i]) || []) {
    indegree.set(to, indegree.get(to) - 1);
    if (indegree.get(to) === 0) queue.push(to);
  }
  if (queue.length !== indegree.size) reasons.push('replacement:cycle');
  return {consistent:reasons.length === 0,reasons:[...new Set(reasons)],qualificationScope:fixture ? 'fictional-evidence-consistency-only' : 'operational-evidence-consistency-only',writesPerformed:0};
}
if (typeof module !== 'undefined') module.exports = {validateEditionEvidence};

/* Edition relationship/withdrawal receipts supplement existing fields/history.
   The purpose envelope is independent evidence, not a new native approval field. */
function editionTransitionIntent(input = {}) {
  const reasons = [];
  const text = v => typeof v === 'string' && v.trim().length > 0;
  const time = v => text(v) && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(v) && Number.isFinite(Date.parse(v)) && new Date(v).toISOString().slice(0,19) === v.slice(0,19);
  const pinKey = p => p && text(p.DocumentUID) && text(p.policyEdition) && text(p.resourceReference) && text(p.nativeVersionRef) && /^[a-f0-9]{64}$/i.test(p.sha256 || '') ? JSON.stringify([p.DocumentUID,p.policyEdition,p.resourceReference,p.nativeVersionRef,p.sha256]) : null;
  const {subject = {}, decision = {}, purposeEvidence = {}, route = {}} = input;
  const fixture = input.mode === 'fictional-qualification';
  if (!['fictional-qualification','operational-evidence'].includes(input.mode)) reasons.push('invalid-mode');
  if (!['replace','withdraw'].includes(input.operation)) reasons.push('unsupported-operation');
  if (!pinKey(subject) || subject.downloadedSHA256 !== subject.sha256) reasons.push('subject:unverified-pin');
  if (!text(input.expectedETag) || input.expectedETag.trim() === '*' || input.expectedETag !== input.observedETag) reasons.push('subject:stale-version');
  if (!time(input.observedAtUtc)) reasons.push('invalid-observation-time');
  const decisionSubject = input.operation === 'replace' ? (input.replacementPublication?.authorised || {}) : subject;
  if (!text(decision.EventUID) || decision.DocumentReference !== decisionSubject.resourceReference || decision.ReviewedVersionRef !== decisionSubject.nativeVersionRef || decision.DocumentSHA256 !== decisionSubject.sha256 || decision.Stage !== 'Decision' || decision.RecordState !== 'Recorded' || decision.DecisionOutcome !== 'Approved (recorded)' || !['None recorded','Resolved'].includes(decision.ConditionsState) || !text(decision.DecisionReference)) reasons.push('decision:wrong-or-incomplete');
  if (!time(decision.OccurredOn)) reasons.push('decision:invalid-chronology');
  if (purposeEvidence.decisionEventUID !== decision.EventUID || purposeEvidence.purpose !== input.operation || !text(purposeEvidence.reference) || pinKey(purposeEvidence.subject) !== pinKey(subject)) reasons.push('decision:purpose-unproven');
  if (!text(route.reference) || !text(route.revision) || !/^[a-f0-9]{64}$/i.test(route.sourceSHA256 || '') || (!fixture && route.currentAuthorityConfirmed !== true)) reasons.push('route:unconfirmed');
  if (fixture && [subject,decision,purposeEvidence,route].some(p => p.FictionalTest !== true)) reasons.push('fixture-boundary-missing');
  if (input.operation === 'replace') {
    const publication = validateEditionEvidence(input.replacementPublication);
    reasons.push(...publication.reasons.map(r => 'replacement:' + r));
    if (input.replacementPublication?.mode !== input.mode) reasons.push('replacement:mode-mismatch');
    const replacement = input.replacementPublication?.published;
    if (!pinKey(replacement) || pinKey(replacement) === pinKey(subject) || pinKey(purposeEvidence.replacement) !== pinKey(replacement)) reasons.push('replacement:wrong-edition');
  }
  return {reasons,text,time,pinKey,subject,decision,purposeEvidence,route,fixture};
}

/* Proposal check has no effect/readback requirement and grants no write right. */
function validateEditionTransitionProposal(input = {}) {
  const object = v => v && typeof v === 'object' && !Array.isArray(v);
  const invalid = !object(input) || !['subject','decision','purposeEvidence','route'].every(k => object(input[k])) ||
    (input.operation === 'replace' && (!object(input.replacementPublication) ||
      !['edition','authorised','published','route','decision','publication','actorEvidence'].every(k => object(input.replacementPublication[k]))));
  if (invalid) return {consistent:false,reasons:['proposal:malformed-evidence'],qualificationScope:'fictional-transition-proposal-only',nativeWriterEnabled:false,writesPerformed:0};
  const {reasons,time,decision} = editionTransitionIntent(input);
  if (input.mode !== 'fictional-qualification') reasons.push('proposal:native-generalisation-unqualified');
  if (Object.hasOwn(input,'effect')) reasons.push('proposal:unexpected-effect');
  if (time(decision.OccurredOn) && time(input.observedAtUtc) && Date.parse(decision.OccurredOn) > Date.parse(input.observedAtUtc)) reasons.push('decision:invalid-chronology');
  return {consistent:reasons.length === 0,reasons:[...new Set(reasons)],qualificationScope:'fictional-transition-proposal-only',nativeWriterEnabled:false,writesPerformed:0};
}
if (typeof module !== 'undefined') module.exports.validateEditionTransitionProposal = validateEditionTransitionProposal;

function validateEditionTransitionEvidence(input = {}) {
  const {reasons,text,time,pinKey,subject,decision,fixture} = editionTransitionIntent(input);
  const {effect = {}} = input;
  if (time(decision.OccurredOn) && time(effect.readbackAtUtc) && Date.parse(decision.OccurredOn) > Date.parse(effect.readbackAtUtc)) reasons.push('decision:invalid-chronology');
  if (fixture && effect.FictionalTest !== true) reasons.push('fixture-boundary-missing');
  if (!text(effect.receiptReference) || effect.decisionEventUID !== decision.EventUID || pinKey(effect.subject) !== pinKey(subject) || effect.historyRetained !== true || !time(effect.readbackAtUtc) || (time(effect.readbackAtUtc) && time(input.observedAtUtc) && Date.parse(effect.readbackAtUtc) > Date.parse(input.observedAtUtc))) reasons.push('effect:unverified-receipt');
  if (input.operation === 'withdraw') {
    if (effect.outcome !== 'withdrawn-from-active-projection' || effect.activeProjectionState !== 'withdrawn' || !text(effect.activeProjectionEvidenceReference)) reasons.push('withdrawal:active-state-unproven');
  }
  if (input.operation === 'replace') {
    const replacement = input.replacementPublication?.published;
    if (pinKey(effect.replacement) !== pinKey(replacement)) reasons.push('replacement:wrong-edition');
    if (effect.outcome !== 'replaced-in-active-projection' || effect.activeProjectionState !== 'superseded' || !text(effect.activeProjectionEvidenceReference)) reasons.push('replacement:active-state-unproven');
  }
  return {consistent:reasons.length === 0,reasons:[...new Set(reasons)],qualificationScope:fixture ? 'fictional-transition-evidence-only' : 'operational-transition-evidence-only',writesPerformed:0};
}
if (typeof module !== 'undefined') module.exports.validateEditionTransitionEvidence = validateEditionTransitionEvidence;

/* Complete, read-only relationship snapshot. A successful local check never
   enables a native writer or turns an archive capture into an issued edition. */
function validateEditionRelationships(input = {}) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) input = {};
  const reasons = [];
  const text = v => typeof v === 'string' && v.trim().length > 0;
  const key = p => p && ['DocumentUID','policyEdition','resourceReference','nativeVersionRef'].every(k => text(p[k])) && /^[a-f0-9]{64}$/.test(p.sha256 || '')
    ? JSON.stringify([p.DocumentUID,p.policyEdition,p.resourceReference,p.nativeVersionRef,p.sha256]) : null;
  const {nodes = [], relationships = [], proposed = {}} = input;
  const snapshot = input.snapshot || {};
  if (input.mode !== 'fictional-qualification') reasons.push('native-generalisation-unqualified');
  if (snapshot.complete !== true || snapshot.hasNextLink !== false || !text(snapshot.evidenceReference)
      || !text(snapshot.beforeToken) || snapshot.beforeToken.trim() === '*' || snapshot.beforeToken !== snapshot.afterToken) reasons.push('graph:incomplete-or-changed');
  const inventory = new Map(), identities = new Set();
  if (!Array.isArray(nodes)) reasons.push('graph:invalid-nodes');
  else for (const node of nodes) {
    const pin = key(node), identity = node && JSON.stringify([node.DocumentUID,node.policyEdition]);
    if (!pin || node.FictionalTest !== true || node.downloadedSHA256 !== node.sha256) { reasons.push('graph:unverified-node'); continue; }
    if (inventory.has(pin) || identities.has(identity)) reasons.push('graph:ambiguous-identity');
    inventory.set(pin,node); identities.add(identity);
  }
  const adjacency = new Map(), seen = new Set();
  const edges = Array.isArray(relationships) ? [...relationships,proposed] : [proposed];
  if (!Array.isArray(relationships)) reasons.push('graph:invalid-relationships');
  for (const edge of edges) {
    const from = key(edge && edge.replacement), to = key(edge && edge.replaced);
    if (!from || !to || edge.FictionalTest !== true || !text(edge.evidenceReference)) { reasons.push('graph:incomplete-edge'); continue; }
    if (!inventory.has(from) || !inventory.has(to)) reasons.push('graph:unknown-target');
    for (const pin of [from,to]) {
      const node = inventory.get(pin);
      if (node && (node.representationKind !== 'issued' || !text(node.issuedReceiptReference))) reasons.push('graph:archive-only-or-unissued');
    }
    // One policy edition cannot replace itself under a different file/version/hash.
    if (edge.replacement.DocumentUID === edge.replaced.DocumentUID && edge.replacement.policyEdition === edge.replaced.policyEdition) reasons.push('graph:self-link');
    const pair = JSON.stringify([from,to]);
    if (seen.has(pair)) reasons.push('graph:duplicate-edge');
    seen.add(pair);
    if (!adjacency.has(from)) adjacency.set(from,[]);
    adjacency.get(from).push(to);
  }
  // Iterative topological traversal also handles long chains without recursion.
  const indegree = new Map();
  for (const [from,targets] of adjacency) {
    if (!indegree.has(from)) indegree.set(from,0);
    for (const to of targets) indegree.set(to,(indegree.get(to) || 0)+1);
  }
  const queue = [...indegree].filter(([,degree]) => degree === 0).map(([pin]) => pin);
  for (let i=0; i<queue.length; i++) for (const to of adjacency.get(queue[i]) || []) {
    indegree.set(to,indegree.get(to)-1);
    if (indegree.get(to) === 0) queue.push(to);
  }
  if (queue.length !== indegree.size) reasons.push('graph:cycle');
  return {consistent:reasons.length === 0,reasons:[...new Set(reasons)],
    qualificationScope:'fictional-relationship-consistency-only',nativeWriterEnabled:false,
    controlledPublicationQualified:false,writesPerformed:0};
}
if (typeof module !== 'undefined') module.exports.validateEditionRelationships = validateEditionRelationships;
