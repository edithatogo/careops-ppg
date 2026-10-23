"""Composition and stale-input refusal; synthetic observations, no tenant calls."""
import copy
import json
import unittest
from build_operator_entry import _flatten
from build_prepared_recording_chain import build, STAGES
from binary_publication import digest
from test_prepared_binary_publication import fixture as publication_fixture

COLLECTION="_api/web/lists(guid'00000000-0000-4000-8000-000000000008')/items"


def fixture():
    purpose,target,binding=publication_fixture()
    _flatten(purpose['properties']['definition']['actions'])['Read_selected_case']['inputs']['parameters']['parameters/uri']="@concat('"+COLLECTION.replace("'","''")+"(',string(1),')')"
    binding['approvedPurposeDefinitionSHA256']=digest(purpose['properties']['definition'])
    targets={stage:copy.deepcopy(target) for stage in STAGES}
    for stage,t in targets.items():t['name']='FICTIONAL-'+stage
    content={'kind':'local-downloaded-binary-parity-v1','downloadEvidence':{'source':{},'issued':{},'producer':{}}}
    receipt={'UniqueId':'FICTIONAL-proof','ETag':'"proof,1"','DocumentReference':'https://example.invalid/proof.json'}
    evidence=json.dumps({'kind':'independent-binary-publication-producer-qualification-v1',
        'copyFlowName':targets['publication']['name'],'copyRunId':'FICTIONAL-run',
        'proofContentSHA256':digest(content),'proofReceipt':receipt}).encode()
    import hashlib
    binding['reviewedBinaryProof']={'receipt':receipt,'content':content,'producerEvidenceSHA256':hashlib.sha256(evidence).hexdigest()}
    config={'publicationBinding':binding,'caseListUri':COLLECTION,
        'approvedTargetDefinitionSHA256':{stage:digest(t['properties']['definition']) for stage,t in targets.items()}}
    return purpose,targets,config,evidence


class RecordingChainTests(unittest.TestCase):
    def test_one_proof_reaches_all_three_graphs_without_supplied_implementation_parent(self):
        args=fixture();before=copy.deepcopy(args)
        outputs,manifest=build(*args)
        self.assertEqual(args,before)
        self.assertEqual(set(outputs),set(STAGES))
        self.assertFalse(manifest['runtimeQualified']);self.assertEqual(manifest['nativeWrites'],0)
        for stage,flow in outputs.items():
            self.assertEqual(flow['name'],args[1][stage]['name'])
            self.assertEqual(flow['properties']['state'],'Stopped')
            self.assertEqual(flow['properties']['connectionReferences'],args[1][stage]['properties']['connectionReferences'])
            self.assertIn('FICTIONAL-proof',json.dumps(flow))
        flat=_flatten(outputs['verification']['properties']['definition']['actions'])
        self.assertIn('SelectedVerification_parent',flat)
        self.assertNotIn('COMPILER-RUNTIME-PARENT',json.dumps(outputs))
        self.assertNotIn('Create_implementation',flat)

    def test_reviewed_note_contract_reaches_existing_implementation_compiler(self):
        args=fixture();field={'InternalName':'ImplementationActionsNote','TypeAsString':'Note',
            'RichText':False,'AppendOnly':False,'ReadOnlyField':False}
        args[2].update(implementationActionsNoteField=field,
            approvedImplementationActionsNoteFieldSHA256=digest(field))
        before=copy.deepcopy(args);outputs,_=build(*args);self.assertEqual(args,before)
        payload=outputs['implementation']['properties']['definition']['actions']['Implementation_payload']['inputs']
        self.assertEqual(payload['ImplementationActionsNote'],"@triggerBody()?['text_2']")
        self.assertNotIn('COMPILER-RUNTIME-PARENT',json.dumps(outputs))
        args[2]['implementationActionsNoteField']['RichText']=True
        with self.assertRaises(ValueError):build(*args)

    def test_stale_target_active_target_and_duplicate_identity_refused(self):
        for mode in ('stale','active','duplicate'):
            with self.subTest(mode=mode):
                args=fixture();t=args[1]
                if mode=='stale':t['implementation']['properties']['definition']['changed']=True
                if mode=='active':t['verification']['properties']['state']='Started'
                if mode=='duplicate':t['verification']['name']=t['publication']['name']
                with self.assertRaises(ValueError):build(*args)

    def test_missing_or_changed_independent_evidence_never_opens_recording(self):
        args=fixture();args[2]['publicationBinding']['reviewedBinaryProof']=None
        with self.assertRaisesRegex(ValueError,'Separately verified'):build(*args)
        args=fixture()
        with self.assertRaisesRegex(ValueError,'Actual separately reviewed'):build(*args[:-1],args[-1]+b' ')
