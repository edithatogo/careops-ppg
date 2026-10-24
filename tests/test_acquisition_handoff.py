import copy
import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_acquisition_handoff import prepare, main, read_json


def fixture():
    raw = b'%PDF-1.4\nFICTIONAL retained original\n%%EOF\n'
    sha = hashlib.sha256(raw).hexdigest()
    source = 'https://publisher.example/a//source.pdf'
    profile = dict(qualificationId='11111111-2222-4333-8444-555555555555', sourceKey='fictional-source',
                   frameworkEditionId='fictional-1', sourceURL=source, allowedOrigins=['https://publisher.example'],
                   stagingRoot='/Fictional qualification', ownershipEvidence='FICTIONAL existing capture selection',
                   connectionReference=dict(id='/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness',
                                            connectionName='fictional-existing', source='Embedded'),
                   expectedBytes=len(raw), expectedSHA256=sha)
    assertion = dict(field='edition', value='Fictional edition one', sourceURL=source,
                     sourceSHA256=sha, locator='Fictional cover', observedAt='2026-10-24T01:00:00Z')
    pub = dict(key='pub:fictional', kind='Publication', title='Fictional publication', issuer='Fictional issuer',
               publicationKey='pub:fictional', editionKey=None, frameworkKeys=[], sourceStatus='Unknown',
               role='Normative', requiredCapture=True, assertions=[assertion], data={})
    edition = dict(copy.deepcopy(pub), key='edition:fictional-1', kind='Edition',
                   editionKey='edition:fictional-1', frameworkKeys=['fictional-1'])
    cap = dict(copy.deepcopy(edition), key='capture:existing-consumer-key', kind='Capture',
               data=dict(sha256=sha, bytes=len(raw), sourceURL=source,
                         nativeURL='https://example.sharepoint.com/sites/Fictional/Evidence/retained.pdf',
                         acquiredAt='2026-10-23T01:00:00Z', editionResolution='source-asserted',
                         acquisitionRoute='Earlier independent retained original'))
    selection = dict(publication=pub, edition=edition, capture=cap, knownFrameworkKeys=['fictional-1'])
    result = dict(kind='ppg-supplied-byte-hash-result-v1', qualificationId=profile['qualificationId'],
                  sourceKey=profile['sourceKey'], actualBytes=len(raw), actualSHA256=sha,
                  expectedSHA256=sha, integrityMatches=True, sourceProvenanceAuthenticated=False,
                  nativeAcquisitionQualified=False)
    observation = dict(observedAt='2026-10-24T01:00:00Z', workflowId='fictional-flow', runId='fictional-run-1',
                       receiptSHA256='a'*64, sourceFile=dict(uniqueId='fictional-native-file', nativeVersion='1.0',
                       etag='"fictional,1"', url='https://example.sharepoint.com/sites/Fictional/Staging/source.pdf',
                       bytes=len(raw)))
    return selection, profile, result, observation, raw


