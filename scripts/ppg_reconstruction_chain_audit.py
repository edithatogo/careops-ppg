# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
"""Audit a frozen reconstruction evidence chain without native writes."""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urldefrag, urlsplit


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def checked_file(directory, name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('Invalid artifact path')
    relative = PurePosixPath(name)
    if relative.is_absolute() or relative.as_posix() != name or any(part in ('.', '..') for part in relative.parts):
        raise ValueError('Artifact path escapes package')
    current = directory
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Symlink in artifact path')
    if not current.is_file():
        raise ValueError('Missing artifact')
    return current


def audit(root, expected_head):
    if not re.fullmatch(r'[0-9a-f]{64}', expected_head):
        raise ValueError('A pinned SHA-256 head is required')
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Invalid chain root')
    base_dir = root / 'reconstruction-package-v1'
    if base_dir.is_symlink() or not base_dir.is_dir():
        raise ValueError('Invalid base package')
    base_manifest = checked_file(base_dir, 'package-manifest.json')
    manifests = [base_manifest]
    extensions = []
    for path in root.iterdir():
        match = re.fullmatch(r'reconstruction-package-extension-v([1-9][0-9]*)', path.name)
        if match:
            if path.is_symlink() or not path.is_dir():
                raise ValueError('Invalid extension directory')
            extensions.append((int(match.group(1)), path))
    extensions.sort()
    if not extensions or [n for n, _ in extensions] != list(range(1, len(extensions) + 1)):
        raise ValueError('Missing or non-contiguous extensions')
    total = 0
    for index, directory in [(0, base_dir)] + extensions:
        manifest_path = base_manifest if index == 0 else checked_file(directory, 'extension-manifest.json')
        if index:
            manifests.append(manifest_path)
        manifest = json.loads(manifest_path.read_bytes())
        if index == 1 and manifest.get('basePackageManifestSha256') != digest(base_manifest):
            raise ValueError('Base manifest binding mismatch')
        if index > 1:
            if manifest.get('priorExtensionSha256') != digest(manifests[-2]):
                raise ValueError('Prior extension binding mismatch')
            if 'priorExtension' in manifest and manifest['priorExtension'] != f'reconstruction-package-extension-v{index - 1}/extension-manifest.json':
                raise ValueError('Prior extension path mismatch')
        entries = manifest.get('files')
        if isinstance(entries, dict):
            entries = [{'path': name, 'sha256': value} for name, value in entries.items()]
        if not isinstance(entries, list) or not entries:
            raise ValueError('Missing artifact list')
        names = set()
        for entry in entries:
            name, expected = entry.get('path'), entry.get('sha256')
            if name in names or not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
                raise ValueError('Duplicate artifact or invalid digest')
            names.add(name)
            artifact = checked_file(directory, name)
            if digest(artifact) != expected or ('bytes' in entry and artifact.stat().st_size != entry['bytes']):
                raise ValueError('Artifact hash or length mismatch')
            total += 1
    if digest(manifests[-1]) != expected_head:
        raise ValueError('Head manifest mismatch')
    return {'headSha256': expected_head, 'baseManifestSha256': digest(base_manifest),
            'extensions': len(extensions), 'artifactsChecked': total, 'nativeWrites': 0,
            'limitations': ['Integrity of captured files and declared chain only.',
                            'Does not prove completeness, native restoration, access or runtime behavior.']}


def pointer(document, path):
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('Invalid JSON pointer')
    value = document
    for raw in path[1:].split('/'):
        if re.search(r'~(?![01])', raw):
            raise ValueError('Invalid JSON pointer escape')
        token = raw.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', token):
                raise ValueError('Invalid array index')
            value = value[int(token)]
        elif isinstance(value, dict):
            value = value[token]
        else:
            raise ValueError('Pointer traverses scalar')
    return value


def verify_selected_index(root):
    """Reconcile the selected index with manifest-bound captured records."""
    base = root / 'reconstruction-package-v1'
    ext = root / 'reconstruction-package-extension-v1'
    manifest = json.loads(checked_file(base, 'package-manifest.json').read_bytes())
    extension = json.loads(checked_file(ext, 'extension-manifest.json').read_bytes())
    index_name = 'selected-reconstruction-index-v4.json'
    if not any(e.get('path') == index_name for e in extension['files']):
        raise ValueError('Selected index is not manifest-bound')
    index = json.loads(checked_file(ext, index_name).read_bytes())
    declared = {e['path']: e for e in manifest['files']}
    references = {}
    for entry in index['artifacts']:
        name = entry['path']
        bound = declared.get('evidence/' + name)
        if name in references or not bound or bound['sha256'] != entry['sha256'] or bound.get('bytes') != entry.get('bytes'):
            raise ValueError('Index artifact is not uniquely bound to the base package')
        references[name] = checked_file(base, 'evidence/' + name)
    core = index['coreCase']
    core_name = core['readback']
    core_bound = declared.get('evidence/' + core_name)
    if not core_bound or core_bound['sha256'] != core['sha256']:
        raise ValueError('Core readback is not bound to the base package')
    references[core_name] = checked_file(base, 'evidence/' + core_name)
    documents = {}
    def read(name):
        if name not in references:
            raise ValueError('Record references an undeclared artifact')
        if name not in documents:
            documents[name] = json.loads(references[name].read_bytes())
        return documents[name]
    selected = index['selectedRecords']
    for record in selected:
        row = pointer(read(record['source']), record['jsonPointer'])
        if not isinstance(row, dict) or row.get('Id', row.get('ID')) != record['nativeItemId']:
            raise ValueError('Selected record identity mismatch')
        if any(row.get(key) != value for key, value in record['keys'].items()):
            raise ValueError('Selected record key mismatch')
    counts = {}
    core_rows = {}
    for label in ('coreCase', 'workflowCohort'):
        group = index[label]
        nodes = group['nodes']
        identities = set()
        for node in nodes:
            identity = (node['kind'], node['key'])
            if identity in identities:
                raise ValueError('Duplicate cohort node')
            identities.add(identity)
            for side in ('live', 'recovery'):
                source = group.get(side + 'Readback', group.get('readback'))
                row = pointer(read(source), node[side + 'Pointer'])
                if (not isinstance(row, dict) or row.get(node['keyField']) != node['key']
                        or row.get('Id', row.get('ID')) != node[side + 'ItemId']):
                    raise ValueError('Cohort record pointer mismatch')
                if label == 'coreCase':
                    core_rows[(side, node['kind'], node['key'])] = row
        counts[label] = len(nodes)
    edges = index['coreCase']['edges']
    edge_ids = set()
    for edge in edges:
        identity = (edge['side'], edge['sourceKind'], edge['sourceKey'], edge['field'],
                    edge['targetKind'], edge['targetKey'])
        if identity in edge_ids or edge['side'] not in ('live', 'recovery'):
            raise ValueError('Duplicate or invalid core edge')
        edge_ids.add(identity)
        source = core_rows.get((edge['side'], edge['sourceKind'], edge['sourceKey']))
        target = core_rows.get((edge['side'], edge['targetKind'], edge['targetKey']))
        if source is None or target is None or source.get(edge['field']) != edge['targetKey']:
            raise ValueError('Core relationship does not resolve')
    representations = index['checkedFileRepresentations']
    roles = set()
    for representation in representations:
        role, sha = representation['role'], representation['sha256']
        if not role or role in roles:
            raise ValueError('Duplicate or missing representation role')
        roles.add(role)
        row = pointer(read(representation['source']), representation['jsonPointer'])
        file = row.get('file', {})
        blob = declared.get('bytes/' + sha + '.bin')
        if (file.get('UniqueId') != representation['fileUniqueId']
                or file.get('UIVersionLabel') != representation['nativeVersion']
                or row.get('sha256') != sha or row.get('bytes') != representation['bytes']
                or not blob or blob.get('sha256') != sha or blob.get('bytes') != representation['bytes']):
            raise ValueError('File representation or packaged blob mismatch')
    return {'artifactReferences': len(references), 'selectedRecords': len(selected),
            'coreNodes': counts['coreCase'], 'workflowNodes': counts['workflowCohort'], 'coreEdges': len(edges),
            'fileRepresentations': len(representations),
            'limitations': ['Selected declared core edges only; does not establish all relationships or live currentness.']}


def verify_workflow_lookups(root):
    """Check captured rows, lookup schemas and target rows, not only a summary."""
    ext = root / 'reconstruction-package-extension-v10'
    manifest = json.loads(checked_file(ext, 'extension-manifest.json').read_bytes())
    name = 'workflow-lookup-evidence-v2-20261029.json'
    if not any(entry.get('path') == name for entry in manifest['files']):
        raise ValueError('Lookup evidence is not manifest-bound')
    evidence = json.loads(checked_file(ext, name).read_bytes())
    if evidence.get('nativeWrites') != 0 or evidence.get('nulls') != []:
        raise ValueError('Lookup capture includes unresolved populated keys')
    links = {
        'ReviewContextLink': ('contexts', 'ReviewContextKey', 'ReviewContextKey'),
        'AssessmentLink': ('assessments', 'AssessmentKey', 'AssessmentKey'),
        'RequirementLink': ('requirements', 'RequirementKey', 'RequirementKey'),
        'ExpectationVersionLink': ('expectations', 'ExpectationVersionKey', 'ExpectationVersionKey'),
        'RequestLink': ('requests', 'RequestKey', 'RequestKey'),
        'MappingLink': ('mappings', 'MappingKey', 'MappingKey'),
        'EvidenceVersionLink': ('versions', 'EvidenceVersionKey', 'EvidenceVersionKey'),
        'ObservationEvidenceLink': ('versions', 'ObsEvidenceVersionKey', 'EvidenceVersionKey'),
        'BaselineEvidenceLink': ('versions', 'BaseEvidenceVersionKey', 'EvidenceVersionKey'),
        'FollowUpEvidenceLink': ('versions', 'FollowUpEvidenceVersionKey', 'EvidenceVersionKey'),
        'TargetScopeMappingLink': ('mappings', 'TargetScopeMappingKey', 'MappingKey'),
        'SourceEvidenceVersionLink': ('versions', 'SourceEvidenceVersionKey', 'EvidenceVersionKey'),
        'DecisionLink': ('decisions', 'DecisionKey', 'DecisionKey')}
    group_keys = {'requests': 'RequestKey', 'events': 'EventKey', 'narratives': 'NarrativeVersionKey',
                  'improvement': 'ImprovementCaseKey', 'decisions': 'DecisionKey', 'decisionEvents': 'DecisionEventKey'}
    group_fields = {
        'requests': {'AssessmentLink', 'ExpectationVersionLink', 'RequirementLink', 'ReviewContextLink'},
        'events': {'EvidenceVersionLink', 'MappingLink', 'RequestLink'},
        'narratives': {'AssessmentLink', 'RequirementLink', 'ReviewContextLink'},
        'improvement': {'AssessmentLink', 'BaselineEvidenceLink', 'FollowUpEvidenceLink',
                        'ObservationEvidenceLink', 'RequirementLink', 'ReviewContextLink', 'TargetScopeMappingLink'},
        'decisions': {'ReviewContextLink', 'SourceEvidenceVersionLink'},
        'decisionEvents': {'DecisionLink'}}
    supports = {}
    for item in evidence['support']:
        identity = (item['side'], item['group'], item['key'])
        if (identity in supports or item['side'] not in ('live', 'recovery') or item['group'] not in group_keys
                or item['row'].get(group_keys[item['group']]) != item['key']):
            raise ValueError('Duplicate or invalid selected workflow row')
        supports[identity] = item
    expected = {}
    for item in supports.values():
        fields = item['fields']
        names = [field['InternalName'] for field in fields]
        if len(names) != len(set(names)) or set(names) != group_fields[item['group']]:
            raise ValueError('Missing, duplicate or unrecognized lookup schema')
        for field in fields:
            name = field['InternalName']
            target_kind, source_key, target_key = links[name]
            if source_key not in item['row'] or name + 'Id' not in item['row']:
                raise ValueError('Lookup field or source key absent from captured row')
            value, item_id = item['row'].get(source_key), item['row'].get(name + 'Id')
            if (field.get('TypeAsString') != 'Lookup' or field.get('LookupField') != target_key
                    or not isinstance(field.get('LookupList'), str) or not field['LookupList'].strip('{}')):
                raise ValueError('Lookup schema mismatch')
            if value in (None, '') and item_id is None:
                continue
            if not isinstance(value, str) or not value or type(item_id) is not int or item_id < 1:
                raise ValueError('Lookup key or item ID missing')
            identity = (item['side'], item['group'], item['key'], name)
            expected[identity] = (target_kind, value, item_id, field.get('LookupList', '').strip('{}').lower(), target_key)
    checks = {}
    for check in evidence['checks']:
        key = (check['side'], check['group'], check['key'], check['field'])
        if key in checks:
            raise ValueError('Duplicate lookup check')
        checks[key] = check
    if set(checks) != set(expected):
        raise ValueError('Lookup check coverage mismatch')
    target_rows = {}
    for target in evidence['targetSnapshots']:
        identity = (target['side'], target['kind'], target['listId'].strip('{}').lower(), target['itemId'], target['targetKeyField'])
        if identity in target_rows:
            raise ValueError('Duplicate target snapshot')
        target_rows[identity] = target['row']
    for key, (kind, value, item_id, list_id, field) in expected.items():
        check = checks[key]
        if (check.get('targetKind'), check.get('targetKey'), check.get('itemId')) != (kind, value, item_id):
            raise ValueError('Lookup summary disagrees with source row')
        target = target_rows.get((key[0], kind, list_id, item_id, field))
        if not target or target.get('Id') != item_id or target.get(field) != value:
            raise ValueError('Lookup target does not resolve')
    summaries = evidence['summary']
    summary_keys = [(item['side'], item['group']) for item in summaries]
    if len(summary_keys) != len(set(summary_keys)):
        raise ValueError('Duplicate list summary')
    for summary in summaries:
        count = sum(1 for item in supports.values() if item['side'] == summary['side'] and item['group'] == summary['group'])
        if count != summary['selected'] or summary['pages'] < 1 or summary['selected'] > summary['listCount']:
            raise ValueError('Selected workflow count mismatch')
    if set((side, group) for side, group, _ in supports) != set(summary_keys):
        raise ValueError('Workflow summary coverage mismatch')
    return {'selectedRows': len(supports), 'resolvedLookups': len(expected), 'targetSnapshots': len(target_rows),
            'limitations': ['Sequential captured reads; not all workflow types or current native state are covered.']}


def verify_requirement_corpus(root):
    """Compare retained expected keys and source fields with both captured lists."""
    base = root / 'reconstruction-package-v1'
    ext = root / 'reconstruction-package-extension-v11'
    extension = json.loads(checked_file(ext, 'extension-manifest.json').read_bytes())
    expected_name = 'expected-node-manifest-v1.json'
    if not any(entry.get('path') == expected_name for entry in extension['files']):
        raise ValueError('Expected requirement manifest is not bound')
    expected = json.loads(checked_file(ext, expected_name).read_bytes())
    index = json.loads(checked_file(root / 'reconstruction-package-extension-v1', 'selected-reconstruction-index-v4.json').read_bytes())
    base_manifest = json.loads(checked_file(base, 'package-manifest.json').read_bytes())
    path = 'evidence/' + index['requirementSnapshot']
    if not any(entry.get('path') == path for entry in base_manifest['files']):
        raise ValueError('Requirement snapshot is not bound')
    captured_path = checked_file(base, path)
    current_ext = root / 'reconstruction-package-extension-v12'
    if current_ext.exists():
        current_name = 'corpus-capture-link-current-20261029.json'
        current_manifest = json.loads(checked_file(current_ext, 'extension-manifest.json').read_bytes())
        if not any(entry.get('path') == current_name for entry in current_manifest['files']):
            raise ValueError('Current requirement snapshot is not bound')
        captured_path = checked_file(current_ext, current_name)
    postflight_ext = root / 'reconstruction-package-extension-v14'
    if postflight_ext.exists():
        postflight_name = 'corpus-capture-link-postflight-20261029.json'
        postflight_manifest = json.loads(checked_file(postflight_ext, 'extension-manifest.json').read_bytes())
        if not any(entry.get('path') == postflight_name for entry in postflight_manifest['files']):
            raise ValueError('Postflight requirement snapshot is not bound')
        captured_path = checked_file(postflight_ext, postflight_name)
    captured = json.loads(captured_path.read_bytes())
    nodes = expected['expectedNodes']
    keys = [node.get('RequirementKey') for node in nodes]
    if (not keys or any(not isinstance(key, str) or not key for key in keys)
            or len(keys) != len(set(keys)) or len(keys) != index['expectedRequirementKeys']
            or len(keys) != captured['expectedKeys']):
        raise ValueError('Expected requirement key accounting mismatch')
    if expected['edition']['CaptureKey'] != index['captureIdentity'] or any(node.get('CaptureKey') != index['captureIdentity'] for node in nodes):
        raise ValueError('Expected capture identity mismatch')
    expected_by_key = {node['RequirementKey']: node for node in nodes}
    roots = 0
    for node in nodes:
        parent = node.get('ParentRequirementKey')
        if not parent:
            roots += 1
        seen = {node['RequirementKey']}
        while parent:
            if parent in seen or parent not in expected_by_key:
                raise ValueError('Missing or cyclic requirement parent')
            seen.add(parent)
            parent = expected_by_key[parent].get('ParentRequirementKey')
    fields = ('RequirementKey', 'FrameworkKey', 'RequirementCode', 'RequirementKind', 'ParentRequirementKey',
              'PublisherCode', 'RequirementNodeKind', 'PublicationKey', 'EditionKey', 'CaptureKey',
              'SourceSHA256', 'SourceURL', 'SourceLocator')
    rows_by_side = {}
    for side in ('source', 'recovery'):
        snapshot = captured['snapshots'][side]
        rows = snapshot['inventory']['rows']
        if snapshot['inventory']['pages'] < 1 or not snapshot['metadata'].get('EnableVersioning'):
            raise ValueError('Invalid requirement snapshot metadata')
        by_key = {row.get('RequirementKey'): row for row in rows}
        if len(by_key) != len(rows) or set(by_key) != set(keys):
            raise ValueError('Captured requirement keys mismatch')
        for node in nodes:
            row = by_key[node['RequirementKey']]
            if any(field not in node or field not in row or row[field] != node[field] for field in fields):
                raise ValueError('Requirement source field mismatch')
        rows_by_side[side] = by_key
    expected_url = expected['edition']['nativeCaptureURL']
    expected_sha = expected['edition']['SourceSHA256']
    expected_host = urlsplit(expected_url)
    if expected_host.scheme != 'https' or not expected_host.netloc or expected_host.fragment:
        raise ValueError('Invalid expected native capture URL')
    copy_bases, source_links, copy_links = set(), 0, 0
    for key in keys:
        source, recovery = rows_by_side['source'][key], rows_by_side['recovery'][key]
        if any(field not in source or field not in recovery or source[field] != recovery[field]
               for field in ('Title', 'RequirementText')):
            raise ValueError('Requirement human-visible field mismatch')
        source_url = (source.get('SourceCaptureLink') or {}).get('Url')
        recovery_url = (recovery.get('SourceCaptureLink') or {}).get('Url')
        copy_url = (recovery.get('RecoveryCopyURI') or {}).get('Url')
        if not all(isinstance(url, str) and url for url in (source_url, recovery_url, copy_url)):
            raise ValueError('Missing capture link')
        source_base, source_fragment = urldefrag(source_url)
        recovery_base, recovery_fragment = urldefrag(recovery_url)
        copy = urlsplit(copy_url)
        if (source_base != expected_url or not re.fullmatch(r'page=[1-9][0-9]*', source_fragment)
                or source_fragment != recovery_fragment or copy.scheme != 'https' or copy.netloc != expected_host.netloc
                or copy.fragment or copy_url == expected_url or recovery.get('SourceCaptureSHA256') != expected_sha
                or not recovery.get('SourceFileVersion')):
            raise ValueError('Capture identity, page or recovery copy mismatch')
        copy_bases.add(copy_url)
        if recovery_base == copy_url:
            copy_links += 1
        elif recovery_base == expected_url:
            source_links += 1
        else:
            raise ValueError('Unrecognized recovery capture target')
    if len(copy_bases) != 1:
        raise ValueError('Recovery copy identity is inconsistent')
    if postflight_ext.exists() and (source_links != 0 or copy_links != len(keys)):
        raise ValueError('Postflight recovery capture links do not all target the isolated copy')
    file_evidence = None
    file_ext = root / 'reconstruction-package-extension-v15'
    if file_ext.exists():
        name = 'capture-source-copy-owner-readback-20261029.json'
        file_manifest = json.loads(checked_file(file_ext, 'extension-manifest.json').read_bytes())
        if not any(entry.get('path') == name for entry in file_manifest['files']):
            raise ValueError('Owner capture file evidence is not bound')
        readback = json.loads(checked_file(file_ext, name).read_bytes())
        files = {item['side']: item for item in readback['results']}
        if len(readback['results']) != 2 or set(files) != {'source', 'recovery'} or readback.get('nativeWrites') != 0:
            raise ValueError('Capture file readback cardinality mismatch')
        source_file, recovery_file = files['source'], files['recovery']
        if (source_file['id'].lower() != expected['edition']['fileUniqueId'].lower()
                or source_file['url'] != expected_url or recovery_file['url'] != next(iter(copy_bases))
                or any(f['sha256'] != expected_sha or f['bytes'] != expected['edition']['sourceBytes']
                       or f.get('terminalPageReached') is not True or f.get('pages', 0) < 1
                       for f in files.values())):
            raise ValueError('Capture file identity, bytes or pagination mismatch')
        prior_versions = {item['VersionLabel'] for item in source_file['versions']}
        if expected['edition']['nativeFileVersion'] not in prior_versions | {source_file['currentNativeVersion']}:
            raise ValueError('Pinned native source version is absent')
        if any(rows_by_side['recovery'][key]['SourceFileVersion'] != source_file['currentNativeVersion'] for key in keys):
            raise ValueError('Recovery source-version assertion differs from file readback')
        file_evidence = {'sourceCurrentNativeVersion': source_file['currentNativeVersion'],
                         'pinnedSourceNativeVersion': expected['edition']['nativeFileVersion'],
                         'recoveryNativeVersion': recovery_file['currentNativeVersion'],
                         'sha256': expected_sha, 'bytes': source_file['bytes']}
    return {'expectedKeys': len(keys), 'sourceKeys': len(rows_by_side['source']),
            'recoveryKeys': len(rows_by_side['recovery']),
            'rootRequirements': roots, 'resolvedParentLinks': len(keys) - roots,
            'populatedSummaries': sum(bool(rows_by_side['source'][key]['RequirementText']) for key in keys),
            'recoveryLinksToCopy': copy_links, 'recoveryLinksToOriginal': source_links,
            'captureFiles': file_evidence,
            'limitations': ['Retained expected manifest is not independent source-completeness proof.',
                            'Captured list observations are non-atomic; URL representations and native history are separate.']}


def verify_narrative_citations(root):
    """Reconcile selected narrative citations without changing original provenance."""
    def bound(ext, name):
        directory = root / f'reconstruction-package-extension-v{ext}'
        manifest = json.loads(checked_file(directory, 'extension-manifest.json').read_bytes())
        if not any(entry.get('path') == name for entry in manifest['files']):
            raise ValueError('Narrative input is not manifest-bound')
        return json.loads(checked_file(directory, name).read_bytes())
    lookup = bound(10, 'workflow-lookup-evidence-v2-20261029.json')
    expected = bound(11, 'expected-node-manifest-v1.json')
    corpus = bound(14, 'corpus-capture-link-postflight-20261029.json')
    file_data = bound(15, 'capture-source-copy-owner-readback-20261029.json')
    identity = bound(16, 'narrative-citation-source-native-20261029.json')
    index = bound(1, 'selected-reconstruction-index-v4.json')
    edition = expected['edition']
    if (identity.get('nativeWrites') != 0 or identity.get('fileUniqueId') != edition['fileUniqueId']
            or identity.get('expectedCaptureKey') != edition['CaptureKey']
            or identity.get('expectedSourceSha256') != edition['SourceSHA256']
            or type(identity.get('itemId')) is not int or identity['itemId'] < 1):
        raise ValueError('Narrative source capture identity mismatch')
    source_file = [row for row in file_data['results'] if row['side'] == 'source']
    if len(source_file) != 1 or source_file[0]['id'] != identity['fileUniqueId'] or source_file[0]['sha256'] != edition['SourceSHA256']:
        raise ValueError('Narrative source bytes do not match identity')
    rows = {}
    for item in lookup['support']:
        if item['group'] == 'narratives':
            key = (item['side'], item['key'])
            if key in rows:
                raise ValueError('Duplicate narrative version')
            rows[key] = item['row']
    live_keys = {key for side, key in rows if side == 'live'}
    recovery_keys = {key for side, key in rows if side == 'recovery'}
    if not live_keys or live_keys != recovery_keys or len(rows) != 2 * len(live_keys):
        raise ValueError('Narrative version coverage mismatch')
    cohort = index['workflowCohort']
    base = root / 'reconstruction-package-v1'
    documents = {side: json.loads(checked_file(base, 'evidence/' + cohort[side + 'Readback']).read_bytes())
                 for side in ('live', 'recovery')}
    nodes = {}
    for node in cohort['nodes']:
        if node['kind'] in ('mappings', 'versions'):
            for side in ('live', 'recovery'):
                ident = (side, node['kind'], node['key'])
                if ident in nodes:
                    raise ValueError('Duplicate citation target node')
                nodes[ident] = pointer(documents[side], node[side + 'Pointer'])
    requirements = {side: {r['RequirementKey']: r for r in corpus['snapshots'][side]['inventory']['rows']}
                    for side in ('source', 'recovery')}
    citation_count = 0
    for key in live_keys:
        live, restored = rows[('live', key)], rows[('recovery', key)]
        if live.get('CitationsJSON') != restored.get('CitationsJSON'):
            raise ValueError('Original citation JSON changed in recovery')
        citations = json.loads(live['CitationsJSON'])
        if not isinstance(citations, list) or len(citations) != 2 or {c.get('kind') for c in citations} != {'requirement-source', 'synthetic-evidence'}:
            raise ValueError('Unsupported selected narrative citations')
        source_citation = next(c for c in citations if c['kind'] == 'requirement-source')
        evidence_citation = next(c for c in citations if c['kind'] == 'synthetic-evidence')
        if (source_citation.get('fileUniqueId') != identity['fileUniqueId'] or source_citation.get('itemId') != identity['itemId']
                or source_citation.get('captureKey') != edition['CaptureKey'] or source_citation.get('editionKey') != edition['EditionKey']):
            raise ValueError('Requirement citation provenance mismatch')
        for side in ('live', 'recovery'):
            narrative = rows[(side, key)]
            req = requirements['source' if side == 'live' else 'recovery'].get(source_citation.get('requirementKey'))
            if (not req or narrative.get('RequirementKey') != source_citation['requirementKey']
                    or req.get('CaptureKey') != source_citation['captureKey'] or req.get('EditionKey') != source_citation['editionKey']):
                raise ValueError('Requirement citation target mismatch')
            page = re.search(r'PDF page (\d+)', source_citation.get('locator') or '')
            req_page = re.search(r'PDF page (\d+)', req.get('SourceLocator') or '')
            if not page or not req_page or page.group(1) != req_page.group(1):
                raise ValueError('Requirement citation page mismatch')
            mapping = nodes.get((side, 'mappings', evidence_citation.get('mappingKey')))
            version = nodes.get((side, 'versions', evidence_citation.get('evidenceVersionKey')))
            if (not mapping or not version or mapping.get('RequirementKey') != source_citation['requirementKey']
                    or mapping.get('EvidenceVersionKey') != evidence_citation['evidenceVersionKey']
                    or version.get('OData__x0053_HA256') != evidence_citation.get('sha256')):
                raise ValueError('Evidence citation mapping or version mismatch')
        sha = evidence_citation['sha256']
        blob = checked_file(base, 'bytes/' + sha + '.bin')
        if digest(blob) != sha:
            raise ValueError('Evidence citation blob mismatch')
        locator = re.fullmatch(r'Fixture lines (\d+)[–-](\d+)', evidence_citation.get('locator') or '')
        if not locator or not (1 <= int(locator.group(1)) <= int(locator.group(2)) <= len(blob.read_text().splitlines())):
            raise ValueError('Evidence citation locator outside captured file')
        citation_count += len(citations)
    return {'narrativeVersionsPerSide': len(live_keys), 'citationsPerSide': citation_count,
            'originalCitationJsonPreserved': True,
            'limitations': ['Captured source and file metadata are sequential owner reads.',
                            'Checks selected citation targets and locator bounds, not substantive evidence sufficiency.']}


def verify_decision_contracts(root):
    """Reconcile selected fictional decision, condition and change source contracts."""
    ext = root / 'reconstruction-package-extension-v17'
    manifest = json.loads(checked_file(ext, 'extension-manifest.json').read_bytes())
    names = ('condition-source-native-readback-20261029.json', 'condition-source-file-readback-20261029.json')
    if not set(names) <= {entry['path'] for entry in manifest['files']}:
        raise ValueError('Decision evidence is not manifest-bound')
    native_raw = checked_file(ext, names[0]).read_bytes()
    native = json.loads(native_raw)
    source = json.loads(checked_file(ext, names[1]).read_bytes())
    if (native.get('nativeWrites') != 0 or native.get('readOnly') is not True or native.get('identityVerified') is not True
            or native.get('siteAdminVerified') is not True or source.get('nativeWrites') != 0
            or source.get('inputSha256') != hashlib.sha256(native_raw).hexdigest()):
        raise ValueError('Decision source read identity or binding mismatch')
    for query in native['queries'].values():
        if query.get('terminalPageReached') is not True or query.get('pages', 0) < 1:
            raise ValueError('Incomplete decision native query')
    package = source['package']
    if package.get('fixtureOnly') is not True or package.get('submissionEnabled') is not False or package.get('notificationsEnabled') is not False:
        raise ValueError('Decision package is not an explicitly non-sending fixture')
    blob = checked_file(root / 'reconstruction-package-v1', 'bytes/' + source['sha256'] + '.bin')
    if digest(blob) != source['sha256'] or blob.stat().st_size != source['byteCount'] or json.loads(blob.read_bytes()).get('package') != package:
        raise ValueError('Decision source package bytes mismatch')
    versions = native['queries']['versions']['rows']
    if len(versions) != 1:
        raise ValueError('Decision source evidence version cardinality')
    version = versions[0]
    parts = [part.strip() for part in version['SourceItemKey'].split(';')]
    exact = version['ExactVersion']
    if (f"fileUniqueId:{source['fileId']}" not in parts or f"file version {source['fileVersion']}" not in exact
            or f"UniqueId {source['fileId']}" not in exact or f"SHA-256 {source['sha256']}" not in exact):
        raise ValueError('Decision source native version mismatch')
    source_sets = {}
    for group, id_field in (('decisions', 'DecisionKey'), ('conditions', 'ConditionKey'), ('changes', 'ChangeKey')):
        items = package[group]
        keyed = {item.get(id_field): item for item in items}
        if not items or None in keyed or len(keyed) != len(items):
            raise ValueError('Decision package key coverage mismatch')
        source_sets[group] = keyed
    native_decisions = native['queries']['decisions']['rows']
    if {r['DecisionKey'] for r in native_decisions} != set(source_sets['decisions']) or len(native_decisions) != len(source_sets['decisions']):
        raise ValueError('Current native decision set mismatch')
    for row in native_decisions:
        details = json.loads(row['DecisionDetailsJSON'])
        if (row['ReviewContextKey'] != native['scope'] or row['SourceEvidenceVersionKey'] != version['EvidenceVersionKey']
                or row['SourceLocator'] != source_sets['decisions'][row['DecisionKey']]['SourceLocator']
                or details.get('fixtureOnly') is not True or details.get('realIssuerAuthorityVerified') is not False):
            raise ValueError('Current decision source or authority mismatch')
    native_events = native['queries']['events']['rows']
    event_keys = [row.get('DecisionEventKey') for row in native_events]
    expected_events = set(source_sets['conditions']) | set(source_sets['changes'])
    if None in event_keys or len(event_keys) != len(set(event_keys)) or set(event_keys) != expected_events:
        raise ValueError('Current native decision-event set mismatch')
    for row in native_events:
        group = {'condition': 'conditions', 'change': 'changes'}.get(row.get('EventKind'))
        key = row['DecisionEventKey']
        if not group or key not in source_sets[group]:
            raise ValueError('Current decision-event kind mismatch')
        item = source_sets[group][key]
        details = json.loads(row['EventDetailsJSON'])
        if (row.get('DecisionKey') != item.get('DecisionKey')
                or row.get('EventState') != item.get('ConditionState' if group == 'conditions' else 'SubmissionState')
                or (group == 'conditions' and row.get('ConditionKey') != key)
                or details.get('fixtureOnly') is not True or details.get('realIssuerAuthorityVerified') is not False):
            raise ValueError('Current decision-event source or authority mismatch')
    support = json.loads(checked_file(root / 'reconstruction-package-extension-v10', 'workflow-lookup-evidence-v2-20261029.json').read_bytes())['support']
    paired = {}
    for item in support:
        if item['group'] in ('decisions', 'decisionEvents'):
            identity = (item['side'], item['group'], item['key'])
            if identity in paired:
                raise ValueError('Duplicate selected decision record')
            paired[identity] = item['row']
    counts = {}
    for side in ('live', 'recovery'):
        found = {group: set() for group in source_sets}
        for (which, kind, _), row in paired.items():
            if which != side:
                continue
            contract = json.loads(row['ContractDecisionJSON' if kind == 'decisions' else 'ContractEventJSON'])
            group = 'decisions' if kind == 'decisions' else {'condition': 'conditions', 'change': 'changes'}.get(row.get('EventKind'))
            id_field = {'decisions': 'DecisionKey', 'conditions': 'ConditionKey', 'changes': 'ChangeKey'}.get(group)
            key = contract.get(id_field) if id_field else None
            if not group or key not in source_sets[group] or key in found[group] or contract != source_sets[group][key]:
                raise ValueError('Nested decision contract differs from source')
            if group != 'decisions' and (row.get('DecisionKey') != contract.get('DecisionKey') or row.get('EventState') != contract.get('ConditionState' if group == 'conditions' else 'SubmissionState')):
                raise ValueError('Decision event parent or state mismatch')
            found[group].add(key)
        if any(found[group] != set(source_sets[group]) for group in found):
            raise ValueError('Selected decision contract coverage mismatch')
        counts[side] = {group: len(found[group]) for group in found}
    return {'bySide': counts, 'sourceSha256': source['sha256'], 'fixtureOnly': True,
            'limitations': ['Captured native and source reads are sequential.', 'Fictional source is not evidence of real issuer authority or accreditation.']}


def verify_improvement_fixture(root):
    """Reconcile the selected fictional improvement graph to its source bytes."""
    base = root / 'reconstruction-package-v1'
    index = json.loads(checked_file(root / 'reconstruction-package-extension-v1', 'selected-reconstruction-index-v4.json').read_bytes())
    evidence = json.loads(checked_file(root / 'reconstruction-package-extension-v10', 'workflow-lookup-evidence-v2-20261029.json').read_bytes())
    representations = {r['role']: r for r in index['checkedFileRepresentations']}
    if not {'improvement_files', 'improvement_replica'} <= set(representations):
        raise ValueError('Improvement file representations missing')
    original, replica = representations['improvement_files'], representations['improvement_replica']
    if original['sha256'] != replica['sha256'] or original['bytes'] != replica['bytes']:
        raise ValueError('Improvement source and copy bytes differ')
    blob = checked_file(base, 'bytes/' + original['sha256'] + '.bin')
    if digest(blob) != original['sha256'] or blob.stat().st_size != original['bytes']:
        raise ValueError('Improvement source blob mismatch')
    source = json.loads(blob.read_bytes())
    if source.get('fixtureOnly') is not True or source.get('realServiceActivity') is not False or source.get('humanReviewClaimed') is not False:
        raise ValueError('Improvement source is not a bounded fictional fixture')
    selected = {}
    for item in evidence['support']:
        if item['group'] != 'improvement':
            continue
        case = json.loads(item['row']['ContractCaseJSON'])
        if case.get('fixtureOnly') is True:
            side = item['side']
            if side not in ('live', 'recovery') or side in selected:
                raise ValueError('Duplicate selected improvement fixture')
            selected[side] = (item['row'], case)
    if set(selected) != {'live', 'recovery'}:
        raise ValueError('Improvement fixture missing a namespace')
    if selected['live'][0]['ContractCaseJSON'] != selected['recovery'][0]['ContractCaseJSON']:
        raise ValueError('Recovered improvement contract changed')
    cohort = index['workflowCohort']
    evidence_key = selected['live'][0]['ObsEvidenceVersionKey']
    version_nodes = [node for node in cohort['nodes'] if node['kind'] == 'versions' and node['key'] == evidence_key]
    if len(version_nodes) != 1:
        raise ValueError('Improvement evidence version not uniquely indexed')
    versions = {}
    for side in ('live', 'recovery'):
        data = json.loads(checked_file(base, 'evidence/' + cohort[side + 'Readback']).read_bytes())
        versions[side] = pointer(data, version_nodes[0][side + 'Pointer'])
        if (versions[side].get('EvidenceVersionKey') != evidence_key
                or f"UniqueId {original['fileUniqueId']}" not in versions[side].get('ExactVersion', '')
                or f"file version {original['nativeVersion']}" not in versions[side].get('ExactVersion', '')
                or f"SHA-256 {original['sha256']}" not in versions[side].get('ExactVersion', '')):
            raise ValueError('Improvement evidence-version provenance mismatch')
    side_counts = {}
    for side, (row, case) in selected.items():
        if case.get('nativeWrites') is not False or case.get('humanReviewClaimed') is not False:
            raise ValueError('Improvement fixture boundary mismatch')
        groups = ('observations', 'findings', 'actionReferences', 'measurements', 'effectivenessJudgements')
        if any(not isinstance(case.get(group), list) for group in groups):
            raise ValueError('Improvement case sections missing')
        observations, findings, actions, measurements, judgements = (case[group] for group in groups)
        if (len(observations), len(findings), len(actions), len(measurements), len(judgements)) != (1, 1, 1, 2, 1):
            raise ValueError('Selected improvement cardinality mismatch')
        observation, finding, action, judgement = observations[0], findings[0], actions[0], judgements[0]
        if (observation['ObservationKey'] != row['ObservationKey'] or observation['EvidenceVersionKey'] != row['ObsEvidenceVersionKey']
                or finding['FindingKey'] != row['FindingKey'] or finding['ObservationKey'] != observation['ObservationKey']
                or any(finding[field] != row[field] for field in ('ReviewContextKey', 'AssessmentKey', 'RequirementKey', 'ScopeKey'))
                or action['ActionReferenceKey'] != row['ActionReferenceKey'] or action['FindingKey'] != finding['FindingKey']
                or judgement['JudgementKey'] != row['JudgementKey'] or judgement['FindingKey'] != finding['FindingKey']
                or judgement['ActionReferenceKey'] != action['ActionReferenceKey']):
            raise ValueError('Improvement graph reference mismatch')
        source_action = source['action']
        action_fields = ('recordKey', 'recordVersion', 'recordType', 'ownerRoleRef', 'state', 'dueDate', 'completedAt')
        if (action.get('SourceLocator') != 'JSON Pointer /action'
                or any(source_action.get(name) != action.get(name[0].upper() + name[1:]) for name in action_fields)
                or action.get('RecordType') != 'FictionalAction' or action.get('State') != 'completed'
                or action.get('CompletionEvidenceVersionKey') != observation['EvidenceVersionKey']):
            raise ValueError('Improvement action source mismatch')
        if (f"UniqueId {original['fileUniqueId']}" not in action.get('SourceDocumentExactVersion', '')
                or f"file version {original['nativeVersion']}" not in action.get('SourceDocumentExactVersion', '')
                or f"SHA-256 {original['sha256']}" not in action.get('SourceDocumentExactVersion', '')
                or action.get('SourceDocumentURI') != versions['live'].get('SourceURI')):
            raise ValueError('Improvement action file identity mismatch')
        measured = {}
        for measurement in measurements:
            phase = measurement.get('Phase')
            source_name = {'baseline': 'baseline', 'follow-up': 'followUp'}.get(phase)
            if not source_name or phase in measured:
                raise ValueError('Improvement measurement phase mismatch')
            source_period = source[source_name]
            records = source_period['records']
            if (not isinstance(records, list) or any(type(r.get('fieldPresent')) is not bool for r in records)
                    or measurement['Numerator'] != sum(r['fieldPresent'] for r in records)
                    or measurement['Denominator'] != len(records)
                    or measurement['PeriodStart'] != source_period['start'] or measurement['PeriodEnd'] != source_period['end']
                    or measurement['SourceLocator'] != f'JSON Pointer /{source_name}/records'
                    or measurement['FindingKey'] != finding['FindingKey']
                    or measurement['ActionReferenceKey'] != action['ActionReferenceKey']
                    or measurement['IndicatorVersionKey'] != row['IndicatorVersionKey']
                    or measurement['EvidenceVersionKey'] != observation['EvidenceVersionKey']):
                raise ValueError('Improvement measurement source mismatch')
            measured[phase] = measurement['MeasurementKey']
        if (len(set(measured.values())) != 2 or set(json.loads(row['MeasurementKeysJSON'])) != set(measured.values())
                or judgement.get('BaselineMeasurementKey') != measured['baseline']
                or judgement.get('FollowUpMeasurementKey') != measured['follow-up']
                or judgement.get('Outcome') != 'unknown' or judgement.get('JudgementState') != 'not-performed'
                or judgement.get('ActorIdentityRef') is not None or judgement.get('JudgedAt') is not None
                or row.get('EffectivenessOutcome') != 'unknown'):
            raise ValueError('Improvement outcome or measurement linkage mismatch')
        side_counts[side] = {'observations': 1, 'findings': 1, 'actions': 1, 'measurements': 2, 'judgements': 1}
    return {'bySide': side_counts, 'sourceSha256': original['sha256'], 'fixtureOnly': True,
            'limitations': ['Counts are constructed test data, not service performance or effectiveness.',
                            'Checks one selected improvement fixture; other improvement cases remain separate.']}


def verify_improvement_technical_case(root):
    """Check the earlier synthetic observation/finding without inferring effectiveness."""
    base = root / 'reconstruction-package-v1'
    index = json.loads(checked_file(root / 'reconstruction-package-extension-v1', 'selected-reconstruction-index-v4.json').read_bytes())
    lookup = json.loads(checked_file(root / 'reconstruction-package-extension-v10', 'workflow-lookup-evidence-v2-20261029.json').read_bytes())
    corpus = json.loads(checked_file(root / 'reconstruction-package-extension-v14', 'corpus-capture-link-postflight-20261029.json').read_bytes())
    selected = {}
    for item in lookup['support']:
        if item['group'] == 'improvement':
            case = json.loads(item['row']['ContractCaseJSON'])
            if case.get('syntheticFixture') is True:
                if item['side'] not in ('live', 'recovery') or item['side'] in selected:
                    raise ValueError('Duplicate technical improvement case')
                selected[item['side']] = (item['row'], case)
    if set(selected) != {'live', 'recovery'} or selected['live'][0]['ContractCaseJSON'] != selected['recovery'][0]['ContractCaseJSON']:
        raise ValueError('Technical improvement case coverage or provenance mismatch')
    cohort = index['workflowCohort']
    counts = {}
    for side, (row, case) in selected.items():
        if (case.get('readinessScoreComputed') is not False or case.get('assessmentOutcomeInferred') is not False
                or case.get('actionReference') is not None or case.get('measurements') != []
                or json.loads(row['MeasurementKeysJSON']) != [] or row.get('EffectivenessOutcome') != 'unknown'):
            raise ValueError('Technical case infers outcome or has unexpected action/measurements')
        for nested, field in (('reviewContextKey', 'ReviewContextKey'), ('assessmentKey', 'AssessmentKey'),
                              ('requirementKey', 'RequirementKey'), ('scopeKey', 'ScopeKey')):
            if case.get(nested) != row.get(field):
                raise ValueError('Technical case scope mismatch')
        obs, finding, judgement = case['observation'], case['finding'], case['effectivenessJudgement']
        if (obs.get('ObservationKey') != row.get('ObservationKey') or obs.get('EvidenceVersionKey') != row.get('ObsEvidenceVersionKey')
                or obs.get('AccessClass') != 'synthetic-non-personal' or finding.get('FindingKey') != row.get('FindingKey')
                or finding.get('ObservationKey') != obs.get('ObservationKey')
                or any(finding.get(field) != row.get(field) for field in ('AssessmentKey', 'RequirementKey', 'ScopeKey'))
                or judgement.get('JudgementKey') != row.get('JudgementKey') or judgement.get('Outcome') != 'unknown'
                or judgement.get('ActorIdentityRef') is not None or judgement.get('JudgedAt') is not None):
            raise ValueError('Technical improvement graph or unknown-state mismatch')
        nodes = [node for node in cohort['nodes'] if node['kind'] == 'versions' and node['key'] == obs['EvidenceVersionKey']]
        if len(nodes) != 1:
            raise ValueError('Technical evidence version missing')
        document = json.loads(checked_file(base, 'evidence/' + cohort[side + 'Readback']).read_bytes())
        version = pointer(document, nodes[0][side + 'Pointer'])
        sha = version.get('OData__x0053_HA256')
        if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha):
            raise ValueError('Technical evidence hash missing')
        blob = checked_file(base, 'bytes/' + sha + '.bin')
        if digest(blob) != sha:
            raise ValueError('Technical evidence bytes mismatch')
        locators = finding.get('EvidenceLocators')
        if not isinstance(locators, list) or len(locators) != 2:
            raise ValueError('Technical evidence locators missing')
        lines = re.fullmatch(r'Synthetic fixture lines (\d+)[–-](\d+)', locators[0])
        page = re.match(r'Requirement register source capture page (\d+)', locators[1])
        req_side = 'source' if side == 'live' else 'recovery'
        matching = [r for r in corpus['snapshots'][req_side]['inventory']['rows'] if r.get('RequirementKey') == row['RequirementKey']]
        req_page = re.search(r'PDF page (\d+)', matching[0].get('SourceLocator') or '') if len(matching) == 1 else None
        if (not lines or not 1 <= int(lines.group(1)) <= int(lines.group(2)) <= len(blob.read_text().splitlines())
                or not page or not req_page or page.group(1) != req_page.group(1)):
            raise ValueError('Technical case locator mismatch')
        counts[side] = {'observations': 1, 'findings': 1, 'actions': 0, 'measurements': 0, 'outcome': 'unknown'}
    return {'bySide': counts, 'syntheticFixture': True,
            'limitations': ['Locator bounds and captured references are checked, not substantive effectiveness.',
                            'This is one selected case in sequential owner captures.']}


