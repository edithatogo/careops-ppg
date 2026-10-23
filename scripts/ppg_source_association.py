"""Hold a passage-backed retrieval association without changing catalogue truth."""
import copy
import hashlib
import json
import re
from collections import Counter


def hold_title_conflict(preparation, document_uid, original_bytes, text_bytes,
                        recorded_identifier, printed_title, locator, evidence_ref):
    rows = copy.deepcopy(preparation['comparisonMatrix'])
    matches = [r for r in rows if r['documentUID'] == document_uid]
    if (len(matches) != 1 or len(rows) != preparation['catalogueCount']
            or len({r['documentUID'] for r in rows}) != len(rows)):
        raise ValueError('Incomplete or ambiguous catalogue identity')
    row = matches[0]
    if not all(isinstance(v, str) and v.strip() for v in
               [recorded_identifier, printed_title, locator, evidence_ref]):
        raise ValueError('Conflict needs identifier, title, passage and evidence')
    lines = text_bytes.decode('utf-8').split('\n')
    span = re.fullmatch(r'lines=(\d+)-(\d+)', locator)
    if not span or not 1 <= int(span[1]) <= int(span[2]) <= len(lines):
        raise ValueError('Invalid printed-title passage')
    passage = '\n'.join(lines[int(span[1])-1:int(span[2])])
    if printed_title not in passage or not re.search(
            r'Document\s+Number\s*:?\s*' + re.escape(recorded_identifier)
            + r'(?=\s|$)', '\n'.join(lines[:30]), re.I):
        raise ValueError('Printed identity evidence missing')
    normalise = lambda value: ' '.join(re.findall(r'\w+', value.casefold()))
    if normalise(printed_title) == normalise(row['title']):
        raise ValueError('Matching titles do not establish a title conflict')
    sha = lambda value: hashlib.sha256(value).hexdigest()
    original_sha, text_sha = sha(original_bytes), sha(text_bytes)
    held = dict(kind='title_identifier_conflict', state='held',
                documentUID=document_uid, catalogueTitle=row['title'],
                catalogueDocumentId=row['sourceDocumentId'],
                recordedDocumentId=recorded_identifier, printedTitle=printed_title,
                originalSha256=original_sha, textSha256=text_sha,
                locator=locator, quote=passage, evidenceRef=evidence_ref,
                resolution=None, sourceChanged=False)
    holds = row.setdefault('sourceAssociationHolds', [])
    prior = [h for h in holds if h['originalSha256'] == original_sha]
    if prior and prior != [held]:
        raise ValueError('Existing conflict differs; preserve evidence and resolution')
    if not prior:
        holds.append(held)
    # Retrieval fields, coverage and prior assessments remain historical assertions.
    # This is an additive hold; it does not decide either document's true identity.
    result = copy.deepcopy(preparation)
    result['comparisonMatrix'] = rows
    return result


