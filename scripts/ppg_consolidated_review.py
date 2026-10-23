"""Consolidate retained review evidence and current reviewer snapshots; no native writes."""
import copy
from scripts.ppg_annotation_adapter import annotations_from_export
from scripts.ppg_review_intelligence import carry_annotations
from scripts.ppg_unassociated_review import content_digest


def consolidate(prior, corpus, external, annotations, content, fallback):
    uid = prior['requestedSubject']['documentUID']
    matrix = corpus['comparisonMatrix']
    old_matrix = prior['comparisonBatch']['comparisonMatrix']
    if matrix != old_matrix or len({r['documentUID'] for r in matrix}) != len(matrix):
        raise ValueError('Catalogue matrix changed; reconcile identities first')
    reviews = [r['unassociatedSourceReview'] for r in corpus['sources'] if 'unassociatedSourceReview' in r]
    seen = set()
    for review in reviews:
        if (review['sourceIndex'] in seen or review['contentSHA256'] != content_digest(review)
                or review['subjectInspectionSHA256'] != prior['inspectedSourceSha256']
                or review['catalogueIdentityAssigned'] or review['currentAuthorityVerified']
                or review['humanDecision'] is not None):
            raise ValueError('Invalid source-only review or authority promotion')
        seen.add(review['sourceIndex'])
    for old in prior['sourceOnlyReviews']:
        matches = [r for r in reviews if r['sourceIndex'] == old['sourceIndex']]
        if matches != [old]:
            raise ValueError('Prior review missing or changed')
    all_annotations = annotations_from_export(annotations)
    subject_annotations = [a for a in all_annotations if a['documentUID'] == uid]
    current_by_id = {a['annotationId']: a for a in subject_annotations}
    if len(current_by_id) != len(subject_annotations):
        raise ValueError('Duplicate annotation identity')
    for old in prior['preparation']['unresolvedAnnotations']:
        new = current_by_id.get(old['annotationId'])
        if not new or new['originalText'] != old['originalText']:
            raise ValueError('Original annotation missing or changed')
        # Older packs may omit enriched context, but recorded values must survive.
        old_history, new_history = old['versionHistory'], new['versionHistory']
        if len(new_history) < len(old_history):
            raise ValueError('Annotation history truncated')
        for before, after in zip(old_history, new_history):
            if any(after.get(k) != v for k, v in before.items()):
                raise ValueError('Historical annotation context changed')
    rows = content['items']['value']
    elements = {e['elementId'] for e in prior['historicalStructuredInventory']['elements']}
    if (not content['sourceFieldsVerifiedAgainstSeeds'] or not content['currentReviewerFieldsPreserved']
            or len(rows) != len(elements) or {r['SourceElementId'] for r in rows} != elements
            or any(r['DocumentUID'] != uid or r['SourceEditionKey'] != prior['inspectedSourceSha256'] for r in rows)):
        raise ValueError('Structured content is incomplete or bound to another source')
    if fallback['sourceSha256'] != prior['inspectedSourceSha256']:
        raise ValueError('Word fallback binds another inspection')
    result = copy.deepcopy(prior)
    result.update(packKind='consolidated_historical_review_pack', status='interim_development_manual_review',
                  release='11.0.0', currentVersionVerification='open_nonblocking',
                  developmentEligible=True, currentSourceVerified=False, currentTemplateVerified=False,
                  sourceOnlyReviews=copy.deepcopy(reviews),
                  sourceOnlyCriterionResponses=[dict(sourceIndex=r['sourceIndex'], sourceOriginalSHA256=r['originalSHA256'],
                      criterionResponseVersion=r['criterionResponseVersion'], response=copy.deepcopy(response))
                      for r in reviews for response in r.get('criterionResponses', [])],
                  externalReviewEvidence=copy.deepcopy(external),
                  currentSubjectAnnotations=copy.deepcopy(subject_annotations),
                  nativeStructuredContentSnapshot=copy.deepcopy(content),
                  wordFallback=copy.deepcopy(fallback),
                  retrievalCorpusReconciliation=copy.deepcopy(corpus))
    unresolved = carry_annotations(all_annotations, uid, prior['requestedSubject']['documentVersion'], [])
    result['preparation']['unresolvedAnnotations'] = unresolved
    result['preparation']['status'] = 'interim_development_manual_review'
    result['preparation']['nextActions'] = [
        'Use the retained V6 Word, current reviewer snapshot and candidate-module section map for manual development/review.',
        'Resolve mapping and Word conversion exceptions explicitly; preserve original content and human edits.',
        'Verify current procedure/template/control authority when available; reconcile into a new version without blocking interim development.']
    result['sourceOnlyFindings'] = [copy.deepcopy(f) for r in reviews for f in r['findings']]
    result['priorPreparationGaps'] = copy.deepcopy(result['preparation']['gaps'])
    result['preparation']['gaps'] = [
        'Current procedure/template/control authority remains unverified and is nonblocking for authorised historical development.',
        'Catalogue coverage includes metadata-only and held records; provisional identity does not establish requested-edition comparisons.',
        'Candidate heading mappings, conversion exceptions, mandatory rules and full Word visual/regeneration fidelity remain unresolved.']
    result['priorEvidencePins'] = {k: result[k] for k in ['annotationExportSHA256', 'relationshipExportSHA256'] if k in result}
    result.pop('annotationExportSHA256', None)
    result['preparation'].pop('annotationExportSHA256', None)
    result['carriedAnnotationCount'] = len(unresolved)
    result['metadataRevision'] = 11
    result['reviewFindingIndex'] = {}
    for pair in result['comparisonBatch']['pairAssessments']:
        for finding in pair['findings']:
            result['reviewFindingIndex'].setdefault(finding['criterionId'], []).append(dict(
                scope='catalogue_pair', sourceOriginalSHA256=pair['comparator']['originalSha256'],
                findingId=finding['findingId'], claimType=finding['claimType'], suggestedAction=finding['suggestedAction']))
    for review in reviews:
        for finding in review['findings']:
            result['reviewFindingIndex'].setdefault(finding['criterionId'], []).append(dict(
                scope='source_only', sourceOriginalSHA256=review['originalSHA256'],
                findingId=finding['findingId'], claimType=finding['claimType'], suggestedAction=finding['suggestedAction']))
    result['supersedesPackForNavigationOnly'] = '10; earlier evidence and held-run pins unchanged'
    return result
