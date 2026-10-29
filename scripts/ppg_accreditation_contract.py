# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
"""Minimal portable standards/evidence checks; no native writes or decisions.

Reuses the existing hierarchy contract. Native field bindings and source captures
remain owned by their existing producers. Presence checks never prove authority.
"""
from scripts.ppg_standards_contract import unique, validate
from scripts.ppg_source_standards import digest

REQUIREMENT_KINDS = {
    'standard', 'criterion', 'action-group', 'action', 'subclause',
    'qualifier', 'note', 'quality-statement', 'nested-list-item',
}


def required(row, *names):
    if not isinstance(row, dict):
        raise ValueError('Record must be an object')
    for name in names:
        if not isinstance(row.get(name), str) or not row[name].strip():
            raise ValueError('Missing text '+name)


def validate_source_bindings(graph, catalogue):
    """Reconcile supplied EC identities; this does not authenticate bytes/authority."""
    if not isinstance(catalogue, dict) or not isinstance(catalogue.get('records'), list):
        raise ValueError('Catalogue records must be a list')
    for record in catalogue['records']:
        required(record, 'key', 'kind')
    records = unique(catalogue['records'], 'key')
    frameworks = {row['FrameworkKey']: row for row in graph['frameworks']}
    for requirement in graph['requirements']:
        source = requirement['source']
        selected = []
        for field, kind in [('PublicationKey', 'Publication'),
                            ('EditionKey', 'Edition'), ('CaptureKey', 'Capture')]:
            row = records.get(source[field])
            if row is None or row['kind'] != kind:
                raise ValueError('Missing or wrong-kind catalogue '+field)
            selected.append(row)
        publication, edition, capture = selected
        if (publication.get('publicationKey') != publication['key']
                or publication.get('editionKey') is not None
                or edition.get('publicationKey') != publication['key']
                or edition.get('editionKey') != edition['key']
                or capture.get('publicationKey') != publication['key']
                or capture.get('editionKey') != edition['key']
                or frameworks[requirement['FrameworkKey']]['EditionKey'] != edition['key']):
            raise ValueError('Catalogue publication/edition/capture endpoints differ')
        for row in [edition, capture]:
            keys = row.get('frameworkKeys')
            if (not isinstance(keys, list)
                    or any(not isinstance(key, str) or not key.strip() for key in keys)
                    or len(keys) != len(set(keys))
                    or requirement['FrameworkKey'] not in keys):
                raise ValueError('Explicit catalogue framework membership required')
        if (not isinstance(capture.get('data'), dict)
                or capture['data'].get('sha256') != source['sha256']):
            raise ValueError('Catalogue source hash differs')
    return len(graph['requirements'])


