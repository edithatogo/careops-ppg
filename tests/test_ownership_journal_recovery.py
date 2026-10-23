"""Exercise the emitted continuation against retained and changed native frames."""
import copy
import hashlib
import json
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/lifecycle"))
from build_ownership_journal_recovery import build
from build_selected_ownership_projection import build as projection
from build_case_work_router import rename_actions
from build_multisource_case_context import digest, _projection_source_uri
from build_operator_entry import _flatten
from build_selected_event_routes import audit_actions
from test_selected_ownership_projection import fixture as projection_fixture
from test_prepared_closure_check import Expressions

UID = '00000000-0000-4000-8000-000000000009'


def fixture():
    profile = projection(*projection_fixture())
    definition = profile['properties']['definition']
    definition['actions'] = rename_actions(definition['actions'], 'Selected_')
    definition['actions']['Selected_case_context'] = {'type': 'Compose', 'inputs': {}, 'runAfter': {}}
    definition['actions']['Route_ownership_projection'] = {'type': 'Compose', 'inputs': 'existing route', 'runAfter': {}}
    definition['triggers'] = {'manual': {'type': 'Request', 'runtimeConfiguration': {'concurrency': {'runs': 1}}}}
    nodes = _flatten(definition['actions'])
    for name in ('Selected_Projection_before_source', 'Selected_Projection_after_source'):
        nodes[name]['inputs']['parameters']['parameters/uri'] = _projection_source_uri()
    role = 'FICTIONAL test role'
    before = {'CaseUID': 'LC-FICTIONAL-OP-TEST', 'Id': 1, 'caseStatus': 'Initiated — FICTIONAL',
              'accountableRole': 'UNACCEPTED — proposed fictional role: ' + role,
              'unknownHumanField': '@retain literal human text'}
    context = {'CaseUID': before['CaseUID'], 'nativeItemId': 1, 'caseETag': 'case-token',
               'scope': {'source': 'fictional'}, 'sourcePins': {'UniqueId': UID, 'ETag': 'source-token'},
               'baselineReference': 'baseline', 'baselineUniqueId': UID, 'baselineETag': 'baseline-token'}
    offer = {'EventUID': 'OFFER', 'RecordState': 'Proposed', 'FictionalTest': True, 'SubjectRole': role}
    response = {**offer, 'EventUID': 'RESPONSE', 'ParentEventUID': 'OFFER', 'RecordState': 'Accepted',
                'ConditionsState': 'None recorded'}
    journal = {'kind': 'fictional-ownership-projection-before-v1', 'runId': 'original-run',
               'context': context, 'beforeCase': before, 'beforeCaseETag': 'case-token',
               'proposedPatch': {'accountableRole': role, 'caseStatus': 'Ownership accepted — FICTIONAL'},
               'offer': offer, 'response': response}
    raw = json.dumps(journal).encode()
    binding = {'qualificationOnly': True, 'approvedDefinitionSHA256': digest(definition),
               'journalFile': {'UniqueId': UID, 'ETag': 'journal-token'}, 'journalSHA256': hashlib.sha256(raw).hexdigest()}
    return profile, binding, raw


def observations(raw):
    journal = json.loads(raw)
    pin = {'UniqueId': UID, 'ETag': 'journal-token', 'Length': len(raw)}
    bodies = {'Selected_Read_projection_case': journal['beforeCase'],
              'Selected_Read_projection_offer': {'value': [journal['offer']]},
              'Selected_Read_projection_responses': {'value': [journal['response']]},
              'Selected_Read_projection_journal': {'value': [pin]},
              'Selected_Read_projection_commit': {'value': []},
              'JournalRecovery_commit_absent': {'value': []},
              'JournalRecovery_before': pin, 'JournalRecovery_after': pin}
    outputs = {'Selected_case_context': {**journal['context'], 'contextValid': True},
               'Selected_Read_projection_case': {'headers': {'ETag': 'case-token'}},
               'JournalRecovery_expected': journal, 'JournalRecovery_parse': journal,
               'Test_trigger': {'text': 'Project ownership'}}
    return copy.deepcopy(bodies), {k: copy.deepcopy(v) for k, v in outputs.items()}


