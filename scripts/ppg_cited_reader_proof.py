"""Check retained selected-source reader exports offline; never call a service.

This verifies internal consistency, not authenticity of supplied exports or current
native state. It never grants assistant, citation, permission or clinical acceptance.
Keep the binding, source bytes and raw action exports private.
"""
import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from ppg_cited_reader_flow import MAX_BYTES, PIN_FIELDS, checked_binding

LABELS = ('first', 'replay', 'refusal', 'recovery')
ACTIONS = {'Metadata_before', 'Require_expected_source', 'Read_content',
           'Metadata_after', 'Require_unchanged_source', 'Selected_source_result',
           'Refuse_SOURCE_PIN', 'Refuse_SOURCE_CHANGED'}
OUTPUTS = {'Metadata_before', 'Metadata_after', 'Read_content', 'Selected_source_result'}
BOUNDARY = 'Opaque native connector content; no extracted-text or citation-locator claim.'
LINK_KEYS = {'nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink'}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def instant(value):
    require(isinstance(value, str), 'missing_timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('invalid_timestamp') from None
    require(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0,
            'utc_timestamp_required')
    return parsed.astimezone(timezone.utc)


def pin_values(value):
    require(isinstance(value, dict) and all(k in value for k in PIN_FIELDS), 'incomplete_pin')
    require(all(type(value[k]) in (str, int) for k in PIN_FIELDS), 'invalid_pin_type')
    result = {k: str(value[k]) for k in PIN_FIELDS}
    result['UniqueId'] = result['UniqueId'].lower()
    return result


def content_bytes(value):
    if isinstance(value, str):
        data = value.encode('utf-8')
    else:
        require(isinstance(value, dict) and set(value) == {'$content-type', '$content'},
                'unsupported_content_shape')
        require(isinstance(value['$content-type'], str) and bool(value['$content-type'])
                and isinstance(value['$content'], str), 'invalid_binary_content')
        require(len(value['$content']) <= 4 * ((MAX_BYTES + 2) // 3), 'content_too_large')
        try:
            data = base64.b64decode(value['$content'], validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('invalid_base64') from None
    require(len(data) <= MAX_BYTES, 'content_too_large')
    return data


def action_statuses(history, run):
    require(isinstance(history, dict) and history.get('complete') is True,
            'incomplete_action_history')
    pages = history.get('nativePages')
    require(isinstance(pages, list) and 1 <= len(pages) <= 10, 'missing_native_pages')
    flattened = []
    for index, page in enumerate(pages):
        require(isinstance(page, dict) and isinstance(page.get('value'), list),
                'invalid_native_page')
        links = {page[k] for k in LINK_KEYS if page.get(k)}
        require(len(links) <= 1 and (bool(links) == (index < len(pages) - 1)),
                'unexhausted_or_ambiguous_action_pages')
        flattened.extend(page['value'])
    require(flattened == history.get('value'), 'action_page_rows_differ')
    require(all(isinstance(row, dict) and isinstance(row.get('properties'), dict)
                for row in flattened), 'invalid_action_row')
    names = [row.get('name') for row in flattened]
    require(len(names) == len(ACTIONS) and set(names) == ACTIONS, 'missing_or_duplicate_actions')
    require(all(row.get('id') == run['id'] + '/actions/' + row['name'] for row in flattened),
            'action_run_identity_mismatch')
    return {row['name']: row.get('properties', {}).get('status') for row in flattened}


def verify_evidence(binding, retained_bytes, bundle):
    binding = checked_binding(binding)
    pin = pin_values(binding['pin'])
    require(isinstance(retained_bytes, bytes) and 0 < len(retained_bytes) <= MAX_BYTES
            and str(len(retained_bytes)) == pin['Length'], 'retained_source_length_mismatch')
    require(isinstance(bundle, dict) and set(bundle) == set(LABELS), 'four_run_bundle_required')
    expected_result = {
        'schemaVersion': 1, 'sourceId': binding['sourceId'],
        'canonicalUrl': binding['siteUrl'].split('/sites/')[0].split('/teams/')[0]
                        + pin['ServerRelativeUrl'],
        'nativeUniqueId': pin['UniqueId'],
        'nativeVersionRef': pin['MajorVersion'] + '.' + pin['MinorVersion'],
        'nativePin': pin, 'authorityLabel': binding['authorityLabel'],
        'contentBoundary': BOUNDARY, 'sha256': None, 'binarySHA256': None,
        'textExtractionQualified': False, 'nativeAssistantRuntimeQualified': False,
        'status': 'selected-source-read',
    }
    runs = []; parent = None; previous_end = None
    for label in LABELS:
        evidence = bundle[label]
        require(isinstance(evidence, dict) and isinstance(evidence.get('run'), dict), 'invalid_run_export')
        run = evidence['run']; properties = run.get('properties')
        require(isinstance(properties, dict), 'invalid_run_properties')
        require(isinstance(run.get('name'), str) and bool(run['name'])
                and isinstance(run.get('id'), str)
                and run['id'].endswith('/runs/' + run['name']), 'invalid_run_identity')
        flow = run['id'].rsplit('/runs/', 1)[0]
        require('/flows/' in flow and (parent is None or parent == flow), 'mixed_flow_exports')
        parent = flow
        require(run['name'] not in [r['run'] for r in runs], 'duplicate_run')
        start = instant(properties['startTime']); end = instant(properties['endTime'])
        require(start <= end and (previous_end is None or previous_end <= start),
                'nonserial_or_reordered_runs')
        previous_end = end
        statuses = action_statuses(evidence['actions'], run)
        outputs = evidence['outputs']
        require(isinstance(outputs, dict), 'invalid_outputs')
        expected_statuses = {key: 'Succeeded' for key in ACTIONS}
        expected_statuses.update(Refuse_SOURCE_PIN='Skipped', Refuse_SOURCE_CHANGED='Skipped')
        if label == 'refusal':
            require(properties.get('status') == 'Failed'
                    and properties.get('error', {}).get('code') == 'SOURCE_PIN',
                    'expected_source_pin_refusal_missing')
            expected_statuses = {key: 'Skipped' for key in ACTIONS}
            expected_statuses.update(Metadata_before='Succeeded', Refuse_SOURCE_PIN='Succeeded',
                                     Require_expected_source='Cancelled')
            require(set(outputs) == {'Metadata_before'}, 'refusal_has_content_or_result')
        else:
            require(properties.get('status') == 'Succeeded', 'successful_run_required')
            require(set(outputs) == OUTPUTS, 'successful_outputs_incomplete')
        require(statuses == expected_statuses, 'unexpected_action_execution')
        require(isinstance(outputs.get('Metadata_before'), dict), 'invalid_metadata_before_output')
        require(pin_values(outputs['Metadata_before']['body']) == pin, 'source_pin_before_mismatch')
        if label != 'refusal':
            require(isinstance(outputs.get('Metadata_after'), dict)
                    and isinstance(outputs.get('Read_content'), dict), 'invalid_success_output_shape')
            require(pin_values(outputs['Metadata_after']['body']) == pin, 'source_pin_after_mismatch')
            require(content_bytes(outputs['Read_content']['body']) == retained_bytes,
                    'read_content_bytes_mismatch')
            result = outputs['Selected_source_result']
            require(isinstance(result, dict) and set(result) == set(expected_result) | {'content', 'retrievedAtUtc'},
                    'result_fields_mismatch')
            for key, wanted in expected_result.items():
                require(type(result[key]) is type(wanted) and result[key] == wanted,
                        'result_contract_mismatch:' + key)
            require(content_bytes(result['content']) == retained_bytes, 'result_bytes_mismatch')
            require(start <= instant(result['retrievedAtUtc']) <= end, 'retrieval_time_outside_run')
        runs.append({'phase': label, 'run': run['name'], 'status': properties['status']})
    return {
        'schemaVersion': 1, 'offlineEvidenceConsistent': True, 'runs': runs,
        'returnedBytes': len(retained_bytes),
        'independentlyComputedSHA256': hashlib.sha256(retained_bytes).hexdigest(),
        'sourcePinBeforeAndAfterConsistent': True, 'preContentRefusalConsistent': True,
        'unchangedReplayAndRecoveryConsistent': True,
        'nativeEvidenceAuthenticityQualified': False, 'currentNativeStateVerified': False,
        'nativeAssistantRuntimeQualified': False, 'callerPermissionTrimmingQualified': False,
        'textExtractionQualified': False, 'clinicalAcceptance': False,
    }


def read_json(path):
    require(path.stat().st_size <= 8_000_000, 'evidence_file_too_large')
    return json.loads(path.read_bytes())


def load_bundle(directory):
    result = {}
    for label in LABELS:
        keys = {'Metadata_before'} if label == 'refusal' else OUTPUTS
        result[label] = {
            'run': read_json(directory / (label + '-run.json')),
            'actions': read_json(directory / (label + '-actions.json')),
            'outputs': {key: read_json(directory / (label + '-' + key + '-outputs.json')) for key in keys},
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', required=True, type=Path)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--evidence-directory', required=True, type=Path)
    args = parser.parse_args()
    try:
        require(args.source.stat().st_size <= MAX_BYTES, 'retained_source_too_large')
        proof = verify_evidence(read_json(args.binding), args.source.read_bytes(),
                                load_bundle(args.evidence_directory))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        # No exception text: JSON/file errors can contain private content or paths.
        print(json.dumps({'offlineEvidenceConsistent': False, 'errorType': type(exc).__name__}))
        return 1
    print(json.dumps(proof, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
