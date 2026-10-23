import hashlib
import json
import os
from unittest.mock import patch
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_source_surveillance import capture, compare, load_snapshot, render, read_regular_bounded, MAX_CAPTURE_BYTES, MAX_RECEIPT_BYTES


class SurveillanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.config={'familyId':'fictional-policy-family','sources':[{'sourceKey':'fixture-policy','canonicalUrl':'https://example.invalid/policy'}]}
    def snapshot(self,name,body=b'FICTIONAL source edition1',status='captured',version='1',time='2026-10-16T01:00:00Z'):
        observed=dict(sourceKey='fixture-policy',status=status,capturedAtUtc=time)
        if status=='captured':
            p=self.root/(name+'.input');p.write_bytes(body)
            observed.update(file=str(p),canonicalUrl=self.config['sources'][0]['canonicalUrl'],sha256=hashlib.sha256(body).hexdigest(),nativeVersionRef=version,acquisitionRoute='fictional fixture; no native retrieval')
        dest=self.root/name;capture(self.config,[observed],dest);return dest
    def test_capture_preserves_raw_and_refuses_overwrite(self):
        p=self.snapshot('one');snapshot,_=load_snapshot(p);self.assertEqual((p/'fixture-policy.raw').read_bytes(),b'FICTIONAL source edition1');self.assertFalse(snapshot['authorityDetermined'])
        with self.assertRaises(FileExistsError):self.snapshot('one')
    def test_changed_and_unchanged_and_explicit_case_links(self):
        a=self.snapshot('a');b=self.snapshot('b',b'FICTIONAL source edition2');r=compare(a,b,[dict(CaseUID='fictional-case',sourceKeys=['fixture-policy'])]);self.assertEqual(r['changes'][0]['kind'],'captured-bytes-changed');self.assertTrue(r['cases'][0]['potentiallyAffected']);self.assertFalse(r['caseWrites']);self.assertEqual(compare(a,a,[])['changes'][0]['kind'],'unchanged')
    def test_denied_missing_unsupported_error_are_not_deletions(self):
        a=self.snapshot('base')
        for state in ('denied','missing','unsupported','error'):
            b=self.snapshot(state,status=state);r=compare(a,b,[]);self.assertFalse(r['baselinePromotionAllowed']);self.assertEqual(r['changes'][0]['kind'],'source-unavailable-exception');self.assertFalse((b/'fixture-policy.raw').exists())
    def test_failed_baseline_stays_exception(self):
        a=self.snapshot('denied',status='denied');b=self.snapshot('ok');self.assertFalse(compare(a,b,[])['baselinePromotionAllowed'])
    def test_tampered_capture_rejected(self):
        a=self.snapshot('a');(a/'fixture-policy.raw').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'integrity'):load_snapshot(a)
    def test_old_capture_scope_and_unresolved_links_fail_closed(self):
        a=self.snapshot('a');old=self.snapshot('old',time='2026-10-15T01:00:00Z')
        with self.assertRaisesRegex(ValueError,'predates'):compare(a,old,[])
        with self.assertRaisesRegex(ValueError,'links'):compare(a,a,[dict(CaseUID='fictional',sourceKeys=['unknown'])])
        x=json.loads((a/'snapshot.json').read_text());x['sources'][0]['canonicalUrl']='https://example.invalid/other';b=self.snapshot('b');(b/'snapshot.json').write_text(json.dumps(x))
        with self.assertRaisesRegex(ValueError,'binding'):compare(a,b,[])
    def test_failure_content_and_bad_time_rejected_before_output(self):
        for observed in [dict(sourceKey='fixture-policy',status='denied',capturedAtUtc='2026-10-16T01:00:00Z',text='stale secret'),dict(sourceKey='fixture-policy',status='missing',capturedAtUtc='not-a-time')]:
            with self.assertRaises(ValueError):capture(self.config,[observed],self.root/'invalid')
            self.assertFalse((self.root/'invalid').exists())
    def test_version_only_change_is_not_semantic_change(self):
        a=self.snapshot('a');b=self.snapshot('b',version='2');report=compare(a,b,[]);change=report['changes'][0]
        self.assertEqual(change['kind'],'version-reference-changed')
        self.assertEqual(report['familyId'],self.config['familyId'])
        self.assertEqual(change['canonicalUrl'],self.config['sources'][0]['canonicalUrl'])
        self.assertEqual((change['beforeNativeVersionRef'],change['afterNativeVersionRef']),('1','2'))
        for label,directory in [('baselineSnapshot',a),('candidateSnapshot',b)]:
            self.assertEqual(report[label]['receiptSHA256'],hashlib.sha256((directory/'snapshot.json').read_bytes()).hexdigest())
        self.assertNotEqual(report['baselineSnapshot']['receiptSHA256'],report['candidateSnapshot']['receiptSHA256'])
        self.assertEqual(report['caseLinksSHA256'],hashlib.sha256(b'[]').hexdigest())

    def test_bounded_reads_reject_oversize_and_nonregular_before_output(self):
        large=self.root/'large';large.touch()
        with large.open('r+b') as handle:handle.truncate(MAX_CAPTURE_BYTES+1)
        for file in [large,self.root]:
            observation=dict(sourceKey='fixture-policy',status='captured',canonicalUrl=self.config['sources'][0]['canonicalUrl'],capturedAtUtc='2026-10-16T01:00:00Z',file=str(file),sha256='a'*64,acquisitionRoute='fictional')
            with self.assertRaises(ValueError):capture(self.config,[observation],self.root/'invalid')
            self.assertFalse((self.root/'invalid').exists())
        fifo=self.root/'fifo';os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError,'regular'):read_regular_bounded(fifo,10)
        symlink=self.root/'symlink';symlink.symlink_to(large)
        with self.assertRaisesRegex(ValueError,'regular'):read_regular_bounded(symlink,10)

    def test_bounded_read_enforces_limit_after_stat_growth(self):
        file=self.root/'growth';file.write_bytes(b'0123456789abcdef')
        real_fstat=os.fstat
        def stale_fstat(fd):
            value=real_fstat(fd)
            return os.stat_result(tuple(value[:6])+(0,)+tuple(value[7:]))
        with patch('ppg_source_surveillance.os.fstat',side_effect=stale_fstat):
            with self.assertRaisesRegex(ValueError,'limit'):read_regular_bounded(file,8)
        self.assertEqual(file.read_bytes(),b'0123456789abcdef')

    def test_stored_raw_and_receipt_reads_are_bounded(self):
        snapshot=self.snapshot('one');raw=snapshot/'fixture-policy.raw'
        with raw.open('r+b') as handle:handle.truncate(MAX_CAPTURE_BYTES+1)
        with self.assertRaisesRegex(ValueError,'limit'):load_snapshot(snapshot)
        receipt=snapshot/'snapshot.json'
        with receipt.open('r+b') as handle:handle.truncate(MAX_RECEIPT_BYTES+1)
        with self.assertRaisesRegex(ValueError,'limit'):load_snapshot(snapshot)

    def test_failure_receipt_cannot_leak_stale_version_or_content(self):
        a=self.snapshot('a');b=self.snapshot('b',status='denied')
        record=json.loads((b/'snapshot.json').read_text());record['sources'][0]['nativeVersionRef']='denied-secret'
        (b/'snapshot.json').write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError,'denied/stale'):compare(a,b,[])

    def test_failure_comparison_has_only_known_binding_and_no_stale_version(self):
        a=self.snapshot('a');b=self.snapshot('b',status='denied');report=compare(a,b,[])
        change=report['changes'][0]
        self.assertIsNone(change['afterNativeVersionRef']);self.assertIsNone(change['afterSHA256'])
        self.assertEqual(change['canonicalUrl'],self.config['sources'][0]['canonicalUrl'])

    def test_html_report_preserves_provenance_and_escapes_input(self):
        a=self.snapshot('a',version='<script>alert(1)</script>');report=compare(a,a,[])
        rendered=render(report)
        self.assertIn(report['familyId'],rendered)
        self.assertIn(report['baselineSnapshot']['receiptSHA256'],rendered)
        self.assertIn('&lt;script&gt;',rendered);self.assertNotIn('<script>',rendered)

    def test_stored_version_provenance_must_be_text(self):
        a=self.snapshot('a');record=json.loads((a/'snapshot.json').read_text())
        record['sources'][0]['nativeVersionRef']={'unqualified':'value'}
        (a/'snapshot.json').write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError,'version'):load_snapshot(a)

    def test_oversized_receipt_rejected_before_destination_creation(self):
        self.config['familyId']='x'*(MAX_RECEIPT_BYTES+1)
        with self.assertRaisesRegex(ValueError,'receipt exceeds'):self.snapshot('oversized')
        self.assertFalse((self.root/'oversized').exists())



