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
}
const MAX_WIRE_BYTES = 4000000;
const MAX_RAW_BYTES = 2000000;
const EXISTING_FORMAT_VERSION = "ppg-existing-artifacts-v1";
const EXISTING_FORMAT_SHA256 = "4c47e9f92f99047288af5dd477f7ccd6320e4a38a304f57992ab89fadf2e4113";
function main(workbook: ExcelScript.Workbook, jobJson: string, membersJson: string): PackageResult {
  // The workbook exists only to host the authorised Run script action.
  const envelope: { kind?: string; jobJson: string; coverJson: string } = JSON.parse(jobJson);
  if (utf8(JSON.stringify({jobJson,membersJson})).length > MAX_WIRE_BYTES) throw Error('request_limit');
  const result: PackageResult = JSON.parse(envelope.kind === 'standard-cover-input-v1' ?
    packageCover(envelope.jobJson, membersJson, envelope.coverJson) : packageJob(jobJson, membersJson));
  return result;
}
function packageJob(jobJson: string, membersJson: string): string {
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
    if (!Number.isInteger(expected.size) || expected.size < 0 || expected.size > MAX_RAW_BYTES ||
        !/^[0-9a-f]{64}$/.test(expected.sha256 || "")) throw Error("member_contract_invalid");
    if (typeof expected.sourceReference !== "string" || !expected.sourceReference.trim() ||
        typeof expected.sourceVersionRef !== "string" || !expected.sourceVersionRef.trim()) throw Error("member_provenance_missing");
    const bytes = decodeMember(actual.base64);
    total += bytes.length;
    if (total > MAX_RAW_BYTES) throw Error("complete_package_oversize");
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
  if (total + provenanceBytes.length > MAX_RAW_BYTES) throw Error("complete_package_oversize");
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
