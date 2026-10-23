"""Reconcile retained byte evidence and assessments without assigning identities."""
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect_sources(screen, read_bytes=lambda path: Path(path).read_bytes()):
    """Verify actual originals/extractions; this is byte accounting, not appraisal."""
    facts = []
    for index, source in enumerate(screen['corpus']):
        original = read_bytes(source['originalPath'])
        text = read_bytes(source['textPath'])
        if (digest(original) != source['sourceSha256']
                or digest(text) != source['textSha256']):
            raise ValueError('Retained source bytes changed')
        decoded = text.decode('utf-8')
        facts.append(dict(sourceIndex=index, originalSha256=digest(original),
                          textSha256=digest(text), originalBytes=len(original),
                          textBytes=len(text), textLines=len(decoded.split('\n')),
                          words=len(decoded.split())))
    return facts


def reconcile(screen, ledger, facts, unassociated_reviews=()):
    """Use frozen verified facts to rebuild a report; never mutate either input."""
    source_rows = screen['records']
    rows = ledger['comparisonMatrix']
    ids = [r['documentUID'] for r in rows]
    source_ids = [r['documentUID'] for r in source_rows]
    if (len(ids) != ledger['catalogueCount'] or len(ids) != screen['catalogueCount']
            or len(ids) != len(set(ids)) or len(source_ids) != len(set(source_ids))
            or set(ids) != set(source_ids)):
        raise ValueError('Incomplete or ambiguous catalogue accounting')
    corpus = screen['corpus']
    if len(corpus) != screen['sourceCount'] or len(facts) != len(corpus):
        raise ValueError('Incomplete corpus accounting')
    pairs = [(s['sourceSha256'], s['textSha256']) for s in corpus]
    if len(pairs) != len(set(pairs)):
        raise ValueError('Duplicate corpus representation')
    by_pair = {pair: index for index, pair in enumerate(pairs)}
    by_uid = {r['documentUID']: r for r in rows}
    if any(any(row[key] != by_uid[row['documentUID']][key]
                   for key in ['sourceDocumentId', 'title']) for row in source_rows):
        raise ValueError('Catalogue identity assertions differ from screen')
    links = {i: [] for i in range(len(corpus))}
    for row in source_rows:
        indexes = row['sourceIndexes']
        if len(indexes) != len(set(indexes)):
            raise ValueError('Duplicate retrieval association')
        for i in indexes:
            if type(i) is not int or i not in links:
                raise ValueError('Invalid corpus index')
            links[i].append(row['documentUID'])
    assessments = {i: [] for i in links}
    holds = {i: [] for i in links}
    for row in rows:
        uid = row['documentUID']
        entries = ([row['retainedTextPairAssessment']]
                   if row.get('retainedTextPairAssessment') else [])
        entries += row.get('retainedIdentifierCandidateAssessments', [])
        seen = set()
        for entry in entries:
            pair = (entry['comparatorOriginalSHA256'], entry['comparatorTextSHA256'])
            if pair not in by_pair or pair in seen:
                raise ValueError('Unknown or duplicate assessment representation')
            seen.add(pair)
            i = by_pair[pair]
            if uid not in links[i]:
                raise ValueError('Assessment has no retained retrieval association')
            if entry.get('currentAuthorityVerified') is not False:
                raise ValueError('Provisional assessment boundary missing')
            assessments[i].append(dict(documentUID=uid,
                                       contentProvenanceState=('content_hash_recorded' if entry.get('assessmentContentSHA256')
                                                               else 'legacy_content_hash_missing'),
                                       assessment=copy.deepcopy(entry)))
        for hold in row.get('sourceAssociationHolds', []):
            if hold['state'] != 'held':
                continue
            pair = (hold['originalSha256'], hold['textSha256'])
            if pair not in by_pair or uid not in links[by_pair[pair]]:
                raise ValueError('Hold has no retained representation/association')
            holds[by_pair[pair]].append(copy.deepcopy(hold))
    source_reviews = {}
    for review in unassociated_reviews:
        index = review.get('sourceIndex')
        if type(index) is not int or index not in links or links[index] or index in source_reviews:
            raise ValueError('Source-only review index is associated, unknown or duplicated')
        expected = hashlib.sha256(json.dumps(
            {k: v for k, v in review.items() if k != 'contentSHA256'},
            sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if (review.get('kind') != 'unassociated_retained_source_review'
                or review.get('contentSHA256') != expected
                or (review.get('originalSHA256'), review.get('textSHA256')) != pairs[index]
                or review.get('catalogueIdentityAssigned') is not False
                or review.get('currentAuthorityVerified') is not False
                or review.get('humanDecision') is not None):
            raise ValueError('Source-only review provenance or boundary mismatch')
        source_reviews[index] = copy.deepcopy(review)
    results = []
    for i, (source, fact) in enumerate(zip(corpus, facts)):
        if (type(fact.get('sourceIndex')) is not int or fact.get('sourceIndex') != i
                or (fact.get('originalSha256'), fact.get('textSha256')) != pairs[i]
                or any(type(fact.get(k)) is not int or fact[k] < 0
                       for k in ['originalBytes', 'textBytes', 'textLines', 'words'])):
            raise ValueError('Byte facts differ from frozen corpus')
        assessed = {a['documentUID'] for a in assessments[i]}
        held = {h['documentUID'] for h in holds[i]}
        if assessed & held:
            raise ValueError('Held association has an assessment')
        pending = sorted(set(links[i]) - assessed - held)
        state = ('held_source_association' if held else
                 'associated_unassessed' if pending else
                 'assessed_retained_text' if assessed else
                 'unassociated_reviewed' if i in source_reviews else 'unassociated_unassessed')
        results.append(dict(sourceIndex=i, state=state, byteFacts=copy.deepcopy(fact),
                            source=copy.deepcopy(source),
                            retrievalAssociations=[dict(documentUID=uid,
                                sourceDocumentId=by_uid[uid]['sourceDocumentId'],
                                title=by_uid[uid]['title']) for uid in links[i]],
                            assessments=assessments[i], sourceAssociationHolds=holds[i],
                            pendingAssociatedDocumentUIDs=pending,
                            identityAssignedByReconciliation=False,
                            currentAuthorityVerified=False))
    for index, review in source_reviews.items():
        results[index]['unassociatedSourceReview'] = review
    states = dict(Counter(r['state'] for r in results))
    report = dict(schemaVersion=1, kind='retained_corpus_reconciliation',
                catalogueCount=len(rows), retainedSourceCount=len(corpus),
                sourceStates=states,
                extractionCoverage=dict(Counter(s['textCoverage'] for s in corpus)),
                unassociatedHeaderSourceIndexes=[r['sourceIndex'] for r in results
                    if not r['retrievalAssociations'] and r['source']['headerIdentifiers']],
                assessmentProvenance=dict(Counter(a['contentProvenanceState']
                    for values in assessments.values() for a in values)),
                catalogueMetadataOnlyCount=sum(r['coverage'] == 'metadata_only' for r in source_rows),
                sources=results, comparisonMatrix=copy.deepcopy(rows),
                humanDecision=None, identityChanges=0, newAssessments=0,
                limitations=[
                    'Frozen byte facts are observations; rebuilding this report does not reverify source availability.',
                    'Unassociated texts remain unappraised; header assertions are retrieval leads, not assigned identities.',
                    'Sampled OCR and unverified extraction fullness remain explicit; byte checks are not visual fidelity.',
                    'Retained-text assessments do not verify the requested current subject/template or clinical authority.',
                    'No catalogue source fields, prior assessments, holds or human decisions are changed.'])

    if source_reviews:
        report['sourceOnlyReviewCount'] = len(source_reviews)
    return report
