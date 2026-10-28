import copy
import unittest

from test_lifecycle_relationship_checkpoint import fixture
from scripts.ppg_relationship_versions import native_history_plan, recover, head
from scripts.ppg_lifecycle_relationship_checkpoint import freeze_context, scoped_manifest, prepare_reference_transition
from scripts.ppg_source_standards import digest


def pair():
    snapshot,rows,a=fixture();b=copy.deepcopy(a);b['scope']={**a['scope'],'CaseUID':'LC-FICTIONAL-OP-B','DocumentReference':'fixture:draft-B'}
    policy=snapshot['journal']['events'][1]['body'];b['sourceBinding']['journalPin']=policy
    b['sourceBinding']['source'].update(DocumentUID='FICTIONAL-original-other',UniqueId='source-B',DocumentReference='fixture:source-B',sha256=policy['sha256'])
    source=b['sourceBinding']['source'];original={**a['preparedRevision']['originalSourceScope'],'CaseUID':b['scope']['CaseUID'],'DocumentReference':source['DocumentReference'],'ReviewedVersionRef':'sharepoint:source-B:'+source['ETag'],'DocumentSHA256':source['sha256']}
    b['preparedRevision'].update(scope=b['scope'],originalSourceScope=original)
    b['preparedRevision']['file']['UniqueId']='draft-B'
    b['binaryProof']['sourcePin']['UniqueId']='draft-B'
    b['sourceContext']={'scope':original,'sourcePins':{k:source[k] for k in ('UniqueId','ETag','DocumentUID')}}
    b['issued'].update(UniqueId='issued-B',DocumentReference='fixture:issued-B',PublishedVersionRef='fixture:issued-B-v1')
    b['binaryProof']['issuedPin']['UniqueId']='issued-B'
    for name in a['frames']:
        ar=a['frames'][name]['before']['value'];br=b['frames'][name]['before']['value']
        for row in br:
            row.update(b['scope']);row['Id']+=20;row['GUID']+='-B';row['EventUID']+='-B'
            for field in ('ParentEventUID','ReadinessEventUID'):
                if row.get(field):row[field]+='-B'
            if row.get('Stage')=='Publication':
                row['PublicationURL']=b['issued']['DocumentReference'];row['PublishedVersionRef']=b['issued']['PublishedVersionRef']
        full=ar+br
        for ctx in (a,b):ctx['frames'][name]={'before':{'value':copy.deepcopy(full)},'after':{'value':copy.deepcopy(full)}}
    for key in ('request','response','readiness','publication'):b['selected'][key]+='-B'
    b['selected']['purposes']={k:v+'-B' for k,v in b['selected']['purposes'].items()}
    checkpoints={k:freeze_context(snapshot,rows,v) for k,v in [('A',a),('B',b)]}
    stored={k:{'file':{'UniqueId':'manifest-'+k,'ETag':'"manifest-pin"','DocumentReference':'fixture:manifest-'+k},
               'contentSHA256':digest(scoped_manifest(v,rows))} for k,v in checkpoints.items()}
    request={'requestId':'FICTIONAL-RV25-LC07-source-reference','recordedAt':'2026-10-28T00:00:00Z','effectiveFrom':'2026-10-28T00:00:00Z','actorRef':'FICTIONAL technical operator'}
    return snapshot,rows,checkpoints,stored,request


class LifecycleReferenceTransitionTests(unittest.TestCase):
    def test_both_cycles_prepare_only_a_proposed_source_reference(self):
        args=pair();result=prepare_reference_transition(*args);journal=recover(result['snapshot'])
        self.assertEqual(result['expectedPreviousHead'],head(recover(args[0])))
        self.assertTrue(result['nativePlan']['nativeCheckpointComplete'])
        self.assertEqual(journal['events'][-1]['body']['type'],'references')
        self.assertEqual(journal['events'][-1]['body']['from'],args[2]['B']['payload']['context']['sourceBinding']['journalPin'])
        self.assertFalse(result['nativeWriterEnabled']);self.assertFalse(result['realPolicyAuthority'])
    def test_missing_cycle_changed_manifest_and_cross_snapshot_refused(self):
        for kind in ('missing','manifest','token','snapshot','actor'):
            with self.subTest(kind=kind):
                args=list(pair())
                if kind=='missing':del args[2]['B']
                elif kind=='manifest':args[3]['A']['contentSHA256']='changed'
                elif kind=='token':args[3]['A']['file']['ETag']='*'
                elif kind=='snapshot':args[0]={}
                else:args[4]['actorRef']='Real actor'
                with self.assertRaises(ValueError):prepare_reference_transition(*args)


if __name__=='__main__':unittest.main()
