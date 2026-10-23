"""Prepare the existing two-policy next-review producer and context consumer.

Offline only: no sign-in, deployment, invocation or business decisions. The output
folder is create-only; private native bindings never belong in the portable kit.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path

from build_multisource_case_context import (
    _check_context_shape, digest, validate_sources, with_eligible_sources,
)
from build_operator_entry import build, with_case_work_handoff, _flatten
from build_selected_event_routes import audit_actions


def target_identity(flow):
    return {'flowName': flow['name'],
            'environmentName': flow['properties']['environment']['name'],
            'definition': flow['properties']['definition']}


def prepare(legacy, case_work, configuration, case_work_sha256):
    """Compile from retained snapshots; the hash identifies the inspected target."""
    if digest(target_identity(case_work)) != case_work_sha256:
        raise ValueError('Inspected case-work target changed')
    definition = case_work['properties']['definition']
    profiles = validate_sources(configuration['allowedSources'], configuration['siteUrl'])
    existing = _check_context_shape(definition)
    if existing is None:
        consumer = with_eligible_sources(case_work, profiles, digest(definition))
    else:
        if existing != profiles:
            raise ValueError('Installed context profiles differ from selected configuration')
        consumer = copy.deepcopy(case_work)
        consumer['properties']['state'] = 'Stopped'
    consumer_sha256 = digest(target_identity(consumer))
    context_limits = _flatten(consumer['properties']['definition']['actions'])['Selected_case_context']['inputs']['limits']
    additional_operations = {}
    for marker, operations in (
            ('additionalOwnershipProjectionSource', ('Project ownership',)),
            ('additionalPreparationContextSource', ('Check preparation', 'Check readiness'))):
        if context_limits.get(marker) is not None:
            additional_operations.update({operation: context_limits[marker] for operation in operations})
    producer = with_case_work_handoff(build(legacy, configuration), consumer, consumer_sha256)
    producer['properties']['state'] = 'Stopped'
    geometry = {name: audit_actions(flow['properties']['definition'])
                for name, flow in [('consumer', consumer), ('producer', producer)]}
    if any(value['actionCount'] > 500 for value in geometry.values()):
        raise ValueError('Prepared flow exceeds native action limit')
    manifest = {
        'kind': 'offline-next-review-handoff-preparation', 'schemaVersion': 1,
        'sourceOnly': True, 'nativeInstalled': False, 'nativeExecuted': False,
        'observedCaseWorkSHA256': case_work_sha256,
        'preparedConsumerSHA256': consumer_sha256, 'geometry': geometry,
        'sourceCount': len(profiles),
        'remaining': [
            'Native owner refreshes targets and preserves current operations.',
            'Save consumer and compare actual native definition/identity with candidate.',
            'Rebuild against consumer readback before saving the producer.',
            'Verify both contexts, supported next-review receipts, replay and unknown-source refusal.',
        ],
        'limits': {
            'additionalSourcesCheckContextOnly': not additional_operations,
            'otherOperationsRetainOriginalSource': not additional_operations,
            'configuredAdditionalSourceOperations': additional_operations,
            'sourceSpecificPreparationFolderConfigured': context_limits.get('additionalPreparationArtifactFolders') is not None,
            'sourceSpecificReadinessRolesConfigured': context_limits.get('additionalPreparationReadinessRoles') is not None,
            'laterWritersQualified': False, 'ordinaryUserAccessQualified': False,
            'businessDecisionsGranted': False,
        },
    }
    return consumer, producer, manifest


def write_bundle(destination, consumer, producer, manifest):
    """Never replace an existing folder, candidate or hand-edited artifact."""
    values = [('consumer-candidate.json', consumer), ('producer-candidate.json', producer)]
    encoded = {name: (json.dumps(value, indent=2) + '\n').encode() for name, value in values}
    report = copy.deepcopy(manifest)
    report['outputSHA256'] = {name: hashlib.sha256(data).hexdigest() for name, data in encoded.items()}
    encoded['manifest.json'] = (json.dumps(report, indent=2) + '\n').encode()
    destination = Path(destination)
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    # Manifest is written last. A partial folder is retained on I/O failure and
    # must be inspected; a retry cannot silently overwrite it.
    for name, data in encoded.items():
        descriptor = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initiation', type=Path, required=True)
    parser.add_argument('--case-work', type=Path, required=True)
    parser.add_argument('--configuration', type=Path, required=True)
    parser.add_argument('--case-work-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = {'initiation': args.initiation, 'caseWork': args.case_work, 'configuration': args.configuration}
    raw = {name: path.read_bytes() for name, path in paths.items()}
    inputs = {name: json.loads(data) for name, data in raw.items()}
    consumer, producer, manifest = prepare(inputs['initiation'], inputs['caseWork'],
                                           inputs['configuration'], args.case_work_sha256)
    manifest['inputSHA256'] = {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()}
    write_bundle(args.output, consumer, producer, manifest)
    print(json.dumps({'sourceOnly': True, 'nativeInstalled': False,
                      'sourceCount': manifest['sourceCount'], 'geometry': manifest['geometry']}))


if __name__ == '__main__':
    main()
