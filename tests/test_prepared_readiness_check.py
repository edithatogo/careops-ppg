import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/lifecycle'))
from build_prepared_readiness_check import build_actions
from build_selected_event_routes import audit_actions
from test_selected_event_routes import fixtures


class PreparedReadinessTests(unittest.TestCase):
    def setUp(self):
        self.context, _, _ = fixtures()
        self.binding = {
            'readinessCollectionUri': "_api/web/lists(guid'00000000-0000-4000-8000-000000000009')/items",
            'consultationCollectionUri': "_api/web/lists/getbytitle('PPG Consultation and Handoff Events')/items",
            'requiredFictionalRoles': ['FICTIONAL content-review role']}

    def test_no_connector_effect_or_form_pin_enters_observer(self):
        before = copy.deepcopy((self.context, self.binding))
        graph = build_actions(self.context, self.binding)
        def walk(actions):
            for action in actions.values():
                if action['type'] == 'OpenApiConnection':
                    params = action['inputs']['parameters']
                    self.assertEqual(params['parameters/method'], 'GET')
                    self.assertNotIn('parameters/body', params)
                    self.assertEqual(params['dataset'], 'https://example.invalid/site')
                walk(action.get('actions', {})); walk(action.get('else', {}).get('actions', {}))
        walk(graph)
        self.assertNotIn('triggerBody(', json.dumps(graph))
        self.assertEqual((self.context, self.binding), before)
        # Sibling dependencies and action namespaces must remain valid when composed.
        combined = copy.deepcopy(self.context['properties']['definition'])
        combined['actions'].update(graph)
        audit_actions(combined)

    def test_truncated_or_filtered_history_cannot_be_requested(self):
        for suffix in ["?$filter=Finding eq 'Ready for decision'", '?$top=1', '?$select=EventUID',
                       '/(1)', '?%24filter=ConditionsState%20ne%20Open', '%3f$top=1']:
            with self.subTest(suffix=suffix):
                bad = {**self.binding, 'readinessCollectionUri': self.binding['readinessCollectionUri'] + suffix}
                with self.assertRaises(ValueError): build_actions(self.context, bad)
        for suffix in ['?$top=1', "?$filter=ConditionsState ne 'Open'"]:
            bad = {**self.binding, 'consultationCollectionUri': self.binding['consultationCollectionUri'] + suffix}
            with self.assertRaises(ValueError): build_actions(self.context, bad)

    def test_write_capable_or_unqualified_reader_is_rejected(self):
        for change in ['method', 'override', 'body', 'provider']:
            c = copy.deepcopy(self.context)
            x = c['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']['inputs']
            if change == 'method': x['parameters']['parameters/method'] = 'POST'
            if change == 'override': x['parameters']['parameters/headers'] = {'X-HTTP-Method': 'MERGE'}
            if change == 'body': x['parameters']['parameters/body'] = '{}'
            if change == 'provider': x['host']['apiId'] = 'unqualified-provider'
            with self.subTest(change=change), self.assertRaises(ValueError): build_actions(c, self.binding)

    def test_empty_or_implied_consultation_plan_cannot_pass(self):
        for roles in [[], ['Real implied reviewer'], ['FICTIONAL role', 'FICTIONAL role']]:
            with self.subTest(roles=roles), self.assertRaises(ValueError):
                build_actions(self.context, {**self.binding, 'requiredFictionalRoles': roles})

    def test_full_history_rechecked_without_discarding_concurrency_tokens(self):
        graph = build_actions(self.context, self.binding)['Check_prepared_readiness']['actions']
        for name in ['Readiness_stable_before', 'Readiness_stable_after',
                     'Readiness_consultation_stable_before', 'Readiness_consultation_stable_after']:
            # Normalize only the request-generated OData response identifier. Native Id,
            # GUID, ETags, timestamps and every business field survive the comparison.
            self.assertEqual(graph[name]['inputs']['select'], "@union(item(),json('{\"odata.id\":null}'))")
        for name in ['Readiness_history_before', 'Readiness_history_after', 'Readiness_consultation_after']:
            self.assertEqual(graph[name]['inputs']['parameters']['parameters/headers']['Accept'],
                             'application/json;odata=minimalmetadata')
        before = graph['Ready_consultation_Runtime_guard']['actions']['Readiness_consultation_before']
        self.assertEqual(before['inputs']['parameters']['parameters/headers']['Accept'],
                         'application/json;odata=minimalmetadata')
        final = graph['Readiness_context_current']['inputs']
        for collection in ['Readiness_history_before', 'Readiness_history_after',
                           'Readiness_consultation_before', 'Readiness_consultation_after']:
            for link in ['odata.nextLink', '@odata.nextLink']:
                self.assertIn("empty(body('" + collection + "')?['" + link + "'])", final)
        for label in ['case', 'draft', 'receipt', 'template', 'source', 'baseline']:
            self.assertIn('Readiness_' + label + '_final', final)
        result = graph['Native_readiness_observation']['inputs']
        self.assertIn('Readiness_context_current', result['readinessEvidenceConsistent'])
        self.assertIn('coverageHistoryComplete', result['readinessEvidenceConsistent'])
        for key in ['contentReadinessGranted', 'progressionGranted', 'policyApproved', 'actorAuthorityQualified']:
            self.assertIs(result[key], False)
        # Cross-version supersession and duplicate event identity are searched in
        # complete history, not only the exact-version subset.
        for name in ['Readiness_identity_rows', 'Readiness_superseders']:
            self.assertEqual(graph[name]['inputs']['from'], "@body('Readiness_history_before')?['value']")


if __name__ == '__main__': unittest.main()
