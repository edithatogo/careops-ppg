"""Assemble evidence and unresolved work for manual review; never issue documents."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from scripts.ppg_review_intelligence import carry_annotations


def build(inputs):
    subject = inputs['subject']
    catalogue = inputs['catalogue']
    criteria = inputs['criteria']
    uid = subject['documentUID']
    rows = catalogue['records']
    ids = [r['documentUID'] for r in rows]
    if len(ids) != len(set(ids)) or len(ids) != catalogue['catalogueCount'] or uid not in ids:
        raise ValueError('Incomplete or ambiguous catalogue accounting')
    inventory = inputs.get('contentInventory')
    gaps = list(inputs.get('sourceGaps', []))
    if not subject.get('verifiedSource'):
        gaps.append('Requested subject source identity/version/bytes not verified; no current-edition substantive findings established.')
    if not inputs['template'].get('verifiedSource'):
        gaps.append('Current template authority and version not verified.')
    if inventory:
        if inventory['sourceSha256'] != subject.get('sourceSha256'):
            raise ValueError('Inventory does not bind subject bytes')
        elements = inventory['elements']
        element_ids = [e['elementId'] for e in elements]
        if len(element_ids) != len(set(element_ids)) or not elements:
            raise ValueError('Missing or duplicate content elements')
        for e in elements:
            if e['disposition'] not in {'mapped', 'retained_unmapped', 'unresolved'}:
                raise ValueError('Unknown content disposition')
            if e['disposition'] == 'mapped' and not e.get('targetModule'):
                raise ValueError('Mapped element needs target module')
        if any(e['disposition'] != 'mapped' for e in elements):
            gaps.append('Source elements remain retained/unmapped or unresolved; complete mapping is not established.')
    else:
        elements = []
        gaps.append('Subject element inventory unavailable; preservation/mapping cannot yet be demonstrated.')
    # Structural inventory IDs are version-specific; stable section mapping is separate.
    annotations = carry_annotations(inputs['annotations'], uid, subject.get('documentVersion'),
                                   inputs.get('stableSectionIds', []))
    if inputs.get('annotationCoverage') != 'complete':
        gaps.append('Annotation retrieval/history coverage is incomplete or unverified.')
    comparison = []
    for r in rows:
        comparison.append({**copy.deepcopy(r), 'comparisonState': 'not_compared',
                           'reason': 'Verified subject and comparator passages required; identifier matches are retrieval leads.'})
    gaps.append('Full-text comparison remains unperformed for '+str(len(rows))+' catalogue entries.')
    return dict(schemaVersion=1, packKind='manual_review_preparation',
                status='held_missing_evidence', subject=copy.deepcopy(subject),
                template=copy.deepcopy(inputs['template']), catalogueSourceSha256=catalogue['sourceSha256'],
                catalogueCount=len(rows), comparisonMatrix=comparison,
                contentInventory=copy.deepcopy(inventory), unresolvedAnnotations=annotations,
                annotationCoverage=inputs.get('annotationCoverage', 'unknown'),
                criteriaVersion=criteria['criteriaVersion'],
                reviewChecklist=[{**copy.deepcopy(c), 'response':'unknown_missing_evidence',
                                  'findings':[], 'humanDecision':None} for c in criteria['criteria']],
                decisionOptions=criteria['decisionOptions'], findings=[], humanDecision=None,
                standardsEvidence=copy.deepcopy(inputs.get('standardsEvidence', [])),
                sourceCandidates=copy.deepcopy(inputs.get('sourceCandidates', [])),
                gaps=gaps, nextActions=['Obtain verified subject/current template',
                                       'Reconcile source identities and acquire comparator passages',
                                       'Complete element/module mapping and review checklist',
                                       'Record human disposition after evidence review'],
                policyApproved=False, publicationAuthorised=False, notificationsEnabled=False)


def save(inputs, directory):
    pack = build(inputs)
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=False)
    # New directory only: retries never replace a human-edited pack.
    raw = (json.dumps(pack, indent=2, ensure_ascii=False)+'\n').encode()
    (target/'review-pack.json').write_bytes(raw)
    (target/'inputs.json').write_text(json.dumps(inputs,indent=2,ensure_ascii=False)+'\n')
    summary = ['# Manual review preparation', '', pack['subject']['title'], '',
               '**Held: evidence incomplete. No clinical findings or decision established.**', '',
               'Catalogue entries accounted: '+str(pack['catalogueCount']),
               'Entries substantively compared: 0',
               'Unresolved annotations carried forward: '+str(len(pack['unresolvedAnnotations'])), '',
               '## Evidence gaps', ''] + ['- '+g for g in pack['gaps']]
    summary += ['', '## Next actions', ''] + ['- '+a for a in pack['nextActions']]
    if pack['sourceCandidates']:
        summary += ['', '## Recovered source candidates', '',
                    'Candidate evidence is retained in review-pack.json. It does not establish the requested edition or current authority.',
                    'Candidates retained: '+str(len(pack['sourceCandidates']))]
    summary += ['', 'The complete comparison ledger, checklist, annotations and provenance are in [review-pack.json](review-pack.json).',
                'Maintain the original Word procedure and template separately; this preparation record does not regenerate or overwrite either.', '']
    (target/'README.md').write_text('\n'.join(summary))
    receipt = dict(packSha256=hashlib.sha256(raw).hexdigest(), catalogueCount=pack['catalogueCount'],
                   status=pack['status'], outputFiles=['README.md','review-pack.json','inputs.json'])
    (target/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(save(json.loads(args.input.read_text()),args.output)))
