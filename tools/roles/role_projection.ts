// Bounded Office Script projection. No workbook cells, sources or permissions change.
type Json = string | number | boolean | null | Json[] | { [key: string]: Json };
interface Role { roleId: string; title: string; scope: Json; holderKind: string }
interface Assignment { assignmentId: string; documentUID: string; roleId: string; responsibilityType: string; effectiveFrom: string; effectiveUntil: string | null; status: string; evidenceRef: string | null }
interface Appointment { appointmentId: string; roleId: string; holderId: string | null; appointmentKind: string; effectiveFrom: string; effectiveUntil: string | null; status: string; evidenceRef: string | null; delegationScope: Json; authorityEvidence: string | null }
interface Handover { handoverId: string; kind: string; fromRoleId: string; toRoleId: string; fromAppointmentId: string | null; toAppointmentId: string | null; documentUIDs: string[]; effectiveFrom: string; status: string; acceptedBy: string | null; acceptedAt: string | null; evidenceRef: string | null }
interface Model { roles: Role[]; assignments: Assignment[]; appointments: Appointment[]; handovers: Handover[]; historicalDecisions: Json[] }
interface Resolution { state: string; holderId: string | null; appointmentIds: string[]; grantsAccess: boolean }
interface Responsibility extends Assignment { roleTitle: string; resolution: Resolution; concurrentAssignmentIds: string[]; delegationScope: Json; grantsClinicalAuthority: boolean }
interface Projection { schemaVersion: number; asOf: string; responsibilities: Responsibility[]; historicalDecisions: Json[]; handovers: Handover[]; notificationsEnabled: boolean; sourceModified: boolean; accessModified: boolean }
interface NativeRow { [key: string]: Json }
interface NativePage { value: NativeRow[]; 'odata.nextLink'?: string; '@odata.nextLink'?: string; __next?: string; nextLink?: string }
interface NativeBundle { roles: NativePage; assignments: NativePage; appointments: NativePage; handovers: NativePage; historicalDecisions?: Json[] }
const RESPONSIBILITIES = ['executive_accountability', 'custodian', 'author', 'review_lead', 'contributor', 'subject_expert', 'consumer_representative', 'consultee', 'endorser', 'authorising_officer', 'document_controller', 'publisher', 'implementation_lead', 'assurance_reviewer'];
const STATES = ['proposed', 'accepted', 'declined', 'ended', 'superseded'];
function date(value: string): string {
  if (typeof value !== 'string' || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value) || value.slice(0, 4) === '0000') throw new Error('Role date must use Gregorian YYYY-MM-DD');
  const parsed = new Date(value + 'T00:00:00Z');
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) throw new Error('Invalid role calendar date');
  return value;
}
function unique<T>(rows: T[], getKey: (row: T) => string): Map<string, T> {
  const result = new Map<string, T>();
  for (const row of rows) { const key = getKey(row); if (typeof key !== 'string' || !key || result.has(key)) throw new Error('Missing or duplicate record identity'); result.set(key, row); }
  return result;
}
function active(row: { effectiveFrom: string; effectiveUntil: string | null }, day: string): boolean {
  const start = date(row.effectiveFrom), end = row.effectiveUntil === undefined || row.effectiveUntil === null || row.effectiveUntil === '' ? null : date(row.effectiveUntil);
  if (end !== null && end <= start) throw new Error('Invalid effective interval');
  return start <= day && (end === null || day < end);
}
function resolve(appointments: Appointment[], role: string, day: string): Resolution {
  const matches = appointments.filter(a => a.roleId === role && active(a, day));
  if (matches.length !== 1) return { state: matches.length ? 'ambiguous' : 'unconfirmed', holderId: null, appointmentIds: matches.map(a => a.appointmentId), grantsAccess: false };
  const item = matches[0];
  if (item.status !== 'accepted' || !item.evidenceRef) return { state: 'unconfirmed', holderId: null, appointmentIds: [item.appointmentId], grantsAccess: false };
  if (item.appointmentKind === 'vacant' && item.holderId) throw new Error('Vacancy cannot name a holder');
  return { state: item.appointmentKind === 'vacant' ? 'vacant' : item.holderId ? 'resolved' : 'unconfirmed', holderId: item.holderId ?? null, appointmentIds: [item.appointmentId], grantsAccess: false };
}
function projectModel(input: Model, onDate: string): Projection {
  // Copy at the boundary; every original appointment/decision remains untouched.
  const bundle = JSON.parse(JSON.stringify(input)) as Model, day = date(onDate);
  bundle.handovers = bundle.handovers ?? [];
  const roles = unique(bundle.roles, r => r.roleId), appointments = unique(bundle.appointments, r => r.appointmentId), assignments = unique(bundle.assignments, r => r.assignmentId);
  for (const a of bundle.appointments) {
    if (!roles.has(a.roleId) || !['substantive', 'acting', 'delegated', 'vacant'].includes(a.appointmentKind)) throw new Error('Unknown appointment role or kind');
    if (a.appointmentKind === 'vacant' && a.holderId) throw new Error('Vacancy cannot name a holder');
    if (a.appointmentKind === 'delegated' && (!a.delegationScope || !a.authorityEvidence)) throw new Error('Delegation needs scope and authority evidence');
    active(a, day);
  }
  unique(bundle.handovers, r => r.handoverId);
  for (const h of bundle.handovers) {
    if (!roles.has(h.fromRoleId) || !roles.has(h.toRoleId)) throw new Error('Unknown handover role');
    date(h.effectiveFrom);
    if (!Array.isArray(h.documentUIDs) || !h.documentUIDs.length || h.documentUIDs.some(uid => typeof uid !== 'string' || !uid)) throw new Error('Explicit handover document scope required');
    if (h.kind === 'succession') {
      const old = appointments.get(h.fromAppointmentId ?? ''), next = appointments.get(h.toAppointmentId ?? '');
      if (h.fromRoleId !== h.toRoleId || !old || !next || old.roleId !== h.fromRoleId || next.roleId !== h.fromRoleId || old.appointmentId === next.appointmentId || old.effectiveUntil !== h.effectiveFrom || next.effectiveFrom !== h.effectiveFrom) throw new Error('Succession appointments/dates do not meet');
    } else if (h.kind !== 'portfolio_transfer' || h.fromRoleId === h.toRoleId) throw new Error('Invalid handover kind or transfer roles');
    if (!STATES.includes(h.status)) throw new Error('Unknown handover status');
    if (h.status === 'accepted' && (!h.acceptedBy || !h.evidenceRef || typeof h.acceptedAt !== 'string' || !/(Z|[+-][0-9]{2}:[0-9]{2})$/.test(h.acceptedAt) || !Number.isFinite(Date.parse(h.acceptedAt)))) throw new Error('Accepted handover requires actor, timezone-bearing time and evidence');
  }
  const responsibilities: Responsibility[] = [];
  for (const row of bundle.assignments) {
    if (!roles.has(row.roleId) || !RESPONSIBILITIES.includes(row.responsibilityType) || !row.documentUID || !STATES.includes(row.status)) throw new Error('Unknown assignment role/responsibility/status or missing document');
    if (!active(row, day)) continue;
    let resolution = resolve(bundle.appointments, row.roleId, day);
    if (row.status !== 'accepted' || !row.evidenceRef) resolution = { state: 'unconfirmed_assignment', holderId: null, appointmentIds: [], grantsAccess: false };
    const peers = bundle.assignments.filter(a => a.assignmentId !== row.assignmentId && a.documentUID === row.documentUID && a.responsibilityType === row.responsibilityType && active(a, day));
    const selected = resolution.appointmentIds.length === 1 ? appointments.get(resolution.appointmentIds[0]) : undefined;
    if (selected?.appointmentKind === 'delegated') {
      const scope = selected.delegationScope;
      if (!scope || typeof scope !== 'object' || Array.isArray(scope) || !Array.isArray(scope.documentUIDs) || !scope.documentUIDs.includes(row.documentUID) || !Array.isArray(scope.responsibilityTypes) || !scope.responsibilityTypes.includes(row.responsibilityType)) resolution = { state: 'delegation_scope_unconfirmed', holderId: null, appointmentIds: resolution.appointmentIds, grantsAccess: false };
    }
    responsibilities.push({ ...row, roleTitle: roles.get(row.roleId)!.title, resolution, concurrentAssignmentIds: peers.map(a => a.assignmentId), delegationScope: selected?.delegationScope ?? null, grantsClinicalAuthority: false });
  }
  return { schemaVersion: 1, asOf: onDate, responsibilities, historicalDecisions: bundle.historicalDecisions ?? [], handovers: bundle.handovers, notificationsEnabled: false, sourceModified: false, accessModified: false };
}
function fromNative(native: NativeBundle): Model {
  function rows(page: NativePage): NativeRow[] { if (!page || !Array.isArray(page.value) || page['odata.nextLink'] || page['@odata.nextLink'] || page.__next || page.nextLink) throw new Error('Incomplete native export'); return page.value; }
  const value = (r: NativeRow, key: string): string | null => r[key] === undefined || r[key] === null ? null : r[key] as string;
  const roles = rows(native.roles).map(r => ({ roleId: r.RoleKey as string, title: r.Title as string, scope: r.Scope ?? null, holderKind: r.HolderKind as string }));
  const assignments = rows(native.assignments).map(r => ({ assignmentId: r.AssignmentKey as string, documentUID: r.DocumentUID as string, roleId: r.RoleKey as string, responsibilityType: r.ResponsibilityType as string, effectiveFrom: r.EffectiveFrom as string, effectiveUntil: value(r, 'EffectiveUntil'), status: (r.ReviewState as string).toLowerCase(), evidenceRef: value(r, 'EvidenceRef') }));
  const appointments = rows(native.appointments).map(r => { let scope: Json = r.DelegationScope ?? null; if (typeof scope === 'string' && scope) { try { scope = JSON.parse(scope) as Json; } catch { /* unstructured scope remains explicitly unconfirmed */ } } return { appointmentId: r.AppointmentKey as string, roleId: r.RoleKey as string, holderId: value(r, 'HolderKey'), appointmentKind: r.AppointmentKind as string, effectiveFrom: r.EffectiveFrom as string, effectiveUntil: value(r, 'EffectiveUntil'), status: (r.ReviewState as string).toLowerCase(), evidenceRef: value(r, 'EvidenceRef'), delegationScope: scope, authorityEvidence: value(r, 'AuthorityEvidence') }; });
  const handovers = rows(native.handovers).map(r => ({ handoverId: r.HandoverKey as string, kind: r.HandoverKind as string, fromRoleId: r.FromRoleKey as string, toRoleId: r.ToRoleKey as string, fromAppointmentId: value(r, 'FromAppointmentKey'), toAppointmentId: value(r, 'ToAppointmentKey'), documentUIDs: JSON.parse(r.DocumentUIDs as string) as string[], effectiveFrom: r.EffectiveFrom as string, status: (r.ReviewState as string).toLowerCase(), acceptedBy: value(r, 'AcceptedBy'), acceptedAt: value(r, 'AcceptedAt'), evidenceRef: value(r, 'EvidenceRef') }));
  return { roles, assignments, appointments, handovers, historicalDecisions: native.historicalDecisions ?? [] };
}
function main(workbook: ExcelScript.Workbook, requestJson: string): string {
  if (utf8(requestJson).length > 1000000) throw new Error('Role input exceeds bounded qualification size');
  const request = JSON.parse(requestJson) as { kind: string; native: NativeBundle; asOf: string; scriptSHA256: string; roleContractSHA256: string };
  if (request.kind !== 'ppg-role-projection-v1' || !/^[0-9a-f]{64}$/.test(request.scriptSHA256) || !/^[0-9a-f]{64}$/.test(request.roleContractSHA256)) throw new Error('Unsupported request or missing version pins');
  const sourceJson = JSON.stringify(request.native), sourceSha256 = sha256(utf8(sourceJson));
  const projection = projectModel(fromNative(request.native), request.asOf);
  const runKey = sha256(utf8([sourceSha256, request.asOf, request.scriptSHA256, request.roleContractSHA256].join('\n')));
  const manifest = { schemaVersion: 1, kind: 'office_script_role_snapshot', asOf: request.asOf, runKey,
    sourceSha256, projectionScriptSHA256: request.scriptSHA256, roleContractSha256: request.roleContractSHA256,
    historicalDecisions: projection.historicalDecisions, handovers: projection.handovers,
    historicalDecisionsCoverage: request.native.historicalDecisions ? 'supplied_snapshot_only' : 'not_retrieved_original_decisions_untouched',
    sourceModified: false, grantsAccess: false, grantsClinicalAuthority: false, notificationsEnabled: false,
    interpretation: 'Dated derived snapshot; no assignment, transfer or clinical decision is applied' };
  const records = projection.responsibilities.map(row => ({
    Title: Array.from(request.asOf + ' — ' + row.roleTitle).slice(0, 255).join(''),
    SnapshotKey: sha256(utf8(runKey + '\n' + row.assignmentId)), RunKey: runKey,
    AsOfDate: request.asOf, SourceSHA256: sourceSha256, DocumentUID: row.documentUID,
    AssignmentKey: row.assignmentId, RoleKey: row.roleId, ResponsibilityType: row.responsibilityType,
    HolderKey: row.resolution.holderId, ResolutionState: row.resolution.state,
    Projection: JSON.stringify(row), SourceManifest: JSON.stringify(manifest)
  }));
  // The workbook is only an execution container: no cell/file/network operations.
  const result = JSON.stringify({ manifest, projection, records, sourceJson });
  if (utf8(result).length > 1000000) throw new Error('Role output exceeds bounded qualification size');
  return result;
}

