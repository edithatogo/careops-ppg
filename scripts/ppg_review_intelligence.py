"""Read-only review contracts: no assignments, clinical decisions or native writes."""
from datetime import date
import re

HIERARCHICAL = {'governed_by', 'local_variation_of', 'supersedes', 'implements'}
RELATIONS = HIERARCHICAL | {'supplements', 'references', 'proposed_consolidation_with'}


def validate_relationships(rows):
    """Check accepted hierarchy across relation types; proposals do not change it."""
    graph = {}
    seen = set()
    for row in rows:
        key = row['relationshipId']
        if key in seen:
            raise ValueError('Duplicate relationship identity')
        seen.add(key)
        if row['type'] not in RELATIONS:
            raise ValueError('Unknown relationship type')
        if row['status'] not in {'proposed', 'accepted', 'rejected', 'superseded'}:
            raise ValueError('Unknown relationship status')
        if row['fromDocumentUID'] == row['toDocumentUID']:
            raise ValueError('Self relationship')
        if row['status'] == 'accepted' and row['type'] in HIERARCHICAL:
            graph.setdefault(row['fromDocumentUID'], set()).add(row['toDocumentUID'])
    def visit(node, trail, complete):
        if node in trail:
            raise ValueError('Circular accepted hierarchy')
        if node in complete:
            return
        for child in graph.get(node, ()):
            visit(child, trail | {node}, complete)
        complete.add(node)
    complete = set()
    for node in graph:
        visit(node, set(), complete)
    return True


def role_date(value):
    """Require the register's unambiguous Gregorian YYYY-MM-DD convention."""
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('Role date must use YYYY-MM-DD')
    return date.fromisoformat(value)


def resolve_role(appointments, role_id, on_date):
    """Resolve a dated appointment, never choose around overlap or adverse history.

    Intervals are [effectiveFrom, effectiveUntil). Acting appointments need explicit
    nonoverlapping dates, not implicit precedence over substantive appointments.
    A vacancy requires an explicit accepted vacancy appointment; missing data is unconfirmed.
    """
    day = role_date(on_date)
    matches = []
    seen = set()
    for item in appointments:
        if item['appointmentId'] in seen:
            raise ValueError('Duplicate appointment identity')
        seen.add(item['appointmentId'])
        start = role_date(item['effectiveFrom'])
        until = item.get('effectiveUntil')
        end = None if until is None or until == '' else role_date(until)
        if end and end <= start:
            raise ValueError('Invalid appointment interval')
        if item['roleId'] == role_id and start <= day and (end is None or day < end):
            matches.append(item)
    if len(matches) != 1:
        return {'state': 'unconfirmed' if not matches else 'ambiguous', 'holderId': None,
                'appointmentIds': [m['appointmentId'] for m in matches], 'grantsAccess': False}
    item = matches[0]
    if item.get('status') != 'accepted' or not item.get('evidenceRef'):
        return {'state': 'unconfirmed', 'holderId': None,
                'appointmentIds': [item['appointmentId']], 'grantsAccess': False}
    if item.get('appointmentKind') == 'vacant' and item.get('holderId'):
        raise ValueError('Vacancy cannot name a holder')
    state = ('vacant' if item.get('appointmentKind') == 'vacant' else
             'resolved' if item.get('holderId') else 'unconfirmed')
    return {'state': state,
            'holderId': item.get('holderId'), 'appointmentIds': [item['appointmentId']],
            'grantsAccess': False}


def classify_source_standard(raw, framework):
    """Preserve the source assertion; even an exact code is only a candidate."""
    value = str(raw).strip() if raw is not None else ''
    codes = {r['code']: r['requirementId'] for r in framework['requirements']}
    return {'sourceAssertion': raw, 'frameworkEditionId': framework['frameworkEditionId'],
            'candidateRequirementId': codes.get(value),
            'status': 'proposed' if value in codes else 'unresolved',
            'establishesCompliance': False}


