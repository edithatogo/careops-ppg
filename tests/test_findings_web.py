import copy
import unittest
from scripts.ppg_findings_web import render


class FindingsWeb(unittest.TestCase):
    def setUp(self):
        self.finding = dict(findingId='fictional-1', criterionId='fictional-criterion', claimType='inference',
                            statement='<script>source text</script>', suggestedAction='seek_further_evidence',
                            benefit='Recorded benefit', effort='Recorded effort', dependencies='Recorded dependency',
                            uncertainty='Recorded unknown', humanDecision=None,
                            citations=[dict(sourceId='fixture', locator='page 1', sourceSha256='a'*64, quote='Exact <passage>')])
        self.pack = dict(comparisonBatch={'pairAssessments':[{'comparator':{'title':'Fictional comparator', 'documentVersion':'1'},'findings':[self.finding]}]},
                         sourceOnlyReviews=[], preparation={'catalogueCount':2}, humanDecision=None,
                         policyApproved=False, publicationAuthorised=False, notificationsEnabled=False)
    def test_all_fields_and_passages_preserved_without_source_mutation(self):
        old = copy.deepcopy(self.pack)
        body, proof = render(self.pack, 'https://example.test/pack')
        self.assertIn('&lt;script&gt;source text&lt;/script&gt;', body)
        self.assertIn('Exact &lt;passage&gt;', body)
        for key in ['benefit','effort','dependencies','uncertainty']:
            self.assertIn(self.finding[key], body)
        self.assertEqual(proof['findings'], 1)
        self.assertEqual(proof['citations'], 1)
        self.assertFalse(proof['newAppraisal'])
        self.assertEqual(old, self.pack)
    def test_duplicate_decision_unsafe_link_and_missing_citation_refused(self):
        with self.assertRaises(ValueError):render(self.pack, 'javascript:alert(1)')
        self.pack['sourceOnlyReviews']=[dict(sourceIndex=2, findings=[self.finding])]
        with self.assertRaises(ValueError):render(self.pack, 'https://example.test/pack')
        self.pack['sourceOnlyReviews']=[]
        self.finding['citations']=[]
        with self.assertRaises(ValueError):render(self.pack, 'https://example.test/pack')
        self.finding['humanDecision']='Not a suggestion'
        with self.assertRaises(ValueError):render(self.pack, 'https://example.test/pack')
    def test_native_serialisation_does_not_join_words_across_line_breaks(self):
        self.finding['citations'][0]['quote'] = 'First line\nsecond line\tthird line\r\nfourth line'
        body, _ = render(self.pack, 'https://example.test/pack')
        self.assertIn('First line second line third line fourth line', body)
        self.assertTrue(body.startswith('<p>'))
        self.assertNotIn('line\nsecond', body)
