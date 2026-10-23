"""Prepare an explicitly historical development supplement without modifying its inputs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from scripts.ppg_structured_content import prepare


def build(pack, inventory, modules, template_inventory, source_bytes, template_bytes, original_source_sha256):
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    template_hash = hashlib.sha256(template_bytes).hexdigest()
    if template_hash != template_inventory['sourceSha256']:
        raise ValueError('Template bytes do not match inventory')
    if inventory['sourceSha256'] != pack['historicalStructuredInventory']['sourceSha256']:
        raise ValueError('Historical inspection differs from frozen pack')
    if source_hash != original_source_sha256:
        raise ValueError('Original source differs from frozen pack')
    subject = pack['preparation']['subject']
    capture = prepare(subject['documentUID'], inventory, modules,
                      {'originalSourceSha256': source_hash, 'basis': 'historical_v6'})
    result = {
        'schemaVersion': 1, 'kind': 'interim_development_supplement',
        'developmentEligible': True, 'currentVersionVerification': 'open_nonblocking',
        'basis': {'source': 'historical V6', 'originalSourceSha256': source_hash,
                 'inspectionSha256': inventory['sourceSha256'],
                 'template': 'existing candidate; current authority unverified',
                 'templateSha256': template_hash, 'directionDate': '2026-10-20'},
        'requestedEditionVerified': False, 'currentTemplateVerified': False,
        'clinicalDecision': None, 'publicationAuthorised': False,
        'notificationsEnabled': False, 'structuredCapture': capture,
        'templateElementAccounting': copy.deepcopy(template_inventory),
        'frozenPack': copy.deepcopy(pack),
        'limitations': [
            'Historical V6 is the authorised development basis, never relabelled as V7.',
            'Template headings and modules are proposals; mandatory rules remain unverified.',
            'Original packages preserve tables, media, comments and revisions; structural capture does not prove visual or conversion fidelity.',
            'Current-version verification remains open independently of development.',
            'Frozen runs, annotations, reviewer fields and decisions are preserved without repinning or disposition.',
            'Later companion evidence remains separately versioned; this supplement does not claim fresh tenant-state capture.']}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    paths = json.loads(args.input.read_text())
    load = lambda key: json.loads(Path(paths[key]).read_text())
    result = build(load('pack'), load('inventory'), load('modules'), load('templateInventory'),
                   Path(paths['source']).read_bytes(), Path(paths['template']).read_bytes(),
                   paths['originalSourceSha256'])
    with args.output.open('x') as out:
        json.dump(result, out, indent=2, ensure_ascii=False)
    print(json.dumps({'developmentEligible': True,
                      'elements': result['structuredCapture']['elementCount'],
                      'currentVersionVerified': False, 'nativeWrites': 0}))


if __name__ == '__main__':
    main()
