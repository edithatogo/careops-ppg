/* Pure validation for the existing renewal owner's SDK result.
   No sign-in, token decoding, cache access, persistence or target calls. */
export function validateRenewalIdentity(result, expected) {
  const text = value => typeof value === 'string' && value.trim().length > 0;
  const guid = value => text(value) && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const same = (left, right) => typeof left === 'string' && left.toLowerCase() === right.toLowerCase();
  const refuse = code => { throw new Error(code); };
  if (!object(expected) || !text(expected.username) || !guid(expected.tenantId) || !guid(expected.appId)
      || (expected.objectId !== undefined && !guid(expected.objectId))) refuse('ExpectedIdentityIncomplete');
  if (!object(result)) refuse('SDKResultMissing');
  const account = result.account;
  const claims = result.idTokenClaims;
  if (account !== undefined && account !== null && !object(account)) refuse('SDKAccountMalformed');
  if (claims !== undefined && claims !== null && !object(claims)) refuse('SDKClaimsMalformed');
  const principals = [account?.username, claims?.preferred_username, claims?.upn].filter(value => value !== undefined && value !== null);
  const tenants = [result.tenantId, account?.tenantId, claims?.tid].filter(value => value !== undefined && value !== null && value !== '');
  if (!principals.length || principals.some(value => !text(value) || !same(value, expected.username))) refuse('SDKPrincipalUnverified');
  if (!tenants.length || tenants.some(value => !guid(value) || !same(value, expected.tenantId))) refuse('SDKTenantUnverified');
  // A null account needs complete SDK-provided ID claims, not fabricated cache
  // metadata or decoded bearer-token assertions. Require the intended client.
  const accountHasIdentity = object(account) && text(account.username);
  if (!accountHasIdentity && (!object(claims) || !text(claims.preferred_username ?? claims.upn)
      || !guid(claims.tid) || !same(claims.aud, expected.appId))) refuse('SDKNullAccountIdentityIncomplete');
  if (claims?.aud !== undefined && !same(claims.aud, expected.appId)) refuse('SDKClientMismatch');
  if (expected.objectId !== undefined) {
    const ids = [account?.localAccountId, claims?.oid].filter(value => value !== undefined && value !== null);
    if (!ids.length || ids.some(value => !guid(value) || !same(value, expected.objectId))) refuse('SDKObjectIdentityUnverified');
  }
  return Object.freeze({ identityMetadataMatches: true,
    identitySource: accountHasIdentity ? 'sdk-account' : 'sdk-id-token-claims',
    targetAccessVerified: false, nativeWritePermitted: false });
}
