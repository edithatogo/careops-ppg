#!/usr/bin/env python3
"""Independently verify a saved native CSV against its committed source candidate."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re


def classify(month, report_month):
    if not isinstance(month, str) or not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', month) or month[:4] == '0000':
        return 'Date exception'
    year, number = map(int, report_month.split('-'))
    end = year * 12 + number - 1 + 3
    end_month = f'{end // 12:04d}-{end % 12 + 1:02d}'
    if month < report_month:
        return 'Overdue'
    if month == report_month:
        return 'Due this month'
    if month <= end_month:
        return 'Due next three months'
    return 'Later'


def safe_text(value):
    value = '' if value is None else str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r')) else value


def verify(candidate, rows, report_month=None):
    expected = {o['DocumentUID']: o for o in candidate['operations']}
    raw = {r['sourceRow']: r['fields'] for r in candidate['rawRecords']}
    months = {r['Report month'] for r in rows}
    if report_month:
        months.add(report_month)
    if len(months) != 1:
        raise ValueError('Missing or mixed report months; supply --month for empty reports')
    month = months.pop()
    reportable = {uid for uid, op in expected.items()
                  if classify(op['fields'].get('sourceNextReviewMonth'), month) != 'Later'}
    ids = [r['DocumentUID'] for r in rows]
    if len(ids) != len(set(ids)) or set(ids) != reportable:
        raise ValueError('Missing, duplicated or unexpected report identities')
    mapped = {'Review month': 'sourceNextReviewMonth', 'Custodian': 'sourceCustodian',
              'Document ID': 'sourceDocumentId', 'Title': 'sourceTitle',
              'Source status': 'sourceStatus', 'Risk': 'sourceRisk',
              'Review date raw': 'sourceNextReviewDateRaw', 'Evidence': 'rawSourceRecordRef'}
    routes = {'Authorising officer': 'sourceAuthorisingOfficer',
              'Operational hierarchy': 'sourceExecutiveHierarchy', 'Service director': 'sourceServiceDirector',
              'Service': 'sourceServiceIndex', 'Source comments': 'sourceComments'}
    for row in rows:
        op = expected[row['DocumentUID']]
        fields = op['fields']
        facts = raw[op['sourceRow']]
        if row['Bucket'] != classify(fields.get('sourceNextReviewMonth'), month):
            raise ValueError('Incorrect month bucket')
        for column, source in mapped.items():
            if row[column] != safe_text(fields.get(source)):
                raise ValueError(f'Source mismatch: {column}')
        for column, source in routes.items():
            if row[column] != safe_text(facts.get(source)):
                raise ValueError(f'Route/source mismatch: {column}')
        if row['Source SHA256'] != candidate['sourceSha256'] or not row['Freshness'] or not row['Generated UTC']:
            raise ValueError('Missing or mismatched provenance')
    return {'rows': len(rows), 'uniqueIdentities': len(set(ids)), 'month': month,
            'buckets': dict(Counter(r['Bucket'] for r in rows)), 'allSourceAndRouteFieldsMatch': True, 'catalogueRows': candidate['inputCount'],
            'laterAccounted': candidate['inputCount'] - len(rows)}


def verify_retained(candidate, checkpoint, catalogue, rows):
    """Check every original retained field independently of the native flow."""
    from ppg_source_sync import retention_contract
    from ppg_monthly_report import SOURCE_FIELDS
    contract = retention_contract(candidate, checkpoint, catalogue)
    expected = {r['DocumentUID']:r for r in catalogue if r['DocumentUID'] in contract['retainedUIDs']}
    ids = [r['DocumentUID'] for r in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError('Retained identity accounting mismatch')
    for row in rows:
        for key in SOURCE_FIELDS:
            value = expected[row['DocumentUID']].get(key)
            if key == 'sourceRowNumber' and isinstance(value, (int, float)) and not isinstance(value, bool) and int(value) == value:
                value = int(value)
            if row[key] != safe_text(value):
                raise ValueError('Retained original field mismatch: ' + key)
        if row['Accounting'] != 'Retained source absence; current clinical status unresolved; original recorded fields preserved':
            raise ValueError('Retained source absence meaning missing')
    return {'activeSourceRows':len(contract['activeUIDs']), 'retainedAbsentRows':len(rows),
            'totalCatalogueIdentities':len(contract['catalogueUIDs']), 'allRetainedOriginalFieldsMatch':True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--csv', type=Path, required=True)
    parser.add_argument('--month', help='YYYY-MM; required for an empty report')
    args = parser.parse_args()
    with args.csv.open(newline='', encoding='utf-8-sig') as stream:
        result = verify(json.loads(args.candidate.read_text()), list(csv.DictReader(stream)), args.month)
    print(json.dumps(result, indent=2))
