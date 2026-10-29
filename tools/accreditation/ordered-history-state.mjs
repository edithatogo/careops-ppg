/* Decide a bounded native history transition without issuing any request. */
function stableHistoryValue(value, parent = '') {
  if (Array.isArray(value)) return value.map(item => stableHistoryValue(item));
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.keys(value).sort().filter(key =>
    !(parent === '__metadata' && (key === 'id' || key === 'uri')) &&
    !(parent === '__deferred' && key === 'uri')
  ).map(key => [key, stableHistoryValue(value[key], key)]));
}

export function matchesSourceHistories(actual, captured) {
  if (!Array.isArray(actual) || !Array.isArray(captured) || actual.length !== captured.length) return false;
  const normalize = rows => rows.map(row => stableHistoryValue(row)).sort((a,b) => String(a.VersionLabel).localeCompare(String(b.VersionLabel)));
  const labels = actual.map(row => row.VersionLabel);
  return new Set(labels).size === labels.length && JSON.stringify(normalize(actual)) === JSON.stringify(normalize(captured));
}

function exactFields(actual, expected) {
  return Object.entries(expected).every(([key, value]) => {
    if (key === 'SourceCaptureLink' || key === 'RecoveryCopyURI') {
      if (value === null) return actual[key] === null;
      return actual[key]?.Url === value?.Url && actual[key]?.Description === value?.Description;
    }
    return Object.hasOwn(actual, key) && JSON.stringify(actual[key]) === JSON.stringify(value);
  });
}

export function decideOrderedHistory(actual, versions, plan) {
  if (!plan?.key || plan.firstValues?.RequirementKey !== plan.key ||
      plan.currentValues?.RequirementKey !== plan.key || !Array.isArray(versions)) throw Error('HISTORY_PLAN_INVALID');
  if (actual === null) {
    if (versions.length) throw Error('HISTORY_CONFLICT');
    return {action:'create'};
  }
  if (!actual || actual.RequirementKey !== plan.key || !Number.isInteger(actual.Id)) throw Error('HISTORY_CONFLICT');
  const byLabel = new Map(versions.map(version => [version.VersionLabel, version]));
  if (byLabel.size !== versions.length) throw Error('HISTORY_CONFLICT');
  const first = byLabel.get('1.0'), second = byLabel.get('2.0');
  if (!first || !exactFields(first, plan.firstValues)) throw Error('HISTORY_FIRST_VERSION_CONFLICT');
  if (actual.OData__UIVersionString === '1.0' && versions.length === 1 && first.IsCurrentVersion === true && exactFields(actual, plan.firstValues)) {
    const etag = actual.__metadata?.etag;
    if (typeof etag !== 'string' || !etag || etag === '*') throw Error('HISTORY_ETAG_REQUIRED');
    return {action:'update', id:actual.Id, etag};
  }
  if (actual.OData__UIVersionString === '2.0' && versions.length === 2 && first.IsCurrentVersion === false && second?.IsCurrentVersion === true &&
      exactFields(second, plan.currentValues) && exactFields(actual, plan.currentValues)) return {action:'noop', id:actual.Id};
  throw Error('HISTORY_CONFLICT');
}
