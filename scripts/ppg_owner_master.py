"""Prepare one owner-operated controlled-master review; no native writes or sends.

CLI outputs are private, create-only evidence. Review and acceptance are distinct;
a decision records supplied user evidence, never manufactures approval or issuance.
"""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

RUBRIC = Path(__file__).resolve().parents[1] / 'config/lifecycle-owner-review-rubric-v1.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def required_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('missing_' + name)
    return value


def sha(value, name):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError('invalid_' + name)
    return value


def planning_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('iso_calendar_date_required')
    return date.fromisoformat(value)


def prepare(job, source, candidate):
    """Pin a new proposed edition without changing the source or prior editions."""
    for key in ('documentUID', 'occurrenceUID', 'requestUID', 'proposedEdition', 'changeSummary'):
        required_text(job.get(key), key)
    if job.get('scope') != 'owner-approved-workbench':
        raise ValueError('workbench_scope_required')
    if job.get('contentOwnership') != 'project-owned':
        raise ValueError('project_owned_content_required')
    pin = job['source']
    for key in ('reference', 'edition', 'nativeId', 'nativeVersion', 'etag'):
        required_text(pin.get(key), 'source_' + key)
    if pin['etag'] == '*':
        raise ValueError('exact_source_token_required')
    if sha(pin.get('sha256'), 'source_hash') != digest(source):
        raise ValueError('source_bytes_changed')
    if job['proposedEdition'] == pin['edition']:
        raise ValueError('distinct_proposed_edition_required')
    if not source or not candidate:
        raise ValueError('empty_content')
    if job.get('planningReviewDate') is not None:
        planning_date(job['planningReviewDate'])
    rubric = json.loads(RUBRIC.read_text())
    body = {
        'schemaVersion': 1, 'kind': 'owner-master-preparation',
        **{key: job[key] for key in ('documentUID', 'occurrenceUID', 'requestUID',
                                   'proposedEdition', 'changeSummary', 'scope', 'contentOwnership',
                                   'planningReviewDate')},
        'source': pin, 'candidateSHA256': digest(candidate),
        'supersedes': {'documentUID': job['documentUID'], 'edition': pin['edition'],
                       'sourceSHA256': pin['sha256'], 'proposedOnly': True},
        'rubricId': rubric['rubricId'], 'rubricSHA256': digest(canonical(rubric)),
        'requiredReviewAreas': rubric['areas'], 'state': 'Awaiting agent review',
        'userAcceptance': None, 'effectiveDate': None, 'officialCurrent': False,
        'clinicalEffectivenessEstablished': False, 'nativeWritesPerformed': False,
        'notificationsAllowed': False, 'sourcePreserved': True,
    }
    return {**body, 'preparationSHA256': digest(canonical(body))}



def consume_request(request, job, source, candidate):
    """Bind a retained native queue request; changed purpose/date cannot replay."""
    if request.get('kind') != 'owner-guide-preparation-request':
        raise ValueError('native_request_kind')
    if not re.fullmatch(r'GUIDE-[A-Za-z0-9-]{1,90}', request.get('requestUID', '')):
        raise ValueError('safe_request_reference_required')
    for key in ('documentUID', 'occurrenceUID', 'requestUID', 'proposedEdition', 'scope', 'source'):
        if request.get(key) != job.get(key):
            raise ValueError('native_request_binding_' + key)
    if request.get('candidateSHA256') != digest(candidate):
        raise ValueError('native_request_candidate_changed')
    if ((request.get('planningReviewDate') or None) != job.get('planningReviewDate')
            or request.get('nativeDataWrites') != 0
            or request.get('approvalRecorded') is not False
            or request.get('issued') is not False
            or request.get('notificationsAllowed') is not False
            or request.get('agentSessionRequired') is not True):
        raise ValueError('native_request_scope_changed')
    required_text(request.get('purpose'), 'request_purpose')
    body = prepare(job, source, candidate)
    del body['preparationSHA256']
    body.update(nativeRequestSHA256=digest(canonical(request)), purpose=request['purpose'])
    return {**body, 'preparationSHA256': digest(canonical(body))}


def verify_preparation(manifest, candidate):
    body = {k: v for k, v in manifest.items() if k != 'preparationSHA256'}
    if digest(canonical(body)) != manifest.get('preparationSHA256'):
        raise ValueError('preparation_tampered')
    if digest(candidate) != manifest['candidateSHA256']:
        raise ValueError('candidate_revision_changed')
    rubric = json.loads(RUBRIC.read_text())
    if manifest['rubricSHA256'] != digest(canonical(rubric)):
        raise ValueError('rubric_changed')
    return rubric


