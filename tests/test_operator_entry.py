"""Local emitted-entry checks; no platform calls or native qualification."""
import copy
import hashlib
import inspect
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/lifecycle'))
from build_operator_entry import (build, next_input_expression, expression_parts,
                                  namespace_actions, action_references,
                                  with_case_work_handoff, rebind_case_work_handoff,
                                  case_work_identity_digest)
from build_operator_initiation import build as initiation
from build_selected_event_routes import audit_actions
from test_next_review_occurrence import fixture
from test_prepared_closure_check import Expressions
from test_prepared_decision_outcome import flatten


def legacy_fixture():
    reference, binding = fixture()
    return initiation(reference, binding['initiation'])


def entry_input(**changes):
    result = dict(text='LC02-OP-FUTURE-A', text_1='OCC-FUTURE-A',
                  text_2='FICTIONAL future outcome', text_3='FICTIONAL next action',
                  text_4='FICTIONAL proposed role', text_5='Create next review',
                  text_6='LC04-CLOSED-FUTURE-A')
    result.update(changes)
    return result


def check(expression, body):
    # Existing harness spelling adapter only. The emitted flow keeps the actual
    # supported native encodeUriComponent function and is never transformed.
    return Expressions(outputs={'Test_trigger': body}).evaluate(
        expression.replace('encodeUriComponent(', 'uriComponent('))


def handoff_fixture(candidate=None):
    """Small synthetic target contract; not a qualified consumer implementation."""
    candidate = candidate or build(legacy_fixture())
    producer = flatten(candidate['properties']['definition']['actions'])
    request = producer['Request']['inputs']
    create = producer['Create_case']['inputs']['parameters']
    collection = create['parameters/uri'].replace("'", "''")
    def read(uri):
        return {'type': 'OpenApiConnection', 'runAfter': {}, 'inputs': {
            'parameters': {'dataset': create['dataset'], 'parameters/method': 'GET',
                           'parameters/uri': uri}}}
    nodes = {
        'Read_selected_case': read("@concat('" + collection + "(',string(outputs('Resolved_case_item_id')),')')"),
        'Find_case_reference': read("@concat('" + collection + "?$filter=CaseUID eq ',outputs('Case_reference_value'))"),
        'Verify_case_reference_identity': {'type': 'Compose', 'inputs': True, 'runAfter': {}},
        'Validate_case_operation': {'type': 'If', 'expression': "@equals(triggerBody()?['text'],'Check context')", 'actions': {}, 'runAfter': {}},
        'Selected_case_context': {'type': 'Compose', 'runAfter': {}, 'inputs': {
            'contextOrigin': 'manual_case_reference_lookup',
            'limits': {'selectedRowProvenanceClaimed': False},
            'sourcePins': {'DocumentUID': request['DocumentUID']},
            'scope': {key: request[key] for key in
                      ('DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')}}}}
    target = {'name': '00000000-0000-4000-8000-000000000099', 'properties': {
        'environment': {'name': 'Default-00000000-0000-4000-8000-000000000098'},
        'definition': {'triggers': {'manual': {'type': 'Request', 'kind': 'Button',
            'inputs': {'schema': {'type': 'object', 'properties': {
                'text': {'type': 'string', 'title': 'Operation'},
                'text_6': {'type': 'string', 'title': 'Case reference'}},
                'required': ['text', 'text_6']}}}}, 'actions': nodes}}}
    return candidate, target


