"""Focused local checks for the composed prepared verification consumer."""
import copy
import re
import unittest
from unittest.mock import patch
from test_prepared_implementation import fixture as implementation_fixture, frame_evaluator
from build_prepared_implementation import build as implementation_build, digest
from build_prepared_verification import build
from test_prepared_binary_publication import flatten
from test_prepared_closure_check import Expressions


def fixture():
    impl = implementation_build(*implementation_fixture())
    target = implementation_fixture()[1]
    parent = {k: 'FICTIONAL-' + k for k in ['CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256',
        'ParentEventUID', 'ReadinessEventUID', 'PublicationURL', 'PublishedVersionRef']}
    parent.update(EventUID='LC04-IMPL-PREPARED-FIXTURE', Stage='Implementation', RecordState='Recorded',
        FictionalTest=True, ConditionsState='None recorded', SupersedesEventUID=None,
        ImplementationActions="FICTIONAL checked operator's access", EvidenceReference='fictional://implementation',
        NextAction='FICTIONAL verify', OccurredOn='2026-10-18T12:00:00Z', GUID='FICTIONAL-guid', Id=1, **{'odata.etag':'"1"'})
    return impl, target, {'qualificationOnly':True, 'approvedImplementationDefinitionSHA256':digest(impl['properties']['definition']),
        'approvedTargetDefinitionSHA256':digest(target['properties']['definition']), 'retainedImplementation':parent}


def graph(): return build(*fixture())['properties']['definition']['actions']


