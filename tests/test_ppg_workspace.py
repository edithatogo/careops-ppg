import copy
import importlib.util
import json
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workspace', ROOT / 'scripts/ppg_workspace.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class WorkspaceTests(unittest.TestCase):
    def test_manifest_and_future_capability(self):
        m = json.loads((ROOT / 'config/workspace.example.json').read_text())
        self.assertTrue(w.validate(m))
        future = copy.deepcopy(m['capabilities'][0])
        future.update(key='future-example', lifecycle='planned', resources=[], dependencies=['catalogue'])
        m['capabilities'].append(future)
        self.assertTrue(w.validate(m))
        m['capabilities'].append(future)
        with self.assertRaises(ValueError):
            w.validate(m)

    def test_schema_rejects_invalid_types_and_unresolved_resources(self):
        m = json.loads((ROOT / 'config/workspace.example.json').read_text())
        m['statusPolicy']['notifications'] = True
        with self.assertRaises(ValueError):
            w.validate(m)
        m['statusPolicy']['notifications'] = False
        m['surfaces'][0]['resourceRef'] = 'missing-resource'
        with self.assertRaises(ValueError):
            w.validate(m)
        m['surfaces'][0]['resourceRef'] = 'hub'
        m['capabilities'][0]['resources'] = 'not-an-array'
        with self.assertRaises(ValueError):
            w.validate(m)

    def test_native_flow_writes_only_bound_presentation_row(self):
        spec = importlib.util.spec_from_file_location('flow_builder', ROOT / 'scripts/build_workspace_status_flow.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        binding = {'destination': {'siteUrl': 'https://example.invalid/sites/test'},
                   'workspace': {'statusListId': 'status-list', 'statusItemId': 7}}
        source = {'env': 'test', 'refs': {'shared_sharepointonline': {'connectionName': 'existing', 'source': 'Embedded'}}}
        flow = builder.build(binding, source)
        writes = []
        def walk(actions):
            for action in actions.values():
                inputs = action.get('inputs', {})
                params = inputs.get('parameters', {}) if isinstance(inputs, dict) else {}
                if params.get('parameters/method') == 'POST':
                    writes.append(params['parameters/uri'])
                walk(action.get('actions', {}))
        walk(flow['definition']['actions'])
        self.assertEqual(writes, ["_api/web/lists(guid'status-list')/items(7)"] * 2)
        self.assertEqual(flow['definition']['triggers']['Every_15_minutes']['runtimeConfiguration']['concurrency']['runs'], 1)
        self.assertNotIn('shared_teams', json.dumps(flow))

    def test_no_healthy_on_missing_or_inconsistent_evidence(self):
        self.assertEqual(w.project_status({}, {}, {})['status'], 'unknown')

    def test_display_freshness_boundaries_preserve_input_and_health(self):
        now = datetime(2026, 10, 15, 4, tzinfo=timezone.utc)
        for health in ('healthy', 'held', 'failed'):
            for age, expected in ((-1, 'unknown'), (0, health), (60, health),
                                  (1800, health), (1801, 'stale')):
                with self.subTest(health=health, age_seconds=age):
                    status = {'status': health,
                              'projectedAt': (now - timedelta(seconds=age)).isoformat(),
                              'reason': 'Retained evidence',
                              'lastSuccessfulReconciliation': '2026-10-14T03:00:00Z'}
                    original = copy.deepcopy(status)
                    self.assertEqual(w.display_status(status, now), expected)
                    self.assertEqual(status, original)

    def test_display_missing_or_invalid_projection_is_unknown(self):
        now = datetime(2026, 10, 15, 4, tzinfo=timezone.utc)
        for status in ({'status': 'healthy'},
                       {'status': 'held', 'projectedAt': None},
                       {'status': 'failed', 'projectedAt': 'invalid'}):
            with self.subTest(status=status):
                original = copy.deepcopy(status)
                self.assertEqual(w.display_status(status, now), 'unknown')
                self.assertEqual(status, original)

    def test_health_hold_failure_recovery_and_staleness(self):
        now = datetime(2026, 10, 15, 4, tzinfo=timezone.utc)
        source = {'checkedUtc': '2026-10-15T03:59:00Z', 'sourceETag': 'v1'}
        checkpoint = {'status': 'completed', 'asOfUtc': '2026-10-15T03:00:00Z', 'centralSourceETag': 'v1', 'readbackCount': 985}
        self.assertEqual(w.project_status(source, checkpoint, {'status': 'completed', 'asOfUtc': checkpoint['asOfUtc']}, now)['status'], 'healthy')
        self.assertEqual(w.project_status(source, checkpoint, {}, now)['status'], 'unknown')
        source['sourceETag'] = 'v2'
        attempt = {'status': 'failed_partial_or_unverified', 'asOfUtc': '2026-10-15T03:30:00Z', 'attemptedWrites': 0}
        held = w.project_status(source, checkpoint, attempt, now)
        self.assertEqual(held['status'], 'held')
        source['sourceChanged'] = False  # a later poll never overrides version comparison
        self.assertEqual(w.project_status(source, checkpoint, attempt, now)['status'], 'held')
        attempt['attemptedWrites'] = 1
        self.assertEqual(w.project_status(source, checkpoint, attempt, now)['status'], 'failed')
        self.assertEqual(w.display_status(held, now + timedelta(minutes=31)), 'stale')
        checkpoint.update(centralSourceETag='v2', asOfUtc='2026-10-15T03:50:00Z')
        self.assertEqual(w.project_status(source, checkpoint, attempt, now)['status'], 'healthy')
        source['checkedUtc'] = '2026-10-15T01:00:00Z'
        self.assertEqual(w.project_status(source, checkpoint, attempt, now)['status'], 'unknown')
        source['sourceETag'] = 'v3'
        self.assertEqual(w.project_status(source, checkpoint, attempt, now)['status'], 'held')


if __name__ == '__main__':
    unittest.main()
