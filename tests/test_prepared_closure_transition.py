"""Exercise the emitted transition's actual evidence/concurrency/recovery gates."""
import base64
import copy
import hashlib
import unittest
from build_prepared_closure_transition import build_actions
from build_selected_event_routes import audit_actions
from test_case_work_closure_route import fixture as router_fixture
from test_prepared_closure_check import Expressions
from test_prepared_decision_outcome import flatten


def fixture():
    context, _, _, _ = router_fixture()
    uid = lambda n: '00000000-0000-4000-8000-' + str(n).zfill(12)
    payload = b'FICTIONAL exact approved document bytes'
    binary = {'$content-type': 'application/octet-stream', '$content': base64.b64encode(payload).decode()}
    reads = {}
    retained = {}
    for index, key in enumerate(['assurance', 'readiness', 'consultation', 'source', 'draft', 'issued', 'proof', 'date', 'originalSource', 'sourceBaseline', 'template', 'generationReceipt', 'ownershipCommit'], 1):
        collection = index < 4
        reads[key] = {'uri': "_api/web/lists(guid'" + uid(index) + "')/items" if collection else "_api/web/GetFileById('" + uid(index) + "')", 'collection': collection}
        retained[key] = [{'Id': index, 'GUID': uid(index), 'odata.id': None}] if collection else {'UniqueId': uid(index), 'ETag': '"1"', 'odata.id': None}
    for content, key in [('sourceContent', 'source'), ('issuedContent', 'issued'), ('dateContent', 'date')]:
        reads[content] = {'uri': reads[key]['uri'] + '/$value', 'collection': False}
        retained[content] = {'$content': binary['$content']} if key != 'date' else {'reviewDate': '2099-01-01'}
    observation = {'closureEvidenceConsistent': True, 'nextReviewDateProvenanceConsistent': True,
        'nextOccurrencePrerequisitesConsistent': True, 'preparedScope': {'CaseUID': 'LC-FICTIONAL-OP-TEST',
            'DocumentSHA256': hashlib.sha256(payload).hexdigest()}, 'issuedFile': {'UniqueId': uid(6), 'ETag': '"1"'},
        'selectedEvents': {k: 'FICTIONAL-' + k for k in ['committee', 'officer', 'coordinator', 'authorisation', 'publication', 'implementation', 'verification']},
        'nextReviewDate': '2099-01-01', 'nextReviewRuleReference': 'fictional://explicit-test-rule', 'nextReviewEvidenceFileUID': uid(8)}
    binding = {'qualificationOnly': True, 'requestReference': 'LC04-CLOSE-TEST', 'expectedCaseUID': 'LC-FICTIONAL-OP-TEST',
        'expectedCaseETag': '"3"', 'expectedCaseStatus': 'Ownership accepted — FICTIONAL',
        'caseItemUri': "_api/web/lists(guid'" + uid(9) + "')/items(9)",
        'folderUri': "_api/web/GetFolderByServerRelativePath(decodedurl='/site/evidence')",
        'evidenceReads': reads, 'expectedEvidence': retained, 'expectedObservation': observation}
    return context, binding


