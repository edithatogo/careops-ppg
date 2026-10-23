"""Evaluate the composed implementation gates with fictional native observations."""
import copy
import re
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'tools/lifecycle'),
               str(Path(__file__).resolve().parents[1] / 'tools/policy-editions')]
from build_prepared_implementation import build, digest
from build_prepared_binary_publication import build as publication_build
from test_prepared_binary_publication import fixture as publication_fixture, flatten
from test_prepared_closure_check import Expressions, SCOPE
from test_prepared_purpose_events import rows as purpose_rows, SCOPE as PURPOSE_SCOPE


def fixture():
    purpose, target, binding = publication_fixture()
    publication = publication_build(purpose, target, binding)
    return publication, target, {'qualificationOnly': True,
        'approvedPublicationDefinitionSHA256': digest(publication['properties']['definition']),
        'approvedTargetDefinitionSHA256': digest(target['properties']['definition'])}


def graph():
    return build(*fixture())['properties']['definition']['actions']


def frame_evaluator():
    bodies = {}
    pins = {key: {'UniqueId': 'FICTIONAL-' + key, 'ETag': '"1"'}
            for key in ['file', 'qualificationReceipt', 'template', 'source', 'baseline']}
    pins['file']['nativeVersion'] = '2.0'
    out = {'Native_prepared_revision': {'currentCaseETag': '"3"', 'preparedRevision': {
        'scope': SCOPE, **{k: pins[k] for k in ['file', 'qualificationReceipt', 'template']}}},
        'Selected_case_context': {'sourcePins': pins['source'], 'baselineUniqueId': pins['baseline']['UniqueId'],
                                  'baselineETag': pins['baseline']['ETag']},
        'Chosen_purpose': {'EventUID': 'LC03-PURPOSE-FICTIONAL'}, 'Publication_uid': 'FICTIONAL-publication',
        'Implementation_after_Purpose_before_history_consistent': True,
        'Implementation_after_Purpose_case_before': {'headers': {'ETag': '"3"'}},
        'Test_trigger': {'text': 'Record implementation'}}
    for label, pin in [('draft', 'file'), ('receipt', 'qualificationReceipt'), ('template', 'template'),
                       ('source', 'source'), ('baseline', 'baseline')]:
        bodies['Implementation_after_Purpose_' + label + '_before'] = copy.deepcopy(pins[pin])
    bodies['Implementation_after_Purpose_case_before'] = {'CaseUID': SCOPE['CaseUID'], 'evidenceDraftLink': SCOPE['DocumentReference']}
    for kind, original in [('readiness', 'Readiness_stable_after'), ('consultation', 'Readiness_consultation_stable_after')]:
        bodies['Implementation_after_Purpose_' + kind + '_before'] = {'value': []}
        bodies['Implementation_after_Purpose_' + kind + '_before_stable'] = []
        bodies[original] = []
    for code in ['committee', 'officer', 'coordinator', 'authorisation']:
        bodies['Implementation_after_Purpose_before_rows_' + code] = [{'EventUID': 'FICTIONAL-' + code}]
        out['Implementation_after_Purpose_before_valid_' + code] = True
    bodies.update(Find_publication_before_copy=[{'EventUID': 'FICTIONAL-publication'}], Find_corrections_before_copy=[],
                  Find_existing_publication=[{'EventUID': 'FICTIONAL-publication'}], Find_publication_corrections=[],
                  Publication_others_initial_stable=[], Publication_others_late_stable=[])
    issued = {'UniqueId': 'FICTIONAL-issued', 'ETag': '"1"', 'UIVersionLabel': '1.0', 'Length': '10', 'ServerRelativeUrl': '/site/issued.docx'}
    bodies['Read_issued'] = issued; bodies['Implementation_after_issued'] = copy.deepcopy(issued)
    bodies['Read_binary_proof_before'] = {'UniqueId': 'FICTIONAL-proof', 'ETag': '"1"'}
    bodies['Implementation_after_proof'] = copy.deepcopy(bodies['Read_binary_proof_before'])
    return Expressions(bodies, out)


