"""Exercise selected-source bindings, refusals and preservation on emitted graphs."""
import copy
import unittest

from build_reusable_consultation_routes import build, BINDINGS, RESPONSE_BINDINGS, READS, _selected
from build_multisource_case_context import digest
from build_operator_entry import _flatten
from build_selected_event_routes import audit_actions
from test_multisource_case_context import fixture as context_fixture
from test_prepared_closure_check import Expressions


def fixture(stage='request'):
    original, profiles = context_fixture()
    original['name'] = 'existing-' + stage
    d = original['properties']['definition']
    for name in ('Test_folder', 'Test_role'):
        d['actions'][name] = {'type': 'Compose', 'inputs': 'original', 'runAfter': {}}
    n = _flatten(d['actions'])
    site = n['Read_selected_case']['inputs']['parameters']['dataset']
    reader = n['Read_source_before']
    for name in READS:
        d['actions'][name] = copy.deepcopy(reader)
        d['actions'][name]['runAfter'] = {'Resolve_context': ['Succeeded']}
        d['actions'][name]['inputs']['parameters']['parameters/uri'] = (
            "_api/web/GetFileById('" + profiles[0]['UniqueId'] + "')?$select=UniqueId,ETag,Length")
    field = 'text' if stage == 'request' else 'text_5'
    choices = ('Ownership offer', 'Consultation request') if stage == 'request' else ('Ownership response', 'Consultation response')
    schema = d['triggers']['manual']['inputs']['schema']
    schema['properties'][field] = {'type': 'string', 'title': 'Action'}
    d['actions']['Validate_event_operation'] = {'type': 'If', 'expression':
        "@contains(createArray('" + "','".join(choices) + "'),triggerBody()?['" + field + "'])",
        'actions': {}, 'else': {'actions': {}}, 'runAfter': {'Resolve_context': ['Succeeded']}}
    d['actions']['Consultation_payload'] = {'type': 'Compose', 'inputs': {'SubjectRole': 'FICTIONAL original role'}, 'runAfter': {}}
    d['actions']['Find_prepared_receipt'] = copy.deepcopy(reader)
    d['actions']['Find_prepared_receipt']['inputs']['parameters']['parameters/uri'] = '_api/original-receipt'
    d['actions']['Native_prepared_revision'] = {'type': 'Compose', 'runAfter': {}, 'inputs':
        {'preparedRevision': {'qualificationReceipt': {'DocumentReference': site + '/original-receipt'}}}}
    d['actions']['Verify_prepared_selection'] = {'type': 'If', 'runAfter': {},
        'expression': "@equals(outputs('Test_folder'),'original')", 'actions': {}, 'else': {'actions': {}}}
    if stage == 'response':
        for name, value in {
            'Consultation_before_checks_0': "@equals(outputs('Test_role'),'FICTIONAL original role')",
            'Consultation_coverage_Problems': {'where': "@not(equals(item()?['SubjectRole'],'FICTIONAL original role'))"},
            'Consultation_coverage_R0_Rows': {'where': "@equals(item()?['SubjectRole'],'FICTIONAL original role')"},
            'Consultation_coverage_Receipt': {'requiredRoleResults': [{'SubjectRole': 'FICTIONAL original role'}]},
        }.items():
            d['actions'][name] = {'type': 'Compose', 'inputs': value, 'runAfter': {}}
    # Include a real transport writer so preservation covers effects, not only reads.
    d['actions']['Retained_writer'] = copy.deepcopy(reader)
    d['actions']['Retained_writer']['inputs']['parameters']['parameters/method'] = 'POST'
    d['actions']['Retained_writer']['inputs']['parameters']['parameters/body'] = {'FictionalTest': True}
    additional = copy.deepcopy(original)
    a = _flatten(additional['properties']['definition']['actions'])
    ctx = a['Selected_case_context']['inputs']
    for key in ('DocumentUID', 'UniqueId', 'ETag'):
        ctx['sourcePins'][key] = profiles[1][key]
    for key, source_key in [('DocumentReference', 'DocumentReference'), ('ReviewedVersionRef', 'ReviewedVersionRef'), ('DocumentSHA256', 'sha256')]:
        ctx['scope'][key] = profiles[1][source_key]
    for name, path in {**BINDINGS, **(RESPONSE_BINDINGS if stage == 'response' else {})}.items():
        target = a[name]
        for key in path[:-1]: target = target[key]
        value = target[path[-1]]
        def change(v):
            if isinstance(v, str): return v.replace('original', 'additional')
            if isinstance(v, dict): return {k: change(x) for k, x in v.items()}
            if isinstance(v, list): return [change(x) for x in v]
            return v
        target[path[-1]] = change(value)
    return original, additional, profiles


def compose(original, additional, profiles, stage='request'):
    return build(original, additional, profiles, {'stage': stage,
        'approvedOriginalDefinitionSHA256': digest(original['properties']['definition']),
        'approvedAdditionalDefinitionSHA256': digest(additional['properties']['definition'])})


