# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
"""Reconcile all declared workflow fields, references and file versions without writes."""
import json
import re
from urllib.parse import unquote, urlsplit


def _unique(rows, key):
    result = {}
    for row in rows:
        value = row.get(key)
        if value is None or value in result:
            raise ValueError('Missing or duplicate recovery identity: ' + key)
        result[value] = row
    return result


def _file_bindings(source_row, recovery_row, proof):
    """Bind bytes to the declared records, including preserved origin identities."""
    source_id = re.search(r'fileUniqueId:([^;\s]+)', source_row.get('SourceItemKey', ''), re.I)
    if source_id is None or source_id.group(1).lower() != proof['source']['UniqueId'].lower():
        raise ValueError('Source row is detached from its file proof')
    source_url = urlsplit(source_row.get('SourceURI', ''))
    source_path = unquote(source_url.path)
    historical = re.fullmatch(r'(.*)/_vti_history/([0-9]+)/(.+)', source_path)
    if historical:
        versions = [v for v in proof.get('sourceHistory', [])
                    if str(v.get('ID')) == historical.group(2)
                    and v.get('VersionLabel') == proof['sourceVersion']]
        if len(versions) != 1:
            raise ValueError('Source URL history does not match the exact file version')
        source_path = historical.group(1) + '/' + historical.group(3)
    if (source_url.scheme != 'https' or not source_url.hostname or source_url.username
            or source_url.password or source_path != proof['source']['ServerRelativeUrl']):
        raise ValueError('Source URL does not name the proved file')
    relocation = recovery_row.get('RecoveryCopyURI')
    recovery_uri = relocation.get('Url') if isinstance(relocation, dict) else relocation
    recovery_url = urlsplit(recovery_uri or recovery_row.get('SourceURI', ''))
    if (recovery_url.scheme != 'https' or recovery_url.netloc != source_url.netloc
            or recovery_url.query or recovery_url.fragment
            or unquote(recovery_url.path) != proof['recovered']['ServerRelativeUrl']):
        raise ValueError('Recovery row does not link to the proved independent file')
    # SourceItemKey may deliberately retain origin provenance. The actual copy
    # relationship is established by the explicit recovery URI checked above.
    identity = recovery_row.get('SourceItemKey', '')
    recovered_id = re.search(r'fileUniqueId:([^;\s]+)', identity, re.I)
    if (identity != source_row.get('SourceItemKey') and
            (recovered_id is None or recovered_id.group(1).lower() != proof['recovered']['UniqueId'].lower())):
        raise ValueError('Recovery row file identity has unexplained drift')


