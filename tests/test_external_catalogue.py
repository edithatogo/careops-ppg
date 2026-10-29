import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

try:
    from scripts.ppg_external_catalogue import page_inventory, payloads, validate, snapshot, reconstruct, changes
    from jsonschema import FormatChecker
    if not {'date-time', 'uri'} <= FormatChecker.checkers.keys():
        raise unittest.SkipTest('Optional external catalogue format profile is not installed; run its hash-locked Python 3.15.1 profile')
except ModuleNotFoundError as error:
    if error.name not in {'bs4', 'jsonschema', 'referencing'}:
        raise
    raise unittest.SkipTest('Optional external catalogue libraries are not installed; run its hash-locked Python 3.15.1 profile') from error


class ExternalCatalogue(unittest.TestCase):
    def fixture(self):
        assertion = dict(field='title', value='Fictional standard',
                         sourceURL='https://www.safetyandquality.gov.au/resources/fictional',
                         sourceSHA256='a'*64, locator='main/h1', observedAt='2026-10-24T01:00:00Z')
        publication = dict(key='pub:fictional', kind='Publication', title='Fictional standard',
                           issuer='Fictional issuer', publicationKey='pub:fictional', editionKey=None,
                           frameworkKeys=[], sourceStatus='Published', role='Normative',
                           requiredCapture=False, assertions=[assertion], data={})
        edition = dict(copy.deepcopy(publication), key='edition:fictional-1', kind='Edition',
                       editionKey='edition:fictional-1')
        return dict(schemaVersion=1, tranche='fictional', observedAt='2026-10-24T01:00:00Z',
                    scope='Fictional only', records=[publication, edition],
                    coverage=dict(collectionEntries=1,included=1,excluded=0,unresolved=0,
                                  referencesInspected=0,localTextGaps=None,fullCollectionComplete=False))

    def test_valid_payloads_do_not_mutate_input_or_accept_clinical_state(self):
        b=self.fixture();before=copy.deepcopy(b)
        rows=payloads(b)
        self.assertEqual(b,before)
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r['ReviewState']=='Proposed' for r in rows))

    def test_duplicate_keys_refused(self):
        b=self.fixture();b['records'].append(copy.deepcopy(b['records'][0]))
        with self.assertRaisesRegex(ValueError,'Duplicate'):validate(b)

    def test_real_format_validation_is_enabled(self):
        from jsonschema import ValidationError
        b=self.fixture();b['observedAt']='not a timestamp'
        with self.assertRaises(ValidationError):validate(b)

    def test_unknown_framework_refused(self):
        b=self.fixture();b['records'][1]['frameworkKeys']=['unknown']
        with self.assertRaisesRegex(ValueError,'framework'):validate(b)

    def test_mismatched_publication_refused(self):
        b=self.fixture();b['records'][1]['publicationKey']='pub:unknown'
        with self.assertRaisesRegex(ValueError,'publication'):validate(b)

    def test_denominator_and_false_completeness_refused(self):
        b=self.fixture();b['coverage']['unresolved']=1
        with self.assertRaisesRegex(ValueError,'denominator'):validate(b)
        b['coverage']['collectionEntries']=2;b['coverage']['fullCollectionComplete']=True
        with self.assertRaisesRegex(ValueError,'Unresolved'):validate(b)

    def test_capture_hash_and_path_binding(self):
        b=self.fixture();raw=b'fictional source'
        c=dict(copy.deepcopy(b['records'][1]),kind='Capture',key='capture:fictional',
               data=dict(file='source.pdf',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
                         sourceURL='https://www.safetyandquality.gov.au/source.pdf'))
        b['records'].append(c)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source.pdf';p.write_bytes(raw);validate(b,capture_root=d)
            p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'bytes'):validate(b,capture_root=d)
            c['data']['file']='../outside.pdf'
            with self.assertRaisesRegex(ValueError,'regular file'):validate(b,capture_root=d)

    def test_source_and_clinical_promotion_refused(self):
        b=self.fixture();b['records'][0]['data']['clinicalApplicabilityAccepted']=True
        with self.assertRaisesRegex(ValueError,'clinical'):validate(b)
        b=self.fixture();b['records'][0]['assertions'][0]['sourceURL']='https://example.com/source'
        with self.assertRaisesRegex(ValueError,'Official'):validate(b)

    def test_library_html_parser_keeps_occurrences_without_minting_identity(self):
        raw=b'<main><h1>Fictional</h1><a href="/a//b">One<a href="/a//b">Two</main>'
        r=page_inventory(raw,'https://www.safetyandquality.gov.au/resources/fixture')
        self.assertEqual(len(r['occurrences']),2)
        self.assertTrue(all(x['url'].endswith('/a//b') for x in r['occurrences']))
        self.assertTrue(all('publicationKey' not in x for x in r['occurrences']))

    def test_missing_main_refused(self):
        with self.assertRaisesRegex(ValueError,'main'):page_inventory(b'<title>Sign in</title>',
            'https://www.safetyandquality.gov.au/resources/fixture')

    def test_native_snapshot_reconstruction_preserves_business_records(self):
        b=self.fixture();rows=payloads(b)
        with tempfile.TemporaryDirectory() as d:
            exported=snapshot(b,rows,d)
            self.assertEqual(reconstruct(exported,d),b)
            self.assertEqual(b,self.fixture())
            rows[0]['Title']='Human correction'
            with self.assertRaisesRegex(ValueError,'drift'):snapshot(b,rows,d)

    def test_recovery_rebinding_is_explicit_and_retains_original(self):
        b=self.fixture();b['records'][0]['data']['relatedRecordsURL']='https://example.sharepoint.com/sites/test/Lists/source/AllItems.aspx?FilterField1=PublicationKey&FilterValue1=pub%3Afictional'
        with tempfile.TemporaryDirectory() as d:
            exported=snapshot(b,payloads(b),d)
            result=reconstruct(exported,d,dict(folderURL='https://example.sharepoint.com/sites/test/recovery',listURL='https://example.sharepoint.com/sites/test/Lists/recovery/AllItems.aspx'))
            self.assertEqual(result['records'][0]['key'],b['records'][0]['key'])
            self.assertIn('/Lists/recovery/',result['records'][0]['data']['relatedRecordsURL'])
            self.assertIn('/Lists/source/',b['records'][0]['data']['relatedRecordsURL'])
            with self.assertRaisesRegex(ValueError,'SharePoint'):reconstruct(exported,d,dict(folderURL='https://example.com/recovery',listURL='https://example.com/list'))

    def test_observation_changes_never_promote_or_withdraw(self):
        result=changes({'a':{'sha':'old'},'b':{'sha':'old'},'c':{'sha':'old'}},
                       {'a':{'sha':'new'},'c':{'error':'timeout'},'d':{'sha':'new'}})
        self.assertEqual([x['state'] for x in result],['changed_review_required','not_observed','retrieval_failed_baseline_held','new_candidate'])
        self.assertTrue(all(not x['baselinePromoted'] and not x['applicabilityAccepted'] for x in result))

    def test_timestamps_or_headers_alone_are_not_policy_changes(self):
        self.assertEqual(changes({'a':{'sha256':'same','observedAt':'old','headers':{'etag':'old'}}},
                                 {'a':{'sha256':'same','observedAt':'new','headers':{'etag':'new'}}})[0]['state'],'unchanged')

    def test_link_injection_is_refused_before_native_payloads(self):
        b=self.fixture();b['records'][0]['data']['sourceURL']='https://example.org/pretend-official'
        with self.assertRaisesRegex(ValueError,'Official'):payloads(b)
        b=self.fixture();b['records'][0]['data']['nativeURL']='javascript:alert(1)'
        with self.assertRaisesRegex(ValueError,'SharePoint'):payloads(b)
        b=self.fixture();b['records'][0]['data']['relatedRecordsURL']='https://example.sharepoint.com/sites/test/redirect.aspx?url=https://example.org'
        with self.assertRaisesRegex(ValueError,'navigation'):payloads(b)

    def test_outside_scope_link_leads_are_accounted_without_fetching(self):
        value=page_inventory(b'<main><h1>Fictional</h1><a href="https://example.org/resource">External lead</a></main>',
                             'https://www.safetyandquality.gov.au/resources/fixture')
        self.assertEqual(value['occurrences'],[])
        self.assertEqual(len(value['outsideSelectedScope']),1)


if __name__=='__main__':unittest.main()
