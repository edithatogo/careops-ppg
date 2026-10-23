/* Bounded Office Script packaging kernel; no workbook reads/writes or network.
 * ZIP32 STORE layout follows the existing submission assembler. SHA-256/UTF-8
 * helpers are retained from the source-sync kernel; QW3 is not modified.
 * Native connector execution must be qualified separately.
 */
interface Member { path: string; sha256: string; size: number; sourceReference: string; sourceVersionRef: string; role?: string; }
interface Content { path: string; base64: string; }
interface Job {
  schemaVersion: number; jobId: string; documentKind: string; CaseUID: string;
  sourceSnapshotRef: string; sourceSHA256: string; templateVersion?: string;
  templateSHA256?: string; outputRevision: string; includedRecordIDs: string[];
  createdAtUtc: string; members: Member[];
  provenanceMode?: string; assemblyTemplateVersion?: string; assemblyTemplateSHA256?: string;
  authoringProvenance?: { status: string; generationReceipt: string | null; };
}
interface ZipEntry { name: string; bytes: number[]; }
interface PackageResult {
  schemaVersion: number; jobId: string; outputRevision: string; jobSHA256: string;
  packageSHA256: string; packageBytes: number; memberCount: number; zipBase64: string;
  status: string; sourceWrites: boolean; sent: boolean; wordGenerationPerformed?: boolean;
  coverSHA256?: string; coverBytes?: number; coverBase64?: string; generationRoute?: string;
  requestSHA256?: string; claimJson?: string; jobJson?: string;
  finalisationMembersJson?: string; generatedDocumentSHA256?: string;
}
const MAX_WIRE_BYTES = 4000000;
const MAX_RAW_BYTES = 2000000;
const EXISTING_FORMAT_VERSION = "ppg-existing-artifacts-v1";
const EXISTING_FORMAT_SHA256 = "4c47e9f92f99047288af5dd477f7ccd6320e4a38a304f57992ab89fadf2e4113";
function main(workbook: ExcelScript.Workbook, jobJson: string, membersJson: string): PackageResult {
  // The workbook exists only to host the authorised Run script action.
  const envelope: { kind?: string; jobJson: string; coverJson: string } = JSON.parse(jobJson);
  if (utf8(JSON.stringify({jobJson,membersJson})).length > MAX_WIRE_BYTES) throw Error('request_limit');
  const result: PackageResult = JSON.parse(envelope.kind === 'm365-saved-body-package-v1' ? packageSavedBody(jobJson,membersJson) : envelope.kind === 'm365-case-intake-request-v1' ? nativeCaseIntake(jobJson,membersJson) : ['m365-cover-request-v1','m365-full-review-request-v1'].indexOf(envelope.kind || '') >= 0 ?
    nativeCoverRequest(jobJson, membersJson) : envelope.kind === 'standard-cover-input-v1' ?
    packageCover(envelope.jobJson, membersJson, envelope.coverJson) : packageJob(jobJson, membersJson));
  return result;
}

