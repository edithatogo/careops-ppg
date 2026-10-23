"""Prepare the three existing recording flows from one reviewed binary proof.

Offline deployment preparation only: no service calls, activation or execution.
Reuses existing compilers and rejects stale target snapshots before composition.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'policy-editions'))
from binary_publication import digest
from build_prepared_binary_publication import build as publication_build
from build_prepared_implementation import build as implementation_build
from build_selected_prepared_verification import build as verification_build
from build_selected_event_routes import audit_actions

STAGES = ('publication', 'implementation', 'verification')


def build(purpose, targets, config, producer_evidence):
    required_config = {'publicationBinding', 'caseListUri', 'approvedTargetDefinitionSHA256'}
    note_keys = {'implementationActionsNoteField', 'approvedImplementationActionsNoteFieldSHA256'}
    if (set(targets) != set(STAGES) or not required_config <= set(config)
            or not set(config) <= required_config | note_keys):
        raise ValueError('Exact three existing targets and reviewed configuration required')
    pins = config['approvedTargetDefinitionSHA256']
    if set(pins) != set(STAGES):
        raise ValueError('Every target must have an explicitly reviewed definition pin')
    names = []
    for stage in STAGES:
        target = targets[stage]
        if target['properties'].get('state') != 'Stopped':
            raise ValueError('Stopped target snapshot required: ' + stage)
        if digest(target['properties']['definition']) != pins[stage]:
            raise ValueError('Target definition changed: ' + stage)
        names.append(target.get('name'))
    if any(not name for name in names) or len(set(names)) != 3:
        raise ValueError('Three distinct existing flow identities required')
    binding = copy.deepcopy(config['publicationBinding'])
    if binding.get('reviewedBinaryProof') is None:
        raise ValueError('Separately verified binary proof required; no eligibility flag substitute')
    if binding['approvedTargetDefinitionSHA256'] != pins['publication']:
        raise ValueError('Publication target pins disagree')
    publication = publication_build(purpose, targets['publication'], binding, producer_evidence)
    implementation_binding = {
        'qualificationOnly': True,
        'approvedPublicationDefinitionSHA256': digest(publication['properties']['definition']),
        'approvedTargetDefinitionSHA256': pins['implementation']}
    for key in note_keys & config.keys():
        implementation_binding[key] = copy.deepcopy(config[key])
    implementation = implementation_build(publication, targets['implementation'], implementation_binding)
    verification = verification_build(implementation, targets['verification'], {
        'qualificationOnly': True,
        'approvedImplementationDefinitionSHA256': digest(implementation['properties']['definition']),
        'approvedTargetDefinitionSHA256': pins['verification'],
        'caseListUri': config['caseListUri']})
    outputs = dict(zip(STAGES, (publication, implementation, verification)))
    manifest = {'kind': 'prepared-recording-chain-v1', 'nativeWrites': 0,
        'runtimeQualified': False, 'requiresFreshNativePreflightBeforeSave': True,
        'sourcePurposeDefinitionSHA256': digest(purpose['properties']['definition']),
        'reviewedInputTargetDefinitionSHA256': copy.deepcopy(pins),
        'reviewedProofReceipt': copy.deepcopy(binding['reviewedBinaryProof']['receipt']),
        'outputs': {}}
    for stage, flow in outputs.items():
        manifest['outputs'][stage] = {
            'flowName': flow['name'], 'state': flow['properties']['state'],
            'definitionSHA256': digest(flow['properties']['definition']),
            'geometry': audit_actions(flow['properties']['definition'])}
    return outputs, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--purpose', required=True)
    for stage in STAGES: parser.add_argument('--' + stage + '-target', required=True)
    parser.add_argument('--config', required=True)
    parser.add_argument('--producer-evidence', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(Path(path).read_bytes())
    outputs, manifest = build(read(args.purpose),
        {stage: read(getattr(args, stage + '_target')) for stage in STAGES},
        read(args.config), Path(args.producer_evidence).read_bytes())
    folder = Path(args.output)
    folder.mkdir(parents=False, exist_ok=False)
    for stage, flow in outputs.items():
        with (folder / (stage + '.json')).open('x') as f: json.dump(flow, f, indent=2)
    with (folder / 'manifest.json').open('x') as f: json.dump(manifest, f, indent=2)
    print('Prepared three existing flow candidates; no native operations performed.')


if __name__ == '__main__': main()
