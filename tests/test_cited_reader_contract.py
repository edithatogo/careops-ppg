"""Keep the shipped reader example aligned with existing evidence fixtures."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from ppg_cited_reader_flow import build_flow, checked_binding, PIN_FIELDS


class ShippedReaderContract(unittest.TestCase):
    def test_native_qualification_retains_its_single_source_and_unqualified_boundaries(self):
        backend = json.loads((ROOT / 'config/cited-evidence.json').read_text())['powerAutomateReader']
        native = backend['nativeQualification']
        self.assertEqual(native['sourceCount'], 1)
        self.assertEqual(native['qualifiedFormats'], ['TXT'])
        self.assertEqual(native['beforeAfterPinFields'], len(PIN_FIELDS))
        self.assertEqual(native['finalState'], 'Stopped')
        self.assertEqual(native['successfulCases'], ['initial-read', 'unchanged-replay', 'restored-recovery'])
        self.assertIn('not byte-exact', native['representation'])
        self.assertIn('caller permission trimming', native['unqualifiedCases'])
        self.assertIn('conversational assistant publication', native['unqualifiedCases'])
        self.assertFalse(backend['runtimeHashesComputed'])
        self.assertFalse(backend['nativeAssistantRuntimeQualified'])
        fixture = json.loads((ROOT / 'templates/cited-evidence/power-automate-binding.json').read_text())
        self.assertEqual(native['verifiedOutputBytes'], int(checked_binding(fixture)['pin']['Length']))

    def test_example_pin_and_reference_fixture_have_exact_length_and_known_hash(self):
        selected = json.loads((ROOT / 'templates/cited-evidence/power-automate-binding.json').read_text())
        pin = checked_binding(selected)['pin']
        job = json.loads((ROOT / 'templates/cited-evidence/source-preparation-job.json').read_text())
        source = next(s for s in job['sources'] if s['sourceId'] == selected['sourceId'])
        body = (ROOT / 'templates/cited-evidence' / source['file']).read_bytes()
        self.assertEqual(len(body), int(pin['Length']))
        self.assertEqual(hashlib.sha256(body).hexdigest(), source['sha256'])
        self.assertEqual(body.decode('utf-8').encode('utf-8'), body)
        self.assertEqual(pin['Name'], source['file'])
        self.assertEqual(selected['authorityLabel'], source['authorityLabel'])

    def test_partial_backend_does_not_widen_assistant_scope_or_claim_complete_receipt(self):
        contract = json.loads((ROOT / 'config/cited-evidence.json').read_text())
        backend = contract['powerAutomateReader']
        self.assertEqual(contract['maximumSelectedSources'], 5)
        self.assertEqual(backend['maximumFixedSourcesPerProfile'], 1)
        for key in ('runtimeHashesComputed', 'textExtractionQualified',
                    'callerPermissionTrimmingQualified', 'nativeAssistantRuntimeQualified',
                    'requiresPremiumConnector'):
            self.assertIs(backend[key], False)
        for key in ('builder', 'guide'):
            self.assertTrue((ROOT / backend[key]).is_file())
        binding = json.loads((ROOT / 'templates/cited-evidence/power-automate-binding.json').read_text())
        existing = {'properties': {'connectionReferences': {
            'shared_sharepointonline': {'connectionReferenceLogicalName': 'fictional_sp', 'source': 'Embedded'}}}}
        flow = build_flow(existing, binding)
        result = flow['properties']['definition']['actions']['Selected_source_result']['inputs']
        self.assertEqual(result['status'], backend['resultStatus'])
        self.assertIsNone(result['sha256'])
        self.assertIsNone(result['binarySHA256'])
        self.assertIs(flow['properties']['definition']['triggers']['manual']['inputs']['schema']['additionalProperties'], False)


if __name__ == '__main__':
    unittest.main()
