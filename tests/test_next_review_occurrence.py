"""Meaningful lineage/date/replay/recovery checks on the emitted native graph."""
import base64
import copy
import hashlib
import json
import re
import unittest
from build_next_review_occurrence import build
from build_selected_event_routes import audit_actions
from test_prepared_closure_check import Expressions
from test_prepared_decision_outcome import flatten


def fixture():
    uid = lambda n: '00000000-0000-4000-8000-' + str(n).zfill(12)
    site = 'https://example.invalid/site'
    casebase = "_api/web/lists(guid'" + uid(1) + "')/items"
    reference = {'properties': {'connectionReferences': {'shared_sharepointonline': {'connectionName': 'fictional-connection'}},
        'definition': {'triggers': {'manual': {'type': 'Request', 'inputs': {}}},
            'actions': {'Qualified_case': {'type': 'OpenApiConnection', 'inputs': {'parameters': {
                'dataset': site, 'parameters/uri': casebase + '(9)'}}}}}}}
    content = 'FICTIONAL original authoritative source'
    source = {'DocumentUID': 'FICTIONAL-ORIGINAL', 'UniqueId': uid(2), 'ETag': '"original1"',
        'DocumentReference': site + '/original.txt', 'ReviewedVersionRef': 'original-v1',
        'content': content, 'sha256': hashlib.sha256(content.encode()).hexdigest()}
    scope = {'CaseUID': 'LC-FICTIONAL-OP-COMPLETED', 'DocumentReference': site + '/prepared.docx',
        'ReviewedVersionRef': 'prepared-v2', 'DocumentSHA256': 'a' * 64}
    parent = {'Id': 9, 'CaseUID': scope['CaseUID'], 'caseStatus': 'Review closed — FICTIONAL',
        'GUID': uid(9), 'nextAction': 'Preserve completed review', 'odata.id': None}
    date_record = {'FictionalTest': True, 'notOperational': True, 'policyAuthorityGranted': False,
        'scope': scope, 'reviewDate': '2099-01-01', 'ruleReference': 'fictional://test-rule'}
    def file(n, value):
        raw = json.dumps(value, separators=(',', ':')).encode()
        return {'metadata': {'UniqueId': uid(n), 'ETag': '"1"', 'UIVersionLabel': '1.0', 'Length': len(raw)},
            'record': value, 'SHA256': hashlib.sha256(raw).hexdigest(), 'contentBase64': base64.b64encode(raw).decode()}
    date = file(10, date_record)
    issued = {'UniqueId': uid(11), 'ETag': '"2"'}
    observation = {'closureEvidenceConsistent': True, 'nextReviewDateProvenanceConsistent': True, 'nextOccurrencePrerequisitesConsistent': True, 'preparedScope': scope, 'issuedFile': issued, 'nextReviewDate': '2099-01-01',
        'nextReviewRuleReference': date_record['ruleReference'], 'nextReviewEvidenceFileUID': uid(10)}
    commit_record = {'kind': 'fictional-prepared-closure-commit-v1', 'realPolicyEffects': False,
        'contract': {'kind': 'fictional-prepared-closure-contract-v1', 'CaseUID': parent['CaseUID'], 'observation': observation, 'patch': {'caseStatus': 'Review closed — FICTIONAL'}, 'initialCaseETag': '"3"', 'initialCaseStatus': 'Ownership accepted — FICTIONAL'},
        'afterProof': {'afterCase': parent, 'afterCaseETag': '"4"'}}
    contract = commit_record['contract']
    commit_record['afterProof'].update(kind='fictional-prepared-closure-after-v1', contract=contract)
    commit_record['beforeProof'] = {'kind': 'fictional-prepared-closure-before-v1', 'contract': contract, 'beforeCaseETag': '"3"', 'beforeCase': {**parent, 'caseStatus': contract['initialCaseStatus']}}
    binding = {'qualificationOnly': True, 'targetDateFieldType': 'Text', 'canonicalInputs': {'text': 'LC02-OP-NEXT-TEST', 'text_1': 'OCC-NEXT-TEST',
        'text_2': 'FICTIONAL next review', 'text_3': 'FICTIONAL seek proposed ownership',
        'text_4': 'FICTIONAL Case9 next-occurrence test role'},
        'completedCaseUri': casebase + '(9)', 'completedCaseETag': '"4"',
        'completedReview': {'case': parent, 'preparedScope': scope, 'issuedFile': issued,
            'originalSource': {k: source[k] for k in ['DocumentUID', 'DocumentReference', 'ReviewedVersionRef', 'sha256']}},
        'date': date, 'closureCommit': file(12, commit_record),
        'initiation': {'qualificationOnly': True, 'source': source, 'siteUrl': site,
            'caseListUri': casebase, 'evidenceFolder': '/site/PPG Review Evidence/Templates'}}
    return reference, binding


