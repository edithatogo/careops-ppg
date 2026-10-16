import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_readiness import for_version, validate


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.event = dict(EventUID='fictional-event', CaseUID='fictional-case',
                          DocumentReference='fictional-document', ReviewedVersionRef='v1',
                          DocumentSHA256='a'*64, Finding='Not assessed', ConditionsState='Unknown')

    def test_pending_is_honest(self):
        self.assertEqual(validate(self.event), [])
        self.assertFalse(for_version(self.event, 'v1', 'a'*64)['policyApproved'])

    def test_finding_requires_human_evidence_and_na_rationale(self):
        for finding in ('Ready for decision', 'Needs changes', 'Not applicable'):
            self.event['Finding'] = finding
            self.assertIn('required:EvidenceReference', validate(self.event))
            self.assertIn('required:FindingSummary', validate(self.event))

    def test_old_finding_never_applies_to_new_version(self):
        self.event.update(Finding='Ready for decision', AssessorName='Fictional assessor',
                          AssessedOn='2026-10-15', FindingSummary='Fictional finding',
                          EvidenceReference='fictional://evidence')
        self.assertEqual(for_version(self.event, 'v1', 'a'*64)['finding'], 'Ready for decision')
        for version, sha in [('v2', 'a'*64), ('v1', 'b'*64)]:
            result = for_version(self.event, version, sha)
            self.assertFalse(result['appliesToRequestedVersion'])
            self.assertEqual(result['finding'], 'Not assessed')
            self.assertFalse(result['policyApproved'])

    def test_hash_and_open_conditions(self):
        self.event.update(DocumentSHA256='z'*64, ConditionsState='Open')
        self.assertIn('invalid:DocumentSHA256', validate(self.event))
        self.assertIn('required:ConditionsNotes', validate(self.event))


if __name__ == '__main__':
    unittest.main()
