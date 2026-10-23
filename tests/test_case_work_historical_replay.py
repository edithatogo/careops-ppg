"""Historical ownership survives draft selection, never unrelated case changes."""
import copy
import unittest
from build_case_work_router import allow_selected_evidence_link_replay, projection_actions
from build_selected_ownership_projection import build
from build_operator_entry import _flatten
from test_selected_ownership_projection import fixture
from test_prepared_closure_check import Expressions


def observation():
    row={'CaseUID':'LC-FICTIONAL-OP-TEST','accountableRole':'FICTIONAL role',
         'caseStatus':'Ownership accepted — FICTIONAL','unknownHumanField':'retain',
         'evidenceDraftLink':'https://example.invalid/site/source.txt',
         'Modified':'old','EditorId':1,'OData__UIVersionString':'2.0','odata.etag':'old-token'}
    context={'CaseUID':row['CaseUID'],'baselineReference':'baseline','baselineUniqueId':'uid','baselineETag':'token'}
    commit={'kind':'fictional-ownership-projection-commit-v1','CaseUID':row['CaseUID'],
        'responseUID':'LC02-OP-RESP-TEST','afterCaseETag':'old-token','afterCase':copy.deepcopy(row),
        'offerETag':'offer-token','responseETag':'response-token','context':context}
    bodies={'Read_projection_case':copy.deepcopy(row),'Read_projection_journal':{'value':[{}]}}
    outputs={'Selected_case_context':context,'Parse_baseline':{'request':{'proposedRole':'FICTIONAL role'}},
        'Parse_committed_projection':commit,'Read_projection_case':{'headers':{'ETag':'old-token'}},
        'Projection_replay_offer':{'headers':{'ETag':'offer-token'}},'Projection_replay_response':{'headers':{'ETag':'response-token'}}}
    return bodies,outputs


def selected_draft():
    bodies,outputs=observation()
    bodies['Read_projection_case'].update(evidenceDraftLink='https://example.invalid/site/edited.docx',
        Modified='new',EditorId=2,OData__UIVersionString='3.0',**{'odata.etag':'new-token'})
    outputs['Read_projection_case']['headers']['ETag']='new-token'
    return bodies,outputs


class HistoricalProjectionReplayTests(unittest.TestCase):
    def graphs(self):
        strict=build(*fixture());before=copy.deepcopy(strict)
        adapted=allow_selected_evidence_link_replay(projection_actions(strict))
        self.assertEqual(strict,before)
        return _flatten(strict['properties']['definition']['actions']),_flatten(adapted)

    def test_later_draft_selection_is_historical_not_current_qualification(self):
        strict,adapted=self.graphs();bodies,outputs=selected_draft();ev=Expressions(bodies,outputs)
        self.assertFalse(ev.evaluate(strict['Verify_committed_projection']['expression']))
        self.assertTrue(ev.evaluate(adapted['Verify_committed_projection']['expression']))
        receipt=adapted['Native_projection_replay']['inputs']
        self.assertTrue(ev.evaluate(receipt['historicalReplay']))
        for key in ['caseAtProjectionSnapshot','currentSnapshotMatches','currentProjectionQualified']:
            self.assertFalse(ev.evaluate(receipt[key]),key)
        self.assertEqual(receipt['caseWriteCount'],0)
        self.assertFalse(receipt['progressionGranted'])
        self.assertFalse(receipt['caseOwnershipUpdated'])

    def test_unchanged_snapshot_still_matches_exactly(self):
        _,adapted=self.graphs();ev=Expressions(*observation())
        self.assertTrue(ev.evaluate(adapted['Verify_committed_projection']['expression']))
        self.assertFalse(ev.evaluate(adapted['Native_projection_replay']['inputs']['historicalReplay']))
        self.assertTrue(ev.evaluate(adapted['Native_projection_replay']['inputs']['currentProjectionQualified']))

    def test_other_case_changes_are_not_hidden_by_historical_mode(self):
        _,adapted=self.graphs();expression=adapted['Verify_committed_projection']['expression']
        for key in ['unknownHumanField','Title','nextAction','targetDate','sourceBaselineRef',
                    'linkedDocumentUIDs','accountableRole','caseStatus','GUID','Created','AuthorId']:
            bodies,outputs=selected_draft();bodies['Read_projection_case'][key]='changed'
            self.assertFalse(Expressions(bodies,outputs).evaluate(expression),key)
        bodies,outputs=selected_draft();del bodies['Read_projection_case']['unknownHumanField']
        self.assertFalse(Expressions(bodies,outputs).evaluate(expression))

    def test_changed_strict_contract_is_refused_without_loosening_comparison(self):
        actions=projection_actions(build(*fixture()))
        verify=actions['Verify_projection_evidence']['actions']['Choose_projection_path']['actions']['Verify_committed_projection']
        verify['expression']=verify['expression'].replace("union(body('Read_projection_case'),", "union(body('OTHER'),")
        with self.assertRaisesRegex(ValueError,'full-row committed replay contract'):
            allow_selected_evidence_link_replay(actions)
