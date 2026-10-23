import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/lifecycle'))
from build_prepared_decision_outcome import build, digest
from build_prepared_readiness_check import build_actions as readiness
from build_selected_event_routes import audit_actions
from test_selected_event_routes import fixtures


def fixture():
    c, _, _ = fixtures(); d = c['properties']['definition']
    def read(uri):
        x = copy.deepcopy(d['actions']['Resolve_context']['actions']['Read_selected_case'])
        x['inputs']['parameters']['parameters/uri'] = uri; return x
    fields = {k: {'type': 'string', 'title': k} for k in ('text', 'text_1', 'text_2', 'text_3', 'text_4')}
    trigger = {'type': 'Request', 'kind': 'Button', 'inputs': {'schema': {'type': 'object', 'properties': fields}}}
    d['triggers']['manual'] = copy.deepcopy(trigger)
    d['triggers']['manual']['inputs']['schema']['properties']['text_6'] = {'type': 'string', 'title': 'Case reference'}
    d['actions']['Route_preparation_check'] = {'type': 'If', 'expression': "@equals(triggerBody()?['text'],'Check preparation')",
        'runAfter': {'Resolve_context': ['Succeeded']}, 'actions': {'Native_prepared_revision': {'type': 'Compose', 'inputs': {}, 'runAfter': {}}}, 'else': {'actions': {}}}
    rb = {'readinessCollectionUri': "_api/web/lists(guid'00000000-0000-4000-8000-000000000009')/items",
          'consultationCollectionUri': "_api/web/lists/getbytitle('PPG Consultation and Handoff Events')/items",
          'requiredFictionalRoles': ['FICTIONAL content-review role']}
    d['actions']['Route_readiness_check'] = {'type': 'If', 'expression': '@true',
        'runAfter': {'Route_preparation_check': ['Succeeded']}, 'actions': readiness(c, rb), 'else': {'actions': {}}}
    # Dangerous unrelated source writers must never be imported.
    writer = read('_api/web/protected-case'); writer['inputs']['parameters']['parameters/method'] = 'POST'
    d['actions']['Route_ownership_projection'] = writer
    target = {'properties': {'state': 'Stopped', 'definition': {'triggers': {'manual': trigger}, 'actions': {}},
                            'connectionReferences': copy.deepcopy(c['properties']['connectionReferences'])}}
    binding = {'qualificationOnly': True, 'approvedCaseWorkDefinitionSHA256': digest(d),
        'approvedTargetDefinitionSHA256': digest(target['properties']['definition']),
        'assuranceCollectionUri': "_api/web/lists(guid'00000000-0000-4000-8000-000000000010')/items", 'eventUIDUnique': True,
        'observedFieldTypes': {'ConditionsNotes': 'Text', 'NextAction': 'Note', 'Summary': 'Text', 'EvidenceReference': 'Text', 'DecisionReference': 'Text'},
        'observedTextMaxLengths': {key: 255 for key in ('Title', 'Summary', 'ConditionsNotes', 'EvidenceReference', 'DecisionReference')}}
    return c, target, binding


def flatten(group):
    result = {}
    for name, a in group.items():
        result[name] = a; result.update(flatten(a.get('actions', {}))); result.update(flatten(a.get('else', {}).get('actions', {})))
    return result


