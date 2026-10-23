"""Inventory recorded role labels without resolving people, roles or authority."""
import argparse
import hashlib
import json
from pathlib import Path

FIELDS = ('sourceCustodian', 'sourceAuthorisingOfficer',
          'sourceExecutiveHierarchy', 'sourceServiceDirector')
STATES = ('sourceStatus', 'sourceStatusCategory')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def inventory(candidate):
    snapshot = candidate.get('sourceSha256', '')
    raw, operations = candidate.get('rawRecords'), candidate.get('operations')
    if (len(snapshot) != 64 or any(c not in '0123456789abcdef' for c in snapshot)
            or not isinstance(raw, list) or not isinstance(operations, list)
            or candidate.get('exceptions') or candidate.get('inputCount') != len(raw)
            or len(raw) != len(operations)):
        raise ValueError('Complete qualified source candidate required')
    by_row, uids = {}, set()
    for op in operations:
        uid, row = op.get('DocumentUID'), op.get('sourceRow')
        if (not isinstance(uid, str) or not uid or uid in uids
                or type(row) is not int or row < 1 or row in by_row):
            raise ValueError('Missing/duplicate stable identity or source row')
        by_row[row] = op; uids.add(uid)
    records, labels, seen = [], {}, set()
    for row in raw:
        number, fields = row.get('sourceRow'), row.get('fields')
        if (type(number) is not int or number < 1 or number in seen
                or number not in by_row or not isinstance(fields, dict)):
            raise ValueError('Incomplete source-row accounting')
        seen.add(number)
        if not set(FIELDS + STATES) <= set(fields):
            raise ValueError('Missing role/state source field')
        assertions = {}
        for name in FIELDS + STATES:
            value = fields[name]
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError('Unsupported source assertion')
            key = digest({'field': name, 'rawValue': value})
            entry = labels.setdefault(key, dict(field=name, rawValue=value,
                recordCount=0, confirmedRoleId=None, confirmedHolderId=None))
            entry['recordCount'] += 1
            assertions[name] = dict(rawValue=value, labelKey=key,
                classification='missing' if value is None or value == '' else
                'unclassified_source_assertion' if isinstance(value, str) else 'non_text_source_assertion')
        records.append(dict(documentUID=by_row[number]['DocumentUID'], sourceRow=number,
                            sourceSnapshot=snapshot, assertions=assertions))
    if seen != set(by_row):
        raise ValueError('Unaccounted operation')
    summary = {name: dict(records=len(records), distinctRawValues=sum(x['field'] == name for x in labels.values()),
        missing=sum(r['assertions'][name]['classification'] == 'missing' for r in records),
        nonText=sum(r['assertions'][name]['classification'] == 'non_text_source_assertion' for r in records))
        for name in FIELDS + STATES}
    return dict(schemaVersion=1, sourceSnapshot=snapshot, inputDigest=digest(candidate),
                recordCount=len(records), records=records, labels=sorted(labels.values(), key=lambda x:(x['field'],digest(x['rawValue']))),
                summary=summary, absentSourceCapabilities=['author', 'review_lead', 'appointments', 'accepted_handovers'],
                acceptedMappings=[], assignmentsCreated=0, sourceWrites=False, grantsAccess=False,
                grantsClinicalAuthority=False, scope='Retained snapshot assertions only; labels may name people, roles, groups or combinations. No automatic equivalence or conflict decision.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = inventory(json.loads(args.candidate.read_text()))
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'records': result['recordCount'], 'assignmentsCreated': 0, 'sourceWrites': False}))
