"""Check optional closure integration preserves existing writers and modes."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/lifecycle'))
from build_case_work_router import build
from build_prepared_decision_outcome import digest
from build_selected_event_routes import audit_actions
from test_selected_event_routes import fixtures
from test_prepared_decision_outcome import flatten
from build_prepared_closure_check import CHAIN


def fixture():
    c, t, _ = fixtures(); a = c['properties']['definition']['actions']['Resolve_context']['actions']
    reader = copy.deepcopy(a['Read_selected_case'])
    a['Verify_baseline_boundary']['actions']['Read_baseline_before'] = copy.deepcopy(reader)
    req = a['Verify_baseline_boundary']['actions']['Verify_request']['actions']
    req['Read_source_before'] = copy.deepcopy(reader); req['Read_source_content'] = copy.deepcopy(reader)
    pin = digest(c['properties']['definition'])
    common = {'qualificationOnly': True, 'approvedContextDefinitionSHA256': pin,
              'expectedCaseUID': 'LC-FICTIONAL-OP-TEST', 'eventListUri': "_api/web/lists(getbytitle='unused')/items"}
    old = {**common, 'expectedCaseETag': '"1"', 'expectedResponseUID': 'LC02-OP-RESP-TEST',
        'caseItemUri': "_api/web/lists(guid'00000000-0000-4000-8000-000000000007')/items(7)",
        'folderUri': "_api/web/GetFolderByServerRelativePath(decodedurl='/site/evidence')", 'journalName': 'before.json', 'commitName': 'commit.json'}
    rb = {'readinessCollectionUri': "_api/web/lists(guid'00000000-0000-4000-8000-000000000009')/items",
        'consultationCollectionUri': "_api/web/lists/getbytitle('PPG Consultation and Handoff Events')/items", 'requiredFictionalRoles': ['FICTIONAL test role']}
    b = {'legacyProjection': old, 'preparation': {**common,
        'projectionCommitUniqueId': '00000000-0000-4000-8000-000000000008', 'projectionCommitETag': '"1"', 'preparedRevision': None},
        'preparedSelection': {'artifactFolderRelative': '/site/evidence', 'caseEvidenceFieldType': 'Note',
            'templateFileUniqueId': '00000000-0000-4000-8000-000000000011'}, 'preparedReadiness': rb}
    closure = {**rb, 'assuranceCollectionUri': "_api/web/lists(guid'00000000-0000-4000-8000-000000000010')/items",
        'selectedEvents': {key: 'FICTIONAL-' + key for key in CHAIN},
        'purposeReferences': {key: 'fictional://purpose/' + key for key in CHAIN[:4]}}
    return c, t, b, closure


class ClosureRouteTests(unittest.TestCase):
    def test_optional_route_preserves_existing_graphs_and_six_exclusive_writers(self):
        c, t, b, closure = fixture(); original = copy.deepcopy((c, t, b, closure))
        old = build(c, t, b); new = build(c, t, {**b, 'preparedClosure': closure})
        oa = old['properties']['definition']['actions']; na = new['properties']['definition']['actions']
        self.assertNotIn('Route_closure_check', oa)
        for name, action in oa.items():
            if name not in ['Validate_case_operation', 'Route_preparation_check']: self.assertEqual(na[name], action)
        self.assertEqual(na['Route_preparation_check']['actions'], oa['Route_preparation_check']['actions'])
        for result in [old, new]:
            actions = flatten(result['properties']['definition']['actions'])
            writes = {k for k, v in actions.items() if v['type'] == 'OpenApiConnection' and v['inputs']['parameters']['parameters/method'] != 'GET'}
            self.assertEqual(len(writes), 6)
        self.assertEqual((c, t, b, closure), original)
        self.assertEqual(new['properties']['state'], 'Stopped')
        audit_actions(new['properties']['definition'])

    def test_new_route_is_read_only_and_waits_for_same_execution_preparation(self):
        c, t, b, closure = fixture(); out = build(c, t, {**b, 'preparedClosure': closure})
        route = out['properties']['definition']['actions']['Route_closure_check']
        self.assertEqual(route['runAfter'], {'Route_preparation_check': ['Succeeded']})
        self.assertIn("equals(triggerBody()?['text'],'Check closure')", route['expression'])
        for v in flatten(route['actions']).values():
            if v['type'] == 'OpenApiConnection':
                self.assertEqual(v['inputs']['parameters']['parameters/method'], 'GET')
                self.assertNotIn('parameters/body', v['inputs']['parameters'])
        a = flatten(route['actions'])
        scoped = a['Closure_scoped_assurance']['inputs']['where']
        for key in ['CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256']:
            self.assertIn("outputs('Native_prepared_revision')?['preparedRevision']?['scope']?['" + key + "']", scoped)
        self.assertFalse(a['Closure_date_consistent']['inputs'])
        self.assertIsNone(a['Native_closure_observation']['inputs']['nextReviewDate'])
        self.assertIsNone(a['Native_closure_observation']['inputs']['nextReviewEvidenceFileUID'])
        self.assertFalse(a['Native_closure_observation']['inputs']['closurePerformed'])
        self.assertFalse(a['Native_closure_observation']['inputs']['nextOccurrenceCreated'])

    def test_missing_or_unsafe_selections_fail_without_a_historical_default(self):
        c, t, b, closure = fixture()
        for selected in [{}, {**closure['selectedEvents'], 'committee': 'unsafe/path'},
                         {**closure['selectedEvents'], 'committee': 'X' * 256}]:
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                build(c, t, {**b, 'preparedClosure': {**closure, 'selectedEvents': selected}})


if __name__ == '__main__': unittest.main()
