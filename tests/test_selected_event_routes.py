import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/lifecycle'))
from build_selected_event_routes import build, audit_actions
from build_selected_ownership_offer import build as original_offer
from build_selected_ownership_response import build as original_response


def fixtures():
    def read(previous=None):
        return {'type': 'OpenApiConnection', 'inputs': {'host': {
            'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
            'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
            'parameters': {'dataset': 'https://example.invalid/site',
                'parameters/method': 'GET', 'parameters/uri': '_api/web/fixture'}},
            'runAfter': {previous: ['Succeeded']} if previous else {}}
    def condition(actions, previous=None):
        return {'type': 'If', 'expression': '@true', 'actions': actions, 'else': {'actions': {}},
            'runAfter': {previous: ['Succeeded']} if previous else {}}
    source = {'Read_source_after': read(), 'Recheck_case': read('Read_source_after'),
        'Recheck_baseline': read('Recheck_case'),
        'Verify_source_and_case': condition({'Selected_case_context': {
            'type': 'Compose', 'inputs': {'contextValid': True}, 'runAfter': {}}}, 'Recheck_baseline')}
    baseline = {'Parse_baseline': {'type': 'Compose', 'inputs': {'request': {}}, 'runAfter': {}},
                'Verify_request': condition(source, 'Parse_baseline')}
    definition = {'triggers': {'manual': {'type': 'Request', 'kind': 'ApiConnection',
        'inputs': {'schema': {'rows': {'type': 'array', 'items': {'type': 'object', 'properties': {}}}}}}},
        'actions': {'Resolve_context': {'type': 'Scope', 'runAfter': {}, 'actions': {
            'Read_selected_case': read(), 'Verify_baseline_boundary': condition(baseline, 'Read_selected_case')}},
            'Held_unverified_read': {'type': 'Compose', 'inputs': {'writeCount': 0},
                'runAfter': {'Resolve_context': ['Failed', 'TimedOut']}}}}
    refs = {'shared_sharepointonline': {'connectionName': 'fixture-qualified-connection'}}
    context = {'properties': {'definition': definition, 'connectionReferences': copy.deepcopy(refs)}}
    event_uri = "_api/web/lists/getbytitle('PPG Consultation and Handoff Events')/items"
    creator = read(); creator['inputs']['parameters'].update({'parameters/method': 'POST', 'parameters/uri': event_uri})
    target = {'properties': {'definition': {'actions': {'Create_E1': creator}}, 'connectionReferences': refs}}
    digest = hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return context, target, {'qualificationOnly': True, 'approvedContextDefinitionSHA256': digest,
        'eventListUri': event_uri, 'technicalConsultationRole': 'FICTIONAL content-review role', 'preparedRevision': None}


def success(flow):
    return flow['properties']['definition']['actions']['Resolve_context']['actions']['Verify_baseline_boundary']['actions']['Verify_request']['actions']['Verify_source_and_case']['actions']


class SelectedEventRoutesTests(unittest.TestCase):
    def test_both_routes_preserve_retained_payload_and_shared_context(self):
        for kind, delegate in [('request', original_offer), ('response', original_response)]:
            with self.subTest(kind=kind):
                context, target, binding = fixtures(); before = copy.deepcopy((context, target, binding))
                original = delegate(context, target, binding); routed = build(kind, context, target, binding)
                work = success(routed)['Route_ownership_event']['actions']
                self.assertEqual(work['Offer_payload']['inputs'], success(original)['Offer_payload']['inputs'])
                self.assertEqual(before, (context, target, binding))
                self.assertLessEqual(audit_actions(routed['properties']['definition'])['maximumActionDepth'], 8)
                self.assertEqual(routed['properties']['state'], 'Stopped')
                hold = success(routed)['Route_unbound_consultation']['actions']['Held_unbound_consultation']['inputs']
                self.assertIsNone(hold['preparedRevision']); self.assertFalse(hold['progressionGranted'])
                self.assertEqual(hold['eventWriteCount'], 0)

    def test_response_parent_read_precedes_payload_in_its_own_scope(self):
        flow = build('response', *fixtures()); work = success(flow)['Route_ownership_event']['actions']
        self.assertEqual(work['Read_current_offer']['runAfter'], {})
        self.assertEqual(work['Offer_payload']['runAfter'], {'Read_response_history': ['Succeeded']})
        work['Read_current_offer']['runAfter'] = {'Selected_case_context': ['Succeeded']}
        with self.assertRaisesRegex(ValueError, 'sibling'):
            audit_actions(flow['properties']['definition'])

    def test_unbound_consultation_needs_no_fabricated_response_fields(self):
        for kind, mode in [('request', 'text'), ('response', 'text_5')]:
            flow = build(kind, *fixtures()); schema = flow['properties']['definition']['triggers']['manual']['inputs']['schema']
            self.assertEqual(schema['properties']['rows']['items']['required'], [mode])
            self.assertEqual(len(schema['properties']['rows']['items']['properties'][mode]['enum']), 2)

    def test_response_form_instructions_cover_both_supported_modes(self):
        flow=build('response',*fixtures())
        fields=flow['properties']['definition']['triggers']['manual']['inputs']['schema']['properties']['rows']['items']['properties']
        self.assertEqual(fields['text_1']['title'],'Response / outcome')
        self.assertIn('Accepted or Declined',fields['text_1']['description'])
        self.assertIn('Responded, Unanswered, Declined or Conditional',fields['text_1']['description'])
        self.assertIn('LC02-OP-RESP-',fields['text']['description'])
        self.assertIn('LC-CONSULT-RESP-',fields['text']['description'])
        for key in ('text','text_1','text_2','text_3','text_4'):
            self.assertIn('Required for either response action',fields[key]['description'])
            self.assertNotIn('Required when recording an ownership response',fields[key]['description'])

    def test_after_proof_drift_never_becomes_an_unconditional_success(self):
        flow = build('response', *fixtures()); work = success(flow)['Route_ownership_event']['actions']
        after = work['Verify_offer_before']['actions']['Verify_offer']['actions']
        receipt = after['Native_offer_receipt']['inputs']
        self.assertEqual(receipt['qualified'], "@equals(outputs('Event_after_checks'),true)")
        self.assertFalse(receipt['progressionGranted'])
        self.assertIn('retained-event-context-changed', receipt['effectState'])

    def test_unqualified_prepared_revision_cannot_enable_consultation(self):
        context, target, binding = fixtures(); binding['preparedRevision'] = {'qualified': True}
        with self.assertRaisesRegex(ValueError, 'consumer must be qualified'):
            build('request', context, target, binding)


if __name__ == '__main__':
    unittest.main()
