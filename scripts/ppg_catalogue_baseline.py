"""Prepare a create-only installation baseline from retained accepted identity evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

FIELDS = ('Title DocumentUID sourceDocumentId sourceTitle sourceCustodian sourceNextReviewDateRaw '
          'sourceNextReviewMonth sourceStatus sourceRisk sourceSnapshotRef sourceAsOfUtc '
          'sourceRowNumber rawSourceRecordRef sourceIdentityDecisionRef').split()


def prepare(rows, checkpoint, candidate):
    if checkpoint.get('status') != 'completed' or checkpoint.get('sourceSha256') != candidate.get('sourceSha256'):
        raise ValueError('Accepted checkpoint and candidate must name the same source bytes')
    ledger = checkpoint.get('identityLedger', {})
    aliases = ledger.get('aliases', [])
    uids = [str(UUID(a['documentUID'])) for a in aliases]
    actual = [str(UUID(r['DocumentUID'])) for r in rows]
    if not uids or len(set(uids)) != len(uids) or len(set(actual)) != len(actual) or set(uids) != set(actual):
        raise ValueError('Exact unique catalogue and ledger identities required')
    operations = candidate.get('operations', [])
    active = [str(UUID(o['DocumentUID'])) for o in operations]
    absent = checkpoint.get('retainedAbsentUIDs', [])
    if len(set(active)) != len(active) or set(active) & set(absent) or set(active) | set(absent) != set(uids):
        raise ValueError('Every identity must be active or explicitly retained absent')
    if checkpoint.get('readbackCount') != len(active) or checkpoint.get('catalogueReadbackCount') != len(rows):
        raise ValueError('Checkpoint counts differ from selected evidence')
    by_uid = {r['DocumentUID']: r for r in rows}
    for op in operations:
        for key, value in op['fields'].items():
            if key not in FIELDS:
                raise ValueError('Unexpected source-owned field')
            # Preserve the qualified SharePoint blank and numeric-note codecs.
            from scripts.ppg_source_sync import source_equal
            if not source_equal(key, by_uid[op['DocumentUID']].get(key), value):
                raise ValueError('Catalogue differs from accepted candidate: ' + key)
    payloads = [{k: r.get(k) for k in FIELDS} for r in rows]
    return {'schemaVersion': 1, 'mode': 'create-only-retained-baseline', 'rows': payloads,
            'identityLedger': ledger, 'checkpoint': checkpoint, 'activeCount': len(active),
            'retainedAbsentCount': len(absent), 'baselineAsOf': checkpoint['asOfUtc'],
            'currentSourceReconciled': False, 'clinicalReviewOrApproval': False,
            'absenceAcknowledgementsExtended': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('rows', 'checkpoint', 'candidate', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    if '.local' not in a.output.resolve().parts:
        p.error('Native baseline outputs must stay private under .local')
    data = {k: getattr(a, k).read_bytes() for k in ('rows', 'checkpoint', 'candidate')}
    result = prepare(*(json.loads(data[k]) for k in ('rows', 'checkpoint', 'candidate')))
    result['inputHashes'] = {k: hashlib.sha256(v).hexdigest() for k, v in data.items()}
    with a.output.open('x') as f:
        json.dump(result, f, indent=2)
    a.output.chmod(0o600)


if __name__ == '__main__':
    main()