interface SavedBodyRequest {
  kind: string; generatedJobJson: string; generatedClaimJson: string;
  savedPinBefore: NativePin; savedPinAfter: NativePin;
  documentPath: string; savedBodyBase64: string; existingSavedClaimJson: string;
}
function packageSavedBody(requestJson: string, membersJson: string): string {
  // Separate finalisation protocol: never change the generated v1 claim or
  // reinterpret an existing legacy ZIP. The native caller must acquire saved
  // bytes between metadata reads and retain uncertain writes for reconciliation.
  if (utf8(JSON.stringify({requestJson,membersJson})).length > MAX_WIRE_BYTES) throw Error('request_limit');
  const req: SavedBodyRequest = JSON.parse(requestJson);
  if (!req || req.kind !== 'm365-saved-body-package-v1') throw Error('saved_body_request_invalid');
  const job: Job = JSON.parse(req.generatedJobJson), claim: NativeClaim = JSON.parse(req.generatedClaimJson);
  const originalJobSHA = sha256(utf8(req.generatedJobJson));
  if (!job || job.schemaVersion !== 1 || !claim || claim.kind !== 'PPG-native-package-claim-v1'
      || claim.jobId !== job.jobId || claim.jobSHA256 !== originalJobSHA
      || !/^[a-f0-9]{64}$/.test(claim.requestSHA256 || '') || claim.createdAtUtc !== job.createdAtUtc
      || !/^[A-Za-z0-9_-]{1,100}$/.test(claim.generationRunId || '')) throw Error('generated_claim_mismatch');
  if (!['document/PPG-review-DRAFT.docx','cover/PPG-cover-DRAFT.docx'].includes(req.documentPath)) throw Error('saved_document_path_invalid');
  const keys = ['UniqueId','ETag','Length','UIVersionLabel','ServerRelativeUrl'];
  const before = req.savedPinBefore, after = req.savedPinAfter;
  if (!before || !after || keys.some(k => typeof before[k as keyof NativePin] !== 'string'
      || !(before[k as keyof NativePin] as string).trim() || before[k as keyof NativePin] !== after[k as keyof NativePin])
      || before.ETag.trim() === '*' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(before.UniqueId)
      || !/^\d+$/.test(before.Length) || !before.ServerRelativeUrl.startsWith('/')
      || !before.ServerRelativeUrl.endsWith('/'+job.jobId+'.docx')) throw Error('saved_body_unstable_pin');
  const body = decodeMember(req.savedBodyBase64), digest = sha256(body);
  if (body.length < 4 || body[0] !== 80 || body[1] !== 75 || body[2] !== 3 || body[3] !== 4
      || body.length !== Number(before.Length)) throw Error('saved_body_invalid');
  const members: Content[] = JSON.parse(membersJson);
  if (!Array.isArray(job.members) || job.members.filter(m => m.path === req.documentPath).length !== 1
      || !Array.isArray(members) || members.some(m => m.path === req.documentPath)) throw Error('saved_body_member_ambiguous');
  // Reject changed non-document inputs against the original manifest before
  // rebinding only the saved document. packageJob checks paths/counts/digests.
  const selected = job.members.find(m => m.path === req.documentPath);
  if (!selected) throw Error('saved_body_member_missing');
  const generatedDocumentSHA256 = selected.sha256;
  const savedPin = {UniqueId:before.UniqueId,ETag:before.ETag,Length:before.Length,
    UIVersionLabel:before.UIVersionLabel,ServerRelativeUrl:before.ServerRelativeUrl};
  const savedClaim = {kind:'PPG-native-saved-body-claim-v1',jobId:job.jobId,
    generatedJobSHA256:originalJobSHA,generatedClaimSHA256:sha256(utf8(req.generatedClaimJson)),
    generatedDocumentSHA256,savedDocumentSHA256:digest,savedPin};
  const savedClaimJson = JSON.stringify(savedClaim);
  if (typeof req.existingSavedClaimJson !== 'string') throw Error('saved_claim_state_required');
  if (req.existingSavedClaimJson && req.existingSavedClaimJson !== savedClaimJson) throw Error('saved_output_edited_requires_reconciliation');
  selected.sha256 = digest; selected.size = body.length;
  selected.sourceReference = before.ServerRelativeUrl;
  selected.sourceVersionRef = before.UIVersionLabel+':'+before.ETag;
  const finalJob = {...job,savedBodyProvenance:savedClaim};
  const jobJson = JSON.stringify(finalJob);
  const result: PackageResult = JSON.parse(packageJob(jobJson,JSON.stringify([
    {path:req.documentPath,base64:req.savedBodyBase64},...members]),3000000));
  const response = JSON.stringify({...result,jobJson,claimJson:savedClaimJson,
    coverBase64:req.savedBodyBase64,coverSHA256:digest,coverBytes:body.length,
    generatedDocumentSHA256,generationRoute:'sharepoint-saved-body-finalisation-v1',
    wordGenerationPerformed:false,requestSHA256:claim.requestSHA256});
  if (utf8(response).length > MAX_WIRE_BYTES) throw Error('response_limit');
  return response;
}
function packageJob(jobJson: string, membersJson: string, rawLimit: number = MAX_RAW_BYTES): string {
  // Count escaped string parameters as actually serialized, with routing headroom.
  if (utf8(JSON.stringify({ jobJson, membersJson })).length > MAX_WIRE_BYTES) throw Error("request_limit");
  const job: Job = JSON.parse(jobJson);
  const contents: Content[] = JSON.parse(membersJson);
  if (!job || (job.schemaVersion !== 1 && job.schemaVersion !== 2) || !/^job-[a-z0-9-]{1,64}$/.test(job.jobId || "")) throw Error("invalid_job");
  validateMode(job);
  const templateVersion = job.schemaVersion === 1 ? job.templateVersion : job.assemblyTemplateVersion;
  const templateHash = job.schemaVersion === 1 ? job.templateSHA256 : job.assemblyTemplateSHA256;
  for (const value of [job.documentKind, job.CaseUID, job.sourceSnapshotRef, templateVersion, job.outputRevision])
    if (typeof value !== "string" || !value.trim()) throw Error("technical_identity_missing");
  if (!/^[0-9a-f]{64}$/.test(job.sourceSHA256 || "") || !/^[0-9a-f]{64}$/.test(templateHash || "")) throw Error("identity_hash_invalid");
  if (!Array.isArray(job.includedRecordIDs) || !job.includedRecordIDs.length ||
      job.includedRecordIDs.some(x => typeof x !== "string" || !x.trim()) ||
      new Set(job.includedRecordIDs).size !== job.includedRecordIDs.length) throw Error("included_identity_invalid");
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(job.createdAtUtc || "") ||
      !Number.isFinite(Date.parse(job.createdAtUtc)) || new Date(job.createdAtUtc).toISOString() !==
      job.createdAtUtc.replace(/:([0-9]{2})Z$/, ":$1.000Z")) throw Error("utc_time_invalid");
  if (!Array.isArray(job.members) || job.members.length > 203 || !Array.isArray(contents) ||
      job.members.length !== contents.length) throw Error("member_count_mismatch");
  if (job.schemaVersion === 2) {
    const roles = ["recorded-baseline", "existing-manual-draft", "selection-record"];
    if (job.members.length !== roles.length || new Set(job.members.map(m => m.role)).size !== roles.length ||
        job.members.some(m => roles.indexOf(m.role || "") < 0)) throw Error("existing_artifact_members_invalid");
  }
  const names = new Set<string>();
  const entries: ZipEntry[] = [];
  let total = 0;
  for (let i = 0; i < job.members.length; i++) {
    const expected = job.members[i], actual = contents[i];
    safePath(expected.path);
    const key = expected.path.normalize("NFC").toLowerCase();
    if (key === "package-provenance.json" || key.startsWith("package-provenance.json/") ||
        Array.from(names).some(name => name === key || name.startsWith(key + "/") || key.startsWith(name + "/")))
      throw Error("member_path_collision");
    names.add(key);
    if (actual.path !== expected.path) throw Error("member_order_or_path_mismatch");
    if (!Number.isInteger(expected.size) || expected.size < 0 || expected.size > rawLimit ||
        !/^[0-9a-f]{64}$/.test(expected.sha256 || "")) throw Error("member_contract_invalid");
    if (typeof expected.sourceReference !== "string" || !expected.sourceReference.trim() ||
        typeof expected.sourceVersionRef !== "string" || !expected.sourceVersionRef.trim()) throw Error("member_provenance_missing");
    const bytes = decodeMember(actual.base64);
    total += bytes.length;
    if (total > rawLimit) throw Error("complete_package_oversize");
    if (bytes.length !== expected.size || sha256(bytes) !== expected.sha256) throw Error("member_hash_or_size_mismatch");
    entries.push({ name: expected.path, bytes });
  }
  const provenance = JSON.stringify(job.schemaVersion === 1 ?
    { schemaVersion: 1, jobSHA256: sha256(utf8(jobJson)), job,
      status: "DRAFT / HUMAN CHECK REQUIRED", sourceWrites: false, sent: false, policyApproved: false } :
    { schemaVersion: 2, jobSHA256: sha256(utf8(jobJson)), job,
      status: "DRAFT / HUMAN CHECK REQUIRED", sourceWrites: false, sent: false, policyApproved: false,
      wordGenerationPerformed: false });
  const provenanceBytes = utf8(provenance);
  if (total + provenanceBytes.length > rawLimit) throw Error("complete_package_oversize");
  entries.push({ name: "package-provenance.json", bytes: provenanceBytes });
  const zip = storeZip(entries);
  const record: PackageResult = { schemaVersion: job.schemaVersion, jobId: job.jobId, outputRevision: job.outputRevision,
    jobSHA256: sha256(utf8(jobJson)), packageSHA256: sha256(zip), packageBytes: zip.length,
    memberCount: entries.length, zipBase64: encodeBase64(zip),
    status: "DRAFT / HUMAN CHECK REQUIRED", sourceWrites: false, sent: false };
  if (job.schemaVersion === 2) record.wordGenerationPerformed = false;
  const result = JSON.stringify(record);
  if (utf8(result).length > MAX_WIRE_BYTES) throw Error("response_limit");
  return result;
}
function validateMode(job: Job): void {
  if (job.schemaVersion === 1) {
    if (job.provenanceMode !== undefined || job.assemblyTemplateVersion !== undefined ||
        job.assemblyTemplateSHA256 !== undefined || job.authoringProvenance !== undefined)
      throw Error("ambiguous_provenance_mode");
    return;
  }
  const allowed = ["schemaVersion", "provenanceMode", "jobId", "documentKind", "CaseUID", "sourceSnapshotRef",
    "sourceSHA256", "assemblyTemplateVersion", "assemblyTemplateSHA256", "authoringProvenance",
    "outputRevision", "includedRecordIDs", "createdAtUtc", "members", "packagingEngine", "caseBinding",
    "catalogueBinding", "selectionManifest", "artifactProvenance", "qualificationScope"];
  if (job.provenanceMode !== "existing-artifacts" || Object.keys(job).some(key => allowed.indexOf(key) < 0))
    throw Error("ambiguous_provenance_mode");
  if (job.documentKind !== "existing-case-artifact-package" ||
      job.assemblyTemplateVersion !== EXISTING_FORMAT_VERSION || job.assemblyTemplateSHA256 !== EXISTING_FORMAT_SHA256)
    throw Error("assembly_template_unqualified");
  if (!job.authoringProvenance || job.authoringProvenance.status !== "unknown" ||
      job.authoringProvenance.generationReceipt !== null ||
      Object.keys(job.authoringProvenance).sort().join(",") !== "generationReceipt,status")
    throw Error("historical_authoring_provenance_invalid");
}
function safePath(value: string): void {
  if (typeof value !== "string" || value.length > 240 || /[\\:\x00-\x1f\x7f]/.test(value) ||
      value.split("/").some(x => !x || x === "." || x === ".." || /[. ]$/.test(x))) throw Error("unsafe_member_path");
}
function decodeMember(value: string): number[] {
  if (typeof value !== "string" || value.length % 4 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) throw Error("invalid_base64");
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/", bytes: number[] = [];
  for (let i = 0; i < value.length; i += 4) {
    const a = alphabet.indexOf(value[i]), b = alphabet.indexOf(value[i+1]);
    const c = value[i+2] === "=" ? 0 : alphabet.indexOf(value[i+2]), d = value[i+3] === "=" ? 0 : alphabet.indexOf(value[i+3]);
    if ((value[i+2] === "=" && (b & 15)) || (value[i+3] === "=" && (c & 3))) throw Error("noncanonical_base64");
    bytes.push((a << 2) | (b >>> 4));
    if (value[i+2] !== "=") bytes.push(((b & 15) << 4) | (c >>> 2));
    if (value[i+3] !== "=") bytes.push(((c & 3) << 6) | d);
  }
  return bytes;
}
function encodeBase64(bytes: number[]): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const chunks: string[] = [];
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i], b = bytes[i+1] || 0, c = bytes[i+2] || 0;
    chunks.push(alphabet[a >>> 2] + alphabet[((a & 3) << 4) | (b >>> 4)] +
      (i+1 < bytes.length ? alphabet[((b & 15) << 2) | (c >>> 6)] : "=") +
      (i+2 < bytes.length ? alphabet[c & 63] : "="));
  }
  return chunks.join("");
}
function storeZip(entries: ZipEntry[]): number[] {
  // ZIP32 STORE, UTF-8 names, fixed DOS timestamp 1980-01-01; deterministic bytes.
  const crcTable = Array.from({ length: 256 }, (_, index) => {
    let c = index; for (let k = 0; k < 8; k++) c = (c & 1) ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const chunks: number[][] = [], directory: number[][] = [];
  let offset = 0;
  const put = (bytes: number[], at: number, value: number, size: number) => {
    for (let i = 0; i < size; i++) bytes[at+i] = (value >>> (i*8)) & 255;
  };
  for (const entry of entries) {
    const name = utf8(entry.name), bytes = entry.bytes;
    let crc = 0xffffffff; for (const b of bytes) crc = crcTable[(crc ^ b) & 255] ^ (crc >>> 8);
    crc = (crc ^ 0xffffffff) >>> 0;
    const local = new Array<number>(30 + name.length).fill(0);
    put(local,0,0x04034b50,4); put(local,4,20,2); put(local,6,0x800,2); put(local,12,0x21,2);
    put(local,14,crc,4); put(local,18,bytes.length,4); put(local,22,bytes.length,4); put(local,26,name.length,2);
    name.forEach((b,i) => { local[30+i] = b; });
    const central = new Array<number>(46 + name.length).fill(0);
    put(central,0,0x02014b50,4); put(central,4,20,2); put(central,6,20,2); put(central,8,0x800,2); put(central,14,0x21,2);
    put(central,16,crc,4); put(central,20,bytes.length,4); put(central,24,bytes.length,4); put(central,28,name.length,2); put(central,42,offset,4);
    name.forEach((b,i) => { central[46+i] = b; });
    chunks.push(local,bytes); directory.push(central); offset += local.length + bytes.length;
  }
  const size = directory.reduce((n,b) => n + b.length,0), end = new Array<number>(22).fill(0);
  put(end,0,0x06054b50,4); put(end,8,entries.length,2); put(end,10,entries.length,2); put(end,12,size,4); put(end,16,offset,4);
  const result: number[] = [];
  for (const chunk of [...chunks,...directory,end]) for (const b of chunk) result.push(b);
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

// Fixed seven-field cover only. The maintained DOCX is compiled once into pinned
// parts; per-job population runs in the existing Standard Office Script runtime.
interface CoverPart { path: string; base64: string; sha256: string; }
interface CoverInput { templateSHA256: string; parts: CoverPart[]; values: { [key: string]: string }; }
interface CoverContract { route: string; manifestSHA256: string; templateSHA256: string; path: string; }
const COVER_FIELDS = ['PPGCoverTitle','PPGCoverCaseUID','PPGDocumentUID','PPGPolicyEdition','PPGCoverRecordedOwner','PPGCoverReviewDate','PPGCoverOutputRevision'];
function textFromUtf8(bytes: number[]): string {
  // Strict round trip also rejects invalid / noncanonical UTF-8.
  let escaped = ''; for (const b of bytes) escaped += '%' + b.toString(16).padStart(2,'0');
  const value = decodeURIComponent(escaped);
  if (sha256(utf8(value)) !== sha256(bytes)) throw Error('cover_utf8_invalid');
  return value;
}
function coverBytes(coverJson: string): number[] {
  if (utf8(coverJson).length > 500000) throw Error('cover_manifest_oversize');
  const input: CoverInput = JSON.parse(coverJson);
  if (!/^[0-9a-f]{64}$/.test(input.templateSHA256) || !input.values ||
      Object.keys(input.values).sort().join(',') !== COVER_FIELDS.slice().sort().join(',') ||
      COVER_FIELDS.some(k => typeof input.values[k] !== 'string' || !input.values[k].trim() || input.values[k].length > 255 || /[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]/.test(input.values[k]))) throw Error('cover_values_invalid');
  const date = input.values.PPGCoverReviewDate;
  if (date !== 'Unresolved' && (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(Date.parse(date)) || new Date(date).toISOString().slice(0,10) !== date)) throw Error('cover_date_invalid');
  if (!Array.isArray(input.parts) || input.parts.length > 100) throw Error('cover_parts_invalid');
  const entries: ZipEntry[] = [], names = new Set<string>(); let count = 0, total = 0;
  for (const part of input.parts) {
    safePath(part.path); const key = part.path.toLowerCase();
    if (names.has(key)) throw Error('cover_part_collision'); names.add(key);
    let bytes = decodeMember(part.base64); total += bytes.length;
    if (total > 300000 || sha256(bytes) !== part.sha256) throw Error('cover_part_changed');
    if (part.path === 'word/document.xml') {
      let xml = textFromUtf8(bytes); const seen = new Set<string>();
      xml = xml.replace(/<w:sdt>[^]*?<\/w:sdt>/g, block => {
        const match = block.match(/<w:tag w:val="([^"]+)"\s*\/>/);
        if (!match || COVER_FIELDS.indexOf(match[1]) < 0) throw Error('cover_control_unexpected');
        const field = match[1];
        if (seen.has(field) || (block.match(/<w:dataBinding\b/g) || []).length !== 1 ||
            (block.match(/<w:t>/g) || []).length !== 1 || !block.includes('<w:t>[Unresolved]</w:t>')) throw Error('cover_template_changed');
        seen.add(field); count++;
        const value = input.values[field].replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\r/g,'&#13;').replace(/\n/g,'&#10;').replace(/\t/g,'&#9;');
        // Detach the output controls so later SharePoint metadata cannot rebind
        // this revision. The maintained template retains all its bindings.
        return block.replace(/<w:dataBinding\b[^]*?\/>/,'').replace('<w:t>[Unresolved]</w:t>','<w:t xml:space="preserve">'+value+'</w:t>');
      });
      if (count !== 7 || !xml.includes('DRAFT') || xml.includes('<w:dataBinding')) throw Error('cover_shape_invalid');
      bytes = utf8(xml);
    }
    entries.push({name:part.path,bytes});
  }
  if (count !== 7 || !names.has('[content_types].xml') || !names.has('_rels/.rels')) throw Error('cover_shape_invalid');
  return storeZip(entries);
}
function packageCover(jobJson: string, membersJson: string, coverJson: string): string {
  if (utf8(JSON.stringify({jobJson,membersJson,coverJson})).length > MAX_WIRE_BYTES) throw Error('request_limit');
  const job: Job & { coverSnapshot: CoverContract } = JSON.parse(jobJson);
  const input: CoverInput = JSON.parse(coverJson), contract = job.coverSnapshot;
  if (job.schemaVersion !== 1 || !contract || contract.route !== 'standard-office-script-fixed-cover-v1' ||
      contract.manifestSHA256 !== sha256(utf8(coverJson)) || contract.templateSHA256 !== input.templateSHA256 ||
      job.templateSHA256 !== input.templateSHA256 || input.values.PPGCoverOutputRevision !== job.outputRevision ||
      input.values.PPGCoverCaseUID !== job.CaseUID) throw Error('cover_contract_mismatch');
  const bytes = coverBytes(coverJson), hash = sha256(bytes), contents: Content[] = JSON.parse(membersJson);
  const matches = job.members.filter(m => m.path === contract.path);
  if (matches.length !== 1 || contents.some(c => c.path === contract.path) || matches[0].sha256 !== hash || matches[0].size !== bytes.length) throw Error('cover_output_mismatch');
  const assembled = job.members.map(m => m.path === contract.path ? {path:m.path,base64:encodeBase64(bytes)} : contents.find(c => c.path === m.path));
  if (contents.length !== job.members.length - 1 || assembled.some(c => !c)) throw Error('cover_member_mismatch');
  const result: PackageResult = JSON.parse(packageJob(jobJson,JSON.stringify(assembled)));
  const response = JSON.stringify({...result,wordGenerationPerformed:true,coverSHA256:hash,coverBytes:bytes.length,coverBase64:encodeBase64(bytes),generationRoute:contract.route});
  if (utf8(response).length > MAX_WIRE_BYTES) throw Error('response_limit');
  return response;
}

interface NativeCoverRequest {
  kind: string; requestItemId: number; createdAtUtc: string; generationRunId: string; existingClaimJson: string;
  templateVersion: string; template: CoverInput; values: { [key: string]: string };
  sourceJobJson: string; sourceReceiptJson: string;
  sourcePin: { UniqueId: string; ETag: string; Length: string; ServerRelativeUrl: string };
  pinsJson: string;
  fullDocumentInputJson?: string;
  sourceSelectionJson?: string;
  intakeScopeJson?: string;
  includeFinalisationMembers?: boolean;
}
interface NativeClaim {
  kind: string; jobId: string; requestSHA256: string; jobSHA256: string; createdAtUtc: string; generationRunId: string;
}
interface NativePin { role: string; UniqueId: string; ETag: string; Length: string; UIVersionLabel: string; ServerRelativeUrl: string; }
function nativeCoverRequest(requestJson: string, membersJson: string, caseIntake: boolean = false): string {
  // Per-job preparation occurs in the existing M365 script, from frozen native
  // inputs. The locally compiled template is a maintained authoring asset only.
  if (utf8(JSON.stringify({requestJson,membersJson})).length > MAX_WIRE_BYTES) throw Error('request_limit');
  const req: NativeCoverRequest = JSON.parse(requestJson), contents: Content[] = JSON.parse(membersJson);
  const intakeScope: {baselinePackagePath:string;draftPackagePath:string} | undefined = req.intakeScopeJson ? JSON.parse(req.intakeScopeJson) : undefined;
  if(intakeScope && !caseIntake)throw Error('intake_adapter_required');
  const rawLimit=caseIntake?3000000:MAX_RAW_BYTES;
  const sourcePath = intakeScope ? intakeScope.baselinePackagePath : 'evidence/existing-pack.zip';
  if(intakeScope && !['evidence/recorded-baseline.zip','evidence/recorded-baseline.json'].includes(sourcePath))throw Error('intake_baseline_path_invalid');
  if(intakeScope && !['evidence/selected-draft.docx','evidence/original-source.txt'].includes(intakeScope.draftPackagePath))throw Error('intake_draft_path_invalid');
  const full = req.kind === 'm365-full-review-request-v1';
  if ((!full && req.kind !== 'm365-cover-request-v1') || !/^[A-Za-z0-9_-]{1,100}$/.test(req.generationRunId || '') || !Number.isSafeInteger(req.requestItemId) || req.requestItemId < 1 ||
      !req.values || !/^[a-z0-9][a-z0-9-]{0,39}$/.test(req.values.PPGCoverOutputRevision || '') ||
      typeof req.templateVersion !== 'string' || !req.templateVersion.trim() ||
      typeof req.pinsJson !== 'string' || utf8(req.pinsJson).length > 100000) throw Error('native_request_invalid');
  const pins: NativePin[] = JSON.parse(req.pinsJson);
  const roles = ['request','compiled-template','maintained-template','source-pack','source-job','source-receipt','engine'];
  if (full) roles.push('full-document-input');
  if (req.intakeScopeJson) roles.push('selected-baseline','selected-draft');
  if (!Array.isArray(pins) || pins.length !== roles.length || new Set(pins.map(p => p.role)).size !== roles.length ||
      pins.some(p => roles.indexOf(p.role) < 0 || [p.UniqueId,p.ETag,p.UIVersionLabel,p.ServerRelativeUrl].some(v => typeof v !== 'string' || !v.trim()) ||
        typeof p.Length !== 'string' || !/^\d+$/.test(p.Length))) throw Error('native_pins_missing');
  const sourceJob: Job = JSON.parse(req.sourceJobJson);
  const receipt: { jobSHA256: string; package: { sha256: string; UniqueId: string; ETag: string; Length: string } } = JSON.parse(req.sourceReceiptJson);
  if (!sourceJob || (sourceJob.schemaVersion !== 1 && sourceJob.schemaVersion !== 2) ||
      sourceJob.CaseUID !== req.values.PPGCoverCaseUID || !Array.isArray(sourceJob.includedRecordIDs) ||
      sha256(utf8(req.sourceJobJson)) !== receipt.jobSHA256 ||
      !req.sourcePin || req.sourcePin.UniqueId.toLowerCase() !== receipt.package.UniqueId.toLowerCase() ||
      req.sourcePin.ETag !== receipt.package.ETag || String(req.sourcePin.Length) !== String(receipt.package.Length) ||
      typeof req.sourcePin.ServerRelativeUrl !== 'string' || !req.sourcePin.ServerRelativeUrl.startsWith('/')) throw Error('frozen_package_binding_mismatch');
  if (!Array.isArray(contents) || contents.length !== (req.intakeScopeJson ? 3 : 2) || contents[0].path !== 'existing-pack.zip' ||
      contents[1].path !== 'maintained-template.docx' || (intakeScope && contents[2].path !== intakeScope.draftPackagePath)) throw Error('native_source_members_invalid');
  const source = decodeMember(contents[0].base64), originalTemplate = decodeMember(contents[1].base64);
  if (source.length + originalTemplate.length > rawLimit || source.length < 4 ||
      (!intakeScope && (source[0] !== 80 || source[1] !== 75 || source[2] !== 3 || source[3] !== 4)) ||
      source.length !== Number(req.sourcePin.Length) || sha256(source) !== receipt.package.sha256 ||
      sha256(originalTemplate) !== req.template.templateSHA256) throw Error('native_source_hash_mismatch');
  const coverJson = JSON.stringify({templateSHA256:req.template.templateSHA256,parts:req.template.parts,values:req.values});
  const fullJson = full ? JSON.stringify({template:req.template,input:JSON.parse(req.fullDocumentInputJson || 'null')}) : '';
  const fullInput: FullReviewValues | undefined = full ? JSON.parse(req.fullDocumentInputJson || 'null') : undefined;
  let includedRecordIDs=sourceJob.includedRecordIDs.slice();
  if (full && req.sourceSelectionJson) {
    const selection: {kind:string;CaseUID:string;currentPolicyClaim:boolean;nextOccurrenceFindingsInherited:boolean;
      candidate:{DocumentReference:string;UniqueId:string;ETag:string;SHA256:string};
      includedEvents:{[key:string]:{CaseUID:string;EventUID:string;DocumentReference:string;ReviewedVersionRef:string;DocumentSHA256:string;FictionalTest:boolean}[]}}=JSON.parse(req.sourceSelectionJson);
    if(selection.kind!=='fictional-lifecycle-revision-selection-v1' || selection.CaseUID!==sourceJob.CaseUID || selection.currentPolicyClaim!==false || selection.nextOccurrenceFindingsInherited!==false)throw Error('full_selection_scope_invalid');
    for(const kind of Object.keys(selection.includedEvents))for(const event of selection.includedEvents[kind]){
      if(event.CaseUID!==sourceJob.CaseUID || event.FictionalTest!==true || event.DocumentReference!==selection.candidate.DocumentReference || event.DocumentSHA256!==selection.candidate.SHA256 || event.ReviewedVersionRef!=='sharepoint:'+selection.candidate.UniqueId+':'+selection.candidate.ETag || !event.EventUID)throw Error('full_event_scope_invalid');
      includedRecordIDs.push(event.EventUID);
    }
    if(new Set(includedRecordIDs).size!==includedRecordIDs.length)throw Error('full_record_duplicate');
  }
  if (full && (!fullInput || fullInput.CaseUID !== sourceJob.CaseUID || fullInput.outputRevision !== req.values.PPGCoverOutputRevision ||
      fullInput.sourceSHA256 !== sha256(source) || fullInput.templateVersion !== req.templateVersion ||
      JSON.stringify(fullInput.includedRecordIDs) !== JSON.stringify(includedRecordIDs))) throw Error('full_source_identity_mismatch');
  const cover = full ? fullDocumentBytes(fullJson) : coverBytes(coverJson), sourceSHA = sha256(source);
  const frozen = JSON.stringify({requestItemId:req.requestItemId,templateVersion:req.templateVersion,
    templateSHA256:req.template.templateSHA256,compiledPartsSHA256:sha256(utf8(JSON.stringify(req.template.parts))),
    values:req.values,sourceJobSHA256:receipt.jobSHA256,sourcePackageSHA256:sourceSHA,
    sourcePin:req.sourcePin,pinsJson:req.pinsJson,selectionKind:'existing-frozen-package',
    ...(full ? {fullDocumentInputJson:req.fullDocumentInputJson,sourceSelectionJson:req.sourceSelectionJson || '',generationRoute:'standard-office-script-full-review-v1'} : {}),
    ...(req.intakeScopeJson ? {intakeScopeJson:req.intakeScopeJson} : {}),
    ...(req.includeFinalisationMembers === true ? {savedBodyFinalisationProtocol:'v1'} : {})});
  const requestSHA = sha256(utf8(frozen)), jobId = 'job-item'+req.requestItemId+'-'+req.values.PPGCoverOutputRevision;
  let created = req.createdAtUtc, generationRunId = req.generationRunId;
  let old: NativeClaim | undefined;
  if (req.existingClaimJson) {
    old = JSON.parse(req.existingClaimJson);
    if (!old || old.kind !== 'PPG-native-package-claim-v1' || old.jobId !== jobId || old.requestSHA256 !== requestSHA)
      throw Error('native_request_changed_requires_new_revision');
    created = old.createdAtUtc; generationRunId = old.generationRunId;
    if (!/^[A-Za-z0-9_-]{1,100}$/.test(generationRunId || '')) throw Error('native_claim_run_missing');
  }
  const sourceSelection = utf8(req.sourceJobJson), snapshot = utf8(frozen);
  const documentPath=full ? 'document/PPG-review-DRAFT.docx' : 'cover/PPG-cover-DRAFT.docx';
  const job: Job & { coverSnapshot: CoverContract; selectionKind: string; parentJobSHA256: string; generationRunId: string } = {
    schemaVersion:1,jobId,documentKind:full ? 'full-review-and-existing-package' : 'fixed-cover-and-existing-package',CaseUID:sourceJob.CaseUID,
    sourceSnapshotRef:req.sourcePin.ServerRelativeUrl,sourceSHA256:sourceSHA,
    templateVersion:req.templateVersion,templateSHA256:req.template.templateSHA256,
    outputRevision:req.values.PPGCoverOutputRevision,includedRecordIDs,
    createdAtUtc:created,generationRunId,selectionKind:'existing-frozen-package',parentJobSHA256:receipt.jobSHA256,
    coverSnapshot:{route:full ? 'standard-office-script-full-review-v1' : 'standard-office-script-fixed-cover-v1',manifestSHA256:sha256(utf8(full ? fullJson : coverJson)),
      templateSHA256:req.template.templateSHA256,path:documentPath},
    members:[
      {path:documentPath,sha256:sha256(cover),size:cover.length,sourceReference:full ? 'maintained-full-review-template' : 'maintained-cover-template',sourceVersionRef:req.templateVersion},
      {path:sourcePath,sha256:sourceSHA,size:source.length,sourceReference:req.sourcePin.ServerRelativeUrl,sourceVersionRef:req.sourcePin.ETag},
      {path:'selection/frozen-source-job.json',sha256:sha256(sourceSelection),size:sourceSelection.length,sourceReference:'existing-frozen-source-job',sourceVersionRef:receipt.jobSHA256},
      {path:'generation/request-snapshot.json',sha256:sha256(snapshot),size:snapshot.length,sourceReference:'SharePoint request item '+req.requestItemId,sourceVersionRef:requestSHA}
    ]};
  if(req.intakeScopeJson){
    const extra=decodeMember(contents[2].base64), scope:{draftReference:string;draftPin:NativePin}=JSON.parse(req.intakeScopeJson);
    job.members.push({path:contents[2].path,sha256:sha256(extra),size:extra.length,sourceReference:scope.draftReference,sourceVersionRef:scope.draftPin.ETag});
  }
  const jobJson = JSON.stringify(job), hash = sha256(utf8(jobJson));
  if (old && old.jobSHA256 !== hash) throw Error('native_claim_job_mismatch');
  const claim: NativeClaim = {kind:'PPG-native-package-claim-v1',jobId,requestSHA256:requestSHA,jobSHA256:hash,createdAtUtc:created,generationRunId};
  const members = [{path:sourcePath,base64:contents[0].base64},
    {path:'selection/frozen-source-job.json',base64:encodeBase64(sourceSelection)},
    {path:'generation/request-snapshot.json',base64:encodeBase64(snapshot)}];
  if(req.intakeScopeJson)members.push(contents[2]);
  const result: PackageResult = JSON.parse(full ? packageJob(jobJson,JSON.stringify([{path:documentPath,base64:encodeBase64(cover)},...members]),rawLimit) : packageCover(jobJson,JSON.stringify(members),coverJson));
  if (full) {
    result.wordGenerationPerformed=true; result.coverSHA256=sha256(cover); result.coverBytes=cover.length;
    result.coverBase64=encodeBase64(cover); result.generationRoute='standard-office-script-full-review-v1';
  }
  const response = JSON.stringify({...result,
    ...(req.includeFinalisationMembers === true ? {zipBase64:''} : {}),
    requestSHA256:requestSHA,claimJson:JSON.stringify(claim),jobJson,
    ...(req.includeFinalisationMembers === true ? {finalisationMembersJson:JSON.stringify(members)} : {})});
  if (utf8(response).length > MAX_WIRE_BYTES) throw Error('response_limit');
  return response;
}

interface IntakeCase { Id:number;CaseUID:string;Title:string;linkedDocumentUIDs:string;sourceBaselineRef:string;evidenceDraftLink:string;
  'odata.etag':string;OData__UIVersionString:string;caseStatus?:string;proposedOutcome?:string;accountableRole?:string;nextAction?:string; }
interface IntakeRow {Id:number;DocumentUID:string;sourceDocumentId:string;sourceSnapshotRef:string;rawSourceRecordRef:string;'odata.etag':string;}
interface CaseIntakeRequest extends NativeCoverRequest {
  intake:{site:string;mode:string;expectedCaseUID:string;case: IntakeCase;catalogue: IntakeRow[];baselinePin:NativePin;draftPin:NativePin;
    eventSets?:{[key:string]:{value:{CaseUID:string}[];[key:string]:{CaseUID:string}[]|string}};
    historicalSelection?:{kind:string;caseBinding:IntakeCase;catalogueBinding:{records:IntakeRow[]};sources:{role:string;sourceReference:string;nativePin:NativePin;sha256:string}[]};};
}
function nativeCaseIntake(requestJson:string,membersJson:string):string {
  if(utf8(JSON.stringify({requestJson,membersJson})).length>MAX_WIRE_BYTES)throw Error('request_limit');
  const req:CaseIntakeRequest=JSON.parse(requestJson), x=req.intake, c=x.case, rows=x.catalogue, members:Content[]=JSON.parse(membersJson);
  const lifecycle=x.mode==='fictional-initiated-source';
  const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if(!x || (lifecycle?!/^LC-FICTIONAL-[A-Za-z0-9-]{1,180}$/.test(c.CaseUID):!uuid.test(c.CaseUID)) || c.CaseUID!==x.expectedCaseUID || !Number.isSafeInteger(c.Id) || c.Id<1 || !c['odata.etag'] || !c.OData__UIVersionString || !c.Title ||
     !/^https:\/\/[^/]+\.sharepoint\.com\/(sites|teams)\/[^?#]+$/.test(x.site) || !['catalogue-current','recorded-baseline','fictional-initiated-source'].includes(x.mode))throw Error('intake_case_invalid');
  function path(ref:string):string{
    if(typeof ref!=='string'||!ref.startsWith(x.site+'/')||/[?#\\]/.test(ref))throw Error('intake_source_outside_site');
    const p=decodeURIComponent(ref.slice(ref.indexOf('/',8)));
    if(p.split('/').some(v=>v==='.'||v==='..')||p.includes('%'))throw Error('intake_source_outside_site');return p;
  }
  const ids:string[]=JSON.parse(c.linkedDocumentUIDs);
  if(!Array.isArray(ids)||!ids.length||ids.length>200||ids.some(v=>typeof v!=='string'||!v.trim()||(!lifecycle&&!uuid.test(v)))||new Set(ids).size!==ids.length ||
     !Array.isArray(rows)||(!lifecycle&&(rows.length!==ids.length||new Set(rows.map(r=>r.DocumentUID)).size!==ids.length))||
     rows.some(r=>!ids.includes(r.DocumentUID)||!r['odata.etag']||!r.sourceDocumentId||!r.rawSourceRecordRef))throw Error('intake_catalogue_identity_unresolved');
  if(members.length!==3||members[0].path!=='existing-pack.zip'||members[1].path!=='maintained-template.docx'||members[2].path!=='evidence/selected-draft.docx')throw Error('intake_members_invalid');
  const baseline=decodeMember(members[0].base64), draft=decodeMember(members[2].base64);
  const jsonBaseline=c.sourceBaselineRef.toLowerCase().endsWith('.json');
  for(const pair of [{ref:c.sourceBaselineRef,pin:x.baselinePin,raw:baseline,suffix:jsonBaseline?'.json':'.zip'},{ref:c.evidenceDraftLink,pin:x.draftPin,raw:draft,suffix:lifecycle?'.txt':'.docx'}]){
    if(path(pair.ref)!==pair.pin.ServerRelativeUrl||!pair.ref.toLowerCase().endsWith(pair.suffix)||!uuid.test(pair.pin.UniqueId)||!pair.pin.ETag||!pair.pin.UIVersionLabel||
      String(pair.raw.length)!==String(pair.pin.Length)||pair.raw.length<4)throw Error('intake_file_binding_invalid');
    if(['.zip','.docx'].includes(pair.suffix)&&(pair.raw[0]!==80||pair.raw[1]!==75||pair.raw[2]!==3||pair.raw[3]!==4))throw Error('intake_file_binding_invalid');
  }
  if(jsonBaseline){const capture=JSON.parse(textFromUtf8(baseline));if(!capture||typeof capture!=='object')throw Error('intake_capture_invalid');}
  if(lifecycle){
    const request:{request:{CaseUID:string;DocumentUID:string;occurrenceReference:string;qualificationOnly:boolean;realPolicyEffects:boolean;DocumentReference:string;ReviewedVersionRef:string;DocumentSHA256:string}}=JSON.parse(textFromUtf8(baseline)),r=request.request;
    if(!jsonBaseline||!c.caseStatus||!c.caseStatus.startsWith('Initiated')||rows.length||!r||r.CaseUID!==c.CaseUID||r.qualificationOnly!==true||r.realPolicyEffects!==false||!r.occurrenceReference||
      JSON.stringify(ids)!==JSON.stringify([r.DocumentUID])||r.DocumentReference!==c.evidenceDraftLink||r.ReviewedVersionRef!=='sharepoint:'+x.draftPin.UniqueId+':'+x.draftPin.ETag||r.DocumentSHA256!==sha256(draft))throw Error('initiated_source_binding_mismatch');
    textFromUtf8(draft);
    if(!x.eventSets||Object.keys(x.eventSets).sort().join()!=='assurance,consultation,readiness'||Object.keys(x.eventSets).some(k=>!Array.isArray(x.eventSets[k].value)||x.eventSets[k].value.length||['nextLink','odata.nextLink','@odata.nextLink'].some(n=>!!x.eventSets![k][n])))throw Error('new_occurrence_has_events_or_incomplete_read');
  }else if(x.mode==='catalogue-current'){
    if(rows.some(r=>r.sourceSnapshotRef!==c.sourceBaselineRef))throw Error('catalogue_baseline_mismatch');
  }else{
    const h=x.historicalSelection;
    if(!h||h.kind!=='existing-case-artifact-selection'||['Id','CaseUID','linkedDocumentUIDs','sourceBaselineRef','evidenceDraftLink','odata.etag','OData__UIVersionString'].some(k=>JSON.stringify(h.caseBinding[k as keyof IntakeCase])!==JSON.stringify(c[k as keyof IntakeCase]))||
      h.catalogueBinding.records.length!==ids.length||h.catalogueBinding.records.some(r=>!ids.includes(r.DocumentUID)||r.sourceSnapshotRef!==c.sourceBaselineRef)||
      new Set(h.catalogueBinding.records.map(r=>r.DocumentUID)).size!==ids.length)throw Error('historical_case_binding_mismatch');
    const originals=h.sources.filter(s=>s.role==='recorded-baseline');
    if(originals.length!==1||originals[0].sourceReference!==c.sourceBaselineRef||originals[0].sha256!==sha256(baseline)||
      ['UniqueId','ETag','Length','UIVersionLabel','ServerRelativeUrl'].some(k=>originals[0].nativePin[k as keyof NativePin]!==x.baselinePin[k as keyof NativePin]))throw Error('historical_baseline_changed');
  }
  const scope={kind:'catalogue-case-intake-v1',mode:x.mode,CaseUID:c.CaseUID,case:c,catalogue:rows,
    historicalSelection:x.mode==='recorded-baseline'?x.historicalSelection:null,
    baselineReference:c.sourceBaselineRef,baselinePin:x.baselinePin,baselineSHA256:sha256(baseline),baselinePackagePath:'evidence/recorded-baseline.'+(jsonBaseline?'json':'zip'),
    draftReference:c.evidenceDraftLink,draftPin:x.draftPin,draftSHA256:sha256(draft),
    draftPackagePath:lifecycle?'evidence/original-source.txt':'evidence/selected-draft.docx',
    draftScope:lifecycle?'exact original source for initiated fictional occurrence; no candidate selected':'freshly observed existing manual draft; not asserted byte-identical to historical draft',
    ...(lifecycle?{ownOccurrenceEvents:x.eventSets}:{}),
    currentPolicyClaim:false,businessReviewPerformed:false,findingsInherited:false,sourceWrites:false,caseWrites:false};
  const scopeJson=JSON.stringify(scope);
  const sourceJob:Job={schemaVersion:1,jobId:'job-case-item'+c.Id+'-'+req.values.PPGCoverOutputRevision,documentKind:lifecycle?'read-only-initiated-fictional-source-intake':'read-only-catalogue-case-intake',CaseUID:c.CaseUID,
    sourceSnapshotRef:c.sourceBaselineRef,sourceSHA256:sha256(baseline),templateVersion:'catalogue-case-intake-v1',templateSHA256:sha256(utf8('catalogue-case-intake-v1')),
    outputRevision:req.values.PPGCoverOutputRevision,includedRecordIDs:ids,createdAtUtc:req.existingClaimJson?JSON.parse(req.existingClaimJson).createdAtUtc:req.createdAtUtc,members:[]};
  const sourceJobJson=JSON.stringify({...sourceJob,selection:scope});
  const values:FullReviewValues={};for(const key of FULL_SCALARS)values[key]='Unresolved — no finding selected by this source-only intake.';
  values.case_title=c.Title;values.CaseUID=c.CaseUID;values.source_snapshot=encodeURI(c.sourceBaselineRef);values.version='DRAFT / '+(lifecycle?'INITIATED FICTIONAL SOURCE ONLY':x.mode==='recorded-baseline'?'RECORDED HISTORICAL BASELINE':'CATALOGUE-MATCHED SNAPSHOT')+' / currency unassessed';
  values.intended_result=c.proposedOutcome||'Unresolved';values.source_manifest='Recorded baseline '+encodeURI(c.sourceBaselineRef)+'\nSHA-256 '+sha256(baseline)+'\nBaseline version '+x.baselinePin.UIVersionLabel+'; case version '+c.OData__UIVersionString+'\nSelection mode '+x.mode+'; current policy currency is not assessed.';
  values.draft_links_and_changes=(lifecycle?'Exact original source (no existing candidate selected) ':'Separately pinned existing draft ')+encodeURI(c.evidenceDraftLink)+'\nSHA-256 '+sha256(draft)+'; native version '+x.draftPin.UIVersionLabel+'. Earlier draft bytes and proof are retained separately.';
  values.ownership_and_implementation='Recorded case value (acceptance unassessed): '+(c.accountableRole||'Unresolved');values.next_action=c.nextAction||'Unresolved';
  values.documentKind='catalogue-case-source-only-review-package';values.sourceSHA256=sha256(baseline);values.templateVersion=req.templateVersion;values.outputRevision=req.values.PPGCoverOutputRevision;values.includedRecordIDs=ids;
  values.OptionalContent='Source-only intake. Original baseline and selected draft are included unchanged. No review, approval, ownership acceptance or earlier occurrence findings are inferred.';
  values.comparison_rows=[];values.consultation_rows=[];
  req.kind='m365-full-review-request-v1';req.values={...req.values,PPGCoverCaseUID:c.CaseUID};req.sourcePin=x.baselinePin;
  req.sourceJobJson=sourceJobJson;req.sourceReceiptJson=JSON.stringify({jobSHA256:sha256(utf8(sourceJobJson)),package:{sha256:sha256(baseline),UniqueId:x.baselinePin.UniqueId,ETag:x.baselinePin.ETag,Length:x.baselinePin.Length}});
  req.fullDocumentInputJson=JSON.stringify(values);req.sourceSelectionJson='';req.intakeScopeJson=scopeJson;
  members[2].path=scope.draftPackagePath;
  return nativeCoverRequest(JSON.stringify(req),JSON.stringify(members),true);
}

interface FullReviewValues { [key: string]: string | string[] | { [key: string]: string }[]; }
interface FullReviewTemplate extends CoverInput {
  kind: string; mainXml: string;
  slots: { [key: string]: { block: boolean; paragraphProperties: string } };
  repeats: { [key: string]: { fields: string[]; wrapper: string; item: string } };
}
const FULL_SCALARS = ('case_title CaseUID source_snapshot version intended_result source_manifest draft_links_and_changes ownership_and_implementation decision_route candidate_reference reviewer_response operative_confirmation role_acceptance review_findings decision_evidence next_action measures documentKind sourceSHA256 templateVersion outputRevision includedRecordIDs OptionalContent').split(' ');
const FULL_GROUPS: { [key: string]: string[] } = {
  comparison_rows:['ComparisonSource','ComparisonGoverningSource','ComparisonControl','ComparisonChange','ComparisonGap'],
  consultation_rows:['ConsultationRole','ConsultationQuestion','ConsultationVersion','ConsultationResponse']
};
function fullDocumentBytes(fullJson: string): number[] {
  if (utf8(fullJson).length > 700000) throw Error('full_input_limit');
  const data: {template:FullReviewTemplate;input:FullReviewValues} = JSON.parse(fullJson), t=data.template, input=data.input;
  const fields=FULL_SCALARS.concat(Object.keys(FULL_GROUPS));
  if (!t || t.kind !== 'PPG-full-review-template-v1' || !input || Object.keys(input).sort().join() !== fields.slice().sort().join() ||
      Object.keys(t.slots).sort().join() !== FULL_SCALARS.concat(...Object.keys(FULL_GROUPS).map(k=>FULL_GROUPS[k])).sort().join() ||
      Object.keys(t.repeats).sort().join() !== Object.keys(FULL_GROUPS).sort().join()) throw Error('full_shape_invalid');
  function xmlText(value: string): string {
    if (typeof value !== 'string' || value.length > 12000 || /[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]|[\ud800-\udbff](?![\udc00-\udfff])|(^|[^\ud800-\udbff])[\udc00-\udfff]/.test(value)) throw Error('full_text_invalid');
    return value.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function textRuns(value: string): string {
    return value.replace(/\r\n?/g,'\n').split('\n').map(line=>line.split(/(https:\/\/[^\s<>"\[\]]+)/g).map(piece=>{
      const run='<w:r><w:t xml:space="preserve">'+xmlText(piece)+'</w:t></w:r>';
      // An explicit Word HYPERLINK field needs no external relationship and
      // preserves the exact evidence URL in the visible text and saved field.
      if (!piece.startsWith('https://')) return run;
      // Sentence delimiters following a URL belong to the visible prose, not
      // the target (for example "candidate.docx; version 2.0").
      const target=piece.replace(/[.,;]+$/g,''), suffix=piece.slice(target.length);
      return '<w:fldSimple w:instr=" HYPERLINK &quot;'+xmlText(target)+'&quot; "><w:r><w:t xml:space="preserve">'+xmlText(target)+'</w:t></w:r></w:fldSimple>'+(suffix ? '<w:r><w:t xml:space="preserve">'+xmlText(suffix)+'</w:t></w:r>' : '');
    }).join('')).join('<w:r><w:br/></w:r>');
  }
  function fill(xml: string, values: { [key: string]: string }): string {
    return xml.replace(/<!--PPG_VALUE:([A-Za-z_0-9]+)-->/g,(_,name:string)=>{
      if (!(name in values) || !t.slots[name]) throw Error('full_slot_missing');
      const slot=t.slots[name], runs=textRuns(values[name]);
      return slot.block ? '<w:p>'+slot.paragraphProperties+runs+'</w:p>' : runs;
    });
  }
  const scalars: { [key: string]: string } = {};
  for (const name of FULL_SCALARS) {
    const value=input[name];
    if (name === 'includedRecordIDs') {
      if (!Array.isArray(value) || !value.length || value.some(v=>typeof v !== 'string' || !v.trim()) || new Set(value).size !== value.length) throw Error('full_records_invalid');
      scalars[name]=(value as string[]).join('; ');
    } else { if (typeof value !== 'string') throw Error('full_scalar_invalid'); scalars[name]=value; }
    xmlText(scalars[name]);
  }
  if (['CaseUID','source_snapshot','version','documentKind','sourceSHA256','templateVersion','outputRevision'].some(k=>!scalars[k].trim()) || !/^[0-9a-f]{64}$/.test(scalars.sourceSHA256)) throw Error('full_identity_missing');
  let xml=t.mainXml;
  for (const name of Object.keys(FULL_GROUPS)) {
    const rows=input[name], repeat=t.repeats[name];
    if (!Array.isArray(rows) || rows.length > 50 || repeat.fields.join() !== FULL_GROUPS[name].join()) throw Error('full_repeat_invalid');
    const items=rows.map(row=>{
      if (!row || typeof row !== 'object' || Array.isArray(row) || Object.keys(row).sort().join() !== repeat.fields.slice().sort().join()) throw Error('full_row_invalid');
      return fill(repeat.item,row as { [key: string]: string });
    }).join('');
    const marker='<!--PPG_REPEAT:'+name+'-->';
    if (xml.split(marker).length !== 2 || repeat.wrapper.split('<!--PPG_ITEMS-->').length !== 2) throw Error('full_repeat_template_changed');
    xml=xml.replace(marker, rows.length ? repeat.wrapper.replace('<!--PPG_ITEMS-->',items) : '');
  }
  xml=fill(xml,scalars); let id=1000;
  // Generated hyperlinks are rich content. Retaining the template's plain-text
  // declaration passes schema validation but Word rejects the saved document.
  // Convert only the detached output controls; the maintained template is intact.
  xml=xml.replace(/<w:text(?:\s[^<>]*)?\/>/g,'<w:richText/>');
  xml=xml.replace(/<w:id w:val="-?\d+"\s*\/>/g,()=>'<w:id w:val="'+id+++'"/>');
  if (xml.includes('<!--PPG_') || xml.includes('<w:dataBinding') || !xml.includes('DRAFT') || xml.includes('<!DOCTYPE')) throw Error('full_output_invalid');
  const entries: ZipEntry[]=[],names=new Set<string>();let total=0,main=0;
  if (!Array.isArray(t.parts) || t.parts.length > 100 || !/^[0-9a-f]{64}$/.test(t.templateSHA256)) throw Error('full_parts_invalid');
  for (const part of t.parts) {
    safePath(part.path);const key=part.path.toLowerCase();if(names.has(key)) throw Error('full_part_collision');names.add(key);
    let bytes=decodeMember(part.base64);total+=bytes.length;
    if (total>300000 || sha256(bytes)!==part.sha256) throw Error('full_template_changed');
    if(part.path==='word/document.xml'){bytes=utf8(xml);main++;}
    entries.push({name:part.path,bytes});
  }
  if(main!==1 || !names.has('[content_types].xml') || !names.has('_rels/.rels')) throw Error('full_package_invalid');
  const result=storeZip(entries);if(result.length>MAX_RAW_BYTES)throw Error('full_document_limit');return result;
}
