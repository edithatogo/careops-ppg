import test from 'node:test';
import assert from 'node:assert/strict';
import { validateRenewalIdentity } from '../tools/lifecycle/validate_renewal_identity.mjs';
const expected = { username: 'fictional@example.invalid',
  tenantId: '00000000-0000-4000-8000-000000000001',
  appId: '00000000-0000-4000-8000-000000000002',
  objectId: '00000000-0000-4000-8000-000000000003' };
const claims = { preferred_username: expected.username, tid: expected.tenantId,
  aud: expected.appId, oid: expected.objectId };
const account = { username: expected.username, tenantId: expected.tenantId, localAccountId: expected.objectId };
test('existing account and complete null-account SDK claims are supported without granting access', () => {
  for (const result of [{ account, tenantId: expected.tenantId }, { account: null, idTokenClaims: claims, tenantId: '' }]) {
    const before = structuredClone(result);
    const checked = validateRenewalIdentity(result, expected);
    assert.equal(checked.identityMetadataMatches, true);
    assert.equal(checked.targetAccessVerified, false);
    assert.equal(checked.nativeWritePermitted, false);
    assert.deepEqual(result, before);
  }
});
test('missing metadata and malformed or conflicting identities always refuse', () => {
  const invalid = [null, {}, { account: null }, { account: [] }, { idTokenClaims: 'invalid' },
    { account, tenantId: '00000000-0000-4000-8000-000000000099' },
    { account, idTokenClaims: { ...claims, preferred_username: 'other@example.invalid' } },
    { account: { ...account, username: '' }, idTokenClaims: claims },
    { account: null, idTokenClaims: { ...claims, aud: undefined } },
    { account: {}, idTokenClaims: { ...claims, aud: undefined } },
    { account: null, idTokenClaims: { ...claims, tid: undefined } },
    { account: null, idTokenClaims: { ...claims, aud: '00000000-0000-4000-8000-000000000099' } },
    { account: null, idTokenClaims: { ...claims, oid: '00000000-0000-4000-8000-000000000099' } }];
  for (const result of invalid) assert.throws(() => validateRenewalIdentity(result, expected));
});
test('bearer fields are never inspected or treated as identity evidence', () => {
  const result = { account, tenantId: expected.tenantId };
  Object.defineProperty(result, 'accessToken', { get() { throw new Error('Bearer must not be read'); } });
  assert.equal(validateRenewalIdentity(result, expected).identityMetadataMatches, true);
  assert.throws(() => validateRenewalIdentity({ accessToken: 'FICTIONAL-unverified-bearer' }, expected), /SDKPrincipalUnverified/);
});