def propose_identifier_variant(screen, ledger, source_index, document_uid,
                               original_bytes, text_bytes, recorded_identifier,
                               printed_title, title_locator, document_code,
                               evidence_ref, matching_identifier=False):
    """Add an unverified retrieval lead; never correct source identity or assess text."""
    source_rows = screen['records']
    ledger_rows = ledger['comparisonMatrix']
    source_ids = [r['documentUID'] for r in source_rows]
    ledger_ids = [r['documentUID'] for r in ledger_rows]
    if (len(source_ids) != screen['catalogueCount']
            or len(ledger_ids) != ledger['catalogueCount']
            or len(set(source_ids)) != len(source_ids)
            or len(set(ledger_ids)) != len(ledger_ids)
            or set(source_ids) != set(ledger_ids)):
        raise ValueError('Incomplete or ambiguous catalogue accounting')
    if ('coverageCounts' in screen and screen['coverageCounts'] !=
            dict(Counter(r['coverage'] for r in source_rows))):
        raise ValueError('Coverage counts differ from retrieval rows')
    if any(not isinstance(r.get('sourceIndexes'), list)
           or len(set(r['sourceIndexes'])) != len(r['sourceIndexes'])
           or any(type(i) is not int or not 0 <= i < len(screen['corpus'])
                  for i in r['sourceIndexes']) for r in source_rows):
        raise ValueError('Invalid existing retrieval indexes')
    by_uid = {r['documentUID']: r for r in ledger_rows}
    if any((r['title'], r['sourceDocumentId']) !=
           (by_uid[r['documentUID']]['title'], by_uid[r['documentUID']]['sourceDocumentId'])
           for r in source_rows):
        raise ValueError('Catalogue assertions differ')
    if (type(source_index) is not int or not 0 <= source_index < len(screen['corpus'])
            or screen['sourceCount'] != len(screen['corpus'])
            or document_uid not in by_uid):
        raise ValueError('Unknown source or catalogue entry')
    if not all(isinstance(v, str) and v.strip() for v in
               [recorded_identifier, printed_title, title_locator, document_code, evidence_ref]):
        raise ValueError('Explicit identity evidence required')
    if type(matching_identifier) is not bool:
        raise ValueError('Explicit identifier match mode required')
    if not re.fullmatch(r'\d{1,8}', document_code):
        raise ValueError('Explicit numeric document code required')
    source = screen['corpus'][source_index]
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    if (sha(original_bytes) != source['sourceSha256']
            or sha(text_bytes) != source['textSha256']):
        raise ValueError('Source bytes changed')
    for row in ledger_rows:
        if any(h.get('state') == 'held' and h.get('originalSha256') == sha(original_bytes)
               for h in row.get('sourceAssociationHolds', [])):
            raise ValueError('Source association held')
    lines = text_bytes.decode('utf-8').split('\n')
    header = '\n'.join(lines[:30])
    if not re.search(r'Document\s+Number\s*:?\s*' + re.escape(recorded_identifier)
                     + r'(?=\s|$)', header, re.I):
        raise ValueError('Printed identifier missing')
    span = re.fullmatch(r'lines=(\d+)-(\d+)', title_locator)
    if not span or not 1 <= int(span[1]) <= int(span[2]) <= len(lines):
        raise ValueError('Invalid printed-title passage')
    passage = '\n'.join(lines[int(span[1])-1:int(span[2])])
    if printed_title not in passage:
        raise ValueError('Printed title missing')
    row = next(r for r in source_rows if r['documentUID'] == document_uid)
    ignored = {'policy', 'procedure', 'guideline', 'for', 'the', 'a', 'an', 'of', 'and', 'to'}
    title_tokens = lambda value: [t for t in re.findall(r'\w+', value.casefold())
                                  if t not in ignored]
    if not title_tokens(printed_title) or title_tokens(printed_title) != title_tokens(row['title']):
        raise ValueError('Printed and catalogue titles need explicit reconciliation')
    code_pattern = r'(?<=-)' + re.escape(document_code) + r'(?=-)'
    code_rows = [r for r in source_rows if
                 (r['sourceDocumentId'].casefold() == recorded_identifier.casefold()
                  if matching_identifier else re.search(code_pattern, r['sourceDocumentId']))]
    if len(code_rows) != 1 or code_rows[0]['documentUID'] != document_uid:
        raise ValueError('Ambiguous document-code family')
    if not re.search(code_pattern, recorded_identifier):
        raise ValueError('Printed document code differs')
    catalogue_identifier = row['sourceDocumentId']
    if matching_identifier and recorded_identifier.casefold() != catalogue_identifier.casefold():
        raise ValueError('Matching identifier mode requires complete printed identifier')
    if not matching_identifier and recorded_identifier == catalogue_identifier:
        raise ValueError('Matching identifiers do not need a variant lead')
    org = lambda value: value.split('-', 1)[0].casefold()
    if org(recorded_identifier) != org(catalogue_identifier):
        raise ValueError('Issuing organisation differs')
    version = re.search(r'Version\s+No\.?\s*:?\s*(\d+(?:\.\d+)*)', header, re.I)
    catalogue_version = re.search(r'-V(\d+(?:\.\d+)*)-', catalogue_identifier, re.I)
    def parts(value):
        result = value.split('.')
        while len(result) > 1 and result[-1] == '0':
            result.pop()
        return result
    if not version or not catalogue_version or parts(version[1]) != parts(catalogue_version[1]):
        raise ValueError('Independent printed/catalogue version evidence differs')
    identifier_version = re.search(r'-V(\d+(?:\.\d+)*)-', recorded_identifier, re.I)
    if identifier_version and parts(identifier_version[1]) != parts(version[1]):
        raise ValueError('Printed identifier and version header disagree')
    lead = dict(kind='identifier_variant_retrieval_lead',
                status='unverified_identifier_variant', documentUID=document_uid,
                sourceIndex=source_index, catalogueDocumentId=catalogue_identifier,
                recordedDocumentId=recorded_identifier, printedTitle=printed_title,
                titleLocator=title_locator, titleQuote=passage,
                printedVersionAssertion=version[1], documentCode=document_code,
                originalSHA256=sha(original_bytes), textSHA256=sha(text_bytes),
                evidenceRef=evidence_ref, currentAuthorityVerified=False,
                identityAssigned=False, humanDecision=None, sourceChanged=False)
    if matching_identifier:
        lead.update(kind='matching_identifier_retrieval_lead',
                    status='unverified_matching_identifier')
    lead['contentSHA256'] = sha(json.dumps(lead, sort_keys=True).encode())
    previous = row.get('retrievalCandidateEvidence', [])
    same = [e for e in previous if e['sourceIndex'] == source_index]
    links = [r for r in source_rows if source_index in r['sourceIndexes']]
    bucket = ('matchingIdentifierSourceIndexes' if matching_identifier
              else 'otherEditionSourceIndexes')
    other_bucket = ('otherEditionSourceIndexes' if matching_identifier
                    else 'matchingIdentifierSourceIndexes')
    if same:
        if (same != [lead] or len(links) != 1 or links[0]['documentUID'] != document_uid
                or row['sourceIndexes'].count(source_index) != 1
                or row.get(bucket, []).count(source_index) != 1
                or source_index in row.get(other_bucket, [])
                or row['coverage'] == 'metadata_only'):
            raise ValueError('Existing retrieval evidence differs; preserve prior work')
        return dict(screen=copy.deepcopy(screen), candidate=lead,
                    catalogueLedgerChanged=False, newAssessments=0)
    if links:
        raise ValueError('Existing source association requires reconciliation')
    result = copy.deepcopy(screen)
    target = next(r for r in result['records'] if r['documentUID'] == document_uid)
    target['sourceIndexes'].append(source_index)
    target.setdefault(bucket, []).append(source_index)
    target.setdefault('retrievalCandidateEvidence', []).append(lead)
    if target['coverage'] == 'metadata_only':
        target['coverage'] = ('matching_catalogue_identifier' if matching_identifier
                              else 'other_edition_candidate')
    result['coverageCounts'] = dict(Counter(r['coverage'] for r in result['records']))
    return dict(screen=result, candidate=lead, catalogueLedgerChanged=False, newAssessments=0)