class NextReviewTests(unittest.TestCase):
    def graph(self): return flatten(build(*fixture())['properties']['definition']['actions'])

    def test_single_case_uri_escapes_native_guid_literal(self):
        reference, binding = fixture()
        graph = flatten(build(reference, binding)['properties']['definition']['actions'])
        base = binding['initiation']['caseListUri'].replace("'", "''")
        expected = "@concat('" + base + "(',string(first(body('Read_case')?['value'])?['Id']),')')"
        for name in ['Next_case_selected', 'Next_case_receipt_item_before', 'Next_case_receipt_item_after']:
            expression = graph[name]['inputs']['parameters']['parameters/uri']
            self.assertEqual(expression, expected)
            # Decode WDL string literals and verify the actual native URI prefix.
            prefix = re.match(r"@concat\('((?:[^']|'')*)',string", expression)
            self.assertIsNotNone(prefix)
            self.assertEqual(prefix.group(1).replace("''", "'"), binding['initiation']['caseListUri'] + '(')

    def receipt_context(self):
        a = self.graph(); _, binding = fixture()
        row = {'Id': 10, 'ID': 10, 'CaseUID': 'LC-FICTIONAL-OP-OCC-NEXT-TEST',
               'GUID': '00000000-0000-4000-8000-000000000010',
               'Created': '2026-10-18T00:00:00Z', 'Modified': '2026-10-18T00:00:00Z',
               'accountableRole': 'UNACCEPTED — proposed fictional role: FICTIONAL test',
               'targetDate': '2099-01-01', 'caseStatus': 'Initiated — FICTIONAL'}
        collection_row = {**row, 'ComplianceAssetId': None, 'OData__ColorTag': None,
                          'ServerRedirectedEmbedUri': None}
        bodies = {'Read_case': {'value': [copy.deepcopy(collection_row)]},
                  'Next_case_selected': copy.deepcopy(row),
                  'Next_find_receipt': {'value': []}, 'Find_case': {'value': []},
                  'Find_request': {'value': []},
                  'Recheck_source': {'ETag': binding['initiation']['source']['ETag']},
                  'Next_parent_final': binding['completedReview']['case']}
        outputs = {'Request': {'CaseUID': row['CaseUID']},
                   'Next_expected_case': binding['completedReview']['case'],
                   'Next_parent_final': {'headers': {'ETag': binding['completedCaseETag']}}}
        for key in ['Next_case_selected', 'Next_case_receipt_item_before', 'Next_case_receipt_item_after']:
            bodies[key] = copy.deepcopy(row)
            outputs[key] = {'statusCode': 200, 'headers': {'ETag': '"case,1"'}}
        for key in ['Next_case_receipt_before', 'Next_case_receipt_after']:
            bodies[key] = {'value': [copy.deepcopy(collection_row)]}
            outputs[key] = {'statusCode': 200}
        for name, file in [('date', binding['date']), ('commit', binding['closureCommit'])]:
            for suffix in ['before', 'final']:
                bodies['Next_' + name + '_' + suffix] = copy.deepcopy(file['metadata'])
        ev = Expressions(bodies, outputs)
        self.refresh_snapshot_checks(a, ev)
        outputs['Next_receipt_payload'] = {k: ev.evaluate(v) for k, v in a['Next_receipt_payload']['inputs'].items()}
        outputs['Next_saved_receipt'] = copy.deepcopy(outputs['Next_receipt_payload'])
        return a, ev

    def refresh_snapshot_checks(self, a, ev):
        for side in ['before', 'after']:
            ev.outputs['Next_case_' + side + '_stable'] = ev.evaluate(a['Next_case_' + side + '_stable']['inputs'])

    def test_original_baseline_and_completed_revision_remain_distinct(self):
        reference, binding = fixture(); before = copy.deepcopy((reference, binding))
        result = build(reference, binding); self.assertEqual((reference, binding), before)
        a = flatten(result['properties']['definition']['actions']); request = a['Request']['inputs']; payload = a['Case_payload']['inputs']
        source = binding['initiation']['source']
        self.assertEqual(request['DocumentReference'], source['DocumentReference'])
        self.assertEqual(request['DocumentSHA256'], source['sha256'])
        self.assertEqual(request['completedReview']['preparedScope'], binding['completedReview']['preparedScope'])
        self.assertNotEqual(request['DocumentReference'], request['completedReview']['preparedScope']['DocumentReference'])
        self.assertEqual(payload['evidenceDraftLink'], source['DocumentReference'])
        self.assertIn('UNACCEPTED', payload['accountableRole'])
        self.assertEqual(payload['targetDate'], "@outputs('Next_date_record')?['reviewDate']")
        self.assertEqual(result['properties']['state'], 'Stopped')

    def test_missing_or_conflicting_provenance_refuses_build(self):
        for mutate in [lambda b: b['completedReview']['originalSource'].update(DocumentReference='https://example.invalid/issued.docx'),
                       lambda b: b.update(completedCaseETag='*'),
                       lambda b: b['canonicalInputs'].update(text_4='Inherited accepted owner'),
                       lambda b: b['closureCommit'].update(SHA256='0' * 64),
                       lambda b: b['date']['metadata'].update(ETag='*')]:
            r, b = fixture(); mutate(b)
            with self.assertRaises(ValueError): build(r, b)

    def date_binding(self, value):
        reference, binding = fixture()
        binding['date']['record']['reviewDate'] = value
        binding['closureCommit']['record']['contract']['observation']['nextReviewDate'] = value
        # Retain matching raw provenance so the date check, rather than a stale
        # fixture hash, determines whether this candidate can be built.
        for key in ('date', 'closureCommit'):
            file = binding[key]
            raw = json.dumps(file['record'], separators=(',', ':')).encode()
            file.update(contentBase64=base64.b64encode(raw).decode(), SHA256=hashlib.sha256(raw).hexdigest())
            file['metadata']['Length'] = len(raw)
        return reference, binding

    def test_calendar_date_contract_rejects_alternative_encodings_and_invalid_days(self):
        for value in ('20990101', '2099-W01-4', '01/01/2099', '2099-1-1',
                      '2099-01-01T00:00:00Z', '2098-12-31T14:00:00-10:00',
                      '2100-02-29', '2099-04-31', '0000-01-01', '', None, 20990101):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build(*self.date_binding(value))

    def test_canonical_calendar_dates_preserve_exact_day_and_provenance(self):
        for value in ('2099-01-01', '2000-02-29', '2100-02-28', '2099-12-31'):
            with self.subTest(value=value):
                result = build(*self.date_binding(value))
                actions = flatten(result['properties']['definition']['actions'])
                self.assertEqual(actions['Next_expected_date']['inputs']['reviewDate'], value)
                self.assertEqual(actions['Case_payload']['inputs']['targetDate'], "@outputs('Next_date_record')?['reviewDate']")

    def test_origin_gate_requires_actual_unique_case_identity_and_matching_parent(self):
        a = self.graph(); _, b = fixture()
        bodies = {'Next_completed_case': b['completedReview']['case'],
            'Next_case_identity_field': {'InternalName': 'CaseUID', 'EnforceUniqueValues': True},
            'Next_target_date_field': {'InternalName': 'targetDate', 'TypeAsString': 'Text', 'MaxLength': 255}}
        outputs = {'Next_expected_case': b['completedReview']['case'], 'Next_expected_date': b['date']['record'],
            'Next_expected_commit': b['closureCommit']['record'], 'Next_date_record': b['date']['record'],
            'Next_commit_record': b['closureCommit']['record'], 'Next_completed_case': {'headers': {'ETag': b['completedCaseETag']}}}
        for name, file in [('date', b['date']), ('commit', b['closureCommit'])]:
            for suffix in ['before', 'after']: bodies['Next_' + name + '_' + suffix] = {**file['metadata'], 'Length': str(file['metadata']['Length'])}
        expression = a['Next_validate_origin']['expression']
        self.assertTrue(Expressions(bodies, outputs).evaluate(expression))
        wrong = copy.deepcopy(bodies); wrong['Next_case_identity_field']['EnforceUniqueValues'] = False
        self.assertFalse(Expressions(wrong, outputs).evaluate(expression))
        date_column_changed = copy.deepcopy(bodies); date_column_changed['Next_target_date_field']['TypeAsString'] = 'DateTime'
        self.assertFalse(Expressions(date_column_changed, outputs).evaluate(expression))
        stale = copy.deepcopy(outputs); stale['Next_completed_case']['headers']['ETag'] = '"5"'
        self.assertFalse(Expressions(bodies, stale).evaluate(expression))
        changed = copy.deepcopy(bodies); changed['Next_date_after'] = {**changed['Next_date_after'], 'ETag': '"2"'}
        self.assertFalse(Expressions(changed, outputs).evaluate(expression))

    def test_existing_intent_and_missing_case_cannot_repeat_create(self):
        a = self.graph(); expr = a['Next_require_new_intent']['expression']
        self.assertTrue(Expressions({'Next_find_intent': {'value': []}}).evaluate(expr))
        self.assertFalse(Expressions({'Next_find_intent': {'value': [{}]}}).evaluate(expr))
        self.assertFalse(Expressions({'Next_find_intent': {'value': [], 'odata.nextLink': 'next'}}).evaluate(expr))
        self.assertEqual(a['Next_read_intent']['runAfter'], {'Next_create_intent': ['Succeeded']})
        self.assertEqual(a['Read_case']['runAfter'], {'Next_reconcile_intent': ['Succeeded']})
        check = a['Next_verify_intent']['expression']
        self.assertFalse(Expressions(outputs={'Next_stored_intent': None, 'Next_intent_payload': {'request': 'expected'}}).evaluate(check))
        self.assertIn('Next_reconcile_intent', a['Verify_case']['expression'])

    def test_annotation_rich_completed_parent_uses_exact_closure_get_contract(self):
        reference, binding = fixture()
        parent = copy.deepcopy(binding['completedReview']['case'])
        parent.update({'odata.metadata': 'https://example.invalid/site/_api/$metadata#SP.Data.Cases/@Element',
                       'odata.type': 'SP.Data.CasesListItem',
                       'odata.id': 'https://example.invalid/site/_api/items(9)',
                       'odata.etag': binding['completedCaseETag'],
                       'odata.editLink': 'Web/Lists/Items(9)', 'targetDate': None,
                       'unresolvedContent': None})
        binding['completedReview']['case'] = parent
        commit = binding['closureCommit']
        commit['record']['afterProof']['afterCase'] = {**parent, 'odata.id': None}
        raw = json.dumps(commit['record'], separators=(',', ':')).encode()
        commit.update(contentBase64=base64.b64encode(raw).decode(), SHA256=hashlib.sha256(raw).hexdigest())
        commit['metadata']['Length'] = len(raw)
        original = copy.deepcopy((reference, binding))
        a = flatten(build(reference, binding)['properties']['definition']['actions'])
        self.assertEqual((reference, binding), original)
        expected = {**parent, 'odata.id': None}
        self.assertEqual(a['Next_expected_case']['inputs'], expected)
        for name in ['Next_completed_case', 'Next_parent_final']:
            params = a[name]['inputs']['parameters']
            self.assertEqual(params['parameters/uri'], binding['completedCaseUri'])
            # Exact literal headers observed on both retained Cycle_case reads.
            self.assertEqual(params['parameters/headers'], {'Accept': 'application/json;odata=minimalmetadata'})
        for name, action in a.items():
            if action['type'] != 'OpenApiConnection' or name in ['Next_completed_case', 'Next_parent_final']:
                continue
            self.assertEqual(action['inputs']['parameters']['parameters/headers'],
                             {'Accept': 'application/json;odata=nometadata',
                              'Content-Type': 'application/json;odata=nometadata'}, name)
        bodies = {'Next_completed_case': parent,
                  'Next_case_identity_field': {'InternalName': 'CaseUID', 'EnforceUniqueValues': True},
                  'Next_target_date_field': {'InternalName': 'targetDate', 'TypeAsString': 'Text', 'MaxLength': 255}}
        outputs = {'Next_expected_case': expected, 'Next_expected_date': binding['date']['record'],
                   'Next_expected_commit': commit['record'], 'Next_date_record': binding['date']['record'],
                   'Next_commit_record': commit['record'],
                   'Next_completed_case': {'headers': {'ETag': binding['completedCaseETag']}}}
        for name, file in [('date', binding['date']), ('commit', commit)]:
            for suffix in ['before', 'after']:
                bodies['Next_' + name + '_' + suffix] = copy.deepcopy(file['metadata'])
        origin = Expressions(bodies, outputs)
        _, final = self.receipt_context()
        final.bodies['Next_parent_final'] = parent
        final.outputs['Next_expected_case'] = expected
        for expression, ev, body_name in [(a['Next_validate_origin']['expression'], origin, 'Next_completed_case'),
                                           (a['Final_source_guard']['expression'], final, 'Next_parent_final')]:
            self.assertTrue(ev.evaluate(expression))
            for missing in ['odata.metadata', 'odata.type', 'odata.etag', 'odata.editLink', 'targetDate', 'unresolvedContent']:
                ev.bodies[body_name] = {k: v for k, v in parent.items() if k != missing}
                self.assertFalse(ev.evaluate(expression), (body_name, missing))
            ev.bodies[body_name] = copy.deepcopy(parent)
            ev.bodies[body_name]['odata.id'] = 'different response-transport annotation'
            self.assertTrue(ev.evaluate(expression))

    def test_saved_receipt_replay_preserves_exact_row_and_reports_unknown_on_drift(self):
        a, ev = self.receipt_context(); receipt = a['Native_initiation_receipt']['inputs']
        ev.bodies['Find_case'] = {'value': [{}]}; ev.bodies['Find_request'] = {'value': [{}]}
        self.assertTrue(ev.evaluate(receipt['qualified'])); self.assertEqual(ev.evaluate(receipt['caseCreatedCount']), 0)
        ev.outputs['Next_saved_receipt']['case']['GUID'] = 'replacement'
        self.assertFalse(ev.evaluate(receipt['qualified'])); self.assertIsNone(ev.evaluate(receipt['caseCreatedCount']))
        self.assertTrue(ev.evaluate(receipt['reconcileBeforeRetry']))

    def test_first_and_existing_case_reconciliation_have_distinct_create_counts(self):
        for cases, requests, receipts, expected_count, recovery in [(0, 0, 0, 1, False), (1, 1, 0, 0, True), (1, 1, 1, 0, False)]:
            a, ev = self.receipt_context(); receipt = a['Native_initiation_receipt']['inputs']
            ev.bodies.update({'Find_case': {'value': [{}] * cases}, 'Find_request': {'value': [{}] * requests}, 'Next_find_receipt': {'value': [{}] * receipts}})
            self.assertTrue(ev.evaluate(a['Final_source_guard']['expression']))
            self.assertTrue(ev.evaluate(receipt['qualified']))
            self.assertEqual(ev.evaluate(receipt['caseCreatedCount']), expected_count)
            self.assertEqual(ev.evaluate(receipt['recoveredExistingCase']), recovery)
            if cases:
                self.assertFalse(ev.evaluate(a['Ensure_case']['expression']))
        self.assertIn("equals(string(outputs('Retained_request')?['request']),string(outputs('Request')))", a['Verify_request']['expression'])

    def test_concurrent_role_edit_and_token_drift_hold_before_receipt_creation(self):
        for change in ['role', 'role-same-token', 'token', 'GUID', 'Created', 'Id']:
            a, ev = self.receipt_context()
            row = ev.bodies['Next_case_receipt_before']['value'][0]
            if change.startswith('role'): row['accountableRole'] = 'HUMAN EDIT — different proposed role'
            elif change != 'token': row[change] = 'replacement' if change != 'Id' else 20
            if change.startswith('role'):
                ev.bodies['Next_case_receipt_item_before']['accountableRole'] = row['accountableRole']
            elif change != 'token':
                ev.bodies['Next_case_receipt_item_before'][change] = row[change]
            if change in ['role', 'token']:
                ev.outputs['Next_case_receipt_item_before']['headers']['ETag'] = '"case,2"'
            self.refresh_snapshot_checks(a, ev)
            with self.subTest(change=change):
                self.assertFalse(ev.outputs['Next_case_before_stable'])
                self.assertFalse(ev.evaluate(a['Final_source_guard']['expression']))
                self.assertFalse(ev.evaluate(a['Native_initiation_receipt']['inputs']['qualified']))
        self.assertEqual(a['Final_source_guard']['runAfter'], {'Next_case_before_stable': ['Succeeded']})
        self.assertEqual(a['Next_case_selected']['runAfter'], {})
        self.assertEqual(a['Recheck_source']['runAfter'], {'Next_case_selected': ['Succeeded']})

    def test_edit_after_receipt_save_cannot_qualify_or_claim_reconciliation(self):
        for change in ['role', 'role-same-token', 'token', 'GUID', 'Created', 'Id']:
            a, ev = self.receipt_context()
            ev.bodies['Find_case'] = {'value': [{}]}; ev.bodies['Find_request'] = {'value': [{}]}
            row = ev.bodies['Next_case_receipt_after']['value'][0]
            if change.startswith('role'): row['accountableRole'] = 'HUMAN EDIT — different proposed role'
            elif change != 'token': row[change] = 'replacement' if change != 'Id' else 20
            if change.startswith('role'):
                ev.bodies['Next_case_receipt_item_after']['accountableRole'] = row['accountableRole']
            elif change != 'token':
                ev.bodies['Next_case_receipt_item_after'][change] = row[change]
            if change in ['role', 'token']:
                ev.outputs['Next_case_receipt_item_after']['headers']['ETag'] = '"case,2"'
            self.refresh_snapshot_checks(a, ev)
            receipt = a['Native_initiation_receipt']['inputs']
            with self.subTest(change=change):
                self.assertFalse(ev.outputs['Next_case_after_stable'])
                self.assertFalse(ev.evaluate(receipt['qualified']))
                self.assertIsNone(ev.evaluate(receipt['caseCreatedCount']))
                self.assertIsNone(ev.evaluate(receipt['requestCreatedCount']))
                self.assertFalse(ev.evaluate(receipt['recoveredExistingCase']))
                self.assertTrue(ev.evaluate(receipt['reconcileBeforeRetry']))
        self.assertEqual(a['Next_case_receipt_after']['runAfter'], {'Next_saved_receipt': ['Succeeded']})
        self.assertEqual(a['Native_initiation_receipt']['runAfter'], {'Next_case_after_stable': ['Succeeded']})

    def test_saved_receipt_retains_actual_header_token_across_replay(self):
        a, ev = self.receipt_context()
        self.assertEqual(ev.outputs['Next_saved_receipt']['caseETag'], '"case,1"')
        # Same visible row, changed native token: the retained receipt must not
        # be silently rewritten to claim that the later revision was created.
        for name in ['Next_case_selected', 'Next_case_receipt_item_before', 'Next_case_receipt_item_after']:
            ev.outputs[name]['headers']['ETag'] = '"case,2"'
        self.refresh_snapshot_checks(a, ev)
        ev.outputs['Next_receipt_payload']['caseETag'] = '"case,2"'
        self.assertTrue(ev.outputs['Next_case_before_stable'])
        self.assertTrue(ev.outputs['Next_case_after_stable'])
        self.assertFalse(ev.evaluate(a['Native_initiation_receipt']['inputs']['qualified']))
        self.assertEqual(a['Next_ensure_receipt']['expression'], "@and(equals(length(body('Next_find_receipt')?['value']),0))")
        self.assertEqual(a['Next_ensure_receipt']['else']['actions'], {})

    def test_measured_null_shape_qualifies_without_altering_raw_rows_or_receipt(self):
        a, ev = self.receipt_context(); original = copy.deepcopy((ev.bodies, ev.outputs))
        keys = {'ComplianceAssetId', 'OData__ColorTag', 'ServerRedirectedEmbedUri'}
        collection = ev.bodies['Read_case']['value'][0]
        single = ev.bodies['Next_case_selected']
        self.assertEqual(collection.keys() - single.keys(), keys)
        self.assertTrue(all(collection[k] is None for k in keys))
        self.refresh_snapshot_checks(a, ev)
        self.assertTrue(ev.outputs['Next_case_before_stable'])
        self.assertTrue(ev.outputs['Next_case_after_stable'])
        self.assertTrue(ev.evaluate(a['Native_initiation_receipt']['inputs']['qualified']))
        self.assertEqual(ev.outputs['Next_receipt_payload']['case'], {**collection, 'odata.id': None})
        self.assertEqual((ev.bodies, ev.outputs), original)
        # Explicit null is also permitted on the item surface, provided every
        # single-item observation agrees exactly with that selected shape.
        for name in ['Next_case_selected', 'Next_case_receipt_item_before', 'Next_case_receipt_item_after']:
            ev.bodies[name].update(dict.fromkeys(keys))
        self.refresh_snapshot_checks(a, ev)
        self.assertTrue(ev.outputs['Next_case_before_stable'])
        self.assertTrue(ev.outputs['Next_case_after_stable'])
        self.assertTrue(ev.evaluate(a['Native_initiation_receipt']['inputs']['qualified']))

    def test_null_exception_does_not_hide_nonnull_values_or_unknown_missing_null_field(self):
        keys = ['ComplianceAssetId', 'OData__ColorTag', 'ServerRedirectedEmbedUri']
        for key in keys:
            for single_value in ['nonnull', 'different-nonnull']:
                a, ev = self.receipt_context()
                ev.bodies['Next_case_selected'][key] = single_value
                for side in ['before', 'after']:
                    ev.bodies['Next_case_receipt_item_' + side][key] = single_value
                if single_value == 'different-nonnull':
                    for name in ['Read_case', 'Next_case_receipt_before', 'Next_case_receipt_after']:
                        ev.bodies[name]['value'][0][key] = 'collection-nonnull'
                self.refresh_snapshot_checks(a, ev)
                with self.subTest(key=key, single_value=single_value):
                    self.assertFalse(ev.outputs['Next_case_before_stable'])
                    self.assertFalse(ev.outputs['Next_case_after_stable'])
                    self.assertFalse(ev.evaluate(a['Native_initiation_receipt']['inputs']['qualified']))
        # An additional null omitted only by the item endpoint is NOT one of
        # the measured three fields and must not be silently completed/dropped.
        a, ev = self.receipt_context()
        for name in ['Read_case', 'Next_case_receipt_before', 'Next_case_receipt_after']:
            ev.bodies[name]['value'][0]['unresolvedHumanField'] = None
        self.refresh_snapshot_checks(a, ev)
        self.assertFalse(ev.outputs['Next_case_before_stable'])
        self.assertFalse(ev.outputs['Next_case_after_stable'])

    def test_same_surface_added_or_deleted_fields_remain_exact(self):
        for side in ['before', 'after']:
            for change in ['known-single-null-added', 'known-collection-null-deleted',
                           'unknown-null-added', 'human-field-deleted']:
                a, ev = self.receipt_context()
                collection = ev.bodies['Next_case_receipt_' + side]['value'][0]
                single = ev.bodies['Next_case_receipt_item_' + side]
                if change == 'known-single-null-added': single['ComplianceAssetId'] = None
                elif change == 'known-collection-null-deleted': del collection['ComplianceAssetId']
                elif change == 'unknown-null-added':
                    collection['newHumanField'] = single['newHumanField'] = None
                else: del collection['accountableRole']; del single['accountableRole']
                self.refresh_snapshot_checks(a, ev)
                with self.subTest(side=side, change=change):
                    self.assertFalse(ev.outputs['Next_case_' + side + '_stable'])
                    self.assertFalse(ev.evaluate(a['Native_initiation_receipt']['inputs']['qualified']))
        # A missing human null also remains different from an explicit null.
        a, ev = self.receipt_context()
        ev.bodies['Read_case']['value'][0]['unresolvedHumanField'] = None
        ev.bodies['Next_case_selected']['unresolvedHumanField'] = None
        self.refresh_snapshot_checks(a, ev)
        self.assertFalse(ev.outputs['Next_case_before_stable'])
        self.assertFalse(ev.outputs['Next_case_after_stable'])

    def test_changed_receipt_still_holds_with_raw_collection_nulls_retained(self):
        for change in ['system-nonnull', 'known-null-deleted', 'unknown-null', 'human-field-deleted', 'token']:
            a, ev = self.receipt_context(); saved = ev.outputs['Next_saved_receipt']
            if change == 'system-nonnull': saved['case']['ComplianceAssetId'] = 'human-edit'
            elif change == 'known-null-deleted': del saved['case']['ComplianceAssetId']
            elif change == 'unknown-null': saved['case']['unresolvedHumanField'] = None
            elif change == 'human-field-deleted': del saved['case']['accountableRole']
            else: saved['caseETag'] = '"case,2"'
            receipt = a['Native_initiation_receipt']['inputs']
            with self.subTest(change=change):
                self.assertFalse(ev.evaluate(receipt['qualified']))
                self.assertIsNone(ev.evaluate(receipt['caseCreatedCount']))
                self.assertIsNone(ev.evaluate(receipt['requestCreatedCount']))
                self.assertFalse(ev.evaluate(receipt['recoveredExistingCase']))
                self.assertTrue(ev.evaluate(receipt['reconcileBeforeRetry']))

    def test_disappearance_duplicates_pagination_and_failed_gets_hold_at_both_checks(self):
        for side in ['before', 'after']:
            collection = 'Next_case_receipt_' + side
            item = 'Next_case_receipt_item_' + side
            mutations = [lambda e: e.bodies[collection].update(value=[]),
                         lambda e: e.bodies[collection]['value'].append(copy.deepcopy(e.bodies[collection]['value'][0])),
                         lambda e: e.outputs[item].update(statusCode=404),
                         lambda e: e.outputs[collection].update(statusCode=500),
                         lambda e: e.outputs.update({item: None}),
                         lambda e: (e.outputs.update({collection: None}), e.bodies.update({collection: None}))]
            mutations += [lambda e, key=key: e.bodies[collection].update({key: 'unread-page'})
                          for key in ['odata.nextLink', '@odata.nextLink', 'nextLink']]
            for index, mutate in enumerate(mutations):
                a, ev = self.receipt_context(); mutate(ev)
                self.refresh_snapshot_checks(a, ev)
                with self.subTest(side=side, mutation=index):
                    self.assertFalse(ev.outputs['Next_case_' + side + '_stable'])
                    self.assertFalse(ev.evaluate(a['Native_initiation_receipt']['inputs']['qualified']))
                    if side == 'before': self.assertFalse(ev.evaluate(a['Final_source_guard']['expression']))
        for field in ['GUID', 'Created']:
            a, ev = self.receipt_context()
            for value in ev.bodies.values():
                if isinstance(value, dict) and field in value: value[field] = None
                for row in value.get('value', []) if isinstance(value, dict) else []: row[field] = None
            self.refresh_snapshot_checks(a, ev)
            self.assertFalse(ev.outputs['Next_case_before_stable'])
            self.assertFalse(ev.outputs['Next_case_after_stable'])

    def test_actual_text_date_encoding_rejects_timestamp_shift_or_changed_day(self):
        a = self.graph(); payload = {k: 'FICTIONAL-' + k for k in a['Case_payload']['inputs']}
        payload['targetDate'] = '2099-01-01'
        intent = {'kind': 'fictional-next-review-case-intent-v1', 'request': {'CaseUID': 'FICTIONAL'}, 'casePayload': payload}
        bodies = {'Read_case': {'value': [copy.deepcopy(payload)]}, 'Find_case': {'value': []}, 'Next_find_intent': {'value': []}}
        outputs = {'Case_payload': payload, 'Next_reconcile_intent': intent, 'Request': intent['request']}
        expression = a['Verify_case']['expression']
        self.assertTrue(Expressions(bodies, outputs).evaluate(expression))
        # targetDate is native Text, unlike the separate readiness DateOnly field.
        # A timestamp in this field is changed text, never silently converted.
        for value in ['2099-01-01T00:00:00Z', '2098-12-31T14:00:00Z', '2099-01-02', '01/01/2099', None]:
            changed = copy.deepcopy(bodies); changed['Read_case']['value'][0]['targetDate'] = value
            self.assertFalse(Expressions(changed, outputs).evaluate(expression), value)

    def test_writers_do_not_touch_completed_case_or_source_and_never_retry(self):
        a = self.graph(); _, b = fixture()
        writers = {k: v for k, v in a.items() if v['type'] == 'OpenApiConnection' and v['inputs']['parameters']['parameters/method'] != 'GET'}
        self.assertEqual(set(writers), {'Create_request', 'Create_case', 'Next_create_intent', 'Next_create_receipt'})
        for action in writers.values():
            self.assertEqual(action['inputs']['retryPolicy'], {'type': 'none'})
            self.assertNotEqual(action['inputs']['parameters']['parameters/uri'], b['completedCaseUri'])
            if action is not writers['Create_case']: self.assertIn('overwrite=false', action['inputs']['parameters']['parameters/uri'])

    def test_native_graph_size_depth_and_dependencies(self):
        result = build(*fixture()); audit = audit_actions(result['properties']['definition'])
        self.assertLessEqual(audit['maximumActionDepth'], 8)
        self.assertLessEqual(audit['actionCount'], 100)
        actions = flatten(result['properties']['definition']['actions'])
        refs = set(re.findall(r"(?:body|outputs|actions|result)\('([^']+)'\)", json.dumps(result['properties']['definition'])))
        self.assertTrue(refs <= actions.keys(), refs - actions.keys())
        self.assertLess(max(len(v['expression']) for v in actions.values() if isinstance(v.get('expression'), str)), 8192)


if __name__ == '__main__': unittest.main()