def carry_annotations(annotations, document_uid, current_version, section_ids):
    """Return unresolved suggestions with reconciliation flags; never edit originals."""
    states = {'received', 'triaged', 'deferred', 'accepted', 'rejected', 'incorporated', 'superseded'}
    result = []
    seen = set()
    for item in annotations:
        if item['annotationId'] in seen:
            raise ValueError('Duplicate annotation identity')
        seen.add(item['annotationId'])
        if item['status'] not in states:
            raise ValueError('Unknown annotation status')
        if item['documentUID'] != document_uid or item['status'] in {'rejected', 'incorporated', 'superseded'}:
            continue
        result.append({**item, 'requiresReconciliation':
                       item['documentVersion'] != current_version or
                       bool(item.get('sectionId') and item['sectionId'] not in section_ids)})
    return result


def validate_review_run(run):
    """Require provenance for findings, including inferences; unknowns cannot decide."""
    required = {'runId', 'documentUID', 'documentVersion', 'documentSha256',
                'templateVersion', 'templateSha256', 'criteriaVersion', 'promptId',
                'promptVersion', 'promptSha256', 'evidenceSnapshots', 'coverageManifestRef',
                'runtimeIdentity', 'startedAt', 'completedAt', 'status', 'findings',
                'limitations', 'humanDisposition'}
    if required - run.keys():
        raise ValueError('Missing review-run fields')
    if run['status'] not in {'prepared', 'running', 'completed', 'failed', 'held_missing_evidence'}:
        raise ValueError('Unknown run status')
    if run['status'] == 'completed' and not run['completedAt']:
        raise ValueError('Completed run requires completion time')
    for field in ['documentSha256', 'templateSha256', 'promptSha256']:
        value = run[field]
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Invalid bound content hash')
    runtime = run['runtimeIdentity']
    if not {'executionMode', 'provider', 'model', 'modelVersion', 'versionAvailability'} <= runtime.keys():
        raise ValueError('Missing runtime identity or explicit availability')
    evidence = {}
    for item in run['evidenceSnapshots']:
        key = item['sourceId']
        if key in evidence:
            raise ValueError('Ambiguous source snapshot')
        evidence[key] = item
    seen = set()
    for finding in run['findings']:
        if finding['findingId'] in seen:
            raise ValueError('Duplicate finding identity')
        seen.add(finding['findingId'])
        kind = finding['claimType']
        if kind not in {'evidence', 'inference', 'unknown'}:
            raise ValueError('Unknown claim type')
        if kind != 'unknown' and not finding['sourceCitations']:
            raise ValueError('Finding lacks evidence')
        if kind == 'unknown' and finding['suggestedAction'] not in {None, 'seek_further_evidence'}:
            raise ValueError('Unknown cannot support a disposition')
        for cite in finding['sourceCitations']:
            source = evidence.get(cite['sourceId'])
            if not source or not cite.get('locator') or any(
                    cite.get(k) != source.get(k) for k in ['sourceVersion', 'sourceSha256']):
                raise ValueError('Citation does not match bound source version/hash/locator')
    if any(run.get(k) is not False for k in ['policyApproved', 'publicationAuthorised', 'notificationsEnabled']):
        raise ValueError('Suggestion run must explicitly disclaim authority and sending')
    return True


def change_candidate(source_id, baseline, observed):
    """On-demand byte-change candidate; acquisition failure never advances baseline."""
    if observed.get('status') != 'captured' or not observed.get('sha256'):
        return {'sourceId': source_id, 'state': 'acquisition_exception',
                'advanceBaseline': False, 'notifyOwner': False}
    if baseline and baseline.get('sourceId') != source_id:
        raise ValueError('Baseline source identity mismatch')
    if observed.get('sourceId') != source_id:
        raise ValueError('Observed source identity mismatch')
    if baseline and baseline.get('sha256') == observed['sha256']:
        state = 'unchanged_bytes'
    else:
        state = 'new_baseline_candidate' if not baseline else 'changed_bytes_candidate'
    import hashlib
    fingerprint = hashlib.sha256((source_id + '\n' + (baseline or {}).get('sha256', '') +
                                  '\n' + observed['sha256']).encode()).hexdigest()
    return {'sourceId': source_id, 'state': state, 'fingerprint': fingerprint,
            'advanceBaseline': False, 'notifyOwner': False,
            'semanticChangeEstablished': False, 'applicabilityEstablished': False}
