import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('generation', Path(__file__).resolve().parents[1] / 'scripts/ppg_generation_contract.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def fixture():
    # Minimal in-memory test container only; never a user document or native output claim.
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>FICTIONAL TEST</w:t></w:r></w:p></w:body></w:document>')
    document = stream.getvalue()
    template, inputs = b'fictional-template-bytes', b'{"title":"FICTIONAL TEST"}'
    def pin(uid, path, raw):
        return dict(UniqueId=uid, ETag='"opaque,' + uid + '"', UIVersionLabel='1.0',
                    ServerRelativeUrl=path, sha256=g.sha(raw), Length=len(raw))
    request = dict(schemaVersion=1, kind='ppg-native-generation-request', route='sharepoint-structured',
                   documentKind='review-preparation', CaseUID='fictional-case', occurrenceKey='fictional-occurrence',
                   outputRevision='draft-1', sourceSnapshotRef='fictional-source-v1', sourceSHA256='a' * 64,
                   templateVersion='fictional-template-v1', inputSHA256=g.sha(inputs),
                   includedRecordIDs=['fictional-policy'], template=pin('11111111-1111-4111-8111-111111111111', '/library/template.docx', template),
                   sourceBindings={'caseBinding': {'CaseUID': 'fictional-case', 'sourceBaselineRef': 'fictional-source-v1', 'odata.etag': '"case,1"'},
                                   'catalogueBinding': {'records': [{'DocumentUID': 'fictional-policy', 'odata.etag': '"record,1"'}]},
                                   'sources': [{'role': 'recorded-baseline', 'sha256': 'a' * 64, 'nativePin': {'UniqueId': '33333333-3333-4333-8333-333333333333', 'ETag': '"source,1"', 'ServerRelativeUrl': '/library/baseline.zip'}}]},
                   invocation=dict(environmentId='fictional-environment', flowId='fictional-flow', actionName='Generate',
                                   operationId='SubmitDocGenForm', formId='fictional-form'))
    request['formBinding'] = {'formId': 'fictional-form', 'kind': 'document-generation', 'outputFormat': 'docx', 'metadataSHA256': 'c' * 64}
    invocation = dict(request['invocation'], runId='fictional-run', status='Succeeded', completedAtUtc='2026-10-17T00:00:00Z')
    receipt = dict(schemaVersion=1, kind='ppg-native-generation-receipt', requestSHA256=g.fingerprint(request),
                   status='Succeeded', generationPerformed=True, invocation=invocation,
                   output=pin('22222222-2222-4222-8222-222222222222', '/library/generated.docx', document))
    observation = dict(requestSHA256=g.fingerprint(request), invocation=invocation, output=receipt['output'],
                       templateBefore=request['template'], templateAfter=request['template'],
                       sourceBindingsBefore=request['sourceBindings'], sourceBindingsAfter=request['sourceBindings'],
                       inputSHA256=request['inputSHA256'])
    observation['formBefore'] = request['formBinding']
    observation['formAfter'] = request['formBinding']
    return request, receipt, inputs, template, document, copy.deepcopy(observation)


def verify(f):
    request, receipt, inputs, template, document, observation = f
    return g.verify_generation(request, json.dumps(receipt).encode(), inputs, template, document, observation)


class GenerationContractTests(unittest.TestCase):
    def test_success_retains_identity_versions_hashes_without_claiming_production(self):
        f = fixture()
        result = verify(f)
        self.assertEqual(result['output']['sha256'], g.sha(f[4]))
        self.assertEqual(result['includedRecordIDs'], ['fictional-policy'])
        self.assertEqual(result['qualificationScope'], 'local-binding-verification-only')
        self.assertTrue(result['productionQualificationRequired'])
        self.assertFalse(result['policyApproved'])

    def test_existing_artifact_receipt_cannot_be_relabelled_as_generation(self):
        f = list(fixture())
        f[1] = dict(schemaVersion=2, provenanceMode='existing-artifacts', wordGenerationPerformed=False)
        with self.assertRaisesRegex(g.GenerationError, 'generation_receipt_invalid'):
            verify(f)

    def test_changed_input_template_or_human_edited_output_refuses_without_writes(self):
        for index, code in ((2, 'frozen_input_changed'), (3, 'template_changed'), (4, 'generated_output_changed')):
            f = list(fixture())
            f[index] += b'changed'
            with self.subTest(index=index), self.assertRaisesRegex(g.GenerationError, code):
                verify(f)

    def test_native_stale_source_or_template_or_output_refuses(self):
        for key, code in (('sourceBindingsAfter', 'native_source_bindings_changed'),
                          ('templateAfter', 'native_template_pin_changed'), ('output', 'native_output_pin_changed')):
            f = list(fixture())
            f[5][key] = {'changed': True}
            with self.subTest(key=key), self.assertRaisesRegex(g.GenerationError, code):
                verify(f)

    def test_receipt_alone_cannot_supply_native_run_observation(self):
        f = list(fixture())
        f[5]['invocation']['runId'] = 'another-run'
        with self.assertRaisesRegex(g.GenerationError, 'native_invocation_unconfirmed'):
            verify(f)

    def test_failed_or_missing_invocation_never_produces_a_binding(self):
        for mutate in (lambda r: r.update(status='Failed'),
                       lambda r: r.update(generationPerformed=False),
                       lambda r: r['invocation'].pop('runId')):
            f = fixture()
            mutate(f[1])
            with self.assertRaises(g.GenerationError):
                verify(f)

    def test_invalid_docx_is_rejected_even_when_receipt_hash_matches(self):
        f = list(fixture())
        f[4] = b'not a docx'
        f[1]['output']['sha256'] = g.sha(f[4])
        f[1]['output']['Length'] = len(f[4])
        f[5]['output'] = copy.deepcopy(f[1]['output'])
        with self.assertRaisesRegex(g.GenerationError, 'generated_docx_invalid'):
            verify(f)

    def test_ambiguous_json_or_nonfinite_values_fail_closed(self):
        for raw in (b'{"generationPerformed":false,"generationPerformed":true}', b'{"x":NaN}'):
            with self.assertRaises(g.GenerationError):
                g.strict_json(raw)

    def test_fresh_output_cannot_replace_a_selected_source_or_manual_draft(self):
        f = list(fixture())
        f[1]['output']['UniqueId'] = f[0]['sourceBindings']['sources'][0]['nativePin']['UniqueId']
        f[5]['output'] = copy.deepcopy(f[1]['output'])
        with self.assertRaisesRegex(g.GenerationError, 'generated_output_overlaps_preserved_source'):
            verify(f)

    def test_receipt_cannot_rebind_case_catalogue_or_baseline(self):
        for key, value, code in (('CaseUID', 'another-case', 'generation_case_binding_mismatch'),
                                 ('includedRecordIDs', ['another-policy'], 'generation_catalogue_binding_mismatch'),
                                 ('sourceSHA256', 'b' * 64, 'generation_baseline_hash_mismatch')):
            f = list(fixture())
            f[0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(g.GenerationError, code):
                verify(f)

    def test_upload_form_or_changed_generation_form_cannot_pass(self):
        f = list(fixture())
        f[0]['formBinding']['kind'] = 'file-upload'
        with self.assertRaisesRegex(g.GenerationError, 'document_generation_form_unconfirmed'):
            verify(f)
        f = list(fixture())
        f[5]['formAfter']['metadataSHA256'] = 'd' * 64
        with self.assertRaisesRegex(g.GenerationError, 'native_generation_form_changed'):
            verify(f)

    def test_word_route_requires_its_actual_operation_and_no_form_binding(self):
        f = list(fixture())
        f[0]['route'] = 'word-online-business'
        f[0]['invocation'] = {'environmentId': 'fictional-environment', 'flowId': 'fictional-flow', 'actionName': 'Populate', 'operationId': 'CreateFileItem'}
        f[0].pop('formBinding')
        f[1]['requestSHA256'] = g.fingerprint(f[0])
        f[1]['invocation'] = dict(f[0]['invocation'], runId='fictional-word-run', status='Succeeded', completedAtUtc='2026-10-17T00:00:00Z')
        f[5]['requestSHA256'] = g.fingerprint(f[0])
        f[5]['invocation'] = copy.deepcopy(f[1]['invocation'])
        self.assertEqual(verify(f)['invocation']['operationId'], 'CreateFileItem')