def target_digest(target):
    return hashlib.sha256(json.dumps({'flowName': target['name'],
        'environmentName': target['properties']['environment']['name'],
        'definition': target['properties']['definition']},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class OperatorHandoffTests(unittest.TestCase):
    def test_rebinding_changes_only_locator_fingerprint_and_preserves_general_receipt_routing(self):
        producer, old = handoff_fixture()
        producer = with_case_work_handoff(producer, old, target_digest(old))
        producer['properties']['state'] = 'Started'
        # A later qualified producer adaptation must survive the rebind intact.
        producer['properties']['definition']['actions']['Operator_handoff_receipt']['inputs'] = "@json('null')"
        before = copy.deepcopy(producer)
        current = copy.deepcopy(old)
        current['properties']['definition']['actions']['Additional_read_only_result'] = {
            'type': 'Compose', 'inputs': {'writeCount': 0}, 'runAfter': {}}
        pin = hashlib.sha256(json.dumps(producer['properties']['definition'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        out = rebind_case_work_handoff(producer, old, current, pin)
        self.assertEqual(producer, before)
        node = flatten(out['properties']['definition']['actions'])['Operator_case_work_handoff']['inputs']
        self.assertEqual(node['entrypointSHA256'], case_work_identity_digest(current))
        node['entrypointSHA256'] = target_digest(old)
        out['properties']['state'] = 'Started'
        self.assertEqual(out, producer)

    def test_rebind_refuses_stale_producer_wrong_previous_consumer_and_changed_identity(self):
        for mutation in ('producer', 'previous', 'identity', 'contract'):
            producer, old = handoff_fixture()
            producer = with_case_work_handoff(producer, old, target_digest(old))
            current = copy.deepcopy(old)
            if mutation == 'previous': old['properties']['definition']['actions']['changed'] = {'type': 'Compose', 'inputs': False, 'runAfter': {}}
            elif mutation == 'identity': current['name'] = '00000000-0000-4000-8000-000000000088'
            elif mutation == 'contract': flatten(producer['properties']['definition']['actions'])['Operator_case_work_handoff']['inputs']['ownershipAccepted'] = True
            pin = hashlib.sha256(json.dumps(producer['properties']['definition'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                rebind_case_work_handoff(producer, old, current, '0'*64 if mutation == 'producer' else pin)

    def test_handoff_preserves_all_existing_actions_and_adds_no_invocation(self):
        candidate, target = handoff_fixture(); before = copy.deepcopy((candidate, target))
        result = with_case_work_handoff(candidate, target, target_digest(target))
        self.assertEqual((candidate, target), before)
        actions = result['properties']['definition']['actions']
        for name, original in candidate['properties']['definition']['actions'].items():
            self.assertEqual(actions[name], original)
        self.assertEqual(actions['Operator_handoff_receipt']['runAfter'], {'NextReview_Entry': ['Succeeded']})
        added = {k: v for k, v in actions.items() if k not in candidate['properties']['definition']['actions']}
        self.assertTrue(all(a['type'] in ('Compose', 'If') for a in flatten(added).values()))
        output = flatten(added)['Operator_case_work_handoff']['inputs']
        self.assertTrue(output['locatorOnly']); self.assertFalse(output['flowInvoked'])
        self.assertFalse(output['ownershipAccepted']); self.assertFalse(output['readinessGranted'])
        self.assertFalse(output['approvalGranted']); self.assertFalse(output['ordinaryUserAccessQualified'])
        self.assertEqual(output['formValues']['text'], 'Check context')
        self.assertEqual(result['properties']['connectionReferences'], candidate['properties']['connectionReferences'])
        self.assertFalse(action_references(actions) - flatten(actions).keys())
        for key in ('name', 'environment'):
            changed = copy.deepcopy(target)
            if key == 'name': changed['name'] = '00000000-0000-4000-8000-000000000010'
            else: changed['properties']['environment']['name'] = 'Default-00000000-0000-4000-8000-000000000011'
            with self.subTest(retarget=key), self.assertRaisesRegex(ValueError, 'identity or definition changed'):
                with_case_work_handoff(candidate, changed, target_digest(target))

    def test_receipt_mismatch_or_reconciliation_prevents_handoff(self):
        candidate, target = handoff_fixture()
        graph = flatten(with_case_work_handoff(candidate, target, target_digest(target))['properties']['definition']['actions'])
        body = entry_input(); receipt = {'CaseUID': 'LC-FICTIONAL-OP-' + body['text_1'],
            'caseItemId': 12, 'requestReference': body['text'], 'occurrenceReference': body['text_1'],
            'realPolicyEffects': False, 'ownershipAccepted': False,
            'qualified': True, 'reconcileBeforeRetry': False}
        original_request = flatten(candidate['properties']['definition']['actions'])['Request']['inputs']
        receipt['retainedReceipt'] = {'request': {key: original_request[key] for key in
            ('DocumentUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')}}
        def evaluate(row, inputs=body):
            return Expressions(outputs={'Test_trigger': inputs, 'Operator_handoff_receipt': row}).evaluate(graph['Operator_handoff_ready']['expression'])
        self.assertTrue(evaluate(receipt))
        for changes in [{'CaseUID': 'LC-FICTIONAL-OP-OTHER'}, {'caseItemId': 0},
                        {'requestReference': 'OTHER'}, {'occurrenceReference': 'OTHER'},
                        {'realPolicyEffects': True}, {'ownershipAccepted': True},
                        {'qualified': False}, {'reconcileBeforeRetry': True},
                        {'retainedReceipt': {'request': {'DocumentUID': 'FICTIONAL-OTHER'}}}]:
            self.assertFalse(evaluate({**receipt, **changes}), changes)
        self.assertFalse(evaluate(None))
        initial = {**body, 'text_5': ''}
        self.assertTrue(evaluate({k: v for k, v in receipt.items() if k not in ('qualified', 'reconcileBeforeRetry')}, initial))
        self.assertNotIn('entryUrl', graph['Operator_handoff_held']['inputs'])

    def test_changed_or_wrong_target_form_source_and_collection_are_rejected(self):
        for change in ('digest', 'trigger', 'required', 'source', 'collection', 'site', 'origin', 'environment', 'flow'):
            candidate, target = handoff_fixture(); expected = target_digest(target)
            nodes = target['properties']['definition']['actions']
            if change == 'digest': expected = '0' * 64
            elif change == 'trigger': target['properties']['definition']['triggers']['manual']['kind'] = 'Http'
            elif change == 'required': target['properties']['definition']['triggers']['manual']['inputs']['schema']['required'].append('text_7')
            elif change == 'source': nodes['Selected_case_context']['inputs']['scope']['DocumentSHA256'] = '0' * 64
            elif change == 'collection': nodes['Find_case_reference']['inputs']['parameters']['parameters/uri'] = "@concat('other/items?',outputs('Case_reference_value'))"
            elif change == 'site': nodes['Read_selected_case']['inputs']['parameters']['dataset'] = 'https://other.invalid'
            elif change == 'origin': nodes['Selected_case_context']['inputs']['contextOrigin'] = 'caller_assertion'
            elif change == 'environment': target['properties']['environment']['name'] = '../other'
            elif change == 'flow': target['name'] = 'https://other.invalid'
            if change != 'digest': expected = target_digest(target)
            with self.subTest(change=change), self.assertRaises(ValueError):
                with_case_work_handoff(candidate, target, expected)

    def test_runtime_receipt_selection_and_locator_use_actual_successful_branch(self):
        from test_native_completed_review import NativeCompletedReviewTests
        owner = NativeCompletedReviewTests(); legacy = legacy_fixture()
        legacy['properties']['connectionReferences'] = owner.reference()['properties']['connectionReferences']
        candidate, target = handoff_fixture(build(legacy, owner.complete_binding()))
        graph = flatten(with_case_work_handoff(candidate, target, target_digest(target))['properties']['definition']['actions'])
        for mode, name in [('', 'Native_initiation_receipt'), ('Create next review', 'NextOccurrence_Native_initiation_receipt')]:
            row = {'CaseUID': 'LC-FICTIONAL-OP-OCC-OTHER-' + name}
            ev = Expressions(outputs={'Test_trigger': entry_input(text_5=mode), name: row})
            self.assertEqual(ev.evaluate(graph['Operator_handoff_receipt']['inputs']), row)
            ev.outputs['Operator_handoff_receipt'] = row
            self.assertEqual(ev.evaluate(graph['Operator_case_work_handoff']['inputs']['formValues']['text_6']), row['CaseUID'])
        audit = audit_actions(candidate['properties']['definition'])
        changed = audit_actions(with_case_work_handoff(candidate, target, target_digest(target))['properties']['definition'])
        self.assertEqual(changed['actionCount'] - audit['actionCount'], 4)
        self.assertLessEqual(changed['maximumActionDepth'], 8)


class OperatorEntryTests(unittest.TestCase):
    def test_initiation_writers_explicitly_disable_transport_retries(self):
        legacy = legacy_fixture()
        nodes = flatten(legacy['properties']['definition']['actions'])
        writers = {name: action for name, action in nodes.items()
                   if action.get('type') == 'OpenApiConnection'
                   and action['inputs']['parameters']['parameters/method'] != 'GET'}
        self.assertEqual(set(writers), {'Create_request', 'Create_case'})
        for action in writers.values():
            self.assertEqual(action['inputs']['retryPolicy'], {'type': 'none'})
        # Default composition retains the original initiation writers exactly.
        composed = flatten(build(legacy)['properties']['definition']['actions'])
        for name in ('Create_request', 'Create_case'):
            self.assertEqual(composed[name]['inputs']['retryPolicy'], {'type': 'none'})

    def test_integrated_candidate_route_preserves_legacy_and_holds_before_writers(self):
        from test_native_completed_review import NativeCompletedReviewTests
        binding = NativeCompletedReviewTests().runtime_binding()
        legacy = legacy_fixture()
        legacy['properties']['connectionReferences'] = NativeCompletedReviewTests().reference()['properties']['connectionReferences']
        # Use the retained synthetic source profile/site; no live tenant binding.
        result = build(legacy, binding)
        old = legacy['properties']['definition']['actions']['Validate_operator_input']['actions']
        current = result['properties']['definition']['actions']['Validate_operator_input']['actions']
        self.assertEqual(current, old)
        graph = flatten(result['properties']['definition']['actions']['NextReview_Entry']['actions'])
        self.assertEqual(graph['Completed_observer_unavailable']['type'], 'Terminate')
        for action in graph.values():
            if action['type'] == 'OpenApiConnection':
                self.assertEqual(action['inputs']['parameters']['parameters/method'], 'GET')
        audit = audit_actions(result['properties']['definition'])
        self.assertLessEqual(audit['maximumActionDepth'], 8)
        self.assertLessEqual(audit['actionCount'], 500)

    def test_existing_builder_api_and_legacy_success_actions_remain_exact(self):
        legacy = legacy_fixture(); original = copy.deepcopy(legacy)
        result = build(legacy)
        self.assertEqual(legacy, original)
        self.assertEqual(list(inspect.signature(initiation).parameters), ['reference', 'binding'])
        before = legacy['properties']['definition']; after = result['properties']['definition']
        self.assertEqual(after['actions']['Validate_operator_input']['actions'], before['actions']['Validate_operator_input']['actions'])
        self.assertEqual(after['actions']['Validate_operator_input']['else']['actions']['Route_legacy_input_refusal']['actions'],
                         before['actions']['Validate_operator_input']['else']['actions'])
        self.assertEqual(result['properties']['connectionReferences'], legacy['properties']['connectionReferences'])
        self.assertEqual(result['properties']['displayName'], legacy['properties']['displayName'])
        self.assertEqual(result['properties']['state'], 'Stopped')
        for key in before.keys() - {'actions', 'triggers'}:
            self.assertEqual(after[key], before[key])

    def test_exact_five_required_fields_and_original_trigger_settings(self):
        legacy = legacy_fixture(); result = build(legacy)
        before = legacy['properties']['definition']['triggers']['manual']
        after = result['properties']['definition']['triggers']['manual']
        old_schema, new_schema = before['inputs']['schema'], after['inputs']['schema']
        self.assertEqual(new_schema['required'], old_schema['required'])
        self.assertEqual(set(new_schema['properties']) - set(old_schema['properties']), {'text_5', 'text_6'})
        for key in old_schema['properties']:
            self.assertEqual(new_schema['properties'][key], old_schema['properties'][key])
        self.assertEqual({k: v for k, v in before.items() if k != 'inputs'},
                         {k: v for k, v in after.items() if k != 'inputs'})

    def test_old_callers_default_and_explicit_initiate_use_only_legacy_route(self):
        actions = flatten(build(legacy_fixture())['properties']['definition']['actions'])
        for operation in [None, '', 'Initiate review', '  Initiate review  ']:
            body = entry_input(); body.pop('text_5'); body.pop('text_6')
            if operation is not None: body['text_5'] = operation
            self.assertTrue(check(actions['Validate_operator_input']['expression'], body))
            self.assertFalse(check(actions['NextReview_Entry']['expression'], body))
            self.assertFalse(check(actions['NextReview_input_refusal']['expression'], body))

    def test_unknown_or_ambiguous_operation_reaches_neither_writer_route(self):
        actions = flatten(build(legacy_fixture())['properties']['definition']['actions'])
        for changes in [dict(text_5='Publish policy'), dict(text_5=''), dict(text_5='Initiate review')]:
            body = entry_input(); body.update(changes)
            self.assertFalse(check(actions['Validate_operator_input']['expression'], body))
            self.assertFalse(check(actions['NextReview_Entry']['expression'], body))
            self.assertTrue(check(actions['NextReview_input_refusal']['expression'], body))

    def test_non_case9_completed_references_are_syntactic_inputs_not_trust(self):
        actions = flatten(build(legacy_fixture())['properties']['definition']['actions'])
        for reference in ['LC04-CLOSED-FUTURE-A', 'OTHER_CLOSED.2', 'Z' * 80]:
            body = entry_input(); body['text_6'] = reference
            self.assertTrue(check(actions['NextReview_Entry']['expression'], body))
            self.assertFalse(check(actions['Validate_operator_input']['expression'], body))
        unavailable = actions['NextReview_unavailable']
        self.assertEqual(unavailable['type'], 'Terminate')
        self.assertEqual(unavailable['inputs']['runError']['code'], 'GeneralCompletedReviewUnavailable')

    def test_missing_or_invalid_completed_reference_is_refused(self):
        for reference in [None, '', ' ', 'Z' * 81, 'bad/reference', "bad'quote", 'Ā', 'a%20b', 'a!b']:
            body = entry_input(); body['text_6'] = reference
            self.assertFalse(check(next_input_expression(), body), reference)

    def test_next_request_occurrence_prefix_suffix_and_ascii_contract(self):
        expression = next_input_expression()
        for field, prefix in [('text', 'LC02-OP-'), ('text_1', 'OCC-')]:
            for suffix in ['', ' ', 'A' * 51, 'Ā', 'A B', 'A.B', '!', '~', '*', '(A)', '../A', 'A/B', "A'B", '%41']:
                body = entry_input(); body[field] = prefix + suffix
                self.assertFalse(check(expression, body), (field, suffix))
            for suffix in ['A', 'a0_-', 'Z' * 50]:
                body = entry_input(); body[field] = prefix + suffix
                self.assertTrue(check(expression, body), (field, suffix))

    def test_fictional_outcome_action_and_role_are_not_acceptance(self):
        for field, maximum in [('text_2', 1000), ('text_3', 1000), ('text_4', 200)]:
            for value in ['', 'Accepted responsibility', 'FICTIONAL' + 'X' * maximum]:
                body = entry_input(); body[field] = value
                self.assertFalse(check(next_input_expression(), body))
        result = build(legacy_fixture())
        writers = [a for a in flatten(result['properties']['definition']['actions']).values()
                   if a['type'] == 'OpenApiConnection' and a['inputs']['parameters']['parameters/method'] != 'GET']
        original_writers = [a for a in flatten(legacy_fixture()['properties']['definition']['actions']).values()
                            if a['type'] == 'OpenApiConnection' and a['inputs']['parameters']['parameters/method'] != 'GET']
        self.assertEqual(writers, original_writers)

    def test_no_unqualified_self_asserted_binding_or_action_injection_enables_next(self):
        legacy = legacy_fixture(); original = copy.deepcopy(legacy)
        for binding in [{'qualified': True}, {'closureCommit': {'kind': 'coherent'}},
                        {'completedReview': {'nativeQualified': True}},
                        {'actions': {'Post': {'type': 'Http'}}}]:
            with self.assertRaisesRegex(ValueError, 'not qualified or integrated'):
                build(legacy, binding)
        self.assertEqual(legacy, original)
        self.assertEqual(build(legacy, {}), build(legacy))

    def test_structure_references_and_recomposition_refusal(self):
        result = build(legacy_fixture()); definition = result['properties']['definition']
        audit = audit_actions(definition)
        self.assertLessEqual(audit['maximumActionDepth'], 8)
        self.assertLess(audit['actionCount'], 100)
        self.assertTrue(action_references(definition['actions']) <= flatten(definition['actions']).keys())
        self.assertLess(len(next_input_expression()), 8192)
        self.assertEqual(definition['actions']['NextReview_Entry']['runAfter'], {'Validate_operator_input': ['Succeeded']})
        with self.assertRaisesRegex(ValueError, 'uncomposed'):
            build(result)

    def test_namespace_rewrites_real_wdl_and_interpolation_only(self):
        mapping = {'Request': 'NextReview_Request'}
        cases = [
            ("@outputs('Request')", "@outputs('NextReview_Request')", {'Request'}),
            ("@body( 'Request' )", "@body( 'NextReview_Request' )", {'Request'}),
            ("@actions('Request')", "@actions('NextReview_Request')", {'Request'}),
            ("@result('Request')", "@result('NextReview_Request')", {'Request'}),
            ("Status @{outputs('Request')?['CaseUID']}", "Status @{outputs('NextReview_Request')?['CaseUID']}", {'Request'}),
            ("@{body('Request')}", "@{body('NextReview_Request')}", {'Request'}),
            ("@equals(outputs('Request'),'literal body(''NotAnAction'')')",
             "@equals(outputs('NextReview_Request'),'literal body(''NotAnAction'')')", {'Request'}),
        ]
        for value, expected, refs in cases:
            self.assertEqual(expression_parts(value, mapping), (expected, refs))

    def test_plain_unknown_escaped_and_json_literals_are_not_references(self):
        for value in ["FICTIONAL preserve literal body('Request') in this human note",
                      "FICTIONAL body('NotAnAction') outputs('Request') actions('Request')",
                      "@@outputs('Request')", "literal @@{outputs('Request')}",
                      "@json('{\"note\":\"body(''NotAnAction'')\",\"close\":\"}\"}')"]:
            self.assertEqual(expression_parts(value, {'Request': 'Renamed'}), (value, set()))

    def test_nested_retained_proof_is_never_lexed_or_modified_by_ancestor(self):
        literal = {'human': "FICTIONAL body('NotAnAction')", 'startsAt': "@body('Request')",
                   'unparsed': "@not even valid 'quoted", 'nullField': None}
        group = {'Request': {'type': 'Compose', 'inputs': 'request', 'runAfter': {}},
                 'Gate': {'type': 'If', 'expression': "@equals(outputs('Request'),'request')",
                          'actions': {'Next_expected_commit': {'type': 'Compose', 'inputs': literal, 'runAfter': {}}},
                          'else': {'actions': {}}, 'runAfter': {'Request': ['Succeeded']}}}
        before = copy.deepcopy(group); result = namespace_actions(group)
        self.assertEqual(group, before)
        self.assertEqual(flatten(result)['NextReview_Next_expected_commit']['inputs'], literal)
        self.assertEqual(result['NextReview_Gate']['runAfter'], {'NextReview_Request': ['Succeeded']})
        self.assertEqual(action_references(result), {'NextReview_Request'})

    def test_reference_audit_distinguishes_unknown_literal_from_actual_unknown(self):
        legacy = legacy_fixture()
        own = legacy['properties']['definition']['actions']['Validate_operator_input']['actions']
        own['Human_note'] = {'type': 'Compose', 'inputs': "FICTIONAL body('NotAnAction')", 'runAfter': {}}
        build(legacy)
        for actual in ["@body('NotAnAction')", "Status @{outputs('NotAnAction')}"]:
            own['Human_note']['inputs'] = actual
            with self.assertRaisesRegex(ValueError, 'Unresolved WDL action references'):
                build(legacy)

    def test_namespace_handles_switch_cases_default_and_literal_selectors(self):
        group = {'Request': {'type': 'Compose', 'inputs': 'x', 'runAfter': {}},
                 'Switch': {'type': 'Switch', 'expression': "@outputs('Request')",
                            'cases': {'one': {'case': "literal body('NotAnAction')", 'actions': {
                                'Value': {'type': 'Compose', 'inputs': "@outputs('Request')", 'runAfter': {}}}}},
                            'default': {'actions': {'Other': {'type': 'Compose', 'inputs': 'literal', 'runAfter': {}}}},
                            'runAfter': {'Request': ['Succeeded']}}}
        renamed = namespace_actions(group)
        self.assertEqual(renamed['NextReview_Switch']['cases']['one']['case'], "literal body('NotAnAction')")
        self.assertEqual(action_references(renamed), {'NextReview_Request'})
        audit_actions({'actions': renamed})

    def test_malformed_wdl_and_ambiguous_action_names_fail_without_mutating(self):
        for value in ["@equals('unterminated", 'Status @{body(\'Request\')']:
            with self.assertRaises(ValueError): expression_parts(value)
        duplicate = {'Request': {'type': 'If', 'expression': '@true', 'actions': {
            'Request': {'type': 'Compose', 'inputs': 'data', 'runAfter': {}}}}}
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            namespace_actions(duplicate)

    def test_resolver_can_explicitly_mark_literal_control_data_without_text_rewrite(self):
        raw = {'note': "@not valid 'WDL", 'human': "body('NotAnAction')",
               'actions': {'Request': 'human data'}, 'runAfter': {'Request': None}}
        graph = {'Trusted_completed_profile': {'type': 'Compose', 'inputs': raw, 'runAfter': {}}}
        result = namespace_actions(graph, literal_inputs={'Trusted_completed_profile'})
        self.assertEqual(result['NextReview_Trusted_completed_profile']['inputs'], raw)
        self.assertEqual(action_references(result, literal_inputs={'NextReview_Trusted_completed_profile'}), set())

    def test_unknown_actual_reference_stays_unresolved_after_namespacing(self):
        graph = {'Read': {'type': 'Compose', 'inputs': "actual @{outputs('Missing')}", 'runAfter': {}}}
        result = namespace_actions(graph)
        self.assertEqual(action_references(result), {'Missing'})
        self.assertNotIn('Missing', result)

    def test_unqualified_reference_shape_or_concurrency_never_changes_input(self):
        for change in ['concurrency', 'required-fields', 'trigger-kind']:
            legacy = legacy_fixture()
            trigger = legacy['properties']['definition']['triggers']['manual']
            if change == 'concurrency': trigger['runtimeConfiguration']['concurrency']['runs'] = 2
            elif change == 'required-fields': trigger['inputs']['schema']['required'].pop()
            else: legacy['properties']['definition']['triggers']['recurrence'] = {'type': 'Recurrence'}
            before = copy.deepcopy(legacy)
            with self.subTest(change=change), self.assertRaises(ValueError): build(legacy)
            self.assertEqual(legacy, before)


if __name__ == '__main__': unittest.main()