class PreparedVerificationTests(unittest.TestCase):
    def test_native_text255_method_limit_rejects_overflow_without_truncation(self):
        a = graph()
        expression = a['Validate_verification_input']['expression']
        check = "@lessOrEquals(length(string(triggerBody()?['text_3'])),255)"
        self.assertIn(check[1:], expression)
        for length, accepted in [(255, True), (256, False), (356, False)]:
            text = 'FICTIONAL ' + 'x' * (length - 10)
            ev = Expressions(outputs={'Test_trigger': {'text_3': text}})
            self.assertEqual(ev.evaluate(check), accepted)
            self.assertEqual(ev.evaluate(a['Verification_payload']['inputs']['VerificationMethod']), text)
        self.assertEqual(a['Verification_payload']['inputs']['NextAction'], "@triggerBody()?['text_5']")

    def test_first_timestamp_matches_native_seconds_and_replay_keeps_original(self):
        expression = graph()['Verification_payload']['inputs']['OccurredOn']
        for clock in ['2026-10-17T22:30:49.6799185Z', '2026-10-17T22:30:49.9999999Z']:
            with patch('test_prepared_closure_check.NOW', clock):
                self.assertEqual(Expressions({'Find_verification': []}).evaluate(expression),
                                 '2026-10-17T22:30:49Z')
                for original in ['2026-10-16T12:00:00Z', '2026-10-16T12:00:00.123Z']:
                    self.assertEqual(Expressions({'Find_verification': [
                        {'OccurredOn': original}]}).evaluate(expression), original)

    def test_immutable_binding_stopped_single_writer_and_resolved_references(self):
        args=fixture(); before=copy.deepcopy(args); result=build(*args); self.assertEqual(args,before)
        self.assertEqual(result['properties']['state'],'Stopped'); a=result['properties']['definition']['actions']; flat=flatten(a)
        writers={k:v for k,v in flat.items() if v['type']=='OpenApiConnection' and v['inputs']['parameters']['parameters/method']!='GET'}
        self.assertEqual(set(writers),{'Create_verification'}); self.assertEqual(writers['Create_verification']['inputs']['retryPolicy'],{'type':'none'})
        refs=set(re.findall(r"(?:body|outputs|actions)\('([^']+)'\)",str(a))); self.assertTrue(refs<=flat.keys(),refs-flat.keys())
        self.assertLess(max(len(v['expression']) for v in flat.values() if isinstance(v.get('expression'),str)),8192)
        for key in ['approvedImplementationDefinitionSHA256','approvedTargetDefinitionSHA256']:
            bad=copy.deepcopy(args);bad[2][key]='0'*64
            with self.assertRaises(ValueError):build(*bad)

    def test_action_renaming_preserves_retained_human_text(self):
        args=fixture();parent=args[2]['retainedImplementation']
        parent['ImplementationActions']="FICTIONAL inspect Read_issued and body('Read_issued')"
        a=build(*args)['properties']['definition']['actions']
        self.assertEqual(a['Retained_implementation']['inputs']['ImplementationActions'],parent['ImplementationActions'])
        self.assertIn("inspect Read_issued and body(''Read_issued'')",a['Implementation_payload']['inputs']['ImplementationActions'])

    def test_adverse_outcomes_keep_open_conditions_and_exact_entered_finding(self):
        payload=graph()['Verification_payload']['inputs']
        for outcome,condition in [('Verified (recorded)','None recorded'),('Failed','Open'),('Inconclusive','Open')]:
            ev=Expressions(outputs={'Test_trigger':{'text_2':outcome,'text_3':'FICTIONAL unresolved finding'}})
            self.assertEqual(ev.evaluate(payload['ConditionsState']),condition)
            notes=ev.evaluate(payload['ConditionsNotes'])
            if condition=='Open':self.assertEqual(notes,'FICTIONAL unresolved finding')
            else:self.assertIn('no real effectiveness or closure',notes)

    def test_full_proof_metadata_equality_uses_exact_same_request_projection(self):
        a=graph();after='Verification_after_Implementation_after_proof'
        self.assertNotEqual(a['Implementation_after_proof']['inputs'],a['Read_binary_proof_before']['inputs'])
        self.assertEqual(a[after]['inputs'],a['Read_binary_proof_before']['inputs'])
        self.assertEqual(a[after]['runAfter'],{'Verification_after_Implementation_after_issued':['Succeeded']})
        self.assertIn('$select=UniqueId,ETag,Length,ServerRelativeUrl',a[after]['inputs']['parameters']['parameters/uri'])

    def test_evidence_reference_must_equal_actual_retained_publication_proof(self):
        expression=graph()['Verify_verification_identity']['expression']
        bodies={'Find_verification':[],'Find_verification_corrections':[]}
        output={'Native_implementation_receipt':{'publication':{'EvidenceReference':'https://example.invalid/retained-proof.json'}},
                'Test_trigger':{'text_4':'https://example.invalid/retained-proof.json'}}
        self.assertTrue(Expressions(bodies,output).evaluate(expression))
        for reference in ['fictional://unbound-proof','https://example.invalid/other-proof.json']:
            changed=copy.deepcopy(output);changed['Test_trigger']['text_4']=reference
            self.assertFalse(Expressions(bodies,changed).evaluate(expression))
        changed=copy.deepcopy(output);changed['Native_implementation_receipt']['publication']['EvidenceReference']=''
        changed['Test_trigger']['text_4']=''
        self.assertFalse(Expressions(bodies,changed).evaluate(expression))

    def test_missing_corrected_open_or_nonfictional_parent_refused(self):
        for key,value in [('FictionalTest',False),('ConditionsState','Open'),('SupersedesEventUID','OTHER'),('odata.etag','*'),('GUID',''),('Id',0)]:
            args=fixture();args[2]['retainedImplementation'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):build(*args)

    def test_upstream_trust_gate_and_complete_after_checks_without_parent_creation(self):
        a=graph()
        self.assertEqual(a['Verify_record_producer_trust']['expression'],'@and(false)')
        self.assertNotIn('Verification_after_Verify_record_producer_trust',a)
        self.assertEqual(a['Ensure_implementation']['type'],'Compose')
        self.assertNotIn('Verification_after_Ensure_implementation',a)
        self.assertIn('Verify_retained_implementation',a['Ensure_implementation']['runAfter'])
        checks=[k for k in a if k.startswith('Verification_after_Implementation_after_frame_check_')]
        self.assertTrue(checks)
        for name in checks:self.assertIn("outputs('"+name+"'),true",a['Verify_verification_after']['expression'])
        self.assertIn("body('Verification_after_Implementation_after_proof')",a['Verify_verification_after']['expression'])

    def test_full_precondition_chain_fits_without_duplicating_initial_graph(self):
        args=fixture();source=args[0]['properties']['definition']['actions'];previous='Verify_implementation_after'
        for index in range(42):
            name='Additional_case_guard_'+str(index)
            source[name]={'type':'If','expression':"@not(empty(outputs('Native_prepared_revision')?['preparedRevision']?['scope']?['CaseUID']))",
                          'actions':{},'else':{'actions':{'Stop_case_guard_'+str(index):{'type':'Terminate','inputs':{'runStatus':'Failed'}}}},
                          'runAfter':{previous:['Succeeded']}}
            previous=name
        source['Native_implementation_receipt']['runAfter']={previous:['Succeeded']}
        args[2]['approvedImplementationDefinitionSHA256']=digest(args[0]['properties']['definition'])
        self.assertEqual(len(flatten(source)),291)
        a=build(*args)['properties']['definition']['actions'];flat=flatten(a)
        self.assertLessEqual(len(flat),500)
        for index in range(42):
            name='Additional_case_guard_'+str(index)
            self.assertEqual(a[name],source[name])
            self.assertNotIn('Verification_after_'+name,a)
        self.assertEqual(a['Native_implementation_receipt']['runAfter'],{previous:['Succeeded']})
        self.assertIn('Native_implementation_receipt',a['Find_verification']['runAfter'])

    def test_reused_complete_after_frame_detects_source_proof_and_history_drift(self):
        a=graph();expression=a['Verification_after_Implementation_after_frame_check_0']['inputs']
        original=frame_evaluator()
        bodies={('Verification_after_'+k if k.startswith('Implementation_after_') else k):v for k,v in original.bodies.items()}
        outputs={('Verification_after_'+k if k.startswith('Implementation_after_') else k):v for k,v in original.outputs.items()}
        self.assertTrue(Expressions(bodies,outputs).evaluate(expression))
        for name in ['Verification_after_Implementation_after_issued','Verification_after_Implementation_after_proof',
                     'Verification_after_Implementation_after_Purpose_draft_before']:
            changed=copy.deepcopy(bodies);changed[name]['ETag']='"CHANGED"'
            self.assertFalse(Expressions(changed,outputs).evaluate(expression))
        changed=copy.deepcopy(outputs);changed['Verification_after_Implementation_after_Purpose_before_history_consistent']=False
        self.assertFalse(Expressions(bodies,changed).evaluate(expression))
        for kind in ['readiness','consultation']:
            changed=copy.deepcopy(bodies);name='Verification_after_Implementation_after_Purpose_'+kind+'_before'
            changed[name]['value']=[{'EventUID':'AFTER-ONLY-CHANGE'}];changed[name+'_stable']=[{'EventUID':'AFTER-ONLY-CHANGE','odata.id':None}]
            self.assertFalse(Expressions(changed,outputs).evaluate(expression))

    def test_exact_retained_parent_fullrow_and_missing_parent_hold(self):
        a=graph();p=fixture()[2]['retainedImplementation'];out={'Retained_implementation':{**p,'odata.id':None}}
        expression=a['Verify_retained_implementation']['expression']
        self.assertTrue(Expressions({'Find_implementation':[p]},out).evaluate(expression))
        for rows in [[],[p,p],[{**p,'odata.etag':'"2"'}],[{**p,'ImplementationActions':'CHANGED'}]]:
            self.assertFalse(Expressions({'Find_implementation':rows},out).evaluate(expression))

    def test_payload_scope_parent_and_explicit_outcome_replay_chronology(self):
        a=graph();p=fixture()[2]['retainedImplementation'];payload={k:'FIXTURE-'+k for k in a['Verification_payload']['inputs']}
        payload['OccurredOn']='2026-10-19T12:00:00Z'; row={**payload,'Id':2,'GUID':'FICTIONAL-row','odata.etag':'"1"'}
        bodies={'Find_verification':[row]};out={'Verification_payload':payload,'Retained_implementation':p}
        expression=a['Verify_verification_replay']['expression'];self.assertTrue(Expressions(bodies,out).evaluate(expression))
        for key,value in [('VerificationResult','Failed'),('VerificationMethod','CHANGED'),('ParentEventUID','OTHER'),('OccurredOn','2026-10-17T12:00:00Z'),('odata.etag','*')]:
            changed=copy.deepcopy(bodies);changed['Find_verification'][0][key]=value
            self.assertFalse(Expressions(changed,out).evaluate(expression))
        self.assertIn("'Verified (recorded)','Failed','Inconclusive'",a['Validate_verification_input']['expression'])
        self.assertEqual(a['Verification_payload']['inputs']['ParentEventUID'],p['EventUID'])

    def test_actual_final_gate_rejects_metadata_drift_pagination_and_changed_parent(self):
        a=graph();p=fixture()[2]['retainedImplementation']
        payload={k:'FIXTURE-'+k for k in a['Verification_payload']['inputs']};payload['OccurredOn']='2026-10-19T12:00:00Z'
        row={**payload,'Id':2,'GUID':'FICTIONAL-row','odata.etag':'"1"'}
        bodies={'Read_verification':[row],'Read_verification_corrections':[], 'Find_verification':[],
                'Verification_others_before_stable':[copy.deepcopy(p)], 'Verification_others_after_stable':[copy.deepcopy(p)],
                'Verification_parent_after':[p], 'Verification_parent_corrections_after':[],
                'Verification_after_Implementation_after_Purpose_before_assurance':{'value':[p,row]}}
        pairs=[('Read_issued','Implementation_after_issued'),('Read_binary_proof_before','Implementation_after_proof')]
        pairs += [('Before_event_Purpose_'+kind+'_before','Implementation_after_Purpose_'+kind+'_before')
                  for kind in ['draft','receipt','template','source','baseline','case']]
        for before_name,after_name in pairs:
            bodies[before_name]={'ETag':'"1"','UniqueId':before_name}
            bodies['Verification_after_'+after_name]=copy.deepcopy(bodies[before_name])
        proof={'UniqueId':'FICTIONAL-proof','ETag':'"1"','Length':'3902','ServerRelativeUrl':'/site/PPG-proof.json','odata.type':'SP.File','odata.id':'BEFORE-TRANSPORT-ID'}
        bodies['Read_binary_proof_before']=proof
        bodies['Verification_after_Implementation_after_proof']={**proof,'odata.id':'AFTER-TRANSPORT-ID'}
        out={'Verification_payload':payload,'Retained_implementation':{**p,'odata.id':None}}
        out.update({k:True for k in a if k.startswith('Verification_after_Implementation_after_frame_check_')})
        expression=a['Verify_verification_after']['expression']
        self.assertTrue(Expressions(bodies,out).evaluate(expression))
        for name,key,value in [('Verification_after_Implementation_after_issued','ETag','"2"'),
                               ('Verification_after_Implementation_after_proof','Length','9999'),
                               ('Verification_after_Implementation_after_proof','ServerRelativeUrl','/site/OTHER-proof.json'),
                               ('Verification_after_Implementation_after_Purpose_case_before','ETag','"2"'),
                               *[('Verification_after_Implementation_after_Purpose_before_assurance',marker,'MORE')
                                 for marker in ('nextLink','@nextLink','odata.nextLink','@odata.nextLink')]]:
            changed=copy.deepcopy(bodies);changed[name][key]=value
            self.assertFalse(Expressions(changed,out).evaluate(expression))
        changed=copy.deepcopy(bodies);changed['Verification_others_after_stable'][0]['NextAction']='CHANGED'
        self.assertFalse(Expressions(changed,out).evaluate(expression))
        changed=copy.deepcopy(bodies);changed['Verification_parent_after']=[{**p,'odata.etag':'\"2\"'}]
        self.assertFalse(Expressions(changed,out).evaluate(expression))
        changed=copy.deepcopy(bodies);changed['Verification_parent_corrections_after']=[{}]
        self.assertFalse(Expressions(changed,out).evaluate(expression))

    def test_complete_history_identity_corrections_and_uncertain_effects(self):
        a=graph();expression=a['Verify_verification_identity']['expression']
        proof_out={'Native_implementation_receipt':{'publication':{'EvidenceReference':'https://example.invalid/proof.json'}},
                   'Test_trigger':{'text_4':'https://example.invalid/proof.json'}}
        self.assertTrue(Expressions({'Find_verification':[],'Find_verification_corrections':[]},proof_out).evaluate(expression))
        for bodies in [{'Find_verification':[{},{}],'Find_verification_corrections':[]},{'Find_verification':[],'Find_verification_corrections':[{}]}]:
            self.assertFalse(Expressions(bodies,proof_out).evaluate(expression))
        final=a['Verify_verification_after'];self.assertIn('odata.nextLink',final['expression']);self.assertIn('Verification_others_before_stable',final['expression'])
        held=final['else']['actions']['Held_verification_after']['inputs'];self.assertIsNone(held['verificationCreatedCount']);self.assertTrue(held['reconcileBeforeRetry'])
        self.assertFalse(a['Native_verification_receipt']['inputs']['completionGranted']);self.assertFalse(a['Native_verification_receipt']['inputs']['progressionGranted'])

if __name__=='__main__':unittest.main()