// Reuse the existing offline UTF-8/SHA-256 implementation in this self-contained script.
function utf8(text: string): number[] {
  const bytes: number[] = [];
  for (let i = 0; i < text.length; i++) {
    let cp = text.charCodeAt(i);
    if (cp >= 0xd800 && cp <= 0xdbff) {
      const lo = text.charCodeAt(++i);
      if (!(lo >= 0xdc00 && lo <= 0xdfff)) throw new Error("invalid_unicode");
      cp = 0x10000 + ((cp - 0xd800) << 10) + lo - 0xdc00;
    } else if (cp >= 0xdc00 && cp <= 0xdfff) throw new Error("invalid_unicode");
    if (cp < 0x80) bytes.push(cp);
    else if (cp < 0x800) bytes.push(0xc0 | (cp >>> 6), 0x80 | (cp & 63));
    else if (cp < 0x10000) bytes.push(0xe0 | (cp >>> 12), 0x80 | ((cp >>> 6) & 63), 0x80 | (cp & 63));
    else bytes.push(0xf0 | (cp >>> 18), 0x80 | ((cp >>> 12) & 63), 0x80 | ((cp >>> 6) & 63), 0x80 | (cp & 63));
  }
  return bytes;
}
function sha256(input: number[]): string {
  const k = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
  const h = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const data = input.slice(); const bits = input.length * 8;
  data.push(0x80); while (data.length % 64 !== 56) data.push(0);
  const high = Math.floor(bits / 0x100000000), low = bits >>> 0;
  for (const word of [high, low]) for (let j = 3; j >= 0; j--) data.push((word >>> (j * 8)) & 255);
  const rr = (v: number, n: number) => (v >>> n) | (v << (32 - n));
  for (let offset = 0; offset < data.length; offset += 64) {
    const w: number[] = [];
    for (let i = 0; i < 16; i++) w[i] = ((data[offset + 4*i] << 24) | (data[offset + 4*i+1] << 16) | (data[offset + 4*i+2] << 8) | data[offset + 4*i+3]) >>> 0;
    for (let i = 16; i < 64; i++) {
      const s0 = rr(w[i-15],7) ^ rr(w[i-15],18) ^ (w[i-15] >>> 3);
      const s1 = rr(w[i-2],17) ^ rr(w[i-2],19) ^ (w[i-2] >>> 10);
      w[i] = (w[i-16] + s0 + w[i-7] + s1) >>> 0;
    }
    let [a,b,c,d,e,f,g,j] = h;
    for (let i = 0; i < 64; i++) {
      const t1 = (j + (rr(e,6)^rr(e,11)^rr(e,25)) + ((e&f)^((~e)&g)) + k[i] + w[i]) >>> 0;
      const t2 = ((rr(a,2)^rr(a,13)^rr(a,22)) + ((a&b)^(a&c)^(b&c))) >>> 0;
      j=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
    }
    [a,b,c,d,e,f,g,j].forEach((v,i) => { h[i]=(h[i]+v)>>>0; });
  }
  return h.map(v => v.toString(16).padStart(8,"0")).join("");
}

