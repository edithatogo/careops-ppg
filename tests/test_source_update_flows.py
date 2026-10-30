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

    def test_source_profiles_have_disjoint_namespaces_and_no_notifications(self):
        import json
        from pathlib import Path
        profiles=json.loads(Path('config/source-update-channels.json').read_text())['rss']
        namespaces=[]
        for source in profiles:
            flow=build('rss',self.binding(),source=source)
            actions=flow['properties']['definition']['actions']
            namespaces.append(actions['Failure_payload']['inputs']['ChannelKey'])
            self.assertEqual(actions['Collect_source']['actions']['Read_feed']['inputs']['parameters']['feedUrl'],source['feedUrl'])
            self.assertFalse(flow['properties']['flowFailureAlertSubscribed'])
            self.assertEqual(email_actions(flow),[])
        self.assertEqual(len(namespaces),len(set(namespaces)))
        self.assertEqual(namespaces[0],'rss') # existing Commission rows remain addressable

    def test_empty_identity_falls_back_and_deduplication_preserves_changed_items(self):
        import sys
        from pathlib import Path
        for folder in ('scripts','tests','tools/lifecycle'):
            sys.path.insert(0,str(Path(folder).resolve()))
        from test_native_completed_review import Expressions
        work=build('rss',self.binding())['properties']['definition']['actions']['Collect_source']['actions']['Collect']['actions']
        expression=work['Source_id']['inputs']
        for item,expected in [({'id':'','primaryLink':'https://example.invalid/a'},'https://example.invalid/a'),({'id':'guid-1','primaryLink':'https://example.invalid/a'},'guid-1'),({},'')]:
            self.assertEqual(Expressions({},dict(Current_item=item)).evaluate(expression),expected)
        observation={'title':'FICTIONAL original','link':'https://example.invalid/a'}
        match=work['Match_existing']['inputs']['where']
        stored={'Fingerprint':str(observation),'ProcessingState':'Human reviewed'}
        before=copy.deepcopy(stored)
        self.assertTrue(Expressions({},dict(Current_item=stored,Observation=observation)).evaluate(match))
        self.assertFalse(Expressions({},dict(Current_item=stored,Observation={**observation,'title':'FICTIONAL changed'})).evaluate(match))
        self.assertEqual(stored,before)
        complete=work['Require_complete_query']['inputs']['content']['complete']
        self.assertFalse(Expressions({'Read_existing':{'value':[],'odata.nextLink':'https://example.invalid/next'}},{}).evaluate(complete))

    def test_newsletter_dates_and_publisher_links_are_source_specific(self):
        source=dict(key='fictional-news',publisher='Example',name='News',fallbackUrl='https://example.invalid/news',linkDomains=['example.invalid'])
        binding=self.binding();binding['subjectContains']='Example News'
        flow=build('newsletter',binding,source=source)
        actions=flow['properties']['definition']['actions']['Collect_source']['actions']
        work=actions['Collect']['actions']
        self.assertIsNone(work['Observation']['inputs']['publishedAt'])
        self.assertEqual(work['Observation']['inputs']['receivedAt'],"@item()?['receivedDateTime']")
        self.assertIn('https://example.invalid/',work['Email_link_fragments']['inputs']['where'])
        self.assertNotIn('safetyandquality',str(flow))
        self.assertIn("'re:'",actions['Original_issues']['inputs']['where'])
        self.assertIn("'example news'",actions['Original_issues']['inputs']['where'])
        del binding['subjectContains']
        with self.assertRaises(ValueError):build('newsletter',binding,source=source)

    def test_configuration_cannot_inject_odata_or_bind_another_commission_feed(self):
        source=dict(key="bad'key",publisher='Example',name='News',fallbackUrl='https://example.invalid/news',feedUrl='https://example.invalid/feed')
        with self.assertRaises(ValueError):build('rss',self.binding(),source=source)
        source['key']='acsqhc-rss'
        with self.assertRaises(ValueError):build('rss',self.binding(),source=source)

    def test_manual_newsletter_reads_one_original_without_mutating_mail(self):
        b=self.binding()
        with self.assertRaises(ValueError):build('newsletter',b,manual=True)
        b.update(messageId='FICTIONAL/message+id',subjectContains='Example news')
        f=build('newsletter',b,manual=True)
        actions=f['properties']['definition']['actions']['Collect_source']['actions']
        read=actions['Read_existing_message']['inputs']['parameters']
        self.assertEqual(read['Method'],'GET')
        self.assertIn('FICTIONAL%2Fmessage%2Bid?',read['Uri'])
        self.assertIn("['emailAddress']",actions['Original_issues']['inputs']['where'])
        self.assertIn("['content']",actions['Collect']['actions']['Email_link_fragments']['inputs']['from'])
        arrival=build('newsletter',b)['properties']['definition']['actions']['Collect_source']['actions']
        self.assertNotIn("['content']",arrival['Collect']['actions']['Email_link_fragments']['inputs']['from'])
        self.assertEqual(email_actions(f),[])

    def test_manifest_binds_source_without_claiming_native_completion(self):
        from scripts.ppg_source_update_flows import deployment_manifest
        f=build('rss',self.binding())
        m=deployment_manifest(f,source_commit='a'*40)
        self.assertFalse(m['nativeReadbackVerified'])
        self.assertFalse(m['runtimeVerified'])
        changed=copy.deepcopy(f);changed['properties']['definition']['contentVersion']='2.0.0.0'
        self.assertNotEqual(m['definitionSHA256'],deployment_manifest(changed,source_commit='a'*40)['definitionSHA256'])
        with self.assertRaises(ValueError):deployment_manifest(f,source_commit='main')

    def test_internal_source_is_bounded_read_only_and_retains_version(self):
        b=self.binding();b.update(sourceSite='https://example.sharepoint.com/sites/internal',sourceListId=str(UUID(int=2,version=4)),sourceTitle='Patient safety notice')
        source=dict(key='fictional-internal-notices',publisher='Example',name='Internal notices',fallbackUrl='https://example.sharepoint.com/sites/internal/Lists/Notices/DispForm.aspx')
        f=build('sharepoint',b,source=source)
        actions=f['properties']['definition']['actions']['Collect_source']['actions']
        read=actions['Read_source']['inputs']['parameters']
        self.assertEqual(read['parameters/method'],'GET')
        self.assertEqual(read['dataset'],b['sourceSite'])
        self.assertIn('Title%20eq%20',read['parameters/uri'])
        self.assertIn('Require_complete_source',actions)
        observation=actions['Collect']['actions']['Observation']['inputs']
        self.assertEqual(observation['sourceVersion'],"@item()?['OData__UIVersionString']")
        self.assertEqual(email_actions(f),[])
        b['sourceSite']='https://contoso.sharepoint.com/sites/internal'
        with self.assertRaises(ValueError):build('sharepoint',b,source=source)
