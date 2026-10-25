"""Prepare one stopped URL-upload qualification graph; never deploy or run it."""
from __future__ import annotations

import argparse
import base64
import binascii
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import urlsplit
from uuid import UUID

API = '/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness'
SLOT = 'shared_onedriveforbusiness'
MAX_BYTES = 3 * 1024 * 1024  # Selected qualification envelope, not a provider limit.
POLL_COUNT = 12
ROOT = Path(__file__).resolve().parents[1]


def _literal(value, maximum=2048):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or value.startswith('@') or '@{' in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('bounded literal string required')
    return value


def _profile(profile):
    required = {'qualificationId', 'sourceKey', 'frameworkEditionId', 'sourceURL',
                'allowedOrigins', 'stagingRoot', 'ownershipEvidence',
                'connectionReference', 'expectedBytes', 'expectedSHA256'}
    if not isinstance(profile, dict) or set(profile) != required:
        raise ValueError('exact qualification profile required')
    value = copy.deepcopy(profile)
    try:
        uid = UUID(value['qualificationId'])
        if not uid.int or str(uid) != value['qualificationId']:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('canonical nonzero qualification UUID required') from exc
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,79}', _literal(value['sourceKey'], 80)):
        raise ValueError('literal source key required')
    _literal(value['frameworkEditionId'], 160)
    _literal(value['ownershipEvidence'])
    source = _literal(value['sourceURL'])
    if '\\' in source or any(c.isspace() for c in source):
        raise ValueError('literal HTTPS source URL required')
    try:
        u = urlsplit(source)
        if (u.scheme != 'https' or not u.hostname or u.username or u.password
                or u.port not in (None, 443) or u.fragment):
            raise ValueError()
    except ValueError as exc:
        raise ValueError('literal HTTPS source URL required') from exc
    allowed = value['allowedOrigins']
    if (not isinstance(allowed, list) or not 1 <= len(allowed) <= 5
            or any(not isinstance(origin, str) for origin in allowed)
            or len(allowed) != len(set(allowed))):
        raise ValueError('explicit origin allowlist required')
    for origin in allowed:
        _literal(origin)
        parsed = urlsplit(origin)
        if not parsed.hostname or origin != 'https://' + parsed.hostname.lower():
            raise ValueError('exact HTTPS origins required')
    if 'https://' + u.hostname.lower() not in allowed:
        raise ValueError('source outside origin allowlist')
    root = _literal(value['stagingRoot'], 500)
    path = PurePosixPath(root)
    if (not root.startswith('/') or root in ('/', '/Documents') or root.endswith('/')
            or '\\' in root or any(part in ('', '.', '..') for part in root.split('/')[1:])
            or str(path) != root or '%' in root or ':' in root):
        raise ValueError('explicit owned staging folder required')
    ref = value['connectionReference']
    if (not isinstance(ref, dict) or set(ref) != {'id', 'connectionName', 'source'}
            or ref['id'] != API or ref['source'] != 'Embedded'
            or not isinstance(ref['connectionName'], str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', ref['connectionName'])):
        raise ValueError('one exact existing embedded OneDrive reference required')
    if (type(value['expectedBytes']) is not int or not 1 <= value['expectedBytes'] <= MAX_BYTES
            or not isinstance(value['expectedSHA256'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', value['expectedSHA256'])):
        raise ValueError('bounded expected bytes and SHA256 required')
    value['stagingPath'] = root + '/' + str(uid) + '.captured'
    return value


def _after(name, *states):
    return {name: list(states or ('Succeeded',))}


def _set(name, value, after=None):
    return {'type': 'SetVariable', 'runAfter': after or {},
            'inputs': {'name': name, 'value': value}}


def _hold(code):
    return {'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed',
            'runError': {'code': code, 'message': 'Qualification held. Preserve staging and inspect the existing run before another submission.'}}}


def _if(expression, actions, otherwise, after=None):
    return {'type': 'If', 'runAfter': after or {}, 'expression': expression,
            'actions': actions, 'else': {'actions': otherwise}}


def build(profile):
    """Return a first-invocation experiment, not a resumable production producer."""
    p = _profile(profile)
    stage = p['stagingPath']

    def operation(operation_id, parameters, after=None):
        return {'type': 'OpenApiConnection', 'runAfter': after or {},
                'inputs': {'host': {'apiId': API, 'connectionName': SLOT,
                                    'operationId': operation_id},
                           'parameters': parameters, 'retryPolicy': {'type': 'none'}}}

    def metadata(after=None):
        return operation('GetFileMetadataByPath', {'path': stage}, after)

    ready = "@and(equals(body('Poll_metadata')?['Size']," + str(p['expectedBytes']) + "),equals(body('Poll_metadata')?['IsFolder'],false),not(empty(body('Poll_metadata')?['Id'])),not(empty(body('Poll_metadata')?['ETag'])))"
    polling = {
        'Wait_for_transfer': {'type': 'Wait', 'runAfter': {},
                              'inputs': {'interval': {'count': 5, 'unit': 'Second'}}},
        'Poll_metadata': metadata(_after('Wait_for_transfer')),
        'Count_poll': {'type': 'IncrementVariable',
                       'runAfter': _after('Poll_metadata', 'Succeeded', 'Failed', 'TimedOut'),
                       'inputs': {'name': 'acquisition_attempts', 'value': 1}},
        'Observe_poll': _if("@equals(actions('Poll_metadata')?['status'],'Succeeded')",
            {'Check_size': _if(ready, {'Mark_ready': _set('acquisition_ready', True)}, {})},
            {'Classify_failure': _if("@not(equals(outputs('Poll_metadata')?['statusCode'],404))",
                {'Mark_error': _set('acquisition_error', True)}, {})}, _after('Count_poll')),
    }
    create = {
        'Mark_upload_attempt': _set('acquisition_upload_attempted', True),
        'Upload_fixed_source': operation('CopyFile', {'source': p['sourceURL'],
            'destination': stage, 'overwrite': False}, _after('Mark_upload_attempt')),
        'Poll_for_completion': {'type': 'Until', 'runAfter': _after('Upload_fixed_source'),
            'expression': "@or(variables('acquisition_ready'),variables('acquisition_error'),greaterOrEquals(variables('acquisition_attempts')," + str(POLL_COUNT) + '))',
            'limit': {'count': POLL_COUNT, 'timeout': 'PT2M'}, 'actions': polling},
    }
    branch = {
        'Profile': {'type': 'Compose', 'runAfter': {}, 'inputs': {
            'qualificationId': p['qualificationId'], 'sourceKey': p['sourceKey'],
            'frameworkEditionId': p['frameworkEditionId'], 'sourceURL': p['sourceURL'],
            'stagingPath': stage, 'ownershipEvidence': p['ownershipEvidence'],
            'priorNativeRunsMustBeZero': True, 'singleInvocationQualificationOnly': True,
            'uncertainEffectRequiresReadback': True, 'nativeAcceptanceEstablished': False}},
        'Probe_stage': metadata(_after('Profile')),
        'Resolve_stage': _if("@equals(actions('Probe_stage')?['status'],'Succeeded')",
            {'Existing_stage': _set('acquisition_ready', True)},
            {'Allow_create': _if("@equals(outputs('Probe_stage')?['statusCode'],404)",
                                create, {'Hold_probe_failure': _hold('StageProbeFailed')})},
            _after('Probe_stage', 'Succeeded', 'Failed', 'TimedOut')),
    }
    stable = "@and(not(empty(body('Metadata_before')?['Id'])),not(empty(body('Metadata_before')?['ETag'])),equals(body('Metadata_before')?['Id'],body('Metadata_after')?['Id']),equals(body('Metadata_before')?['ETag'],body('Metadata_after')?['ETag']),equals(body('Metadata_before')?['Size']," + str(p['expectedBytes']) + "),equals(body('Metadata_after')?['Size']," + str(p['expectedBytes']) + "),equals(body('Metadata_before')?['IsFolder'],false),equals(body('Metadata_after')?['IsFolder'],false))"
    result = {'type': 'Compose', 'runAfter': {}, 'inputs': {
        'state': 'content-awaiting-independent-verification',
        'qualificationId': p['qualificationId'], 'sourceKey': p['sourceKey'],
        'frameworkEditionId': p['frameworkEditionId'], 'requestedSourceURL': p['sourceURL'],
        'finalSourceURL': None, 'redirectsVerified': False,
        'expectedRawSHA256': p['expectedSHA256'], 'actualRawSHA256': None,
        'byteIntegrityVerified': False, 'representationVerified': False,
        'metadataSnapshotStable': True, 'stagingPath': stage,
        'metadataBefore': "@body('Metadata_before')", 'metadataAfter': "@body('Metadata_after')",
        'content': "@body('Read_content')", 'uploadAttempted': "@variables('acquisition_upload_attempted')",
        'pollAttempts': "@variables('acquisition_attempts')", 'runName': "@workflow()?['run']?['name']",
        'catalogueWrites': 0, 'checkpointAdvanced': False, 'nativeAcquisitionQualified': False,
        'clinicalApplicabilityAccepted': False, 'notificationsEnabled': False}}
    pre_read = "@and(not(empty(body('Metadata_before')?['Id'])),not(empty(body('Metadata_before')?['ETag'])),equals(body('Metadata_before')?['Size']," + str(p['expectedBytes']) + "),equals(body('Metadata_before')?['IsFolder'],false))"
    content_readback = {
        'Read_content': operation('GetFileContentByPath', {'path': stage, 'inferContentType': False},
                                  {}),
        'Metadata_after': metadata(_after('Read_content')),
        'Require_stable_metadata': _if(stable, {'Report_candidate': result},
            {'Hold_changed_stage': _hold('StageChangedOrWrongSize')}, _after('Metadata_after')),
    }
    readback = {
        'Metadata_before': metadata(),
        'Require_expected_metadata': _if(pre_read, content_readback,
            {'Hold_before_content': _hold('StageMetadataNotExpected')}, _after('Metadata_before')),
    }
    branch['Require_ready'] = _if("@and(equals(actions('Resolve_stage')?['status'],'Succeeded'),variables('acquisition_ready'),not(variables('acquisition_error')))",
        readback, {'Hold_incomplete': _hold('TransferNotVerified')},
        _after('Resolve_stage', 'Succeeded', 'Failed', 'TimedOut'))
    actions = {}
    prior = None
    for name, kind, value in [('acquisition_attempts', 'integer', 0),
                              ('acquisition_ready', 'boolean', False),
                              ('acquisition_error', 'boolean', False),
                              ('acquisition_upload_attempted', 'boolean', False)]:
        action = 'Init_' + name
        actions[action] = {'type': 'InitializeVariable', 'runAfter': _after(prior) if prior else {},
                           'inputs': {'variables': [{'name': name, 'type': kind, 'value': value}]}}
        prior = action
    actions['Select_fixed_source'] = _if("@equals(triggerBody()?['sourceKey'],'" + p['sourceKey'] + "')",
        branch, {'Hold_unknown_source': _hold('SourceNotSelected')}, _after(prior))
    schema = {'type': 'object', 'additionalProperties': False,
              'properties': {'sourceKey': {'type': 'string', 'title': 'Source key',
                'enum': [p['sourceKey']], 'x-ms-dynamically-added': True, 'x-ms-content-hint': 'TEXT'}},
              'required': ['sourceKey']}
    definition = {'$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#',
                  'contentVersion': '1.0.0.0', 'parameters': {
                      '$authentication': {'type': 'SecureObject', 'defaultValue': {}},
                      '$connections': {'type': 'Object', 'defaultValue': {}}},
                  'triggers': {'manual': {'type': 'Request', 'kind': 'Button', 'inputs': {'schema': schema}}},
                  'actions': actions, 'outputs': {}}
    return {'properties': {'displayName': 'PPG | Fixed-source URL qualification ' + p['qualificationId'][:8],
            'state': 'Stopped', 'flowFailureAlertSubscribed': False,
            'definition': definition, 'connectionReferences': {SLOT: p['connectionReference']}}}


def verify_readback(profile, report, independent_bytes):
    """Verify supplied byte parity; never authenticate a run or advance a checkpoint."""
    p = _profile(profile)
    if not isinstance(report, dict):
        raise ValueError('qualification report object required')
    fixed = {'state': 'content-awaiting-independent-verification',
             'qualificationId': p['qualificationId'], 'sourceKey': p['sourceKey'],
             'frameworkEditionId': p['frameworkEditionId'],
             'requestedSourceURL': p['sourceURL'], 'stagingPath': p['stagingPath'],
             'expectedRawSHA256': p['expectedSHA256']}
    if any(report.get(k) != v for k, v in fixed.items()):
        raise ValueError('report differs from fixed qualification profile')
    # Preserve the producer boundary: expected values and booleans are not proof.
    for field in ('byteIntegrityVerified', 'representationVerified', 'redirectsVerified',
                  'checkpointAdvanced', 'nativeAcquisitionQualified',
                  'clinicalApplicabilityAccepted', 'notificationsEnabled'):
        if report.get(field) is not False:
            raise ValueError('unexpected producer acceptance assertion')
    if (report.get('actualRawSHA256', 'missing') is not None
            or report.get('finalSourceURL', 'missing') is not None
            or type(report.get('catalogueWrites')) is not int
            or report['catalogueWrites'] != 0
            or report.get('metadataSnapshotStable') is not True):
        raise ValueError('unexpected producer observation boundary')
    run = _literal(report.get('runName'), 256)
    if type(report.get('uploadAttempted')) is not bool:
        raise ValueError('upload attempt observation required')
    polls = report.get('pollAttempts')
    if type(polls) is not int or not 0 <= polls <= POLL_COUNT:
        raise ValueError('bounded polling observation required')
    before, after = report.get('metadataBefore'), report.get('metadataAfter')
    for metadata in (before, after):
        if (not isinstance(metadata, dict) or metadata.get('IsFolder') is not False
                or type(metadata.get('Size')) is not int
                or metadata['Size'] != p['expectedBytes']):
            raise ValueError('file metadata size or kind differs')
        _literal(metadata.get('Id'), 2048)
        _literal(metadata.get('ETag'), 2048)
    if any(before[k] != after[k] for k in ('Id', 'ETag', 'Size', 'IsFolder')):
        raise ValueError('file identity or version changed during readback')
    content = report.get('content')
    if (not isinstance(content, dict) or set(content) != {'$content-type', '$content'}
            or not isinstance(content['$content-type'], str)
            or not isinstance(content['$content'], str)):
        raise ValueError('explicit binary content envelope required')
    encoded = content['$content']
    expected_encoded = 4 * ((p['expectedBytes'] + 2) // 3)
    if len(encoded) != expected_encoded:
        raise ValueError('encoded content exceeds or differs from expected size')
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('invalid binary content encoding') from exc
    if base64.b64encode(decoded).decode('ascii') != encoded:
        raise ValueError('noncanonical binary content encoding')
    if (type(independent_bytes) is not bytes
            or len(independent_bytes) != p['expectedBytes']
            or len(decoded) != p['expectedBytes']
            or decoded != independent_bytes):
        raise ValueError('independent and connector bytes differ')
    digest = hashlib.sha256(independent_bytes).hexdigest()
    if digest != p['expectedSHA256']:
        raise ValueError('raw content differs from pinned source digest')
    return {'state': 'supplied-readback-byte-parity-verified',
            **{k: p[k] for k in ('qualificationId', 'sourceKey', 'frameworkEditionId',
                                 'sourceURL', 'stagingPath')},
            'runName': run, 'fileId': before['Id'], 'fileETag': before['ETag'],
            'bytes': len(independent_bytes), 'actualRawSHA256': digest,
            'independentByteParityVerified': True,
            'runProvenanceAuthenticated': False, 'representationVerified': False,
            'finalSourceURL': None, 'redirectsVerified': False,
            'nativeAcquisitionQualified': False, 'checkpointAdvanced': False,
            'catalogueWrites': 0, 'nativeWrites': 0}


def main():
    expected = (ROOT / '.python-version').read_text().strip()
    actual = '.'.join(map(str, sys.version_info[:3]))
    if (not expected.startswith('3.15.') or actual != expected
            or sys.version_info.releaselevel != 'final'
            or Path(sys.prefix).resolve() != (ROOT / '.venv').resolve()):
        raise SystemExit('Use the explicitly selected repo-local Python ' + expected)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--report', type=Path, help='Saved Report_candidate inputs, with binary envelope')
    parser.add_argument('--download', type=Path, help='Separately downloaded original bytes; requires --report')
    args = parser.parse_args()
    if bool(args.report) != bool(args.download):
        parser.error('--report and --download must be supplied together')
    if '.local' not in args.output.resolve().parts:
        raise SystemExit('Keep bound flow definitions under .local')
    with args.profile.open('rb') as source:
        raw = source.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise SystemExit('Qualification profile exceeds limit')
    profile = json.loads(raw)
    if args.report:
        with args.report.open('rb') as source:
            report_raw = source.read(4 * ((MAX_BYTES + 2) // 3) + 65537)
        if len(report_raw) > 4 * ((MAX_BYTES + 2) // 3) + 65536:
            raise SystemExit('Qualification report exceeds limit')
        with args.download.open('rb') as source:
            downloaded = source.read(MAX_BYTES + 1)
        flow = verify_readback(profile, json.loads(report_raw), downloaded)
    else:
        flow = build(profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'w') as target:
        json.dump(flow, target, indent=2)
        target.write('\n')
    print(json.dumps({'prepared': not bool(args.report), 'suppliedByteParityVerified': bool(args.report),
                      'nativeWrites': 0, 'nativeAcceptanceEstablished': False,
                      'singleInvocationQualificationOnly': True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
