"""Validate a provisional two-document text assessment; never promote current authority."""
import copy
import hashlib
import json
import re
from pathlib import Path


def assess(preparation, subject_inventory, subject_bytes, comparator, text_bytes, original_bytes, findings, refinements=()):
    subject_sha=hashlib.sha256(subject_bytes).hexdigest()
    text_sha=hashlib.sha256(text_bytes).hexdigest()
    original_sha=hashlib.sha256(original_bytes).hexdigest()
    if subject_sha!=subject_inventory['sourceSha256'] or text_sha!=comparator['textSha256'] or original_sha!=comparator['originalSha256']:
        raise ValueError('Source representation/original hash mismatch')
    text=text_bytes.decode('utf-8');lines=text.split('\n')
    if not re.search(r'Document\s+Number\s*:?\s*'+re.escape(comparator['recordedDocumentId'])+r'(?=\s|$)', '\n'.join(lines[:30]), re.I):
        raise ValueError('Recorded comparator identifier missing from text')
    rows=copy.deepcopy(preparation['comparisonMatrix'])
    ids=[r['documentUID'] for r in rows]
    if len(ids)!=len(set(ids)) or len(rows)!=preparation['catalogueCount']:
        raise ValueError('Incomplete catalogue accounting')
    match=[r for r in rows if r['documentUID']==comparator['documentUID']]
    if len(match)!=1:
        raise ValueError('Comparator identity differs from catalogue assertion')
    if any(h.get('state')=='held' and h.get('originalSha256')==original_sha
           for h in match[0].get('sourceAssociationHolds', [])):
        raise ValueError('Source association held; preserve conflicting identity evidence')
    association=comparator.get('catalogueAssociation')
    candidate=match[0]['sourceDocumentId']!=comparator['recordedDocumentId']
    if candidate:
        if (not isinstance(association, dict)
                or association.get('status')!='unverified_identifier_variant'
                or association.get('catalogueDocumentId')!=match[0]['sourceDocumentId']
                or not all(isinstance(association.get(k), str) and association[k].strip()
                           for k in ['rationale','evidenceRef'])
                or comparator.get('currentAuthorityVerified') is not False):
            raise ValueError('Identifier variant needs explicit unverified catalogue association')
    elif association is not None:
        raise ValueError('Variant association supplied for matching recorded identifier')
    elements={e['sourceLocator']:e for e in subject_inventory['elements']}
    if len(elements)!=len(subject_inventory['elements']): raise ValueError('Ambiguous source locator')
    criteria={c['criterionId'] for c in preparation['reviewChecklist']};actions=set(preparation['decisionOptions'])
    seen=set();checked=copy.deepcopy(findings)
    for f in checked:
        if f['findingId'] in seen: raise ValueError('Duplicate finding')
        seen.add(f['findingId'])
        if f['criterionId'] not in criteria or f['suggestedAction'] not in actions:
            raise ValueError('Unknown criterion/action')
        if f['claimType'] not in {'evidence','inference','unknown'}: raise ValueError('Unknown claim type')
        if f['claimType']=='unknown' and f['suggestedAction']!='seek_further_evidence':
            raise ValueError('Unknown cannot support disposition')
        if f.get('humanDecision') is not None: raise ValueError('Human decision cannot be supplied')
        cited=set()
        for c in f['citations']:
            source=c['sourceId'];cited.add(source)
            if source=='subject-inspection':
                e=elements.get(c['locator']);passage=e['text'] if e else None;expected=subject_sha
                c['containsTrackedRevisions']=bool(e and e.get('containsRevisions'))
                if c['containsTrackedRevisions'] and f['claimType']!='unknown':
                    raise ValueError('Tracked revision passage requires unresolved assessment')
            elif source=='comparator-text':
                m=re.fullmatch(r'lines=(\d+)-(\d+)',c['locator'])
                if not m or not 1<=int(m[1])<=int(m[2])<=len(lines): raise ValueError('Invalid text passage range')
                passage='\n'.join(lines[int(m[1])-1:int(m[2])]);expected=text_sha
            else: raise ValueError('Unknown comparison source')
            if c['sourceSha256']!=expected or not c.get('quote') or not passage or c['quote'] not in passage:
                raise ValueError('Quote/hash/locator mismatch')
        if cited!={'subject-inspection','comparator-text'}: raise ValueError('Pair finding needs both sources')
        if not all(f.get(k) for k in ['statement','benefit','effort','dependencies','uncertainty']):
            raise ValueError('Missing review context')
        f['humanDecision']=None;f['scope']='historical_subject_and_retained_comparator_text_only'
    refined=copy.deepcopy(list(refinements))
    for r in refined:
        if not r.get('statement') or r.get('humanDecision') is not None or not r.get('citations'):
            raise ValueError('Refinement needs evidence and no supplied decision')
        for c in r['citations']:
            e=elements.get(c['locator'])
            if c['sourceId']!='subject-inspection' or c['sourceSha256']!=subject_sha or not e or not c.get('quote') or c['quote'] not in e['text']:
                raise ValueError('Refinement passage mismatch')
        r['scope']='historical_subject_inspection_only';r['humanDecision']=None
    assessment={'findings':[f['findingId'] for f in checked],
        'subjectInspectionSHA256':subject_sha,'comparatorTextSHA256':text_sha,
        'comparatorOriginalSHA256':original_sha,'currentAuthorityVerified':False,
        'assessmentContentSHA256':hashlib.sha256(json.dumps(
            {'findings':checked,'refinements':refined},sort_keys=True).encode()).hexdigest()}
    if candidate:
        assessment.update(recordedDocumentId=comparator['recordedDocumentId'],
            catalogueAssociation=copy.deepcopy(association))
        candidates=match[0].setdefault('retainedIdentifierCandidateAssessments',[])
        previous=[a for a in candidates if a['subjectInspectionSHA256']==subject_sha
                  and a['comparatorOriginalSHA256']==original_sha]
        if previous and previous!=[assessment]:
            raise ValueError('Existing candidate assessment differs; preserve prior review')
        if not previous:
            candidates.append(assessment)
    else:
        previous=match[0].get('retainedTextPairAssessment')
        if previous is not None and previous!=assessment:
            raise ValueError('Existing pair assessment differs or lacks content provenance; preserve prior review')
        if previous is None:
            match[0]['comparisonState']='provisional_historical_pair_review'
            match[0]['retainedTextPairAssessment']=assessment
            match[0]['reason']='Retained text assessed against historical V6 inspection; requested V7/current comparator authority and visual fidelity remain unverified.'
    exact=[r['retainedTextPairAssessment'] for r in rows if r.get('retainedTextPairAssessment')]
    candidates=[a for r in rows for a in r.get('retainedIdentifierCandidateAssessments',[])]
    source_keys=lambda assessments:{(a['subjectInspectionSHA256'],a['comparatorOriginalSHA256']) for a in assessments}
    return dict(schemaVersion=1,kind='provisional_two_document_review',
        status='held_missing_current_subject_template_and_authority',
        requestedSubject=copy.deepcopy(preparation['subject']),comparator=copy.deepcopy(comparator),
        templateContext=copy.deepcopy(preparation.get('template',{})),
        sourceCandidates=copy.deepcopy(preparation.get('sourceCandidates',[])),
        criterionReview=[dict(criterionId=c['criterionId'],historicalPairFindingIds=[f['findingId'] for f in checked if f['criterionId']==c['criterionId']],requestedEditionResponse='unknown_missing_evidence') for c in preparation['reviewChecklist']],
        implementationSHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        subjectInspectionSHA256=subject_sha,comparisonMatrix=rows,catalogueCount=len(rows),
        retainedTextPairsAssessed=len(exact),
        candidateIdentifierPairsAssessed=len(source_keys(candidates)),
        retainedSourcePairsAssessed=len(source_keys(exact+candidates)),
        comparatorIdentityStatus='unverified_identifier_variant' if candidate else 'recorded_identifier_match_only',
        verifiedRequestedEditionComparisons=0,findings=checked,refinements=refined,
        criteriaVersion=preparation['criteriaVersion'],
        promptReferences=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),invokedNativeAI=False)
          for p in [Path('templates/review-intelligence/v1.0.0/manual-review-guide.md'),Path('templates/review-intelligence/v1.0.0/duplication.md')]],
        runtimeIdentity=dict(executionMode='agent_assisted_manual_text_review',provider='Codex',model=None,
                             modelVersion=None,versionAvailability='not_exposed',qualifiedNativeAI=False),
        limitations=['Whole-catalogue semantic assessment remains incomplete.',
                     'Tracked insertions/deletions and original visual content require reconciliation.',
                     'This report makes no current medical/legal/compliance determination.'],
        humanDecision=None,policyApproved=False,publicationAuthorised=False,notificationsEnabled=False)


