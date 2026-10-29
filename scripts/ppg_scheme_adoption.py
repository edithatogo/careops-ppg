# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
"""Versioned scheme configuration for existing framework records; no native writes."""
from copy import deepcopy
from scripts.ppg_accreditation_contract import validate_shared_configuration
from scripts.ppg_source_standards import digest


def project_scheme(framework_key, contract, vocabularies, *, scheme_key=None):
    validate_shared_configuration(contract, vocabularies)
    schemes = [row for row in vocabularies['schemes'] if row['schemeKey'] == scheme_key]
    if scheme_key is not None and (len(schemes) != 1 or framework_key not in schemes[0]['frameworkKeys']):
        raise ValueError('Exact scheme/framework membership required')
    if not isinstance(framework_key, str) or not framework_key.strip():
        raise ValueError('Framework identity required')
    ratings = [deepcopy(row) for row in vocabularies['ratingVocabularies']
               if row['schemeKey'] == scheme_key and row['frameworkKey'] == framework_key]
    if scheme_key is not None and not ratings:
        raise ValueError('Sourced rating vocabulary required')
    payload = dict(schemaVersion=1, FrameworkKey=framework_key, SchemeKey=scheme_key,
                   coreContractVersion=contract['contractVersion'],
                   coreContractSHA256=digest(contract),
                   reviewContextRequired=True, accreditationCycleRequired=False,
                   scheme=deepcopy(schemes[0]) if schemes else None,
                   ratingVocabularies=ratings,
                   internalReviewStates=deepcopy(vocabularies['internalReviewStates']),
                   invariants=deepcopy(vocabularies['invariants']),
                   automaticRating=False, automaticAward=False)
    return dict(kind='framework-scheme-configuration', payload=payload, sha256=digest(payload))


def adoption_action(existing, expected):
    if (not isinstance(expected, dict) or expected.get('kind') != 'framework-scheme-configuration'
            or expected.get('sha256') != digest(expected.get('payload'))):
        raise ValueError('Configuration integrity mismatch')
    if existing is None:
        return 'create'
    if existing == expected:
        return 'reuse'
    raise ValueError('Existing scheme configuration differs; preserve it and reconcile explicitly')


def main():
    import argparse
    import json
    import os
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--framework-key', required=True)
    parser.add_argument('--scheme-key')
    parser.add_argument('--contract', required=True, type=Path)
    parser.add_argument('--vocabularies', required=True, type=Path)
    parser.add_argument('--existing', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = project_scheme(args.framework_key, json.loads(args.contract.read_text()),
                            json.loads(args.vocabularies.read_text()), scheme_key=args.scheme_key)
    action = adoption_action(json.loads(args.existing.read_text()) if args.existing else None, result)
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(action=action, nativeWrites=0)))


if __name__ == '__main__':
    main()
