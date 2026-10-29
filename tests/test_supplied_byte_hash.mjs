// Offline binary vectors: the VM has no workbook, network, Buffer or crypto API.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {stripTypeScriptTypes} from 'node:module';
const source = fs.readFileSync(new URL('../tools/source-integrity/hash_supplied_bytes.ts', import.meta.url), 'utf8');
const code = stripTypeScriptTypes(source);
const context = vm.createContext({});
vm.runInContext(code, context, {timeout: 5000});
const invoke = request => {
  context.requestJson = JSON.stringify(request);
  return JSON.parse(vm.runInContext('main(undefined, requestJson)', context, {timeout: 15000}));
};
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const request = bytes => ({kind: 'ppg-supplied-byte-hash-v1', qualificationId: 'fictional-proof',
  sourceKey: 'fictional-source', expectedBytes: bytes.length, expectedSHA256: digest(bytes), contentBase64: bytes.toString('base64')});
let checks = 0;
for (const length of [0, 1, 2, 3, 55, 56, 63, 64, 65, 127, 128, 129, 1025, 3*1024*1024]) {
  const bytes = Buffer.alloc(length);
  for (let i=0; i<length; i++) bytes[i] = (i*193+255)%256;
  const input = request(bytes), before = JSON.stringify(input), result = invoke(input);
  assert.equal(result.actualSHA256, digest(bytes));
  assert.equal(result.actualBytes, length);
  assert.equal(result.integrityMatches, true);
  assert.equal(result.sourceProvenanceAuthenticated, false);
  assert.equal(result.nativeAcquisitionQualified, false);
  assert.equal(JSON.stringify(input), before);
  assert.equal('contentBase64' in result, false);
  checks++;
}
assert.equal(invoke(request(Buffer.from('abc'))).actualSHA256,
  'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
const base = request(Buffer.from([255]));
for (const change of [{contentBase64: '/x=='}, {contentBase64: '_w=='}, {contentBase64: '/w=\n'},
  {contentBase64: '=w=='}, {contentBase64: '/w=A'}, {contentBase64: '/w==' ,expectedBytes: 2},
  {expectedBytes: -1}, {expectedBytes: 0.5}, {expectedBytes: 3*1024*1024+1},
  {expectedSHA256: 'A'.repeat(64)}, {expectedSHA256: null}, {sourceKey: '../escape'},
  {qualificationId: ''}, {kind: 'other'}, {contentBase64: null}, {extra: 'refuse'}]) {
  assert.throws(() => invoke({...base, ...change})); checks++;
}
for (const key of Object.keys(base)) {
  const missing = {...base}; delete missing[key]; assert.throws(() => invoke(missing)); checks++;
}
for (const invalid of [null, [], 1, 'text']) {assert.throws(() => invoke(invalid)); checks++;}
assert.throws(() => {context.requestJson = ' '.repeat(4*Math.ceil(3*1024*1024/3)+1025); vm.runInContext('main(undefined, requestJson)',context);});
const corrupt = {...base, contentBase64: 'AA=='};
assert.equal(invoke(corrupt).integrityMatches, false);
assert.equal(invoke(corrupt).actualSHA256, digest(Buffer.from([0])));
const wrongExpected = {...base, expectedSHA256: '0'.repeat(64)};
assert.equal(invoke(wrongExpected).integrityMatches, false);
assert.equal(invoke(wrongExpected).actualSHA256, digest(Buffer.from([255])));
if (process.argv[2]) {
  const bytes = fs.readFileSync(process.argv[2]);
  const result = invoke(request(bytes));
  assert.equal(result.actualSHA256, digest(bytes));
  assert.equal(result.integrityMatches, true);
  console.log(JSON.stringify({actualBytes: result.actualBytes, actualSHA256: result.actualSHA256,
    execution: 'offline-node-vm', nativeQualification: false}));
}
console.log(`Supplied-byte hash: ${checks} vector/rejection cases plus mismatch and request-limit checks passed.`);
