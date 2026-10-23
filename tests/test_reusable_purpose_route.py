"""Check cross-source route refusal and preservation on the emitted decision flow."""
import copy
import unittest

from build_reusable_purpose_route import build, BINDINGS
from build_multisource_case_context import digest
from build_operator_entry import _flatten
from build_selected_event_routes import audit_actions
from test_multisource_case_context import fixture as context_fixture
from test_prepared_closure_check import Expressions


def fixture():
    first, profiles = context_fixture()
    first['name'] = 'existing-purpose-flow'
    d = first['properties']['definition']
    reader = _flatten(d['actions'])['Read_source_before']
    props = d['triggers']['manual']['inputs']['schema']['properties']
    props['text_7'] = {'type': 'string', 'title': 'Fictional route', 'description': 'Use original route'}
    for name, path in BINDINGS.items():
        if name == 'Find_prepared_receipt':
            d['actions'][name] = copy.deepcopy(reader)
            d['actions'][name]['inputs']['parameters']['parameters/uri'] = '_api/original-receipt'
            continue
        node = {'type': 'If' if path == ('expression',) else 'Compose', 'runAfter': {}}
        target = node
        for key in path[:-1]:
            target[key] = {}
            target = target[key]
        target[path[-1]] = ('@equals(1,1)' if path == ('expression',) else 'FICTIONAL original')
        if name == 'Purpose_profile': target[path[-1]] = [{'DecisionReference': 'fictional://original/decision'}]
        if name == 'Native_purpose_receipt': target[path[-1]] = {'reference': 'fictional://original/route', 'SHA256': 'original-digest'}
        if name == 'Ready_consultation_Receipt': target[path[-1]] = [{'SubjectRole': 'FICTIONAL original'}]
        if node['type'] == 'If': node.update(actions={}, **{'else': {'actions': {}}})
        d['actions'][name] = node
    d['actions']['Read_prepared_source_final'] = copy.deepcopy(reader)
    d['actions']['Validate_purpose_input'] = {'type': 'If', 'runAfter': {}, 'expression':
        "@and(equals(triggerBody()?['text_7'],'fictional://original/route'),equals(triggerBody()?['text'],'Committee endorsement'))",
        'actions': {}, 'else': {'actions': {}}}
    d['actions']['Retained_purpose_writer'] = copy.deepcopy(reader)
    params = d['actions']['Retained_purpose_writer']['inputs']['parameters']
    params['parameters/method'] = 'POST'
    params['parameters/body'] = {'FictionalTest': True, 'RecordState': 'Recorded'}
    second = copy.deepcopy(first)
    n = _flatten(second['properties']['definition']['actions'])
    ctx = n['Selected_case_context']['inputs']
    for key in ('DocumentUID', 'UniqueId', 'ETag'): ctx['sourcePins'][key] = profiles[1][key]
    for key, src in [('DocumentReference', 'DocumentReference'), ('ReviewedVersionRef', 'ReviewedVersionRef'), ('DocumentSHA256', 'sha256')]:
        ctx['scope'][key] = profiles[1][src]
    def replace(v):
        if isinstance(v, str): return v.replace('original', 'additional')
        if isinstance(v, dict): return {k: replace(x) for k, x in v.items()}
        if isinstance(v, list): return [replace(x) for x in v]
        return v
    for name, path in {**BINDINGS, 'Validate_purpose_input': ('expression',)}.items():
        target = n[name]
        for key in path[:-1]: target = target[key]
        target[path[-1]] = replace(target[path[-1]])
    second['properties']['definition']['triggers']['manual']['inputs']['schema']['properties']['text_7']['description'] = 'Use additional route'
    return first, second, profiles


def compose(a, b, profiles):
    return build(a, b, profiles, {'approvedOriginalDefinitionSHA256': digest(a['properties']['definition']),
        'approvedAdditionalDefinitionSHA256': digest(b['properties']['definition'])})


class ReusablePurposeTests(unittest.TestCase):
    def test_cross_source_route_is_refused_before_source_reads_or_writer(self):
        a, b, profiles = fixture()
        out = compose(a, b, profiles)
        n = _flatten(out['properties']['definition']['actions'])
        for index, profile in enumerate(profiles):
            for route in ('original', 'additional', 'unknown'):
                inputs = {'text': 'Committee endorsement', 'text_7': 'fictional://' + route + '/route'}
                ev = Expressions(outputs={'SourceProfiles_selected': profile, 'Input': inputs})
                evaluate = lambda value: ev.evaluate(value.replace('triggerBody()', "outputs('Input')"))
                self.assertEqual(evaluate(n['Validate_purpose_input']['expression']), route != 'unknown')
                self.assertEqual(evaluate(n['SourceProfiles_operation']['expression']), route == ('additional' if index else 'original'))
        self.assertEqual(n['Read_source_before']['runAfter'], {'SourceProfiles_verify': ['Succeeded']})
        self.assertEqual(n['SourceProfiles_operation_refused']['inputs']['runStatus'], 'Failed')

    def test_selected_decision_references_do_not_inherit_another_sources_route(self):
        a, b, profiles = fixture(); before = copy.deepcopy((a, b))
        out = compose(a, b, profiles); n = _flatten(out['properties']['definition']['actions'])
        for i, profile in enumerate(profiles):
            label = 'additional' if i else 'original'
            ev = Expressions(outputs={'SourceProfiles_selected': profile})
            self.assertEqual(ev.evaluate(n['Purpose_profile']['inputs'][0]['DecisionReference']), 'fictional://' + label + '/decision')
            self.assertEqual(ev.evaluate(n['Ready_consultation_Receipt']['inputs']['requiredRoleResults'][0]['SubjectRole']), 'FICTIONAL ' + label)
        self.assertEqual((a, b), before)
        self.assertEqual(n['Retained_purpose_writer'], _flatten(a['properties']['definition']['actions'])['Retained_purpose_writer'])
        self.assertEqual(out['properties']['connectionReferences'], a['properties']['connectionReferences'])
        self.assertEqual(out['properties']['state'], 'Stopped')
        self.assertEqual(audit_actions(out['properties']['definition'])['actionCount'], audit_actions(a['properties']['definition'])['actionCount'] + 8)
        original = copy.deepcopy(a['properties']['definition']['triggers'])
        actual = copy.deepcopy(out['properties']['definition']['triggers'])
        del original['manual']['inputs']['schema']['properties']['text_7']['description']
        del actual['manual']['inputs']['schema']['properties']['text_7']['description']
        self.assertEqual(actual, original)

    def test_unreviewed_writer_prerequisite_form_and_source_override_refuse(self):
        for mode in ('writer', 'prerequisite', 'form', 'override'):
            a, b, profiles = fixture(); n = _flatten(b['properties']['definition']['actions'])
            if mode == 'writer': n['Retained_purpose_writer']['inputs']['parameters']['parameters/body']['FictionalTest'] = False
            elif mode == 'prerequisite': n['Find_prepared_receipt']['runAfter'] = {'Resolve_context': ['Succeeded']}
            elif mode == 'form': b['properties']['definition']['triggers']['manual']['inputs']['schema']['required'] = []
            else:
                for flow in (a, b):
                    _flatten(flow['properties']['definition']['actions'])['Read_prepared_source_final']['inputs']['parameters']['parameters/headers'] = {'X-HTTP-Method': 'DELETE'}
            with self.subTest(mode=mode), self.assertRaises(ValueError): compose(a, b, profiles)


if __name__ == '__main__': unittest.main()
