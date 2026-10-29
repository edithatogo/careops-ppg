# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
"""Bounded fictional second example; reuses shared graph, access and recovery."""
from copy import deepcopy
from datetime import date

from scripts.ppg_accreditation_contract import validate_graph, freeze, restore
from scripts.ppg_source_standards import digest


def validate_example(package, graph):
    validation = validate_graph(graph)
    if (not isinstance(package, dict) or package.get('fixtureOnly') is not True
            or package.get('nativeWrites') is not False):
        raise ValueError('Second example must remain fictional and local')
    contexts = {row['ReviewContextKey']: row for row in graph['contexts']}
    context = contexts.get(package.get('ReviewContextKey'))
    if context is None or any(context.get(field) is not None for field in (
            'CycleKey', 'AccreditorRef', 'AwardKey')):
        raise ValueError('Cycle-free quality-improvement context required')
    requirements = {row['RequirementKey']: row for row in graph['requirements']}
    statement = requirements.get(package.get('QualityStatementKey'))
    action = requirements.get(package.get('NSQHSRequirementKey'))
    if (statement is None or action is None or statement['kind'] != 'quality-statement'
            or action['kind'] != 'action' or statement['FrameworkKey'] == action['FrameworkKey']):
        raise ValueError('Separate quality-statement and action frameworks required')
    version = package.get('EvidenceVersionKey')
    scoped_assessments = []
    for requirement in (statement, action):
        assessments = [row for row in graph['assessments']
                       if row['RequirementKey'] == requirement['RequirementKey']
                       and row['ReviewContextKey'] == context['ReviewContextKey']]
        if len(assessments) != 1:
            raise ValueError('Separate scoped assessment required for each requirement')
        assessment = assessments[0]
        scoped_assessments.append(assessment)
        mappings = [row for row in graph['mappings']
                    if row['MappingKey'] in assessment['MappingKeys']
                    and row['EvidenceVersionKey'] == version]
        if (len(mappings) != 1 or assessment['outcome'] != 'unknown'
                or assessment['applicability'] != 'unknown'):
            raise ValueError('Shared evidence needs independent unknown judgements')
    if scoped_assessments[0]['ScopeKey'] != scoped_assessments[1]['ScopeKey']:
        raise ValueError('Bounded second example requires the same explicit scope')
    observation, definition = package.get('indicatorObservation'), package.get('indicatorDefinition')
    if not isinstance(observation, dict) or not isinstance(definition, dict):
        raise ValueError('Versioned indicator observation and definition required')
    for row in (observation, definition):
        if any(field in row for field in ('Target', 'ComplianceRating', 'ReadinessScore', 'AccreditationDecision')):
            raise ValueError('No fabricated targets or compliance ratings')
        for field in ('IndicatorDefinitionVersionKey', 'SourceLocator', 'Unit'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError('Explicit indicator version, unit and locator required')
    if (observation['IndicatorDefinitionVersionKey'] != definition['IndicatorDefinitionVersionKey']
            or observation['Unit'] != definition['Unit'] or observation['Unit'] != 'percent'
            or observation.get('EvidenceVersionKey') != version):
        raise ValueError('Indicator definition/version/unit/evidence mismatch')
    source_hash = definition.get('SourceSHA256')
    if (not isinstance(source_hash, str) or len(source_hash) != 64
            or any(value not in '0123456789abcdef' for value in source_hash)):
        raise ValueError('Exact fictional definition source hash required')
    for field in ('ObservationKey', 'PeriodStart', 'PeriodEnd'):
        if not isinstance(observation.get(field), str) or not observation[field].strip():
            raise ValueError('Observation identity and period required')
    try:
        start, end = (date.fromisoformat(observation[field]) for field in ('PeriodStart', 'PeriodEnd'))
    except ValueError as exc:
        raise ValueError('Invalid observation period') from exc
    if end < start:
        raise ValueError('Invalid observation period')
    if (start.isoformat() != observation['PeriodStart'] or end.isoformat() != observation['PeriodEnd']
            or context['period'] != start.isoformat()+'/'+end.isoformat()):
        raise ValueError('Observation period must match the bounded context')
    limits = observation.get('Limitations')
    if not isinstance(limits, list) or not limits or any(not isinstance(x, str) or not x.strip() for x in limits):
        raise ValueError('Explicit source limitations required')
    if 'Numerator' not in observation or 'Denominator' not in observation:
        raise ValueError('Numerator and denominator must be explicit, including null')
    numerator, denominator = observation['Numerator'], observation['Denominator']
    for value in (numerator, denominator):
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError('Invalid indicator counts')
    missing = numerator is None or denominator is None
    if missing:
        reason = observation.get('MissingDataReason')
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('Missing data must remain explicit with a reason')
    if denominator == 0 or (not missing and numerator > denominator):
        raise ValueError('Invalid indicator denominator')
    return dict(graphSha256=validation['graphSha256'], packageSha256=digest(package),
                observationState='missing-data' if missing else 'recorded',
                sourceAuthorityVerified=False, nativeWrites=0, nativeWorkflowQualified=False,
                readinessScoreComputed=False, accreditationDecision=None)


def freeze_example(package, graph):
    validate_example(package, graph)
    payload = dict(package=deepcopy(package), graphSnapshot=freeze(graph))
    return dict(kind='fictional_quality_example_snapshot', payload=payload,
                sha256=digest(payload), nativeRecoveryQualified=False)


def restore_example(snapshot, *, expected_sha256):
    if (not isinstance(snapshot, dict) or snapshot.get('kind') != 'fictional_quality_example_snapshot'
            or snapshot.get('nativeRecoveryQualified') is not False
            or not isinstance(snapshot.get('payload'), dict)
            or snapshot.get('sha256') != expected_sha256
            or digest(snapshot['payload']) != expected_sha256):
        raise ValueError('Second-example snapshot integrity conflict')
    payload = snapshot['payload']
    graph = restore(payload['graphSnapshot'])
    package = deepcopy(payload['package'])
    validate_example(package, graph)
    return package, graph


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    case = json.loads(args.fixture.read_text())
    package, graph = case['package'], case['graph']
    validation = validate_example(package, graph)
    snapshot = freeze_example(package, graph)
    if restore_example(snapshot, expected_sha256=snapshot['sha256']) != (package, graph):
        raise ValueError('Second-example round trip differs')
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, value in (('validation.json', validation), ('snapshot.json', snapshot)):
        target = args.output / name
        with target.open('x') as stream:
            target.chmod(0o600)
            stream.write(json.dumps(value, indent=2)+'\n')
    print(json.dumps(validation))


if __name__ == '__main__':
    main()
