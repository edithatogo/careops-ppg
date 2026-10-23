#!/usr/bin/env python3
"""Validate the workspace contract and project presentation-only health.

No tenant writes, source mutations or implicit business approvals.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def validate_structure(value, schema, path='$'):
    """Validate the structural keywords used by the bundled v1 schema."""
    if 'const' in schema and (value != schema['const'] or
                              isinstance(value, bool) != isinstance(schema['const'], bool)):
        raise ValueError(f'{path}: unexpected constant')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{path}: invalid enum value')
    types = schema.get('type', [])
    types = [types] if isinstance(types, str) else types
    checks = {'object': lambda v: isinstance(v, dict),
              'array': lambda v: isinstance(v, list),
              'string': lambda v: isinstance(v, str),
              'integer': lambda v: type(v) is int,
              'boolean': lambda v: type(v) is bool,
              'null': lambda v: v is None}
    if types and not any(checks[t](value) for t in types):
        raise ValueError(f'{path}: wrong value type')
    if isinstance(value, dict) and 'properties' in schema:
        properties = schema['properties']
        if set(schema.get('required', [])) - value.keys():
            raise ValueError(f'{path}: missing required fields')
        if schema.get('additionalProperties') is False and value.keys() - properties.keys():
            raise ValueError(f'{path}: unexpected fields')
        for key in value.keys() & properties.keys():
            validate_structure(value[key], properties[key], f'{path}.{key}')
    elif isinstance(value, list) and 'items' in schema:
        for index, item in enumerate(value):
            validate_structure(item, schema['items'], f'{path}[{index}]')
    elif isinstance(value, str) and len(value) < schema.get('minLength', 0):
        raise ValueError(f'{path}: empty string')
    elif type(value) is int and value < schema.get('minimum', value):
        raise ValueError(f'{path}: below minimum')
    if schema.get('format') == 'date-time' and value is not None:
        parse_time(value)


def validate(manifest):
    schema = json.loads((Path(__file__).resolve().parents[1] /
                         'config/workspace.schema.json').read_text())
    validate_structure(manifest, schema)
    if manifest.get('schemaVersion') != 1:
        raise ValueError('Unsupported workspace schemaVersion')
    groups = ('capabilities', 'artefacts', 'surfaces')
    keys = {}
    required = {
        'capabilities': ('key', 'purpose', 'lifecycle', 'executionMode', 'responsibleRole', 'resources', 'dependencies', 'acceptanceCriteria'),
        'artefacts': ('key', 'capabilityKey', 'type', 'resourceRef', 'location', 'provenanceRef', 'contentStatus'),
        'surfaces': ('key', 'label', 'type', 'resourceRef', 'placement', 'accessBoundary'),
    }
    for group in groups:
        records = manifest[group]
        keys[group] = {r['key'] for r in records}
        if len(keys[group]) != len(records):
            raise ValueError(f'Duplicate {group} key')
        for record in records:
            for field in required[group]:
                if field not in record:
                    raise ValueError(f'{group}/{record["key"]}: missing {field}')
    for c in manifest['capabilities']:
        if c['lifecycle'] not in ('planned', 'pilot', 'live', 'retired'):
            raise ValueError('Invalid technical lifecycle')
        if c['executionMode'] not in ('native-interactive', 'native-scheduled', 'local-manual'):
            raise ValueError('Invalid execution mode')
        if set(c['resources']) - keys['artefacts'] or set(c['dependencies']) - keys['capabilities']:
            raise ValueError('Unresolved capability reference')
    for a in manifest['artefacts']:
        if a['capabilityKey'] not in keys['capabilities']:
            raise ValueError('Unresolved artefact capability')
    for s in manifest['surfaces']:
        if s['resourceRef'] not in keys['artefacts']:
            raise ValueError('Unresolved surface resource')
    placements = [s['placement'] for s in manifest['surfaces']]
    if len(placements) != len(set(placements)):
        raise ValueError('Duplicate surface placement')
    return True


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def project_status(source, checkpoint, attempt, now=None):
    """A poll cannot clear an outstanding source/committed-version mismatch."""
    now = now or datetime.now(timezone.utc)
    result = {'capabilityKey': 'source-sync', 'status': 'unknown',
              'projectedAt': now.isoformat(), 'latestCheck': source.get('checkedUtc'),
              'lastSuccessfulReconciliation': checkpoint.get('asOfUtc'),
              'observedVersion': source.get('sourceETag'),
              'committedVersion': checkpoint.get('centralSourceETag'),
              'committedCount': checkpoint.get('readbackCount'),
              'latestAttemptOutcome': attempt.get('status'), 'evidenceLink': None,
              'reason': 'Evidence missing or inconsistent', 'nextAction': 'Inspect source-sync evidence'}
    try:
        if not all((source.get('checkedUtc'), source.get('sourceETag'),
                    checkpoint.get('centralSourceETag'), checkpoint.get('asOfUtc'))):
            return result
        if attempt.get('status') not in ('completed', 'running', 'failed_partial_or_unverified') or not attempt.get('asOfUtc'):
            return result
        if not isinstance(checkpoint.get('readbackCount'), int) or checkpoint['readbackCount'] < 1:
            return result
        checked = parse_time(source['checkedUtc'])
        committed = parse_time(checkpoint['asOfUtc'])
        if checked > now or committed > now or parse_time(attempt['asOfUtc']) > now or checkpoint.get('status') != 'completed':
            return result
        changed = source['sourceETag'] != checkpoint['centralSourceETag']
        if changed:
            failed = attempt.get('status') == 'failed_partial_or_unverified'
            recent = bool(attempt.get('asOfUtc')) and parse_time(attempt['asOfUtc']) > committed
            if failed and recent and attempt.get('attemptedWrites') == 0:
                result.update(status='held', reason='Source change detected—reconciliation held',
                              nextAction='Investigate the pre-write failure; resolve identity exceptions through the existing identity contract')
            elif failed and recent:
                result.update(status='failed', reason='Changed-source reconciliation failed or remains unverified')
            else:
                result.update(status='held', reason='Source change detected; reconciliation has not been verified')
        elif attempt.get('status') == 'failed_partial_or_unverified' and parse_time(attempt['asOfUtc']) > committed:
            result.update(status='failed', reason='Latest reconciliation failed; last successful baseline retained')
        elif (now - checked).total_seconds() > 5400:
            result.update(status='unknown', reason='Source check is overdue; last successful baseline retained')
        else:
            result.update(status='healthy', reason='Latest observed source matches the last verified reconciliation', nextAction='None')
    except (ValueError, TypeError, KeyError):
        pass
    return result


def display_status(status, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        if not isinstance(status['projectedAt'], str):
            return 'unknown'
        age = (now - parse_time(status['projectedAt'])).total_seconds()
        if age < 0:
            return 'unknown'
        if age > 1800:
            return 'stale'
    except (KeyError, ValueError, TypeError):
        return 'unknown'
    return status['status']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', nargs='?', default='config/workspace-manifest.json')
    args = parser.parse_args()
    validate(json.loads(Path(args.manifest).read_text()))
    print('Workspace manifest valid')