def validate_shared_configuration(contract, vocabularies):
    """Check the compatible v2 harness configuration without promoting v1 producers."""
    if (not isinstance(contract, dict) or type(contract.get('contractVersion')) is not int
            or contract['contractVersion'] != 2
            or type(contract.get('graphContractVersion')) is not int
            or contract['graphContractVersion'] != 1):
        raise ValueError('Shared configuration v2 and graph contract v1 required')
    kinds = contract.get('requirementKinds')
    if (not isinstance(kinds, list) or any(not isinstance(kind, str) for kind in kinds)
            or len(kinds) != len(set(kinds)) or set(kinds) != REQUIREMENT_KINDS):
        raise ValueError('Configured requirement kinds differ from the harness')
    rules = contract.get('promotionRules')
    if not isinstance(rules, dict) or any(rules.get(key) is not False for key in
            ['automaticAcceptance', 'crosswalkTransfersAcceptance', 'scopeInheritance',
             'nativeWritesImplemented', 'emailEnabled', 'premiumConnectors']):
        raise ValueError('Shared configuration cannot authorize automatic or native promotion')
    rating = contract.get('ratingVocabulary')
    if not isinstance(rating, dict) or rating.get('universalScore') is not False:
        raise ValueError('Shared configuration cannot derive a universal rating score')
    if (not isinstance(vocabularies, dict)
            or type(vocabularies.get('schemaVersion')) is not int
            or vocabularies['schemaVersion'] != 1):
        raise ValueError('Scheme vocabulary configuration v1 required')
    collections = [('authorities', 'authorityKey'), ('schemes', 'schemeKey')]
    indexed = {}
    for collection, key in collections:
        rows = vocabularies.get(collection)
        if not isinstance(rows, list) or not rows:
            raise ValueError('Vocabulary '+collection+' must be a nonempty list')
        for row in rows:
            required(row, key)
        indexed[collection] = unique(rows, key)
    rows = vocabularies.get('ratingVocabularies')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Vocabulary ratingVocabularies must be a nonempty list')
    indexed['ratingVocabularies'] = {}
    for row in rows:
        required(row, 'vocabularyKey', 'vocabularyVersion')
        key = (row['vocabularyKey'], row['vocabularyVersion'])
        if key in indexed['ratingVocabularies']:
            raise ValueError('Duplicate vocabulary identity/version')
        indexed['ratingVocabularies'][key] = row
    for scheme in indexed['schemes'].values():
        required(scheme, 'schemeAuthorityKey', 'assessmentDecisionAuthorityKey')
        keys = scheme.get('frameworkKeys')
        if (not isinstance(keys, list) or not keys
                or any(not isinstance(key, str) or not key.strip() for key in keys)
                or len(keys) != len(set(keys))):
            raise ValueError('Explicit scheme framework membership required')
        if (scheme['schemeAuthorityKey'] not in indexed['authorities']
                or scheme['assessmentDecisionAuthorityKey'] not in indexed['authorities']
                or scheme['schemeAuthorityKey'] == scheme['assessmentDecisionAuthorityKey']):
            raise ValueError('Distinct source and external decision authority roles required')
    for vocabulary in indexed['ratingVocabularies'].values():
        required(vocabulary, 'vocabularyVersion', 'schemeKey', 'frameworkKey', 'use')
        scheme = indexed['schemes'].get(vocabulary['schemeKey'])
        if (scheme is None or vocabulary['frameworkKey'] not in scheme.get('frameworkKeys', [])
                or vocabulary['use'] != 'external-accrediting-assessor-rating-only'):
            raise ValueError('External rating scheme/framework binding required')
        values = vocabulary.get('values')
        if (not isinstance(values, list) or not values
                or any(not isinstance(value, str) or not value.strip() for value in values)
                or len(values) != len(set(values))):
            raise ValueError('Distinct publisher rating values required')
        source = vocabulary.get('source')
        required(source, 'publicationKey', 'captureKey', 'sha256', 'locator')
        sha = source['sha256']
        if len(sha) != 64 or any(char not in '0123456789abcdef' for char in sha):
            raise ValueError('Invalid vocabulary source hash')
        if source.get('editionKey') is None:
            required(source, 'editionState')
        else:
            required(source, 'editionKey')
    internal = vocabularies.get('internalReviewStates')
    if (not isinstance(internal, dict) or internal.get('externalRatingCopy') is not False
            or internal.get('ratingVocabularyKey') is not None
            or internal.get('applicability') != ['Unknown', 'Applicable', 'Not applicable']
            or internal.get('outcome') != ['Unknown', 'Human-recorded']):
        raise ValueError('Internal review states must remain distinct from external ratings')
    expected = {'ratingDoesNotImplyAccreditationDecision', 'evidencePresenceDoesNotAssignRating',
                'mappingDoesNotAssignRating', 'noUniversalScore', 'unknownRemainsExplicit'}
    invariants = vocabularies.get('invariants')
    if (not isinstance(invariants, dict) or set(invariants) != expected
            or any(value is not True for value in invariants.values())):
        raise ValueError('Explicit non-inference vocabulary invariants required')
    return dict(configurationVersion=2, graphContractVersion=1,
                configurationSha256=digest(contract), vocabularySha256=digest(vocabularies),
                sourceAuthorityVerified=False, nativeWrites=0)


