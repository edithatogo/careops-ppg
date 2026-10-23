"""A partial or ambiguous query cannot authorise ownership projection."""
import copy
import unittest
from build_selected_ownership_projection import build
from build_operator_entry import _flatten
from build_selected_event_routes import audit_actions
from test_selected_event_routes import fixtures
from test_prepared_closure_check import Expressions
import hashlib
import json


def fixture():
    context,target,binding=fixtures()
    nodes=context['properties']['definition']['actions']['Resolve_context']['actions']
    read=nodes['Read_selected_case']
    baseline=nodes['Verify_baseline_boundary']['actions']
    baseline['Read_baseline_before']=copy.deepcopy(read)
    baseline['Verify_request']['actions']['Read_source_before']=copy.deepcopy(read)
    binding.update(approvedContextDefinitionSHA256=hashlib.sha256(json.dumps(
        context['properties']['definition'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        expectedCaseUID='LC-FICTIONAL-OP-TEST',expectedCaseETag='"1"',
        expectedResponseUID='LC02-OP-RESP-TEST',caseItemUri="_api/web/lists(guid'00000000-0000-4000-8000-000000000001')/items(1)",
        folderUri="_api/web/GetFolderByServerRelativePath(decodedurl='/site/evidence')",
        journalName='fictional-before.json',commitName='fictional-commit.json')
    return context,target,binding


class OwnershipProjectionTests(unittest.TestCase):
    def test_partial_and_ambiguous_queries_hold_before_any_journal_or_case_write(self):
        flow=build(*fixture());nodes=_flatten(flow['properties']['definition']['actions'])
        expression=nodes['Projection_queries_complete']['inputs']
        names=['Read_projection_offer','Read_projection_responses','Read_projection_journal','Read_projection_commit']
        bodies={n:{'value':[]} for n in names}
        self.assertTrue(Expressions(bodies).evaluate(expression))
        for name in names:
            for key in ['odata.nextLink','@odata.nextLink','nextLink','__next']:
                changed=copy.deepcopy(bodies);changed[name][key]='more-results'
                self.assertFalse(Expressions(changed).evaluate(expression),(name,key))
            changed=copy.deepcopy(bodies);changed[name]['value']=[{},{}]
            self.assertFalse(Expressions(changed).evaluate(expression),name)
        guard=nodes['Verify_projection_evidence']
        self.assertEqual(guard['runAfter'],{'Projection_queries_complete':['Succeeded']})
        self.assertIn("equals(outputs('Projection_queries_complete'),true)",guard['expression'])

    def test_postwrite_history_is_complete_and_writer_contract_stays_bounded(self):
        args=fixture();before=copy.deepcopy(args);flow=build(*args)
        self.assertEqual(args,before)
        nodes=_flatten(flow['properties']['definition']['actions'])
        for key in ['odata.nextLink','@odata.nextLink','nextLink','__next']:
            self.assertIn("empty(body('Projection_response_history_after')?['"+key+"'])",nodes['Verify_projection_after']['expression'])
        writers={n:v for n,v in nodes.items() if v.get('type')=='OpenApiConnection'
                 and v['inputs']['parameters']['parameters/method']!='GET'}
        self.assertEqual(set(writers),{'Create_projection_journal','Apply_projection','Create_projection_commit'})
        for action in writers.values():self.assertEqual(action['inputs']['retryPolicy'],{'type':'none'})
        self.assertEqual(flow['properties']['state'],'Stopped')
        self.assertLessEqual(audit_actions(flow['properties']['definition'])['maximumActionDepth'],8)

    def test_success_requires_exact_saved_commit_readback(self):
        nodes=_flatten(build(*fixture())['properties']['definition']['actions'])
        self.assertEqual(nodes['Read_saved_projection_commit']['runAfter'],{'Create_projection_commit':['Succeeded']})
        self.assertEqual(nodes['Read_saved_projection_commit']['inputs']['parameters']['parameters/method'],'GET')
        receipt=nodes['Native_projection_receipt']
        self.assertEqual(receipt['runAfter'],{'Parse_saved_projection_commit':['Succeeded']})
        expected={'kind':'fictional-ownership-projection-commit-v1','afterCase':{'unknownHumanField':'preserved'}}
        for actual,qualified in [(expected,True),({},False),(None,False),({**expected,'afterCase':{}},False)]:
            ev=Expressions(outputs={'Projection_commit':expected,'Parse_saved_projection_commit':actual})
            self.assertEqual(ev.evaluate(receipt['inputs']['qualified']),qualified)
            self.assertEqual(ev.evaluate(receipt['inputs']['caseOwnershipProjected']),qualified)
            self.assertEqual(ev.evaluate(receipt['inputs']['caseWriteCount']),1 if qualified else None)
            self.assertEqual(ev.evaluate(receipt['inputs']['reconcileBeforeRetry']),not qualified)

    def test_after_guard_preserves_unknown_human_columns(self):
        nodes=_flatten(build(*fixture())['properties']['definition']['actions'])
        before={'CaseUID':'LC-FICTIONAL-OP-TEST','unknownHumanField':'retain','accountableRole':'proposed','caseStatus':'Initiated — FICTIONAL','Modified':'old'}
        after={**before,'accountableRole':'FICTIONAL role','caseStatus':'Ownership accepted — FICTIONAL','Modified':'new'}
        context={'sourcePins':{'ETag':'source-token','UniqueId':'source-uid'},'baselineETag':'baseline-token','baselineUniqueId':'baseline-uid'}
        bodies={'Read_projection_case':before,'Projection_case_after':after,
            'Projection_after_source':context['sourcePins'],'Projection_after_baseline':{'ETag':'baseline-token','UniqueId':'baseline-uid'},
            'Projection_response_history_after':{'value':[{'EventUID':'LC02-OP-RESP-TEST'}]}}
        outputs={'Selected_case_context':context,'Parse_baseline':{'request':{'proposedRole':'FICTIONAL role'}},
            'Projection_case_after':{'headers':{'ETag':'new-token'}},'Projection_case_before':{'headers':{'ETag':'old-token'}}}
        for kind in ['offer','response']:
            for stage in ['before','after']:outputs['Projection_'+kind+'_'+stage]={'headers':{'ETag':kind+'-token'}}
        expression=nodes['Verify_projection_after']['expression']
        self.assertTrue(Expressions(bodies,outputs).evaluate(expression))
        for value in ['changed',None]:
            changed=copy.deepcopy(bodies);changed['Projection_case_after']['unknownHumanField']=value
            self.assertFalse(Expressions(changed,outputs).evaluate(expression))
        changed=copy.deepcopy(bodies);del changed['Projection_case_after']['unknownHumanField']
        self.assertFalse(Expressions(changed,outputs).evaluate(expression))
        changed=copy.deepcopy(outputs);changed['Projection_case_after']['headers']['ETag']='*'
        self.assertFalse(Expressions(bodies,changed).evaluate(expression))

    def test_replay_requires_full_current_case_including_unknown_fields(self):
        nodes=_flatten(build(*fixture())['properties']['definition']['actions'])
        row={'CaseUID':'LC-FICTIONAL-OP-TEST','accountableRole':'FICTIONAL role',
             'caseStatus':'Ownership accepted — FICTIONAL','unknownHumanField':'retain','odata.id':'current-url'}
        context={'CaseUID':row['CaseUID'],'baselineReference':'baseline','baselineUniqueId':'uid','baselineETag':'token'}
        commit={'kind':'fictional-ownership-projection-commit-v1','CaseUID':row['CaseUID'],
            'responseUID':'LC02-OP-RESP-TEST','afterCaseETag':'current-token',
            'afterCase':{**row,'odata.id':'old-transient-url'},'offerETag':'offer-token','responseETag':'response-token','context':context}
        bodies={'Read_projection_case':row,'Read_projection_journal':{'value':[{}]}}
        outputs={'Selected_case_context':context,'Parse_baseline':{'request':{'proposedRole':'FICTIONAL role'}},
            'Parse_committed_projection':commit,'Read_projection_case':{'headers':{'ETag':'current-token'}},
            'Projection_replay_offer':{'headers':{'ETag':'offer-token'}},'Projection_replay_response':{'headers':{'ETag':'response-token'}}}
        expression=nodes['Verify_committed_projection']['expression']
        self.assertTrue(Expressions(bodies,outputs).evaluate(expression))
        changed=copy.deepcopy(bodies);changed['Read_projection_case']['unknownHumanField']='later edit'
        self.assertFalse(Expressions(changed,outputs).evaluate(expression))
