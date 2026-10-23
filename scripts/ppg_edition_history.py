#!/usr/bin/env python3
"""Plan native histories from established identities, never from filename similarity."""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from uuid import UUID


def plan_histories(records):
    groups, unresolved = defaultdict(list), []
    for record in records:
        uid = record.get('documentUID')
        try:
            if not UUID(uid).int:
                raise ValueError('empty UID')
        except (ValueError, TypeError, AttributeError):
            unresolved.append({'record': record, 'reason': 'no_established_identity'})
            continue
        if not record.get('identityEvidence') or not isinstance(record.get('sourceEdition'), str) or not re.fullmatch(r'\d+(?:\.\d+)*', record['sourceEdition']):
            unresolved.append({'record': record, 'reason': 'missing_identity_or_edition_evidence'})
            continue
        if not isinstance(record.get('sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', record['sha256']) or not record.get('sourcePath') or not isinstance(record.get('bytes'), int) or record['bytes'] < 1:
            unresolved.append({'record': record, 'reason': 'incomplete_capture_receipt'})
            continue
        groups[str(UUID(uid))].append(record)
    ready, singletons = [], []
    def numeric(version):
        parts = [int(p) for p in version.split('.')]
        while len(parts) > 1 and parts[-1] == 0:
            parts.pop()
        return tuple(parts)
    for uid, rows in sorted(groups.items()):
        by_hash, by_edition = defaultdict(list), defaultdict(set)
        for row in rows:
            by_hash[row['sha256']].append(row)
            by_edition[numeric(row['sourceEdition'])].add(row['sha256'])
        if any(len(hashes) > 1 for hashes in by_edition.values()) or any(len({numeric(r['sourceEdition']) for r in occurrences}) > 1 for occurrences in by_hash.values()):
            unresolved.append({'documentUID': uid, 'records': rows, 'reason': 'conflicting_edition_content_requires_explicit_order'})
            continue
        ordered = sorted((occurrences[0] for occurrences in by_hash.values()), key=lambda row: numeric(row['sourceEdition']))
        if len(ordered) == 1:
            singletons.append({'documentUID': uid, 'sha256': ordered[0]['sha256'], 'sourceEdition': ordered[0]['sourceEdition']})
            continue
        ready.append({'documentUID': uid, 'identityEvidence': [r['identityEvidence'] for r in ordered],
                      'editions': [{**r, 'order': index + 1,
                                    'orderEvidence': 'Ascending unambiguous printed edition within established DocumentUID; not source approval/capture date',
                                    'occurrences': by_hash[r['sha256']]} for index, r in enumerate(ordered)]})
    return {'ready': ready, 'singletons': singletons, 'unresolved': unresolved,
            'note': 'No target writes. Singletons are not fabricated multi-edition histories; originals remain preserved.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(plan_histories(json.loads(args.input.read_text())), indent=2) + '\n')