def validate_graph(graph, *, catalogue=None):
    if not isinstance(graph, dict):
        raise ValueError('Accreditation graph must be an object')
    if type(graph.get('contractVersion')) is not int or graph['contractVersion'] != 1:
        raise ValueError('Unsupported accreditation contract')
    collection_keys = {
        'frameworks': 'FrameworkKey',
        'requirements': 'RequirementKey',
        'contexts': 'ReviewContextKey',
        'scopes': 'ScopeKey',
        'evidenceVersions': 'EvidenceVersionKey',
        'mappings': 'MappingKey',
        'assessments': 'AssessmentKey',
    }
    for collection, key in collection_keys.items():
        rows = graph.get(collection)
        if not isinstance(rows, list):
            raise ValueError(collection+' must be a list')
        for row in rows:
            required(row, key)
    crosswalks = graph.get('crosswalks')
    if not isinstance(crosswalks, list):
        raise ValueError('crosswalks must be a list')
    for row in crosswalks:
        required(row, 'CrosswalkKey', 'FromRequirementKey', 'ToRequirementKey',
                 'correspondence', 'rationale')
    frameworks = unique(graph['frameworks'], 'FrameworkKey')
    requirements = unique(graph['requirements'], 'RequirementKey')
    contexts = unique(graph['contexts'], 'ReviewContextKey')
    scopes = unique(graph['scopes'], 'ScopeKey')
    versions = unique(graph['evidenceVersions'], 'EvidenceVersionKey')
    mappings = unique(graph['mappings'], 'MappingKey')
    assessments = unique(graph['assessments'], 'AssessmentKey')
    validate([dict(frameworkEditionId=k, status=r['status']) for k, r in frameworks.items()],
        [dict(requirementId=k, frameworkEditionId=r['FrameworkKey'],
              parentRequirementId=r.get('ParentRequirementKey')) for k, r in requirements.items()], [],
        [dict(crosswalkId=r['CrosswalkKey'], fromRequirementId=r['FromRequirementKey'],
              toRequirementId=r['ToRequirementKey'], correspondence=r['correspondence'],
              rationale=r['rationale']) for r in crosswalks])
    codes = set()
    for row in requirements.values():
        required(row, 'FrameworkKey', 'kind')
        if row['kind'] not in REQUIREMENT_KINDS:
            raise ValueError('Unsupported requirement kind')
        code = row.get('publisherCode')
        if code is not None:
            required(row, 'publisherCode')
            # Publisher clause/list labels repeat under distinct parent nodes.
            # Numbered requirements retain edition-wide code uniqueness.
            parent = (row.get('ParentRequirementKey') if row['kind'] in
                      {'subclause', 'nested-list-item'} else None)
            pair = (row['FrameworkKey'], parent, code)
            if pair in codes:
                raise ValueError('Duplicate publisher code within source scope')
            codes.add(pair)
        source = row.get('source')
        if not isinstance(source, dict):
            raise ValueError('Requirement source must be an object')
        required(source, 'PublicationKey', 'EditionKey', 'CaptureKey', 'sha256', 'locator')
        if source['EditionKey'] != frameworks[row['FrameworkKey']]['EditionKey']:
            raise ValueError('Requirement source edition mismatch')
        if len(source['sha256']) != 64 or any(c not in '0123456789abcdef' for c in source['sha256']):
            raise ValueError('Invalid source hash')
    for key, scope in scopes.items():
        trail = {key}
        parent = scope.get('ParentScopeKey')
        while parent:
            if parent not in scopes or parent in trail:
                raise ValueError('Scope parent missing or cyclic')
            trail.add(parent)
            parent = scopes[parent].get('ParentScopeKey')
    for context in contexts.values():
        required(context, 'purpose', 'period')
        scope_keys = context.get('ScopeKeys')
        framework_keys = context.get('FrameworkKeys')
        if (not isinstance(scope_keys, list) or not isinstance(framework_keys, list)
                or any(not isinstance(key, str) or not key.strip()
                       for key in scope_keys + framework_keys)
                or not scope_keys or not framework_keys
                or not set(scope_keys) <= scopes.keys()
                or not set(framework_keys) <= frameworks.keys()):
            raise ValueError('Context membership missing')
        # A core context has no mandatory accreditation cycle or award.
    for version in versions.values():
        required(version, 'EvidenceKey', 'sourceSystem', 'sourceKey', 'sourceVersion', 'accessClass')
        if version['accessClass'] not in {'fictional', 'restricted', 'ordinary'}:
            raise ValueError('Unknown access class')
    for mapping in mappings.values():
        req = requirements.get(mapping['RequirementKey'])
        context = contexts.get(mapping['ReviewContextKey'])
        if (req is None or context is None or mapping['EvidenceVersionKey'] not in versions
                or mapping['ScopeKey'] not in context['ScopeKeys']
                or req['FrameworkKey'] not in context['FrameworkKeys']):
            raise ValueError('Mapping reference or membership missing')
        required(mapping, 'rationale', 'locator', 'period')
        if mapping.get('establishesCompliance') is not False:
            raise ValueError('Mapping cannot establish compliance')
        if mapping['reviewState'] not in {'proposed', 'reviewed', 'rejected', 'superseded', 'needs-review'}:
            raise ValueError('Unknown mapping state')
        if mapping['reviewState'] != 'proposed':
            required(mapping, 'decisionRef')
    for row in crosswalks:
        if row.get('transfersAcceptance') is not False:
            raise ValueError('Crosswalk cannot transfer acceptance')
        source = requirements.get(row['FromRequirementKey'])
        target = requirements.get(row['ToRequirementKey'])
        if source is None or target is None:
            raise ValueError('Crosswalk requirement missing')
        if source['FrameworkKey'] == target['FrameworkKey']:
            raise ValueError('Crosswalk must connect different framework editions')
    for row in assessments.values():
        context = contexts.get(row['ReviewContextKey'])
        req = requirements.get(row['RequirementKey'])
        mapping_keys = row.get('MappingKeys')
        if (not isinstance(mapping_keys, list)
                or any(not isinstance(key, str) or not key.strip()
                       for key in mapping_keys)
                or len(mapping_keys) != len(set(mapping_keys))):
            raise ValueError('Assessment mapping keys must be a list of text keys')
        if (context is None or req is None or row['ScopeKey'] not in context['ScopeKeys']
                or req['FrameworkKey'] not in context['FrameworkKeys']):
            raise ValueError('Assessment membership missing')
        if row['applicability'] not in {'unknown', 'applicable', 'not-applicable'}:
            raise ValueError('Unknown applicability')
        if row['outcome'] not in {'unknown', 'human-recorded'}:
            raise ValueError('Automatic assessment outcome forbidden')
        if row['outcome'] == 'human-recorded' or row['applicability'] != 'unknown':
            required(row, 'humanDecisionRef', 'actorRef', 'decidedAt', 'rationale')
        for key in row['MappingKeys']:
            mapping = mappings.get(key)
            if mapping is None or any(mapping[k] != row[k] for k in
                    ['ReviewContextKey', 'RequirementKey', 'ScopeKey']):
                raise ValueError('Assessment mapping mismatch')
    bound = validate_source_bindings(graph, catalogue) if catalogue is not None else 0
    return dict(contractVersion=1, graphSha256=digest(graph),
        counts={k: len(graph[k]) for k in ['frameworks', 'requirements', 'scopes', 'contexts',
                                         'evidenceVersions', 'mappings', 'assessments', 'crosswalks']},
        catalogueBindingsVerified=catalogue is not None, sourceBoundRequirements=bound,
        catalogueSha256=digest(catalogue) if catalogue is not None else None,
        sourceBytesVerified=False, sourceAuthorityVerified=False,
        nativeWrites=0, humanReadiness='unmeasured', actorAuthorityVerified=False,
        accreditationDecision=None)


