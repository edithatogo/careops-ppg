"""Different eligible PPGs keep their own reviewed routes in one native graph."""
import copy
import unittest
from build_native_completed_review import build_runtime_closure_observer, _source_review_requirements
from build_operator_entry import _flatten, build as entry_build
from build_selected_event_routes import audit_actions
import test_native_completed_review as completed_tests
from test_prepared_closure_check import fixture, Expressions, SCOPE


def binding():
    base=completed_tests.NativeCompletedReviewTests().complete_binding()
    first=base['allowedSources'][0]
    second=copy.deepcopy(first)
    second.update(DocumentUID='FICTIONAL-SECOND',UniqueId='00000000-0000-4000-8000-000000000077')
    for number,profile,roles in [(1,first,['FICTIONAL content-review role']),
                                 (2,second,['FICTIONAL records-review role','FICTIONAL second check role'])]:
        profile['reviewRequirements']={'requiredFictionalRoles':roles,
            'purposeReferences':{role:'fictional://route-'+str(number)+'/'+role for role in base['purposeReferences']}}
    base['allowedSources'].append(second)
    return base


def rows(roles):
    result=[]
    for number,role in enumerate(roles):
        common={**SCOPE,'EventKind':'Consultation','SubjectRole':role,'FictionalTest':True,
            'ConditionsState':'None recorded','SupersedesEventUID':None,'ActorName':'FICTIONAL actor',
            'Summary':'FICTIONAL summary','EvidenceReference':'fictional://evidence','NextAction':'FICTIONAL next'}
        uid='FICTIONAL-request-'+str(number)
        result.extend([{**common,'EventUID':uid,'RecordState':'Pending response','ParentEventUID':None,'OccurredOn':'2026-10-18T10:00:00Z'},
            {**common,'EventUID':'FICTIONAL-response-'+str(number),'RecordState':'Responded','ParentEventUID':uid,
             'ResponseSummary':'FICTIONAL response','OccurredOn':'2026-10-18T11:00:00Z'}])
    return result


def coverage(graph, profile, events):
    nodes=_flatten(graph);guard=nodes['Closure_Ready_consultation_Runtime_guard']
    ev=Expressions(outputs={'Selected_case_context':{'CaseUID':SCOPE['CaseUID'],'sourcePins':{'UniqueId':profile['UniqueId']}},
        'Native_prepared_revision':{'preparationQualified':True,'consultationOpenable':True,
            'originalSourceIsPreparedRevision':False,'preparedRevision':{'scope':SCOPE,
                'originalSourceScope':{'DocumentReference':'fictional://original'}}}})
    if not ev.evaluate(guard['expression']):return None,ev
    for name,action in guard['actions'].items():
        kind=action['type']
        if kind=='OpenApiConnection':ev.bodies[name]={'value':events}
        elif kind=='Query':
            selected=[]
            for row in ev.evaluate(action['inputs']['from']):
                ev.current=row
                if ev.evaluate(action['inputs']['where']):selected.append(row)
            ev.bodies[name]=selected
        elif kind=='Select':
            selected=[]
            for row in ev.evaluate(action['inputs']['from']):
                ev.current=row
                selected.append({key:ev.evaluate(value) for key,value in action['inputs']['select'].items()})
            ev.bodies[name]=selected
        elif kind=='Compose':
            ev.outputs[name]=({key:ev.evaluate(value) for key,value in action['inputs'].items()}
                if isinstance(action['inputs'],dict) else ev.evaluate(action['inputs']))
        else:raise AssertionError(kind)
    return ev.outputs['Closure_Ready_consultation_Receipt'],ev


