"""Prepare loss-aware structured content records; preserve imported and human text."""
import argparse
import hashlib
import json
from pathlib import Path


def validate_modules(definition):
    keys = [m['key'] for m in definition['modules']]
    if len(keys) != len(set(keys)) or 'evidence.unmapped' not in keys:
        raise ValueError('Ambiguous or incomplete module definitions')
    headings = {}
    for module in definition['modules']:
        for heading in module['headings']:
            normal = ' '.join(heading.casefold().split())
            if normal in headings:
                raise ValueError('Ambiguous module heading')
            headings[normal] = module['key']
    for rule in definition.get('rules', []):
        if rule['moduleKey'] not in keys:
            raise ValueError('Unknown rule module')
        if rule['status'] in {'verified_required', 'verified_conditional'}:
            authority = rule.get('authorityEvidence', {})
            if not all(authority.get(k) for k in ['source', 'version', 'sha256']) or not rule.get('templateVerified'):
                raise ValueError('Required rule lacks verified template/authority evidence')
    return headings


def prepare(document_uid, inventory, modules, source_provenance):
    if not isinstance(document_uid, str) or not document_uid.strip():
        raise ValueError('Document identity required')
    headings = validate_modules(modules)
    elements = inventory['elements']
    ids = [e['elementId'] for e in elements]
    if not elements or len(ids) != len(set(ids)):
        raise ValueError('Missing or duplicate source elements')
    if not source_provenance.get('originalSourceSha256'):
        raise ValueError('Original source provenance required')
    source_hash = inventory['sourceSha256']
    records = []
    current = 'core.identity'
    for index, element in enumerate(elements):
        locator = element['sourceLocator']
        text = element.get('text', '')
        if locator.startswith('word/comments') or locator.startswith('word/footnotes') or locator.startswith('word/endnotes'):
            module = 'evidence.annotations'
        elif locator.startswith('word/header') or locator.startswith('word/footer'):
            module = 'evidence.layout'
        elif locator.startswith('word/document.xml'):
            current = headings.get(' '.join(text.casefold().split()), current)
            module = current
        else:
            module = 'evidence.unmapped'
        key = hashlib.sha256((document_uid+'\0'+source_hash+'\0'+element['elementId']).encode()).hexdigest()
        provenance = {**source_provenance, 'derivedPackageSha256': source_hash,
                      'elementXmlSha256': element.get('xmlSha256'), 'sourceLocator': locator,
                      'containsRevisions': element.get('containsRevisions', False),
                      'containsDrawing': element.get('containsDrawing', False),
                      'conversionFidelityVerified': False, 'requestedEditionVerified': False}
        records.append(dict(list='PPG Structured Content', key='ContentKey', record=dict(
            Title=f"{index+1:03d} {element['kind']} — {module}",
            ContentKey=key, DocumentUID=document_uid, SourceEditionKey=source_hash,
            SourceElementId=element['elementId'], SourceOrdinal=index+1,
            SourceText=text if text else None, ProposedModule=module,
            SourceProvenance=json.dumps(provenance, separators=(',', ':'), ensure_ascii=False))))
    return {'schemaVersion': 1, 'moduleVersion': modules['moduleVersion'],
            'moduleStatus': modules['status'], 'documentUID': document_uid,
            'sourcePackageSha256': source_hash, 'elementCount': len(elements),
            'records': records, 'retainedPackageParts': inventory.get('parts', []),
            'sourceAuthorityVerified': False, 'currentTemplateVerified': False,
            'contentMappingComplete': False, 'requiredness': 'unverified',
            'limitations': ['Modules are heading-based proposals, not an accepted template mapping.',
                           'Source comments, revisions and complex content remain in originals; conversion fidelity is unverified.',
                           'ReviewText, ReviewedModule, StableSectionId and BlockReviewState belong to reviewers and are never seeded.',
                           'New source editions receive new keys; cross-version section lineage requires explicit reconciliation.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    result = prepare(data['documentUID'], data['inventory'], data['modules'], data['sourceProvenance'])
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(json.dumps({'elements': result['elementCount'], 'nativeWrites': 0}))
