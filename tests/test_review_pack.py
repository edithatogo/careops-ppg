import copy
import json
import tempfile
import unittest
from pathlib import Path
from scripts.ppg_review_pack import build, save


class ReviewPack(unittest.TestCase):
    def fixture(self):
        return dict(subject=dict(documentUID='d',title='Fictional subject',documentVersion=None,verifiedSource=False),
                    template=dict(verifiedSource=False),catalogue=dict(catalogueCount=2,sourceSha256='a'*64,records=[
                        dict(documentUID='d',title='Fictional subject',coverage='metadata_only'),
                        dict(documentUID='other',title='Fictional comparator',coverage='candidate_text_match')]),
                    criteria=dict(criteriaVersion='1',criteria=[dict(criterionId='need',question='Needed?')],decisionOptions=['retain','seek_further_evidence']),
                    annotationCoverage='complete',annotations=[dict(annotationId='a',documentUID='d',documentVersion='1',
                        sectionId='s',status='deferred',originalText='Fictional suggestion')])

    def test_all_catalogue_and_annotations_survive_without_false_findings(self):
        inputs=self.fixture(); original=copy.deepcopy(inputs);pack=build(inputs)
        self.assertEqual(len(pack['comparisonMatrix']),2)
        self.assertTrue(pack['unresolvedAnnotations'][0]['requiresReconciliation'])
        self.assertEqual(pack['findings'],[])
        self.assertIsNone(pack['humanDecision'])
        self.assertFalse(pack['publicationAuthorised'])
        self.assertEqual(inputs,original)

    def test_incomplete_accounting_and_wrong_source_refused(self):
        inputs=self.fixture();inputs['catalogue']['catalogueCount']=3
        with self.assertRaises(ValueError):build(inputs)
        inputs=self.fixture();inputs['contentInventory']=dict(sourceSha256='wrong',elements=[])
        with self.assertRaises(ValueError):build(inputs)

    def test_retry_preserves_human_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'pack';save(self.fixture(),target)
            (target/'README.md').write_text('Human revision')
            with self.assertRaises(FileExistsError):save(self.fixture(),target)
            self.assertEqual((target/'README.md').read_text(),'Human revision')
            self.assertEqual(json.loads((target/'review-pack.json').read_text())['catalogueCount'],2)

    def test_candidate_edition_does_not_replace_requested_subject(self):
        inputs=self.fixture()
        inputs['sourceCandidates']=[dict(documentVersion='older',
            sourceSha256='b'*64, sourceAuthority='unverified', containsRevisions=True)]
        pack=build(inputs)
        self.assertEqual(pack['sourceCandidates'],inputs['sourceCandidates'])
        self.assertFalse(pack['subject']['verifiedSource'])
        self.assertIsNone(pack['contentInventory'])
        self.assertEqual(pack['status'],'held_missing_evidence')
        self.assertEqual(pack['findings'],[])
        pack['sourceCandidates'][0]['documentVersion']='edited'
        self.assertEqual(inputs['sourceCandidates'][0]['documentVersion'],'older')


if __name__ == '__main__':unittest.main()