class PreparedImplementationTests(unittest.TestCase):
    def test_first_timestamp_matches_native_seconds_and_replay_keeps_original(self):
        expression = graph()['Implementation_payload']['inputs']['OccurredOn']
        for clock in ['2026-10-17T22:30:49.6799185Z', '2026-10-17T22:30:49.9999999Z']:
            with patch('test_prepared_closure_check.NOW', clock):
                observed = Expressions({'Find_implementation': []}).evaluate(expression)
                self.assertEqual(observed, '2026-10-17T22:30:49Z')
                for original in ['2026-10-16T12:00:00Z', '2026-10-16T12:00:00.123Z']:
                    self.assertEqual(Expressions({'Find_implementation': [
                        {'OccurredOn': original}]}).evaluate(expression), original)

    def test_actual_composed_history_rejects_open_conditions_and_extra_records(self):
        actions = graph()
        def permitted(rows):
            outputs = {'Native_prepared_revision': {'preparedRevision': {'scope': PURPOSE_SCOPE}},
                       'Native_readiness_observation': {'selectedEventUID': 'FICTIONAL-ready'},
                       'Chosen_purpose': {'ordinal': 3, 'EventUID': 'FICTIONAL-purpose-authorisation'},
                       'Publication_uid': 'FICTIONAL-publication', 'Implementation_uid': 'FICTIONAL-implementation'}
            outputs.update({'Purpose_uid_' + code: 'FICTIONAL-purpose-' + code
                            for code in ['committee', 'officer', 'coordinator', 'authorisation']})
            ev = Expressions({'Purpose_before_assurance': {'value': rows},
                              'Readiness_scope': [{'AssessedOn': '2026-10-18T14:00:00Z'}]}, outputs)
            active = False
            for name, action in actions.items():
                if name == 'Purpose_before_assurance': active = True; continue
                if not active: continue
                if action['type'] == 'Query':
                    result = []
                    for row in ev.evaluate(action['inputs']['from']):
                        ev.current = row
                        if ev.evaluate(action['inputs']['where']): result.append(row)
                    ev.bodies[name] = result
                elif action['type'] == 'Compose': ev.outputs[name] = ev.evaluate(action['inputs'])
                else: raise AssertionError(name)
                if name == 'Purpose_before_selected':
                    return ev.outputs['Purpose_before_history_consistent'] and all(
                        len(ev.bodies['Purpose_before_rows_' + code]) == 1
                        and ev.outputs['Purpose_before_valid_' + code]
                        for code in ['committee', 'officer', 'coordinator', 'authorisation'])
            raise AssertionError('History boundary missing')
        rows = purpose_rows()
        own = dict(rows[0], EventUID='FICTIONAL-implementation', Stage='Implementation')
        self.assertTrue(permitted(rows + [own]))
        changed = copy.deepcopy(rows); changed[2]['ConditionsState'] = 'Open'
        self.assertFalse(permitted(changed))
        self.assertFalse(permitted(rows + [dict(own, EventUID='OTHER-implementation')]))
        self.assertFalse(permitted(rows + [copy.deepcopy(rows[0])]))

    def test_immutable_inputs_pins_and_single_retry_disabled_event_writer(self):
        p, t, b = fixture(); before = copy.deepcopy((p, t, b)); result = build(p, t, b)
        self.assertEqual((p, t, b), before)
        self.assertEqual(result['properties']['state'], 'Stopped')
        actions = flatten(result['properties']['definition']['actions'])
        writers = {k: v for k, v in actions.items() if v['type'] == 'OpenApiConnection'
                   and v['inputs']['parameters']['parameters/method'] != 'GET'}
        self.assertEqual(set(writers), {'Create_implementation'})
        self.assertEqual(writers['Create_implementation']['inputs']['retryPolicy'], {'type': 'none'})
        for key in ['approvedPublicationDefinitionSHA256', 'approvedTargetDefinitionSHA256']:
            bad = copy.deepcopy(b); bad[key] = '0' * 64
            with self.assertRaises(ValueError): build(p, t, bad)

    def test_unqualified_publication_producer_stays_held_no_saved_receipt_unlock(self):
        a = graph()
        self.assertEqual(a['Verify_record_producer_trust']['expression'], '@and(false)')
        self.assertNotIn('Copy_if_absent', a); self.assertNotIn('Ensure_publication', a)
        self.assertIn("equals(length(body('Find_issued')?['value']),1)", a['Verify_target_cardinality']['expression'])

    def test_missing_future_publication_duplicate_or_corrected_implementation_holds(self):
        expression = graph()['Verify_implementation_parent']['expression']
        bodies = {'Find_existing_publication': [{'OccurredOn': '2026-10-19T12:00:00Z'}],
                  'Purpose_before_rows_authorisation': [{'OccurredOn': '2026-10-18T12:00:00Z'}],
                  'Find_implementation': [], 'Find_implementation_corrections': []}
        self.assertTrue(Expressions(bodies).evaluate(expression))
        for key, value in [('Find_existing_publication', []), ('Find_existing_publication', [{'OccurredOn': '2099-01-01T00:00:00Z'}]),
                           ('Find_implementation', [{}, {}]), ('Find_implementation_corrections', [{}])]:
            bad = copy.deepcopy(bodies); bad[key] = value
            with self.subTest(key=key): self.assertFalse(Expressions(bad).evaluate(expression))

    def test_exact_replay_and_changed_actions_scope_parent_or_token(self):
        a = graph(); expression = a['Verify_implementation_replay']['expression']
        payload = {k: 'FICTIONAL-' + k for k in a['Implementation_payload']['inputs']}
        payload['OccurredOn'] = '2026-10-19T12:00:00Z'
        row = {**payload, 'Id': 7, 'GUID': 'FICTIONAL-row', 'odata.etag': '"1"'}
        bodies = {'Find_implementation': [row], 'Find_existing_publication': [{'OccurredOn': '2026-10-18T12:00:00Z'}]}
        outputs = {'Implementation_payload': payload}
        self.assertTrue(Expressions(bodies, outputs).evaluate(expression))
        for key in ['ImplementationActions', 'ParentEventUID', 'DocumentSHA256', 'EvidenceReference', 'odata.etag']:
            changed = copy.deepcopy(bodies); changed['Find_implementation'][0][key] = '*' if key == 'odata.etag' else 'CHANGED'
            with self.subTest(key=key): self.assertFalse(Expressions(changed, outputs).evaluate(expression))

    def test_complete_after_frame_detects_human_edit_stale_issued_proof_and_conditions(self):
        expression = graph()['Implementation_after_frame_check_0']['inputs']
        self.assertTrue(frame_evaluator().evaluate(expression))
        for name, key, value in [('Implementation_after_issued', 'ETag', '"2"'),
                                 ('Implementation_after_proof', 'ETag', '"2"'),
                                 ('Implementation_after_Purpose_draft_before', 'ETag', '"2"'),
                                 ('Implementation_after_Purpose_readiness_before', 'odata.nextLink', 'MORE')]:
            ev = frame_evaluator(); ev.bodies[name][key] = value
            with self.subTest(name=name): self.assertFalse(ev.evaluate(expression))
        ev = frame_evaluator(); ev.outputs['Implementation_after_Purpose_before_history_consistent'] = False
        self.assertFalse(ev.evaluate(expression))

    def test_final_uncertainty_complete_history_and_no_real_completion(self):
        a = graph(); final = a['Verify_implementation_after']
        held = final['else']['actions']['Held_implementation_after']['inputs']
        self.assertIsNone(held['implementationCreatedCount']); self.assertTrue(held['reconcileBeforeRetry'])
        self.assertIn('odata.nextLink', final['expression'])
        self.assertIn('Implementation_others_before_stable', final['expression'])
        self.assertFalse(a['Native_implementation_receipt']['inputs']['implementationCompletionGranted'])
        self.assertFalse(a['Native_implementation_receipt']['inputs']['progressionGranted'])
        flat = flatten(a); refs = set(re.findall(r"(?:body|outputs|actions)\('([^']+)'\)", str(a)))
        self.assertTrue(refs <= flat.keys(), refs - flat.keys())
        self.assertLess(max(len(v['expression']) for v in flat.values() if isinstance(v.get('expression'), str)), 8192)

    def test_actual_final_gate_holds_each_incomplete_history_marker(self):
        actions=graph();payload={key:'FIXTURE-'+key for key in actions['Implementation_payload']['inputs']}
        payload['OccurredOn']='2026-10-19T12:00:00Z'
        row={**payload,'Id':2,'GUID':'FICTIONAL-row','odata.etag':'"1"'}
        history='Implementation_after_Purpose_before_assurance'
        bodies={history:{'value':[row]},'Read_implementation':[row],
            'Read_implementation_corrections':[],'Find_implementation':[],
            'Implementation_others_before_stable':[],'Implementation_others_after_stable':[],
            'Find_existing_publication':[{'OccurredOn':'2026-10-18T12:00:00Z'}]}
        outputs={'Implementation_payload':payload}
        outputs.update({name:True for name in actions if name.startswith('Implementation_after_frame_check_')})
        expression=actions['Verify_implementation_after']['expression']
        self.assertTrue(Expressions(bodies,outputs).evaluate(expression))
        for marker in ('nextLink','@nextLink','odata.nextLink','@odata.nextLink'):
            changed=copy.deepcopy(bodies);changed[history][marker]='MORE'
            with self.subTest(marker=marker):
                self.assertFalse(Expressions(changed,outputs).evaluate(expression))


if __name__ == '__main__': unittest.main()
