import copy
import unittest
from scripts.ppg_corpus_reconciliation import digest, inspect_sources, reconcile


class CorpusReconciliation(unittest.TestCase):
    def fixture(self):
        store = {'one.pdf': b'original', 'one.txt': b'Document Number: TEST-V1-01/25\nText'}
        source = dict(originalPath='one.pdf', textPath='one.txt',
                      sourceSha256=digest(store['one.pdf']), textSha256=digest(store['one.txt']),
                      textCoverage='sampled_ocr', headerIdentifiers=['TEST-V1-01/25'])
        row = dict(documentUID='fictional', sourceDocumentId='TEST-V2-01/26',
                   title='Fictional', sourceIndexes=[0], coverage='other_edition_candidate')
        screen = dict(catalogueCount=1, sourceCount=1, corpus=[source], records=[row])
        ledger = dict(catalogueCount=1, comparisonMatrix=[copy.deepcopy(row)])
        return screen, ledger, store

    def test_preserves_partial_coverage_and_inputs(self):
        screen, ledger, store = self.fixture()
        before = copy.deepcopy((screen, ledger))
        report = reconcile(screen, ledger, inspect_sources(screen, store.__getitem__))
        self.assertEqual(report['sourceStates'], {'associated_unassessed': 1})
        self.assertEqual(report['extractionCoverage'], {'sampled_ocr': 1})
        self.assertEqual((screen, ledger), before)
        self.assertEqual(report['newAssessments'], 0)

    def test_tampered_actual_bytes_refused(self):
        screen, _, store = self.fixture(); store['one.pdf'] += b'changed'
        with self.assertRaises(ValueError): inspect_sources(screen, store.__getitem__)

    def test_assessment_requires_both_original_and_extraction(self):
        screen, ledger, store = self.fixture(); s = screen['corpus'][0]
        entry = dict(comparatorOriginalSHA256=s['sourceSha256'], comparatorTextSHA256=s['textSha256'],
                     currentAuthorityVerified=False, assessmentContentSHA256='content')
        ledger['comparisonMatrix'][0]['retainedIdentifierCandidateAssessments'] = [entry]
        facts = inspect_sources(screen, store.__getitem__)
        report = reconcile(screen, ledger, facts)
        self.assertEqual(report['sourceStates'], {'assessed_retained_text': 1})
        entry['comparatorTextSHA256'] = 'wrong'
        with self.assertRaises(ValueError): reconcile(screen, ledger, facts)

    def test_unassociated_header_never_binds(self):
        screen, ledger, store = self.fixture(); screen['records'][0]['sourceIndexes'] = []
        report = reconcile(screen, ledger, inspect_sources(screen, store.__getitem__))
        self.assertEqual(report['sourceStates'], {'unassociated_unassessed': 1})
        self.assertEqual(report['unassociatedHeaderSourceIndexes'], [0])
        self.assertEqual(report['identityChanges'], 0)

    def test_held_source_not_counted_as_assessed(self):
        screen, ledger, store = self.fixture(); s = screen['corpus'][0]
        ledger['comparisonMatrix'][0]['sourceAssociationHolds'] = [dict(
            state='held', documentUID='fictional', originalSha256=s['sourceSha256'], textSha256=s['textSha256'])]
        report = reconcile(screen, ledger, inspect_sources(screen, store.__getitem__))
        self.assertEqual(report['sourceStates'], {'held_source_association': 1})

    def test_incomplete_duplicate_and_changed_facts_refused(self):
        for change in ['catalogue', 'duplicate', 'facts']:
            screen, ledger, store = self.fixture(); facts = inspect_sources(screen, store.__getitem__)
            if change == 'catalogue': ledger['catalogueCount'] = 2
            elif change == 'duplicate': screen['records'][0]['sourceIndexes'] = [0, 0]
            else: facts[0]['textSha256'] = 'changed'
            with self.assertRaises(ValueError): reconcile(screen, ledger, facts)

    def test_hold_and_assessment_contradiction_refused(self):
        screen, ledger, store = self.fixture(); s = screen['corpus'][0]; row=ledger['comparisonMatrix'][0]
        row['sourceAssociationHolds'] = [dict(state='held', documentUID='fictional',
            originalSha256=s['sourceSha256'], textSha256=s['textSha256'])]
        row['retainedIdentifierCandidateAssessments'] = [dict(comparatorOriginalSHA256=s['sourceSha256'],
            comparatorTextSHA256=s['textSha256'], currentAuthorityVerified=False, assessmentContentSHA256='content')]
        with self.assertRaises(ValueError): reconcile(screen, ledger, inspect_sources(screen, store.__getitem__))

    def test_changed_identity_assertion_refused(self):
        screen, ledger, store = self.fixture()
        ledger['comparisonMatrix'][0]['sourceDocumentId'] = 'silent-correction'
        with self.assertRaises(ValueError): reconcile(screen, ledger, inspect_sources(screen, store.__getitem__))

    def test_unassociated_assessment_refused(self):
        screen, ledger, store = self.fixture(); source = screen['corpus'][0]
        screen['records'][0]['sourceIndexes'] = []
        ledger['comparisonMatrix'][0]['retainedTextPairAssessment'] = dict(
            comparatorOriginalSHA256=source['sourceSha256'], comparatorTextSHA256=source['textSha256'],
            currentAuthorityVerified=False, assessmentContentSHA256='content')
        with self.assertRaises(ValueError): reconcile(screen, ledger, inspect_sources(screen, store.__getitem__))

    def test_legacy_content_hash_gap_preserved_not_invented(self):
        screen, ledger, store = self.fixture(); source=screen['corpus'][0]
        entry=dict(comparatorOriginalSHA256=source['sourceSha256'], comparatorTextSHA256=source['textSha256'],
                   currentAuthorityVerified=False)
        ledger['comparisonMatrix'][0]['retainedTextPairAssessment']=entry
        report=reconcile(screen, ledger, inspect_sources(screen, store.__getitem__))
        self.assertEqual(report['assessmentProvenance'], {'legacy_content_hash_missing': 1})
        self.assertNotIn('assessmentContentSHA256', report['sources'][0]['assessments'][0]['assessment'])

    def test_unassociated_reviews_are_separate_and_hash_checked(self):
        from scripts.ppg_unassociated_review import content_digest
        screen, ledger, store=self.fixture();screen['records'][0]['sourceIndexes']=[]
        source=screen['corpus'][0]
        review=dict(kind='unassociated_retained_source_review',sourceIndex=0,
                    originalSHA256=source['sourceSha256'],textSHA256=source['textSha256'],
                    catalogueIdentityAssigned=False,currentAuthorityVerified=False,humanDecision=None)
        review['contentSHA256']=content_digest(review)
        report=reconcile(screen,ledger,inspect_sources(screen,store.__getitem__),[review])
        self.assertEqual(report['sourceStates'],{'unassociated_reviewed':1})
        self.assertEqual(report['comparisonMatrix'],ledger['comparisonMatrix'])
        self.assertEqual(report['identityChanges'],0)
        review['humanDecision']='approved'
        with self.assertRaises(ValueError):reconcile(screen,ledger,inspect_sources(screen,store.__getitem__),[review])

    def test_source_review_cannot_reassign_associated_or_duplicate_source(self):
        from scripts.ppg_unassociated_review import content_digest
        screen,ledger,store=self.fixture();source=screen['corpus'][0]
        review=dict(kind='unassociated_retained_source_review',sourceIndex=0,
                    originalSHA256=source['sourceSha256'],textSHA256=source['textSha256'],
                    catalogueIdentityAssigned=False,currentAuthorityVerified=False,humanDecision=None)
        review['contentSHA256']=content_digest(review)
        with self.assertRaises(ValueError):reconcile(screen,ledger,inspect_sources(screen,store.__getitem__),[review])
        screen['records'][0]['sourceIndexes']=[]
        with self.assertRaises(ValueError):reconcile(screen,ledger,inspect_sources(screen,store.__getitem__),[review,review])
