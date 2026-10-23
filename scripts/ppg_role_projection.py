"""Read-only, dated responsibility projection from exported native role records.

Input is a private JSON export, never a request to assign people or change access.
Historical decisions are passed through unchanged. No native write route exists.
"""
import argparse
import copy
import json
from datetime import datetime
from pathlib import Path

from scripts.ppg_review_intelligence import resolve_role, role_date


def index(rows, key):
    result = {}
    for row in rows:
        value = row.get(key)
        if not value or value in result:
            raise ValueError('Missing or duplicate ' + key)
        result[value] = row
    return result


def active(row, day):
    start = role_date(row['effectiveFrom'])
    until = row.get('effectiveUntil')
    end = None if until is None or until == '' else role_date(until)
    if end and end <= start:
        raise ValueError('Invalid effective interval')
    return start <= day and (end is None or day < end)


def project(bundle, on_date):
    day = role_date(on_date)
    roles = index(bundle['roles'], 'roleId')
    appointments = list(index(bundle['appointments'], 'appointmentId').values())
    assignments = index(bundle['assignments'], 'assignmentId')
    decisions = copy.deepcopy(bundle.get('historicalDecisions', []))
    responsibility_types = set(json.loads(Path('config/review-intelligence/roles-v1.json').read_text())['responsibilityTypes'])
    for row in appointments:
        if row['roleId'] not in roles:
            raise ValueError('Unknown appointment role')
        if row.get('appointmentKind') not in {'substantive', 'acting', 'delegated', 'vacant'}:
            raise ValueError('Unknown appointment kind')
        if row.get('appointmentKind') == 'vacant' and row.get('holderId'):
            raise ValueError('Vacancy cannot name a holder')
        if row.get('appointmentKind') == 'delegated' and (
                not row.get('delegationScope') or not row.get('authorityEvidence')):
            raise ValueError('Delegation needs scope and authority evidence')
        active(row, day)
    validate_handovers(bundle.get('handovers', []), roles, appointments)
    result = []
    for row in assignments.values():
        if row['roleId'] not in roles or row['responsibilityType'] not in responsibility_types:
            raise ValueError('Unknown assignment role or responsibility')
        if not row.get('documentUID'):
            raise ValueError('Missing document identity')
        if row['status'] not in {'proposed', 'accepted', 'declined', 'ended', 'superseded'}:
            raise ValueError('Unknown assignment status')
        if not active(row, day):
            continue
        resolution = resolve_role(appointments, row['roleId'], on_date)
        if row['status'] != 'accepted' or not row.get('evidenceRef'):
            resolution = dict(state='unconfirmed_assignment', holderId=None,
                              appointmentIds=[], grantsAccess=False)
        peers = [other for other in assignments.values()
                 if other['assignmentId'] != row['assignmentId']
                 and other['documentUID'] == row['documentUID']
                 and other['responsibilityType'] == row['responsibilityType']
                 and active(other, day)]
        # Multiple contributors can be valid; surface them without selecting a lead.
        # An ambiguous set has no selected appointment or delegation scope.
        selected = (next((a for a in appointments
                          if a['appointmentId'] == resolution['appointmentIds'][0]), None)
                    if len(resolution['appointmentIds']) == 1 else None)
        if selected and selected['appointmentKind'] == 'delegated':
            scope = selected['delegationScope']
            if not isinstance(scope, dict) or row['documentUID'] not in scope.get('documentUIDs', []) or row['responsibilityType'] not in scope.get('responsibilityTypes', []):
                resolution = dict(state='delegation_scope_unconfirmed', holderId=None,
                                  appointmentIds=resolution['appointmentIds'], grantsAccess=False)
        result.append({**copy.deepcopy(row), 'roleTitle': roles[row['roleId']]['title'],
                       'resolution': resolution,
                       'concurrentAssignmentIds': [p['assignmentId'] for p in peers],
                       'delegationScope': selected.get('delegationScope') if selected else None,
                       'grantsClinicalAuthority': False})
    return dict(schemaVersion=1, asOf=on_date, responsibilities=result,
                historicalDecisions=decisions, handovers=copy.deepcopy(bundle.get('handovers', [])), notificationsEnabled=False,
                sourceModified=False, accessModified=False)