class PreparedDecisionTests(unittest.TestCase):
    def test_only_one_possible_assurance_creator_and_no_case_writer_leak(self):
        c, t, b = fixture(); original = copy.deepcopy((c, t, b)); out = build(c, t, b)
        a = flatten(out['properties']['definition']['actions'])
        writes = [(k, v) for k, v in a.items() if v['type'] == 'OpenApiConnection' and v['inputs']['parameters']['parameters/method'] != 'GET']
        self.assertEqual([k for k, _ in writes], ['Create_decision'])
        creator = writes[0][1]
        self.assertEqual(creator['inputs']['parameters']['parameters/uri'], b['assuranceCollectionUri'])
        self.assertEqual(creator['inputs']['retryPolicy'], {'type': 'none'})
        self.assertNotIn('Route_ownership_projection', a)
        self.assertEqual((c, t, b), original)
        audit_actions(out['properties']['definition'])

    def test_review_pin_connection_and_idle_target_are_required(self):
        for change in ('source-pin', 'target-pin', 'connection', 'running', 'uniqueness', 'limits'):
            c, t, b = fixture()
            if change == 'source-pin': b['approvedCaseWorkDefinitionSHA256'] = 'wrong'
            if change == 'target-pin': b['approvedTargetDefinitionSHA256'] = 'wrong'
            if change == 'connection': t['properties']['connectionReferences'] = {}
            if change == 'running': t['properties']['state'] = 'Started'
            if change == 'uniqueness': b['eventUIDUnique'] = False
            if change == 'limits': b['observedTextMaxLengths']['ConditionsNotes'] = 100
            with self.subTest(change=change), self.assertRaises(ValueError): build(c, t, b)

    def test_even_rehashed_prerequisites_cannot_smuggle_writes_or_new_resource(self):
        for change in ('method', 'override', 'dataset', 'body'):
            c, t, b = fixture(); x = c['properties']['definition']['actions']['Route_readiness_check']['actions']['Check_prepared_readiness']['actions']['Readiness_history_after']['inputs']['parameters']
            if change == 'method': x['parameters/method'] = 'POST'
            if change == 'override': x['parameters/headers'] = {'X-HTTP-Method': 'MERGE'}
            if change == 'dataset': x['dataset'] = 'https://other.invalid'
            if change == 'body': x['parameters/body'] = ''
            b['approvedCaseWorkDefinitionSHA256'] = digest(c['properties']['definition'])
            with self.subTest(change=change), self.assertRaises(ValueError): build(c, t, b)

    def test_input_guard_precedes_all_reads_and_long_action_does_not_enter_text_field(self):
        out = build(*fixture()); d = out['properties']['definition']; a = flatten(d['actions'])
        self.assertEqual(d['actions']['Resolve_context']['runAfter'], {'Validate_operator_input': ['Succeeded']})
        allowlist = d['actions']['Validate_operator_input']['expression']
        self.assertIn("createArray('Rejected','Deferred','Return for changes')", allowlist)
        self.assertNotIn('Approved', allowlist)
        for key, maximum in [('text_2', 200), ('text_3', 255), ('text_4', 4000)]:
            self.assertIn("length(string(triggerBody()?['" + key + "']))," + str(maximum), allowlist)
        payload = a['Decision_payload']['inputs']
        self.assertEqual(payload['ConditionsNotes'], "@triggerBody()?['text_2']")
        self.assertEqual(payload['NextAction'], "@triggerBody()?['text_4']")
        self.assertIn("'Rejected','Deferred'", payload['DecisionOutcome'])

    def test_scope_and_readiness_come_from_same_execution_not_form_or_old_fixture(self):
        out = build(*fixture()); a = flatten(out['properties']['definition']['actions']); p = a['Decision_payload']['inputs']
        for key in ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256'):
            self.assertIn("outputs('Native_prepared_revision')?['preparedRevision']?['scope']", p[key])
            self.assertNotIn('triggerBody', p[key])
        self.assertEqual(p['ReadinessEventUID'], "@first(body('Readiness_scope'))?['EventUID']")
        prereq = a['Check_decision_prerequisites']['expression']
        for key in ['readinessEvidenceConsistent', 'technicalConsultationCoverageComplete', 'nativeContextRevalidated']:
            self.assertIn(key, prereq)
        for key in ('ParentEventUID', 'SupersedesEventUID'): self.assertIsNone(p[key])
        for suffix in ['before', 'after']:
            for kind in ['readiness', 'consultation']:
                name = 'Decision_' + kind + '_' + suffix
                self.assertEqual(a[name]['inputs']['parameters']['parameters/headers']['Accept'], 'application/json;odata=minimalmetadata')
                self.assertEqual(a[name + '_stable']['inputs']['select'], "@union(item(),json('{\"odata.id\":null}'))")
        self.assertIsNone(a['Held_decision_after']['inputs']['createdCount'])
        for key in ['policyApproved', 'actorAuthorityQualified', 'progressionGranted']:
            self.assertIs(a['Native_prepared_decision_receipt']['inputs'][key], False)


if __name__ == '__main__': unittest.main()
