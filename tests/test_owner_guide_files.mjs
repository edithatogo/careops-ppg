import test from 'node:test';
import assert from 'node:assert/strict';
import {canonical, sha256, draftFiles, fileDraft} from '../tools/lifecycle/file_owner_guide.mjs';

function fixture() {
  const raw = Buffer.from('synthetic source'), candidate = Buffer.from('synthetic edited guide');
  const source = {nativeId: '00000000-0000-4000-8000-000000000001', nativeVersion: '1.0', etag: '"1"', sha256: sha256(raw), reference: 'https://example.invalid/sites/workbench/source.md'};
  const request = {requestUID: 'GUIDE-synthetic-01', occurrenceUID: 'synthetic-01', documentUID: 'PPG-WORKBENCH-OPERATOR-GUIDE', scope: 'owner-approved-workbench', issued: false, approvalRecorded: false, notificationsAllowed: false, nativeDataWrites: 0, candidateSHA256: sha256(candidate), source};
  const preparation = {candidateSHA256: request.candidateSHA256, nativeRequestSHA256: sha256(canonical(request)), requestUID: request.requestUID, occurrenceUID: request.occurrenceUID, source, state: 'Awaiting agent review', userAcceptance: null};
  preparation.preparationSHA256 = sha256(canonical(preparation));
  const stored = new Map(); let sends = 0;
  const req = async (method, url, options) => {
    if (method === 'POST') {
      sends++;
      assert(url.endsWith("overwrite=false)"));
      const name = url.match(/Files\/Add\(url='([^']+)'/)[1];
      assert(!stored.has(name)); stored.set(name, Buffer.from(options.data));
      return {data: {}};
    }
    assert.equal(method, 'GET');
    if (url.includes('GetFileById')) return {data: url.endsWith('/$value') ? raw : {UniqueId: source.nativeId, ETag: source.etag, UIVersionLabel: source.nativeVersion, ServerRelativeUrl: new URL(source.reference).pathname}};
    if (url.includes('/Files?')) return {data: {value: [...stored].map(([Name]) => ({Name}))}};
    const name = url.match(/decodedurl='([^']+)'/)[1].split('/').at(-1);
    assert(stored.has(name));
    return {data: url.endsWith('/$value') ? stored.get(name) : {UniqueId: name, ETag: '"1"', UIVersionLabel: '1.0', Length: stored.get(name).length}};
  };
  return {request, preparation, candidate, stored, sends: () => sends, args: {request, preparation, candidate, siteUrl: 'https://example.invalid/sites/workbench', folder: '/sites/workbench/PPG Review Evidence/synthetic', req, checkpoint: async () => {}}};
}

test('controlled interruption resumes only missing proof; replay preserves edits and files', async () => {
  const f = fixture(); let verified = 0;
  await assert.rejects(fileDraft({...f.args, checkpoint: async e => {if (e.kind === 'verified' && ++verified === 2) throw Error('controlled-stop');}}), /controlled-stop/);
  assert.equal(f.sends(), 2);
  const recovered = await fileDraft(f.args);
  assert.equal(recovered.creates, 1); assert.equal(recovered.preserved, 2);
  const replay = await fileDraft(f.args);
  assert.equal(replay.creates, 0); assert.equal(f.sends(), 3);
  assert.equal(replay.issued, false);
});

test('changed native request or candidate is refused before replacing existing draft', async () => {
  const f = fixture(); await fileDraft(f.args);
  const saved = Buffer.from(f.stored.get('GUIDE-synthetic-01-draft-r1.md'));
  f.stored.set('GUIDE-synthetic-01-request.json', Buffer.from('competing request'));
  await assert.rejects(fileDraft(f.args), /existing_or_saved_file_bytes_differ/);
  assert.equal(f.sends(), 3); assert.deepEqual(f.stored.get('GUIDE-synthetic-01-draft-r1.md'), saved);
  assert.throws(() => draftFiles(f.request, f.preparation, Buffer.from('changed')));
});

test('unqualified source or destination refuses all writes', async () => {
  const f = fixture();
  await assert.rejects(fileDraft({...f.args, folder: '/sites/workbench/Documents/wrong'}));
  await assert.rejects(fileDraft({...f.args, req: async () => ({data: {UniqueId: 'different'}})}));
  assert.equal(f.sends(), 0);
});

async function acceptedFixture() {
  const f = fixture(); await fileDraft(f.args);
  const review = {preparation: f.preparation, blockers: []};
  review.reviewSHA256 = sha256(canonical(review));
  const decision = {reviewSHA256: review.reviewSHA256, candidateSHA256: sha256(f.candidate),
    decision: {candidateSHA256: sha256(f.candidate), reviewSHA256: review.reviewSHA256,
      decision: 'accept', scope: 'owner-approved-workbench',
      userInstructionReference: 'synthetic:explicit-user-decision', effectiveDate: '2026-10-28'},
    issued: false, officialCurrent: false};
  decision.decisionSHA256 = sha256(canonical(decision));
  return {...f, review, decision, pin: {UniqueId: f.request.requestUID + '-draft-r1.md', ETag: '"1"', UIVersionLabel: '1.0', Length: f.candidate.length}};
}

test('exact accepted revision files control records without institutional issuance', async () => {
  const {fileAcceptance} = await import('../tools/lifecycle/file_owner_guide.mjs');
  const f = await acceptedFixture();
  const result = await fileAcceptance(f.args, f.review, f.decision, f.pin);
  assert.equal(result.creates, 3);
  assert.equal(result.masterRecord.acceptedForWorkbenchUse, true);
  assert.equal(result.masterRecord.officialCurrent, false);
  assert.equal(result.masterRecord.issued, false);
  const replay = await fileAcceptance(f.args, f.review, f.decision, f.pin);
  assert.equal(replay.creates, 0);
});

test('editing accepted artifact or changing decision revision refuses acceptance filing', async () => {
  const {fileAcceptance} = await import('../tools/lifecycle/file_owner_guide.mjs');
  const f = await acceptedFixture();
  f.stored.set(f.request.requestUID + '-draft-r1.md', Buffer.from('preserve new human edit'));
  await assert.rejects(fileAcceptance(f.args, f.review, f.decision, f.pin));
  assert.equal(f.sends(), 3);
  const g = await acceptedFixture();
  g.decision.candidateSHA256 = 'a'.repeat(64);
  await assert.rejects(fileAcceptance(g.args, g.review, g.decision, g.pin));
  assert.equal(g.sends(), 3);
});


test('acceptance validates destination before any authenticated request', async () => {
  const {fileAcceptance} = await import('../tools/lifecycle/file_owner_guide.mjs');
  const f = await acceptedFixture();
  let requests = 0;
  const req = async () => { requests++; throw Error('unexpected transport'); };
  for (const invalid of [
    {folder: '/sites/workbench/Documents/wrong'},
    {siteUrl: 'https://other.invalid/sites/workbench'},
    {siteUrl: 'https://user:password@example.invalid/sites/workbench'},
    {checkpoint: undefined}
  ]) {
    await assert.rejects(fileAcceptance({...f.args, ...invalid, req}, f.review, f.decision, f.pin));
  }
  assert.equal(requests, 0);
  assert.equal(f.sends(), 3);
});
