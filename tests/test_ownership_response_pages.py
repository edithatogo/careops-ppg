"""A partial offer/response history cannot authorise an ownership response."""
import copy
import unittest
from build_selected_ownership_response import build
from build_operator_entry import _flatten
from test_selected_event_routes import fixtures
from test_prepared_closure_check import Expressions


def guard_fixture():
    nodes = _flatten(build(*fixtures())['properties']['definition']['actions'])
    scope = dict(CaseUID='LC-FICTIONAL-TEST', DocumentReference='fictional://source',
                 ReviewedVersionRef='fictional-v1', DocumentSHA256='a'*64)
    request = dict(requestReference='LC02-OP-TEST', proposedRole='FICTIONAL owner')
    parent = dict(scope, Id=1, EventUID='LC02-OP-OFFER-LC02-OP-TEST', RecordState='Proposed',
                  EventKind='Ownership handoff', FictionalTest=True,
                  SubjectRole=request['proposedRole'], FromRole='FICTIONAL initiating role')
    source = dict(ETag='source-token', UniqueId='source-id')
    baseline = dict(ETag='baseline-token', UniqueId='baseline-id')
    context = dict(contextValid=True, scope=scope, caseETag='case-token', sourcePins=source,
                   baselineETag=baseline['ETag'], baselineUniqueId=baseline['UniqueId'])
    bodies = {'Read_selected_case':dict(caseStatus='Initiated — FICTIONAL',
                  accountableRole='UNACCEPTED — proposed fictional role: '+request['proposedRole']),
              'Offer_source_before':source, 'Offer_baseline_before':baseline,
              'Read_current_offer':{'value':[parent]}, 'Read_response_history':{'value':[]},
              'Response_parent_before':parent}
    outputs = {'Parse_baseline':{'request':request}, 'Selected_case_context':context,
               'Offer_case_before':{'headers':{'ETag':'case-token'}},
               'Response_parent_before':{'headers':{'ETag':'parent-token'}},
               'Response_exact_replay':False,
               'Test_trigger':{'text':'LC02-OP-RESP-TEST'}}
    return nodes['Verify_offer_before']['expression'], bodies, outputs


class OwnershipResponsePages(unittest.TestCase):
    def test_complete_offer_and_empty_response_history_pass_prewrite_guard(self):
        expression, bodies, outputs = guard_fixture()
        self.assertTrue(Expressions(bodies, outputs).evaluate(expression))

    def test_each_continuation_marker_holds_actual_prewrite_guard(self):
        expression, bodies, outputs = guard_fixture()
        for name in ['Read_current_offer', 'Read_response_history']:
            for marker in ['nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink', '__next']:
                changed = copy.deepcopy(bodies)
                changed[name][marker] = 'https://example.invalid/next-page'
                with self.subTest(query=name, marker=marker):
                    self.assertFalse(Expressions(changed, outputs).evaluate(expression))