class ReusableConsultationTests(unittest.TestCase):
    def test_large_shared_guards_select_literals_without_duplicating_checks(self):
        repeated = ','.join("equals(outputs('Value'),'retained')" for _ in range(180))
        first = "@and(equals(outputs('Role'),'FICTIONAL first')," + repeated + ')'
        second = first.replace('FICTIONAL first', 'FICTIONAL second')
        emitted = _selected(first, second, "outputs('SelectSecond')")
        self.assertLess(len(emitted), 8192)
        self.assertEqual(emitted.count("outputs('Value')"), 180)
        for selected in (True, False):
            for role in ('FICTIONAL first', 'FICTIONAL second'):
                ev = Expressions(outputs={'SelectSecond': selected, 'Role': role, 'Value': 'retained'})
                self.assertEqual(ev.evaluate(emitted), ev.evaluate(second if selected else first))
                ev.outputs['Value'] = 'changed'
                self.assertFalse(ev.evaluate(emitted))

    def test_action_names_and_property_keys_remain_static_in_each_branch(self):
        for first, second in [("@outputs('First')", "@outputs('Second')"),
                              ("@outputs('Record')?['First']", "@outputs('Record')?['Second']")]:
            emitted = _selected(first, second, "outputs('SelectSecond')")
            self.assertTrue(emitted.startswith('@if('))
            for selected in (True, False):
                ev = Expressions(outputs={'SelectSecond': selected, 'First': 'a', 'Second': 'b',
                                          'Record': {'First': 'a', 'Second': 'b'}})
                self.assertEqual(ev.evaluate(emitted), 'b' if selected else 'a')

    def test_both_sources_select_their_role_folder_and_receipt_without_profile_swap(self):
        for stage in ('request', 'response'):
            first, second, profiles = fixture(stage)
            before = copy.deepcopy((first, second, profiles))
            out = compose(first, second, profiles, stage)
            self.assertEqual(before, (first, second, profiles))
            n = _flatten(out['properties']['definition']['actions'])
            for i, profile in enumerate(profiles):
                label = 'additional' if i else 'original'
                ev = Expressions(outputs={'SourceProfiles_selected': profile, 'Test_folder': label})
                self.assertEqual(ev.evaluate(n['Consultation_payload']['inputs']['SubjectRole']), 'FICTIONAL ' + label + ' role')
                self.assertTrue(ev.evaluate(n['Verify_prepared_selection']['expression']))
                self.assertEqual(ev.evaluate(n['Find_prepared_receipt']['inputs']['parameters']['parameters/uri']), '_api/' + label + '-receipt')
                if stage == 'response':
                    for role in ('FICTIONAL original role', 'FICTIONAL additional role'):
                        ev.current = {'SubjectRole': role}
                        self.assertEqual(ev.evaluate(n['Consultation_coverage_R0_Rows']['inputs']['where']), role == 'FICTIONAL ' + label + ' role')
                        self.assertEqual(ev.evaluate(n['Consultation_coverage_Problems']['inputs']['where']), role != 'FICTIONAL ' + label + ' role')
                for name in READS:
                    ev.outputs['Selected_case_context'] = {'sourcePins': profile}
                    self.assertIn(profile['UniqueId'], ev.evaluate(n[name]['inputs']['parameters']['parameters/uri']))
            self.assertEqual(n['Retained_writer'], _flatten(first['properties']['definition']['actions'])['Retained_writer'])
            self.assertEqual(out['properties']['definition']['triggers'], first['properties']['definition']['triggers'])
            self.assertEqual(out['properties']['connectionReferences'], first['properties']['connectionReferences'])
            self.assertEqual(audit_actions(out['properties']['definition'])['actionCount'], audit_actions(first['properties']['definition'])['actionCount'] + 8)
            self.assertEqual(out['properties']['state'], 'Stopped')

    def test_unknown_source_and_unsupported_operation_stop_at_retained_refusal(self):
        first, second, profiles = fixture()
        n = _flatten(compose(first, second, profiles)['properties']['definition']['actions'])
        ev = Expressions(bodies={'SourceProfiles_matches': []})
        self.assertFalse(ev.evaluate(n['SourceProfiles_verify']['expression']))
        self.assertEqual(n['SourceProfiles_refused']['inputs']['runStatus'], 'Failed')
        expression = n['SourceProfiles_operation']['expression'].replace("triggerBody()?['text']", "outputs('Operation')")
        for operation in ('Ownership offer', 'Consultation request', 'Close review', ''):
            self.assertEqual(Expressions(outputs={'Operation': operation}).evaluate(expression), operation in ('Ownership offer', 'Consultation request'))
        self.assertEqual(n['Read_source_before']['runAfter'], {'SourceProfiles_verify': ['Succeeded']})

    def test_changed_writer_connections_form_or_branch_location_are_refused_even_with_new_pin(self):
        for mutation in ('writer', 'connection', 'form', 'branch'):
            first, second, profiles = fixture()
            n = _flatten(second['properties']['definition']['actions'])
            if mutation == 'writer': n['Retained_writer']['inputs']['parameters']['parameters/body']['FictionalTest'] = False
            elif mutation == 'connection': second['properties']['connectionReferences'] = {}
            elif mutation == 'form': second['properties']['definition']['triggers']['manual']['inputs']['schema']['required'] = []
            else:
                group = second['properties']['definition']['actions']
                group['Validate_event_operation']['actions']['Retained_writer'] = group.pop('Retained_writer')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                compose(first, second, profiles)

    def test_stale_definition_pin_and_foreign_source_are_refused(self):
        first, second, profiles = fixture()
        with self.assertRaisesRegex(ValueError, 'definition changed'):
            build(first, second, profiles, {'stage': 'request', 'approvedOriginalDefinitionSHA256': '0'*64,
                'approvedAdditionalDefinitionSHA256': digest(second['properties']['definition'])})
        profiles[1]['DocumentReference'] = 'https://foreign.invalid/source'
        with self.assertRaises(ValueError): compose(first, second, profiles)

    def test_source_reader_method_override_is_refused_even_when_both_variants_match(self):
        first, second, profiles = fixture()
        for flow in (first, second):
            n = _flatten(flow['properties']['definition']['actions'])
            n['Offer_source_before']['inputs']['parameters']['parameters/headers'] = {'X-HTTP-Method': 'DELETE'}
        with self.assertRaisesRegex(ValueError, 'GET transport'):
            compose(first, second, profiles)


if __name__ == '__main__': unittest.main()
