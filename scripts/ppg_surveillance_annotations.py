"""Propose quiet review annotations from verified captures and explicit standards links."""
import hashlib
import json
from scripts.ppg_source_surveillance import compare, validate_config


def proposals(registry, baseline, candidate, requirements, mappings, existing_keys=()):
    sources = validate_config(registry)
    if registry.get('ownerNotificationsEnabled') is not False or registry.get('automaticBaselinePromotion') is not False:
        raise ValueError('Quiet manual baseline contract required')
    reqs = {}
    for row in requirements:
        key = row['RequirementKey']
        if key in reqs: raise ValueError('Duplicate requirement')
        reqs[key] = row
    mapped, mapping_keys = {}, set()
    for row in mappings:
        if row['MappingKey'] in mapping_keys: raise ValueError('Duplicate mapping')
        mapping_keys.add(row['MappingKey'])
        if row['RequirementKey'] not in reqs: raise ValueError('Mapping requirement unavailable')
        if row['MappingState'] not in {'Proposed','Reviewed','Rejected','Superseded'}:
            raise ValueError('Unknown mapping state')
        if row['MappingState'] in {'Rejected','Superseded'}: continue
        if not row['DocumentUID'] or not row['DocumentVersion'] or not row.get('EvidenceRef'):
            raise ValueError('Mapping needs version-bound evidence')
        edition = reqs[row['RequirementKey']]['FrameworkKey']
        mapped.setdefault(edition, []).append(row)
    report = compare(baseline, candidate, [])
    if report['familyId'] != registry['familyId']: raise ValueError('Registry/capture family differs')
    if {c['sourceKey'] for c in report['changes']} != set(sources):
        raise ValueError('Registry/capture source scope differs')
    queue, deduplicated, unmatched, coverage = [], [], [], []
    for change in report['changes']:
        source = sources[change['sourceKey']]
        if change['canonicalUrl'] != source['canonicalUrl']: raise ValueError('Source URL differs')
        linked = mapped.get(source['frameworkEditionId'], [])
        grouped = {}
        for row in linked:
            grouped.setdefault((row['DocumentUID'],row['DocumentVersion']), []).append(row)
        coverage.append(dict(sourceKey=change['sourceKey'], mappingCount=len(linked),
                             documentVersionCandidates=len(grouped),
                             scope='Explicit standards mappings only; omitted documents unassessed'))
        if change['kind'] in {'source-unavailable-exception','baseline-unavailable'}:
            unmatched.append(dict(sourceKey=change['sourceKey'],kind=change['kind'],
                                  reason='Acquisition/baseline exception, not a substantive source change'))
            continue
        if change['kind'] == 'unchanged': continue
        if change['kind'] not in {'captured-bytes-changed','version-reference-changed'}:
            raise ValueError('Unknown capture comparison signal')
        fingerprint = hashlib.sha256(json.dumps({k:change[k] for k in [
            'sourceKey','canonicalUrl','beforeSHA256','afterSHA256',
            'beforeNativeVersionRef','afterNativeVersionRef']},sort_keys=True).encode()).hexdigest()
        if not grouped:
            unmatched.append(dict(sourceKey=change['sourceKey'],kind=change['kind'],
                                  reason='No recorded document relationship; affected scope unassessed'))
        for (uid,version), rows in sorted(grouped.items()):
            key = hashlib.sha256(('\n'.join([fingerprint,uid,version])).encode()).hexdigest()
            if key in existing_keys:
                deduplicated.append(key);continue
            evidence = dict(source=source,change=change,changeFingerprint=fingerprint,
                            baselineSnapshot=report['baselineSnapshot'],candidateSnapshot=report['candidateSnapshot'],
                            mappingKeys=sorted(r['MappingKey'] for r in rows),
                            requirementKeys=sorted({r['RequirementKey'] for r in rows}),
                            mappingStates=sorted({r['MappingState'] for r in rows}),
                            applicabilityVerified=False,semanticChangeEstablished=False)
            queue.append(dict(AnnotationKey=key,DocumentUID=uid,DocumentVersion=version,
                Title='Source-change review lead: '+change['sourceKey'],ReviewState='Received',
                OriginalSuggestion='AUTOMATED CAPTURE SIGNAL — HUMAN REVIEW REQUIRED\n'
                    +'Selected source bytes/version reference changed: '+source['canonicalUrl']
                    +'\nRecorded standards mappings suggest a review lead only. Changes may be formatting or navigation. '
                    +'Inspect preserved evidence and verify current document/edition applicability before proposing a substantive change. '
                    +'No compliance finding, clinical decision or owner notification is established.',
                EvidenceRef=json.dumps(evidence,sort_keys=True,ensure_ascii=False)))
    return dict(schemaVersion=1,registryVersion=registry['registryVersion'],comparison=report,
                relationshipCoverage=coverage,annotationProposals=queue,
                deduplicatedProposalKeys=deduplicated,unresolvedSources=unmatched,
                baselineAdvanced=False,notificationsEnabled=False,humanDecision=None)


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['registry','baseline','candidate','links','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();links=json.loads(args.links.read_text())
    result=proposals(json.loads(args.registry.read_text()),args.baseline,args.candidate,
                     links['requirements'],links['mappings'],links.get('existingAnnotationKeys',[]))
    with args.output.open('x') as stream:
        stream.write(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'annotationProposals':len(result['annotationProposals']),
                      'unresolvedSources':len(result['unresolvedSources']),'nativeWrites':0}))
