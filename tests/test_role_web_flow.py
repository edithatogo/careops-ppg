import json
import unittest
from scripts.ppg_role_web_flow import script_package, build


class WebFlowContractTests(unittest.TestCase):
    def test_response_envelope_preserves_string_result(self):
        source = 'function main(): string { return "preserved"; }'
        package = script_package(source)
        info = json.loads(package['parameterInfo'])
        self.assertEqual(package['body'], source)
        self.assertEqual(info['returnSchema']['type'], 'object')
        self.assertEqual(info['returnSchema']['properties']['result']['type'], 'string')
        self.assertEqual(info['parameterSchema']['required'], ['requestJson'])

    def test_refuses_unqualified_connector_pair(self):
        with self.assertRaises(ValueError):
            build({'site': 'https://example.invalid', 'connectionReferences': {}})

    def test_persistence_has_only_create_writes_and_no_retry(self):
        from scripts.ppg_role_web_flow import with_persistence
        refs = {k: {'source': 'Embedded'} for k in ['shared_sharepointonline', 'shared_excelonlinebusiness']}
        bindings = {'site': 'https://example.invalid', 'connectionReferences': refs,
                    'registers': {k: 'a'*36 for k in ['roles','assignments','appointments','handovers']},
                    'scriptSHA256': 'b'*64, 'roleContractSHA256': 'c'*64,
                    'scriptParameters': {k: 'fixture' for k in ['source','drive','file','scriptSource','scriptDrive','scriptId']},
                    'snapshotList': '11111111-1111-1111-1111-111111111111'}
        candidate = build(bindings)
        reordered = dict(bindings, registers=dict(reversed(list(bindings['registers'].items()))))
        self.assertEqual(build(reordered), candidate)
        saved = with_persistence(candidate, bindings)
        self.assertNotEqual(candidate, saved)
        self.assertNotIn('Persist_snapshots', candidate['properties']['definition']['actions']['Source_snapshot_stable']['actions'])
        writes = []
        def visit(value):
            if isinstance(value, dict):
                inputs = value.get('inputs', {})
                params = inputs.get('parameters', {}) if isinstance(inputs, dict) else {}
                method = params.get('parameters/method')
                if method and method != 'GET':
                    writes.append(value)
                for child in value.values(): visit(child)
            elif isinstance(value, list):
                for child in value: visit(child)
        visit(saved)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]['inputs']['parameters']['parameters/method'], 'POST')
        self.assertIn(bindings['snapshotList'], writes[0]['inputs']['parameters']['parameters/uri'])
        self.assertEqual(writes[0]['inputs']['retryPolicy'], {'type': 'none'})
        guard = saved['properties']['definition']['actions']['Source_snapshot_stable']['actions']
        self.assertEqual(guard['Preflight_snapshots_exact']['runAfter'], {'Preflight_snapshots': ['Succeeded']})
        saved_actions = guard['Preflight_snapshots_exact']['actions']
        self.assertEqual(saved_actions['Persist_snapshots']['runAfter'], {})
        self.assertNotIn('@div(1,0)', json.dumps(saved))
        self.assertIn('RoleSnapshotConflict', json.dumps(saved))
        self.assertIn('RoleSnapshotChangedDuringSave', json.dumps(saved))
        self.assertIn('RoleSourceChangedAfterSave', json.dumps(saved))
        self.assertEqual(saved['properties']['definition']['triggers']['manual']['runtimeConfiguration']['concurrency']['runs'], 1)