def review(manifest, candidate, findings):
    rubric = verify_preparation(manifest, candidate)
    if findings.get('preparationSHA256') != manifest['preparationSHA256']:
        raise ValueError('review_wrong_preparation')
    rows = findings['checks']
    if not isinstance(rows, list) or sorted(r.get('area', '') for r in rows) != sorted(rubric['areas']):
        raise ValueError('complete_unique_review_areas_required')
    blockers = []
    for row in rows:
        for field, choices in [('response', 'responses'), ('severity', 'severities'),
                               ('disposition', 'dispositions')]:
            if row.get(field) not in rubric[choices]:
                raise ValueError('invalid_review_' + field)
        for key in ('rationale', 'uncertainty'):
            required_text(row.get(key), key)
        if not isinstance(row.get('evidence'), list) or not row['evidence']:
            raise ValueError('review_evidence_required')
        for evidence in row['evidence']:
            required_text(evidence.get('reference'), 'evidence_reference')
            required_text(evidence.get('locator'), 'evidence_locator')
            sha(evidence.get('sha256'), 'evidence_hash')
        if (row['response'] == 'needs-evidence' or row['disposition'] == 'open'
                or row['severity'] in ('critical', 'high')
                or (row['response'] == 'supported-finding' and row['disposition'] == 'no-action')):
            blockers.append(row['area'])
    body = {'kind': 'owner-master-agent-review', 'preparation': manifest,
            'checks': rows, 'blockers': blockers,
            'state': 'Needs evidence' if blockers else 'Awaiting user decision',
            'userAcceptance': None, 'officialCurrent': False}
    return {**body, 'reviewSHA256': digest(canonical(body))}


def record_decision(report, candidate, decision):
    body = {k: v for k, v in report.items() if k != 'reviewSHA256'}
    if digest(canonical(body)) != report.get('reviewSHA256'):
        raise ValueError('review_tampered')
    manifest = report['preparation']
    verify_preparation(manifest, candidate)
    if decision.get('reviewSHA256') != report['reviewSHA256']:
        raise ValueError('decision_wrong_review')
    if decision.get('candidateSHA256') != manifest['candidateSHA256']:
        raise ValueError('decision_wrong_revision')
    if decision.get('scope') != 'owner-approved-workbench':
        raise ValueError('decision_scope_not_supported')
    action = decision.get('decision')
    if action not in ('accept', 'revise', 'return'):
        raise ValueError('invalid_user_decision')
    for key in ('userInstructionReference', 'recordedAt', 'rationale'):
        required_text(decision.get(key), key)
    recorded = datetime.fromisoformat(decision['recordedAt'])
    if recorded.tzinfo is None or recorded.utcoffset() != timezone.utc.utcoffset(recorded):
        raise ValueError('utc_recorded_time_required')
    if action == 'accept' and report['blockers']:
        raise ValueError('unresolved_review_blockers')
    if action == 'accept':
        planning_date(decision['effectiveDate'])
    # This is a record of an externally supplied user decision. Issuance needs its
    # own exact native destination/content/authority proof; no send or status write.
    body = {'kind': 'owner-master-user-decision', 'reviewSHA256': report['reviewSHA256'],
            'documentUID': manifest['documentUID'], 'occurrenceUID': manifest['occurrenceUID'],
            'candidateSHA256': manifest['candidateSHA256'], 'decision': decision,
            'state': 'Accepted for workbench scope' if action == 'accept' else 'Returned for revision',
            'issued': False, 'officialCurrent': False, 'notificationsAllowed': False}
    return {**body, 'decisionSHA256': digest(canonical(body))}


def write_once(path, value):
    """Same bytes replay safely; competing or changed receipts are never replaced."""
    raw = canonical(value) + b'\n'
    try:
        with open(path, 'xb', opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if Path(path).read_bytes() != raw:
            raise ValueError('existing_receipt_differs') from None
        return 'replay-preserved'
    return 'created'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'consume-request', 'review', 'record-decision'])
    parser.add_argument('--input', required=True, help='private job, preparation or review JSON')
    parser.add_argument('--source', help='pinned original bytes; required for prepare')
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--record', help='private findings or actual user decision JSON')
    parser.add_argument('--output', required=True, help='private create-only JSON receipt')
    args = parser.parse_args()
    item = json.loads(Path(args.input).read_text())
    candidate = Path(args.candidate).read_bytes()
    if args.operation in ('prepare', 'consume-request'):
        if not args.source:
            parser.error('--source is required for preparation')
        source = Path(args.source).read_bytes()
        if args.operation == 'consume-request':
            if not args.record:
                parser.error('--record is required for consume-request')
            native_request = json.loads(Path(args.record).read_text())
            result = consume_request(native_request, item, source, candidate)
        else:
            result = prepare(item, source, candidate)
    else:
        if not args.record:
            parser.error('--record is required for review/record-decision')
        record = json.loads(Path(args.record).read_text())
        result = (review(item, candidate, record) if args.operation == 'review'
                  else record_decision(item, candidate, record))
    print(json.dumps({'receipt': write_once(args.output, result), 'state': result['state']}))


if __name__ == '__main__':
    main()
