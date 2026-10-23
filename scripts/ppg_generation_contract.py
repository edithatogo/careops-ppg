"""Read-only binding checks between a native generation receipt and package inputs.

This validates supplied native observations and downloaded artifacts. It does not
invoke Word, establish entitlement, inspect layout, publish, or approve content.
"""
from __future__ import annotations
import argparse
import base64
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile
from uuid import UUID
from xml.etree import ElementTree


class GenerationError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise GenerationError(code)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def constant(value):
        raise GenerationError('nonfinite_json_number')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GenerationError('invalid_json') from None


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def fingerprint(value):
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8'))


def text(value):
    return isinstance(value, str) and bool(value.strip())


def pin(value):
    require(isinstance(value, dict), 'native_pin_missing')
    for key in ('UniqueId', 'ETag', 'UIVersionLabel', 'ServerRelativeUrl', 'sha256'):
        require(text(value.get(key)), 'native_pin_missing')
    try:
        require(UUID(value['UniqueId']).int != 0, 'native_identity_invalid')
    except (ValueError, TypeError, AttributeError):
        raise GenerationError('native_identity_invalid') from None
    require(re.fullmatch(r'[0-9a-f]{64}', value['sha256']) is not None,
            'native_hash_invalid')
    require(re.fullmatch(r'(?:W/)?"[^"\r\n]+"', value['ETag']) is not None,
            'native_etag_invalid')
    size = value.get('Length')
    require((type(size) is int and size > 0) or
            (isinstance(size, str) and re.fullmatch(r'[0-9]+', size) is not None and int(size) > 0),
            'native_size_invalid')
    require(value['ServerRelativeUrl'].startswith('/') and
            not any(part in ('.', '..') for part in value['ServerRelativeUrl'].split('/')),
            'native_path_invalid')
    return value