def change_leads(graph, evidence_key, new_version_key):
    validate_graph(graph)
    versions = {r['EvidenceVersionKey']: r for r in graph['evidenceVersions']}
    if new_version_key not in versions or versions[new_version_key]['EvidenceKey'] != evidence_key:
        raise ValueError('New version must resolve to the same evidence identity')
    return sorted({digest(dict(MappingKey=r['MappingKey'], EvidenceVersionKey=new_version_key))
        for r in graph['mappings'] if versions[r['EvidenceVersionKey']]['EvidenceKey'] == evidence_key
        and r['EvidenceVersionKey'] != new_version_key})


def freeze(graph):
    """Portable exact-record fixture snapshot; not native/file or access recovery."""
    import copy
    validation = validate_graph(graph)
    return dict(kind='accreditation_local_snapshot', graph=copy.deepcopy(graph),
                graphSha256=validation['graphSha256'], nativeRecoveryQualified=False)


def restore(snapshot, *, expected_graph_sha256=None):
    """Restore local records; an independent retained hash can pin provenance.

    The embedded checksum alone detects corruption, not a rewritten graph and
    checksum. Neither mode proves native restoration or source authority.
    """
    if not isinstance(snapshot, dict) or snapshot.get('kind') != 'accreditation_local_snapshot':
        raise ValueError('Unknown snapshot')
    if snapshot.get('nativeRecoveryQualified') is not False:
        raise ValueError('Local snapshot cannot claim native recovery')
    checksum = snapshot.get('graphSha256')
    if (not isinstance(checksum, str) or len(checksum) != 64
            or any(character not in '0123456789abcdef' for character in checksum)):
        raise ValueError('Invalid snapshot checksum')
    if expected_graph_sha256 is not None and checksum != expected_graph_sha256:
        raise ValueError('Snapshot differs from independently retained hash')
    if not isinstance(snapshot.get('graph'), dict):
        raise ValueError('Snapshot graph missing')
    if validate_graph(snapshot['graph'])['graphSha256'] != checksum:
        raise ValueError('Snapshot changed')
    import copy
    return copy.deepcopy(snapshot['graph'])


