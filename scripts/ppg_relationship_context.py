"""Version-bound review context; proposed references never establish authority."""
import copy
import hashlib
import json
from scripts.ppg_review_intelligence import HIERARCHICAL, validate_relationships


def reference_candidates(subject_uid, leads, inventory, inspected_bytes, original_bytes):
    sha = hashlib.sha256(inspected_bytes).hexdigest()
    original_sha = hashlib.sha256(original_bytes).hexdigest()
    if inventory['sourceSha256'] != sha:
        raise ValueError('Inspection inventory/source mismatch')
    passages = {e['sourceLocator']: e['text'] for e in inventory['elements']}
    if len(passages) != len(inventory['elements']):
        raise ValueError('Ambiguous passage locator')
    records, unresolved, seen = [], [], set()
    for lead in leads:
        if (lead['suggestedType'] != 'references' or lead['derivedPackageSha256'] != sha
                or lead['sourceSha256'] != original_sha):
            raise ValueError('Unqualified reference/source')
        locator = lead['sourceLocator']
        if not lead['sourcePassage'] or lead['sourcePassage'] not in passages.get(locator, ''):
            raise ValueError('Unverified reference passage')
        if len(lead['targetCandidates']) != 1:
            unresolved.append(copy.deepcopy(lead))
            continue
        target = lead['targetCandidates'][0]
        if not target.get('sourceDocumentId') or target['documentUID'] == subject_uid:
            raise ValueError('Unusable target identity')
        key = hashlib.sha256(('\n'.join([subject_uid, sha, locator, target['documentUID'],
                                          target['sourceDocumentId'], 'references'])).encode()).hexdigest()
        if key in seen:
            raise ValueError('Duplicate reference lead')
        seen.add(key)
        records.append({'Title': 'Historical reference candidate: '+target['title'].strip(),
                        'RelationshipKey': key, 'FromDocumentUID': subject_uid,
                        'ToDocumentUID': target['documentUID'],
                        'FromVersion': 'historical-inspection:'+sha,
                        'ToVersion': 'catalogue-assertion:'+target['sourceDocumentId'],
                        'RelationshipType': 'references', 'ReviewState': 'Proposed',
                        'Rationale': 'Explicit historical reference; catalogue title identifies a retrieval candidate only. Target text/edition and current-source applicability require reconciliation.',
                        'EvidenceRef': json.dumps({'sourceSha256': lead['sourceSha256'],
                            'derivedPackageSha256': sha, 'locator': locator,
                            'quote': lead['sourcePassage'], 'targetCoverage': target['coverage'],
                            'targetTitle': target['title'], 'establishesAuthority': False,
                            'appliesToRequestedEdition': False}, ensure_ascii=False)})
    return {'records': records, 'unresolved': unresolved,
            'sourceVersion': 'historical-inspection:'+sha}


def review_context(rows, document_uid, document_version):
    """Traverse accepted hierarchy at exact endpoint versions; retain proposals apart."""
    validate_relationships(rows)
    for row in rows:
        if not row.get('fromVersion') or not row.get('toVersion'):
            raise ValueError('Relationship lacks endpoint versions')
    selected = (document_uid, document_version)
    def endpoints(row):
        return ((row['fromDocumentUID'], row['fromVersion']),
                (row['toDocumentUID'], row['toVersion']))
    direct = [copy.deepcopy(r) for r in rows if selected in endpoints(r)]
    def walk(reverse=False, types=HIERARCHICAL - {'supersedes'}):
        found, visited, pending = [], {selected}, [selected]
        while pending:
            current = pending.pop(0)
            for r in rows:
                if r['status'] != 'accepted' or r['type'] not in types:
                    continue
                start, end = endpoints(r)
                if reverse: start, end = end, start
                if start == current and end not in visited:
                    visited.add(end); pending.append(end)
                    found.append({'documentUID': end[0], 'documentVersion': end[1],
                                  'viaRelationshipId': r['relationshipId']})
        return found
    return {'documentUID': document_uid, 'documentVersion': document_version,
            'acceptedUpstream': walk(), 'acceptedDownstream': walk(True),
            'acceptedSupersedes': walk(types={'supersedes'}),
            'acceptedSupersededBy': walk(True, types={'supersedes'}),
            'directAccepted': [r for r in direct if r['status']=='accepted'],
            'directProposed': [r for r in direct if r['status']=='proposed'],
            'otherEditionLinks': [copy.deepcopy(r) for r in rows if
                document_uid in {r['fromDocumentUID'], r['toDocumentUID']} and selected not in endpoints(r)],
            'establishesCompliance': False, 'humanDecision': None}


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    candidate = commands.add_parser('candidates')
    candidate.add_argument('--subject-uid', required=True)
    for name in ['leads', 'inventory', 'inspection', 'original']:
        candidate.add_argument('--'+name, type=Path, required=True)
    context = commands.add_parser('context')
    context.add_argument('--relationships', type=Path, required=True)
    context.add_argument('--document-uid', required=True)
    context.add_argument('--document-version', required=True)
    for command in [candidate, context]: command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'candidates':
        result = reference_candidates(args.subject_uid, json.loads(args.leads.read_text())['leads'],
            json.loads(args.inventory.read_text()), args.inspection.read_bytes(), args.original.read_bytes())
    else:
        result = review_context(json.loads(args.relationships.read_text()), args.document_uid, args.document_version)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({'outputCreated': True, 'nativeWrites': 0}))
