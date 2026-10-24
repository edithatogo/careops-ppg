"""Atlas evidence -> existing PPG supporting attachments; no network or writes.

The caller supplies the qualified Atlas response model and an existing GET-only
client. This module creates no service, credentials, identity crosswalk or policy
judgement. Use qualify_atlas_adapter.py for the isolated fictional demonstration.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime

MAX_BYTES = 1024 * 1024
ATLAS_COMMIT = '21f7721a8971ca6c9e704924503eebdd75356dce'
CONTRACT_SHA256 = 'b73e35c727fdedce6b8da729a0d9c3939368c2bfb47cbc52012ca004af80d141'
PATH = '/api/v1/evidence'

class AdapterError(ValueError):
    """No usable supporting evidence was produced."""

def digest(value):
    return hashlib.sha256(value).hexdigest()

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')

def clock(value):
    if not isinstance(value, str) or len(value) > 40:
        raise AdapterError('invalid_clock')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError()
        return parsed
    except ValueError as exc:
        raise AdapterError('invalid_clock') from exc

def query_parameters(query):
    if not isinstance(query, dict) or set(query) not in (
        {'valid_at', 'observed_at', 'concept_id'},
        {'valid_at', 'observed_at', 'assertion_id'},
    ):
        raise AdapterError('one_lookup_key_and_clocks_required')
    concept = query.get('concept_id', query.get('assertion_id'))
    if not isinstance(concept, str) or not concept.strip() or len(concept) > 512:
        raise AdapterError('invalid_lookup_id')
    clock(query['valid_at']); clock(query['observed_at'])
    return {**query, 'limit': 50}

def capture(client, query):
    """Use only the selected relative API route on an already qualified client.

    No URL/origin, CaseUID, private text, provenance URL or redirect is accepted.
    The qualified caller owns the transport; this release demonstrates TestClient
    only and does not configure a remote production transport.
    """
    # This release supports the qualified in-process TestClient origin only.
    # A real deployment transport needs its own endpoint/access qualification.
    if str(getattr(client, 'base_url', '')).rstrip('/') != 'http://testserver':
        raise AdapterError('unqualified_origin')
    response = client.get(PATH, params=query_parameters(query), follow_redirects=False)
    if response.status_code != 200:
        raise AdapterError('lookup_denied' if response.status_code in (401, 403) else 'lookup_unavailable')
    raw = response.content
    if len(raw) > MAX_BYTES:
        raise AdapterError('response_oversize')
    return {'bytes': raw, 'sha256': digest(raw)}

def supporting_files(raw, query, case_uid, revision, response_model, expected_response_sha256):
    """Validate exact Atlas contract, bind the query, retain unchanged raw bytes."""
    query_parameters(query)
    for value in (case_uid, revision):
        if not isinstance(value, str) or not value.strip() or len(value) > 128:
            raise AdapterError('explicit_local_identity_required')
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise AdapterError('response_oversize')
    if digest(raw) != expected_response_sha256:
        raise AdapterError('response_hash_mismatch')
    try:
        value = json.loads(raw)
        response_model.model_validate_json(raw, strict=True)
    except (ValueError, TypeError) as exc:
        raise AdapterError('schema_drift') from exc
    metadata = value['metadata']; page = metadata['page']; items = value['evidence']
    if metadata.get('api_version') != 'v1' or metadata.get('evidence_version') != '0.6':
        raise AdapterError('schema_drift')
    if page.get('next_cursor') is not None or page['returned'] != len(items) or page['limit'] != 50:
        raise AdapterError('incomplete_page')
    if not items:
        raise AdapterError('no_evidence_no_conclusion')
    for field in ('valid_at', 'observed_at'):
        if clock(metadata['clocks'][field]) != clock(query[field]):
            raise AdapterError('query_clock_mismatch')
    assertions = set(); source_hashes = {}
    for item in items:
        lookup_key = 'concept_id' if 'concept_id' in query else 'assertion_id'
        if item[lookup_key] != query[lookup_key]:
            raise AdapterError('lookup_identity_mismatch')
        # Each assertion belongs to a jurisdiction/dimension; never merge them.
        identity = (item['assertion_id'], item['jurisdiction'], item['dimension'])
        if identity in assertions:
            raise AdapterError('duplicate_assertion')
        assertions.add(identity)
        for field in ('valid_at', 'observed_at'):
            if clock(item['valid_time'][field]) != clock(query[field]):
                raise AdapterError('query_clock_mismatch')
        provenance = item['provenance']
        source_key = (provenance['source_id'], provenance['source_uri'], provenance.get('source_version'))
        source_hash = provenance.get('source_sha256')
        if source_key[2] and source_hash:
            if source_key in source_hashes and source_hashes[source_key] != source_hash:
                raise AdapterError('contradictory_provenance')
            source_hashes[source_key] = source_hash
    receipt = {
        'schemaVersion': 1, 'CaseUID': case_uid, 'outputRevision': revision,
        'adapter': 'ppg-atlas-evidence-v1', 'atlasCommit': ATLAS_COMMIT,
        'atlasContractSHA256': CONTRACT_SHA256, 'request': {'method': 'GET', 'path': PATH, 'query': query_parameters(query)},
        'responseSHA256': digest(raw), 'responseBytes': len(raw),
        'metadata': metadata, 'sourcePins': [
            {**{key: item[key] for key in ('assertion_id', 'concept_id', 'jurisdiction', 'dimension', 'state', 'provenance', 'valid_time')},
             'sourceIntegrity': 'unverified', 'sourceBytesVerified': False,
             'sourcePinsComplete': bool(item['provenance'].get('source_sha256') and item['provenance'].get('source_version')),
             'reason': ('Source bytes were not retrieved or verified' if item['provenance'].get('source_sha256') and item['provenance'].get('source_version')
                        else 'Source hash or version absent; retained as unknown, not inferred')}
            for item in items],
        'status': 'SUPPORTING EVIDENCE / HUMAN CHECK REQUIRED',
        'sourceWrites': False, 'caseWrites': False, 'sent': False, 'policyApproved': False,
        'qualification': 'Local fictional API lookup; no hosted service or clinical acceptance',
        'responseBytesVerified': True, 'sourceBytesVerified': False,
    }
    return [
        {'name': 'atlas-response.json', 'role': 'supporting', 'sourceReference': 'Atlas ' + ATLAS_COMMIT + ' ' + digest(raw), 'bytes': raw},
        {'name': 'atlas-receipt.json', 'role': 'supporting', 'sourceReference': 'Local linkage; not an approval or identity crosswalk', 'bytes': encoded(receipt)},
    ]


def comparison_parameters(query):
    """Select existing concept/jurisdiction/dimension cells, never infer gaps."""
    import re
    if not isinstance(query, dict) or set(query) != {
        'concept_id', 'jurisdictions', 'dimensions', 'valid_at', 'observed_at'
    }:
        raise AdapterError('explicit_comparison_filters_required')
    query_parameters({key: query[key] for key in ('concept_id', 'valid_at', 'observed_at')})
    for field, maximum in (('jurisdictions', 50), ('dimensions', 3)):
        values = query[field]
        if (not isinstance(values, list) or not 1 <= len(values) <= maximum
                or any(not isinstance(v, str) for v in values)
                or len(values) != len(set(values))):
            raise AdapterError('invalid_comparison_filters')
    if (any(not re.fullmatch(r'[A-Z]{2,3}', v) for v in query['jurisdictions'])
            or set(query['dimensions']) - {'regulatory', 'funding', 'formulary'}):
        raise AdapterError('invalid_comparison_filters')
    return {**query, 'limit': 50}


def capture_comparison(client, query):
    """Use the existing read-only comparisons route on qualified TestClient."""
    parameters = comparison_parameters(query)
    if str(getattr(client, 'base_url', '')).rstrip('/') != 'http://testserver':
        raise AdapterError('unqualified_origin')
    response = client.get('/api/v1/comparisons', params=parameters, follow_redirects=False)
    if response.status_code != 200:
        raise AdapterError('lookup_denied' if response.status_code in (401, 403) else 'lookup_unavailable')
    if len(response.content) > MAX_BYTES:
        raise AdapterError('response_oversize')
    return {'bytes': response.content, 'sha256': digest(response.content)}


def supporting_comparison_files(raw, query, case_uid, revision, response_model, expected_response_sha256):
    """Retain actual absence conclusions without manufacturing evidence rows."""
    parameters = comparison_parameters(query)
    for value in (case_uid, revision):
        if not isinstance(value, str) or not value.strip() or len(value) > 128:
            raise AdapterError('explicit_local_identity_required')
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise AdapterError('response_oversize')
    if digest(raw) != expected_response_sha256:
        raise AdapterError('response_hash_mismatch')
    try:
        value = json.loads(raw)
        response_model.model_validate_json(raw, strict=True)
    except (ValueError, TypeError) as exc:
        raise AdapterError('schema_drift') from exc
    metadata = value['metadata']; page = metadata['page']; conclusions = value['conclusions']
    if metadata.get('api_version') != 'v1' or metadata.get('evidence_version') != '0.6':
        raise AdapterError('schema_drift')
    if page.get('next_cursor') is not None or page['returned'] != len(conclusions) or page['limit'] != 50:
        raise AdapterError('incomplete_page')
    if not conclusions:
        raise AdapterError('no_evidence_no_conclusion')
    for field in ('valid_at', 'observed_at'):
        if clock(metadata['clocks'][field]) != clock(query[field]):
            raise AdapterError('query_clock_mismatch')
    seen = set(); source_hashes = {}
    for item in conclusions:
        if item['concept_id'] != query['concept_id']:
            raise AdapterError('lookup_identity_mismatch')
        if item['jurisdiction'] not in query['jurisdictions'] or item['dimension'] not in query['dimensions']:
            raise AdapterError('comparison_filter_mismatch')
        key = (item['concept_id'], item['jurisdiction'], item['dimension'])
        if key in seen:
            raise AdapterError('duplicate_conclusion')
        seen.add(key)
        for field in ('valid_at', 'observed_at'):
            if clock(item['valid_time'][field]) != clock(query[field]):
                raise AdapterError('query_clock_mismatch')
        if item['state'] in ('unknown', 'not_covered') and item.get('status_code') is not None:
            raise AdapterError('absence_cannot_imply_status')
        for provenance in item['provenance']:
            key = (provenance['source_id'], provenance['source_uri'], provenance.get('source_version'))
            source_hash = provenance.get('source_sha256')
            if key[2] and source_hash:
                if key in source_hashes and source_hashes[key] != source_hash:
                    raise AdapterError('contradictory_provenance')
                source_hashes[key] = source_hash
    receipt = {
        'schemaVersion': 1, 'CaseUID': case_uid, 'outputRevision': revision,
        'adapter': 'ppg-atlas-comparison-v1', 'atlasCommit': ATLAS_COMMIT,
        'atlasContractSHA256': CONTRACT_SHA256,
        'request': {'method': 'GET', 'path': '/api/v1/comparisons', 'query': parameters},
        'responseSHA256': digest(raw), 'responseBytes': len(raw), 'metadata': metadata,
        'conclusions': conclusions, 'validity': value.get('validity', []),
        'missingCellsInferred': False, 'responseBytesVerified': True, 'sourceBytesVerified': False,
        'sourceIntegrity': 'unverified; original source bytes were not retrieved',
        'status': 'SUPPORTING EVIDENCE / HUMAN CHECK REQUIRED',
        'sourceWrites': False, 'caseWrites': False, 'sent': False, 'policyApproved': False,
        'qualification': 'Local fictional API lookup; no hosted service or clinical acceptance',
    }
    return [
        {'name': 'atlas-comparison-response.json', 'role': 'supporting', 'sourceReference': 'Atlas ' + ATLAS_COMMIT + ' ' + digest(raw), 'bytes': raw},
        {'name': 'atlas-comparison-receipt.json', 'role': 'supporting', 'sourceReference': 'Local linkage; not an approval or identity crosswalk', 'bytes': encoded(receipt)},
    ]