def main():
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--catalogue', type=Path,
                        help='Existing EC record export for exact source-tuple reconciliation')
    parser.add_argument('--contract-config', type=Path,
                        help='Compatible v2 harness config; requires --vocabularies')
    parser.add_argument('--vocabularies', type=Path)
    parser.add_argument('--expected-graph-sha256',
                        help='Independently retained graph hash; local record integrity only')
    args = parser.parse_args()
    if bool(args.contract_config) != bool(args.vocabularies):
        parser.error('--contract-config and --vocabularies must be supplied together')
    graph = json.loads(args.graph.read_text())
    catalogue = json.loads(args.catalogue.read_text()) if args.catalogue else None
    result = validate_graph(graph, catalogue=catalogue)
    if args.contract_config:
        result['sharedConfiguration'] = validate_shared_configuration(
            json.loads(args.contract_config.read_text()),
            json.loads(args.vocabularies.read_text()))
    snapshot = freeze(graph)
    if restore(snapshot, expected_graph_sha256=args.expected_graph_sha256) != graph:
        raise ValueError('Portable record replay differs')
    # Exclusive directory creation protects earlier outputs and human edits.
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name, data in [('validation.json', result), ('snapshot.json', snapshot)]:
        target = args.output / name
        with target.open('x') as stream:
            target.chmod(0o600)
            stream.write(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
