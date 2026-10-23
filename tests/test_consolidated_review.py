import copy
import unittest
from scripts.ppg_consolidated_review import consolidate
from scripts.ppg_unassociated_review import content_digest


class ConsolidatedReviewTests(unittest.TestCase):
    def setUp(self):
        matrix = [{'documentUID': 'fictional'}]
        self.prior = dict(requestedSubject=dict(documentUID='fictional', documentVersion='1'),
            inspectedSourceSha256='inspection', comparisonBatch=dict(comparisonMatrix=matrix, pairAssessments=[]),
            historicalStructuredInventory=dict(elements=[dict(elementId='element')]),
            sourceOnlyReviews=[], sourceOnlyReviewQuestions={'prior': 'retain'},
            preparation=dict(unresolvedAnnotations=[], gaps=['old gate']), preparedReviewRuns={'pins': ['keep']})
        review = dict(sourceIndex=1, originalSHA256='source', subjectInspectionSHA256='inspection',
                      catalogueIdentityAssigned=False, currentAuthorityVerified=False, humanDecision=None,
                      findings=[dict(criterionId='need', findingId='question', claimType='unknown', suggestedAction='seek_further_evidence')])
        review['contentSHA256'] = content_digest(review)
        self.corpus = dict(comparisonMatrix=matrix, sources=[dict(unassociatedSourceReview=review)])
        self.annotations = dict(binding={}, listId='fictional-list', annotationItems={'value': []}, histories=[])
        self.content = dict(sourceFieldsVerifiedAgainstSeeds=True, currentReviewerFieldsPreserved=True,
            items={'value': [dict(SourceElementId='element', DocumentUID='fictional', SourceEditionKey='inspection', ReviewText='human edit')]})
        self.args = [self.prior, self.corpus, {}, self.annotations, self.content, {'sourceSha256': 'inspection'}]

    def test_adds_evidence_preserves_pins_human_text_and_prior_questions(self):
        before = copy.deepcopy(self.args)
        result = consolidate(*self.args)
        self.assertEqual(self.args, before)
        self.assertEqual(result['preparedReviewRuns'], self.prior['preparedReviewRuns'])
        self.assertEqual(result['sourceOnlyReviewQuestions'], {'prior': 'retain'})
        self.assertEqual(result['nativeStructuredContentSnapshot']['items']['value'][0]['ReviewText'], 'human edit')
        self.assertEqual(result['currentVersionVerification'], 'open_nonblocking')
        self.assertFalse(result['currentSourceVerified'])
        self.assertEqual(len(result['reviewFindingIndex']['need']), 1)

    def test_refuses_lost_changed_or_promoted_evidence(self):
        for change in ['matrix', 'source', 'rows', 'binding', 'fallback', 'duplicate']:
            args = copy.deepcopy(self.args)
            if change == 'matrix': args[1]['comparisonMatrix'] = []
            if change == 'source': args[1]['sources'][0]['unassociatedSourceReview']['currentAuthorityVerified'] = True
            if change == 'rows': args[4]['items']['value'] = []
            if change == 'binding': args[4]['items']['value'][0]['SourceEditionKey'] = 'wrong'
            if change == 'fallback': args[5]['sourceSha256'] = 'wrong'
            if change == 'duplicate': args[1]['sources'] *= 2
            with self.subTest(change=change), self.assertRaises(ValueError):
                consolidate(*args)

    def test_refuses_dropped_prior_source_review(self):
        self.prior['sourceOnlyReviews'] = [copy.deepcopy(self.corpus['sources'][0]['unassociatedSourceReview'])]
        self.corpus['sources'] = []
        with self.assertRaises(ValueError): consolidate(*self.args)
