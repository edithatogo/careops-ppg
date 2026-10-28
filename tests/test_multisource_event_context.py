"""Exercise the actual context/event/manual builders; no native acceptance claim."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/lifecycle'))
from build_multisource_event_context import build
from build_multisource_case_context import digest
from build_selected_case_context import build as context_build
from build_selected_event_routes import build as events
from build_case_reference_entry import build as manual, definition_digest
from build_operator_entry import _flatten
from test_multisource_case_context import fixture as context_fixture
from test_case_reference_entry import fixture as selected_fixture, COLLECTION
from test_selected_event_routes import fixtures as event_fixture
from test_prepared_closure_check import Expressions


def fixture(kind):
    _, profiles = context_fixture(); probe, button, _ = selected_fixture()
    context = context_build(probe, {'qualificationOnly': True, 'siteUrl': 'https://example.invalid/site',
        'caseListUri': COLLECTION, 'evidenceFolder': '/site/evidence', 'source': profiles[0]})
    _, target, binding = event_fixture()
    target['properties']['connectionReferences'] = copy.deepcopy(context['properties']['connectionReferences'])
    binding['approvedContextDefinitionSHA256'] = digest(context['properties']['definition'])
    routed = events(kind, context, target, binding)
    flow = manual(routed, button, {'qualificationOnly': True,
        'approvedDefinitionSHA256': definition_digest(routed['properties']['definition']),
        'approvedButtonTriggerSHA256': definition_digest(button['properties']['definition']['triggers']['manual'])})
    return flow, profiles


class MultisourceEventContextTests(unittest.TestCase):
    def test_both_consumers_preserve_inputs_writer_form_and_references(self):
        for kind in ('request', 'response'):
            flow, profiles = fixture(kind); before = copy.deepcopy((flow, profiles))
            out = build(flow, profiles, digest(flow['properties']['definition']), kind)
            self.assertEqual((flow, profiles), before)
            self.assertEqual(out['properties']['state'], 'Stopped')
            self.assertEqual(out['properties']['connectionReferences'], flow['properties']['connectionReferences'])
            self.assertEqual(out['properties']['definition']['triggers'], flow['properties']['definition']['triggers'])
            a = _flatten(flow['properties']['definition']['actions']); b = _flatten(out['properties']['definition']['actions'])
            for name in ('Create_offer', 'Offer_payload', 'Verify_offer_before', 'Event_after_checks', 'Route_ownership_event'):
                if name in ('Route_ownership_event', 'Verify_offer_before'):
                    if name == 'Verify_offer_before':
                        self.assertTrue(b[name]['expression'].startswith('@and('+a[name]['expression'][1:]+','))
                    else:self.assertEqual(a[name]['expression'], b[name]['expression'])
                    self.assertEqual(a[name]['runAfter'], b[name]['runAfter'])
                    self.assertEqual(a[name]['else'], b[name]['else'])
                else:self.assertEqual(a[name], b[name])

    def test_event_discovery_parent_history_and_readback_refuse_continuations(self):
        for kind in ('request', 'response'):
            flow, profiles = fixture(kind); out = build(flow, profiles, digest(flow['properties']['definition']), kind)
            n = _flatten(out['properties']['definition']['actions'])
            before = ['Find_offer'] + (['Read_current_offer', 'Read_response_history'] if kind == 'response' else [])
            for guard, readers in [('Verify_offer_before', before), ('Verify_offer', ['Read_offer'])]:
                for reader in readers:
                    for marker in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink'):
                        clause = "empty(body('"+reader+"')?['"+marker+"'])"
                        self.assertIn(clause, n[guard]['expression'])
                        self.assertFalse(Expressions(bodies={reader: {marker: 'unread-page'}}).evaluate('@'+clause))

    def test_only_explicit_event_modes_enter_each_source_gate(self):
        for kind in ('request', 'response'):
            flow, profiles = fixture(kind); out = build(flow, profiles, digest(flow['properties']['definition']), kind)
            expression = _flatten(out['properties']['definition']['actions'])['SourceProfiles_operation']['expression']
            field = 'text' if kind == 'request' else 'text_5'
            limits = _flatten(out['properties']['definition']['actions'])['Selected_case_context']['inputs']['limits']
            self.assertNotIn('otherOperationsRetainOriginalSource', limits)
            self.assertEqual(limits['eventOperationField'], field)
            self.assertEqual(limits['eligibleEventOperations'], list(
                ('Ownership offer', 'Consultation request') if kind == 'request'
                else ('Ownership response', 'Consultation response')))
            expression = expression.replace("triggerBody()?['"+field+"']", "outputs('Mode')")
            for mode in ('Ownership offer', 'Consultation request', 'Ownership response', 'Consultation response', 'Check context', 'Project ownership', 'unknown'):
                expected = mode in (('Ownership offer', 'Consultation request') if kind == 'request' else ('Ownership response', 'Consultation response'))
                self.assertEqual(Expressions(outputs={'Mode': mode}).evaluate(expression), expected)

    def test_both_profiles_select_exactly_and_refresh_uses_selected_uid(self):
        for kind in ('request', 'response'):
            flow, profiles = fixture(kind); out = build(flow, profiles, digest(flow['properties']['definition']), kind)
            n = _flatten(out['properties']['definition']['actions'])
            for profile in profiles:
                request = {k: profile[s] for k,s in [('DocumentUID','DocumentUID'),('DocumentReference','DocumentReference'),('ReviewedVersionRef','ReviewedVersionRef'),('DocumentSHA256','sha256')]}
                ev = Expressions(outputs={'Parse_baseline': {'request': request}, 'SourceProfiles_selected': profile})
                for row in profiles:
                    ev.current = row
                    self.assertEqual(ev.evaluate(n['SourceProfiles_matches']['inputs']['where']), row == profile)
                for name in ('Read_source_after','Offer_source_before','Offer_source_after'):
                    self.assertIn(profile['UniqueId'], ev.evaluate(n[name]['inputs']['parameters']['parameters/uri']))

    def test_unknown_mode_stale_digest_duplicate_and_wrong_source_are_refused(self):
        flow, profiles = fixture('request')
        for kind, sources, sha in [('unknown', profiles, digest(flow['properties']['definition'])),
                                   ('request', profiles, '0'*64),
                                   ('request', profiles+[profiles[0]], digest(flow['properties']['definition'])),
                                   ('request', [{**profiles[0], 'content': 'changed'}], digest(flow['properties']['definition']))]:
            with self.assertRaises(ValueError):build(flow, sources, sha, kind)

    def test_wrong_mode_guard_extra_writer_and_changed_refresh_refuse(self):
        for change in ('gate', 'writer', 'refresh', 'retry'):
            flow, profiles = fixture('request'); n = _flatten(flow['properties']['definition']['actions'])
            if change == 'gate':n['Validate_event_operation']['expression'] = '@true'
            elif change == 'writer':flow['properties']['definition']['actions']['Unexpected_writer'] = copy.deepcopy(n['Create_offer'])
            elif change == 'refresh':n['Offer_source_before']['inputs']['parameters']['parameters/uri'] = '_api/web/other'
            else:n['Create_offer']['inputs'].pop('retryPolicy')
            with self.subTest(change=change), self.assertRaises(ValueError):
                build(flow, profiles, digest(flow['properties']['definition']), 'request')

    def test_response_validation_and_single_run_order_cannot_be_bypassed(self):
        for change in ('resolve', 'response', 'concurrency'):
            flow, profiles = fixture('response'); d = flow['properties']['definition']
            if change == 'resolve':d['actions']['Resolve_context']['runAfter'] = {}
            elif change == 'response':d['actions']['Validate_response_input']['runAfter'] = {}
            else:d['triggers']['manual']['runtimeConfiguration']['concurrency']['runs'] = 2
            with self.subTest(change=change), self.assertRaises(ValueError):
                build(flow, profiles, digest(d), 'response')


if __name__ == '__main__':unittest.main()
