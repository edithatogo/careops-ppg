"""Offline graph and output refusal tests; no authentication or native operations."""
import copy
import hashlib
import unittest

from scripts.ppg_integrated_acquisition import build, validate, verify_observation, EXCEL_API
from scripts.ppg_sourcing_preflight import validate as initial_gate
from tests.test_url_acquisition_qualification import profile, readback_fixture, nodes


def runtime():
    return {'source': 'me', 'scriptSource': 'me', 'drive': 'fictional-drive',
            'scriptDrive': 'fictional-drive', 'file': 'fictional-runtime-workbook',
            'scriptId': 'fictional-qualified-script',
            'connectionReference': {'id': EXCEL_API, 'connectionName': 'fictional-excel', 'source': 'Embedded'},
            'scriptPackageSHA256': hashlib.sha256(b'fictional script package').hexdigest(),
            'runtimeSourceSHA256': hashlib.sha256(b'fictional source').hexdigest()}


def integrated_fixture():
    p, transport, raw = readback_fixture()
    r = runtime()
    result = {'kind': 'ppg-supplied-byte-hash-result-v1',
              'qualificationId': p['qualificationId'], 'sourceKey': p['sourceKey'],
              'actualBytes': len(raw), 'actualSHA256': hashlib.sha256(raw).hexdigest(),
              'expectedSHA256': p['expectedSHA256'], 'integrityMatches': True,
              'sourceProvenanceAuthenticated': False, 'nativeAcquisitionQualified': False}
    report = {'kind': 'ppg-integrated-transport-hash-observation-v1',
              'transport': transport, 'hashResult': result,
              'metadataAfterHash': copy.deepcopy(transport['metadataAfter']),
              'workflowId': 'fictional-workflow', 'runName': transport['runName'],
              'scriptPackageSHA256': r['scriptPackageSHA256'],
              'runtimeSourceSHA256': r['runtimeSourceSHA256'],
              'associationPersisted': False, 'checkpointAdvanced': False,
              'fullAcquisitionQualified': False, 'clinicalApplicabilityAccepted': False}
    return p, r, report, raw


class IntegratedAcquisition(unittest.TestCase):
    def test_preparation_preserves_inputs_and_original_transport_gate_stays_narrow(self):
        p, r = profile(), runtime()
        before = copy.deepcopy((p, r))
        flow = build(p, r)
        self.assertEqual((p, r), before)
        self.assertEqual(validate(flow, p, r), [])
        self.assertTrue(initial_gate(flow))  # Generic scripts remain refused there.
        operations = [n for n in nodes(flow) if n['type'] == 'OpenApiConnection']
        self.assertTrue(all(n['inputs']['retryPolicy'] == {'type': 'none'} for n in operations))
        self.assertEqual(len([n for n in operations if n['inputs']['host']['operationId'] == 'RunScriptProdV2']), 1)

    def test_changed_bindings_or_new_indirect_actions_refuse_exact_gate(self):
        for change in ('script', 'expression', 'extra', 'overwrite', 'reference'):
            p, r = profile(), runtime(); f = build(p, r)
            if change == 'script':
                next(n for n in nodes(f) if n['type'] == 'OpenApiConnection' and n['inputs']['host']['operationId'] == 'RunScriptProdV2')['inputs']['parameters']['scriptId'] = 'another-script'
            elif change == 'expression':
                next(n for n in nodes(f) if n.get('inputs') == "@json(body('Run_hash')?['result'])")['inputs'] = '@triggerBody()'
            elif change == 'extra':
                f['properties']['definition']['actions']['Undeclared'] = {'type': 'Workflow', 'runAfter': {}}
            elif change == 'reference':
                f['properties']['connectionReferences']['unreviewed'] = {'id': EXCEL_API, 'connectionName': 'other', 'source': 'Embedded'}
            else:
                next(n for n in nodes(f) if n['type'] == 'OpenApiConnection' and n['inputs']['host']['operationId'] == 'CopyFile')['inputs']['parameters']['overwrite'] = True
            with self.subTest(change=change):self.assertTrue(validate(f, p, r))

    def test_only_known_native_annotations_are_ignored_without_mutation(self):
        p, r = profile(), runtime(); f = build(p, r)
        for n in nodes(f):
            if n['type'] == 'OpenApiConnection':n['inputs']['authentication'] = "@parameters('$authentication')"
        f['properties']['definition'].pop('outputs')
        for ref in f['properties']['connectionReferences'].values():ref['tier'] = 'Standard'
        before = copy.deepcopy(f)
        self.assertEqual(validate(f, p, r), []);self.assertEqual(f, before)
        next(n for n in nodes(f) if n['type'] == 'OpenApiConnection')['inputs']['authentication'] = '@triggerBody()'
        self.assertTrue(validate(f, p, r))

    def test_dynamic_runtime_invalid_pins_alerts_and_enabled_flow_refuse(self):
        for name, value in [('scriptId', "@triggerBody()?['script']"), ('file', 'x@{secret}'),
                            ('runtimeSourceSHA256', ''), ('source', 'another-site')]:
            r = runtime();r[name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):build(profile(), r)
        p, r = profile(), runtime()
        for name, value in [('state', 'Started'), ('flowFailureAlertSubscribed', True)]:
            f = build(p, r);f['properties'][name] = value
            self.assertTrue(validate(f, p, r))

    def test_verified_supplied_output_remains_non_authorising(self):
        p, r, report, raw = integrated_fixture();before = copy.deepcopy(report)
        result = verify_observation(p, r, report, raw)
        self.assertTrue(result['suppliedHashMatchesIndependentBytes'])
        for k in ('integratedRunProvenanceAuthenticated', 'associationPersisted', 'fullAcquisitionQualified'):
            self.assertIs(result[k], False)
        self.assertEqual(report, before)

    def test_hash_digest_byte_count_identity_and_boolean_drift_refuse(self):
        for key, value in [('actualSHA256', '0'*64), ('actualBytes', 1),
                           ('qualificationId', 'another'), ('integrityMatches', 1),
                           ('sourceProvenanceAuthenticated', True)]:
            p, r, report, raw = integrated_fixture();report['hashResult'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):verify_observation(p, r, report, raw)

    def test_late_file_change_and_forged_completion_refuse(self):
        for key in ('Id', 'ETag', 'Size', 'IsFolder'):
            p, r, report, raw = integrated_fixture();report['metadataAfterHash'][key] = 'changed'
            with self.subTest(key=key), self.assertRaises(ValueError):verify_observation(p, r, report, raw)
        for key, value in [('runName', 'other-run'), ('scriptPackageSHA256', '0'*64),
                           ('associationPersisted', True), ('fullAcquisitionQualified', True)]:
            p, r, report, raw = integrated_fixture();report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):verify_observation(p, r, report, raw)


if __name__ == '__main__':
    unittest.main()