class JournalRecoveryTests(unittest.TestCase):
    def test_original_graph_preserved_and_only_conditional_case_and_commit_writers_added(self):
        args = fixture(); original = copy.deepcopy(args)
        result = build(*args)
        self.assertEqual(args, original)
        actions = result['properties']['definition']['actions']
        self.assertEqual({k: actions[k] for k in original[0]['properties']['definition']['actions']},
                         original[0]['properties']['definition']['actions'])
        nodes = _flatten(actions)
        writers = {n: v for n, v in nodes.items() if n.startswith('Continued_') and
                   v.get('type') == 'OpenApiConnection' and v['inputs']['parameters']['parameters/method'] != 'GET'}
        self.assertEqual(set(writers), {'Continued_Selected_Apply_projection', 'Continued_Selected_Create_projection_commit'})
        for writer in writers.values(): self.assertEqual(writer['inputs']['retryPolicy'], {'type': 'none'})
        self.assertIn('Continued_Selected_Projection_case_before',
                      writers['Continued_Selected_Apply_projection']['inputs']['parameters']['parameters/headers']['IF-MATCH'])
        self.assertEqual(result['properties']['state'], 'Stopped')
        self.assertLessEqual(audit_actions(result['properties']['definition'])['maximumActionDepth'], 8)
        expected = nodes['JournalRecovery_expected']['inputs']
        self.assertEqual(expected['beforeCase']['unknownHumanField'], '@@retain literal human text')

    def test_candidate_excludes_first_journal_creation_completed_replay_and_changed_token(self):
        args = fixture(); nodes = _flatten(build(*args)['properties']['definition']['actions'])
        bodies, outputs = observations(args[2]); expression = nodes['JournalRecovery_entry']['expression']
        self.assertTrue(Expressions(bodies, outputs).evaluate(expression))
        for name, value in [('journal', []), ('commit', [{}]), ('responses', [{}, {}])]:
            changed = copy.deepcopy(bodies); changed['Selected_Read_projection_' + name]['value'] = value
            self.assertFalse(Expressions(changed, outputs).evaluate(expression))
        for key in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink', '__next'):
            changed = copy.deepcopy(bodies); changed['Selected_Read_projection_offer'][key] = 'more'
            self.assertFalse(Expressions(changed, outputs).evaluate(expression))
        changed = copy.deepcopy(outputs); changed['Selected_Read_projection_case']['headers']['ETag'] = 'advanced'
        self.assertFalse(Expressions(bodies, changed).evaluate(expression))
        changed = copy.deepcopy(outputs); changed['Test_trigger']['text'] = 'Check context'
        self.assertFalse(Expressions(bodies, changed).evaluate(expression))

    def test_exact_frame_refuses_unknown_field_event_source_baseline_journal_or_commit_changes(self):
        args = fixture(); nodes = _flatten(build(*args)['properties']['definition']['actions'])
        bodies, outputs = observations(args[2]); expression = nodes['JournalRecovery_valid']['expression']
        self.assertTrue(Expressions(bodies, outputs).evaluate(expression))
        mutations = [lambda b, o: b['Selected_Read_projection_case'].update(unknownHumanField='changed'),
                     lambda b, o: b['Selected_Read_projection_offer']['value'][0].update(Note='new human note'),
                     lambda b, o: b['Selected_Read_projection_responses']['value'][0].update(ConditionsState='Open'),
                     lambda b, o: o['Selected_case_context']['sourcePins'].update(ETag='new'),
                     lambda b, o: o['Selected_case_context'].update(baselineETag='new'),
                     lambda b, o: b['JournalRecovery_after'].update(ETag='new'),
                     lambda b, o: o['JournalRecovery_parse'].update(runId='different'),
                     lambda b, o: b['JournalRecovery_commit_absent'].update(value=[{}]),
                     lambda b, o: b['JournalRecovery_commit_absent'].update(__next='more')]
        for mutate in mutations:
            b, o = copy.deepcopy((bodies, outputs)); mutate(b, o)
            self.assertFalse(Expressions(b, o).evaluate(expression), mutate)

    def test_unreviewed_profile_bytes_and_wildcard_pin_refused(self):
        for change in ('definition', 'bytes', 'pin', 'concurrency', 'reader'):
            p, b, raw = fixture()
            if change == 'definition': b['approvedDefinitionSHA256'] = '0' * 64
            elif change == 'bytes': raw += b' '
            elif change == 'pin': b['journalFile']['ETag'] = '*'
            elif change == 'concurrency':
                p['properties']['definition']['triggers']['manual']['runtimeConfiguration']['concurrency']['runs'] = 2
                b['approvedDefinitionSHA256'] = digest(p['properties']['definition'])
            else:
                _flatten(p['properties']['definition']['actions'])['Selected_Projection_after_source']['inputs']['parameters']['parameters/uri'] = 'foreign'
                b['approvedDefinitionSHA256'] = digest(p['properties']['definition'])
            with self.subTest(change=change), self.assertRaises(ValueError): build(p, b, raw)

    def test_changed_final_journal_is_unknown_effect_requiring_reconciliation(self):
        nodes = _flatten(build(*fixture())['properties']['definition']['actions'])
        hold = nodes['Continued_JournalRecovery_uncertain']['inputs']
        self.assertIsNone(hold['caseWriteCount']); self.assertTrue(hold['reconcileBeforeRetry'])
        receipt = nodes['Continued_Selected_Native_projection_receipt']['inputs']
        self.assertEqual(receipt['journalWrites'], 0)
        self.assertIn('runId', receipt['recoveredFromRunId'])
