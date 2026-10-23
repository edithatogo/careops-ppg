"""Prevent technical proof from becoming invented user benefit or unsafe success."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_technical_usability import result, render, digest


def fixture():
    refusals = {'hold': {'runId': 'private-refusal-handle', 'actions': 3}}
    assurance = {'qualified': True, 'qualifiedDistinctCycleRuns': 2, 'qualifiedFullCycles': 1,
                 'cycleCompleteActionRecords': 10, 'counts': {'cases': 2}, 'realPolicyEffects': False,
                 'activeNativeRuns': 0, 'allRefusalWritersSkippedAndFourListsFourFoldersPreserved': True,
                 'twentyArtifactMetadataFramesAndOriginalEditedIssuedBytesPreserved': True,
                 'allNineExactStarted': True, 'sixFreshNativeSafeRefusalRuns': refusals,
                 'refusalCompleteActionRecords': 3, 'nativeGenerationQualified': False,
                 'nativeGeometry': [{'stage': 'example', 'actionCount': 5, 'maximumActionDepth': 2,
                                     'maximumExpressionCharacters': 100}]}
    manifest = {'qualified': True, 'qualifiedCycleRunIds': ['private-first-handle', 'private-replay-handle'],
                'currentNineRawProfiles': [{'stage': 'example', 'state': 'Started',
                                          'definitionReferencesModificationTimeExact': True}],
                'qualifiedFullCycles': 1, 'cycleCompleteActionRecords': 10, 'counts': {'cases': 2},
                'realPolicyEffects': False, 'activeNativeRuns': 0, 'safeRefusalRuns': refusals,
                'refusalCompleteActionRecords': 3, 'observedUTC': '2026-10-21T12:00:00Z'}
    return manifest, assurance, {'passed': True, 'tests': 5}


def build(values):
    m, a, checks = copy.deepcopy(values)
    raw = json.dumps(a).encode()
    m['technicalAssurance'] = {'SHA256': digest(raw)}
    return result(json.dumps(m).encode(), raw, json.dumps(checks).encode(), 'a'*40)


class TechnicalUsabilityTests(unittest.TestCase):
    def test_outputs_do_not_expose_run_handles_or_invent_user_benefits(self):
        report = build(fixture())
        published = json.dumps(report)+''.join(render(report))
        self.assertNotIn('private-first-handle', published)
        self.assertNotIn('private-refusal-handle', published)
        self.assertEqual(report['observation']['actualUserSampleCount'], 0)
        self.assertIsNone(report['observation']['timeSavedSeconds'])
        self.assertIsNone(report['observation']['handsOnSeconds'])
        self.assertIn('not measured', published)

    def test_duplicate_runs_and_inconsistent_counts_refuse(self):
        for field, value in [('qualifiedCycleRunIds', ['same', 'same']), ('counts', {'cases': 999}),
                             ('cycleCompleteActionRecords', 11)]:
            values = fixture(); values[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build(values)

    def test_active_runs_missing_preservation_or_real_effects_refuse(self):
        for field, value in [('activeNativeRuns', 1), ('realPolicyEffects', True),
                             ('allRefusalWritersSkippedAndFourListsFourFoldersPreserved', False)]:
            values = fixture(); values[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                build(values)

    def test_pinned_assurance_tampering_refuses(self):
        m, a, checks = fixture(); m['technicalAssurance'] = {'SHA256': '0'*64}
        with self.assertRaisesRegex(ValueError, 'Pinned'):
            result(json.dumps(m).encode(), json.dumps(a).encode(), json.dumps(checks).encode(), 'a'*40)

    def test_unqualified_profiles_and_excessive_geometry_refuse(self):
        values = fixture(); values[0]['currentNineRawProfiles'][0]['state'] = 'Stopped'
        with self.assertRaises(ValueError): build(values)
        values = fixture(); values[1]['nativeGeometry'][0]['maximumActionDepth'] = 9
        with self.assertRaises(ValueError): build(values)


if __name__ == '__main__':
    unittest.main()