def validate_handovers(handovers, roles, appointments):
    appointments = index(appointments, 'appointmentId')
    for row in index(handovers, 'handoverId').values():
        if row['fromRoleId'] not in roles or row['toRoleId'] not in roles:
            raise ValueError('Unknown handover role')
        role_date(row['effectiveFrom'])
        if not isinstance(row.get('documentUIDs'), list) or not row['documentUIDs'] or any(not isinstance(uid, str) or not uid for uid in row['documentUIDs']):
            raise ValueError('Handover needs explicit document scope')
        if row['kind'] == 'succession':
            if row['fromRoleId'] != row['toRoleId']:
                raise ValueError('Succession cannot transfer portfolio roles')
            for key in ('fromAppointmentId', 'toAppointmentId'):
                appointment = appointments.get(row.get(key))
                if not appointment or appointment['roleId'] != row['fromRoleId']:
                    raise ValueError('Succession appointment mismatch')
            old = appointments[row['fromAppointmentId']]
            new = appointments[row['toAppointmentId']]
            if old['appointmentId'] == new['appointmentId'] or old.get('effectiveUntil') != row['effectiveFrom'] or new['effectiveFrom'] != row['effectiveFrom']:
                raise ValueError('Succession dates or appointments do not meet')
        elif row['kind'] == 'portfolio_transfer':
            if row['fromRoleId'] == row['toRoleId']:
                raise ValueError('Portfolio transfer needs different roles')
        else:
            raise ValueError('Unknown handover kind')
        if row['status'] not in {'proposed', 'accepted', 'declined', 'ended', 'superseded'}:
            raise ValueError('Unknown handover status')
        if row['status'] == 'accepted':
            if not all(row.get(k) for k in ('acceptedBy', 'acceptedAt', 'evidenceRef')):
                raise ValueError('Accepted handover needs actor, time and evidence')
            if datetime.fromisoformat(row['acceptedAt']).tzinfo is None:
                raise ValueError('Acceptance time needs timezone')


def from_native(native):
    """Map explicit exported fields; never silently accept a partial response."""
    def rows(name):
        page = native[name]
        if any(page.get(k) for k in ('odata.nextLink', '@odata.nextLink', '__next', 'nextLink')):
            raise ValueError('Incomplete native export')
        return page['value']
    roles = [dict(roleId=r['RoleKey'], title=r['Title'], scope=r.get('Scope'), holderKind=r['HolderKind'])
             for r in rows('roles')]
    assignments = [dict(assignmentId=r['AssignmentKey'], documentUID=r['DocumentUID'], roleId=r['RoleKey'],
                        responsibilityType=r['ResponsibilityType'], effectiveFrom=r['EffectiveFrom'],
                        effectiveUntil=r.get('EffectiveUntil'), status=r['ReviewState'].lower(), evidenceRef=r.get('EvidenceRef'))
                   for r in rows('assignments')]
    appointments = []
    for r in rows('appointments'):
        scope = r.get('DelegationScope')
        if scope:
            try:
                scope = json.loads(scope)
            except (ValueError, TypeError):
                pass  # Unstructured scope remains explicitly unconfirmed by project().
        appointments.append(dict(appointmentId=r['AppointmentKey'], roleId=r['RoleKey'], holderId=r.get('HolderKey'),
                                 appointmentKind=r['AppointmentKind'], effectiveFrom=r['EffectiveFrom'],
                                 effectiveUntil=r.get('EffectiveUntil'), status=r['ReviewState'].lower(),
                                 evidenceRef=r.get('EvidenceRef'), delegationScope=scope,
                                 authorityEvidence=r.get('AuthorityEvidence')))
    handovers = []
    if 'handovers' in native:
        for r in rows('handovers'):
            handovers.append(dict(handoverId=r['HandoverKey'], kind=r['HandoverKind'],
                                  fromRoleId=r['FromRoleKey'], toRoleId=r['ToRoleKey'],
                                  fromAppointmentId=r.get('FromAppointmentKey'), toAppointmentId=r.get('ToAppointmentKey'),
                                  documentUIDs=json.loads(r['DocumentUIDs']), effectiveFrom=r['EffectiveFrom'],
                                  status=r['ReviewState'].lower(), acceptedBy=r.get('AcceptedBy'), acceptedAt=r.get('AcceptedAt'),
                                  evidenceRef=r.get('EvidenceRef')))
    return dict(roles=roles, assignments=assignments, appointments=appointments, handovers=handovers,
                historicalDecisions=copy.deepcopy(native.get('historicalDecisions', [])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    if isinstance(data.get('roles'), dict):
        data = from_native(data)
    result = project(data, args.as_of)
    with args.output.open('x') as target:
        json.dump(result, target, indent=2)
        target.write('\n')
    print(json.dumps({'responsibilityCount': len(result['responsibilities'])}))


if __name__ == '__main__':
    main()
