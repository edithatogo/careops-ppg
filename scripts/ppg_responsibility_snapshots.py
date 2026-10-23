"""Prepare append-only, dated responsibility rows; never assign people or grant access."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.ppg_role_projection import from_native, project


def snapshots(source_bytes, as_of):
    native = json.loads(source_bytes)
    if not all(k in native for k in ['roles', 'assignments', 'appointments', 'handovers']):
        raise ValueError('Complete four-register export required')
    bundle = from_native(native)
    projection = project(bundle, as_of)
    sha = hashlib.sha256(source_bytes).hexdigest()
    implementation_hashes = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in [
        'scripts/ppg_role_projection.py', 'scripts/ppg_review_intelligence.py',
        'scripts/ppg_responsibility_snapshots.py']}
    logic_sha = hashlib.sha256(json.dumps(implementation_hashes, sort_keys=True).encode()).hexdigest()
    contract_sha = hashlib.sha256(Path('config/review-intelligence/roles-v1.json').read_bytes()).hexdigest()
    run_key = hashlib.sha256(('\n'.join([sha, as_of, logic_sha, contract_sha])).encode()).hexdigest()
    manifest = dict(sourceSha256=sha, asOf=as_of, projectionLogicSha256=logic_sha,
                    roleContractSha256=contract_sha, runKey=run_key,
                    implementationHashes=implementation_hashes,
                    historicalDecisions=projection['historicalDecisions'],
                    handovers=projection['handovers'], sourceModified=False,
                    grantsAccess=False, grantsClinicalAuthority=False,
                    interpretation='Dated derived snapshot; not a live appointment or clinical authority')
    records = []
    for row in projection['responsibilities']:
        key = hashlib.sha256((run_key+'\n'+row['assignmentId']).encode()).hexdigest()
        records.append({'list': 'PPG Responsibility Snapshots', 'key': 'SnapshotKey', 'record': {
            'Title': (as_of+' — '+row['roleTitle'])[:255], 'SnapshotKey': key, 'RunKey': run_key,
            'AsOfDate': as_of, 'SourceSHA256': sha, 'DocumentUID': row['documentUID'],
            'AssignmentKey': row['assignmentId'], 'RoleKey': row['roleId'],
            'ResponsibilityType': row['responsibilityType'],
            'HolderKey': row['resolution']['holderId'], 'ResolutionState': row['resolution']['state'],
            'Projection': json.dumps(row, ensure_ascii=False, sort_keys=True),
            'SourceManifest': json.dumps(manifest, ensure_ascii=False, sort_keys=True)}})
    return dict(manifest=manifest, projection=projection, records=records)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = snapshots(args.input.read_bytes(), args.as_of)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({'snapshotRows': len(result['records']), 'runKey': result['manifest']['runKey'],
                      'nativeWrites': 0}))