class SourceReviewRequirementsTests(unittest.TestCase):
    def graph(self):
        c,_,_=fixture(True);b=binding();before=copy.deepcopy((c,b))
        result=build_runtime_closure_observer(c,b)
        self.assertEqual((c,b),before)
        return result,b

    def test_two_sources_with_different_role_counts_use_exact_reviewed_requirements(self):
        graph,b=self.graph()
        for profile in b['allowedSources']:
            required=profile['reviewRequirements']['requiredFictionalRoles']
            receipt,_=coverage(graph,profile,rows(required))
            self.assertTrue(receipt['coverageHistoryComplete'])
            self.assertEqual([r['SubjectRole'] for r in receipt['requiredRoleResults']],required)
            self.assertTrue(all(r['complete'] for r in receipt['requiredRoleResults']))
            self.assertFalse(receipt['progressionGranted'])
            missing,_=coverage(graph,profile,rows(required)[:-1])
            self.assertFalse(missing['coverageHistoryComplete'])
        wrong=b['allowedSources'][0]['reviewRequirements']['requiredFictionalRoles']
        receipt,_=coverage(graph,b['allowedSources'][1],rows(wrong))
        self.assertFalse(receipt['coverageHistoryComplete'])
        extra,_=coverage(graph,b['allowedSources'][0],rows(wrong)+rows(['FICTIONAL records-review role']))
        self.assertFalse(extra['coverageHistoryComplete'])

    def test_purpose_route_is_configured_by_source_not_claimed_by_closure(self):
        graph,b=self.graph();nodes=_flatten(graph);_,base,events=fixture(True)
        for number,profile in enumerate(b['allowedSources']):
            other=b['allowedSources'][1-number]['reviewRequirements']['purposeReferences']
            own=profile['reviewRequirements']['purposeReferences']
            for index,role in enumerate(['committee','officer','coordinator','authorisation']):
                event={**events[index],'DecisionReference':own[role]}
                ev=Expressions({'Closure_selected_'+role:[event]}, {
                    'Selected_case_context':{'sourcePins':{'UniqueId':profile['UniqueId']}},
                    'Native_prepared_revision':{'preparedRevision':{'scope':SCOPE}},
                    'Closure_Native_readiness_observation':{'selectedEventUID':'FICTIONAL-ready'},
                    'Completed_candidate_record':{'contract':{'observation':{
                        'selectedEvents':base['selectedEvents'],'purposeReferences':other}}}})
                expression=nodes['Closure_selected_'+role+'_valid']['inputs']
                self.assertTrue(ev.evaluate(expression),role)
                event['DecisionReference']=other[role]
                self.assertFalse(ev.evaluate(expression),role)

    def test_single_opt_in_route_also_uses_its_own_requirements(self):
        c,_,_=fixture(True);b=binding();b['allowedSources']=b['allowedSources'][1:]
        graph=build_runtime_closure_observer(c,b);profile=b['allowedSources'][0]
        receipt,_=coverage(graph,profile,rows(profile['reviewRequirements']['requiredFictionalRoles']))
        self.assertTrue(receipt['coverageHistoryComplete'])

    def test_unknown_source_holds_before_history_read(self):
        graph,_=self.graph();receipt,_=coverage(graph,{'UniqueId':'00000000-0000-4000-8000-000000000099'},[])
        self.assertIsNone(receipt)

    def test_incomplete_or_duplicate_routes_refused(self):
        c,_,_=fixture(True)
        for change in [lambda b:b['allowedSources'][1].pop('reviewRequirements'),
                       lambda b:b['allowedSources'][1].update(UniqueId=b['allowedSources'][0]['UniqueId']),
                       lambda b:b['allowedSources'][1]['reviewRequirements'].update(requiredFictionalRoles=[]),
                       lambda b:b['allowedSources'][1]['reviewRequirements'].update(purposeReferences={})]:
            b=binding();change(b)
            with self.assertRaises(ValueError):build_runtime_closure_observer(c,b)

    def test_legacy_configuration_stays_opt_out_and_full_entry_remains_bounded(self):
        self.assertIsNone(_source_review_requirements(completed_tests.NativeCompletedReviewTests().complete_binding()))
        from test_operator_entry import legacy_fixture
        owner=completed_tests.NativeCompletedReviewTests();legacy=legacy_fixture()
        legacy['properties']['connectionReferences']=owner.reference()['properties']['connectionReferences']
        result=entry_build(legacy,binding())
        geometry=audit_actions(result['properties']['definition'])
        self.assertLessEqual(geometry['actionCount'],500)
        self.assertLessEqual(geometry['maximumActionDepth'],8)
        new=_flatten(result['properties']['definition']['actions']['NextReview_Entry']['actions'])
        writers={name for name,action in new.items() if action.get('type')=='OpenApiConnection'
                 and action['inputs']['parameters']['parameters/method']!='GET'}
        self.assertEqual(writers,{'NextOccurrence_Create_request','NextOccurrence_Next_create_intent',
                                  'NextOccurrence_Create_case','NextOccurrence_Next_create_receipt'})
