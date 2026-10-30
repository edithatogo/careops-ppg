# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from uuid import UUID
from scripts.ppg_source_update_flows import build, SP, RSS, MAIL
from scripts.check_email_safety import email_actions


class SourceUpdatesTests(unittest.TestCase):
    def binding(self):
        return dict(site='https://example.sharepoint.com/sites/pilot',listId=str(UUID(int=1,version=4)),sharepoint=dict(id=SP,source='Embedded',connectionName='fixture-sp'),rss=dict(id=RSS,source='Embedded',connectionName='fixture-rss'),outlook=dict(id=MAIL,source='Embedded',connectionName='fixture-mail'),folderId='fictional-folder',senders=['newsletter@example.invalid'])

    def test_daily_rss_has_serial_idempotent_writer_and_no_email(self):
        binding=self.binding();before=copy.deepcopy(binding);flow=build('rss',binding)
        trigger=flow['properties']['definition']['triggers']['Scheduled_collection']
        self.assertEqual(trigger['recurrence']['schedule'],dict(hours=[7],minutes=[0]))
        self.assertEqual(trigger['recurrence']['timeZone'],'E. Australia Standard Time')
        self.assertEqual(trigger['runtimeConfiguration']['concurrency']['runs'],1)
        work=flow['properties']['definition']['actions']['Collect_source']['actions']['Collect']
        self.assertEqual(work['runtimeConfiguration']['concurrency']['repetitions'],1)
        self.assertIn('Match_existing',work['actions'])
        write=work['actions']['Create_if_changed']['actions']['Persist_lead']
        self.assertEqual(write['inputs']['retryPolicy'],dict(type='none'))
        self.assertEqual(write['inputs']['parameters']['parameters/body'],"@string(outputs('Lead_payload'))")
        self.assertIn("lists(guid''",work['actions']['Read_existing']['inputs']['parameters']['parameters/uri'])
        self.assertEqual(email_actions(flow),[])
        self.assertEqual(binding,before)

    def test_mail_requires_verified_binding_and_leaves_message_untouched(self):
        b=self.binding();flow=build('newsletter',b)
        trigger=flow['properties']['definition']['triggers']['Newsletter_arrival']
        self.assertEqual(trigger['inputs']['parameters']['folderPath'],'fictional-folder')
        self.assertEqual(trigger['inputs']['parameters']['from'],'newsletter@example.invalid')
        self.assertFalse(trigger['inputs']['parameters']['includeAttachments'])
        self.assertEqual(email_actions(flow),[])
        b['senders']=[]
        with self.assertRaises(ValueError):build('newsletter',b)

    def test_meteor_is_stopped_and_cannot_call_before_access_is_qualified(self):
        f=build('meteor',dict(indicatorIds=['817898']))
        self.assertEqual(f['properties']['state'],'Stopped')
        actions=f['properties']['definition']['actions']
        self.assertEqual(actions['Access_dependencies']['type'],'Terminate')
        self.assertEqual(actions['Access_dependencies']['inputs']['runStatus'],'Failed')
        self.assertNotIn('Http',[a['type']for a in actions.values()])
        self.assertIn('/Indicators/817898',actions['Selected_endpoints']['inputs']['items'][0])

    def test_failure_is_recorded_and_missing_identity_fails_before_write(self):
        a=build('rss',self.binding())['properties']['definition']['actions']
        self.assertEqual(a['Failure_payload']['runAfter'],{'Collect_source':['Failed','TimedOut']})
        self.assertEqual(a['Failure_payload']['inputs']['ProcessingState'],'Failed')
        schema=a['Collect_source']['actions']['Collect']['actions']['Require_identity']['inputs']['schema']
        self.assertEqual(schema['properties']['id']['minLength'],1)
        self.assertEqual(schema['properties']['id']['maxLength'],255)

    def test_pending_newsletter_cannot_collect_without_verified_sender(self):
        b=self.binding();b['senders']=[]
        f=build('newsletter',b,pending_sender=True)
        self.assertEqual(f['properties']['state'],'Stopped')
        actions=f['properties']['definition']['actions']
        self.assertEqual(list(actions),['Verified_sender_required'])
        self.assertEqual(actions['Verified_sender_required']['inputs']['runStatus'],'Failed')
        self.assertNotIn('from',f['properties']['definition']['triggers']['Newsletter_arrival']['inputs']['parameters'])
        with self.assertRaises(ValueError):build('rss',b,pending_sender=True)

    def test_trigger_and_action_names_are_globally_unique_ignoring_case(self):
        for channel,binding in [('rss',self.binding()),('newsletter',self.binding()),('meteor',dict(indicatorIds=['817898']))]:
            definition=build(channel,binding)['properties']['definition']
            names=[k.lower()for k in definition['triggers']]
            def visit(node):
                if isinstance(node,dict):
                    for key,value in node.items():
                        if key=='actions':names.extend(k.lower()for k in value)
                        visit(value)
                elif isinstance(node,list):
                    for value in node:visit(value)
            visit(definition)
            self.assertEqual(len(names),len(set(names)),channel)