def verify_request_chains(root):
    """Check selected request/response histories without inferring human review."""
    def timestamp(value):
        try:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError('Invalid request event timestamp') from exc
        if parsed.tzinfo is None:
            raise ValueError('Request event timestamp lacks timezone')
        return parsed
    evidence = json.loads(checked_file(root / 'reconstruction-package-extension-v10', 'workflow-lookup-evidence-v2-20261029.json').read_bytes())
    index = json.loads(checked_file(root / 'reconstruction-package-extension-v1', 'selected-reconstruction-index-v4.json').read_bytes())
    cohort = index['workflowCohort']
    mapping_rows = {}
    for side in ('live', 'recovery'):
        doc = json.loads(checked_file(root / 'reconstruction-package-v1', 'evidence/' + cohort[side + 'Readback']).read_bytes())
        for node in cohort['nodes']:
            if node['kind'] == 'mappings':
                mapping_rows[(side, node['key'])] = pointer(doc, node[side + 'Pointer'])
    records = {}
    for item in evidence['support']:
        if item['group'] in ('requests', 'events'):
            key = (item['side'], item['group'], item['key'])
            if key in records:
                raise ValueError('Duplicate request workflow record')
            records[key] = item['row']
    for group in ('requests', 'events'):
        live = {key for side, kind, key in records if side == 'live' and kind == group}
        recovery = {key for side, kind, key in records if side == 'recovery' and kind == group}
        if not live or live != recovery:
            raise ValueError('Request workflow namespace coverage mismatch')
        for key in live:
            a, b = records[('live', group, key)], records[('recovery', group, key)]
            fields = ('RequestState', 'ClosureDetailsJSON') if group == 'requests' else ('EventPayloadJSON', 'ContractEventJSON')
            if any(a.get(field) != b.get(field) for field in fields):
                raise ValueError('Request workflow content changed in recovery')
    counts = {}
    for side in ('live', 'recovery'):
        requests = {key: value for (s, group, key), value in records.items() if s == side and group == 'requests'}
        events = {key: value for (s, group, key), value in records.items() if s == side and group == 'events'}
        by_request = {key: [] for key in requests}
        for key, row in events.items():
            if row.get('EventKey') != key or row.get('RequestKey') not in requests:
                raise ValueError('Request event parent mismatch')
            payload = json.loads(row['EventPayloadJSON'])
            if row.get('ContractEventJSON') and json.loads(row['ContractEventJSON']) != payload:
                raise ValueError('Request event contract mismatch')
            if payload.get('RequestKey') != row['RequestKey']:
                raise ValueError('Request payload parent mismatch')
            if row.get('EventKind') == 'Assignment':
                if not isinstance(payload.get('AssignmentEventKey'), str) or not payload['AssignmentEventKey']:
                    raise ValueError('Assignment payload identity missing')
            elif row.get('EventKind') == 'Response':
                if (not isinstance(payload.get('ResponseEventKey'), str) or not payload['ResponseEventKey']
                        or payload.get('State') != row.get('ResponseState')
                        or timestamp(payload.get('OccurredAt')) != timestamp(row.get('OccurredAt'))
                        or payload.get('EvidenceVersionKey') != row.get('EvidenceVersionKey')
                        or payload.get('MappingKey') != row.get('MappingKey')):
                    raise ValueError('Response event payload mismatch')
                mapping = mapping_rows.get((side, row['MappingKey']))
                request = requests[row['RequestKey']]
                if (not mapping or mapping.get('EvidenceVersionKey') != row['EvidenceVersionKey']
                        or mapping.get('RequirementKey') != request.get('RequirementKey')
                        or mapping.get('ReviewContextKey') != request.get('ReviewContextKey')):
                    raise ValueError('Response mapping or evidence reference mismatch')
                if payload['State'] in ('reviewed', 'accepted') and (payload.get('TechnicalOnly') is not True or payload.get('HumanReviewClaimed') is not False):
                    raise ValueError('Technical response must not imply human review')
            else:
                raise ValueError('Unsupported request event kind')
            by_request[row['RequestKey']].append((row, payload))
        for key, request in requests.items():
            current = by_request[key]
            if not any(row['EventKind'] == 'Assignment' for row, _ in current):
                raise ValueError('Request assignment missing')
            responses = [(row, payload) for row, payload in current if row['EventKind'] == 'Response']
            responses.sort(key=lambda pair: timestamp(pair[1]['OccurredAt']))
            states = [payload['State'] for _, payload in responses]
            if states not in ([], ['received'], ['received', 'reviewed'], ['received', 'reviewed', 'accepted']):
                raise ValueError('Unsupported response state progression')
            previous = None
            last_time = None
            payload_keys = set()
            for row, payload in responses:
                observed = timestamp(payload['OccurredAt'])
                if (payload['ResponseEventKey'] in payload_keys or payload.get('PreviousResponseEventKey') != previous
                        or (last_time is not None and observed <= last_time)):
                    raise ValueError('Response history chain mismatch')
                payload_keys.add(payload['ResponseEventKey'])
                previous = payload['ResponseEventKey']
                last_time = observed
            state = request.get('RequestState')
            if state == 'completed':
                closure = json.loads(request['ClosureDetailsJSON'])
                if (not responses or responses[-1][1]['State'] != 'accepted' or closure.get('TechnicalOnly') is not True
                        or closure.get('HumanReviewClaimed') is not False
                        or closure.get('CompletionDecisionRef') != responses[-1][1].get('DecisionRef')
                        or timestamp(closure.get('CompletedAt')) < timestamp(responses[-1][1]['OccurredAt'])):
                    raise ValueError('Technical request closure mismatch')
            elif state != 'open' or request.get('ClosureDetailsJSON') or (states and states[-1] == 'accepted'):
                raise ValueError('Unexpected request state or closure')
        counts[side] = {'requests': len(requests), 'events': len(events), 'responses': sum(row['EventKind'] == 'Response' for row in events.values())}
    return {'bySide': counts, 'limitations': ['Technical workflow states do not establish human review or evidence sufficiency.',
                                              'Sequential selected-case captures; no organization-wide workflow assertion.']}


