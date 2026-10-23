"""Follow-up presentation contracts with synthetic schema and bindings."""
import json
import copy
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_followup_views import compile_views, verify_views, ROOT
from ppg_guided_workspace import target_state


class FollowupViewsTests(unittest.TestCase):
    def setUp(self):
        config = json.loads((ROOT / 'config/followup-views.json').read_text())
        self.fields = [{'InternalName': f, 'TypeAsString': 'Text'} for f in config['fields']]
        self.bindings = dict(site='https://example.test/sites/demo', queue_path='/sites/demo/Lists/Cases',
                             readiness_path='/sites/demo/Lists/Readiness/AllItems.aspx',
                             assurance_path='/sites/demo/Lists/Assurance/AllItems.aspx')

    def bundle(self):
        return compile_views(**self.bindings, fields=self.fields)

    def test_additive_and_all_cases(self):
        bundle = self.bundle()
        self.assertEqual(len(bundle), 3)
        for item in bundle:
            params = item['create']['parameters']
            self.assertFalse(params['SetAsDefaultView'])
            self.assertFalse(params['PersonalView'])
            self.assertTrue(params['Paged'])
            self.assertNotIn('<Where>', params['Query'])
            self.assertIn('Name="ID"', params['Query'])
            self.assertNotIn('display:none', item['formatter']['CustomFormatter'])

    def test_each_focus_first_and_no_assignment_inferred(self):
        expected = ['Next action:', 'Recorded role:', 'Target as recorded:']
        for item, label in zip(self.bundle(), expected):
            formatter = json.loads(item['formatter']['CustomFormatter'])
            self.assertEqual(formatter['rowFormatter']['children'][1]['children'][0]['txtContent'].strip(), label)
            self.assertIn('no assignment inferred', json.dumps(formatter))
            self.assertIn('confirm agreement', json.dumps(formatter))

    def test_schema_drift_refuses(self):
        self.fields.pop()
        with self.assertRaises(ValueError): self.bundle()
        self.setUp()
        self.fields[4]['TypeAsString'] = 'User'
        with self.assertRaises(ValueError): self.bundle()

    def test_bindings_reject_expression_injection_and_other_sites(self):
        for path in ['/sites/elsewhere/Lists/Cases', "/sites/demo/Lists/a'b", '/sites/demo/../Cases', '/sites/demo/Lists/Cases?x=1']:
            self.bindings['queue_path'] = path
            with self.assertRaises(ValueError): self.bundle()

    def test_root_site_rejects_external_and_backslash_bindings(self):
        self.bindings['site'] = 'https://example.test'
        for path in ['//other.test/Lists/Cases', '/Lists/\\other.test', '/Lists/Case\tName']:
            self.bindings.update(queue_path=path, readiness_path='/Lists/Ready', assurance_path='/Lists/Assurance')
            with self.assertRaises(ValueError): self.bundle()

    def native_views(self):
        result = []
        for expected in self.bundle():
            p = expected['create']['parameters']
            result.append(dict(Title=p['Title'], DefaultView=False, PersonalView=False,
                               Paged=True, RowLimit=p['RowLimit'], ViewFields={'Items':p['ViewFields']},
                               ViewQuery=p['Query'], CustomFormatter=expected['formatter']['CustomFormatter']))
        return result

    def test_saved_readback_accepts_semantic_json_and_xml(self):
        native = self.native_views()
        native[0]['ViewQuery'] = native[0]['ViewQuery'].replace(' />', '/>')
        native[0]['CustomFormatter'] = json.dumps(json.loads(native[0]['CustomFormatter']), indent=2)
        self.assertEqual(verify_views(self.bundle(), native), {'verifiedViews': 3})

    def test_saved_readback_refuses_missing_duplicate_and_presentation_drift(self):
        native = self.native_views()
        for candidate in [native[1:], native + [native[0]]]:
            with self.assertRaises(ValueError): verify_views(self.bundle(), candidate)
        for key, value in [('DefaultView', True), ('PersonalView', True), ('Paged', False),
                           ('RowLimit', 100), ('ViewFields', {'Items':['Title']}),
                           ('ViewQuery', ''), ('CustomFormatter', '{}')]:
            candidate = copy.deepcopy(native)
            candidate[0][key] = value
            with self.assertRaises(ValueError): verify_views(self.bundle(), candidate)

    def test_target_categories_do_not_infer_agreement(self):
        today = date(2026, 10, 18)
        for value, prefix in [('', 'No target'), (' ', 'Pending'), ('after consultation', 'Pending'),
                              ('2026-02-29', 'Invalid'), ('2024-02-29', 'Past'),
                              ('2026-10-18', 'Recorded'), ('2027-01-01', 'Recorded')]:
            self.assertTrue(target_state(value, today).startswith(prefix), value)


if __name__ == '__main__': unittest.main()
