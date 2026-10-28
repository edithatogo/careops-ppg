/** File a bounded owner-guide draft through the caller's qualified no-retry route.
 * The caller must qualify library notification effects and actual user scope first.
 * No authentication, activation, approval, source mutation or send occurs here.
 */
import assert from 'node:assert/strict';
import crypto from 'node:crypto';

export const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
export function canonical(value) {
  return JSON.stringify(value, (_key, item) => item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
}

export function draftFiles(request, preparation, candidate) {
  assert.match(request.requestUID, /^GUIDE-[A-Za-z0-9-]{1,90}$/);
  assert.equal(request.documentUID, 'PPG-WORKBENCH-OPERATOR-GUIDE');
  assert.equal(request.scope, 'owner-approved-workbench');
  assert.equal(request.issued, false);
  assert.equal(request.approvalRecorded, false);
  assert.equal(request.notificationsAllowed, false);
  assert.equal(request.nativeDataWrites, 0);
  assert.equal(request.candidateSHA256, sha256(candidate));
  assert.equal(preparation.candidateSHA256, request.candidateSHA256);
  assert.equal(preparation.nativeRequestSHA256, sha256(canonical(request)));
  assert.equal(preparation.requestUID, request.requestUID);
  assert.equal(preparation.occurrenceUID, request.occurrenceUID);
  assert.equal(canonical(preparation.source), canonical(request.source));
  assert.equal(preparation.state, 'Awaiting agent review');
  assert.equal(preparation.userAcceptance, null);
  const {preparationSHA256, ...body} = preparation;
  assert.equal(preparationSHA256, sha256(canonical(body)));
  return [
    {name: request.requestUID + '-request.json', bytes: Buffer.from(canonical(request) + '\n')},
    {name: request.requestUID + '-draft-r1.md', bytes: Buffer.from(candidate)},
    {name: request.requestUID + '-preparation.json', bytes: Buffer.from(canonical(preparation) + '\n')}
  ];
}

export async function fileDraft(args) {
  return fileRows(args, draftFiles(args.request, args.preparation, args.candidate));
}

function validateTarget({request, siteUrl, folder, checkpoint}) {
  const site = new URL(siteUrl);
  assert.equal(site.protocol, 'https:');
  assert.equal(site.username + site.password + site.search + site.hash, '');
  assert(folder.startsWith(site.pathname + '/PPG Review Evidence/'));
  assert(!folder.includes('..') && !folder.includes('?') && !folder.includes('#'));
  assert.match(request.source.nativeId, /^[a-f0-9-]{36}$/i);
  assert(request.source.etag && request.source.etag !== '*');
  const sourceReference = new URL(request.source.reference);
  assert.equal(sourceReference.origin, site.origin);
  assert.equal(sourceReference.username + sourceReference.password + sourceReference.search + sourceReference.hash, '');
  assert.equal(typeof checkpoint, 'function');
}

async function fileRows(args, files) {
  validateTarget(args);
  const {request, siteUrl, folder, req, checkpoint} = args;
  const sourceReference = new URL(request.source.reference);
  const escape = value => value.replaceAll("'", "''");
  const folderApi = siteUrl + "/_api/web/GetFolderByServerRelativePath(decodedurl='" + escape(folder) + "')";
  const sourceApi = siteUrl + "/_api/web/GetFileById('" + request.source.nativeId + "')";
  async function sourcePin() {
    const meta = (await req('GET', sourceApi + '?$select=UniqueId,ETag,UIVersionLabel,ServerRelativeUrl')).data;
    assert.equal(meta.UniqueId, request.source.nativeId);
    assert.equal(meta.ETag, request.source.etag);
    assert.equal(meta.UIVersionLabel, request.source.nativeVersion);
    assert.equal(meta.ServerRelativeUrl, decodeURIComponent(sourceReference.pathname));
    return meta;
  }
  await sourcePin();
  const source = Buffer.from((await req('GET', sourceApi + '/$value', {responseType: 'arraybuffer'})).data);
  assert.equal(sha256(source), request.source.sha256);
  const existing = (await req('GET', folderApi + '/Files?$select=Name,UniqueId,ETag,Length,UIVersionLabel')).data;
  assert(Array.isArray(existing.value));
  assert(!existing['odata.nextLink'] && !existing['@odata.nextLink']);
  let creates = 0;
  const results = [];
  for (const file of files) {
    const found = existing.value.filter(row => row.Name === file.name);
    assert(found.length <= 1);
    if (!found.length) {
      const url = folderApi + "/Files/Add(url='" + escape(file.name) + "',overwrite=false)";
      // Durable, exclusive intent must complete before transport. On uncertainty,
      // stop. A later invocation reconciles native bytes before another attempt.
      await checkpoint({kind: 'intent', name: file.name, method: 'POST', url, bodySHA256: sha256(file.bytes)});
      await req('POST', url, {data: file.bytes, headers: {'Content-Type': 'application/octet-stream'}});
      creates++;
    }
    const api = siteUrl + "/_api/web/GetFileByServerRelativePath(decodedurl='" + escape(folder + '/' + file.name) + "')";
    const actual = Buffer.from((await req('GET', api + '/$value', {responseType: 'arraybuffer'})).data);
    assert.equal(sha256(actual), sha256(file.bytes), 'existing_or_saved_file_bytes_differ');
    const meta = (await req('GET', api + '?$select=UniqueId,ETag,Length,UIVersionLabel')).data;
    assert(meta.UniqueId && meta.ETag && meta.UIVersionLabel);
    assert.equal(Number(meta.Length), actual.length);
    const receipt = {name: file.name, created: !found.length, sha256: sha256(actual), native: meta};
    await checkpoint({kind: 'verified', ...receipt});
    results.push(receipt);
  }
  await sourcePin();
  return {creates, preserved: files.length - creates, files: results, issued: false, notifications: 0};
}


export async function fileAcceptance(args, review, decision, artifactPin) {
  const {request, preparation, candidate, req, siteUrl, folder} = args;
  draftFiles(request, preparation, candidate);
  validateTarget(args);
  const {reviewSHA256, ...reviewBody} = review;
  const {decisionSHA256, ...decisionBody} = decision;
  assert.equal(reviewSHA256, sha256(canonical(reviewBody)));
  assert.equal(decisionSHA256, sha256(canonical(decisionBody)));
  assert.equal(review.preparation.preparationSHA256, preparation.preparationSHA256);
  assert.deepEqual(review.blockers, []);
  assert.equal(decision.reviewSHA256, reviewSHA256);
  assert.equal(decision.candidateSHA256, sha256(candidate));
  assert.equal(decision.decision.candidateSHA256, sha256(candidate));
  assert.equal(decision.decision.reviewSHA256, reviewSHA256);
  assert.equal(decision.decision.decision, 'accept');
  assert.equal(decision.decision.scope, 'owner-approved-workbench');
  assert(decision.decision.userInstructionReference);
  assert.match(decision.decision.effectiveDate, /^\d{4}-\d{2}-\d{2}$/);
  assert.equal(decision.issued, false);
  assert.equal(decision.officialCurrent, false);
  const name = request.requestUID + '-draft-r1.md';
  const artifactPath = folder + '/' + name;
  const api = siteUrl + "/_api/web/GetFileByServerRelativePath(decodedurl='" + artifactPath.replaceAll("'", "''") + "')";
  async function checkArtifact() {
    const meta = (await req('GET', api + '?$select=UniqueId,ETag,Length,UIVersionLabel')).data;
    for (const key of ['UniqueId', 'ETag', 'UIVersionLabel', 'Length']) assert.equal(String(meta[key]), String(artifactPin[key]));
    const raw = Buffer.from((await req('GET', api + '/$value', {responseType: 'arraybuffer'})).data);
    assert.equal(sha256(raw), decision.candidateSHA256);
  }
  await checkArtifact();
  const record = {
    kind: 'owner-controlled-master-record', schemaVersion: 1,
    documentUID: request.documentUID, edition: request.proposedEdition,
    occurrenceUID: request.occurrenceUID, scope: 'owner-approved-workbench',
    state: 'Accepted for workbench use', acceptedForWorkbenchUse: true,
    acceptedArtifact: {reference: new URL(artifactPath, siteUrl).href,
      sha256: decision.candidateSHA256, native: artifactPin},
    source: request.source, decisionSHA256, reviewSHA256,
    effectiveDate: decision.decision.effectiveDate,
    userInstructionReference: decision.decision.userInstructionReference,
    sourceAndPriorEditionsPreserved: true,
    supersession: 'Separate owner-controlled edition; earlier guide and issued history retained unchanged',
    contentStatusNote: 'The exact reviewed draft bytes remain unchanged. This version-bound record establishes owner acceptance; institutional issuance remains held.',
    officialCurrent: false, issued: false, notificationsAllowed: false
  };
  const files = [['review.json', review], ['decision.json', decision], ['master-record.json', record]]
    .map(([suffix, value]) => ({name: request.requestUID + '-' + suffix, bytes: Buffer.from(canonical(value) + '\n')}));
  const result = await fileRows(args, files);
  await checkArtifact();
  return {...result, masterRecord: record, exactAcceptedArtifactVerified: true};
}