def verify_legacy_request_histories(root):
    """Compare selected legacy event creation/current fields and lookup history."""
    ext = root / 'reconstruction-package-extension-v18'
    manifest = json.loads(checked_file(ext, 'extension-manifest.json').read_bytes())
    names = ('legacy-request-event-history-readback-20261029.json', 'query-response-pilot-reconciliation-v3.json')
    if not set(names) <= {entry['path'] for entry in manifest['files']}:
        raise ValueError('Legacy event evidence is not manifest-bound')
    history = json.loads(checked_file(ext, names[0]).read_bytes())
    baseline = json.loads(checked_file(ext, names[1]).read_bytes())
    lookup = json.loads(checked_file(root / 'reconstruction-package-extension-v10', 'workflow-lookup-evidence-v2-20261029.json').read_bytes())
    if history.get('nativeWrites') != 0 or baseline.get('readOnly') is not True:
        raise ValueError('Legacy event readback qualification mismatch')
    fields = ('EventKey', 'RequestKey', 'EventKind', 'ResponseState', 'MappingKey', 'EvidenceVersionKey',
              'SourceLocator', 'ActorRoleRef', 'OccurredAt', 'PreviousEventKey', 'EventPayloadJSON',
              'AssignmentEventKey', 'ResponseEventKey', 'OwnerIdentityRef', 'DelegateRoleRefsJSON',
              'EffectiveAt', 'Reason', 'ActorIdentityRef', 'DecisionRef', 'Rationale', 'ContractEventJSON')
    old = {row.get('EventKey'): row for row in baseline['events']}
    if len(old) != 2 or len(baseline['events']) != 2 or None in old:
        raise ValueError('Legacy event baseline key mismatch')
    selected = {(item['side'], item['key']): item['row'] for item in lookup['support']
                if item['group'] == 'events' and item['key'] in old}
    if set(selected) != {(side, key) for side in ('live', 'recovery') for key in old}:
        raise ValueError('Legacy event selected coverage mismatch')
    seen = set()
    for item in history['records']:
        identity = (item.get('side'), item.get('key'))
        if identity not in selected or identity in seen or item.get('kind') != 'event' or item.get('pages', 0) < 1:
            raise ValueError('Legacy event history identity mismatch')
        seen.add(identity)
        versions = item['history']
        labels = [v.get('VersionLabel') for v in versions]
        creation = [v for v in versions if v.get('VersionLabel') == '1.0']
        current = [v for v in versions if v.get('IsCurrentVersion') is True]
        if len(labels) != len(set(labels)) or len(creation) != 1 or len(current) != 1:
            raise ValueError('Legacy event version cardinality mismatch')
        baseline_row, current_row = old[item['key']], selected[identity]
        if current[0].get('VersionLabel') != current_row.get('OData__UIVersionString'):
            raise ValueError('Legacy event current version changed')
        for field in fields:
            if (field not in baseline_row or field not in creation[0] or creation[0][field] != baseline_row[field]
                    or field not in current_row or field not in current[0] or current[0][field] != current_row[field]):
                raise ValueError('Legacy event business history mismatch')
        for field in ('RequestLink', 'MappingLink', 'EvidenceVersionLink'):
            value = current[0].get(field)
            if current_row.get(field + 'Id') != (value.get('LookupId') if isinstance(value, dict) else None):
                raise ValueError('Legacy event current lookup mismatch')
    if seen != set(selected):
        raise ValueError('Legacy event history coverage mismatch')
    return {'eventKeys': len(old), 'histories': len(seen), 'businessFieldsCompared': len(fields),
            'limitations': ['Creation business fields and current lookup IDs only; system metadata and complete historical field equality are not inferred.',
                            'Captured baseline and native histories are sequential.']}


