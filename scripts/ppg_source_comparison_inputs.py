"""Qualify retained native XLSB acquisitions for read-only source comparison.

Reuses the baseline extraction route (pyxlsb 1.0.10); no tenant calls, macros,
identity amendments, importer writes or checkpoint changes.
"""
import argparse
import base64
import csv
import hashlib
import json
import tempfile
from pathlib import Path

from ppg_source_sync import digest, prepare
from ppg_source_comparison import compare, render


def extract(envelope, mapping):
    from pyxlsb import open_workbook
    binary = base64.b64decode(envelope['binary']['$content'], validate=True)
    if len(binary) != int(envelope['metadata']['Length']):
        raise ValueError('acquisition length mismatch')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'working-copy.xlsb'
        path.write_bytes(binary)
        with open_workbook(str(path)) as workbook:
            with workbook.get_sheet('Master Document Register') as sheet:
                if sheet.dimension.h > 10000 or sheet.dimension.w != 25:
                    raise ValueError('unqualified source dimensions')
                rows = [[cell.v for cell in row] for row in sheet.rows()]
    while rows and not any(value not in (None, '') for value in rows[-1]):
        rows.pop()
    if not rows or rows[0] != [m['source_header'] for m in mapping]:
        raise ValueError('source header drift')
    def scalar(value):
        # Office Script getValues uses empty strings and JSON integer numbers.
        return '' if value is None else int(value) if isinstance(value, float) and value.is_integer() else value
    records = []
    for number, row in enumerate(rows[1:], 2):
        if len(row) != len(mapping):
            raise ValueError('source row width mismatch')
        records.append({'sourceRow': number, 'fields': {
            column['mirror_field']: scalar(value) for column, value in zip(mapping, row)}})
    return hashlib.sha256(binary).hexdigest(), records


def qualify(baseline, baseline_raw, observed_raw, checkpoint, state, ledger, cases, mapping, observed_ref=''):
    old_hash, old_records = extract(baseline_raw, mapping)
    new_hash, new_records = extract(observed_raw, mapping)
    if (checkpoint['status'] != 'completed' or
            old_hash != checkpoint['sourceSha256'] or old_hash != baseline['sourceSha256'] or
            baseline['inputCount'] != checkpoint['readbackCount'] or
            baseline_raw['metadata']['ETag'] != checkpoint['centralSourceETag'] or
            baseline['contractHash'] != checkpoint['identityContractHash']):
        raise ValueError('committed baseline mismatch')
    native_records = [{'sourceRow': r['sourceRow'], 'fields': r['fields']} for r in baseline['rawRecords']]
    if digest(old_records) != digest(native_records):
        raise ValueError('parser does not reproduce native baseline raw values')
    if (observed_raw['metadata']['ETag'] != state['sourceETag'] or
            observed_raw['metadata']['UniqueId'] != baseline_raw['metadata']['UniqueId']):
        raise ValueError('observed source binding mismatch')
    aliases = [{'source': ledger['sourceSystemId'], 'alias': a['sourceDocumentId'],
                'DocumentUID': a['documentUID']} for a in ledger['aliases']]
    if digest(aliases) != baseline['contractHash']:
        raise ValueError('identity contract changed; explicit qualification required')
    candidate = prepare({'sourceSha256': new_hash, 'records': new_records,
                         'sourceSheet': 'Master Document Register'}, ledger['sourceSystemId'],
                        aliases, {'sourceDocumentId'})
    candidate['provenance'].update({'acquiredAtUtc': observed_raw['acquiredAtUtc'],
                                   'rawSnapshotRef': observed_ref,
                                   'sourceETag': observed_raw['metadata']['ETag'],
                                   'extractionMode': 'read-only cached XLSB values; native baseline parity verified'})
    report = compare(baseline, candidate, cases)
    report['qualification'] = {'nativeBaselineParityCells': len(old_records) * len(mapping),
                               'baselineReadbackCount': checkpoint['readbackCount'],
                               'observedRecordCount': len(new_records),
                               'sourceCheckUtc': state['checkedUtc'],
                               'caseCount': len(cases), 'refreshMode': 'manual-frozen-snapshot',
                               'checkpointSHA256': digest(checkpoint), 'sourceStateSHA256': digest(state),
                               'observedAcquisitionSHA256': digest(observed_raw)}
    return candidate, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'baseline-raw', 'observed-raw', 'checkpoint', 'state', 'ledger', 'cases'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--mapping', type=Path, default=Path(__file__).resolve().parents[1] / 'config/source-field-map.csv')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--observed-ref', required=True, help='Canonical retained raw acquisition URL')
    args = parser.parse_args()
    with args.mapping.open(newline='') as stream:
        mapping = list(csv.DictReader(stream))
    candidate, report = qualify(*(json.loads(getattr(args, name).read_text()) for name in
                                ('baseline', 'baseline_raw', 'observed_raw', 'checkpoint', 'state', 'ledger', 'cases')), mapping, args.observed_ref)
    args.output.mkdir(parents=True, exist_ok=False)
    for filename, value in [('candidate.json', candidate), ('comparison.json', report)]:
        (args.output / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2))
    (args.output / 'comparison.html').write_text(render(report))


if __name__ == '__main__':
    main()
