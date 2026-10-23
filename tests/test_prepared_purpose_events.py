"""Safety checks and synthetic evaluation of emitted purpose-history predicates."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/lifecycle'))
from build_prepared_purpose_events import build, PURPOSES
from build_prepared_decision_outcome import digest
from build_selected_event_routes import audit_actions
from test_prepared_decision_outcome import fixture as decision_fixture, flatten
from test_prepared_closure_check import Expressions

SCOPE = {'CaseUID': 'LC-FICTIONAL-OP-LOCAL-PURPOSE-TEST', 'DocumentReference': 'https://example.invalid/site/prepared.docx',
         'ReviewedVersionRef': 'fictional-prepared-v2', 'DocumentSHA256': 'b' * 64}
PROFILE = {'reference': 'fictional://test/purpose-profile', 'version': '1', 'FictionalTest': True, 'grantsRealAuthority': False}


def fixture():
    c, t, b = decision_fixture()
    b['observedFieldTypes'] = {'ActorName': 'Text', 'Summary': 'Text', 'EvidenceReference': 'Text',
                              'DecisionReference': 'Text', 'ConditionsNotes': 'Text', 'NextAction': 'Note'}
    b['observedTextMaxLengths'] = {k: 255 for k in ('EventUID', 'ActorName', 'Summary', 'EvidenceReference', 'DecisionReference', 'ConditionsNotes')}
    b['fictionalRouteProfile'] = copy.deepcopy(PROFILE)
    return c, t, b


def rows():
    result = []
    for i, (label, code, outcome) in enumerate(PURPOSES):
        reason = 'FICTIONAL locally evaluated assertion only'
        result.append({**SCOPE, 'EventUID': 'FICTIONAL-purpose-' + code, 'Id': i + 1, 'GUID': 'FICTIONAL-GUID-' + code,
            'odata.etag': '"1"', 'Stage': 'Decision', 'RecordState': 'Recorded', 'DecisionOutcome': outcome,
            'DecisionReference': PROFILE['reference'] + '/' + PROFILE['version'] + '/' + digest(PROFILE) + '/' + code,
            'ReadinessEventUID': 'FICTIONAL-ready', 'FictionalTest': True, 'ConditionsState': 'None recorded',
            'ParentEventUID': None if i == 0 else 'FICTIONAL-purpose-' + PURPOSES[i - 1][1], 'SupersedesEventUID': None,
            'ActorName': 'FICTIONAL purpose actor', 'Summary': 'FICTIONAL ' + label + ': ' + reason,
            'ConditionsNotes': reason, 'NextAction': 'FICTIONAL retain this local test',
            'EvidenceReference': 'fictional://test/assertion/' + code, 'OccurredOn': '2026-10-19T12:00:00Z'})
    return result


def history_result(history, selected=3, profile=None, continuation=None):
    c, t, b = fixture()
    if profile is not None: b['fictionalRouteProfile'] = profile
    work = build(c, t, b)['properties']['definition']['actions']['Check_purpose_prerequisites']['actions']
    outputs = {'Native_prepared_revision': {'preparedRevision': {'scope': SCOPE}},
        'Native_readiness_observation': {'selectedEventUID': 'FICTIONAL-ready'},
        'Chosen_purpose': {'ordinal': selected, 'EventUID': 'FICTIONAL-purpose-' + PURPOSES[selected][1]}}
    outputs.update({'Purpose_uid_' + code: 'FICTIONAL-purpose-' + code for _, code, _ in PURPOSES})
    ev = Expressions({'Purpose_before_assurance': {'value': history, **(continuation or {})},
                      'Readiness_scope': [{'AssessedOn': '2026-10-18T14:00:00Z'}]}, outputs)
    active = False
    for name, action in work.items():
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
        if name == 'Purpose_before_history_consistent': return ev.outputs[name]
    raise AssertionError('No history result')


class PreparedPurposeTests(unittest.TestCase):
    def test_partial_history_cannot_qualify_a_valid_prefix_or_identical_retry(self):
        for key in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink'):
            for selected in range(4):
                for count in (selected, selected + 1):
                    with self.subTest(key=key, selected=selected, count=count):
                        self.assertFalse(history_result(rows()[:count], selected,
                            continuation={key: 'https://example.invalid/unread-history'}))
                        self.assertTrue(history_result(rows()[:count], selected,
                            continuation={key: None}))

    def test_explicit_four_purpose_prefixes_and_complete_retry_history(self):
        all_rows = rows()
        for selected in range(4):
            with self.subTest(selected=selected):
                self.assertTrue(history_result(all_rows[:selected], selected))
                self.assertTrue(history_result(all_rows[:selected + 1], selected))
        self.assertTrue(history_result(all_rows, 3))
        self.assertFalse(history_result([], 3))
        self.assertFalse(history_result([all_rows[0], all_rows[2]], 3))

    def test_current_deferred_open_or_extra_scope_scenario_blocks_every_purpose(self):
        adverse = {**rows()[0], 'EventUID': 'FICTIONAL-other-deferred', 'DecisionOutcome': 'Deferred', 'ConditionsState': 'Open'}
        for selected in range(4): self.assertFalse(history_result([adverse], selected))
        for outcome in ['Deferred', 'Rejected', 'Unknown']:
            changed = rows(); changed[-1]['DecisionOutcome'] = outcome
            self.assertFalse(history_result(changed))
        self.assertFalse(history_result(rows() + [{**rows()[0], 'EventUID': 'FICTIONAL-extra-approval'}]))
        for stage in ['Publication', 'Implementation', 'Verification']:
            self.assertFalse(history_result(rows() + [{**rows()[0], 'EventUID': 'FICTIONAL-later-' + stage,
                'Stage': stage, 'ParentEventUID': 'FICTIONAL-unrelated', 'VerificationResult': 'Verified (recorded)'}]))

    def test_cross_scope_parent_profile_ready_tokens_and_global_corrections_hold(self):
        for field, value in [('CaseUID', 'FICTIONAL-other'), ('ParentEventUID', 'FICTIONAL-wrong'),
                             ('DecisionReference', 'fictional://test/other-profile'), ('ReadinessEventUID', 'FICTIONAL-old-ready'),
                             ('odata.etag', '*'), ('FictionalTest', False), ('ConditionsState', 'Open'),
                             ('OccurredOn', '2099-01-01T00:00:00Z')]:
            changed = rows(); changed[1][field] = value
            with self.subTest(field=field): self.assertFalse(history_result(changed))
        self.assertFalse(history_result(rows() + [{**rows()[0], 'CaseUID': 'FICTIONAL-other'}]))
        self.assertFalse(history_result(rows() + [{**rows()[0], 'EventUID': 'FICTIONAL-correction',
            'CaseUID': 'FICTIONAL-other', 'SupersedesEventUID': rows()[0]['EventUID']}]))
        old = rows()
        for row in old: row.update(DocumentReference='fictional://original-source', ReviewedVersionRef='original-v1')
        self.assertFalse(history_result(old))

    def test_changed_profile_cannot_reinterpret_retained_assertion_or_hide_digest(self):
        old_committee = rows()[:1]
        self.assertTrue(history_result(old_committee, 1))
        v2 = {**PROFILE, 'version': '2'}
        self.assertFalse(history_result(old_committee, 1, v2))
        c, t, b = fixture(); old = build(c, t, b)
        b['fictionalRouteProfile'] = v2; new = build(c, t, b)
        old_a = flatten(old['properties']['definition']['actions'])
        new_a = flatten(new['properties']['definition']['actions'])
        # Identity remains occurrence/revision/purpose-bound; a changed profile is
        # refused against existing assertions instead of silently creating a new ID.
        self.assertEqual(old_a['Purpose_uid_committee']['inputs'], new_a['Purpose_uid_committee']['inputs'])
        old_ref = old_a['Purpose_profile']['inputs'][0]['DecisionReference']
        new_ref = new_a['Purpose_profile']['inputs'][0]['DecisionReference']
        self.assertIn(digest(PROFILE), old_ref); self.assertIn(digest(v2), new_ref)
        self.assertNotEqual(old_ref, new_ref)
        b['fictionalRouteProfile'] = {**PROFILE, 'reference': 'fictional://' + 'a' * 152, 'version': 'v' * 12}
        with self.assertRaisesRegex(ValueError, 'Text255'): build(c, t, b)

    def test_only_one_retry_disabled_writer_and_no_projection_or_other_resource(self):
        c, t, b = fixture(); original = copy.deepcopy((c, t, b)); out = build(c, t, b); actions = flatten(out['properties']['definition']['actions'])
        writers = [(k, v) for k, v in actions.items() if v['type'] == 'OpenApiConnection' and v['inputs']['parameters']['parameters/method'] != 'GET']
        self.assertEqual([k for k, _ in writers], ['Create_purpose'])
        self.assertEqual(writers[0][1]['inputs']['retryPolicy'], {'type': 'none'})
        self.assertEqual(writers[0][1]['inputs']['parameters']['parameters/uri'], b['assuranceCollectionUri'])
        self.assertNotIn('Route_ownership_projection', actions); self.assertEqual((c, t, b), original)
        audit_actions(out['properties']['definition'])
        # Query outputs are arrays; the stable projection must not dereference .value.
        for suffix in ['before', 'after']:
            self.assertEqual(actions['Purpose_other_' + suffix + '_stable']['inputs']['from'], "@body('Purpose_other_" + suffix + "')")
        for key in ['policyApproved', 'actorAuthorityQualified', 'progressionGranted']:
            self.assertIs(actions['Native_purpose_receipt']['inputs'][key], False)
        self.assertIsNone(actions['Held_purpose_after']['inputs']['createdCount'])

    def test_explicit_route_version_inputs_and_rehashed_unsafe_prerequisite_rejected(self):
        for change in ['route-authority', 'profile-untracked', 'source-pin', 'connection', 'method']:
            c, t, b = fixture()
            if change == 'route-authority': b['fictionalRouteProfile']['grantsRealAuthority'] = True
            if change == 'profile-untracked': b['fictionalRouteProfile']['unrecordedRule'] = 'unverified'
            if change == 'source-pin': b['approvedCaseWorkDefinitionSHA256'] = 'wrong'
            if change == 'connection': t['properties']['connectionReferences'] = {}
            if change == 'method':
                c['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']['inputs']['parameters']['parameters/method'] = 'POST'
                b['approvedCaseWorkDefinitionSHA256'] = digest(c['properties']['definition'])
            with self.subTest(change=change), self.assertRaises(ValueError): build(c, t, b)
        out = build(*fixture()); a = flatten(out['properties']['definition']['actions'])
        self.assertIn(PROFILE['reference'] + '@1', a['Validate_purpose_input']['expression'])
        self.assertEqual(a['Resolve_context']['runAfter'], {'Validate_purpose_input': ['Succeeded']})
        payload = a['Purpose_payload']['inputs']
        self.assertEqual(payload['ConditionsNotes'], "@triggerBody()?['text_2']")
        self.assertEqual(payload['NextAction'], "@triggerBody()?['text_4']")
        self.assertEqual(payload['ReadinessEventUID'], "@outputs('Native_readiness_observation')?['selectedEventUID']")


if __name__ == '__main__': unittest.main()
