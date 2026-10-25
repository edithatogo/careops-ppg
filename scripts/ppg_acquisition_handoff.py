"""Bind supplied acquisition evidence to a consumer-selected existing capture.

Offline preparation only. Never assigns publication/edition identity or writes
native records. The catalogue remains the sole writer and validates its full v1
manifest before persistence. Supplied JSON does not authenticate a native run.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from ppg_url_acquisition_qualification import _profile, MAX_BYTES


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _text(value, limit=2048):
    if (not isinstance(value, str) or not value or len(value) > limit
            or any(ord(c) < 32 for c in value)):
        raise ValueError('Bounded literal text required')
    return value


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Lowercase SHA-256 required')
    return value


def _url(value, origins=None, native=False):
    _text(value)
    u = urlsplit(value)
    if (u.scheme != 'https' or not u.hostname or u.username or u.password
            or u.port not in (None, 443) or u.fragment or '\\' in value
            or any(c.isspace() for c in value)):
        raise ValueError('Literal HTTPS locator required')
    if origins is not None and 'https://' + u.hostname.lower() not in origins:
        raise ValueError('Locator outside selected source origins')
    if native and (not u.hostname.endswith('.sharepoint.com') or u.query):
        raise ValueError('Stable query-free SharePoint original link required')
    return value


def _record(value, kind):
    fields = {'key', 'kind', 'title', 'issuer', 'publicationKey', 'editionKey',
              'frameworkKeys', 'sourceStatus', 'role', 'requiredCapture', 'assertions', 'data'}
    if not isinstance(value, dict) or set(value) != fields or value['kind'] != kind:
        raise ValueError('Complete consumer-selected catalogue record required')
    if not isinstance(value['key'], str) or not re.fullmatch('[a-z0-9][a-z0-9:._-]{0,199}', value['key']):
        raise ValueError('Existing catalogue key required')
    if (not isinstance(value['data'], dict) or not isinstance(value['assertions'], list)
            or not value['assertions'] or not isinstance(value['frameworkKeys'], list)
            or any(not isinstance(k, str) for k in value['frameworkKeys'])
            or len(set(value['frameworkKeys'])) != len(value['frameworkKeys'])):
        raise ValueError('Catalogue assertions, data and framework keys required')
    if value['data'].get('clinicalApplicabilityAccepted', False) is not False:
        raise ValueError('Acquisition cannot accept clinical applicability')
    return value


def prepare(selection, profile, native_result, observation, original, url_evidence=()):
    """Compare bytes and existing endpoints; return a non-mutating reuse/hold handoff."""
    profile = _profile(profile)
    if not isinstance(selection, dict) or set(selection) != {'publication', 'edition', 'capture', 'knownFrameworkKeys'}:
        raise ValueError('Exact consumer selection required')
    pub = _record(selection['publication'], 'Publication')
    cap = _record(selection['capture'], 'Capture')
    edition = None if selection['edition'] is None else _record(selection['edition'], 'Edition')
    if pub['publicationKey'] != pub['key'] or pub['editionKey'] is not None or cap['publicationKey'] != pub['key']:
        raise ValueError('Publication endpoint differs')
    known = selection['knownFrameworkKeys']
    if not isinstance(known, list) or any(not isinstance(k, str) for k in known) or len(set(known)) != len(known):
        raise ValueError('Explicit known framework keys required')
    for row in [pub, cap] + ([edition] if edition else []):
        if not set(row['frameworkKeys']) <= set(known):
            raise ValueError('Unknown framework endpoint')
    if edition:
        if (edition['publicationKey'] != pub['key'] or edition['editionKey'] != edition['key']
                or cap['editionKey'] != edition['key'] or profile['frameworkEditionId'] not in edition['frameworkKeys']
                or profile['frameworkEditionId'] not in cap['frameworkKeys']):
            raise ValueError('Edition or framework binding differs')
    elif cap['editionKey'] is not None or cap['data'].get('editionResolution') != 'unverified':
        raise ValueError('Unknown edition must remain explicitly unverified')
    data = cap['data']
    if (not isinstance(original, bytes) or not 0 < len(original) <= MAX_BYTES
            or len(original) != profile['expectedBytes'] or digest(original) != profile['expectedSHA256']
            or type(data.get('bytes')) is not int or data['bytes'] != len(original)
            or _sha(data.get('sha256')) != digest(original)):
        raise ValueError('Selected capture and independent original bytes differ')
    source = _url(data.get('sourceURL'), profile['allowedOrigins'])
    native_url = _url(data.get('nativeURL'), native=True)
    fields = {'kind', 'qualificationId', 'sourceKey', 'actualBytes', 'actualSHA256', 'expectedSHA256',
              'integrityMatches', 'sourceProvenanceAuthenticated', 'nativeAcquisitionQualified'}
    if (not isinstance(native_result, dict) or set(native_result) != fields
            or native_result['kind'] != 'ppg-supplied-byte-hash-result-v1'
            or native_result['qualificationId'] != profile['qualificationId']
            or native_result['sourceKey'] != profile['sourceKey']
            or type(native_result['actualBytes']) is not int or native_result['actualBytes'] != len(original)
            or native_result['actualSHA256'] != digest(original)
            or native_result['expectedSHA256'] != profile['expectedSHA256']
            or native_result['integrityMatches'] is not True
            or native_result['sourceProvenanceAuthenticated'] is not False
            or native_result['nativeAcquisitionQualified'] is not False):
        raise ValueError('Supplied native result does not match independent bytes/profile')
    if not isinstance(observation, dict) or set(observation) != {'observedAt', 'workflowId', 'runId', 'sourceFile', 'receiptSHA256'}:
        raise ValueError('Exact acquisition occurrence required')
    when = _text(observation['observedAt'], 80)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})', when) or datetime.fromisoformat(when).utcoffset() is None:
        raise ValueError('Timezone-bearing occurrence time required')
    for key in ['workflowId', 'runId']:
        _text(observation[key], 160)
    _sha(observation['receiptSHA256'])
    file = observation['sourceFile']
    if not isinstance(file, dict) or set(file) != {'uniqueId', 'nativeVersion', 'etag', 'url', 'bytes'}:
        raise ValueError('Exact observed native file pin required')
    for key in ['uniqueId', 'nativeVersion', 'etag']:
        _text(file[key], 160)
    if file['etag'] == '*' or type(file['bytes']) is not int or file['bytes'] != len(original):
        raise ValueError('Stable observed native file pin required')
    _url(file['url'], native=True)
    # Retain literal locators. Equal content never silently normalises URLs.
    evidence = {}
    if not isinstance(url_evidence, (list, tuple)) or len(url_evidence) > 8:
        raise ValueError('Bounded explicit URL evidence required')
    for e in url_evidence:
        if not isinstance(e, dict) or set(e) != {'url', 'sha256', 'bytes', 'receiptSHA256'}:
            raise ValueError('Exact URL byte-evidence entry required')
        url = _url(e['url'], profile['allowedOrigins'])
        if url in evidence or _sha(e['sha256']) != digest(original) or type(e['bytes']) is not int or e['bytes'] != len(original):
            raise ValueError('Conflicting or duplicate URL byte evidence')
        _sha(e['receiptSHA256']); evidence[url] = copy.deepcopy(e)
    locator_bound = source == profile['sourceURL'] or {source, profile['sourceURL']} <= evidence.keys()
    state = 'reuse-existing-capture' if edition and locator_bound else ('held-edition-unverified' if not edition else 'held-locator-evidence')
    binding = {'publicationKey': pub['key'], 'editionKey': cap['editionKey'], 'captureKey': cap['key'],
               'requestedSourceURL': profile['sourceURL'], 'sha256': digest(original)}
    occurrence = {**binding, 'workflowId': observation['workflowId'], 'runId': observation['runId'], 'sourceFile': file}
    return {'kind': 'ppg-acquisition-existing-capture-handoff-v1', 'state': state,
            'binding': binding, 'replayKey': digest(canonical(binding).encode()),
            'occurrenceKey': digest(canonical(occurrence).encode()), 'observation': copy.deepcopy(observation),
            'catalogueSourceURL': source, 'existingRetainedOriginalURL': native_url,
            'sourceLocatorExact': source == profile['sourceURL'], 'providedURLByteEvidence': list(evidence.values()),
            'selectedRecords': copy.deepcopy(selection),
            'selectedRecordSHA256': {row['key']: digest(canonical(row).encode()) for row in [pub, cap] + ([edition] if edition else [])},
            'suppliedHashResultMatchesIndependentBytes': True, 'providedEvidenceAuthenticated': False,
            'nativeMutationAllowed': False, 'checkpointAllowed': False, 'fullAcquisitionQualified': False,
            'catalogueEdits': [], 'originalFilesToCreate': [], 'clinicalApplicabilityAccepted': False}


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def read_json(path):
    with path.open('rb') as f:
        raw = f.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('JSON input limit exceeded')
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['selection', 'profile', 'native-result', 'observation', 'original', 'output']:
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--url-evidence', type=Path)
    args = parser.parse_args(argv)
    with args.original.open('rb') as f:
        raw = f.read(MAX_BYTES + 1)
    result = prepare(read_json(args.selection), read_json(args.profile), read_json(args.native_result),
                     read_json(args.observation), raw, read_json(args.url_evidence) if args.url_evidence else [])
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
