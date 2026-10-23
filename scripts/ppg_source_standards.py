"""Preserve source standards and cached reports without accepting classifications.

Offline only. The optional XLSB reader reuses pyxlsb1.0.10 on unchanged bytes;
it reads cached values without refreshing links, calculating or running macros.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def scalar(value):
    return '' if value is None else int(value) if isinstance(value, float) and value.is_integer() else value


def extract(workbook_path, mapping):
    from pyxlsb import open_workbook
    if len(mapping) != 25 or mapping[12]['mirror_field'] != 'sourceStandard':
        raise ValueError('Qualified 25-column source field map required')
    before = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
    sheets = []
    with open_workbook(str(workbook_path)) as workbook:
        with workbook.get_sheet('Master Document Register') as sheet:
            if sheet.dimension.h > 10000 or sheet.dimension.w != len(mapping):
                raise ValueError('Unqualified main-sheet dimensions')
            rows = [[scalar(c.v) for c in row] for row in sheet.rows()]
        while rows and all(v == '' for v in rows[-1]):
            rows.pop()
        if not rows or rows[0] != [m['source_header'] for m in mapping]:
            raise ValueError('Source header drift')
        records = []
        for number, row in enumerate(rows[1:], 2):
            if len(row) != len(mapping):
                raise ValueError('Source row width mismatch')
            records.append({'sourceRow': number, 'fields': {
                m['mirror_field']: v for m, v in zip(mapping, row)}})
        for name in ['STANDARDS TRACKING', 'OVERDUE BY STANDARD']:
            with workbook.get_sheet(name) as sheet:
                if sheet.dimension.h > 10000 or sheet.dimension.w > 100:
                    raise ValueError('Unqualified tracking-sheet dimensions')
                cells = []
                for row in sheet.rows(sparse=True):
                    cells.extend({'row': c.r + 1, 'column': c.c + 1, 'value': scalar(c.v)}
                                 for c in row if c.v is not None)
                sheets.append({'name': name, 'cells': cells})
    if hashlib.sha256(workbook_path.read_bytes()).hexdigest() != before:
        raise ValueError('Workbook changed during extraction')
    return {'schemaVersion': 1, 'workbookSha256': before,
            'extraction': 'Read-only cached values; no refresh, calculation or macro execution',
            'records': records, 'sheets': sheets}


def reconcile(candidate, extracted, definitions):
    snapshot = candidate['sourceSha256']
    if (extracted.get('schemaVersion') != 1 or extracted['workbookSha256'] != snapshot
            or len(snapshot) != 64 or any(c not in '0123456789abcdef' for c in snapshot)):
        raise ValueError('Workbook and retained source snapshot differ')
    if (not isinstance(candidate.get('allowed'), list)
            or 'sourceDocumentId' not in candidate['allowed'] or candidate.get('exceptions')):
        raise ValueError('Qualified source candidate required')
    raw = candidate['rawRecords']
    expected = [{'sourceRow': r['sourceRow'], 'fields': r['fields']} for r in raw]
    if (digest(expected) != digest(extracted['records'])
            or candidate['inputCount'] != len(raw) or len(candidate['operations']) != len(raw)):
        raise ValueError('Complete raw-value parity and operation coverage required')
    operations = {}
    uids = set()
    for op in candidate['operations']:
        if not op.get('DocumentUID') or op['DocumentUID'] in uids or op['sourceRow'] in operations:
            raise ValueError('Missing/duplicate document identity or source row')
        uids.add(op['DocumentUID'])
        operations[op['sourceRow']] = op
    if len({r['sourceRow'] for r in raw}) != len(raw):
        raise ValueError('Duplicate raw source row')
    selected = definitions.get('sourceFrameworkEditionId')
    if not isinstance(selected, str) or not selected.strip():
        raise ValueError('Explicit source framework edition required')
    published = [f for f in definitions['frameworks']
                 if f['frameworkEditionId'] == selected and f['status'] == 'published']
    if len(published) != 1:
        raise ValueError('Known published candidate framework required')
    headings = {r['code']: r['requirementId'] for r in published[0]['requirements']}
    if (len(published[0]['requirements']) != 8
            or set(headings) != {str(n) for n in range(1, 9)} or len(set(headings.values())) != 8):
        raise ValueError('Known eight-heading index required')
    assertions = []
    counts = Counter()
    for row in raw:
        op = operations.get(row['sourceRow'])
        if op is None or op['fields']['sourceDocumentId'] != row['fields']['sourceDocumentId']:
            raise ValueError('Source row/document association differs')
        value = row['fields']['sourceStandard']
        token = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
        counts[token] += 1
        # Only an actual integral numeric source label supports this retrieval
        # candidate. Strings, booleans, blanks and compound labels stay unmapped.
        code = str(int(value)) if type(value) in (int, float) and value == int(value) else None
        target = headings.get(code)
        key = digest({'sourceSha256': snapshot, 'documentUID': op['DocumentUID'],
                      'sourceStandard': value})
        assertions.append({'assertionKey': key, 'documentUID': op['DocumentUID'],
            'sourceDocumentId': row['fields']['sourceDocumentId'], 'sourceRow': row['sourceRow'],
            'sourceStandard': value, 'sourceSha256': snapshot,
            'sourceField': 'sourceStandard', 'sourceSheet': 'Master Document Register',
            'sourceColumn': 13, 'sourceEdition': None,
            'status': 'candidate_requires_edition_confirmation' if target else 'unmapped_source_label',
            'candidateRequirementIds': [target] if target else [],
            'rationale': 'Numeric heading-code correspondence only; source does not identify an edition.'
                         if target else 'No supported correspondence in the checked eight-heading index.',
            'acceptedMapping': False, 'establishesCompliance': False})
    sheets = extracted['sheets']
    if {s['name'] for s in sheets} != {'STANDARDS TRACKING', 'OVERDUE BY STANDARD'} or len(sheets) != 2:
        raise ValueError('Both retained standards sheets required')
    tracking = next(s for s in sheets if s['name'] == 'STANDARDS TRACKING')
    by_row = {}
    for cell in tracking['cells']:
        coords = (cell['row'], cell['column'])
        if coords[0] < 1 or coords[1] < 1 or coords in by_row:
            raise ValueError('Invalid/duplicate worksheet cell')
        by_row[coords] = cell['value']
    cached = []
    for (number, column), label in sorted(by_row.items()):
        if column != 2 or (type(label) not in (int, float) and label != 'Grand Total'):
            continue
        count = by_row.get((number, 3))
        if type(count) not in (int, float) or count < 0 or count != int(count):
            raise ValueError('Cached tracking count missing/invalid')
        actual = len(raw) if label == 'Grand Total' else counts[json.dumps(scalar(label))]
        cached.append({'row': number, 'label': label, 'cachedCount': count,
                       'retainedMainCount': actual, 'difference': count - actual,
                       'scope': 'Cached report versus retained main rows; cause unverified'})
    summary = {'sourceRecordCount': len(raw), 'rawCellsVerified': sum(len(r['fields']) for r in raw),
        'retainedAbsentUIDCount': len(candidate.get('acknowledgedMissingUIDs', [])),
        'candidateAssertions': sum(bool(a['candidateRequirementIds']) for a in assertions),
        'unmappedAssertions': sum(not a['candidateRequirementIds'] for a in assertions),
        'acceptedMappings': 0, 'sourceWrites': 0, 'notifications': 0,
        'sourceLabelCounts': dict(sorted(counts.items())),
        'cachedTrackingDifferences': [r for r in cached if r['difference'] != 0],
        'sourceEditionVerified': False}
    return {'schemaVersion': 1, 'kind': 'source_standard_reconciliation',
        'sourceSha256': snapshot, 'candidateSha256': digest(candidate),
        'extractionSha256': digest(extracted), 'frameworkDefinitionsSha256': digest(definitions),
        'summary': summary, 'assertions': assertions, 'cachedTrackingComparison': cached,
        'limitations': ['Candidate headings are not accepted classifications or compliance evidence.',
            'Source numeric labels do not identify a framework edition; no draft crosswalk inferred.',
            'Cached tracking cells are preserved, not recalculated or corrected.',
            'Overdue-sheet counts have an unverified filter scope; not active-catalogue totals.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--workbook', type=Path, required=True)
    parser.add_argument('--definitions', type=Path, required=True, help='Reviewed input with explicit sourceFrameworkEditionId; no bundled policy data')
    parser.add_argument('--mapping', type=Path, default=Path('config/source-field-map.csv'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Output exists; preserve prior evidence')
    with args.mapping.open(newline='') as stream:
        extracted = extract(args.workbook, list(csv.DictReader(stream)))
    result = reconcile(json.loads(args.candidate.read_text()), extracted,
                       json.loads(args.definitions.read_text()))
    args.output.mkdir(parents=True, exist_ok=False)
    for name, payload in [('workbook-extract.json', extracted), ('reconciliation.json', result),
                          ('summary.json', result['summary'])]:
        with (args.output / name).open('x') as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['summary']))


if __name__ == '__main__':
    main()