def verify_legacy_request_record_history(root):
    """Compare the older request's creation and current fields in both lists."""
    ext = root / 'reconstruction-package-extension-v19'
    name = 'legacy-request-history-readback-20261029.json'
    manifest = json.loads(checked_file(ext, 'extension-manifest.json').read_bytes())
    if not any(entry.get('path') == name for entry in manifest['files']):
        raise ValueError('Legacy request history is not manifest-bound')
    history = json.loads(checked_file(ext, name).read_bytes())
    baseline = json.loads(checked_file(root / 'reconstruction-package-extension-v18', 'query-response-pilot-reconciliation-v3.json').read_bytes())
    lookup = json.loads(checked_file(root / 'reconstruction-package-extension-v10', 'workflow-lookup-evidence-v2-20261029.json').read_bytes())
    if history.get('nativeWrites') != 0 or baseline.get('readOnly') is not True:
        raise ValueError('Legacy request readback qualification mismatch')
    original = baseline['request']
    key = original.get('RequestKey')
    selected = {item['side']: item['row'] for item in lookup['support'] if item['group'] == 'requests' and item['key'] == key}
    if not key or set(selected) != {'live', 'recovery'}:
        raise ValueError('Legacy request selected coverage mismatch')
    fields = ('Title', 'RequestKey', 'ReviewContextKey', 'AssessmentKey', 'ExpectationVersionKey', 'RequirementKey',
              'ScopeKey', 'DueDate', 'RequestState', 'RequestDedupeKey', 'ResponsibleRoleRef', 'RequestedAt',
              'RequestFingerprint', 'DelegateRoleRefsJSON', 'ClosureDetailsJSON')
    seen = set()
    for item in history['records']:
        side = item.get('side')
        if side not in selected or side in seen or item.get('key') != key or item.get('kind') != 'request' or item.get('pages', 0) < 1:
            raise ValueError('Legacy request history identity mismatch')
        seen.add(side)
        versions = item['history']
        labels = [v.get('VersionLabel') for v in versions]
        creation = [v for v in versions if v.get('VersionLabel') == '1.0']
        current = [v for v in versions if v.get('IsCurrentVersion') is True]
        if len(labels) != len(set(labels)) or len(creation) != 1 or len(current) != 1:
            raise ValueError('Legacy request version cardinality mismatch')
        current_row = selected[side]
        if current[0].get('VersionLabel') != current_row.get('OData__UIVersionString'):
            raise ValueError('Legacy request current version changed')
        for field in fields:
            if (field not in original or field not in creation[0] or creation[0][field] != original[field]
                    or field not in current_row or field not in current[0] or current[0][field] != current_row[field]):
                raise ValueError('Legacy request business history mismatch')
        for field in ('ReviewContextLink', 'AssessmentLink', 'RequirementLink', 'ExpectationVersionLink'):
            value = current[0].get(field)
            if current_row.get(field + 'Id') != (value.get('LookupId') if isinstance(value, dict) else None):
                raise ValueError('Legacy request current lookup mismatch')
    if seen != set(selected):
        raise ValueError('Legacy request history coverage mismatch')
    return {'requests': 1, 'histories': len(seen), 'businessFieldsCompared': len(fields),
            'limitations': ['Creation business fields and current lookup IDs only; system history and human review are not inferred.',
                            'Captured baseline and native histories are sequential.']}


