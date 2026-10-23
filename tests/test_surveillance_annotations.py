import hashlib,json,tempfile,unittest
from pathlib import Path
from scripts.ppg_source_surveillance import capture
from scripts.ppg_surveillance_annotations import proposals


class QuietSurveillance(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.registry=dict(familyId='fictional',registryVersion='1',ownerNotificationsEnabled=False,automaticBaselinePromotion=False,sources=[dict(sourceKey='s',canonicalUrl='https://example.test/source',frameworkEditionId='f')])
        self.requirements=[dict(RequirementKey='r1',FrameworkKey='f'),dict(RequirementKey='r2',FrameworkKey='f')]
        self.mappings=[dict(MappingKey='m1',RequirementKey='r1',DocumentUID='d',DocumentVersion='historical',MappingState='Proposed',EvidenceRef='fictional'),dict(MappingKey='m2',RequirementKey='r2',DocumentUID='d',DocumentVersion='historical',MappingState='Reviewed',EvidenceRef='fictional')]
    def snapshot(self,name,raw,status='captured'):
        p=self.root/(name+'.raw');p.write_bytes(raw);o=dict(sourceKey='s',status=status,capturedAtUtc='2026-10-19T00:00:00Z')
        if status=='captured':o.update(canonicalUrl='https://example.test/source',file=str(p),sha256=hashlib.sha256(raw).hexdigest(),nativeVersionRef=None,acquisitionRoute='fictional')
        out=self.root/name;capture(self.registry,[o],out);return out
    def test_multiple_mapping_paths_create_one_quiet_version_bound_proposal(self):
        a=self.snapshot('a',b'before');b=self.snapshot('b',b'after');r=proposals(self.registry,a,b,self.requirements,self.mappings)
        self.assertEqual(len(r['annotationProposals']),1);p=r['annotationProposals'][0]
        self.assertEqual(p['DocumentVersion'],'historical');self.assertEqual(len(json.loads(p['EvidenceRef'])['mappingKeys']),2)
        self.assertFalse(r['notificationsEnabled']);self.assertFalse(r['baselineAdvanced'])
        replay=proposals(self.registry,a,b,self.requirements,self.mappings,[p['AnnotationKey']])
        self.assertFalse(replay['annotationProposals']);self.assertEqual(replay['deduplicatedProposalKeys'],[p['AnnotationKey']])
    def test_failed_capture_is_exception_not_change_annotation(self):
        a=self.snapshot('a',b'before');b=self.snapshot('b',b'not-used','denied');r=proposals(self.registry,a,b,self.requirements,self.mappings)
        self.assertFalse(r['annotationProposals']);self.assertEqual(r['unresolvedSources'][0]['kind'],'source-unavailable-exception')
    def test_unlinked_change_unassessed_and_unchanged_has_no_proposal(self):
        a=self.snapshot('a',b'before');b=self.snapshot('b',b'after');r=proposals(self.registry,a,b,self.requirements,[])
        self.assertFalse(r['annotationProposals']);self.assertEqual(len(r['unresolvedSources']),1)
        self.assertFalse(proposals(self.registry,a,a,self.requirements,self.mappings)['annotationProposals'])
    def test_notification_and_unknown_relationship_refused(self):
        a=self.snapshot('a',b'a');self.registry['ownerNotificationsEnabled']=True
        with self.assertRaises(ValueError):proposals(self.registry,a,a,self.requirements,self.mappings)
        self.registry['ownerNotificationsEnabled']=False;self.mappings[0]['RequirementKey']='missing'
        with self.assertRaises(ValueError):proposals(self.registry,a,a,self.requirements,self.mappings)
