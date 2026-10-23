"""Validate a complete native standards snapshot before creating review context.

Uses the existing schema/history, standards and relationship validators. Offline,
read-only; validates recorded structure, not clinical evidence or actor authority.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from scripts.ppg_standards_recovery import prepare
from scripts.ppg_standards_contract import validate
from scripts.ppg_relationship_context import review_context
from scripts.ppg_source_standards import digest


def evidence(value):
    if not value:
        return {}
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        # Older manually recorded evidence may be a plain reference. Preserve it;
        # it is not a separately recorded review decision.
        return {'sourceEvidenceRef': value}
    return result if isinstance(result, dict) else {'sourceEvidenceRef': value}


def decision_ref(value):
    ref = value.get('reviewEvidenceRef')
    return ref if isinstance(ref, str) and ref.strip() else None


def inspection_matches(value, sha):
    hashes = [value[k] for k in ['derivedPackageSha256', 'subjectInspectionSHA256'] if k in value]
    return bool(hashes) and all(v == sha for v in hashes)


def validate_snapshot(source_bytes, document_uids):
    plan = prepare(source_bytes)
    if (not isinstance(document_uids, list) or len(document_uids) != len(set(document_uids))
            or any(not isinstance(v, str) or not v.strip() for v in document_uids)):
        raise ValueError('Complete unique document identity inventory required')
    known = set(document_uids)
    registers = {}
    provenance = {}
    for reg in plan['registers']:
        rows = []
        for item in reg['records']:
            row = item['versions'][-1]['record']
            # The recovery validator checks field schemas and value types; also
            # require actual values to belong to their native choice vocabulary.
            for field in reg['definition']['fields']:
                if field['type'] == 'Choice':
                    choices = [e.text for e in ET.fromstring(field['schemaXml']).findall('.//CHOICE')]
                    if row[field['name']] not in choices:
                        raise ValueError('Unknown native choice value')
            rows.append(row)
            provenance[reg['slot'] + ':' + item['keyValue']] = dict(slot=reg['slot'],
                sourceListId=reg['sourceList']['Id'], **item['sourcePlatform'])
        registers[reg['slot']] = rows
    frameworks = [dict(frameworkEditionId=r['FrameworkKey'], status=r['EditionStatus'].lower())
                  for r in registers['frameworks']]
    requirements = [dict(requirementId=r['RequirementKey'], frameworkEditionId=r['FrameworkKey'],
                         parentRequirementId=r['ParentRequirementKey']) for r in registers['requirements']]
    mappings, crosswalks, relationships, unresolved = [], [], [], []

    def document_ref(uid, key, state):
        if uid not in known:
            if state in {'reviewed', 'accepted'}:
                raise ValueError('Accepted/reviewed record has an unresolved document identity')
            unresolved.append(dict(recordKey=key, documentUID=uid,
                                   code='unresolved_document_identity'))

    for r in registers['mappings']:
        e = evidence(r['EvidenceRef'])
        if e.get('establishesCompliance', False) is not False:
            raise ValueError('Mapping evidence cannot claim compliance certification')
        current = e.get('currentObligation', False)
        if type(current) is not bool:
            raise ValueError('Current-obligation assertion must be Boolean')
        state = r['MappingState'].lower()
        document_ref(r['DocumentUID'], r['MappingKey'], state)
        mappings.append(dict(mappingId=r['MappingKey'], documentUID=r['DocumentUID'],
            documentVersion=r['DocumentVersion'], requirementId=r['RequirementKey'],
            rationale=r['Rationale'], status=state, establishesCompliance=False,
            currentObligation=current, reviewEvidenceRef=decision_ref(e)))
    for r in registers['crosswalks']:
        e = evidence(r['EvidenceRef'])
        state = r['ReviewState'].lower()
        if state == 'reviewed' and not decision_ref(e):
            raise ValueError('Reviewed crosswalk needs separately recorded decision evidence')
        crosswalks.append(dict(crosswalkId=r['CrosswalkKey'],
            fromRequirementId=r['FromRequirementKey'], toRequirementId=r['ToRequirementKey'],
            correspondence=r['Correspondence'].lower(), rationale=r['Rationale']))
    for r in registers['relationships']:
        e = evidence(r['EvidenceRef'])
        state = r['ReviewState'].lower()
        if state == 'accepted' and not decision_ref(e):
            raise ValueError('Accepted relationship needs separately recorded decision evidence')
        for uid in [r['FromDocumentUID'], r['ToDocumentUID']]:
            document_ref(uid, r['RelationshipKey'], state)
        relationships.append(dict(relationshipId=r['RelationshipKey'],
            fromDocumentUID=r['FromDocumentUID'], toDocumentUID=r['ToDocumentUID'],
            fromVersion=r['FromVersion'], toVersion=r['ToVersion'],
            type=r['RelationshipType'], status=state, rationale=r['Rationale'],
            evidenceRef=r['EvidenceRef']))
    validate(frameworks, requirements, mappings, crosswalks)
    # Also checks endpoint versions even if no relationships touch a requested PPG.
    review_context(relationships, '__validation_only__', '__no_document__')
    source = json.loads(source_bytes)
    return dict(schemaVersion=1, kind='native_standards_snapshot_validation',
        sourceSnapshotSha256=hashlib.sha256(source_bytes).hexdigest(),
        registersSha256=digest(source['registers']),
        documentIdentityInventorySha256=digest(sorted(document_uids)),
        capturedAtUtc=source.get('capturedAtUtc'),
        summary=dict(recordCount=plan['recordCount'], availableVersionCount=plan['versionCount'],
            registerCounts={k: len(v) for k, v in registers.items()},
            reviewedMappings=sum(r['status'] == 'reviewed' for r in mappings),
            acceptedRelationships=sum(r['status'] == 'accepted' for r in relationships),
            unresolvedDocumentReferences=len(unresolved)),
        registers=copy.deepcopy(registers), mappings=mappings, relationships=relationships,
        provenance=provenance, unresolved=unresolved,
        nativeWrites=0, evidenceReferencesVerified=False, actorAuthorityVerified=False,
        establishesCompliance=False, notificationsEnabled=False)


def context(source_bytes, document_uids, document_uid, document_version, inspection_bytes=None):
    validated = validate_snapshot(source_bytes, document_uids)
    if document_uid not in document_uids or not isinstance(document_version, str) or not document_version.strip():
        raise ValueError('Known subject identity and explicit document version required')
    result = review_context(validated['relationships'], document_uid, document_version)
    result.update(kind='validated_native_standards_context',
        sourceSnapshotSha256=validated['sourceSnapshotSha256'],
        registersSha256=validated['registersSha256'],
        documentIdentityInventorySha256=validated['documentIdentityInventorySha256'],
        nativeValidationSummary=validated['summary'],
        mappings=[copy.deepcopy(r) for r in validated['registers']['mappings']
                  if r['DocumentUID'] == document_uid and r['DocumentVersion'] == document_version],
        otherVersionMappings=[copy.deepcopy(r) for r in validated['registers']['mappings']
                  if r['DocumentUID'] == document_uid and r['DocumentVersion'] != document_version],
        frameworks=validated['registers']['frameworks'], requirements=validated['registers']['requirements'],
        crosswalks=validated['registers']['crosswalks'], nativeProvenance=validated['provenance'],
        unresolvedDocumentReferences=validated['unresolved'],
        evidenceReferencesVerified=False, actorAuthorityVerified=False, nativeWrites=0,
        policyApproved=False, publicationAuthorised=False, notificationsEnabled=False,
        limitations=['Read-only snapshot validation; direct native saves remain unconstrained.',
            'Decision references are presence checks, not authentication, authority or clinical appraisal.',
            'Source snapshot validity does not establish current applicability or full normative coverage.',
            'Different native version labels do not by themselves prove different editions.',
            'Unknown external document identities need a verified identity record before acceptance.'])
    if inspection_bytes is not None:
        sha = hashlib.sha256(inspection_bytes).hexdigest()
        # Group only proposals with an explicit subject-inspection hash. Never
        # rewrite a native version label or use this grouping for accepted graphs.
        result['inspectionBoundProposals'] = dict(inspectionSha256=sha,
            mappings=[copy.deepcopy(r) for r in validated['registers']['mappings']
                if r['DocumentUID'] == document_uid and r['MappingState'] == 'Proposed'
                and evidence(r['EvidenceRef']).get('inspectedSourceSha256') == sha],
            relationships=[copy.deepcopy(r) for r in validated['registers']['relationships']
                if r['FromDocumentUID'] == document_uid and r['ReviewState'] == 'Proposed'
                and inspection_matches(evidence(r['EvidenceRef']), sha)],
            versionLabelsMerged=False, appliesToRequestedEdition=False,
            establishesAuthority=False, humanDecision=None)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['snapshot', 'catalogue', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--document-uid', required=True)
    parser.add_argument('--document-version', required=True)
    parser.add_argument('--inspection-file', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Output exists; preserve prior context and human edits')
    page = json.loads(args.catalogue.read_text())
    from scripts.ppg_role_recovery import complete
    result = context(args.snapshot.read_bytes(), [r['DocumentUID'] for r in complete(page)],
                     args.document_uid, args.document_version,
                     args.inspection_file.read_bytes() if args.inspection_file else None)
    with args.output.open('x') as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(outputCreated=True, nativeWrites=0,
                         validationSummary=result['nativeValidationSummary'])))
