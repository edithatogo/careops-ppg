"""Account for a frozen catalogue against retained text; matches are retrieval leads."""
import argparse
import hashlib
import json
from pathlib import Path


def coverage(candidate, texts):
    rows = candidate['operations']
    ids = [r['DocumentUID'] for r in rows]
    if len(ids) != len(set(ids)) or len(rows) != candidate['inputCount']:
        raise ValueError('Catalogue identity/count mismatch')
    records = []
    for row in rows:
        fields = row['fields']
        alias = fields['sourceDocumentId']
        if not isinstance(alias, str) or not alias.strip():
            raise ValueError('Missing source document identifier')
        matches = []
        for item in texts:
            start = item['text'].find(alias)
            if start >= 0:
                matches.append({'textFile': item['path'], 'textSha256': item['sha256'],
                                'line': item['text'][:start].count('\n') + 1,
                                'excerpt': item['text'][max(0, start-100):start+len(alias)+150]})
        records.append({'documentUID': row['DocumentUID'], 'sourceDocumentId': alias,
                        'title': fields['sourceTitle'],
                        'coverage': 'candidate_text_match' if matches else 'metadata_only',
                        'matches': matches, 'documentVersionVerified': False,
                        'contentComparisonCompleted': False})
    return {'schemaVersion': 1, 'sourceSha256': candidate['sourceSha256'],
            'catalogueCount': len(rows), 'retainedTextCount': len(texts),
            'matchingEntries': sum(bool(r['matches']) for r in records),
            'limitation': 'Exact identifier mentions may be references in another document. '
                          'No match does not prove absence. Current source bytes and identity require verification.',
            'records': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('text_directories', nargs='+', type=Path)
    args = parser.parse_args()
    texts = []
    for path in sorted({p for directory in args.text_directories for p in directory.glob('*.txt')}):
        raw = path.read_bytes()
        texts.append({'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                      'text': raw.decode('utf-8', errors='replace')})
    result = coverage(json.loads(args.candidate.read_text()), texts)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'records'}))
