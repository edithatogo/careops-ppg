"""Screen retained text for literal overlap; preserve edition and coverage gaps."""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

TOKEN = re.compile(r"\w+", re.UNICODE)
HEADER = re.compile(r'Document\s*(?:Number|No\.?)[\s:]*([A-Z][A-Z0-9.\-/]+-V[\d.]+-\d{2}/\d{2})', re.I)


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def identifiers(text):
    # A reference anywhere in a document cannot establish its own identity.
    first_page = text.split('\f', 1)[0][:4000]
    return sorted({m.group(1).upper() for m in HEADER.finditer(first_page)})


def stem(code):
    return re.sub(r'-V[\d.]+-\d{2}/\d{2}$', '', code.upper())


def excerpt(source, start, end):
    return {'sourceSha256': source['sourceSha256'], 'textSha256': source['textSha256'],
            'textPath': source.get('textPath'), 'start': start, 'end': end,
            'line': source['text'][:start].count('\n') + 1,
            'passage': source['text'][start:end]}


def overlaps(subject, comparator, words=12):
    left = list(TOKEN.finditer(subject['text']))
    right = list(TOKEN.finditer(comparator['text']))
    a = [m.group().casefold() for m in left]
    b = [m.group().casefold() for m in right]
    index = {}
    for i in range(len(a)-words+1):
        index.setdefault(tuple(a[i:i+words]), []).append(i)
    found = []
    skip = 0
    for j in range(len(b)-words+1):
        if j < skip:
            continue
        for i in index.get(tuple(b[j:j+words]), []):
            length = words
            while i+length < len(a) and j+length < len(b) and a[i+length] == b[j+length] and length < 80:
                length += 1
            found.append({'words': length,
                          'subject': excerpt(subject, left[i].start(), left[i+length-1].end()),
                          'comparator': excerpt(comparator, right[j].start(), right[j+length-1].end())})
            skip = j+length
            break
    return sorted(found, key=lambda x: x['words'], reverse=True)


def screen(subject, catalogue, sources):
    rows = catalogue['records']
    ids = [r['documentUID'] for r in rows]
    if len(ids) != catalogue['catalogueCount'] or len(ids) != len(set(ids)):
        raise ValueError('Catalogue count or identity mismatch')
    for source in [subject, *sources]:
        if digest(source['text']) != source['textSha256']:
            raise ValueError('Text provenance mismatch')
        if not re.fullmatch('[a-f0-9]{64}', source['sourceSha256']):
            raise ValueError('Original source hash required')
    source_ids = [(s['sourceSha256'], s['textSha256']) for s in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError('Duplicate corpus source/extraction')
    subject_tokens = [m.group().casefold() for m in TOKEN.finditer(subject['text'])]
    keys = {tuple(subject_tokens[i:i+12]) for i in range(len(subject_tokens)-11)}
    frequency = Counter()
    for source in sources:
        tokens = [m.group().casefold() for m in TOKEN.finditer(source['text'])]
        frequency.update({tuple(tokens[i:i+12]) for i in range(len(tokens)-11)} & keys)
    common_threshold = max(5, (len(sources)+19)//20)
    corpus = []
    by_id = {}
    for source in sources:
        codes = identifiers(source['text']) if source.get('textCoverage') != 'sampled_ocr' else []
        shared = overlaps(subject, source)
        item = {k: v for k, v in source.items() if k != 'text'}
        for pair in shared:
            tokens = [m.group().casefold() for m in TOKEN.finditer(pair['subject']['passage'])]
            pair['corpusSourceFrequency'] = frequency[tuple(tokens[:12])]
            urls = re.findall(r'https?://[^\s]+', pair['subject']['passage'])
            url_tokens = sum(len(TOKEN.findall(url)) for url in urls)
            pair['referenceTextCandidate'] = bool(urls) and url_tokens >= len(tokens)/2
        item.update(headerIdentifiers=codes,
                    literalOverlapCandidates=[p for p in shared if p['corpusSourceFrequency'] < common_threshold and not p['referenceTextCandidate']][:3],
                    commonTextMatches=[p for p in shared if p['corpusSourceFrequency'] >= common_threshold or p['referenceTextCandidate']][:3],
                    screenState='screened_literal_overlap_only', semanticReviewCompleted=False)
        corpus.append(item)
        # Conflicting first-page identities remain unbound, including quoted documents.
        if len(codes) == 1:
            by_id.setdefault(codes[0], []).append(len(corpus)-1)
    result = []
    for row in rows:
        code = row['sourceDocumentId'].upper()
        exact = by_id.get(code, [])
        other = [i for key, indexes in by_id.items() if key != code and stem(key) == stem(code) for i in indexes]
        matches = exact + other
        state = 'matching_catalogue_identifier' if exact else 'other_edition_candidate' if other else 'metadata_only'
        result.append({'documentUID': row['documentUID'], 'title': row['title'],
                       'sourceDocumentId': row['sourceDocumentId'], 'coverage': state,
                       'sourceIndexes': matches, 'matchingIdentifierSourceIndexes': exact,
                       'otherEditionSourceIndexes': other,
                       'currentAuthorityVerified': False, 'semanticReviewCompleted': False,
                       'literalOverlapCandidates': sum(len(corpus[i]['literalOverlapCandidates']) for i in matches)})
    return {'schemaVersion': 1, 'kind': 'historical_source_literal_screen',
            'requestedEditionVerified': False, 'subject': {k:v for k,v in subject.items() if k != 'text'},
            'catalogueSourceSha256': catalogue['sourceSha256'], 'catalogueCount': len(result),
            'sourceCount': len(corpus), 'commonTextThreshold': common_threshold, 'coverageCounts': dict(Counter(r['coverage'] for r in result)),
            'records': result, 'corpus': corpus, 'humanDecision': None,
            'limitations': ['Literal overlap is a retrieval lead; it does not establish duplication, conflict or consolidation.',
                           'Header identifiers match retained content to catalogue assertions; they do not establish current approval.',
                           'Other editions remain candidates; no silent replacement of the requested edition.',
                           'Text extraction and unresolved revisions may affect matches. Original files remain necessary.',
                           'Unbound sources are still screened and retained in the corpus ledger.',
                           'Sampled OCR is partial coverage and cannot establish a first-page document identity.',
                           'Frequent shared text is retained separately as possible template/common wording, not silently discarded.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    inputs = json.loads(args.input.read_text())
    result = screen(inputs['subject'], inputs['catalogue'], inputs['sources'])
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
    print(json.dumps({k:result[k] for k in ['catalogueCount','sourceCount','coverageCounts']}))