def reconcile(bundle):
    if (not isinstance(bundle, dict) or not isinstance(bundle.get('pairs'), list) or not bundle['pairs']
            or not isinstance(bundle.get('snapshots'), dict) or not isinstance(bundle.get('files'), list)):
        raise ValueError('Explicit nonempty selected recovery manifest required')
    snapshots = {key.lower(): value for key, value in bundle['snapshots'].items()}
    proofs = _unique(bundle['files'], 'key')
    captures = _unique(bundle.get('captures', []), 'key')
    counts = dict(families=0, records=0, fields=0, lookups=0, logicalReferences=0, files=0)
    annotations = []
    schema_compatibility = []
    missing_source_values = []
    for pair in bundle['pairs']:
        source = _unique(pair['sourceRows'], pair['key'])
        target = _unique(pair['targetRows'], pair['key'])
        if source.keys() != target.keys():
            raise ValueError('Selected recovery key coverage differs: ' + pair['key'])
        source_schema = snapshots[pair['source']['Id'].lower()]['fields']
        target_schema = {field['InternalName']: field for field in snapshots[pair['target']['Id'].lower()]['fields']}
        if pair['source']['Id'].lower() == pair['target']['Id'].lower():
            raise ValueError('Independent recovery list required')
        fields = [field for field in source_schema if not field['Hidden'] and not field['ReadOnlyField']
                  and field['InternalName'] not in ('ContentType', 'Attachments')]
        for field in fields:
            other = target_schema.get(field['InternalName'])
            if other is None:
                raise ValueError('Recovery schema differs: ' + field['InternalName'])
            types = (field['TypeAsString'], other['TypeAsString'])
            if types[0] != types[1]:
                if types not in [('Choice', 'Text'), ('Text', 'Note')]:
                    raise ValueError('Lossy recovery field conversion: ' + field['InternalName'])
                schema_compatibility.append(dict(family=pair['key'], field=field['InternalName'],
                                                  sourceType=types[0], recoveryType=types[1]))
            if field['TypeAsString'] == 'Choice':
                choices = field.get('Choices')
                if isinstance(choices, dict):
                    choices = choices.get('results')
                if types[1] == 'Choice' and other.get('Choices') != field.get('Choices'):
                    raise ValueError('Recovery choices differ: ' + field['InternalName'])
                if any(row.get(field['InternalName']) is not None
                       and row[field['InternalName']] not in choices for row in target.values()):
                    raise ValueError('Recovery value outside source choices')
            if other.get('Required') != field.get('Required'):
                if other.get('Required') is not False:
                    raise ValueError('Recovery must not impose stronger required constraints')
                schema_compatibility.append(dict(family=pair['key'], field=field['InternalName'],
                                                  sourceRequired=field['Required'], recoveryRequired=False))
        for key, row in source.items():
            copy = target[key]
            for reference_name, binding in bundle.get('referenceBindings', {}).items():
                if reference_name == pair['key'] or row.get(reference_name) is None:
                    continue
                for side, record in [('source', row), ('target', copy)]:
                    candidates = snapshots[binding[side].lower()]['rows']
                    matches = [r for r in candidates if r.get(binding['key']) == record.get(reference_name)]
                    if not matches and reference_name == 'IndicatorVersionKey':
                        details = json.loads(record.get('CaseDetailsJSON') or '{}')
                        definition = details.get('indicatorDefinition', {})
                        if (details.get('fixtureOnly') is True and details.get('realServiceActivity') is False
                                and definition.get('key') == record[reference_name]
                                and isinstance(definition.get('definition'), str) and definition['definition'].strip()
                                and isinstance(definition.get('unit'), str) and definition['unit'].strip()
                                and definition.get('publisherObligation') is False):
                            continue
                    if len(matches) != 1:
                        raise ValueError('Unresolved logical reference: ' + reference_name)
                if row[reference_name] != copy.get(reference_name):
                    raise ValueError('Logical reference changed: ' + reference_name)
                counts['logicalReferences'] += 1
            for field in fields:
                name, kind = field['InternalName'], field['TypeAsString']
                if kind.startswith('Lookup'):
                    name += 'Id'
                a, b = row.get(name), copy.get(name)
                if field.get('Required') and a is None:
                    missing_source_values.append(dict(key=key, field=name))
                if kind.startswith('Lookup') and a is not None:
                    other = target_schema[field['InternalName']]
                    def resolve(schema, value):
                        identifier = schema['LookupList'].strip('{}').lower()
                        parent = _unique(snapshots[identifier]['rows'], 'Id').get(value)
                        if parent is None or parent.get(schema['LookupField']) is None:
                            raise ValueError('Unresolved recovery lookup: ' + name)
                        return identifier, schema['LookupField'], parent[schema['LookupField']]
                    left, right = resolve(field, a), resolve(other, b)
                    if left[0] == right[0] or left[1:] != right[1:]:
                        raise ValueError('Lookup does not resolve independently: ' + name)
                    counts['lookups'] += 1
                elif a != b:
                    if pair['key'] == 'EvidenceVersionKey' and name in ('SourceURI', 'SourceItemKey'):
                        proof = proofs.get(key)
                        if proof is None:
                            raise ValueError('File relocation proof missing')
                        if name == 'SourceURI':
                            if unquote(urlsplit(b).path) != proof['recovered']['ServerRelativeUrl']:
                                raise ValueError('Recovery URL does not name verified copy')
                        elif proof['recovered']['UniqueId'] not in b:
                            raise ValueError('Recovery file identity mismatch')
                    elif name in ('CaseDetailsJSON', 'DecisionDetailsJSON'):
                        left, right = json.loads(a), json.loads(b)
                        additions = set(right) - set(left)
                        allowed = {'recoveryRepresentation'} if name == 'CaseDetailsJSON' else {'isolatedMaintenance'}
                        if not additions <= allowed or {k:v for k,v in right.items() if k not in additions} != left:
                            raise ValueError('Recovered contract content differs: ' + name)
                        annotations.append(dict(key=key, field=name, added={k:right[k] for k in additions}))
                    else:
                        raise ValueError('Recovered value differs: ' + name)
                counts['fields'] += 1
            if row.get('CaptureKey') is not None and row.get('SourceSHA256') is not None:
                capture = captures.get(row['CaptureKey'])
                if capture is None or len(capture['files']) != 2:
                    raise ValueError('Source capture proof missing')
                a, b = capture['files']
                if (a['sha256'] != row['SourceSHA256'] or b['sha256'] != row['SourceSHA256']
                        or a['bytes'] != b['bytes'] or a['bytes'] <= 0
                        or a['file']['UniqueId'] == b['file']['UniqueId']):
                    raise ValueError('Independent source capture mismatch')
            if pair['key'] == 'EvidenceVersionKey':
                proof = proofs.get(key)
                expected_version = re.search(r'file version ([0-9]+\.[0-9]+)', row.get('ExactVersion', ''), re.I)
                expected_hash = re.search(r'SHA-256 ([a-f0-9]{64})', row.get('ExactVersion', ''))
                if (expected_hash is None or proof is None or proof['sourceSHA256'] != expected_hash.group(1)
                        or expected_version is None or proof['sourceVersion'] != expected_version.group(1)
                        or proof.get('independent') is not True
                        or proof['source']['UniqueId'] == proof['recovered']['UniqueId']
                        or proof['sourceSHA256'] != proof['targetSHA256']
                        or proof['bytes'] <= 0):
                    raise ValueError('Independent file/version verification missing')
                _file_bindings(row, copy, proof)
                counts['files'] += 1
            counts['records'] += 1
        counts['families'] += 1
    if counts['files'] != len(proofs):
        raise ValueError('Undeclared file proof')
    return dict(selectedCoverageComplete=True, counts=counts, recoveryAnnotations=annotations,
                archiveSchemaCompatibility=schema_compatibility, sourceMissingRequired=missing_source_values,
                nativeWrites=0, nativeReadbackPerformed=False, wholeLibraryRecovery=False, sourceCaptureFiles=len(captures))


def main():
    import argparse
    import os
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = reconcile(json.loads(args.snapshot.read_text()))
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['counts']))


if __name__ == '__main__':
    main()
