import copy,hashlib,unittest
from scripts.ppg_pair_review import assess


class PairReview(unittest.TestCase):
    def setUp(self):
        self.subject=b'fictional subject';self.text=b'Document Number: ID-1\nA distinct purpose\n';self.original=b'fictional PDF'
        sha=lambda b:hashlib.sha256(b).hexdigest()
        self.inventory=dict(sourceSha256=sha(self.subject),elements=[dict(sourceLocator='body#1',text='A subject purpose',containsRevisions=False)])
        self.comparator=dict(documentUID='c',recordedDocumentId='ID-1',textSha256=sha(self.text),originalSha256=sha(self.original))
        self.prep=dict(subject=dict(documentUID='s',verifiedSource=False),comparisonMatrix=[dict(documentUID='s',sourceDocumentId='S-2'),dict(documentUID='c',sourceDocumentId='ID-1')],catalogueCount=2,reviewChecklist=[dict(criterionId='need')],decisionOptions=['retain','seek_further_evidence'],criteriaVersion='1')
        self.finding=dict(findingId='f',criterionId='need',claimType='inference',suggestedAction='retain',statement='Distinct scopes',benefit='Avoid needless merger',effort='low',dependencies='Current sources',uncertainty='Historical only',citations=[dict(sourceId='subject-inspection',sourceSha256=sha(self.subject),locator='body#1',quote='subject purpose'),dict(sourceId='comparator-text',sourceSha256=sha(self.text),locator='lines=2-2',quote='distinct purpose')])
    def run_review(self,finding=None):
        return assess(self.prep,self.inventory,self.subject,self.comparator,self.text,self.original,[finding or self.finding])
    def test_updates_only_provisional_pair_and_preserves_catalogue_inputs(self):
        before=copy.deepcopy(self.prep);r=self.run_review()
        self.assertEqual(r['catalogueCount'],2);self.assertEqual(r['retainedTextPairsAssessed'],1)
        self.assertEqual(r['verifiedRequestedEditionComparisons'],0);self.assertEqual(self.prep,before)
        self.assertFalse(r['runtimeIdentity']['qualifiedNativeAI'])
    def test_tracked_revision_cannot_support_a_definitive_inference(self):
        self.inventory['elements'][0]['containsRevisions']=True
        with self.assertRaises(ValueError):self.run_review()
        f=copy.deepcopy(self.finding);f.update(claimType='unknown',suggestedAction='seek_further_evidence')
        self.assertTrue(self.run_review(f)['findings'][0]['citations'][0]['containsTrackedRevisions'])

    def test_exact_pair_replay_preserves_review_and_rejects_changed_or_legacy_evidence(self):
        first=self.run_review()
        self.prep['comparisonMatrix']=copy.deepcopy(first['comparisonMatrix'])
        self.assertEqual(self.run_review()['comparisonMatrix'],first['comparisonMatrix'])
        self.prep['comparisonMatrix'][1].update(reason='Human working note',comparisonState='operator_triage_pending')
        before=copy.deepcopy(self.prep['comparisonMatrix'])
        self.assertEqual(self.run_review()['comparisonMatrix'],before)
        changed=copy.deepcopy(self.finding);changed['statement']='Changed interpretation with same finding identity'
        with self.assertRaises(ValueError):self.run_review(changed)
        self.prep['comparisonMatrix'][1]['retainedTextPairAssessment'].pop('assessmentContentSHA256')
        with self.assertRaises(ValueError):self.run_review()
    def test_wrong_source_locator_identifier_and_human_decision_refused(self):
        f=copy.deepcopy(self.finding);f['citations'][1]['locator']='lines=99-100'
        with self.assertRaises(ValueError):self.run_review(f)
        f=copy.deepcopy(self.finding);f['humanDecision']='approved'
        with self.assertRaises(ValueError):self.run_review(f)
        self.comparator['recordedDocumentId']='other'
        with self.assertRaises(ValueError):self.run_review()

    def test_identifier_prefix_is_not_an_identity_match(self):
        self.text=self.text.replace(b'ID-1',b'ID-10')
        self.comparator['textSha256']=hashlib.sha256(self.text).hexdigest()
        with self.assertRaises(ValueError):self.run_review()

    def test_save_preserves_an_existing_edited_pack(self):
        import tempfile
        from pathlib import Path
        from scripts.ppg_pair_review import save
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)/'pack';save(self.run_review(),target)
            edited=target/'README.md';edited.write_text('Human working note')
            with self.assertRaises(FileExistsError):save(self.run_review(),target)
            self.assertEqual(edited.read_text(),'Human working note')

    def candidate(self):
        self.prep['comparisonMatrix'][1].update(sourceDocumentId='ID-2',comparisonState='metadata_only',reason='Current source missing')
        self.comparator.update(currentAuthorityVerified=False,catalogueAssociation=dict(
            status='unverified_identifier_variant',catalogueDocumentId='ID-2',
            rationale='Fictional retrieval candidate only; no identity decision',evidenceRef='fictional://screening'))

    def test_candidate_keeps_catalogue_assertion_state_and_prior_review(self):
        self.candidate();before=copy.deepcopy(self.prep);r=self.run_review();row=r['comparisonMatrix'][1]
        self.assertEqual(row['sourceDocumentId'],'ID-2');self.assertEqual(row['comparisonState'],'metadata_only')
        self.assertEqual(row['reason'],'Current source missing');self.assertNotIn('retainedTextPairAssessment',row)
        self.assertEqual(r['retainedTextPairsAssessed'],0);self.assertEqual(r['candidateIdentifierPairsAssessed'],1)
        self.assertEqual(r['retainedSourcePairsAssessed'],1);self.assertEqual(self.prep,before)
        self.prep['comparisonMatrix']=r['comparisonMatrix']
        replay=self.run_review();self.assertEqual(replay['comparisonMatrix'],r['comparisonMatrix'])
        changed=copy.deepcopy(self.finding);changed['statement']='A changed interpretation'
        with self.assertRaises(ValueError):self.run_review(changed)

    def test_variant_refuses_missing_evidence_authority_and_wrong_binding(self):
        self.candidate()
        for key,value in [('status','accepted'),('catalogueDocumentId','other'),('rationale',''),('evidenceRef','')]:
            original=self.comparator['catalogueAssociation'][key];self.comparator['catalogueAssociation'][key]=value
            with self.assertRaises(ValueError):self.run_review()
            self.comparator['catalogueAssociation'][key]=original
        self.comparator['currentAuthorityVerified']=True
        with self.assertRaises(ValueError):self.run_review()
        self.comparator['currentAuthorityVerified']=False
        self.prep['comparisonMatrix'][1]['sourceDocumentId']='ID-1'
        with self.assertRaises(ValueError):self.run_review()

    def test_variant_still_requires_actual_source_bytes_and_passages(self):
        self.candidate();self.original=b'changed original'
        with self.assertRaises(ValueError):self.run_review()
        self.comparator['originalSha256']=hashlib.sha256(self.original).hexdigest()
        f=copy.deepcopy(self.finding);f['citations'][1]['quote']='invented text'
        with self.assertRaises(ValueError):self.run_review(f)
        self.comparator['recordedDocumentId']='ID-10'
        with self.assertRaises(ValueError):self.run_review()
