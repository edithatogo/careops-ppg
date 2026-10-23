type Scalar = string | number | boolean | null;
type Fields = { [key: string]: Scalar };
interface Alias { source: string; alias: string; DocumentUID: string; }
interface AbsenceAcknowledgement {
  DocumentUID: string; sourceSha256: string; baseContractHash: string;
  actor: string; evidenceReference: string; decisionEvidence: string; effect: string;
}
interface Ledger { sourceSystemId: string; aliases: { documentUID: string; sourceDocumentId: string; sourceRowAtBaseline?: number }[]; sourceAbsenceAcknowledgements?: AbsenceAcknowledgement[]; }
interface Extracted { schemaVersion: number; sheet: string; sheetNames: string[]; rowsIncludingHeader: number; columns: number; values: (string | number | boolean)[][]; dateFormats: { column: number; formats: string[] }[]; reviewTexts: string[]; }
/* Read an isolated copy only. Native flow binds the passed bytes to that copy
   with before/after exact-source metadata guards and retained raw acquisition. */
function main(workbook: ExcelScript.Workbook, rawBase64: string,
  identityLedgerJson: string, asOfUtc: string, snapshotRef: string, recordsRef: string,
  identityApplicationJson: string = "") {
  return buildCandidate(extractData(workbook), rawBase64, identityLedgerJson,
    asOfUtc, snapshotRef, recordsRef, identityApplicationJson);
}
function extractData(workbook: ExcelScript.Workbook): Extracted {
  const sheet = workbook.getWorksheet("Master Document Register");
  if (!sheet) throw new Error("source_sheet_missing");
  const used = sheet.getUsedRange(true);
  if (!used || used.getRowIndex() !== 0 || used.getColumnIndex() !== 0 ||
      used.getColumnCount() !== 25 || used.getRowCount() < 2 || used.getRowCount() > 10000)
    throw new Error("source_dimensions_unqualified");
  const count = used.getRowCount();
  return { schemaVersion: 1, sheet: sheet.getName(),
    sheetNames: workbook.getWorksheets().map(s => s.getName()),
    rowsIncludingHeader: count, columns: 25,
    values: sheet.getRangeByIndexes(0, 0, count, 25).getValues(),
    dateFormats: [3, 4, 5, 11].map(column => ({ column: column + 1,
      formats: sheet.getRangeByIndexes(1, column, count - 1, 1).getNumberFormats().map(r => r[0]) })),
    reviewTexts: sheet.getRangeByIndexes(1, 5, count - 1, 1).getTexts().map(r => r[0]) };
}
const expectedHeaders: string[] = ["Document Type\n", "Document ID\n", "ID#", "First Ever Date ", "Last Reviewed ", "Next Review Date", "Title ", "Custodian", "Service Index", "Status", "Status Category", "Published", "Standard", "Priority", "RISK", "Comments ", "HRA 2019 Compatible", "Authorising Officer", "Executive Officer Operational Heirachy", "Service Director", "Clinical/Corp", "Audit Approach", "Audit Approach", "QH overarching P/P or guideline / duplication\nNOTES", "Asset #"];
const fieldNames: string[] = ["sourceDocumentType", "sourceDocumentId", "sourceIdNumber", "sourceFirstEverDateRaw", "sourceLastReviewedRaw", "sourceNextReviewDateRaw", "sourceTitle", "sourceCustodian", "sourceServiceIndex", "sourceStatus", "sourceStatusCategory", "sourcePublishedRaw", "sourceStandard", "sourcePriority", "sourceRisk", "sourceComments", "sourceHRACompatibility", "sourceAuthorisingOfficer", "sourceExecutiveHierarchy", "sourceServiceDirector", "sourceClinicalCorporate", "sourceAuditApproach1", "sourceAuditApproach2", "sourceOverarchingAuthorityNotes", "sourceAssetNumber"];
type JsonValue = Scalar | JsonValue[] | { [key: string]: JsonValue };
interface IdentityProposal {
  schemaVersion: number; status: string; resolution: string; existingUID: string | null;
  exceptionKey: string; source: string; sourceSha256: string; sourceFingerprint: string;
  contractHash: string; rationale: string; evidenceReferences: string[]; decisionEvidence: string;
  history: { from: string; to: string; actor: string; evidence: string; at: string }[];
}
interface IdentityApplication {
  schemaVersion: number; source: string; sourceSha256: string; baseContractHash: string;
  resultContractHash: string; allowed: string[]; baseUIDs: string[]; expectedUIDs: string[];
  newUIDs: string[]; inputCount: number; amendments: JsonValue[];
  acceptedProposals: IdentityProposal[];
  newIdentityAuthorisations: { exceptionKey: string; DocumentUID: string; actor: string; evidenceReference: string }[];
  resultLedger: { sourceSystemId: string; aliases: Alias[]; sourceAbsenceAcknowledgements?: AbsenceAcknowledgement[] };
  status: string; packageHash: string;
  absenceAcknowledgements?: AbsenceAcknowledgement[];
  retainedAbsentUIDs?: string[]; activeUIDs?: string[];
}
function canonical(value: JsonValue): string {
  if (Array.isArray(value)) return '[' + value.map(v => canonical(v)).join(',') + ']';
  if (value !== null && typeof value === 'object')
    return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
function identityHash(value: JsonValue): string { return sha256(utf8(canonical(value))); }
function aliasHash(aliases: Alias[]): string { return identityHash(aliases as unknown as JsonValue); }
function applyIdentityDecisions(extraction: Extracted, sourceSha256: string, ledger: Ledger,
                                applicationJson: string): Ledger {
  const pkg: IdentityApplication = JSON.parse(applicationJson);
  const base: Alias[] = ledger.aliases.map(a => ({source: ledger.sourceSystemId,
    alias: a.sourceDocumentId, DocumentUID: a.documentUID}));
  const baseUIDs = Array.from(new Set(base.map(a => a.DocumentUID))).sort();
  const pkgCopy: { [key: string]: JsonValue } = JSON.parse(applicationJson);
  delete pkgCopy.packageHash;
  if (![1, 2].includes(pkg.schemaVersion) || pkg.status !== 'accepted-awaiting-importer' ||
      pkg.source !== ledger.sourceSystemId || pkg.sourceSha256 !== sourceSha256 ||
      pkg.baseContractHash !== aliasHash(base) || pkg.packageHash !== identityHash(pkgCopy) ||
      canonical(pkg.baseUIDs) !== canonical(baseUIDs) ||
      canonical(pkg.allowed) !== canonical(allowedFields.slice().sort()) ||
      pkg.inputCount !== extraction.values.length - 1 ||
      (!pkg.acceptedProposals.length && !pkg.absenceAcknowledgements?.length))
    throw new Error('identity_application_precondition_failed');
  const revised: Ledger = JSON.parse(JSON.stringify(ledger));
  const unknown: { [key: string]: {alias: string; fingerprint: string} } = {};
  const knownAliases = new Set(base.map(a => a.alias));
  for (let i=1; i<extraction.values.length; i++) {
    const fields: Fields = {}; fieldNames.forEach((k,c) => { fields[k]=extraction.values[i][c]; });
    const alias = fields.sourceDocumentId;
    if (typeof alias !== 'string' || !alias) throw new Error('invalid_source_alias');
    if (!knownAliases.has(alias)) {
      const fingerprint = identityHash({source: ledger.sourceSystemId, sourceSha256, fields});
      const key = identityHash({code:'unknown_alias', sourceFingerprint:fingerprint});
      if (unknown[key]) throw new Error('duplicate_source_exception');
      unknown[key] = {alias, fingerprint};
    }
  }
  const processed = new Set<string>(), newUIDs = new Set<string>(), usedAuths = new Set<string>();
  const amendments: JsonValue[] = [];
  const auths: { [key:string]: {exceptionKey:string; DocumentUID:string; actor:string; evidenceReference:string} } = {};
  for (const auth of pkg.newIdentityAuthorisations) {
    if (!auth.exceptionKey || auths[auth.exceptionKey] || !auth.actor.trim() || !auth.evidenceReference.trim() ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(auth.DocumentUID))
      throw new Error('invalid_new_identity_authorisation');
    auths[auth.exceptionKey]=auth;
  }
  for (const p of pkg.acceptedProposals) {
    const item=unknown[p.exceptionKey];
    if (!item || processed.has(p.exceptionKey) || p.schemaVersion !== 1 || p.status !== 'accepted' ||
        p.source !== pkg.source || p.sourceSha256 !== pkg.sourceSha256 || p.contractHash !== pkg.baseContractHash ||
        p.sourceFingerprint !== item.fingerprint || !p.rationale.trim() || !p.decisionEvidence.trim() ||
        !Array.isArray(p.evidenceReferences) || !p.evidenceReferences.length || p.evidenceReferences.some(e => !e.trim()) ||
        p.history.filter(h => h.from==='proposed' && h.to==='accepted' && h.evidence===p.decisionEvidence && h.actor.trim() && h.at).length !== 1)
      throw new Error('invalid_accepted_identity_decision');
    processed.add(p.exceptionKey);
    let uid: string;
    if (p.resolution==='existing_uid') {
      if (!p.existingUID || !baseUIDs.includes(p.existingUID) || auths[p.exceptionKey])
        throw new Error('existing_identity_not_qualified');
      uid=p.existingUID;
    } else if (p.resolution==='request_new_uid') {
      const auth=auths[p.exceptionKey];
      if (p.existingUID !== null || !auth || baseUIDs.includes(auth.DocumentUID) || newUIDs.has(auth.DocumentUID))
        throw new Error('new_identity_not_qualified');
      uid=auth.DocumentUID; newUIDs.add(uid); usedAuths.add(p.exceptionKey);
    } else throw new Error('unresolved_identity');
    revised.aliases.push({documentUID:uid,sourceDocumentId:item.alias});
    amendments.push({exceptionKey:p.exceptionKey,alias:item.alias,DocumentUID:uid,
      sourceFingerprint:item.fingerprint,proposalHash:identityHash(p as unknown as JsonValue),kind:p.resolution});
  }
  const aliases: Alias[] = revised.aliases.map(a=>({source:ledger.sourceSystemId,alias:a.sourceDocumentId,DocumentUID:a.documentUID}));
  const expectedUIDs=Array.from(new Set(aliases.map(a=>a.DocumentUID))).sort();
  if (pkg.schemaVersion === 2) {
    const lookup: {[alias:string]:string} = {};
    aliases.forEach(a => { lookup[a.alias]=a.DocumentUID; });
    const activeUIDs = extraction.values.slice(1).map(r => lookup[String(r[1])]).sort();
    const missing = expectedUIDs.filter(uid => !activeUIDs.includes(uid));
    const acknowledgements=pkg.absenceAcknowledgements || [];
    const retained: string[]=[];
    for (const ack of acknowledgements) {
      if (!baseUIDs.includes(ack.DocumentUID) || !missing.includes(ack.DocumentUID) || retained.includes(ack.DocumentUID) ||
          ack.sourceSha256!==sourceSha256 || ack.baseContractHash!==pkg.baseContractHash ||
          ack.effect!=='retain_unchanged' || !ack.actor.trim() || !ack.evidenceReference.trim() || !ack.decisionEvidence.trim())
        throw new Error('invalid_source_absence_acknowledgement');
      retained.push(ack.DocumentUID);
    }
    if (!acknowledgements.length || canonical(retained.sort())!==canonical(missing) ||
        canonical(retained)!==canonical(pkg.retainedAbsentUIDs || []) ||
        canonical(activeUIDs)!==canonical(pkg.activeUIDs || []) || new Set(activeUIDs).size!==activeUIDs.length ||
        canonical(acknowledgements as unknown as JsonValue)!==canonical(pkg.resultLedger.sourceAbsenceAcknowledgements as unknown as JsonValue))
      throw new Error('source_absence_set_mismatch');
    revised.sourceAbsenceAcknowledgements=acknowledgements;
  } else if (pkg.absenceAcknowledgements || pkg.retainedAbsentUIDs || pkg.activeUIDs ||
      canonical((pkg.resultLedger.sourceAbsenceAcknowledgements || []) as unknown as JsonValue)!==
      canonical((ledger.sourceAbsenceAcknowledgements || []) as unknown as JsonValue)) {
    throw new Error('absence_requires_schema_two');
  }
  if (processed.size !== Object.keys(unknown).length || usedAuths.size !== Object.keys(auths).length ||
      canonical(amendments)!==canonical(pkg.amendments) ||
      canonical(Array.from(newUIDs).sort())!==canonical(pkg.newUIDs) ||
      canonical(expectedUIDs)!==canonical(pkg.expectedUIDs) ||
      expectedUIDs.length!==baseUIDs.length+newUIDs.size || aliasHash(aliases)!==pkg.resultContractHash ||
      pkg.resultLedger.sourceSystemId!==ledger.sourceSystemId ||
      canonical(aliases as unknown as JsonValue)!==canonical(pkg.resultLedger.aliases as unknown as JsonValue))
    throw new Error('identity_application_result_mismatch');
  return revised;
}

const summaryFields = ["sourceCustodian", "sourceDocumentId", "sourceRisk", "sourceStatus", "sourceTitle"];
const allowedFields = ["rawSourceRecordRef", "sourceAsOfUtc", "sourceCustodian", "sourceDocumentId", "sourceNextReviewDateRaw", "sourceNextReviewMonth", "sourceRisk", "sourceRowNumber", "sourceSnapshotRef", "sourceStatus", "sourceTitle"];
function buildCandidate(extraction: Extracted, rawBase64: string,
  identityLedgerJson: string, asOfUtc: string, snapshotRef: string, recordsRef: string,
  identityApplicationJson: string = "") {
  if (!/^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]00:00)$/.test(asOfUtc) || !Number.isFinite(Date.parse(asOfUtc)) ||
      !snapshotRef.startsWith("https://") || !recordsRef.startsWith("https://") || recordsRef.includes("#"))
    throw new Error("provenance_unqualified");
  const rawBytes = decodeBase64(rawBase64);
  if (rawBytes[0] !== 80 || rawBytes[1] !== 75) throw new Error("raw_xlsb_package_required");
  const sourceSha256 = sha256(rawBytes);
  let ledger = JSON.parse(identityLedgerJson) as Ledger;
  const baseAliases: Alias[] = ledger.aliases.map(a => ({source:ledger.sourceSystemId, alias:a.sourceDocumentId, DocumentUID:a.documentUID}));
  const baseContractHash = aliasHash(baseAliases);
  const baseUIDs = Array.from(new Set(baseAliases.map(a => a.DocumentUID))).sort();
  if (identityApplicationJson) ledger = applyIdentityDecisions(extraction, sourceSha256, ledger, identityApplicationJson);
  if (ledger.sourceSystemId !== "example-ppg-register" || !Array.isArray(ledger.aliases) || !ledger.aliases.length)
    throw new Error("identity_contract_invalid");
  const aliases: Alias[] = ledger.aliases.map(a => ({ source: ledger.sourceSystemId,
    alias: a.sourceDocumentId, DocumentUID: a.documentUID }));
  const lookup: { [key: string]: string } = {};
  const expected: { [key: string]: boolean } = {};
  for (const alias of aliases) {
    if (typeof alias.alias !== "string" || !alias.alias ||
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(alias.DocumentUID))
      throw new Error("identity_contract_invalid");
    const key = JSON.stringify([alias.source, alias.alias]);
    if (lookup[key]) throw new Error("duplicate_alias_contract");
    lookup[key] = alias.DocumentUID; expected[alias.DocumentUID] = true;
  }
  if (extraction.sheet !== "Master Document Register" || extraction.columns !== 25 ||
      extraction.rowsIncludingHeader !== extraction.values.length ||
      JSON.stringify(extraction.values[0]) !== JSON.stringify(expectedHeaders))
    throw new Error("ordinal_header_mismatch");
  const formats = extraction.dateFormats.filter(f => f.column === 6);
  if (formats.length !== 1 || formats[0].formats.length !== extraction.values.length - 1 ||
      extraction.reviewTexts.length !== extraction.values.length - 1) throw new Error("review_date_dimensions_invalid");
  const seen: { [key: string]: boolean } = {};
  const operations: { DocumentUID: string; fields: Fields; sourceRow: number }[] = [];
  const rawRecords: { sourceRow: number; fields: Fields; projectedFields: Fields }[] = [];
  const records: { sourceRow: number; values: Scalar[] }[] = [];
  const exceptions: { code: string; row: number }[] = [];
  for (let i = 1; i < extraction.values.length; i++) {
    const values = extraction.values[i];
    if (values.length !== 25 || values.some(v => typeof v === "number" && !Number.isFinite(v)))
      throw new Error("row_width_or_value_invalid");
    const raw: Fields = {};
    // Office returns blank cells as empty strings. Keep these values unchanged;
    // native summary blank/null codec is separate from the raw export.
    fieldNames.forEach((name, c) => { raw[name] = values[c]; });
    const alias = raw.sourceDocumentId;
    const uid = typeof alias === "string" ? lookup[JSON.stringify([ledger.sourceSystemId, alias])] : undefined;
    const identityIssue = !uid ? "unknown_alias" : seen[uid] ? "duplicate_identity" : "";
    if (identityIssue) exceptions.push({code:identityIssue,row:i+1});
    else seen[uid] = true;
    const review = raw.sourceNextReviewDateRaw;
    const month = reviewMonth(review, formats[0].formats[i - 1], extraction.reviewTexts[i - 1]);
    const fields: Fields = {};
    for (const name of summaryFields) fields[name] = raw[name] === "" || raw[name] === null ? null : String(raw[name]);
    fields.sourceNextReviewDateRaw = JSON.stringify(review);
    fields.sourceNextReviewMonth = month;
    fields.sourceSnapshotRef = snapshotRef; fields.sourceAsOfUtc = asOfUtc;
    fields.sourceRowNumber = i + 1; fields.rawSourceRecordRef = recordsRef + "#sourceRow=" + (i + 1);
    if (!identityIssue) operations.push({ DocumentUID: uid, fields, sourceRow: i + 1 });
    rawRecords.push({ sourceRow: i + 1, fields: raw, projectedFields: fields });
    records.push({ sourceRow: i + 1, values: values.slice() });
  }
  const missingUIDs = Object.keys(expected).filter(uid => !seen[uid]);
  const acknowledgedMissingUIDs: string[] = [];
  const historicalAcknowledgementUIDs = new Set<string>();
  for (const ack of ledger.sourceAbsenceAcknowledgements || []) {
    if (!expected[ack.DocumentUID] || historicalAcknowledgementUIDs.has(ack.DocumentUID) ||
        ack.effect!=='retain_unchanged' ||
        !ack.actor.trim() || !ack.evidenceReference.trim() || !ack.decisionEvidence.trim())
      throw new Error('stale_or_invalid_source_absence_acknowledgement');
    historicalAcknowledgementUIDs.add(ack.DocumentUID);
    // Evidence of an earlier absence remains history when the known identity
    // returns. Only a still-absent identity consumes source-bound authority.
    if (missingUIDs.includes(ack.DocumentUID)) {
      if (ack.sourceSha256!==sourceSha256)
        throw new Error('stale_or_invalid_source_absence_acknowledgement');
      acknowledgedMissingUIDs.push(ack.DocumentUID);
    }
  }
  // Retain all source rows for operator triage. The native writer rejects every
  // exception/missing UID before writes; missing records never imply retirement.
  const headers = expectedHeaders.map((actual, i) => ({ column: i + 1,
    expected: actual, actual, matches: true, mirrorField: fieldNames[i] }));
  const retainedMainRecords = { sourceSha256, sourceSheet: extraction.sheet, headers, records };
  const recordsJson = JSON.stringify(retainedMainRecords);
  const candidate = { source: ledger.sourceSystemId, sourceSha256, inputCount: rawRecords.length,
    operations, exceptions, missingUIDs, acknowledgedMissingUIDs: acknowledgedMissingUIDs.sort(), allowed: allowedFields.slice(),
    contractHash: sha256(utf8(JSON.stringify(aliases.map(a => ({ DocumentUID: a.DocumentUID, alias: a.alias, source: a.source }))))),
    rawRecords, provenance: { mainSha256: sha256(utf8(recordsJson)), sourceSheet: extraction.sheet,
      rawSnapshotRef: snapshotRef, mainRecordsRef: recordsRef,
      dateSystemEvidence: "1900 serial-to-month agrees with displayed next review month on every row",
      nextReviewPrecision: "month", rawByteLength: rawBytes.length } };
  return { candidate, extraction, recordsJson,
    identityContract: {baseContractHash, baseUIDs, ledger},
    identityApplication: identityApplicationJson ? {
      packageHash: (JSON.parse(identityApplicationJson) as IdentityApplication).packageHash,
      baseContractHash: (JSON.parse(identityApplicationJson) as IdentityApplication).baseContractHash,
      newUIDs: (JSON.parse(identityApplicationJson) as IdentityApplication).newUIDs,
      resultLedger: ledger
    } : null };
}
function reviewMonth(raw: Scalar, format: string, displayed: string): string {
  if (typeof raw !== "number" || !Number.isFinite(raw) || raw < 61 || raw >= 2958466 ||
      !["mmm-yyyy", "mmm\\-yyyy", "mmm yyyy", "mmm\\ yyyy", "mmm-yy"].includes(format))
    throw new Error("unqualified_review_month");
  const month = new Date(Math.round((raw - 25569) * 86400000)).toISOString().slice(0, 7);
  const parts = /^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[ -](\d{2}|\d{4})$/i.exec(displayed);
  if (!parts) throw new Error("displayed_review_month_unqualified");
  const m = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].indexOf(parts[1].toLowerCase()) + 1;
  if (month.slice(5) !== String(m).padStart(2, "0") ||
      (parts[2].length === 4 ? month.slice(0, 4) : month.slice(2, 4)) !== parts[2])
    throw new Error("date_system_or_display_mismatch");
  return month;
}
function decodeBase64(input: string): number[] {
  if (!input || input.length % 4 !== 0 || !/^[A-Za-z0-9+/]+={0,2}$/.test(input))
    throw new Error("raw_base64_invalid");
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const result: number[] = [];
  for (let i = 0; i < input.length; i += 4) {
    const a = alphabet.indexOf(input[i]), b = alphabet.indexOf(input[i + 1]);
    const c = input[i + 2] === "=" ? 0 : alphabet.indexOf(input[i + 2]);
    const d = input[i + 3] === "=" ? 0 : alphabet.indexOf(input[i + 3]);
    result.push((a << 2) | (b >>> 4));
    if (input[i + 2] !== "=") result.push(((b & 15) << 4) | (c >>> 2));
    if (input[i + 3] !== "=") result.push(((c & 3) << 6) | d);
  }
  return result;
}
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
