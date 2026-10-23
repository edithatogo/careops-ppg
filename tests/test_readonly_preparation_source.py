"""Qualify the emitted additional-source preparation route without adding writes."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/lifecycle'))
from test_multisource_case_context import fixture as context_fixture
from test_prepared_closure_check import Expressions
from build_prepared_revision_check import build_actions as prepared_reader
from build_prepared_readiness_check import build_actions as readiness_reader
from build_multisource_case_context import (with_eligible_sources, with_readonly_preparation_source,
    with_ownership_projection_source, digest, _check_context_shape, _projection_source_uri)
from build_operator_entry import _flatten
from build_selected_event_routes import audit_actions


def fixture(required_roles=None):
    flow,profiles=context_fixture()
    a=flow['properties']['definition']['actions']
    a['Route_preparation_check']={'type':'If','expression':"@contains(createArray('Check preparation','Check readiness'),triggerBody()?['text'])",'runAfter':{},
        'actions':prepared_reader(flow,{'artifactFolderRelative':'/site/evidence','caseEvidenceFieldType':'Note',
            'templateFileUniqueId':'00000000-0000-4000-8000-000000000011'},'Verified_preparation_ownership')}
    a['Route_readiness_check']={'type':'If','expression':"@equals(triggerBody()?['text'],'Check readiness')",'runAfter':{},
        'actions':readiness_reader(flow,{'readinessCollectionUri':"_api/web/lists(guid'00000000-0000-4000-8000-000000000009')/items",
            'consultationCollectionUri':"_api/web/lists/getbytitle('PPG Consultation and Handoff Events')/items",'requiredFictionalRoles':required_roles or ['FICTIONAL test role']})}
    return with_eligible_sources(flow,profiles,digest(flow['properties']['definition'])),profiles


class ReadonlyPreparationSourceTests(unittest.TestCase):
    def test_projection_can_follow_preparation_without_replacing_its_profile(self):
        original,profiles=fixture()
        source=profiles[1]['UniqueId']
        prepare=lambda flow:with_readonly_preparation_source(flow,source,
            digest(flow['properties']['definition']),
            artifact_folder_relative='/site/qualification-drafts',
            required_fictional_roles=['FICTIONAL content-review role'])
        project=lambda flow:with_ownership_projection_source(flow,source,
            digest(flow['properties']['definition']))
        prepared=prepare(original);before=copy.deepcopy(prepared)
        actual=project(prepared)
        self.assertEqual(prepared,before)
        self.assertEqual(actual,prepare(project(original)))
        self.assertEqual(_check_context_shape(actual['properties']['definition']),profiles)
        nodes=_flatten(actual['properties']['definition']['actions'])
        guard=nodes['SourceProfiles_operation']['expression'].replace(
            "triggerBody()?['text']","outputs('Test_operation')")
        for operation in ('Check context','Project ownership','Check preparation','Check readiness','Close review'):
            ev=Expressions(outputs={'Test_operation':operation,'SourceProfiles_selected':profiles[1]})
            self.assertEqual(ev.evaluate(guard),operation!='Close review')
        for source_row in (profiles[1],{**profiles[1],'UniqueId':'unknown'}):
            ev=Expressions(outputs={'Test_operation':'Project ownership','SourceProfiles_selected':source_row})
            self.assertEqual(ev.evaluate(guard),source_row==profiles[1])
        self.assertEqual(audit_actions(actual['properties']['definition']),
                         audit_actions(prepared['properties']['definition']))

    def test_each_source_retains_its_explicit_role_and_wrong_role_is_a_problem(self):
        flow,profiles=fixture();out=with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']),
            required_fictional_roles=['FICTIONAL content-review role'])
        nodes=_flatten(out['properties']['definition']['actions'])
        for index,profile in enumerate(profiles):
            expected='FICTIONAL test role'if index==0 else 'FICTIONAL content-review role'
            ev=Expressions(outputs={'SourceProfiles_selected':profile})
            result=nodes['Ready_consultation_Receipt']['inputs']['requiredRoleResults'][0]['SubjectRole']
            self.assertEqual(ev.evaluate(result),expected)
            for role in ('FICTIONAL test role','FICTIONAL content-review role'):
                ev.current={'SubjectRole':role,'FictionalTest':True,'SupersedesEventUID':None,
                    'RecordState':'Responded','ConditionsState':'None recorded','EventUID':'response'}
                self.assertEqual(ev.evaluate(nodes['Ready_consultation_R0_Rows']['inputs']['where']),role==expected)
                self.assertEqual(ev.evaluate(nodes['Ready_consultation_Problems']['inputs']['where']),role!=expected)
        original=_flatten(flow['properties']['definition']['actions'])
        for name,action in original.items():
            if action.get('type')=='OpenApiConnection':
                expected=copy.deepcopy(action)
                if name=='Read_prepared_source_final':expected['inputs']['parameters']['parameters/uri']=_projection_source_uri()
                self.assertEqual(nodes[name],expected)
        self.assertEqual(_check_context_shape(out['properties']['definition']),profiles)

    def test_role_plan_rejects_empty_duplicate_real_role_cardinality_and_guard_drift(self):
        for roles in ([],['Real reviewer'],['FICTIONAL one','FICTIONAL two'],['FICTIONAL one','FICTIONAL one']):
            flow,profiles=fixture()
            with self.subTest(roles=roles),self.assertRaises(ValueError):
                with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']),required_fictional_roles=roles)
        flow,profiles=fixture();out=with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']),required_fictional_roles=['FICTIONAL content-review role'])
        nodes=_flatten(out['properties']['definition']['actions']);nodes['Ready_consultation_R0_Rows']['inputs']['where']='@true'
        with self.assertRaises(ValueError):_check_context_shape(out['properties']['definition'])
        flow,profiles=fixture(['FICTIONAL first','FICTIONAL second'])
        with self.assertRaises(ValueError):
            with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']),required_fictional_roles=['FICTIONAL duplicate','FICTIONAL duplicate'])

    def test_source_specific_folder_keeps_original_scope_and_pairs_receipt_lookup(self):
        flow,profiles=fixture();out=with_readonly_preparation_source(flow,profiles[1]['UniqueId'],
            digest(flow['properties']['definition']),artifact_folder_relative='/site/qualification-drafts')
        n=_flatten(out['properties']['definition']['actions'])
        for index,profile in enumerate(profiles):
            folder='/site/evidence' if index==0 else '/site/qualification-drafts'
            for selected in ('/site/evidence','/site/qualification-drafts','/site/unreviewed'):
                bodies={'Read_prepared_case':{'CaseUID':'LC-FICTIONAL-OP-TEST'},
                    'Read_prepared_file_before':{'UniqueId':profiles[0]['UniqueId'],'UIVersionLabel':'2.0'}}
                outputs={'SourceProfiles_selected':profile,'Prepared_document_reference':'https://example.invalid'+selected+'/draft.docx',
                    'Selected_case_context':{'CaseUID':'LC-FICTIONAL-OP-TEST','caseETag':'token'},
                    'Read_prepared_case':{'headers':{'ETag':'token'}}}
                ev=Expressions(bodies,outputs)
                self.assertEqual(ev.evaluate(n['Verify_prepared_selection']['expression']),selected==folder)
                uri=ev.evaluate(n['Find_prepared_receipt']['inputs']['parameters']['parameters/uri'])
                self.assertEqual(uri,"_api/web/GetFolderByServerRelativePath(decodedurl='"+folder+"')/Files?$filter=Name eq 'PPG-prepared-"+profiles[0]['UniqueId']+"-v2.0.json'&$select=Name,UniqueId,ETag")
                reference=ev.evaluate(n['Native_prepared_revision']['inputs']['preparedRevision']['qualificationReceipt']['DocumentReference'])
                self.assertEqual(reference,'https://example.invalid'+folder+'/PPG-prepared-'+profiles[0]['UniqueId']+'-v2.0.json')
        self.assertEqual(_check_context_shape(out['properties']['definition']),profiles)

    def test_folder_binding_refuses_foreign_unsafe_and_changed_selection_guards(self):
        for folder in ('/foreign/drafts','/site/../drafts','/site/drafts?x=1','/site/drafts%20x','/site/evidence','/site/drafts/'):
            flow,profiles=fixture()
            with self.subTest(folder=folder),self.assertRaises(ValueError):
                with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']),artifact_folder_relative=folder)
        for name in ('Verify_prepared_selection','Find_prepared_receipt','Native_prepared_revision'):
            flow,profiles=fixture();out=with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']),artifact_folder_relative='/site/qualification-drafts')
            n=_flatten(out['properties']['definition']['actions'])
            if name=='Verify_prepared_selection':n[name]['expression']='@or(true,'+n[name]['expression'][1:]+')'
            elif name=='Find_prepared_receipt':n[name]['inputs']['parameters']['parameters/uri']+='&unreviewed=true'
            else:n[name]['inputs']['preparedRevision']['qualificationReceipt']['DocumentReference']+='changed'
            with self.subTest(node=name),self.assertRaises(ValueError):_check_context_shape(out['properties']['definition'])

    def test_only_existing_selected_source_gains_two_readonly_modes(self):
        flow,profiles=fixture();out=with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']))
        nodes=_flatten(out['properties']['definition']['actions']);expression=nodes['SourceProfiles_operation']['expression']
        for index,profile in enumerate(profiles):
            for operation in ('Check context','Project ownership','Check preparation','Check readiness','Check closure','Other'):
                ev=Expressions(outputs={'Test_trigger':{'text':operation},'SourceProfiles_selected':profile})
                self.assertEqual(ev.evaluate(expression),index==0 or operation in ('Check context','Check preparation','Check readiness'))
        self.assertEqual(_check_context_shape(out['properties']['definition']),profiles)

    def test_exact_three_edits_preserve_every_other_guard_node_connection_and_input(self):
        flow,profiles=fixture();original=copy.deepcopy(flow)
        out=with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']))
        self.assertEqual(flow,original);self.assertEqual(out['properties']['state'],'Stopped')
        n=_flatten(out['properties']['definition']['actions']);old=_flatten(flow['properties']['definition']['actions'])
        n['SourceProfiles_operation']['expression']=old['SourceProfiles_operation']['expression']
        del n['Selected_case_context']['inputs']['limits']['additionalPreparationContextSource']
        n['Read_prepared_source_final']['inputs']['parameters']['parameters/uri']=old['Read_prepared_source_final']['inputs']['parameters']['parameters/uri']
        out['properties']['state']=flow['properties']['state'];self.assertEqual(out,flow)
        self.assertLessEqual(audit_actions(out['properties']['definition'])['maximumActionDepth'],8)

    def test_final_source_read_follows_each_verified_context(self):
        flow,profiles=fixture();out=with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']))
        n=_flatten(out['properties']['definition']['actions']);uri=n['Read_prepared_source_final']['inputs']['parameters']['parameters/uri']
        self.assertEqual(uri,_projection_source_uri())
        for profile in profiles:
            actual=Expressions(outputs={'Selected_case_context':{'sourcePins':profile}}).evaluate(uri)
            self.assertEqual(actual,"_api/web/GetFileById('"+profile['UniqueId']+"')?$select=UniqueId,ETag,Length")
        for name in ('Route_preparation_check','Route_readiness_check'):
            self.assertTrue(all(a['inputs']['parameters']['parameters/method']=='GET' for a in _flatten(n[name]['actions']).values()if a['type']=='OpenApiConnection'))

    def test_existing_projection_exception_is_preserved_without_broadening_it(self):
        flow,profiles=fixture();flow=with_ownership_projection_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']))
        out=with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']))
        self.assertEqual(_check_context_shape(out['properties']['definition']),profiles)
        n=_flatten(out['properties']['definition']['actions']);self.assertEqual(n['Selected_case_context']['inputs']['limits']['additionalOwnershipProjectionSource'],profiles[1]['UniqueId'])
        self.assertFalse(Expressions(outputs={'Test_trigger':{'text':'Check closure'},'SourceProfiles_selected':profiles[1]}).evaluate(n['SourceProfiles_operation']['expression']))

    def test_changed_digest_unknown_seed_and_repeated_source_refused(self):
        for mode in ('digest','unknown','seed','repeat'):
            flow,profiles=fixture();source=profiles[1]['UniqueId'];pin=digest(flow['properties']['definition'])
            if mode=='digest':pin='0'*64
            elif mode=='unknown':source='00000000-0000-4000-8000-000000000099'
            elif mode=='seed':source=profiles[0]['UniqueId']
            else:
                flow=with_readonly_preparation_source(flow,source,pin);pin=digest(flow['properties']['definition'])
            with self.subTest(mode=mode),self.assertRaises(ValueError):with_readonly_preparation_source(flow,source,pin)

    def test_writing_foreign_or_unknown_readers_and_postcomposition_tampering_refused(self):
        for change in ('method','body','dataset','connection','uri','type','override','else'):
            flow,profiles=fixture();nodes=_flatten(flow['properties']['definition']['actions']);node=nodes['Read_prepared_source_final']
            if change=='type':node['type']='Http'
            elif change=='connection':node['inputs']['host']['connectionName']='foreign'
            elif change=='override':node['inputs']['parameters']['parameters/headers']={'X-HTTP-Method':'MERGE'}
            elif change=='else':
                writer=copy.deepcopy(node);writer['inputs']['parameters']['parameters/method']='POST'
                nodes['Route_readiness_check']['else']={'actions':{'Hidden_write':writer}}
            else:node['inputs']['parameters'][{'method':'parameters/method','body':'parameters/body','dataset':'dataset','uri':'parameters/uri'}[change]]={'method':'POST','body':'data','dataset':'https://foreign.invalid','uri':'unknown'}[change]
            with self.subTest(change=change),self.assertRaises(ValueError):with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']))
        flow,profiles=fixture();out=with_readonly_preparation_source(flow,profiles[1]['UniqueId'],digest(flow['properties']['definition']))
        _flatten(out['properties']['definition']['actions'])['Read_prepared_source_final']['inputs']['parameters']['parameters/uri']='static-source'
        with self.assertRaises(ValueError):_check_context_shape(out['properties']['definition'])