def verify_generation(request, receipt_bytes, input_bytes, template_bytes,
                      output_bytes, observation):
    require(isinstance(request, dict) and request.get('schemaVersion') == 1 and
            request.get('kind') == 'ppg-native-generation-request', 'generation_request_invalid')
    require(request.get('route') in ('sharepoint-structured', 'word-online-business'),
            'generation_route_invalid')
    for key in ('documentKind', 'CaseUID', 'occurrenceKey', 'outputRevision',
                'sourceSnapshotRef', 'templateVersion', 'inputSHA256', 'sourceSHA256'):
        require(text(request.get(key)), 'generation_identity_missing')
    for key in ('inputSHA256', 'sourceSHA256'):
        require(re.fullmatch(r'[0-9a-f]{64}', request[key]) is not None,
                'generation_hash_invalid')
    included = request.get('includedRecordIDs')
    require(isinstance(included, list) and included and all(text(x) for x in included)
            and len(set(included)) == len(included), 'included_records_invalid')
    template = pin(request.get('template'))
    require(isinstance(request.get('sourceBindings'), dict) and request['sourceBindings'],
            'frozen_source_bindings_missing')
    bindings = request['sourceBindings']
    case = bindings.get('caseBinding', {})
    catalogue = bindings.get('catalogueBinding')
    require(isinstance(catalogue, dict), 'generation_catalogue_binding_mismatch')
    records = catalogue.get('records', [])
    sources = bindings.get('sources', [])
    require(isinstance(case, dict) and case.get('CaseUID') == request['CaseUID'] and
            case.get('sourceBaselineRef') == request['sourceSnapshotRef'],
            'generation_case_binding_mismatch')
    require(isinstance(records, list) and all(isinstance(r, dict) for r in records) and
            len(records) == len(included) and {r.get('DocumentUID') for r in records} == set(included),
            'generation_catalogue_binding_mismatch')
    require(isinstance(sources, list) and sources and all(isinstance(r, dict) for r in sources),
            'generation_source_pins_missing')
    baselines = [r for r in sources if r.get('role') == 'recorded-baseline']
    require(len(baselines) == 1 and baselines[0].get('sha256') == request['sourceSHA256'],
            'generation_baseline_hash_mismatch')
    for source in sources:
        native = source.get('nativePin')
        require(isinstance(native, dict) and text(native.get('UniqueId')) and
                text(native.get('ETag')) and text(native.get('ServerRelativeUrl')),
                'generation_source_pins_missing')
    invocation = request.get('invocation')
    require(isinstance(invocation, dict) and all(text(invocation.get(k)) for k in
            ('environmentId', 'flowId', 'actionName', 'operationId')),
            'invocation_binding_missing')
    expected_operation = ('SubmitDocGenForm' if request['route'] == 'sharepoint-structured'
                          else 'CreateFileItem')
    require(invocation['operationId'] == expected_operation, 'generation_operation_invalid')
    if request['route'] == 'sharepoint-structured':
        require(text(invocation.get('formId')), 'generation_form_missing')
        form = request.get('formBinding')
        require(isinstance(form, dict) and form.get('formId') == invocation['formId'] and
                form.get('kind') == 'document-generation' and form.get('outputFormat') == 'docx' and
                isinstance(form.get('metadataSHA256'), str) and
                re.fullmatch(r'[0-9a-f]{64}', form['metadataSHA256']) is not None,
                'document_generation_form_unconfirmed')
    else:
        require('formBinding' not in request, 'ambiguous_generation_route')
    require(sha(input_bytes) == request['inputSHA256'], 'frozen_input_changed')
    require(sha(template_bytes) == template['sha256'] and
            len(template_bytes) == int(template['Length']), 'template_changed')
    receipt = strict_json(receipt_bytes)
    require(isinstance(receipt, dict) and receipt.get('schemaVersion') == 1 and
            receipt.get('kind') == 'ppg-native-generation-receipt', 'generation_receipt_invalid')
    require(receipt.get('requestSHA256') == fingerprint(request), 'generation_request_changed')
    require(receipt.get('status') == 'Succeeded' and receipt.get('generationPerformed') is True,
            'generation_not_succeeded')
    actual = receipt.get('invocation')
    require(isinstance(actual, dict) and all(actual.get(k) == v for k, v in invocation.items())
            and text(actual.get('runId')) and actual.get('status') == 'Succeeded',
            'generation_invocation_mismatch')
    require(text(actual.get('completedAtUtc')) and
            re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', actual['completedAtUtc']) is not None,
            'generation_completion_time_missing')
    output = pin(receipt.get('output'))
    require(output['UniqueId'] != template['UniqueId'] and
            output['ServerRelativeUrl'] != template['ServerRelativeUrl'],
            'template_output_overlap')
    require(all(output['UniqueId'] != r['nativePin']['UniqueId'] and
                output['ServerRelativeUrl'] != r['nativePin']['ServerRelativeUrl'] for r in sources),
            'generated_output_overlaps_preserved_source')
    require(sha(output_bytes) == output['sha256'] and len(output_bytes) == int(output['Length']),
            'generated_output_changed')
    require(isinstance(observation, dict) and observation.get('requestSHA256') == fingerprint(request)
            and observation.get('invocation') == actual, 'native_invocation_unconfirmed')
    require(observation.get('output') == output, 'native_output_pin_changed')
    require(observation.get('templateBefore') == template and
            observation.get('templateAfter') == template, 'native_template_pin_changed')
    require(observation.get('sourceBindingsBefore') == request['sourceBindings'] and
            observation.get('sourceBindingsAfter') == request['sourceBindings'],
            'native_source_bindings_changed')
    if request['route'] == 'sharepoint-structured':
        require(observation.get('formBefore') == request['formBinding'] and
                observation.get('formAfter') == request['formBinding'], 'native_generation_form_changed')
    require(observation.get('inputSHA256') == request['inputSHA256'],
            'native_generation_input_changed')
    # Structural checks never substitute for Word rendering, repeats or edit proof.
    try:
        with zipfile.ZipFile(io.BytesIO(output_bytes)) as document:
            names = document.namelist()
            require(len(set(names)) == len(names), 'duplicate_docx_member')
            require(len(output_bytes) <= 10_000_000 and
                    sum(info.file_size for info in document.infolist()) <= 100_000_000,
                    'generated_docx_size_limit')
            require(document.testzip() is None, 'docx_crc_invalid')
            require('[Content_Types].xml' in names and 'word/document.xml' in names,
                    'generated_docx_missing_parts')
            body = ElementTree.fromstring(document.read('word/document.xml'))
            require(body.tag == '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document',
                    'generated_docx_body_invalid')
    except (zipfile.BadZipFile, ElementTree.ParseError, RuntimeError, KeyError):
        raise GenerationError('generated_docx_invalid') from None
    return {'schemaVersion': 1, 'kind': 'ppg-generation-package-binding',
            'qualificationScope': 'local-binding-verification-only',
            'productionQualificationRequired': True,
            'requestSHA256': fingerprint(request), 'receiptSHA256': sha(receipt_bytes),
            'inputSHA256': request['inputSHA256'], 'CaseUID': request['CaseUID'],
            'documentKind': request['documentKind'], 'occurrenceKey': request['occurrenceKey'],
            'outputRevision': request['outputRevision'],
            'sourceSnapshotRef': request['sourceSnapshotRef'], 'sourceSHA256': request['sourceSHA256'],
            'includedRecordIDs': included, 'templateVersion': request['templateVersion'],
            'template': template, 'invocation': actual, 'output': output,
            'sourceWrites': False, 'caseWrites': False, 'sent': False, 'policyApproved': False,
            'requiredPackageRoles': ['recorded-baseline', 'generated-draft', 'generation-receipt', 'selection-record']}


