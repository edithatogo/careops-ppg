import copy
import hashlib
import unittest
from scripts.ppg_relationship_context import reference_candidates, review_context


class RelationshipContext(unittest.TestCase):
    def test_no_cross_version_traversal_or_proposal_promotion(self):
        def edge(key,a,av,b,bv,state='accepted',kind='governed_by'):
            return dict(relationshipId=key,fromDocumentUID=a,fromVersion=av,toDocumentUID=b,toVersion=bv,status=state,type=kind)
        rows=[edge('1','a','1','b','1'),edge('2','b','2','c','1'),
              edge('3','child','1','a','1'),edge('4','a','1','x','1','proposed'),
              edge('5','b','1','a','1',kind='references')]
        result=review_context(rows,'a','1')
        self.assertEqual([x['documentUID'] for x in result['acceptedUpstream']],['b'])
        self.assertEqual([x['documentUID'] for x in result['acceptedDownstream']],['child'])
        self.assertEqual(len(result['directProposed']),1)
        current=review_context(rows,'a','2')
        self.assertFalse(current['acceptedUpstream']);self.assertEqual(len(current['otherEditionLinks']),4)
        with self.assertRaises(ValueError):review_context(rows+[edge('6','b','1','a','1')],'a','1')

    def fixture(self):
        raw=b'fictional source';sha=hashlib.sha256(raw).hexdigest()
        inv=dict(sourceSha256=sha,elements=[dict(sourceLocator='body#1',text='Refer to X')])
        lead=dict(suggestedType='references',sourceSha256=hashlib.sha256(b'original').hexdigest(),derivedPackageSha256=sha,
                  sourceLocator='body#1',sourcePassage='Refer to X',targetCandidates=[dict(documentUID='x',sourceDocumentId='X-1',title='X',coverage='metadata_only')])
        return raw,inv,lead

    def test_unresolved_targets_not_invented_and_quotes_checked(self):
        raw,inv,lead=self.fixture()
        original=copy.deepcopy(lead)
        result=reference_candidates('a',[lead],inv,raw,b'original')
        self.assertEqual(result['records'][0]['ReviewState'],'Proposed')
        self.assertEqual(lead,original)
        lead['targetCandidates']=[]
        self.assertEqual(len(reference_candidates('a',[lead],inv,raw,b'original')['unresolved']),1)
        lead['sourcePassage']='Invented'
        with self.assertRaises(ValueError):reference_candidates('a',[lead],inv,raw,b'original')
        with self.assertRaises(ValueError):reference_candidates('a',[original],inv,b'changed',b'original')

    def test_supersession_history_is_not_governing_authority(self):
        row=dict(relationshipId='s',fromDocumentUID='new',fromVersion='2',
                 toDocumentUID='old',toVersion='1',status='accepted',type='supersedes')
        r=review_context([row],'new','2')
        self.assertFalse(r['acceptedUpstream'])
        self.assertEqual(r['acceptedSupersedes'][0]['documentUID'],'old')
        self.assertEqual(review_context([row],'old','1')['acceptedSupersededBy'][0]['documentUID'],'new')
