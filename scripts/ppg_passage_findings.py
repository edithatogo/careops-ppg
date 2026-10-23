"""Attach provisional, passage-checked suggestions without promoting source authority."""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def build(preparation, inventory, source_bytes, findings):
    digest = hashlib.sha256(source_bytes).hexdigest()
    if inventory['sourceSha256'] != digest:
        raise ValueError('Inventory does not bind inspected source bytes')
    passages = {}
    for element in inventory['elements']:
        locator = element['sourceLocator']
        if locator in passages:
            raise ValueError('Ambiguous passage locator')
        passages[locator] = element['text']
    criteria = {c['criterionId'] for c in preparation['reviewChecklist']}
    actions = set(preparation['decisionOptions'])
    seen = set()
    checked = copy.deepcopy(findings)
    for finding in checked:
        key = finding['findingId']
        if key in seen:
            raise ValueError('Duplicate finding')
        seen.add(key)
        if finding['criterionId'] not in criteria or finding['suggestedAction'] not in actions:
            raise ValueError('Unknown criterion or action')
        if finding['claimType'] not in {'evidence', 'inference', 'unknown'}:
            raise ValueError('Unknown claim type')
        if finding['claimType'] == 'unknown' and finding['suggestedAction'] != 'seek_further_evidence':
            raise ValueError('Unknown cannot support disposition')
        if not finding.get('citations'):
            raise ValueError('Missing passage evidence')
        for cite in finding['citations']:
            if cite['sourceSha256'] != digest or not cite.get('quote') or cite['quote'] not in passages.get(cite['locator'], ''):
                raise ValueError('Citation quote/hash/locator mismatch')
        if not all(finding.get(k) for k in ['statement', 'benefit', 'effort', 'dependencies', 'uncertainty']):
            raise ValueError('Missing suggestion context')
        if finding.get('humanDecision') is not None:
            raise ValueError('Suggestion cannot supply human decision')
        finding['humanDecision'] = None
        finding['scope'] = 'historical_inspection_only'
    return {'schemaVersion': 1, 'packKind': 'provisional_passage_findings',
            'status': 'held_missing_current_source_and_template',
            'requestedSubject': copy.deepcopy(preparation['subject']),
            'inspectedSourceSha256': digest, 'inspectedSourceAuthority': inventory['sourceAuthority'],
            'preparation': copy.deepcopy(preparation), 'findings': checked,
            'limitations': ['Historical conversion fidelity and current applicability unverified.',
                            'No comparator semantic coverage is promoted by these findings.',
                            'No qualified native AI execution or clinical review claimed.'],
            'humanDecision': None, 'policyApproved': False,
            'publicationAuthorised': False, 'notificationsEnabled': False}


def save(preparation, inventory, source_bytes, findings, directory):
    pack = build(preparation, inventory, source_bytes, findings)
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=False)
    raw = (json.dumps(pack, indent=2, ensure_ascii=False)+'\n').encode()
    (target/'review-findings.json').write_bytes(raw)
    lines = ['# Provisional historical review findings', '',
             'Current procedure and template remain unverified. No decision or issuance follows.', '',
             'The complete preparation, catalogue accounting and source gaps are retained in review-findings.json.', '']
    for f in pack['findings']:
        lines += ['## '+f['findingId'], '', f['statement'], '',
                  'Proposed action: '+f['suggestedAction']+'. Effort: '+f['effort']+'.', '',
                  'Benefit: '+f['benefit'], '', 'Dependencies: '+f['dependencies'], '',
                  'Uncertainty: '+f['uncertainty'], '']
        lines += ['- '+c['locator']+': '+c['quote'] for c in f['citations']]
        lines += ['']
    (target/'README.md').write_text('\n'.join(lines))
    receipt = {'sha256': hashlib.sha256(raw).hexdigest(), 'findings': len(pack['findings']),
               'catalogueCount': preparation['catalogueCount'], 'nativeStorageVerified': False}
    (target/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['preparation', 'inventory', 'source', 'findings', 'output']:
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(save(json.loads(a.preparation.read_text()), json.loads(a.inventory.read_text()),
                          a.source.read_bytes(), json.loads(a.findings.read_text()), a.output)))
