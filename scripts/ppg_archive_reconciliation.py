#!/usr/bin/env python3
"""Read-only archive coverage by content hash; never infer editions from URLs."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

DOCUMENTS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.xlsb', '.rtf', '.ppt', '.pptx', '.odt'}


def reconcile(occurrences, uploaded_hashes, copies, root):
    groups = defaultdict(list)
    for row in occurrences:
        groups[row['sha256']].append(row)
    result = []
    for sha, rows in sorted(groups.items()):
        sizes = {r['bytes'] for r in rows}
        if len(sizes) != 1:
            raise ValueError('Conflicting sizes for identical hash')
        local = []
        for row in copies:
            if row['sha256'] != sha or not row.get('local_copy'):
                continue
            path = root / row['local_copy']
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != sha or len(raw) not in sizes:
                raise ValueError('Local capture hash/size mismatch')
            local.append(str(path.resolve()))
        result.append({'sha256': sha, 'bytes': next(iter(sizes)),
                       'isDocument': any(r.get('format', '').lower() in DOCUMENTS for r in rows),
                       'coveredByOriginal533': sha in uploaded_hashes,
                       'verifiedLocalCopies': sorted(set(local)), 'occurrences': rows})
    docs = [r for r in result if r['isDocument']]
    missing = [r for r in docs if not r['coveredByOriginal533']]
    return {'schemaVersion': 1, 'scope': 'Retained inventories; original ZIP audit pending',
            'occurrenceCount': len(occurrences), 'distinctCount': len(result),
            'documentDistinctCount': len(docs), 'missingDocumentDistinctCount': len(missing),
            'missingDocumentsWithLocalBytes': sum(bool(r['verifiedLocalCopies']) for r in missing),
            'records': result}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('collection', type=Path)
    parser.add_argument('uploaded_manifest', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    load = lambda name: json.loads((args.collection / name).read_text())
    manifest = json.loads(args.uploaded_manifest.read_text())
    output = reconcile(load('inventory.json'), {r['sha256'] for r in manifest['files']},
                       load('combined-collection.json'), args.collection)
    args.output.write_text(json.dumps(output, indent=2))
    print(json.dumps({k: v for k, v in output.items() if k != 'records'}))