def verify_custody_navigation(root):
    """Reconcile selected custody parent lookups and indexed reverse rows."""
    ext = root / 'reconstruction-package-extension-v20'
    name = 'responsibility-navigation-evidence-20261029.json'
    manifest = json.loads(checked_file(ext, 'extension-manifest.json').read_bytes())
    if not any(entry.get('path') == name for entry in manifest['files']):
        raise ValueError('Custody navigation evidence is not bound')
    data = json.loads(checked_file(ext, name).read_bytes())
    if data.get('nativeWrites') != 0 or set(data['output']) != {'source', 'destination'}:
        raise ValueError('Custody navigation namespace coverage mismatch')
    index = json.loads(checked_file(root / 'reconstruction-package-extension-v1', 'selected-reconstruction-index-v4.json').read_bytes())
    corpus = json.loads(checked_file(root / 'reconstruction-package-extension-v14', 'corpus-capture-link-postflight-20261029.json').read_bytes())
    fields = ('ResponsibilityKey', 'ExpectationVersionKey', 'RequirementKey', 'ScopeKey', 'ResponsibilityType',
              'AssignmentState', 'IdentityRef', 'IdentityKind', 'UnknownReason', 'EffectiveFrom', 'EffectiveTo',
              'SourceItemKey', 'SourceVersion', 'SourceLocator', 'AuthorIdentityRef')
    a, b = data['output']['source']['actual'], data['output']['destination']['actual']
    if any(field not in a or field not in b or a[field] != b[field] for field in fields):
        raise ValueError('Custody business fields differ between namespaces')
    if not a.get('ResponsibilityKey') or not a.get('ExpectationVersionKey') or not a.get('RequirementKey'):
        raise ValueError('Custody stable identity missing')
    for side in ('source', 'destination'):
        result = data['output'][side]
        actual, resolved = result['actual'], result['resolved']
        if set(resolved) != {'expectation', 'requirement'}:
            raise ValueError('Custody parent coverage mismatch')
        for kind, key_field, link_field, schema_name in (
                ('expectation', 'ExpectationVersionKey', 'ExpectationVersionLinkId', 'ExpectationVersionLink'),
                ('requirement', 'RequirementKey', 'RequirementLinkId', 'RequirementLink')):
            detail = resolved[kind]
            parent, schema = detail['parent'], detail['schema']
            uri = parent.get('__metadata', {}).get('uri', '')
            match = re.search(r"/Lists\(guid'([0-9a-f-]{36})'\)/Items\((\d+)\)$", uri, re.I)
            if (not match or schema.get('InternalName') != schema_name or schema.get('TypeAsString') != 'Lookup'
                    or schema.get('LookupField') != key_field or schema.get('LookupList', '').strip('{}').lower() != match.group(1).lower()
                    or parent.get('Id') != int(match.group(2)) or actual.get(link_field) != parent.get('Id')
                    or parent.get(key_field) != actual.get(key_field)):
                raise ValueError('Custody parent lookup mismatch')
        expectation = resolved['expectation']['parent']
        requirement = resolved['requirement']['parent']
        if (expectation.get('RequirementKey') != actual['RequirementKey'] or expectation.get('ScopeKey') != actual['ScopeKey']
                or requirement.get('CaptureKey') != index['captureIdentity']):
            raise ValueError('Custody scope or capture mismatch')
        rows = corpus['snapshots']['source' if side == 'source' else 'recovery']['inventory']['rows']
        candidates = [row for row in rows if row.get('RequirementKey') == actual['RequirementKey']]
        if len(candidates) != 1 or candidates[0].get('Id') != requirement['Id']:
            raise ValueError('Custody requirement not in captured corpus')
        reverse = result['reverse']
        if (result['indexField'].get('InternalName') != 'ExpectationVersionKey' or result['indexField'].get('Indexed') is not True
                or reverse.get('pages', 0) < 1 or len(reverse['rows']) != 1
                or reverse['rows'][0].get('ResponsibilityKey') != actual['ResponsibilityKey']
                or reverse['rows'][0].get('Id') != actual['Id']):
            raise ValueError('Custody indexed reverse navigation mismatch')
    return {'namespaces': 2, 'forwardParentLinks': 4, 'indexedReverseQueries': 2,
            'limitations': ['Selected owner-only technical custody; no clinical or organizational delegation inferred.',
                            'Sequential native observations, not an independent restore.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--verify-selected-index', action='store_true')
    parser.add_argument('--verify-workflow-lookups', action='store_true')
    parser.add_argument('--verify-requirement-corpus', action='store_true')
    parser.add_argument('--verify-narrative-citations', action='store_true')
    parser.add_argument('--verify-decision-contracts', action='store_true')
    parser.add_argument('--verify-improvement-fixture', action='store_true')
    parser.add_argument('--verify-improvement-technical-case', action='store_true')
    parser.add_argument('--verify-request-chains', action='store_true')
    parser.add_argument('--verify-legacy-request-histories', action='store_true')
    parser.add_argument('--verify-legacy-request-record', action='store_true')
    parser.add_argument('--verify-custody-navigation', action='store_true')
    args = parser.parse_args()
    result = audit(args.root, args.expected_head)
    if args.verify_selected_index:
        result['selectedIndex'] = verify_selected_index(args.root)
    if args.verify_workflow_lookups:
        result['workflowLookups'] = verify_workflow_lookups(args.root)
    if args.verify_requirement_corpus:
        result['requirementCorpus'] = verify_requirement_corpus(args.root)
    if args.verify_narrative_citations:
        if not (args.verify_selected_index and args.verify_workflow_lookups and args.verify_requirement_corpus):
            parser.error('Narrative citation checks require selected-index, workflow-lookup and requirement-corpus checks')
        result['narrativeCitations'] = verify_narrative_citations(args.root)
    if args.verify_decision_contracts:
        if not args.verify_workflow_lookups:
            parser.error('Decision contract checks require workflow-lookup checks')
        result['decisionContracts'] = verify_decision_contracts(args.root)
    if args.verify_improvement_fixture:
        if not (args.verify_selected_index and args.verify_workflow_lookups):
            parser.error('Improvement checks require selected-index and workflow-lookup checks')
        result['improvementFixture'] = verify_improvement_fixture(args.root)
    if args.verify_improvement_technical_case:
        if not (args.verify_selected_index and args.verify_workflow_lookups and args.verify_requirement_corpus):
            parser.error('Technical improvement checks require index, lookup and requirement-corpus checks')
        result['improvementTechnicalCase'] = verify_improvement_technical_case(args.root)
    if args.verify_request_chains:
        if not (args.verify_selected_index and args.verify_workflow_lookups):
            parser.error('Request-chain checks require selected-index and workflow-lookup checks')
        result['requestChains'] = verify_request_chains(args.root)
    if args.verify_legacy_request_histories:
        if not (args.verify_selected_index and args.verify_workflow_lookups and args.verify_request_chains):
            parser.error('Legacy history checks require selected-index, workflow-lookup and request-chain checks')
        result['legacyRequestHistories'] = verify_legacy_request_histories(args.root)
    if args.verify_legacy_request_record:
        if not args.verify_legacy_request_histories:
            parser.error('Legacy request record check requires legacy request history checks')
        result['legacyRequestRecord'] = verify_legacy_request_record_history(args.root)
    if args.verify_custody_navigation:
        if not (args.verify_selected_index and args.verify_requirement_corpus):
            parser.error('Custody checks require selected-index and requirement-corpus checks')
        result['custodyNavigation'] = verify_custody_navigation(args.root)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
