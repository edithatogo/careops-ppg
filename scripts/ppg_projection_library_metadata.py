"""Describe a dated projection bundle using existing generic library properties."""
import hashlib
import json
import html
from datetime import date


def properties(bundle_bytes):
    runs = json.loads(bundle_bytes)
    if not isinstance(runs, list) or not runs:
        raise ValueError('Nonempty dated projection bundle required')
    entries, seen = [], set()
    for run in runs:
        m = run['manifest']
        if m['runKey'] in seen or run['projection']['asOf'] != m['asOf']:
            raise ValueError('Ambiguous projection run/date')
        seen.add(m['runKey'])
        if date.fromisoformat(m['asOf']).isoformat() != m['asOf']:
            raise ValueError('Canonical YYYY-MM-DD as-of date required')
        if any(m.get(k) is not False for k in ['sourceModified','grantsAccess','grantsClinicalAuthority']):
            raise ValueError('Derived projection must not confer authority')
        for key in ['sourceSha256','runKey','projectionLogicSha256','roleContractSha256']:
            value = m[key]
            if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('Invalid projection provenance hash')
        entries.append({key:m[key] for key in ['asOf','sourceSha256','runKey','projectionLogicSha256','roleContractSha256']})
    dates = sorted({x['asOf'] for x in entries})
    title = 'Dated responsibility snapshot' if len(entries)==1 else 'Dated responsibility snapshot bundle'
    title += ' — '+', '.join(dates)
    if len(title)>255:
        title='Dated responsibility snapshot bundle — '+str(len(entries))+' runs; see description'
    return {'Title':title, '_ExtendedDescription':json.dumps({
        'artifactKind':'dated_responsibility_projection', 'liveResponsibility':False,
        'runs':entries, 'refreshMode':'on_demand',
        'interpretation':'Stored snapshots, not live ownership or clinical authority'},sort_keys=True),
        'PPGCaptureSHA256':hashlib.sha256(bundle_bytes).hexdigest()}


def decode_description(value):
    """Decode the observed generic Description property once; other fields stay exact."""
    if not isinstance(value,str):
        raise ValueError('Description must be selected explicitly')
    return json.loads(html.unescape(value))