def save(report, directory):
    target=Path(directory);target.mkdir(parents=True,exist_ok=False)
    raw=(json.dumps(report,indent=2,ensure_ascii=False)+'\n').encode()
    (target/'pair-review.json').write_bytes(raw)
    lines=['# Provisional retained-text comparison','','Historical discharge-summary inspection versus one retained comparator. Current authority, requested V7 source and template remain unverified. No current medical/legal/compliance determination or human decision is made.','',
           'Catalogue rows accounted: '+str(report['catalogueCount'])+'. Retained-text pairs assessed: '+str(report['retainedTextPairsAssessed'])+'. Verified requested-edition comparisons: 0.','']
    if report.get('candidateIdentifierPairsAssessed'):
        lines+=['Separately retained identifier-variant candidate sources: '+str(report['candidateIdentifierPairsAssessed'])+'. These do not promote catalogue-edition comparison state or establish stable identity/authority.','']
    for f in report['findings']:
        lines += ['## '+f['findingId'],'',f['statement'],'','Suggested action: '+f['suggestedAction']+'. Effort: '+f['effort']+'.','','Benefit: '+f['benefit'],'','Dependencies: '+f['dependencies'],'','Uncertainty: '+f['uncertainty'],'']
        lines += ['- '+c['sourceId']+' '+c['locator']+': '+c['quote'] for c in f['citations']]
        lines += ['']
    if report.get('refinements'):
        lines += ['## Review refinements','']
        for r in report['refinements']:
            lines += [r['statement'],'']+['- '+c['locator']+': '+c['quote'] for c in r['citations']]+['']
    lines += ['All current-edition criteria remain unknown pending verified sources and wider assessment. The complete catalogue ledger and exact source bindings are in pair-review.json. Other catalogue rows are not silently marked compared.','']
    (target/'README.md').write_text('\n'.join(lines))
    receipt=dict(reportSHA256=hashlib.sha256(raw).hexdigest(),catalogueCount=report['catalogueCount'],retainedTextPairsAssessed=report['retainedTextPairsAssessed'],candidateIdentifierPairsAssessed=report.get('candidateIdentifierPairsAssessed',0),retainedSourcePairsAssessed=report.get('retainedSourcePairsAssessed',report['retainedTextPairsAssessed']),verifiedRequestedEditionComparisons=0,humanDecision=None)
    (target/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['preparation','subject-inventory','subject-inspection','comparator','comparator-text','comparator-original','findings','output']:
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--refinements',type=Path)
    a=p.parse_args()
    report=assess(json.loads(a.preparation.read_text()),json.loads(a.subject_inventory.read_text()),a.subject_inspection.read_bytes(),json.loads(a.comparator.read_text()),a.comparator_text.read_bytes(),a.comparator_original.read_bytes(),json.loads(a.findings.read_text()),json.loads(a.refinements.read_text()) if a.refinements else [])
    print(json.dumps(save(report,a.output)))