class AcquisitionHandoffTests(unittest.TestCase):
    def test_existing_capture_reused_without_rewriting_history_or_claiming_provenance(self):
        args = fixture(); before = copy.deepcopy(args); out = prepare(*args)
        self.assertEqual(out['state'], 'reuse-existing-capture')
        self.assertEqual(out['selectedRecords'], args[0]); self.assertEqual(args, before)
        self.assertEqual(out['binding']['captureKey'], 'capture:existing-consumer-key')
        self.assertEqual(out['selectedRecords']['capture']['data']['acquiredAt'], '2026-10-23T01:00:00Z')
        self.assertEqual(out['originalFilesToCreate'], []); self.assertEqual(out['catalogueEdits'], [])
        for k in ['providedEvidenceAuthenticated', 'nativeMutationAllowed', 'checkpointAllowed',
                  'fullAcquisitionQualified', 'clinicalApplicabilityAccepted']:
            self.assertIs(out[k], False)

    def test_new_run_retains_occurrence_without_duplicating_capture_replay_identity(self):
        args = fixture(); first = prepare(*args)
        args[3]['runId'] = 'fictional-run-2'; args[3]['observedAt'] = '2026-10-24T02:00:00Z'
        args[1]['qualificationId'] = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
        args[2]['qualificationId'] = args[1]['qualificationId']
        second = prepare(*args)
        self.assertEqual(first['replayKey'], second['replayKey'])
        self.assertNotEqual(first['occurrenceKey'], second['occurrenceKey'])
        self.assertEqual(first['binding']['captureKey'], second['binding']['captureKey'])

    def test_identical_bytes_in_a_different_selected_edition_keep_distinct_replay_keys(self):
        args=fixture();first=prepare(*args)
        args[0]['knownFrameworkKeys'].append('fictional-2')
        args[0]['edition']['key']='edition:fictional-2'
        args[0]['edition']['editionKey']='edition:fictional-2'
        args[0]['edition']['frameworkKeys']=['fictional-2']
        args[0]['capture']['key']='capture:another-existing-key'
        args[0]['capture']['editionKey']='edition:fictional-2'
        args[0]['capture']['frameworkKeys']=['fictional-2']
        args[1]['frameworkEditionId']='fictional-2'
        second=prepare(*args)
        self.assertNotEqual(first['replayKey'],second['replayKey'])
        self.assertEqual(first['binding']['sha256'],second['binding']['sha256'])

    def test_distinct_locators_do_not_normalise_on_matching_bytes(self):
        args = fixture(); args[1]['sourceURL'] = 'https://publisher.example/a/source.pdf'
        out = prepare(*args)
        self.assertEqual(out['state'], 'held-locator-evidence'); self.assertFalse(out['sourceLocatorExact'])
        self.assertNotEqual(out['catalogueSourceURL'], out['binding']['requestedSourceURL'])

    def test_explicit_two_locator_evidence_permits_reuse_but_never_proves_redirects(self):
        args = fixture(); args[1]['sourceURL'] = 'https://publisher.example/a/source.pdf'
        evidence = [dict(url=u, sha256=args[1]['expectedSHA256'], bytes=len(args[4]), receiptSHA256=c*64)
                    for u,c in [(args[1]['sourceURL'],'a'),(args[0]['capture']['data']['sourceURL'],'b')]]
        self.assertEqual(prepare(*args, evidence)['state'], 'reuse-existing-capture')
        self.assertEqual(prepare(*args, evidence[:1])['state'], 'held-locator-evidence')
        self.assertFalse(prepare(*args, evidence)['providedEvidenceAuthenticated'])
        evidence[1]['sha256'] = '0'*64
        with self.assertRaises(ValueError): prepare(*args, evidence)

    def test_unknown_edition_stays_held_without_assigning_latest(self):
        args = fixture(); args[0]['edition'] = None; cap=args[0]['capture']
        cap['editionKey'] = None; cap['data']['editionResolution'] = 'unverified'
        out=prepare(*args); self.assertEqual(out['state'], 'held-edition-unverified')
        self.assertIsNone(out['binding']['editionKey'])

    def test_cross_publication_and_framework_conflicts_refuse(self):
        for target, field, value in [('capture','publicationKey','pub:other'),
                                      ('edition','editionKey','edition:other'),
                                      ('capture','editionKey','edition:other'),
                                      ('edition','frameworkKeys',['other']),
                                      ('capture','frameworkKeys',[])]:
            args=fixture();args[0][target][field]=value
            with self.subTest(target=target,field=field), self.assertRaises(ValueError):prepare(*args)

    def test_digest_length_and_same_size_corruption_refuse(self):
        args=fixture();bad=bytes([args[4][0]^1])+args[4][1:]
        with self.assertRaises(ValueError):prepare(*args[:4],bad)
        for field,value in [('sha256','0'*64),('bytes',True),('bytes',1)]:
            args=fixture();args[0]['capture']['data'][field]=value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):prepare(*args)

    def test_native_result_identity_hash_and_premature_acceptance_refuse(self):
        for field,value in [('qualificationId','other'),('sourceKey','other'),('actualBytes',True),
                            ('actualSHA256','0'*64),('expectedSHA256','0'*64),('integrityMatches',False),
                            ('sourceProvenanceAuthenticated',True),('nativeAcquisitionQualified',True)]:
            args=fixture();args[2][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):prepare(*args)

    def test_occurrence_requires_time_and_stable_native_pin(self):
        for field,value in [('observedAt','2026-10-24T01:00:00'),('observedAt','2026-02-30T00:00:00Z'),
                            ('receiptSHA256','bad'),('runId','')]:
            args=fixture();args[3][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):prepare(*args)
        for field,value in [('nativeVersion',1),('etag','*'),('bytes',True),
                            ('url','https://example.sharepoint.com/file.pdf?token=fictional')]:
            args=fixture();args[3]['sourceFile'][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):prepare(*args)

    def test_source_boundaries_and_clinical_state_refuse(self):
        for field,value in [('nativeURL','https://publisher.example/private.pdf'),
                            ('sourceURL','https://other.example/source.pdf'),('clinicalApplicabilityAccepted',True)]:
            args=fixture();args[0]['capture']['data'][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):prepare(*args)

    def test_evidence_duplicates_and_unbounded_entries_refuse(self):
        args=fixture();e=dict(url=args[1]['sourceURL'],sha256=args[1]['expectedSHA256'],
                             bytes=len(args[4]),receiptSHA256='a'*64)
        for evidence in [[e,e],[e]*9,[dict(e,extra='refuse')]]:
            with self.assertRaises(ValueError):prepare(*args,evidence)

    def test_cli_create_only_and_strict_json_input(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);args=fixture();cli=[]
            for name,value in zip(['selection','profile','native-result','observation'],args):
                f=p/(name+'.json');f.write_text(json.dumps(value));cli+=['--'+name,str(f)]
            original=p/'original.pdf';original.write_bytes(args[4]);out=p/'handoff.json'
            cli+=['--original',str(original),'--output',str(out)]
            self.assertEqual(main(cli),0);first=out.read_bytes()
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):main(cli)
            self.assertEqual(out.read_bytes(),first);self.assertEqual(original.read_bytes(),args[4])
            for text in ['{"a":1,"a":2}', '{"a":NaN}', ' '* (1024*1024+1)]:
                bad=p/'bad.json';bad.write_text(text)
                with self.assertRaises(ValueError):read_json(bad)


if __name__ == '__main__':
    unittest.main()
