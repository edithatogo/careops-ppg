"""Audit a recorded manual portfolio transfer; never apply assignments or permissions."""
import argparse
import copy
import hashlib
import json
from datetime import timedelta
from pathlib import Path

from scripts.ppg_review_intelligence import role_date
from scripts.ppg_role_projection import active, from_native, index, project


def audit_transfer(bundle, handover_id, assignment_pairs):
    handovers = index(bundle.get('handovers', []), 'handoverId')
    handover = handovers.get(handover_id)
    if not handover or handover['kind'] != 'portfolio_transfer' or handover['status'] != 'accepted':
        raise ValueError('Recorded accepted portfolio transfer required')
    day = role_date(handover['effectiveFrom'])
    if day.year == 1 and day.month == 1 and day.day == 1:
        raise ValueError('Transfer needs a preceding date')
    before_day = day-timedelta(days=1)
    before = project(bundle, before_day.isoformat())
    after = project(bundle, day.isoformat())  # Validates all role/handover references.
    scope = handover['documentUIDs']
    if len(scope) != len(set(scope)):
        raise ValueError('Duplicate document scope')
    for other in handovers.values():
        if (other['handoverId'] != handover_id and other['kind'] == 'portfolio_transfer'
                and other['status'] == 'accepted' and other['fromRoleId'] == handover['fromRoleId']
                and other['effectiveFrom'] == handover['effectiveFrom']
                and set(other['documentUIDs']) & set(scope)):
            raise ValueError('Ambiguous accepted portfolio transfers')
    assignments = index(bundle['assignments'], 'assignmentId')
    if not isinstance(assignment_pairs, list) or not assignment_pairs:
        raise ValueError('Explicit assignment pairs required')
    used, dimensions, checked = set(), set(), []
    for pair in assignment_pairs:
        if not isinstance(pair, dict) or set(pair) != {'fromAssignmentId', 'toAssignmentId'}:
            raise ValueError('Assignment pair needs exact source and destination keys')
        old_id, new_id = pair['fromAssignmentId'], pair['toAssignmentId']
        if any(not isinstance(k, str) or not k or k in used for k in (old_id, new_id)) or old_id == new_id:
            raise ValueError('Missing, duplicate or reused assignment identity')
        used.update((old_id, new_id))
        old, new = assignments.get(old_id), assignments.get(new_id)
        if not old or not new:
            raise ValueError('Unknown assignment identity')
        if (old['roleId'] != handover['fromRoleId'] or new['roleId'] != handover['toRoleId']
                or old['documentUID'] != new['documentUID'] or old['documentUID'] not in scope
                or old['responsibilityType'] != new['responsibilityType']):
            raise ValueError('Assignment roles, document or responsibility differ from transfer')
        if any(a['status'] != 'accepted' or not a.get('evidenceRef') for a in (old, new)):
            raise ValueError('Both assignments need recorded acceptance and evidence')
        if (old.get('effectiveUntil') != day.isoformat() or new['effectiveFrom'] != day.isoformat()
                or not active(old, before_day) or not active(new, day)):
            raise ValueError('Assignment intervals do not meet at transfer date')
        dimension = (old['documentUID'], old['responsibilityType'])
        if dimension in dimensions:
            raise ValueError('Ambiguous source responsibility')
        dimensions.add(dimension)
        for other in assignments.values():
            if (other['assignmentId'] != new_id and other['roleId'] == handover['toRoleId']
                    and (other['documentUID'], other['responsibilityType']) == dimension
                    and active(other, day)):
                raise ValueError('Overlapping destination assignment')
        checked.append(copy.deepcopy(pair))
    required = {a['assignmentId'] for a in assignments.values()
                if a['roleId'] == handover['fromRoleId'] and a['documentUID'] in scope
                and active(a, before_day)}
    if required != {p['fromAssignmentId'] for p in checked} or {d[0] for d in dimensions} != set(scope):
        raise ValueError('Incomplete scoped portfolio assignment accounting')
    return dict(schemaVersion=1, kind='manual_portfolio_transfer_audit',
                handover=copy.deepcopy(handover), assignmentPairs=checked,
                before=before, after=after, historicalDecisions=copy.deepcopy(bundle.get('historicalDecisions', [])),
                recordedAcceptanceOnly=True, authorityVerified=False,
                sourceModified=False, accessModified=False, nativeWrites=0, notificationsEnabled=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--handover', required=True)
    parser.add_argument('--pairs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source_bytes = args.input.read_bytes()
    pair_bytes = args.pairs.read_bytes()
    bundle = json.loads(source_bytes)
    if isinstance(bundle.get('roles'), dict):
        bundle = from_native(bundle)
    result = audit_transfer(bundle, args.handover, json.loads(pair_bytes))
    result.update(sourceSHA256=hashlib.sha256(source_bytes).hexdigest(),
                  assignmentPairsSHA256=hashlib.sha256(pair_bytes).hexdigest(),
                  implementationHashes={name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                      for name in ['scripts/ppg_portfolio_transfer.py',
                                   'scripts/ppg_role_projection.py', 'scripts/ppg_review_intelligence.py']})
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'assignmentPairsVerified': len(result['assignmentPairs']), 'nativeWrites': 0}))
