import hashlib
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('publication_builder', Path(__file__).parents[1] / 'tools/policy-editions/build_publication_qualification.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PublicationQualificationTests(unittest.TestCase):
    def fixture(self):
        raw = 'FICTIONAL source only\n'
        scope = dict(CaseUID='fictional-case', DocumentReference='https://example.invalid/source', ReviewedVersionRef='fictional-version-1', DocumentSHA256=hashlib.sha256(raw.encode()).hexdigest())
        request = dict(FictionalTest=True, site='https://example.invalid', qualificationFolder='/qualification', targetPath='/qualification/FICTIONAL-issued.txt', sourceUniqueId='fictional-source', sourceETag='"1"', EventUID='LC04-PUBLICATION-FIXTURE', requestId='fixture-request', occurredOn='2026-10-18T00:00:00Z', scope=scope, decision=dict(scope, FictionalTest=True, EventUID='fictional-authorisation', DecisionOutcome='Approved (recorded)', DecisionReference='fictional://decision', Stage='Decision', RecordState='Recorded', ConditionsState='None recorded', ReadinessEventUID='fictional-readiness'))
        reference = {'properties': {'definition': {'parameters': {'$authentication': {'type': 'SecureObject', 'defaultValue': {}}, '$connections': {'type': 'Object', 'defaultValue': {}}}}, 'connectionReferences': {'shared_sharepointonline': {'source': 'Embedded', 'connectionName': 'fictional-connection'}}}}
        return request, reference, raw

    def test_profile_is_manual_serial_and_stopped(self):
        result = mod.build(*self.fixture())
        self.assertEqual(result['properties']['state'], 'Stopped')
        trigger = result['properties']['definition']['triggers']['manual']
        self.assertEqual(trigger['kind'], 'Button')
        self.assertEqual(trigger['runtimeConfiguration']['concurrency']['runs'], 1)

    def test_missing_decision_refuses_before_any_write(self):
        result = mod.build(*self.fixture())
        gate = result['properties']['definition']['actions']['Decision_exists']
        self.assertEqual(gate['else']['actions']['Refuse_DecisionUnavailable']['inputs']['runError']['code'], 'DecisionUnavailable')
        self.assertIn('Decision_guard', gate['actions'])

    def test_no_case_writes_overwrite_or_notifications(self):
        import json
        result = mod.build(*self.fixture())
        encoded = json.dumps(result)
        self.assertNotIn('overwrite=true', encoded)
        self.assertIn('overwrite=false', encoded)
        self.assertNotIn('shared_teams', encoded)
        self.assertNotIn('shared_office365', encoded)
        self.assertNotIn('X-HTTP-Method', encoded)
        self.assertIn('TargetChanged', encoded)
        self.assertIn('PublicationConflict', encoded)
        self.assertIn('\"DecisionOutcome\": \"Unknown\"', encoded)
        self.assertIn('\"VerificationResult\": \"Not verified\"', encoded)
        self.assertIn('OccurredOn', encoded)

    def test_unapproved_mismatched_or_real_inputs_refuse(self):
        for edit in [lambda r: r.update(FictionalTest=False), lambda r: r.update(targetPath='/real-policy'), lambda r: r['decision'].update(DecisionOutcome='Endorsed (recorded)'), lambda r: r['decision'].update(DocumentSHA256='0'*64), lambda r: r['scope'].update(DocumentSHA256='0'*64)]:
            req, ref, raw = self.fixture()
            edit(req)
            with self.assertRaises(ValueError):
                mod.build(req, ref, raw)


if __name__ == '__main__':
    unittest.main()
