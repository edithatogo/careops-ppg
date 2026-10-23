"""Locator-only producer composition against the actual emitted context adapter."""
import copy
import unittest
from test_multisource_case_context import candidate, COLLECTION
from build_operator_entry import with_case_work_handoff, _flatten
from test_operator_entry import handoff_fixture, target_digest, entry_input
from test_prepared_closure_check import Expressions


def fixture():
    producer,identity=handoff_fixture();target,profiles=candidate()
    target['name']=identity['name'];target['properties']['environment']=identity['properties']['environment']
    definition=target['properties']['definition'];definition['actions']['Validate_case_operation']={
        'type':'If','expression':"@equals(triggerBody()?['text'],'Check context')",'runAfter':{},'actions':{}}
    nodes=_flatten(producer['properties']['definition']['actions'])
    nodes['Create_case']['inputs']['parameters']['parameters/uri']=COLLECTION
    nodes['Request']['inputs'].update({key:profiles[0]['sha256' if key=='DocumentSHA256' else key]
        for key in ('DocumentUID','DocumentReference','ReviewedVersionRef','DocumentSHA256')})
    return producer,target,profiles


class MultisourceOperatorHandoffTests(unittest.TestCase):
    def test_both_exact_source_receipts_admit_locator_but_mixed_or_unknown_scopes_hold(self):
        producer,target,profiles=fixture();before=copy.deepcopy((producer,target))
        out=with_case_work_handoff(producer,target,target_digest(target))
        self.assertEqual((producer,target),before)
        nodes=_flatten(out['properties']['definition']['actions']);body=entry_input()
        for profile in profiles:
            scope={key:profile['sha256' if key=='DocumentSHA256' else key]
                for key in ('DocumentUID','DocumentReference','ReviewedVersionRef','DocumentSHA256')}
            for changed in (None,*scope,'qualified','reconcileBeforeRetry','caseItemId'):
                receipt={'CaseUID':'LC-FICTIONAL-OP-'+body['text_1'],'caseItemId':12,
                    'requestReference':body['text'],'occurrenceReference':body['text_1'],
                    'realPolicyEffects':False,'ownershipAccepted':False,'qualified':True,
                    'reconcileBeforeRetry':False,'retainedReceipt':{'request':copy.deepcopy(scope)}}
                if changed in scope:receipt['retainedReceipt']['request'][changed]='unknown'
                elif changed=='qualified':receipt[changed]=False
                elif changed=='reconcileBeforeRetry':receipt[changed]=True
                elif changed=='caseItemId':receipt[changed]=0
                ev=Expressions(outputs={'Test_trigger':body,'Operator_handoff_receipt':receipt})
                with self.subTest(source=profile['DocumentUID'],changed=changed):
                    self.assertEqual(ev.evaluate(nodes['Operator_handoff_ready']['expression']),changed is None)
        added={key:value for key,value in out['properties']['definition']['actions'].items()
            if key not in producer['properties']['definition']['actions']}
        self.assertTrue(all(a['type'] in ('Compose','If') for a in _flatten(added).values()))
        locator=nodes['Operator_case_work_handoff']['inputs']
        self.assertTrue(locator['locatorOnly']);self.assertFalse(locator['flowInvoked'])
        self.assertFalse(locator['ordinaryUserAccessQualified'])
        self.assertEqual(locator['formValues']['text'],'Check context')
        self.assertNotIn('entryUrl',nodes['Operator_handoff_held']['inputs'])

    def test_changed_consumer_guards_are_rejected_even_with_refreshed_definition_pin(self):
        for changed in ('selection','operation','final','source_uri','source_method','source_header','refusal','context','unsupported_seed'):
            producer,target,profiles=fixture();nodes=_flatten(target['properties']['definition']['actions'])
            if changed=='selection':nodes['SourceProfiles_matches']['inputs']['where']='@true'
            elif changed=='operation':nodes['SourceProfiles_operation']['expression']='@true'
            elif changed=='final':nodes['Verify_source_and_case']['expression']='@true'
            elif changed=='source_uri':nodes['Read_source_before']['inputs']['parameters']['parameters/uri']='_api/web/other'
            elif changed=='source_method':nodes['Read_source_before']['inputs']['parameters']['parameters/method']='POST'
            elif changed=='source_header':nodes['Read_source_before']['inputs']['parameters']['parameters/headers']['X-HTTP-Method']='MERGE'
            elif changed=='refusal':nodes['SourceProfiles_operation_refused']['type']='Compose'
            elif changed=='context':nodes['Selected_case_context']['inputs']['sourcePins']['UniqueId']='caller'
            else:_flatten(producer['properties']['definition']['actions'])['Request']['inputs']['DocumentUID']='FICTIONAL-OTHER'
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                with_case_work_handoff(producer,target,target_digest(target))

    def test_stale_target_digest_refuses_and_no_target_is_modified(self):
        producer,target,_=fixture();pin=target_digest(target)
        _flatten(target['properties']['definition']['actions'])['SourceProfiles_configured']['inputs'][1]['ETag']='"2"'
        with self.assertRaisesRegex(ValueError,'changed since inspection'):
            with_case_work_handoff(producer,target,pin)


if __name__=='__main__':unittest.main()
