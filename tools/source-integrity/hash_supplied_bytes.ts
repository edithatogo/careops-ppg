// Supplied-byte integrity only. No fetching, workbook access or identity decisions.
interface HashRequest {
  kind: string; qualificationId: string; sourceKey: string;
  expectedBytes: number; expectedSHA256: string; contentBase64: string;
}
const MAX_BYTES = 3 * 1024 * 1024;
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function decodeCanonical(text: string, expected: number): number[] {
  if (text.length !== 4 * Math.ceil(expected / 3)) throw new Error('base64_length');
  const padding = (3 - expected % 3) % 3;
  const end = text.length - padding;
  // Single pass: no unbounded regular-expression recursion on multi-MiB input.
  const bytes: number[] = [];
  let accumulator = 0, bits = 0;
  for (let i = 0; i < text.length; i++) {
    if (i >= end) {
      if (text[i] !== '=') throw new Error('base64_padding');
      continue;
    }
    const value = ALPHABET.indexOf(text[i]);
    if (value < 0) throw new Error('base64_alphabet');
    accumulator = (accumulator << 6) | value;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      bytes.push((accumulator >>> bits) & 255);
      accumulator &= (1 << bits) - 1;
    }
  }
  if (accumulator !== 0 || bytes.length !== expected) throw new Error('base64_canonical');
  return bytes;
}

function hashRequest(requestJson: string): string {
  if (typeof requestJson !== 'string' || requestJson.length > 4 * Math.ceil(MAX_BYTES / 3) + 1024) throw new Error('request_limit');
  const request = JSON.parse(requestJson) as HashRequest;
  const keys = ['kind', 'qualificationId', 'sourceKey', 'expectedBytes', 'expectedSHA256', 'contentBase64'];
  if (!request || typeof request !== 'object' || Array.isArray(request) ||
      Object.keys(request).length !== keys.length || keys.some(key => !Object.prototype.hasOwnProperty.call(request, key))) throw new Error('request_shape');
  if (request.kind !== 'ppg-supplied-byte-hash-v1' ||
      typeof request.qualificationId !== 'string' || !/^[a-zA-Z0-9-]{1,80}$/.test(request.qualificationId) ||
      typeof request.sourceKey !== 'string' || !/^[a-z0-9-]{1,80}$/.test(request.sourceKey)) throw new Error('request_identity');
  if (!Number.isInteger(request.expectedBytes) || request.expectedBytes < 0 || request.expectedBytes > MAX_BYTES ||
      typeof request.expectedSHA256 !== 'string' || !/^[0-9a-f]{64}$/.test(request.expectedSHA256) ||
      typeof request.contentBase64 !== 'string') throw new Error('request_profile');
  const bytes = decodeCanonical(request.contentBase64, request.expectedBytes);
  const actualSHA256 = sha256(bytes);
  return JSON.stringify({kind: 'ppg-supplied-byte-hash-result-v1',
    qualificationId: request.qualificationId, sourceKey: request.sourceKey,
    actualBytes: bytes.length, actualSHA256, expectedSHA256: request.expectedSHA256,
    integrityMatches: actualSHA256 === request.expectedSHA256,
    sourceProvenanceAuthenticated: false, nativeAcquisitionQualified: false});
}

function main(workbook: ExcelScript.Workbook, requestJson: string): string {
  return hashRequest(requestJson);
}

// Reused verbatim from tools/roles/role_projection.ts; existing owner unchanged.
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
