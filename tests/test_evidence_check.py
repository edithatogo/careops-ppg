import copy
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_evidence_check import check_answer, in_scope


def fixture():
    text='FICTIONAL captured reference\nThe interval is12months.\nCurrent authority is unconfirmed.\n'
    s=dict(nativeUniqueId='11111111-1111-4111-8111-111111111111',sourceId='fictional-1',canonicalUrl='https://example.invalid/sites/ppg/source.txt',nativeVersionRef='1.0',retrievedAtUtc='2026-10-16T00:00:00Z',authorityLabel='captured-reference-unconfirmed',status='retrieved',sha256=hashlib.sha256(text.encode()).hexdigest(),text=text)
    c={k:s[k] for k in ('sourceId','canonicalUrl','nativeVersionRef','sha256','authorityLabel')};c.update(startLine=2,endLine=2,quote='The interval is12months.')
    a=dict(questionId='fictional-q',status='supported',claims=[dict(claimId='claim1',text='The captured text states12months.',assertsCurrentAuthority=False,citations=[c])],limitations=['Current authority unconfirmed'],actionsPerformed=[],policyApproved=False)
    return a,[s]


class EvidenceCheckTests(unittest.TestCase):
    def check(self,a,s):return check_answer(a,s,'https://example.invalid/sites/ppg/')
    def test_exact_citation_does_not_establish_semantics_or_promotion(self):
        a,s=fixture();r=self.check(a,s);self.assertTrue(r['mechanicallyValid']);self.assertFalse(r['promotionReady']);self.assertIn('not assessed',r['semanticEntailment'])
    def test_stale_hash_version_and_wrong_quote_rejected(self):
        for key,value in [('sha256','b'*64),('nativeVersionRef','2.0'),('quote','invented')]:
            a,s=fixture();a['claims'][0]['citations'][0][key]=value;self.assertFalse(self.check(a,s)['mechanicallyValid'])
    def test_denied_missing_unsupported_not_citable(self):
        for state in ('denied','missing','unsupported','changed-during-read'):
            a,s=fixture();s[0]={'sourceId':'fictional-1','status':state};self.assertIn('citation_source_not_retrieved',self.check(a,s)['issues'])
    def test_approval_write_and_uncited_claim_rejected(self):
        a,s=fixture();a.update(policyApproved=True,actionsPerformed=['write']);self.assertIn('write_or_approval_claim',self.check(a,s)['issues']);a,s=fixture();a['claims'][0]['citations']=[];self.assertFalse(self.check(a,s)['mechanicallyValid'])
    def test_archive_label_and_locator_fail_closed(self):
        a,s=fixture();c=a['claims'][0]['citations'][0];c['authorityLabel']='current';c['startLine']=0;self.assertFalse(self.check(a,s)['mechanicallyValid'])
    def test_scope_excludes_lookalikes_traversal_signed_links(self):
        for u in ('https://example.invalid.evil/sites/ppg/source.txt','https://example.invalid/sites/ppg/../../secret','https://example.invalid/sites/ppg/source.txt?token=secret'):
            self.assertFalse(in_scope(u,'https://example.invalid/sites/ppg/'))
    def test_source_content_tampering_and_denied_content_rejected(self):
        a,s=fixture();s[0]['text']='changed';self.assertFalse(self.check(a,s)['mechanicallyValid']);a,s=fixture();s[0]['status']='denied';self.assertTrue(any('unreadable_source_contains_content' in x for x in self.check(a,s)['issues']))
    def test_unknown_and_refused_have_no_claims(self):
        for state in ('unknown','refused'):
            a=dict(status=state,claims=[],actionsPerformed=[],policyApproved=False);self.assertTrue(self.check(a,[])['mechanicallyValid']);a['claims']=[{}];self.assertFalse(self.check(a,[])['mechanicallyValid'])

    def test_receipt_requires_valid_native_identity(self):
        for value in (None,'','fictional-native-id',123,'00000000-0000-0000-0000-000000000000'):
            with self.subTest(value=value):
                a,s=fixture();s[0]['nativeUniqueId']=value
                self.assertFalse(self.check(a,s)['mechanicallyValid'])

    def test_jointly_invalid_receipt_and_citation_labels_rejected(self):
        a,s=fixture();s[0]['authorityLabel']='current-approved'
        a['claims'][0]['citations'][0]['authorityLabel']='current-approved'
        self.assertIn('invalid_authority_label:fictional-1',self.check(a,s)['issues'])

    def test_invalid_source_status_rejected_even_without_claims(self):
        a={'status':'unknown','claims':[],'actionsPerformed':[],'policyApproved':False}
        r=self.check(a,[{'sourceId':'fictional-1','status':'accepted'}])
        self.assertIn('invalid_source_status:fictional-1',r['issues'])

    def test_retrieval_time_requires_valid_explicit_utc(self):
        for value in ('not-a-date','2026-02-30T00:00:00Z','2026-10-16',
                      '2026-10-16T00:00:00','2026-10-16T10:00:00+10:00'):
            with self.subTest(value=value):
                a,s=fixture();s[0]['retrievedAtUtc']=value
                self.assertIn('invalid_retrieval_time:fictional-1',self.check(a,s)['issues'])
        a,s=fixture();s[0]['retrievedAtUtc']='2026-10-16T00:00:00+00:00'
        self.assertTrue(self.check(a,s)['mechanicallyValid'])


if __name__=='__main__':unittest.main()