def prepare_package_inputs(request, receipt_bytes, input_bytes, template_bytes,
                           output_bytes, observation, baseline_bytes,
                           selection_bytes, job_id, created_at):
    """Bind generated output to the existing schema1 packaging kernel, read-only.

    The kernel assembles supplied bytes; this adapter does not invoke generation
    or turn supplied observations into production qualification.
    """
    binding = verify_generation(request, receipt_bytes, input_bytes, template_bytes,
                                output_bytes, observation)
    require(isinstance(job_id, str) and
            re.fullmatch(r'job-[a-z0-9-]{1,64}', job_id) is not None, 'invalid_job')
    require(isinstance(created_at, str) and re.fullmatch(
        r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z', created_at) is not None,
        'utc_time_invalid')
    try:
        datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    except ValueError:
        raise GenerationError('utc_time_invalid') from None
    selection = strict_json(selection_bytes)
    require(isinstance(selection, dict) and selection.get('schemaVersion') == 1 and
            selection.get('kind') == 'existing-case-artifact-selection',
            'selection_record_invalid')
    require(all(selection.get(k) == request['sourceBindings'][k]
                for k in ('caseBinding', 'catalogueBinding', 'sources')),
            'selection_generation_binding_mismatch')
    baseline = next(r for r in request['sourceBindings']['sources']
                    if r['role'] == 'recorded-baseline')
    require(sha(baseline_bytes) == baseline['sha256'], 'package_baseline_changed')
    native = baseline['nativePin']
    require(str(len(baseline_bytes)) == str(native.get('Length')),
            'package_baseline_length_changed')
    output = binding['output']
    parts = [
        ('sources/recorded-baseline.zip', 'recorded-baseline', baseline_bytes,
         native['ServerRelativeUrl'], native['ETag']),
        ('drafts/generated.docx', 'generated-draft', output_bytes,
         output['ServerRelativeUrl'], output['ETag']),
        ('generation/generation-receipt.json', 'generation-receipt', receipt_bytes,
         'native-generation-run:' + binding['invocation']['runId'], binding['receiptSHA256']),
        ('selection/selection.json', 'selection-record', selection_bytes,
         request['sourceSnapshotRef'], sha(selection_bytes)),
    ]
    members = [dict(path=path, role=role, sha256=sha(raw), size=len(raw),
                    sourceReference=reference, sourceVersionRef=version)
               for path, role, raw, reference, version in parts]
    # Match the retained kernel's raw limit before serializing base64. The kernel
    # independently applies its full provenance and serialized wire-size guards.
    require(sum(m['size'] for m in members) <= 2_000_000, 'complete_package_oversize')
    job = dict(schemaVersion=1, jobId=job_id, documentKind=request['documentKind'],
               CaseUID=request['CaseUID'], sourceSnapshotRef=request['sourceSnapshotRef'],
               sourceSHA256=request['sourceSHA256'], templateVersion=request['templateVersion'],
               templateSHA256=request['template']['sha256'], outputRevision=request['outputRevision'],
               includedRecordIDs=request['includedRecordIDs'], createdAtUtc=created_at,
               members=members, generationBinding=binding,
               selectionSHA256=sha(selection_bytes))
    contents = [dict(path=path, base64=base64.b64encode(raw).decode('ascii'))
                for path, _, raw, _, _ in parts]
    return dict(qualificationScope='local-generation-package-inputs-only',
                productionQualificationRequired=True, job=job, members=contents,
                nativeWrites=False, sourceWrites=False, caseWrites=False,
                sent=False, policyApproved=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('request', 'receipt', 'input', 'template', 'document', 'observation'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--package-baseline', type=Path)
    parser.add_argument('--package-selection', type=Path)
    parser.add_argument('--job-id')
    parser.add_argument('--created-at')
    args = parser.parse_args()
    package_args = (args.package_baseline, args.package_selection, args.job_id, args.created_at)
    if any(x is not None for x in package_args) and not all(x is not None for x in package_args):
        parser.error('Package preparation requires --package-baseline, --package-selection, --job-id and --created-at together.')
    inputs = (strict_json(args.request.read_bytes()), args.receipt.read_bytes(),
              args.input.read_bytes(), args.template.read_bytes(), args.document.read_bytes(),
              strict_json(args.observation.read_bytes()))
    result = (prepare_package_inputs(*inputs, args.package_baseline.read_bytes(),
                                     args.package_selection.read_bytes(), args.job_id, args.created_at)
              if all(x is not None for x in package_args) else verify_generation(*inputs))
    print(json.dumps(result, ensure_ascii=False, indent=2))