class ClosureTransitionTests(unittest.TestCase):
    def graph(self): return flatten(build_actions(*fixture()))

    def test_only_owned_case_status_merge_and_create_only_receipts(self):
        c, b = fixture(); before = copy.deepcopy((c, b)); actions = build_actions(c, b)
        self.assertEqual((c, b), before)
        a = flatten(actions)
        writers = {k: v for k, v in a.items() if v['type'] == 'OpenApiConnection' and v['inputs']['parameters']['parameters/method'] != 'GET'}
        merges = [v for v in writers.values() if v['inputs']['parameters']['parameters/headers'].get('X-HTTP-Method') == 'MERGE']
        self.assertEqual(len(merges), 1)
        self.assertEqual(a['Cycle_contract']['inputs']['patch'], {'caseStatus': 'Review closed — FICTIONAL'})
        self.assertEqual(merges[0]['inputs']['parameters']['parameters/uri'], b['caseItemUri'])
        self.assertEqual(merges[0]['inputs']['parameters']['parameters/headers']['IF-MATCH'], "@outputs('Cycle_case_prewrite')?['headers']?['ETag']")
        for v in writers.values():
            self.assertEqual(v['inputs']['retryPolicy'], {'type': 'none'})
            if v not in merges: self.assertIn('overwrite=false', v['inputs']['parameters']['parameters/uri'])

    def test_first_write_requires_same_execution_observation_and_exact_date_rule(self):
        a = self.graph(); b = fixture()[1]
        observation = {**b['expectedObservation'], **{k: False for k in ['closurePerformed', 'nextOccurrenceCreated', 'progressionGranted', 'actorAuthorityQualified', 'realPolicyEffects']}, 'writeCount': 0}
        bodies = {'Cycle_case': {'caseStatus': b['expectedCaseStatus']}, 'Cycle_find_before': {'value': []}, 'Cycle_find_after': {'value': []}}
        outputs = {'Native_closure_observation': observation, 'Cycle_contract': a['Cycle_contract']['inputs'], 'Cycle_case': {'headers': {'ETag': b['expectedCaseETag']}}}
        expression = a['Cycle_validate_initial']['expression']
        self.assertTrue(Expressions(bodies, outputs).evaluate(expression))
        for key, value in [('closureEvidenceConsistent', False), ('nextReviewDateProvenanceConsistent', False), ('nextReviewRuleReference', 'fictional://different-rule'), ('nextReviewDate', '2099-02-01'), ('actorAuthorityQualified', True)]:
            changed = copy.deepcopy(outputs); changed['Native_closure_observation'][key] = value
            self.assertFalse(Expressions(bodies, changed).evaluate(expression), key)

    def test_stale_or_tampered_prewrite_refuses_merge(self):
        a = self.graph(); row = {'CaseUID': 'LC-FICTIONAL-OP-TEST', 'caseStatus': 'Ownership accepted — FICTIONAL', 'nextAction': 'Human edit retained'}
        snap = fixture()[1]['expectedEvidence']
        outputs = {'Cycle_prewrite_complete': True, 'Cycle_prewrite_snapshot': snap, 'Cycle_current_snapshot': snap,
            'Cycle_case_prewrite': {'headers': {'ETag': '"3"'}}, 'Cycle_case': {'headers': {'ETag': '"3"'}}, 'Cycle_first_stored_before': {'durable': True}, 'Cycle_before_payload': {'durable': True}}
        bodies = {'Cycle_case_prewrite': copy.deepcopy(row), 'Cycle_case': copy.deepcopy(row)}
        expression = a['Cycle_verify_prewrite']['expression']
        self.assertTrue(Expressions(bodies, outputs).evaluate(expression))
        for stored in [None, {}, {'corrupt': True}]:
            corrupt = copy.deepcopy(outputs); corrupt['Cycle_first_stored_before'] = stored
            self.assertFalse(Expressions(bodies, corrupt).evaluate(expression))
        stale = copy.deepcopy(outputs); stale['Cycle_case_prewrite']['headers']['ETag'] = '"4"'
        self.assertFalse(Expressions(bodies, stale).evaluate(expression))
        edited = copy.deepcopy(bodies); edited['Cycle_case_prewrite']['nextAction'] = 'Concurrent human edit'
        self.assertFalse(Expressions(edited, outputs).evaluate(expression))
        changed = copy.deepcopy(outputs); changed['Cycle_prewrite_snapshot']['assurance'].append({'Id': 99})
        changed['Cycle_current_snapshot'] = copy.deepcopy(snap)
        self.assertFalse(Expressions(bodies, changed).evaluate(expression))

    def test_after_gate_preserves_unknown_human_fields_and_requires_new_token(self):
        a = self.graph(); before = {'CaseUID': 'LC-FICTIONAL-OP-TEST', 'caseStatus': 'Ownership accepted — FICTIONAL', 'customHumanField': 'Do not erase'}
        after = {**before, 'caseStatus': 'Review closed — FICTIONAL', 'Modified': '2098-01-01T00:00:00Z', 'EditorId': 1}
        outputs = {'Cycle_after_complete': True, 'Cycle_after_snapshot': {}, 'Cycle_current_snapshot': {},
            'Cycle_case': {'headers': {'ETag': '"3"'}}, 'Cycle_case_after': {'headers': {'ETag': '"4"'}}}
        expression = a['Cycle_verify_after']['expression']
        self.assertTrue(Expressions({'Cycle_case': before, 'Cycle_case_after': after}, outputs).evaluate(expression))
        altered = {**after, 'customHumanField': 'Erased'}
        self.assertFalse(Expressions({'Cycle_case': before, 'Cycle_case_after': altered}, outputs).evaluate(expression))
        stale = copy.deepcopy(outputs); stale['Cycle_case_after']['headers']['ETag'] = '"3"'
        self.assertFalse(Expressions({'Cycle_case': before, 'Cycle_case_after': after}, stale).evaluate(expression))

    def test_partial_effect_without_after_proof_never_repeats_merge(self):
        a = self.graph()
        missing = {'Cycle_find_before': {'value': [{}]}, 'Cycle_find_after': {'value': []}, 'Cycle_find_commit': {'value': []}}
        self.assertFalse(Expressions(missing, {'Cycle_reads_valid': True}).evaluate(a['Cycle_choose_recovery']['expression']))
        # The alternative first path also refuses an existing journal. Only a
        # reconciled durable after-proof can reach the commit-only recovery path.
        self.assertIn("equals(length(body('Cycle_find_before')?['value']),0)", a['Cycle_validate_initial']['expression'])
        recovery = flatten(a['Cycle_verify_recovery']['actions'])
        self.assertNotIn('Cycle_apply_closure', recovery)
        self.assertEqual([v['inputs']['parameters']['parameters/method'] for v in recovery.values() if v['type'] == 'OpenApiConnection'], ['POST', 'GET'])

    def test_replay_checks_exact_contract_row_token_and_full_evidence(self):
        a = self.graph(); contract = a['Cycle_contract']['inputs']; row = {'CaseUID': contract['CaseUID'], 'caseStatus': 'Review closed — FICTIONAL', 'odata.id': None}
        snap = fixture()[1]['expectedEvidence']; proof = {'afterCase': row, 'afterCaseETag': '"4"', 'evidence': snap}
        before_proof = {'kind': 'fictional-prepared-closure-before-v1', 'contract': contract, 'beforeCaseETag': '"3"', 'beforeCase': {**row, 'caseStatus': contract['initialCaseStatus']}, 'evidence': snap}
        proof['kind'] = 'fictional-prepared-closure-after-v1'; proof['contract'] = contract
        commit = {'kind': 'fictional-prepared-closure-commit-v1', 'contract': contract, 'beforeProof': before_proof, 'afterProof': proof}
        bodies = {'Cycle_case': row, 'Cycle_find_before': {'value': [{}]}, 'Cycle_find_after': {'value': [{}]}}
        outputs = {'Cycle_commit_record': commit, 'Cycle_contract': contract, 'Cycle_case': {'headers': {'ETag': '"4"'}}, 'Cycle_current_snapshot': snap, 'Cycle_replay_before': before_proof, 'Cycle_replay_after': proof}
        expression = a['Cycle_verify_replay']['expression']
        self.assertTrue(Expressions(bodies, outputs).evaluate(expression))
        malformed = copy.deepcopy(outputs)
        malformed['Cycle_commit_record']['beforeProof']['kind'] = 'arbitrary-mutually-matching-blob'
        malformed['Cycle_replay_before'] = copy.deepcopy(malformed['Cycle_commit_record']['beforeProof'])
        self.assertFalse(Expressions(bodies, malformed).evaluate(expression))
        changed = copy.deepcopy(outputs); changed['Cycle_contract']['requestReference'] = 'LC04-DIFFERENT'
        changed['Cycle_commit_record'] = copy.deepcopy(commit)
        self.assertFalse(Expressions(bodies, changed).evaluate(expression))
        self.assertFalse(any(v['type'] == 'OpenApiConnection' for v in flatten(a['Cycle_verify_replay']['actions']).values()))

    def test_supported_recovery_uses_durable_matching_after_proof_only(self):
        a = self.graph(); contract = a['Cycle_contract']['inputs']; snap = fixture()[1]['expectedEvidence']
        old = {'CaseUID': contract['CaseUID'], 'caseStatus': contract['initialCaseStatus'], 'nextAction': 'Retain human text', 'odata.id': None}
        row = {**old, 'caseStatus': 'Review closed — FICTIONAL'}
        before = {'kind': 'fictional-prepared-closure-before-v1', 'contract': contract, 'beforeCaseETag': contract['initialCaseETag'], 'beforeCase': old, 'evidence': snap}
        after = {'kind': 'fictional-prepared-closure-after-v1', 'contract': contract, 'afterCase': row, 'afterCaseETag': '"4"', 'evidence': snap}
        outputs = {'Cycle_contract': contract, 'Cycle_before_record': before, 'Cycle_after_record': after, 'Cycle_current_snapshot': snap, 'Cycle_case': {'headers': {'ETag': '"4"'}}}
        expression = a['Cycle_verify_recovery']['expression']
        self.assertTrue(Expressions({'Cycle_case': row}, outputs).evaluate(expression))
        changed = copy.deepcopy(outputs); changed['Cycle_after_record']['afterCaseETag'] = '"5"'
        self.assertFalse(Expressions({'Cycle_case': row}, changed).evaluate(expression))
        tampered = copy.deepcopy(outputs); tampered['Cycle_before_record']['beforeCase']['nextAction'] = 'Lost text'
        self.assertFalse(Expressions({'Cycle_case': row}, tampered).evaluate(expression))

    def test_corrupt_or_missing_durable_records_block_first_effect_or_commit(self):
        a = self.graph()
        after = a['Cycle_verify_durable_after']['expression']
        for stored in [None, {}, {'changed': True}]:
            self.assertFalse(Expressions(outputs={'Cycle_first_stored_after': stored, 'Cycle_first_after_record': {'valid': True}}).evaluate(after))
        self.assertTrue(Expressions(outputs={'Cycle_first_stored_after': {'valid': True}, 'Cycle_first_after_record': {'valid': True}}).evaluate(after))
        self.assertEqual(a['Cycle_first_read_before']['runAfter'], {'Cycle_create_before': ['Succeeded']})
        self.assertEqual(a['Cycle_prewrite_assurance']['runAfter'], {'Cycle_first_stored_before': ['Succeeded']})
        self.assertIn("equals(outputs('Cycle_first_stored_before'),outputs('Cycle_before_payload'))", a['Cycle_verify_prewrite']['expression'])
        for prefix in ['First_', 'Recovery_']:
            payload = a[prefix + 'Cycle_commit_payload']['inputs']
            self.assertIn('stored' if prefix == 'First_' else 'record', payload['beforeProof'])
            self.assertIn('stored' if prefix == 'First_' else 'record', payload['afterProof'])
            receipt = a[prefix + 'Native_closure_transition']['inputs']
            ev = Expressions(outputs={prefix + 'Cycle_saved_commit': {'bad': True}, prefix + 'Cycle_commit_payload': {'good': True}})
            self.assertFalse(ev.evaluate(receipt['qualified']))
            self.assertTrue(ev.evaluate(receipt['reconcileBeforeRetry']))

    def test_retained_metadata_projection_and_native_json_binary_transport(self):
        c, b = fixture()
        for key, spec in b['evidenceReads'].items():
            if not spec['collection'] and not key.endswith('Content'):
                fields = sorted(k for k in b['expectedEvidence'][key] if not k.startswith('odata.'))
                spec['uri'] += '?$select=' + ','.join(fields)
        b['expectedEvidence']['proof']['odata.metadata'] = 'https://example.invalid/site/_api/$metadata#SP.File&$select=ETag,UniqueId'
        a = flatten(build_actions(c, b))
        reordered = copy.deepcopy(b); reordered['evidenceReads']['proof']['uri'] = reordered['evidenceReads']['proof']['uri'].replace('ETag,UniqueId', 'UniqueId,ETag')
        with self.assertRaises(ValueError): build_actions(c, reordered)
        self.assertIn('?$select=ETag,UniqueId', a['Cycle_current_proof']['inputs']['parameters']['parameters/uri'])
        wrong = copy.deepcopy(b); wrong['evidenceReads']['proof']['uri'] += ',Length'
        with self.assertRaises(ValueError): build_actions(c, wrong)
        record = {'reviewDate': '2099-01-01'}
        import json
        raw = json.dumps(record)
        date_expression = a['Cycle_current_snapshot']['inputs']['dateContent']
        self.assertEqual(Expressions({'Cycle_current_dateContent': raw}).evaluate(date_expression), record)
        wrapped = {'$content': base64.b64encode(raw.encode()).decode()}
        # The existing owner's expression harness lacks this standard intrinsic.
        # Supply only its decoded literal; evaluate the emitted branch/JSON logic.
        primitive = "base64ToString(body('Cycle_current_dateContent')?['$content'])"
        self.assertIn(primitive, date_expression)
        decoded = base64.b64decode(wrapped['$content']).decode()
        supplied = date_expression.replace(primitive, "'" + decoded.replace("'", "''") + "'")
        self.assertEqual(Expressions({'Cycle_current_dateContent': wrapped}).evaluate(supplied), record)
        expression = a['Cycle_current_snapshot']['inputs']['sourceContent']['$content']
        original = b['expectedEvidence']['sourceContent']['$content']
        self.assertEqual(Expressions({'Cycle_current_sourceContent': {'$content': original, '$content-type': 'different transport type'}}).evaluate(expression), original)
        self.assertIsNone(Expressions({'Cycle_current_sourceContent': 'unsupported plain text'}).evaluate(expression))

    def test_incomplete_or_unbound_evidence_cannot_build(self):
        for mutate in [lambda b: b.update(expectedCaseETag='*'),
                       lambda b: b['expectedObservation'].update(nextReviewDateProvenanceConsistent=False),
                       lambda b: b['expectedEvidence'].pop('dateContent'),
                       lambda b: b['evidenceReads']['assurance'].update(uri=b['evidenceReads']['assurance']['uri']+'?$filter=Id eq 1')]:
            c, b = fixture(); mutate(b)
            with self.assertRaises(ValueError): build_actions(c, b)

    def test_incomplete_history_or_ambiguous_receipts_hold_all_writer_routes(self):
        a = self.graph(); b = fixture()[1]
        bodies = {'Cycle_case': {'CaseUID': b['expectedCaseUID']}, **{'Cycle_find_' + k: {'value': []} for k in ['before', 'after', 'commit']}}
        outputs = {'Cycle_case': {'headers': {'ETag': '"3"'}}, 'Cycle_current_complete': True,
            'Cycle_current_snapshot': b['expectedEvidence'], 'Cycle_expected_evidence': b['expectedEvidence']}
        expression = a['Cycle_reads_valid']['inputs']
        self.assertTrue(Expressions(bodies, outputs).evaluate(expression))
        incomplete = copy.deepcopy(outputs); incomplete['Cycle_current_complete'] = False
        self.assertFalse(Expressions(bodies, incomplete).evaluate(expression))
        ambiguous = copy.deepcopy(bodies); ambiguous['Cycle_find_commit']['value'] = [{}, {}]
        self.assertFalse(Expressions(ambiguous, outputs).evaluate(expression))
        partial = copy.deepcopy(bodies); partial['Cycle_find_after']['odata.nextLink'] = 'next-page'
        self.assertFalse(Expressions(partial, outputs).evaluate(expression))

    def test_graph_names_dependencies_and_native_depth(self):
        graph = build_actions(*fixture())
        result = audit_actions({'actions': graph})
        self.assertLessEqual(result['maximumActionDepth'], 8)
        self.assertLessEqual(result['actionCount'], 180)


if __name__ == '__main__': unittest.main()
