import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/lifecycle'))
from build_prepared_consultation_events import build
from build_selected_prepared_context import build as embed,digest
from test_selected_prepared_context import fixture
from test_selected_event_routes import success

URI="_api/web/lists/getbytitle('PPG Consultation and Handoff Events')/items"
ROLE='FICTIONAL content-review role'

def composed(kind):
    event,source=fixture(kind)
    return embed(kind,event,source,digest(source['properties']['definition']))

def branch(flow):return flow['properties']['definition']['actions']['Route_prepared_consultation_event']

class PreparedConsultationEventsTests(unittest.TestCase):
    def test_modes_are_disjoint_and_ownership_graph_is_unchanged(self):
        for kind,field,mode in [('request','text','Consultation request'),('response','text_5','Consultation response')]:
            source=composed(kind);before=copy.deepcopy(source);out=build(kind,source,URI,ROLE)
            self.assertEqual(before,source)
            self.assertEqual(success(source)['Route_ownership_event'],success(out)['Route_ownership_event'])
            route=branch(out)
            self.assertIn("triggerBody()?['"+field+"'],'"+mode+"'",route['expression'])
            self.assertIn("outputs('Native_prepared_revision')?['preparationQualified'],true",route['expression'])
            self.assertEqual(route['runAfter'],{'Route_consultation_prepared_context':['Succeeded']})
            self.assertEqual(route['else']['actions'],{})
            self.assertEqual(out['properties']['state'],'Stopped')

    def test_exact_revision_replay_and_both_metadata_brackets_gate_qualification(self):
        out=build('request',composed('request'),URI,ROLE);work=branch(out)['actions']
        payload=work['Consultation_payload']['inputs']
        self.assertIn("['file']?['UniqueId']",payload['EventUID']);self.assertIn("['file']?['nativeVersion']",payload['EventUID'])
        self.assertEqual(payload['SubjectRole'],ROLE);self.assertEqual(payload['RecordState'],'Pending response')
        self.assertIsNone(payload['ResponseSummary'])
        guard=work['Verify_consultation_before'];apply=guard['actions']
        for label in ('case','draft','receipt','template','source','baseline'):
            self.assertIn('Consultation_'+label+'_before',guard['expression'])
        creator=apply['Ensure_consultation_event']
        self.assertIn("length(body('Find_consultation_event')?['value']),0",creator['expression'])
        self.assertEqual(creator['actions']['Create_consultation_event']['inputs']['parameters']['parameters/uri'],URI)
        verify=apply['Verify_consultation_event']
        for key in payload:
            if key!='OccurredOn':self.assertIn("['"+key+"']",verify['expression'])
        self.assertNotIn("['OccurredOn']",verify['expression'])
        after=verify['actions'];receipt=after['Native_consultation_receipt']['inputs']
        self.assertIn("outputs('Consultation_after_checks')",receipt['qualified'])
        for label in ('case','draft','receipt','template','source','baseline'):
            self.assertIn('Consultation_'+label+'_after',after['Consultation_after_checks']['inputs'])
        self.assertFalse(receipt['progressionGranted']);self.assertFalse(receipt['contentReadinessGranted']);self.assertFalse(receipt['approvalGranted'])
        uncertain=verify['else']['actions']['Held_uncertain_consultation_event']['inputs']
        self.assertIsNone(uncertain['eventWriteCount']);self.assertIsNone(uncertain['consultationRecorded'])

    def test_response_requires_exact_parent_complete_history_and_bounded_inputs(self):
        out=build('response',composed('response'),URI,ROLE);work=branch(out)['actions']
        self.assertIn("'LC-CONSULT-RESP-'",work['Consultation_input_valid']['inputs'])
        self.assertIn("'Responded','Unanswered','Declined','Conditional'",work['Consultation_input_valid']['inputs'])
        self.assertIn('2000',work['Consultation_input_valid']['inputs'])
        self.assertEqual(work['Read_consultation_request']['runAfter'],{'Validate_consultation_response':['Succeeded']})
        payload=work['Consultation_payload']['inputs']
        self.assertIn('255',payload['ConditionsNotes']);self.assertEqual(payload['NextAction'],"@triggerBody()?['text_4']")
        expression=work['Verify_consultation_before']['expression']+' '.join(v['inputs'] for k,v in work.items() if k.startswith('Consultation_before_checks_'))
        self.assertIn('Read_consultation_history',expression);self.assertIn('odata.nextLink',expression)
        self.assertIn("['SupersedesEventUID']",expression)
        for key in ('CaseUID','DocumentReference','ReviewedVersionRef','DocumentSHA256','SubjectRole','FictionalTest'):
            self.assertIn("['"+key+"']",expression)
        after=work['Verify_consultation_before']['actions']['Verify_consultation_event']['actions']
        self.assertIn('Consultation_parent_after',after['Consultation_after_checks']['inputs'])
        self.assertIn('Consultation_history_after',after['Consultation_after_checks']['inputs'])

    def test_coverage_requires_fresh_native_bracket_after_complete_history(self):
        out=build('response',composed('response'),URI,ROLE)
        after=branch(out)['actions']['Verify_consultation_before']['actions']['Verify_consultation_event']['actions']
        gate=after['Check_current_consultation_coverage']
        self.assertEqual(gate['expression'],"@equals(outputs('Consultation_after_checks'),true)")
        self.assertEqual(gate['runAfter'],{'Native_consultation_receipt':['Succeeded']})
        actions=gate['actions'];runtime=actions['Consultation_coverage_Runtime_guard']
        reader=runtime['actions']['Read_current_consultation_coverage']
        self.assertEqual(reader['inputs']['parameters']['parameters/uri'],URI)
        self.assertEqual(reader['inputs']['parameters']['parameters/method'],'GET')
        receipt=actions['Native_consultation_coverage_receipt']['inputs']
        self.assertIn("['coverageHistoryComplete'],true",receipt['technicalCoverageComplete'])
        for label in ('case','draft','receipt','template','source','baseline'):
            self.assertIn('Consultation_'+label+'_coverage',receipt['technicalCoverageComplete'])
        self.assertFalse(receipt['progressionGranted']);self.assertFalse(receipt['contentReadinessAssessed']);self.assertFalse(receipt['policyApproved'])

    def test_append_retries_are_disabled_and_fresh_parent_history_gate_creation(self):
        out=build('response',composed('response'),URI,ROLE)
        posts=[]
        def inspect(value):
            if isinstance(value,dict):
                inputs=value.get('inputs',{})
                if isinstance(inputs,dict) and inputs.get('parameters',{}).get('parameters/method')=='POST':
                    posts.append(inputs)
                for child in value.values():inspect(child)
            elif isinstance(value,list):
                for child in value:inspect(child)
        inspect(out['properties']['definition']['actions'])
        self.assertEqual(len(posts),2)
        for inputs in posts:self.assertEqual(inputs['retryPolicy'],{'type':'none'})
        work=branch(out)['actions'];guard=work['Verify_consultation_before']
        self.assertEqual(work['Consultation_parent_before']['runAfter'],{'Consultation_baseline_before':['Succeeded']})
        self.assertEqual(work['Consultation_history_before']['runAfter'],{'Consultation_parent_before':['Succeeded']})
        checks=[k for k in work if k.startswith('Consultation_before_checks_')]
        self.assertTrue(checks)
        self.assertEqual(work[checks[0]]['runAfter'],{'Consultation_history_before':['Succeeded']})
        self.assertEqual(guard['runAfter'],{checks[-1]:['Succeeded']})
        expression=guard['expression']+' '.join(work[k]['inputs'] for k in checks)
        self.assertTrue(all(len(work[k]['inputs'])<=6000 for k in checks))
        self.assertIn("union(first(body('Consultation_history_before')?['value']),json('{\"odata.id\":null}'))",expression)
        self.assertIn("union(first(body('Read_consultation_history')?['value']),json('{\"odata.id\":null}'))",expression)
        self.assertIn("not(empty(outputs('Consultation_parent_before')?['headers']?['ETag']))",expression)
        for key in work['Consultation_payload']['inputs']:
            if key not in ('ConditionsNotes',):
                self.assertIn("body('Consultation_parent_before')?['"+key+"']",expression)
        after=guard['actions']['Verify_consultation_event']['actions']['Consultation_after_checks']['inputs']
        self.assertIn("outputs('Consultation_parent_after')?['headers']?['ETag'],outputs('Consultation_parent_before')?['headers']?['ETag']",after)
        self.assertIn("union(first(body('Consultation_history_after')?['value']),json('{\"odata.id\":null}'))",after)
        self.assertIn("union(first(body('Read_consultation_event')?['value']),json('{\"odata.id\":null}'))",after)
        self.assertEqual((expression+after).count('union(first('),4)
        self.assertEqual((expression+after).count("json('{\"odata.id\":null}')"),4)
        self.assertNotIn('removeProperty(',expression+after)

    def test_request_response_absence_is_explicit_null_and_answered_finding_stays_strict(self):
        request=branch(build('request',composed('request'),URI,ROLE))['actions']['Consultation_payload']['inputs']
        self.assertIsNone(request['ResponseSummary'])
        work=branch(build('response',composed('response'),URI,ROLE))['actions']
        checks=work['Verify_consultation_before']['expression']+' '.join(v['inputs'] for k,v in work.items() if k.startswith('Consultation_before_checks_'))
        self.assertIn("equals(first(body('Read_consultation_request')?['value'])?['ResponseSummary'],null)",checks)
        self.assertEqual(work['Consultation_payload']['inputs']['ResponseSummary'],"@triggerBody()?['text_2']")
        self.assertIn("not(empty(trim(string(coalesce(triggerBody()?['text_2'],'')))))",work['Consultation_input_valid']['inputs'])

    def test_unapproved_list_or_nonfictional_role_is_refused(self):
        source=composed('request')
        for uri,role in [(URI.replace('Events','Other'),ROLE),(URI,'Actual reviewer')]:
            with self.assertRaises(ValueError):build('request',source,uri,role)
