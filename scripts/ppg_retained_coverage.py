"""Derive explicit catalogue coverage from retained evidence; never assign identity."""
import copy
import hashlib
import json
from collections import Counter
from urllib.parse import urlsplit
from scripts.ppg_findings_web import text


def derive(pack):
    corpus = pack['retrievalCorpusReconciliation']
    matrix = corpus['comparisonMatrix']
    by_uid = {r['documentUID']: r for r in matrix}
    if len(by_uid) != len(matrix) or len(matrix) != corpus['catalogueCount']:
        raise ValueError('Incomplete or duplicate catalogue identities')
    if matrix != pack['preparation']['comparisonMatrix']:
        raise ValueError('Conflicting catalogue matrices')
    sources = corpus['sources']
    if len(sources) != corpus['retainedSourceCount']:
        raise ValueError('Incomplete retained source inventory')
    evidence = {uid: [] for uid in by_uid}
    seen_indexes = set()
    source_states = Counter()
    for source in sources:
        index = source['sourceIndex']
        if type(index) is not int or index < 0 or index in seen_indexes:
            raise ValueError('Invalid or duplicate source index')
        seen_indexes.add(index)
        facts = source['byteFacts']
        original, text = facts['originalSha256'], facts['textSha256']
        if (facts['sourceIndex'] != index
                or original != source['source']['sourceSha256']
                or text != source['source']['textSha256']):
            raise ValueError('Source representation pins differ')
        associations = source['retrievalAssociations']
        linked = [a['documentUID'] for a in associations]
        if len(set(linked)) != len(linked) or any(uid not in by_uid for uid in linked):
            raise ValueError('Unknown or duplicate retrieval association')
        for a in associations:
            if any(a[k] != by_uid[a['documentUID']][k] for k in ['sourceDocumentId', 'title']):
                raise ValueError('Retrieval association changed catalogue assertions')
        assessments = {}
        for a in source['assessments']:
            uid, item = a['documentUID'], a['assessment']
            if (uid not in linked or uid in assessments
                    or item['comparatorOriginalSHA256'] != original
                    or item['comparatorTextSHA256'] != text
                    or item['subjectInspectionSHA256'] != pack['inspectedSourceSha256']
                    or item.get('currentAuthorityVerified') is not False):
                raise ValueError('Assessment association/version/pins differ')
            assessments[uid] = item
        held = {}
        for hold in source['sourceAssociationHolds']:
            uid = hold['documentUID']
            if (uid not in linked or uid in held or uid in assessments
                    or hold['state'] != 'held' or hold['originalSha256'] != original
                    or hold['textSha256'] != text):
                raise ValueError('Invalid or conflicting held association')
            held[uid] = hold
        pending = set(linked) - set(assessments) - set(held)
        recorded_pending = source['pendingAssociatedDocumentUIDs']
        if len(set(recorded_pending)) != len(recorded_pending) or set(recorded_pending) != pending:
            raise ValueError('Pending coverage does not account for every association')
        source_states[source['state']] += 1
        for uid in linked:
            item = assessments.get(uid)
            status = ('held' if uid in held else 'available_not_reviewed' if uid in pending
                      else 'provisional_identifier_variant' if item.get('catalogueAssociation')
                      else 'provisional_recorded_identifier')
            evidence[uid].append(dict(sourceIndex=index, originalSHA256=original,
                textSHA256=text, extractionCoverage=source['source']['textCoverage'],
                status=status, assessment=copy.deepcopy(item), hold=copy.deepcopy(held.get(uid))))
    if seen_indexes != set(range(len(sources))):
        raise ValueError('Gapped retained source inventory')
    rows = []
    for uid, original in by_uid.items():
        items = sorted(evidence[uid], key=lambda r: r['sourceIndex'])
        counts = Counter(r['status'] for r in items)
        state = ('metadata_only' if not items else 'available_not_reviewed'
                 if counts['available_not_reviewed'] else 'provisional_review_with_hold'
                 if counts['held'] and len(items) > counts['held'] else 'held'
                 if counts['held'] else 'provisional_review')
        rows.append(dict(documentUID=uid, sourceDocumentId=original['sourceDocumentId'],
            title=original['title'], originalRetrievalAssertion=copy.deepcopy(original),
            retainedSourceCoverage=state, sourceCount=len(items),
            recordedIdentifierAssessments=counts['provisional_recorded_identifier'],
            identifierVariantAssessments=counts['provisional_identifier_variant'],
            heldAssociations=counts['held'], pendingAssociations=counts['available_not_reviewed'],
            sources=items, currentAuthorityVerified=False, humanDecision=None))
    counts = dict(Counter(r['retainedSourceCoverage'] for r in rows))
    metadata = counts.get('metadata_only', 0)
    if metadata != corpus['catalogueMetadataOnlyCount']:
        raise ValueError('Metadata-only roll-up differs from actual source associations')
    return dict(schemaVersion=1, kind='derived_retained_catalogue_coverage',
        canonicalInputSHA256=hashlib.sha256(json.dumps(pack, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        catalogueCount=len(rows), retainedSourceCount=len(sources), coverageCounts=counts,
        originalRetrievalCounts=dict(Counter(r.get('coverage', 'unknown') for r in matrix)),
        sourceStates=dict(source_states), rows=rows, nativeWrites=0, identityChanges=0,
        humanDecision=None, currentAuthorityVerified=False,
        limitations=['Original retrieval assertions are historical and retained unchanged.',
                    'Provisional text review does not verify requested/current editions or clinical applicability.',
                    'Extraction coverage is retained per source; byte availability does not prove visual fidelity.'])


def render(report, links):
    """Readable web ledger; source assertions and current derivation stay separate."""
    for href in links.values():
        u = urlsplit(href)
        if u.scheme != 'https' or not u.netloc or u.username or u.password:
            raise ValueError('Expected qualified HTTPS evidence link')
    parts = ['<h2>Retained-source coverage for the historical discharge-summary pilot</h2>',
             '<p>Current procedure/template authority is open and nonblocking. Provisional comparisons are not clinical decisions or verified current-edition reviews.</p>',
             '<p>Original retrieval labels describe an earlier search. Current retained-source coverage is derived separately from every recorded association, assessment and hold; original assertions remain unchanged.</p>',
             '<p>'+text(report['catalogueCount'])+' catalogue identities; '+text(report['retainedSourceCount'])+' retained assets. Current coverage: '+text(report['coverageCounts'])+'. Original retrieval labels: '+text(report['originalRetrievalCounts'])+'.</p>']
    for label, href in links.items():
        parts.append('<p><a href="'+text(href)+'">'+text(label)+'</a></p>')
    for state in sorted(report['coverageCounts']):
        rows = [r for r in report['rows'] if r['retainedSourceCoverage'] == state]
        parts.extend(['<h3>'+text(state)+' — '+str(len(rows))+' identities</h3>',
            '<table><thead><tr><th>Document and identity</th><th>Original retrieval label</th><th>Recorded / variant / held / pending</th><th>Retained source indexes and extraction scope</th></tr></thead><tbody>'])
        for r in rows:
            indexes = '; '.join(str(s['sourceIndex'])+': '+s['status']+'; '+s['extractionCoverage'] for s in r['sources']) or 'No associated retained text; no negative duplication conclusion'
            numbers = ' / '.join(str(r[k]) for k in ['recordedIdentifierAssessments', 'identifierVariantAssessments', 'heldAssociations', 'pendingAssociations'])
            parts.append('<tr><td>'+text(r['title'])+'; '+text(r['sourceDocumentId'])+'; '+text(r['documentUID'])+'</td><td>'+text(r['originalRetrievalAssertion'].get('coverage', 'unknown'))+'</td><td>'+numbers+'</td><td>'+text(indexes)+'</td></tr>')
        parts.append('</tbody></table>')
    parts.append('<p>Source-only reviews and unassociated assets are separate from catalogue identities. Exact source hashes, assessment provenance and holds are in the downloadable ledger and unchanged pack. No identity, source field, human decision or notification is changed.</p>')
    return '\n'.join(parts)
