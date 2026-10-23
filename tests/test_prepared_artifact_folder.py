"""The recorder may use a second existing folder without losing its first one."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/lifecycle'))
from test_multisource_case_context import fixture as context_fixture
from test_prepared_closure_check import Expressions
from build_prepared_revision_check import build_actions
from build_prepared_artifact_folder import build
from build_multisource_case_context import digest, _check_preparation_folders
from build_operator_entry import _flatten


def fixture():
    flow,_=context_fixture()
    flow['properties']['definition']['actions']['Prepared_reader']={'type':'Scope','runAfter':{},'actions':build_actions(flow,
        {'artifactFolderRelative':'/site/evidence','caseEvidenceFieldType':'Note','templateFileUniqueId':'00000000-0000-4000-8000-000000000011'},'Verified_preparation_ownership')}
    reader=copy.deepcopy(_flatten(flow['properties']['definition']['actions'])['Read_selected_case'])
    reader['inputs']['parameters']['parameters/method']='POST';reader['runAfter']={}
    flow['properties']['definition']['actions']['Existing_event_writer']=reader
    return flow


class PreparedArtifactFolderTests(unittest.TestCase):
    def test_canonical_reader_reuses_paired_folder_lookup_and_receipt_reference(self):
        flow, _ = context_fixture()
        binding = {'artifactFolderRelative': '/site/evidence', 'caseEvidenceFieldType': 'Note',
                   'templateFileUniqueId': '00000000-0000-4000-8000-000000000011',
                   'additionalPreparedArtifactFolder': '/site/shared-drafts'}
        nodes = _flatten(build_actions(flow, binding, 'Verified_preparation_ownership'))
        for folder, accepted in [('/site/evidence', True), ('/site/shared-drafts', True),
                                 ('/site/shared-draftsevil', False), ('/site/other', False)]:
            ev = Expressions({'Read_prepared_case': {'CaseUID': 'LC-FICTIONAL-OP-TEST'},
                              'Read_prepared_file_before': {'UniqueId': 'file-id', 'UIVersionLabel': '2.0'}},
                             {'Prepared_document_reference': 'https://example.invalid' + folder + '/draft.docx',
                              'Selected_case_context': {'CaseUID': 'LC-FICTIONAL-OP-TEST', 'caseETag': 'token'},
                              'Read_prepared_case': {'headers': {'ETag': 'token'}}})
            self.assertEqual(ev.evaluate(nodes['Verify_prepared_selection']['expression']), accepted)
            if accepted:
                self.assertIn("decodedurl='" + folder + "')/Files?", ev.evaluate(
                    nodes['Find_prepared_receipt']['inputs']['parameters']['parameters/uri']))
                self.assertEqual(ev.evaluate(nodes['Native_prepared_revision']['inputs']['preparedRevision']
                    ['qualificationReceipt']['DocumentReference']),
                    'https://example.invalid' + folder + '/PPG-prepared-file-id-v2.0.json')
        for unsafe in ['/foreign/drafts', '/site/../drafts', '/site/evidence', '/site/drafts?x=1']:
            with self.subTest(folder=unsafe), self.assertRaises(ValueError):
                build_actions(flow, {**binding, 'additionalPreparedArtifactFolder': unsafe},
                              'Verified_preparation_ownership')

    def test_both_existing_folders_pair_selection_and_version_receipt_lookup(self):
        flow=fixture();out=build(flow,'/site/shared-drafts',digest(flow['properties']['definition']));n=_flatten(out['properties']['definition']['actions'])
        for folder in ('/site/evidence','/site/shared-drafts','/site/other','/site/shared-draftsevil'):
            ev=Expressions({'Read_prepared_case':{'CaseUID':'LC-FICTIONAL-OP-TEST'},'Read_prepared_file_before':{'UniqueId':'file-id','UIVersionLabel':'2.0'}},
                {'Prepared_document_reference':'https://example.invalid'+folder+'/draft.docx','Selected_case_context':{'CaseUID':'LC-FICTIONAL-OP-TEST','caseETag':'token'},'Read_prepared_case':{'headers':{'ETag':'token'}}})
            self.assertEqual(ev.evaluate(n['Verify_prepared_selection']['expression']),folder in ('/site/evidence','/site/shared-drafts'))
            if folder in ('/site/evidence','/site/shared-drafts'):
                actual=ev.evaluate(n['Find_prepared_receipt']['inputs']['parameters']['parameters/uri'])
                self.assertEqual(actual,"_api/web/GetFolderByServerRelativePath(decodedurl='"+folder+"')/Files?$filter=Name eq 'PPG-prepared-file-id-v2.0.json'&$select=Name,UniqueId,ETag")
                reference=ev.evaluate(n['Native_prepared_revision']['inputs']['preparedRevision']['qualificationReceipt']['DocumentReference'])
                self.assertEqual(reference,'https://example.invalid'+folder+'/PPG-prepared-file-id-v2.0.json')

    def test_only_guard_lookup_and_metadata_change_all_writers_and_sources_exact(self):
        flow=fixture();before=copy.deepcopy(flow);out=build(flow,'/site/shared-drafts',digest(flow['properties']['definition']));self.assertEqual(flow,before)
        n=_flatten(out['properties']['definition']['actions']);old=_flatten(flow['properties']['definition']['actions'])
        n['Verify_prepared_selection']['expression']=old['Verify_prepared_selection']['expression']
        n['Find_prepared_receipt']['inputs']['parameters']['parameters/uri']=old['Find_prepared_receipt']['inputs']['parameters']['parameters/uri']
        n['Native_prepared_revision']['inputs']['preparedRevision']['qualificationReceipt']['DocumentReference']=old['Native_prepared_revision']['inputs']['preparedRevision']['qualificationReceipt']['DocumentReference']
        del n['Selected_case_context']['inputs']['limits']['additionalPreparedArtifactFolders']
        out['properties']['state']=flow['properties']['state'];self.assertEqual(out,flow)

    def test_stale_digest_unsafe_folder_dynamic_source_and_existing_binding_refused(self):
        for kind in ('digest','foreign','traversal','source','method','repeat'):
            flow=fixture();folder='/site/shared-drafts';pin=digest(flow['properties']['definition'])
            if kind=='digest':pin='0'*64
            elif kind=='foreign':folder='/foreign/drafts'
            elif kind=='traversal':folder='/site/../drafts'
            elif kind=='source':
                _flatten(flow['properties']['definition']['actions'])['Selected_case_context']['inputs']['sourcePins']['UniqueId']="@outputs('unverified')";pin=digest(flow['properties']['definition'])
            elif kind=='method':
                _flatten(flow['properties']['definition']['actions'])['Find_prepared_receipt']['inputs']['parameters']['parameters/method']='POST';pin=digest(flow['properties']['definition'])
            else:flow=build(flow,folder,pin);pin=digest(flow['properties']['definition'])
            with self.subTest(kind=kind),self.assertRaises(ValueError):build(flow,folder,pin)

    def test_changed_remaining_url_guard_cannot_pass_pinned_folder_review(self):
        flow=fixture();out=build(flow,'/site/shared-drafts',digest(flow['properties']['definition']));n=_flatten(out['properties']['definition']['actions']);binding=n['Selected_case_context']['inputs']['limits']['additionalPreparedArtifactFolders']
        n['Verify_prepared_selection']['expression']='@or(true,'+n['Verify_prepared_selection']['expression'][1:]+')'
        with self.assertRaises(ValueError):_check_preparation_folders(n,'https://example.invalid/site',None,binding,by_document_reference=True)

    def test_changed_receipt_reference_fails_pinned_review(self):
        flow=fixture();out=build(flow,'/site/shared-drafts',digest(flow['properties']['definition']))
        n=_flatten(out['properties']['definition']['actions'])
        binding=n['Selected_case_context']['inputs']['limits']['additionalPreparedArtifactFolders']
        n['Native_prepared_revision']['inputs']['preparedRevision']['qualificationReceipt']['DocumentReference']+='changed'
        with self.assertRaises(ValueError):
            _check_preparation_folders(n,'https://example.invalid/site',None,binding,by_document_reference=True)
