"""Runtime selection over synthetic native observations, without tenant writes."""
import copy
import json
import unittest

from build_operator_entry import _flatten
from build_prepared_implementation import digest
from build_selected_prepared_verification import build
from test_prepared_verification import fixture as retained_fixture
from test_prepared_closure_check import Expressions

COLLECTION = "_api/web/lists(guid'00000000-0000-4000-8000-000000000008')/items"
FILE = {'UniqueId': '00000000-0000-4000-8000-000000000001', 'ETag': '"native-file,4"'}


def fixture():
    source, target, binding = retained_fixture()
    node = _flatten(source['properties']['definition']['actions'])['Read_selected_case']
    node['inputs']['parameters']['parameters/uri'] = (
        "@concat('" + COLLECTION.replace("'", "''") + "(',string(1),')')")
    parent = binding.pop('retainedImplementation')
    binding.update(caseListUri=COLLECTION,
        approvedImplementationDefinitionSHA256=digest(source['properties']['definition']))
    case = {'CaseUID': 'LC-FICTIONAL-OP-FIRST', 'evidenceDraftLink': 'https://example.invalid/site/current.docx'}
    parent.update(CaseUID=case['CaseUID'], DocumentReference=case['evidenceDraftLink'],
        ReviewedVersionRef='sharepoint:' + FILE['UniqueId'] + ':' + FILE['ETag'])
    return source, target, binding, case, parent


def select(actions, case, rows, file=None, history_extra=None, cases=None):
    trigger = {'text': 'Record verification', 'text_1': 'LC04-VERIFY-PREPARED-TEST',
        'text_2': 'Verified (recorded)', 'text_3': 'FICTIONAL byte comparison',
        'text_4': 'https://example.invalid/proof.json', 'text_5': 'FICTIONAL next action',
        'text_6': case['CaseUID']}
    ev = Expressions(outputs={'Test_trigger': trigger})
    responses = {'SelectedVerification_cases': {'value': cases if cases is not None else [case]},
        'SelectedVerification_file': file or FILE,
        'SelectedVerification_history': {'value': rows, **(history_extra or {})}}
    for name, action in actions.items():
        if not name.startswith('SelectedVerification_'): continue
        if action['type'] == 'OpenApiConnection': ev.bodies[name] = responses[name]
        elif action['type'] == 'Compose': ev.outputs[name] = ev.evaluate(action['inputs'])
        elif action['type'] == 'If':
            if not ev.evaluate(action['expression']): return None, name, ev
        elif action['type'] == 'Query':
            result = []
            for row in ev.evaluate(action['inputs']['from']):
                ev.current = row
                if ev.evaluate(action['inputs']['where']): result.append(row)
            ev.bodies[name] = result
        else: raise AssertionError(action['type'])
    return ev.outputs['SelectedVerification_parent'], None, ev


class SelectedPreparedVerificationTests(unittest.TestCase):
    def test_two_cases_resolve_native_parents_without_recompiling(self):
        source, target, binding, case, parent = fixture()
        before = copy.deepcopy((source, target, binding)); result = build(source, target, binding)
        self.assertEqual((source, target, binding), before)
        actions = result['properties']['definition']['actions']
        other_case = {**case, 'CaseUID': 'LC-FICTIONAL-OP-SECOND'}
        other = {**parent, 'CaseUID': other_case['CaseUID'], 'Id': 2,
                 'EventUID': 'LC04-IMPL-PREPARED-SECOND', 'GUID': 'different-native-guid'}
        for selected_case, expected in [(case, parent), (other_case, other)]:
            resolved, held, ev = select(actions, selected_case, [parent, other])
            self.assertIsNone(held); self.assertEqual(resolved['EventUID'], expected['EventUID'])
            self.assertEqual(ev.evaluate(actions['Verification_payload']['inputs']['ParentEventUID']), expected['EventUID'])
            self.assertEqual(ev.evaluate(actions['Verification_payload']['inputs']['CaseUID']), selected_case['CaseUID'])

    def test_only_current_native_revision_selected_not_latest_timestamp(self):
        source, target, binding, case, parent = fixture()
        actions = build(source, target, binding)['properties']['definition']['actions']
        old = {**parent, 'ReviewedVersionRef': 'older-version', 'EventUID': 'LC04-IMPL-PREPARED-OLD',
               'OccurredOn': '2099-01-01T00:00:00Z'}
        selected, held, _ = select(actions, case, [old, parent])
        self.assertIsNone(held); self.assertEqual(selected['EventUID'], parent['EventUID'])
        for rows in [[], [parent, {**parent, 'EventUID': 'LC04-IMPL-PREPARED-COMPETING'}]]:
            self.assertEqual(select(actions, case, rows)[1], 'SelectedVerification_unique')

    def test_adverse_or_incomplete_history_never_chosen_around(self):
        source, target, binding, case, parent = fixture()
        actions = build(source, target, binding)['properties']['definition']['actions']
        for key, value in [('ConditionsState', 'Open'), ('FictionalTest', False),
                           ('SupersedesEventUID', 'other'), ('odata.etag', '*'), ('GUID', '')]:
            bad = {**parent, key: value}
            self.assertEqual(select(actions, case, [bad])[1], 'SelectedVerification_parent_valid')
            self.assertEqual(select(actions, case, [bad, parent])[1], 'SelectedVerification_unique')
        for marker in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink'):
            with self.subTest(marker=marker):
                self.assertEqual(select(actions, case, [parent], history_extra={marker: 'more'})[1],
                                 'SelectedVerification_unique')
        self.assertEqual(select(actions, case, [parent], cases=[case, case])[1], 'SelectedVerification_one_case')

    def test_unsafe_case_or_file_route_holds_before_file_read(self):
        source, target, binding, case, parent = fixture()
        actions = build(source, target, binding)['properties']['definition']['actions']
        for link in ['https://elsewhere.invalid/doc.docx', 'https://example.invalid/site/a.docx?x=1',
                     "https://example.invalid/site/a'b.docx", 'https://example.invalid/site/../a.docx']:
            self.assertEqual(select(actions, {**case, 'evidenceDraftLink': link}, [parent])[1], 'SelectedVerification_link')
        self.assertEqual(select(actions, {**case, 'CaseUID': "LC-FICTIONAL-OP-a'b"}, [parent])[1], 'SelectedVerification_input')

    def test_existing_writer_proof_guards_and_frozen_parent_readback_retained(self):
        source, target, binding, case, parent = fixture()
        result = build(source, target, binding); actions = result['properties']['definition']['actions']
        flat = _flatten(actions)
        writers = {k for k, v in flat.items() if v.get('type') == 'OpenApiConnection'
                   and v['inputs']['parameters']['parameters/method'] != 'GET'}
        self.assertEqual(writers, {'Create_verification'})
        self.assertEqual(actions['Verify_record_producer_trust']['expression'], '@and(false)')
        self.assertEqual(actions['Ensure_implementation']['type'], 'Compose')
        self.assertIn('Verify_retained_implementation', actions['Ensure_implementation']['runAfter'])
        self.assertNotIn('COMPILER-RUNTIME-PARENT', json.dumps(result))
        self.assertEqual(actions['Implementation_payload']['inputs']['ConditionsState'], 'None recorded')
        with self.assertRaises(ValueError): build(source, target, {**binding, 'retainedImplementation': parent})
        with self.assertRaises(ValueError): build(source, target, {**binding, 'caseListUri': COLLECTION + '?x=1'})


if __name__ == '__main__': unittest.main()
