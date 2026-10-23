import copy
import json
from pathlib import Path
import unittest
from scripts.ppg_content_requirements import evaluate


class ContentRequirements(unittest.TestCase):
    def setUp(self):
        self.definition = json.loads(Path('config/ppg-content-modules-v1.json').read_text())
        self.definition['requiredness'] = 'verified'
        self.rule = dict(ruleId='fictional-purpose', moduleKey='core.purpose',
                         status='verified_required', progressionSteps=['review'],
                         templateVerified=True,
                         authorityEvidence=dict(source='fictional-fixture', version='1', sha256='a'*64))
        self.definition['rules'] = [self.rule]
        self.record = dict(ContentKey='one', DocumentUID='fixture', SourceEditionKey='edition',
                           ProposedModule='core.purpose', SourceText='Source remains preserved',
                           ReviewedModule='core.purpose', ReviewText='Reviewed text', BlockReviewState='Reviewed')
    def run_check(self, records=None, context=None, step='review'):
        return evaluate(self.definition, [self.record] if records is None else records,
                        'fixture', 'edition', context or {}, step)
    def test_presence_is_read_only_and_does_not_approve(self):
        before = copy.deepcopy((self.definition, self.record))
        out = self.run_check()
        self.assertEqual(out['readiness'], 'presence_checks_clear')
        self.assertTrue(out['draftEditingAllowed'])
        self.assertFalse(out['lifecycleChanged'] or out['policyApproved'])
        self.assertEqual(before, (self.definition, self.record))
    def test_missing_and_unreviewed_text_hold_only_due_step(self):
        self.record['BlockReviewState'] = 'Unreviewed'
        self.assertEqual(self.run_check()['results'][0]['result'], 'missing_reviewed_content')
        self.assertEqual(self.run_check(step='draft')['results'][0]['result'], 'not_due_at_step')
        self.record['BlockReviewState'] = 'Reviewed'
        self.record['ReviewText'] = ''
        self.assertEqual(self.run_check()['results'][0]['result'], 'missing_reviewed_content')
    def test_condition_unknown_is_not_inferred_false_and_explicit_exclusion_is_safe(self):
        self.rule.update(status='verified_conditional', conditions={'site':['fictional-site'], 'population':['adult']})
        self.assertEqual(self.run_check()['results'][0]['result'], 'unknown_applicability')
        self.assertEqual(self.run_check(context={'site':['other-site']})['results'][0]['result'], 'not_applicable')
        self.assertEqual(self.run_check(context={'site':['fictional-site'],'population':['adult']})['results'][0]['result'], 'present')
    def test_unverified_rules_never_produce_readiness_and_bad_authority_refused(self):
        self.rule['status'] = 'proposed'
        self.assertEqual(self.run_check()['results'][0]['result'], 'unverified_rule')
        self.rule['status'] = 'verified_required'
        self.rule['authorityEvidence']['sha256'] = 'not-a-hash'
        with self.assertRaises(ValueError):self.run_check()
        self.definition['rules'] = []
        self.assertEqual(self.run_check()['readiness'], 'unverified_rules')
    def test_mixed_editions_duplicate_rules_and_unsupported_conditions_refused(self):
        changed = dict(self.record, SourceEditionKey='different')
        with self.assertRaises(ValueError):self.run_check(records=[changed])
        with self.assertRaises(ValueError):self.run_check(records=[self.record,self.record])
        self.definition['rules'].append(copy.deepcopy(self.rule))
        with self.assertRaises(ValueError):self.run_check()
        self.definition['rules'].pop()
        self.rule.update(status='verified_conditional', conditions={'unknown':['value']})
        with self.assertRaises(ValueError):self.run_check()
    def test_cli_refuses_to_replace_a_saved_report(self):
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = dict(definition=self.definition, records=[self.record], documentUID='fixture',
                        sourceEditionKey='edition', context={}, progressionStep='review')
            source, target = root/'input.json', root/'report.json'
            source.write_text(json.dumps(data))
            args = [sys.executable, '-m', 'scripts.ppg_content_requirements', str(source), str(target)]
            subprocess.run(args, check=True, capture_output=True)
            saved = target.read_bytes()
            retry = subprocess.run(args, capture_output=True)
            self.assertNotEqual(retry.returncode, 0)
            self.assertEqual(target.read_bytes(), saved)
    def test_content_from_another_site_cannot_satisfy_a_required_module(self):
        self.record['OptionalModifiers'] = json.dumps({'site':['site-b']})
        self.assertEqual(self.run_check(context={'site':['site-a']})['results'][0]['result'], 'missing_reviewed_content')
        self.assertEqual(self.run_check()['results'][0]['result'], 'unknown_applicability')
        self.assertEqual(self.run_check(context={'site':['site-b']})['results'][0]['result'], 'present')
        self.record['OptionalModifiers'] = 'unstructured text'
        with self.assertRaises(ValueError):self.run_check()
