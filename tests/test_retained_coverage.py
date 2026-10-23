import copy
import unittest
from scripts.ppg_retained_coverage import derive, render


class RetainedCoverageTests(unittest.TestCase):
    def fixture(self):
        rows = [dict(documentUID=k, sourceDocumentId=k, title=k,
                     coverage='metadata_only', comparisonState='not_compared') for k in ['a', 'b']]
        assessment = dict(comparatorOriginalSHA256='original', comparatorTextSHA256='text',
                          subjectInspectionSHA256='subject', currentAuthorityVerified=False,
                          catalogueAssociation=dict(status='unverified_identifier_variant'))
        source = dict(sourceIndex=0, byteFacts=dict(sourceIndex=0, originalSha256='original', textSha256='text'),
            source=dict(sourceSha256='original', textSha256='text', textCoverage='sampled_ocr'),
            retrievalAssociations=[dict(documentUID='b', sourceDocumentId='b', title='b')],
            assessments=[dict(documentUID='b', assessment=assessment)],
            sourceAssociationHolds=[], pendingAssociatedDocumentUIDs=[], state='assessed_retained_text')
        return dict(inspectedSourceSha256='subject', preparation=dict(comparisonMatrix=rows),
                    retrievalCorpusReconciliation=dict(comparisonMatrix=rows, catalogueCount=2,
                        retainedSourceCount=1, catalogueMetadataOnlyCount=1, sources=[source]))

    def test_derived_dimension_preserves_old_assertions_and_candidate_uncertainty(self):
        pack = self.fixture(); before = copy.deepcopy(pack); result = derive(pack)
        self.assertEqual(pack, before)
        self.assertEqual(result['originalRetrievalCounts'], {'metadata_only': 2})
        self.assertEqual(result['coverageCounts'], {'metadata_only': 1, 'provisional_review': 1})
        row = result['rows'][1]
        self.assertEqual(row['originalRetrievalAssertion'], before['preparation']['comparisonMatrix'][1])
        self.assertEqual(row['identifierVariantAssessments'], 1)
        self.assertEqual(row['sources'][0]['extractionCoverage'], 'sampled_ocr')
        self.assertFalse(row['currentAuthorityVerified']); self.assertIsNone(row['humanDecision'])

    def test_pending_and_hold_remain_explicit(self):
        pack = self.fixture(); source = pack['retrievalCorpusReconciliation']['sources'][0]
        source['assessments'] = []; source['pendingAssociatedDocumentUIDs'] = ['b']
        self.assertEqual(derive(pack)['rows'][1]['retainedSourceCoverage'], 'available_not_reviewed')
        source['pendingAssociatedDocumentUIDs'] = []
        source['sourceAssociationHolds'] = [dict(documentUID='b', state='held', originalSha256='original', textSha256='text')]
        self.assertEqual(derive(pack)['rows'][1]['retainedSourceCoverage'], 'held')

    def test_web_ledger_includes_every_identity_and_separates_dimensions(self):
        pack = self.fixture()
        for row in pack['preparation']['comparisonMatrix']:
            if row['documentUID'] == 'a': row['title'] = '<unsafe>'
        body = render(derive(pack), {'Evidence': 'https://example.invalid/coverage.json'})
        self.assertEqual(body.count('<tr>'), 4)  # two group headers and two identities
        self.assertIn('&lt;unsafe&gt;', body)
        self.assertIn('Original retrieval labels', body)
        self.assertIn('provisional_identifier_variant', body)
        with self.assertRaises(ValueError): render(derive(pack), {'Evidence': 'javascript:alert(1)'})

    def test_bad_pins_unknown_identity_partial_inventory_and_rollup_refused(self):
        for change in ['pin', 'uid', 'count', 'rollup', 'pending', 'duplicate', 'authority', 'assertion']:
            pack = self.fixture(); corpus = pack['retrievalCorpusReconciliation']; source = corpus['sources'][0]
            if change == 'pin': source['assessments'][0]['assessment']['comparatorTextSHA256'] = 'other'
            if change == 'uid': source['retrievalAssociations'][0]['documentUID'] = 'missing'
            if change == 'count': corpus['retainedSourceCount'] = 2
            if change == 'rollup': corpus['catalogueMetadataOnlyCount'] = 2
            if change == 'pending': source['assessments'] = []
            if change == 'duplicate': source['assessments'] *= 2
            if change == 'authority': source['assessments'][0]['assessment']['currentAuthorityVerified'] = True
            if change == 'assertion': source['retrievalAssociations'][0]['title'] = 'changed'
            with self.subTest(change=change), self.assertRaises(ValueError): derive(pack)


if __name__ == '__main__':
    unittest.main()
