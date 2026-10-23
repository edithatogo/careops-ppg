"""Prepare draft annotation inserts from revalidated historical passage findings."""
import hashlib
import json
from scripts.ppg_passage_findings import build


def payloads(pack, inventory, source_bytes, pack_reference):
    checked = build(pack['preparation'], inventory, source_bytes, pack['findings'])
    if pack['inspectedSourceSha256'] != checked['inspectedSourceSha256']:
        raise ValueError('Pack source binding differs')
    if not pack_reference.startswith('https://'):
        raise ValueError('Stored pack reference required')
    uid = checked['requestedSubject']['documentUID']
    sha = checked['inspectedSourceSha256']
    result = []
    for f in checked['findings']:
        key = hashlib.sha256((uid+'\n'+sha+'\n'+f['findingId']).encode()).hexdigest()
        text = '\n'.join(['ASSISTANT DRAFT — HISTORICAL INSPECTION ONLY', f['statement'],
                          'Proposed action: '+f['suggestedAction'], 'Benefit: '+f['benefit'],
                          'Effort: '+f['effort'], 'Dependencies: '+f['dependencies'],
                          'Uncertainty: '+f['uncertainty'],
                          'No human decision, current-policy deficiency or approval is established.'])
        result.append({'Title': 'Draft: '+f['findingId'], 'AnnotationKey': key,
                       'DocumentUID': uid, 'DocumentVersion': 'historical-inspection:'+sha,
                       'SectionId': 'inspection:'+sha+':'+f['citations'][0]['locator'],
                       'OriginalSuggestion': text, 'EvidenceRef': json.dumps({
                           'packReference': pack_reference, 'findingId': f['findingId'],
                           'sourceSha256': sha, 'citations': f['citations'],
                           'sectionIdentity': 'Version-specific locator, not a confirmed stable section',
                           'requiresCurrentEditionReconciliation': True}, ensure_ascii=False),
                       'ReviewState': 'Received'})
    return result


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['pack', 'inventory', 'source', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--pack-reference', required=True)
    args = parser.parse_args()
    rows = payloads(json.loads(args.pack.read_text()), json.loads(args.inventory.read_text()),
                    args.source.read_bytes(), args.pack_reference)
    with args.output.open('x') as stream:
        stream.write(json.dumps(rows, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({'draftAnnotationPayloads': len(rows), 'nativeWrites': 0}))
