"""Bound native Text255 summaries while preserving independently bound full notes."""
import copy
import unittest
from build_prepared_implementation import build, digest
from test_prepared_implementation import fixture
from test_prepared_closure_check import Expressions


def note_binding():
    source, target, binding = fixture()
    field = {'InternalName': 'ImplementationActionsNote', 'TypeAsString': 'Note',
             'RichText': False, 'AppendOnly': False, 'ReadOnlyField': False}
    binding.update(implementationActionsNoteField=field,
                   approvedImplementationActionsNoteFieldSHA256=digest(field))
    return source, target, binding


def entered(length):
    return {'text': 'Record implementation', 'text_1': 'LC04-IMPL-PREPARED-NOTE-TEST',
            'text_2': 'FICTIONAL ' + 'x' * (length - 10),
            'text_3': 'fictional://implementation/evidence', 'text_4': 'FICTIONAL verify'}


class ImplementationActionNotesTests(unittest.TestCase):
    def test_legacy_text255_refuses_overflow_before_any_writer(self):
        result = build(*fixture())
        actions = result['properties']['definition']['actions']
        schema = result['properties']['definition']['triggers']['manual']['inputs']['schema']
        self.assertEqual(schema['properties']['text_2']['maxLength'], 255)
        self.assertNotIn('ImplementationActionsNote', actions['Implementation_payload']['inputs'])
        for length, accepted in ((255, True), (256, False), (1000, False)):
            with self.subTest(length=length):
                ev = Expressions(outputs={'Test_trigger': entered(length)})
                self.assertEqual(ev.evaluate(actions['Validate_implementation_input']['expression']), accepted)

    def test_plain_note_contract_and_exact_review_pin_are_required(self):
        source, target, binding = note_binding()
        for key, value in [('InternalName', 'OtherColumn'), ('TypeAsString', 'Text'),
                           ('RichText', True), ('AppendOnly', True), ('ReadOnlyField', True)]:
            bad = copy.deepcopy(binding)
            bad['implementationActionsNoteField'][key] = value
            bad['approvedImplementationActionsNoteFieldSHA256'] = digest(bad['implementationActionsNoteField'])
            with self.subTest(key=key), self.assertRaises(ValueError):
                build(source, target, bad)
        bad = copy.deepcopy(binding); bad['approvedImplementationActionsNoteFieldSHA256'] = '0' * 64
        with self.assertRaises(ValueError): build(source, target, bad)
        del bad['implementationActionsNoteField']
        with self.assertRaises(ValueError): build(source, target, bad)

    def test_note_preserves_long_text_and_legacy_summary_stays_bounded(self):
        args = note_binding(); original = copy.deepcopy(args)
        result = build(*args); self.assertEqual(args, original)
        actions = result['properties']['definition']['actions']
        payload = actions['Implementation_payload']['inputs']
        self.assertEqual(result['properties']['definition']['triggers']['manual']['inputs']['schema']['properties']['text_2']['maxLength'], 2000)
        for length, accepted in ((255, True), (256, True), (1000, True), (2000, True), (2001, False)):
            with self.subTest(length=length):
                values = entered(length); ev = Expressions(outputs={'Test_trigger': values})
                self.assertEqual(ev.evaluate(actions['Validate_implementation_input']['expression']), accepted)
                self.assertEqual(ev.evaluate(payload['ImplementationActionsNote']), values['text_2'])
                summary = ev.evaluate(payload['ImplementationActions'])
                self.assertLessEqual(len(summary), 255)
                if length <= 255: self.assertEqual(summary, values['text_2'])
                else: self.assertIn('full action note', summary)

    def test_replay_and_final_readback_detect_changed_or_missing_full_note(self):
        actions = build(*note_binding())['properties']['definition']['actions']
        for read, guard in [('Find_implementation', 'Verify_implementation_replay'),
                            ('Read_implementation', 'Verify_implementation_after')]:
            check = "equals(first(body('" + read + "'))?['ImplementationActionsNote'],outputs('Implementation_payload')?['ImplementationActionsNote'])"
            self.assertIn(check, actions[guard]['expression'])
            text = "FICTIONAL full actions:\noperator's evidence & preserved detail — " + 'x' * 1000
            for stored, expected in ((text, True), (text[:-1] + 'y', False), (None, False)):
                ev = Expressions({read: [{'ImplementationActionsNote': stored}]},
                                 {'Implementation_payload': {'ImplementationActionsNote': text}})
                self.assertEqual(ev.evaluate('@' + check), expected)


    def test_retained_verification_freezes_full_note_not_its_summary(self):
        from build_prepared_verification import build as verification_build
        from test_prepared_verification import fixture as verification_fixture
        implementation = build(*note_binding())
        _, target, binding = verification_fixture()
        text = "FICTIONAL retained operator's actions:\n" + 'x' * 1100
        ev = Expressions(outputs={'Test_trigger': {'text_2': text}})
        payload = implementation['properties']['definition']['actions']['Implementation_payload']['inputs']
        parent = binding['retainedImplementation']
        parent.update(ImplementationActionsNote=text,
                      ImplementationActions=ev.evaluate(payload['ImplementationActions']))
        binding['approvedImplementationDefinitionSHA256'] = digest(implementation['properties']['definition'])
        result = verification_build(implementation, target, binding)
        frozen = result['properties']['definition']['actions']['Implementation_payload']['inputs']
        verifier = Expressions(outputs={'Test_trigger': {'text_2': 'Inconclusive'}})
        self.assertEqual(verifier.evaluate(frozen['ImplementationActionsNote']), text)
        self.assertEqual(verifier.evaluate(frozen['ImplementationActions']), parent['ImplementationActions'])
        del parent['ImplementationActionsNote']
        with self.assertRaisesRegex(ValueError, 'full implementation action note'):
            verification_build(implementation, target, binding)

    def test_runtime_verification_requires_and_retains_current_full_note(self):
        from build_selected_prepared_verification import build as selected_build
        from test_selected_prepared_verification import fixture as selected_fixture, select
        from build_operator_entry import _flatten
        legacy, target, binding, case, parent = selected_fixture()
        implementation = build(*note_binding())
        _flatten(implementation['properties']['definition']['actions'])['Read_selected_case']['inputs']['parameters']['parameters/uri'] = _flatten(legacy['properties']['definition']['actions'])['Read_selected_case']['inputs']['parameters']['parameters/uri']
        binding['approvedImplementationDefinitionSHA256'] = digest(implementation['properties']['definition'])
        result = selected_build(implementation, target, binding)
        actions = result['properties']['definition']['actions']
        text = 'FICTIONAL full actions: ' + 'x' * 1000
        parent.update(ImplementationActionsNote=text,
                      ImplementationActions=Expressions(outputs={'Test_trigger': {'text_2': text}}).evaluate(implementation['properties']['definition']['actions']['Implementation_payload']['inputs']['ImplementationActions']))
        current, held, ev = select(actions, case, [parent])
        self.assertIsNone(held)
        self.assertEqual(current['ImplementationActionsNote'], text)
        self.assertEqual(ev.evaluate(actions['Implementation_payload']['inputs']['ImplementationActionsNote']), text)
        for value in (None, '', 'not fictional', 'FICTIONAL ' + 'x' * 2000):
            changed = {**parent, 'ImplementationActionsNote': value}
            self.assertEqual(select(actions, case, [changed])[1], 'SelectedVerification_parent_valid')


if __name__ == '__main__': unittest.main()
