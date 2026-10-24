"""Join the qualified fixed-source transport and supplied-byte hash in one flow.

Preparation and readback comparison only: never authenticates, saves or runs a flow.
Persistence, provenance authentication and whole-track acceptance remain separate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from scripts.ppg_sourcing_preflight import validate as validate_transport
from scripts.ppg_url_acquisition_qualification import build as build_transport
from scripts.ppg_url_acquisition_qualification import verify_readback

EXCEL = 'shared_excelonlinebusiness'
EXCEL_API = '/providers/Microsoft.PowerApps/apis/' + EXCEL
RUNTIME_KEYS = {'source', 'drive', 'file', 'scriptSource', 'scriptDrive', 'scriptId',
                'connectionReference', 'scriptPackageSHA256', 'runtimeSourceSHA256'}
PARAMETERS = ('source', 'drive', 'file', 'scriptSource', 'scriptDrive', 'scriptId')


def _runtime(runtime):
    if not isinstance(runtime, dict) or set(runtime) != RUNTIME_KEYS:
        raise ValueError('Exact previously qualified hash runtime required')
    result = copy.deepcopy(runtime)
    for k in PARAMETERS:
        value = result[k]
        if (not isinstance(value, str) or not value or len(value) > 512
                or value.startswith('@') or '@{' in value
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError('Literal existing script/workbook bindings required')
    if result['source'] != 'me' or result['scriptSource'] != 'me':
        raise ValueError('Only the qualified personal-drive runtime is supported')
    ref = result['connectionReference']
    if (not isinstance(ref, dict) or set(ref) != {'id', 'connectionName', 'source'}
            or ref['id'] != EXCEL_API or ref['source'] != 'Embedded'
            or not isinstance(ref['connectionName'], str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', ref['connectionName'])):
        raise ValueError('Existing embedded Excel connection required')
    for name in ('scriptPackageSHA256', 'runtimeSourceSHA256'):
        if not isinstance(result[name], str) or not re.fullmatch('[0-9a-f]{64}', result[name]):
            raise ValueError('Qualified script byte pins required')
    return result


def _compose(value, predecessor=None):
    return {'type': 'Compose', 'runAfter': {predecessor: ['Succeeded']} if predecessor else {},
            'inputs': value}


def _hold(code):
    return {'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed',
            'runError': {'code': code, 'message': 'Preserve the run and existing files; reconcile before another invocation.'}}}


def build(profile, runtime):
    """Fixed-source acquisition + native hash, retaining the original upload guards."""
    flow = build_transport(profile)
    if validate_transport(flow):
        raise ValueError('Transport did not pass its existing Standard-only gate')
    r = _runtime(runtime)
    props = flow['properties']
    props['connectionReferences'][EXCEL] = r['connectionReference']
    branch = props['definition']['actions']['Select_fixed_source']['actions']
    readback = branch['Require_ready']['actions']['Require_expected_metadata']['actions']
    stable = readback['Require_stable_metadata']['actions']
    previous = stable.pop('Report_candidate')
    hash_profile = {'kind': 'ppg-supplied-byte-hash-v1', **{
        k: profile[k] for k in ('qualificationId', 'sourceKey', 'expectedBytes', 'expectedSHA256')}}
    stable['Hash_profile'] = _compose(hash_profile)
    stable['Hash_request'] = _compose(
        "@setProperty(outputs('Hash_profile'), 'contentBase64', body('Read_content')?['$content'])",
        'Hash_profile')
    parameters = {k: r[k] for k in PARAMETERS}
    parameters['ScriptParameters/requestJson'] = "@string(outputs('Hash_request'))"
    stable['Run_hash'] = {'type': 'OpenApiConnection', 'runAfter': {'Hash_request': ['Succeeded']},
        'inputs': {'host': {'apiId': EXCEL_API, 'connectionName': EXCEL,
                           'operationId': 'RunScriptProdV2'},
                   'parameters': parameters, 'retryPolicy': {'type': 'none'}}}
    stable['Hash_result'] = _compose("@json(body('Run_hash')?['result'])", 'Run_hash')
    post_hash = copy.deepcopy(readback['Metadata_after'])
    post_hash['runAfter'] = {'Hash_result': ['Succeeded']}
    stable['Metadata_after_hash'] = post_hash
    checks = [
        "equals(outputs('Hash_result')?['kind'],'ppg-supplied-byte-hash-result-v1')",
        "equals(outputs('Hash_result')?['qualificationId'],outputs('Hash_profile')?['qualificationId'])",
        "equals(outputs('Hash_result')?['sourceKey'],outputs('Hash_profile')?['sourceKey'])",
        "equals(outputs('Hash_result')?['actualBytes'],outputs('Hash_profile')?['expectedBytes'])",
        "equals(outputs('Hash_result')?['actualSHA256'],outputs('Hash_profile')?['expectedSHA256'])",
        "equals(outputs('Hash_result')?['expectedSHA256'],outputs('Hash_profile')?['expectedSHA256'])",
        "equals(outputs('Hash_result')?['integrityMatches'],true)",
        "equals(outputs('Hash_result')?['sourceProvenanceAuthenticated'],false)",
        "equals(outputs('Hash_result')?['nativeAcquisitionQualified'],false)",
        "equals(body('Metadata_after_hash')?['Id'],body('Metadata_after')?['Id'])",
        "equals(body('Metadata_after_hash')?['ETag'],body('Metadata_after')?['ETag'])",
        "equals(body('Metadata_after_hash')?['Size'],outputs('Hash_profile')?['expectedBytes'])",
        "equals(body('Metadata_after_hash')?['IsFolder'],false)",
    ]
    report = copy.deepcopy(previous['inputs'])
    # The original transport report stays intact as nested, non-authorising evidence.
    report = {'kind': 'ppg-integrated-transport-hash-observation-v1',
              'transport': report, 'hashResult': "@outputs('Hash_result')",
              'metadataAfterHash': "@body('Metadata_after_hash')",
              'workflowId': "@workflow()?['name']", 'runName': "@workflow()?['run']?['name']",
              'scriptPackageSHA256': r['scriptPackageSHA256'],
              'runtimeSourceSHA256': r['runtimeSourceSHA256'],
              'associationPersisted': False, 'checkpointAdvanced': False,
              'fullAcquisitionQualified': False, 'clinicalApplicabilityAccepted': False}
    stable['Require_integrated_integrity'] = {'type': 'If',
        'runAfter': {'Metadata_after_hash': ['Succeeded']},
        'expression': '@and(' + ','.join(checks) + ')',
        'actions': {'Report_integrated_candidate': _compose(report)},
        'else': {'actions': {'Hold_integrated_integrity': _hold('IntegratedIntegrityHeld')}}}
    # Keep the trigger/schema, display name, acquisition and no-overwrite settings.
    return flow


def _native_projection(flow):
    """Remove only known native readback adornments; no expression normalisation."""
    p = copy.deepcopy(flow['properties'])
    definition = p['definition']
    if definition.get('outputs') == {}:
        definition.pop('outputs')

    def visit(actions):
        for action in actions.values():
            if action.get('type') == 'OpenApiConnection':
                inputs = action['inputs']
                if inputs.get('authentication') == "@parameters('$authentication')":
                    inputs.pop('authentication')
            if 'actions' in action:
                visit(action['actions'])
            for branch in ('else', 'default'):
                if branch in action:
                    visit(action[branch].get('actions', {}))
            for case in action.get('cases', {}).values():
                visit(case.get('actions', {}))
    visit(definition['actions'])
    refs = p['connectionReferences']
    return {'displayName': p['displayName'], 'definition': definition,
            'connectionReferences': {k: {f: v[f] for f in ('id', 'connectionName', 'source')}
                                     for k, v in refs.items()}}


def validate(flow, profile, runtime):
    """Exact graph/binding comparison, including the one reviewed script action.

    An arbitrary Excel action or REST/child-flow path is never allowlisted here.
    Actual alerts, state, creator and script/workbook bytes need native readback.
    """
    try:
        expected = build(profile, runtime)
        if _native_projection(flow) != _native_projection(expected):
            return ['integrated-definition-or-bindings-differ']
        if flow['properties'].get('flowFailureAlertSubscribed') is not False:
            return ['actual-owner-alerts-not-off']
        if flow['properties'].get('state') != 'Stopped':
            return ['stopped-state-required']
    except (KeyError, TypeError, ValueError, AttributeError):
        return ['invalid-integrated-definition-or-profile']
    return []


def source_pins(profile, runtime):
    """Bind reviewed preparation to exact source bytes in a private invocation receipt."""
    candidate = build(profile, runtime)
    return {'candidateSHA256': hashlib.sha256(json.dumps(candidate, sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode()).hexdigest(),
            'scriptPackageSHA256': runtime['scriptPackageSHA256'],
            'runtimeSourceSHA256': runtime['runtimeSourceSHA256'],
            'nativeSaveVerified': False, 'nativeRunVerified': False,
            'associationPersisted': False, 'fullAcquisitionQualified': False}


def verify_observation(profile, runtime, report, independent_bytes):
    """Compare supplied integrated output to independent bytes; not run authentication."""
    r = _runtime(runtime)
    if not isinstance(report, dict) or report.get('kind') != 'ppg-integrated-transport-hash-observation-v1':
        raise ValueError('Integrated observation required')
    for key in ('associationPersisted', 'checkpointAdvanced', 'fullAcquisitionQualified',
                'clinicalApplicabilityAccepted'):
        if report.get(key) is not False:
            raise ValueError('Premature integrated acceptance assertion')
    for key in ('scriptPackageSHA256', 'runtimeSourceSHA256'):
        if report.get(key) != r[key]:
            raise ValueError('Qualified script pins differ')
    transport = verify_readback(profile, report.get('transport'), independent_bytes)
    run = report.get('runName')
    if (run != report['transport']['runName'] or not isinstance(report.get('workflowId'), str)
            or not report['workflowId'] or len(report['workflowId']) > 256):
        raise ValueError('Integrated workflow/run identity differs')
    result = report.get('hashResult')
    expected = {'kind': 'ppg-supplied-byte-hash-result-v1',
                'qualificationId': profile['qualificationId'], 'sourceKey': profile['sourceKey'],
                'actualBytes': len(independent_bytes),
                'actualSHA256': hashlib.sha256(independent_bytes).hexdigest(),
                'expectedSHA256': profile['expectedSHA256'], 'integrityMatches': True,
                'sourceProvenanceAuthenticated': False, 'nativeAcquisitionQualified': False}
    # JSON equality alone would treat booleans as integers in Python.
    if json.dumps(result, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError('Actual supplied-byte hash result differs')
    before = report['transport']['metadataAfter']
    after = report.get('metadataAfterHash')
    if (not isinstance(after, dict) or any(after.get(k) != before.get(k) for k in ('Id', 'ETag'))
            or type(after.get('Size')) is not int or after['Size'] != len(independent_bytes)
            or after.get('IsFolder') is not False):
        raise ValueError('Source metadata changed during hashing')
    return {**transport, 'suppliedHashMatchesIndependentBytes': True,
            'integratedRunProvenanceAuthenticated': False, 'associationPersisted': False,
            'fullAcquisitionQualified': False}