def discover_printed_identifier_leads(screen, corpus_status, source_texts):
    """Account for unassociated sources and surface header leads without binding them."""
    rows = screen['records']
    sources = screen['corpus']
    states = corpus_status['sources']
    ids = [r['documentUID'] for r in rows]
    indexes = [r['sourceIndex'] for r in states]
    if (len(ids) != screen['catalogueCount'] or len(set(ids)) != len(ids)
            or len(sources) != screen['sourceCount'] or len(states) != len(sources)
            or set(indexes) != set(range(len(sources)))
            or any(type(i) is not int for i in indexes)):
        raise ValueError('Complete catalogue/corpus accounting required')
    selected = [r['sourceIndex'] for r in states if r['state'] == 'unassociated_unassessed']
    if set(source_texts) != set(selected):
        raise ValueError('Account for every unassociated unappraised source')
    results = []
    code_pattern = re.compile(r'-(\d{1,5})-(?=V\d|\s*\d{2}/)', re.I)
    def prefix(identifier):
        match = code_pattern.search(identifier)
        return identifier[:match.start()].casefold() if match else None
    for index in selected:
        source = sources[index]
        state = next(r for r in states if r['sourceIndex'] == index)
        if (state.get('retrievalAssociations')
                or any(index in r['sourceIndexes'] for r in rows)):
            raise ValueError('Unassociated state has a retrieval link')
        text_bytes = source_texts[index]
        if hashlib.sha256(text_bytes).hexdigest() != source['textSha256']:
            raise ValueError('Retained text bytes changed')
        text = text_bytes.decode('utf-8')
        header = text.split('\f', 1)[0][:6000]
        assertions = []
        for match in re.finditer(r'Document\s+(?:Number|No\.?|ID)\s*:?\s*([^\n]+)', header, re.I):
            printed = match[1].strip()
            exact = [r for r in rows if r['sourceDocumentId'].casefold() == printed.casefold()]
            codes = code_pattern.findall(printed)
            family = [r for r in rows if printed.split('-', 1)[0].casefold()
                      == r['sourceDocumentId'].split('-', 1)[0].casefold()
                      and any(re.search(r'(?<=-)' + re.escape(c) + r'(?=-)',
                                        r['sourceDocumentId']) for c in codes)]
            candidates = exact or family
            if len(exact) == 1:
                classification = 'case_insensitive_printed_id_match'
            elif len(candidates) > 1:
                classification = 'ambiguous_catalogue_identifier_lead'
            elif len(family) == 1:
                classification = ('unique_identifier_family_lead'
                                  if prefix(printed) == prefix(family[0]['sourceDocumentId'])
                                  else 'numeric_code_collision_different_family')
            else:
                classification = 'printed_header_without_catalogue_match'
            line = header[:match.start(1)].count('\n') + 1
            quote = text.split('\n')[line-1]
            assertions.append(dict(printedIdentifier=printed,
                                   classification=classification,
                                   locator=f'lines={line}-{line}', quote=quote,
                                   textSHA256=source['textSha256'],
                                   needsHeaderContinuation=printed.endswith('-'),
                                   candidateCatalogueAssertions=[dict(documentUID=r['documentUID'],
                                       sourceDocumentId=r['sourceDocumentId'],title=r['title'],
                                       literalIdentifierEqual=r['sourceDocumentId'] == printed)
                                       for r in candidates]))
        discovery = (assertions[0]['classification'] if len(assertions) == 1 else
                     'multiple_printed_header_assertions' if assertions else
                     'no_printed_header_in_checked_prefix')
        results.append(dict(sourceIndex=index,originalSHA256=source['sourceSha256'],
                            textSHA256=source['textSha256'],discoveryState=discovery,
                            observedHeaders=assertions,catalogueIdentityAssigned=False,
                            semanticComparisonPerformed=False,currentAuthorityVerified=False))
    return dict(schemaVersion=1,kind='unassociated_catalogue_retrieval_audit',
                catalogueCount=len(rows),retainedSourceCount=len(sources),
                unassociatedSourcesAccounted=len(results),sources=results,
                discoveryCounts=dict(Counter(r['discoveryState'] for r in results)),
                checkedScope='First formfeed-delimited retained-text page, limited to6000characters; OCR may be incomplete.',
                noHeaderDoesNotExcludeCatalogueMembership=True,
                catalogueLedgerChanged=False,newRetrievalLinks=0,newSemanticAssessments=0,
                humanDecision=None,
                limitations=['Identifier/header leads are not accepted identity or current authority.',
                             'An unassessed archive-source count is not a count of active catalogue PPGs.',
                             'No-header and unmatched sources remain unresolved, not silently excluded.'])
