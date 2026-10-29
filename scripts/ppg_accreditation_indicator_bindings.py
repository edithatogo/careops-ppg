# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
"""Bind prepared indicators to exact read-back catalogue identities; no native writes."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import hashlib
import json
from copy import deepcopy


def bind(prepared, native_catalogue, native_framework):
    framework = native_framework.get('FrameworkKey')
    if not framework or (type(native_framework.get('Id')) is not int or native_framework['Id'] < 1):
        raise ValueError('Read-back framework identity required')
    records = {}
    for row in native_catalogue:
        raw = row['RecordJSON']
        if hashlib.sha256(raw.encode()).hexdigest() != row['PayloadSHA256']:
            raise ValueError('Catalogue payload digest mismatch')
        record = json.loads(raw)
        key = row['RecordKey']
        if key in records or record['key'] != key or record['kind'] != row['RecordKind']:
            raise ValueError('Duplicate or inconsistent catalogue identity')
        for column, field in [('PublicationKey', 'publicationKey'), ('EditionKey', 'editionKey')]:
            if column not in row or row[column] != record.get(field):
                raise ValueError('Native catalogue relationship disagrees with payload')
        if type(row.get('Id')) is not int or row['Id'] < 1:
            raise ValueError('Native catalogue item identity required')
        records[key] = record

    def resolve(sha, url=None):
        candidates = [r for r in records.values() if r['kind'] == 'Capture'
                      and r['data'].get('sha256') == sha
                      and (url is None or r['data'].get('sourceURL') == url)]
        if len(candidates) != 1:
            raise ValueError('Unique exact source capture required')
        capture = candidates[0]
        edition = records.get(capture['editionKey'])
        publication = records.get(capture['publicationKey'])
        if (not edition or edition['kind'] != 'Edition'
                or not publication or publication['kind'] != 'Publication'
                or edition['publicationKey'] != publication['key']
                or edition['editionKey'] != edition['key']
                or publication['publicationKey'] != publication['key']
                or framework not in edition['frameworkKeys']):
            raise ValueError('Exact publication, edition and framework chain required')
        if not capture['data'].get('nativeURL'):
            raise ValueError('Native capture destination required')
        return capture

    result = deepcopy(prepared)
    for row in result['records'] + result['qualityStatements']:
        capture = resolve(row['SourceSHA256'], row.get('SourceURL'))
        row.update(FrameworkKey=framework, PublicationKey=capture['publicationKey'],
                   EditionKey=capture['editionKey'], CaptureKey=capture['key'],
                   catalogueBindingState='exact-native-catalogue-readback',
                   SourceURL=capture['data']['sourceURL'],
                   SourceCaptureURL=capture['data']['nativeURL'])
        if 'IndicatorKey' in row:
            row['IndicatorVersionKey'] = 'indicator-version:' + row['IndicatorKey'] + ':' + capture['key']
            if len(row['IndicatorVersionKey']) > 255:
                raise ValueError('Indicator version key exceeds native Text capacity')
    result['summary'].update(nativeCatalogueBindingsAvailable=len(result['records']),
                             nativeEligibleRecords=len(result['records']),
                             boundQualityStatements=len(result['qualityStatements']))
    result['summary']['nativePersistenceVerified'] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--catalogue', type=Path, required=True)
    parser.add_argument('--framework', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    framework = json.loads(args.framework.read_text())
    result = bind(json.loads(args.prepared.read_text()),
                  json.loads(args.catalogue.read_text()), framework.get('row', framework))
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result['summary'], sort_keys=True))


if __name__ == '__main__':
    main()