class BrowserReceiptTests(unittest.TestCase):
    def setUp(self):
        import base64
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config={'familyId':'fictional-family','sources':[{'sourceKey':'fixture','canonicalUrl':'https://example.invalid/source'}]}
        body=b'fictional source'
        self.result={'sourceKey':'fixture','canonicalUrl':'https://example.invalid/source',
            'finalUrl':'https://example.invalid/source','capturedAtUtc':'2026-10-23T01:00:00Z',
            'status':200,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),
            'headers':{'etag':'"opaque-version"'},'base64':base64.b64encode(body).decode()}

    def capture(self,result,name='snapshot'):
        from ppg_source_surveillance import capture_browser_receipt
        return capture_browser_receipt(self.config,{'kind':'browser-public-source-capture-v1','results':[result]},self.root/name)

    def test_exact_bytes_and_opaque_header_are_preserved_without_input_mutation(self):
        import copy
        before=copy.deepcopy(self.result)
        receipt=self.capture(self.result)
        self.assertEqual(receipt['sources'][0]['nativeVersionRef'],'etag: "opaque-version"')
        self.assertEqual((self.root/'snapshot/fixture.raw').read_bytes(),b'fictional source')
        self.assertEqual(self.result,before)
        with self.assertRaises(FileExistsError):self.capture(self.result)
        baseline=self.root/'baseline'
        observations=[{'sourceKey':'fixture','canonicalUrl':self.result['canonicalUrl'],
            'capturedAtUtc':self.result['capturedAtUtc'],'status':'captured','file':str(self.root/'snapshot/fixture.raw'),
            'sha256':self.result['sha256'],'nativeVersionRef':'etag: "opaque-version"','acquisitionRoute':'fictional retained receipt'}]
        capture(self.config,observations,baseline)
        self.assertEqual(compare(baseline,self.root/'snapshot',[])['changes'][0]['kind'],'unchanged')

    def test_changed_header_is_not_normalised_away(self):
        import copy
        self.capture(self.result,'before');changed=copy.deepcopy(self.result)
        changed['headers']['etag']='"changed-version"';self.capture(changed,'after')
        self.assertEqual(compare(self.root/'before',self.root/'after',[])['changes'][0]['kind'],'version-reference-changed')

    def test_invalid_body_redirect_and_metadata_refuse_before_destination_creation(self):
        import copy
        for key,value in [('sha256','0'*64),('bytes',1),('base64','%%%'),
                          ('finalUrl','https://other.invalid/source'),('headers',{'etag':'\nspoof'})]:
            bad=copy.deepcopy(self.result);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.capture(bad)
            self.assertFalse((self.root/'snapshot').exists())

    def test_failure_is_body_free_and_never_unchanged_or_retirement(self):
        failure={k:self.result[k] for k in ['sourceKey','canonicalUrl','capturedAtUtc']};failure['status']=403
        result=self.capture(failure)
        self.assertFalse(result['complete']);self.assertEqual(result['sources'][0]['status'],'denied')
        self.assertFalse((self.root/'snapshot/fixture.raw').exists())
        failure['base64']='c3RhbGU='
        with self.assertRaisesRegex(ValueError,'body-free'):self.capture(failure,'bad')
        self.assertFalse((self.root/'bad').exists())

    def test_missing_etag_stays_unknown_and_duplicate_sources_refuse(self):
        import copy
        x=copy.deepcopy(self.result);x['headers']={'etag':None}
        self.assertIsNone(self.capture(x)['sources'][0]['nativeVersionRef'])
        from ppg_source_surveillance import capture_browser_receipt
        with self.assertRaises(ValueError):capture_browser_receipt(self.config,
            {'kind':'browser-public-source-capture-v1','results':[x,x]},self.root/'duplicate')


if __name__=='__main__':unittest.main()
