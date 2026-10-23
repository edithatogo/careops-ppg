import copy
import hashlib
import unittest
from scripts.ppg_passage_findings import build
from scripts.ppg_findings_annotations import payloads


class FindingsAnnotations(unittest.TestCase):
    def setUp(self):
        self.raw=b'fictional inspection';self.sha=hashlib.sha256(self.raw).hexdigest()
        self.inv=dict(sourceSha256=self.sha,sourceAuthority='Historical unverified',elements=[dict(sourceLocator='body#1',text='Example text')])
        prep=dict(subject=dict(documentUID='fictional',documentVersion='current-request'),reviewChecklist=[dict(criterionId='quality')],decisionOptions=['minor_revision'])
        f=dict(findingId='f1',criterionId='quality',claimType='inference',suggestedAction='minor_revision',statement='Clarify wording',benefit='Clarity',effort='low',dependencies='Verified source',uncertainty='Current version unavailable',citations=[dict(sourceSha256=self.sha,locator='body#1',quote='Example')])
        self.pack=build(prep,self.inv,self.raw,[f])

    def test_stable_key_explicit_historical_scope_and_no_decision(self):
        a=payloads(self.pack,self.inv,self.raw,'https://example.test/pack')
        b=payloads(self.pack,self.inv,self.raw,'https://example.test/pack')
        self.assertEqual(a,b)
        self.assertEqual(a[0]['ReviewState'],'Received')
        self.assertNotEqual(a[0]['DocumentVersion'],'current-request')
        self.assertIn('ASSISTANT DRAFT',a[0]['OriginalSuggestion'])
        self.assertNotIn('DecisionRationale',a[0])
        self.assertNotIn('IncorporatedVersion',a[0])

    def test_revalidates_quotes_and_source_before_insert(self):
        bad=copy.deepcopy(self.pack);bad['findings'][0]['citations'][0]['quote']='invented'
        with self.assertRaises(ValueError):payloads(bad,self.inv,self.raw,'https://example.test/pack')
        with self.assertRaises(ValueError):payloads(self.pack,self.inv,b'changed','https://example.test/pack')
        with self.assertRaises(ValueError):payloads(self.pack,self.inv,self.raw,'local file')
