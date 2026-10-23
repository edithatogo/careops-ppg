"""Reproducible source-only preparation preserves snapshots and existing outputs."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from test_multisource_case_context import fixture as context_fixture, COLLECTION
from test_operator_entry import legacy_fixture
import test_native_completed_review as completed_tests
from build_operator_entry import _flatten
from prepare_next_review_handoff import prepare, target_identity, digest, write_bundle
from build_multisource_case_context import with_ownership_projection_source
from build_multisource_case_context import with_readonly_preparation_source


def fixture():
    consumer,profiles=context_fixture();consumer['name']='00000000-0000-4000-8000-000000000099'
    consumer['properties']['environment']={'name':'Default-00000000-0000-4000-8000-000000000098'}
    consumer['properties']['definition']['actions']['Validate_case_operation']={
        'type':'If','expression':"@equals(triggerBody()?['text'],'Check context')",'runAfter':{},'actions':{}}
    legacy=legacy_fixture();config=completed_tests.NativeCompletedReviewTests().complete_binding()
    config.update(allowedSources=profiles,caseListUri=COLLECTION)
    legacy['properties']['connectionReferences']=completed_tests.NativeCompletedReviewTests().reference()['properties']['connectionReferences']
    nodes=_flatten(legacy['properties']['definition']['actions'])
    nodes['Create_case']['inputs']['parameters']['parameters/uri']=COLLECTION
    nodes['Request']['inputs'].update({key:profiles[0]['sha256' if key=='DocumentSHA256' else key]
        for key in ('DocumentUID','DocumentReference','ReviewedVersionRef','DocumentSHA256')})
    return legacy,consumer,config,digest(target_identity(consumer))


class PrepareNextReviewHandoffTests(unittest.TestCase):
    def test_manifest_reports_configured_exceptions_without_claiming_native_qualification(self):
        legacy,target,config,pin=fixture()
        _,_,default=prepare(legacy,target,config,pin)
        self.assertTrue(default['limits']['additionalSourcesCheckContextOnly'])
        self.assertEqual(default['limits']['configuredAdditionalSourceOperations'],{})
        from test_readonly_preparation_source import fixture as readonly_fixture
        target,profiles=readonly_fixture()
        _,identity,_,_=fixture()
        target['name']=identity['name'];target['properties']['environment']=identity['properties']['environment']
        target['properties']['definition']['actions']['Validate_case_operation']=identity['properties']['definition']['actions']['Validate_case_operation']
        target=with_readonly_preparation_source(target,profiles[1]['UniqueId'],digest(target['properties']['definition']),artifact_folder_relative='/site/qualification-drafts',required_fictional_roles=['FICTIONAL content-review role'])
        _,_,manifest=prepare(legacy,target,config,digest(target_identity(target)))
        limits=manifest['limits']
        self.assertFalse(limits['additionalSourcesCheckContextOnly'])
        self.assertFalse(limits['otherOperationsRetainOriginalSource'])
        self.assertEqual(limits['configuredAdditionalSourceOperations'],{mode:profiles[1]['UniqueId']for mode in ('Check preparation','Check readiness')})
        self.assertTrue(limits['sourceSpecificPreparationFolderConfigured'])
        self.assertTrue(limits['sourceSpecificReadinessRolesConfigured'])
        self.assertFalse(limits['laterWritersQualified']);self.assertFalse(manifest['nativeExecuted'])

    def test_projection_exception_rebuilds_the_exact_consumer_fingerprint(self):
        legacy,target,config,pin=fixture()
        consumer,producer,_=prepare(legacy,target,config,pin)
        updated=with_ownership_projection_source(consumer,config['allowedSources'][1]['UniqueId'],
                                                digest(consumer['properties']['definition']))
        prepared,new_producer,manifest=prepare(legacy,updated,config,digest(target_identity(updated)))
        self.assertEqual(manifest['limits']['configuredAdditionalSourceOperations'],{'Project ownership':config['allowedSources'][1]['UniqueId']})
        self.assertFalse(manifest['limits']['additionalSourcesCheckContextOnly'])
        self.assertEqual(prepared,updated)
        old=_flatten(producer['properties']['definition']['actions'])['Operator_case_work_handoff']['inputs']
        new=_flatten(new_producer['properties']['definition']['actions'])['Operator_case_work_handoff']['inputs']
        self.assertEqual(new['entrypointSHA256'],digest(target_identity(prepared)))
        self.assertNotEqual(old['entrypointSHA256'],new['entrypointSHA256'])
        self.assertEqual({k:v for k,v in old.items() if k!='entrypointSHA256'},
                         {k:v for k,v in new.items() if k!='entrypointSHA256'})
        self.assertEqual(prepare(legacy,prepared,config,digest(target_identity(prepared)))[:2],
                         (prepared,new_producer))

    def test_rebuild_from_exact_consumer_readback_is_repeatable_and_preserves_inputs(self):
        inputs=fixture();before=copy.deepcopy(inputs)
        consumer,producer,manifest=prepare(*inputs)
        self.assertEqual(inputs,before)
        self.assertEqual(consumer['properties']['state'],'Stopped')
        self.assertEqual(producer['properties']['state'],'Stopped')
        self.assertFalse(manifest['nativeInstalled']);self.assertFalse(manifest['nativeExecuted'])
        self.assertEqual(manifest['sourceCount'],2)
        rebuilt=prepare(inputs[0],consumer,inputs[2],digest(target_identity(consumer)))
        self.assertEqual(rebuilt[:2],(consumer,producer))
        for geometry in manifest['geometry'].values():
            self.assertLessEqual(geometry['maximumActionDepth'],8)
            self.assertLessEqual(geometry['actionCount'],500)

    def test_stale_target_or_changed_installed_profiles_refuse_before_output(self):
        legacy,target,config,pin=fixture()
        with self.assertRaisesRegex(ValueError,'target changed'):prepare(legacy,target,config,'0'*64)
        consumer,_,_=prepare(legacy,target,config,pin)
        config['allowedSources'][1]['ETag']='"2"'
        with self.assertRaisesRegex(ValueError,'profiles differ'):
            prepare(legacy,consumer,config,digest(target_identity(consumer)))

    def test_create_only_bundle_hashes_actual_bytes_and_cannot_overwrite_human_edits(self):
        consumer,producer,manifest=prepare(*fixture())
        with tempfile.TemporaryDirectory() as temporary:
            destination=Path(temporary)/'prepared'
            report=write_bundle(destination,consumer,producer,manifest)
            for name,pin in report['outputSHA256'].items():
                self.assertEqual(hashlib.sha256((destination/name).read_bytes()).hexdigest(),pin)
            self.assertEqual(json.loads((destination/'manifest.json').read_text()),report)
            (destination/'consumer-candidate.json').write_text('preserved human edit')
            before={p.name:p.read_bytes() for p in destination.iterdir()}
            with self.assertRaises(FileExistsError):write_bundle(destination,consumer,producer,manifest)
            self.assertEqual(before,{p.name:p.read_bytes() for p in destination.iterdir()})


if __name__=='__main__':unittest.main()
