"""Exercise the selected-file reader against failures without claiming native ACL proof."""
import json
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


class EvidenceReadTests(unittest.TestCase):
    def run_reader(self, mode, extension='txt', overrides=None, remove=(), after_only=False):
        source=(ROOT/'tools/cited-evidence/read.js').read_text()
        program="""
const crypto=require('node:crypto').webcrypto;
const location={origin:'https://example.invalid'};
let calls=[];let metaCount=0;
const mode=MODE;
const fetch=async(url,options={})=>{
 calls.push({url,method:options.method||'GET'});
 if(mode==='denied')return new Response('SECRET DENIED BODY',{status:403});
 if(url.includes('$value'))return mode==='content-denied'?new Response('SECRET',{status:403}):new Response('FICTIONAL text\\n');
 metaCount++;
 const metadata={Name:'source.EXT',Length:15,UniqueId:'11111111-1111-4111-8111-111111111111',ETag:mode==='changed'&&metaCount>1?'version2':'version1',MajorVersion:1,MinorVersion:0,TimeLastModified:'2026-10-16T00:00:00Z'};
 if(!AFTER_ONLY||metaCount>1){for(const key of REMOVE_KEYS)delete metadata[key];Object.assign(metadata,OVERRIDES);}
 return new Response(JSON.stringify(metadata));
};
SOURCE
readCitedEvidence({sitePath:'/sites/ppg',allowedFolder:'/sites/ppg/evidence',sources:[{sourceId:'fictional-1',path:'/sites/ppg/evidence/source.EXT',authorityLabel:'captured-reference-unconfirmed'}]}).then(result=>process.stdout.write(JSON.stringify({result,calls})));
""".replace('MODE',json.dumps(mode)).replace('EXT',extension).replace('SOURCE',source).replace('AFTER_ONLY',json.dumps(after_only)).replace('REMOVE_KEYS',json.dumps(list(remove))).replace('OVERRIDES',json.dumps(overrides or {}))
        return json.loads(subprocess.check_output(['node','-e',program],text=True))
    def test_readable_versioned_source_and_get_only(self):
        r=self.run_reader('success');s=r['result']['sources'][0];self.assertEqual(s['status'],'retrieved');self.assertEqual(s['text'],'FICTIONAL text\n');self.assertEqual(len(r['calls']),3);self.assertTrue(all(c['method']=='GET' for c in r['calls']))
    def test_metadata_denial_stops_before_body_and_redacts(self):
        r=self.run_reader('denied');self.assertEqual(len(r['calls']),1);self.assertEqual(r['result']['sources'],[{'sourceId':'fictional-1','status':'denied'}]);self.assertNotIn('SECRET',json.dumps(r))
    def test_content_denial_does_not_return_accessible_metadata(self):
        r=self.run_reader('content-denied');self.assertEqual(r['result']['sources'],[{'sourceId':'fictional-1','status':'denied'}])
    def test_changed_version_discards_content(self):
        r=self.run_reader('changed');self.assertEqual(r['result']['sources'],[{'sourceId':'fictional-1','status':'changed-during-read'}])
    def test_unsupported_capture_not_downloaded_or_assumed_absent(self):
        r=self.run_reader('success','captured');self.assertEqual(len(r['calls']),1);self.assertEqual(r['result']['sources'],[{'sourceId':'fictional-1','status':'unsupported'}])

    def test_missing_native_metadata_stops_before_content(self):
        for key in ('UniqueId','Name','Length','ETag','MajorVersion','MinorVersion','TimeLastModified'):
            with self.subTest(key=key):
                r=self.run_reader('success',remove=[key])
                self.assertEqual(len(r['calls']),1)
                self.assertEqual(r['result']['sources'],[{'sourceId':'fictional-1','status':'unsupported'}])

    def test_invalid_native_metadata_stops_before_content(self):
        cases={'Length':[None,True,-1,'NaN','Infinity','',1.5,10**25],
               'UniqueId':['',42,'fictional-native-id','00000000-0000-0000-0000-000000000000'],
               'ETag':[' ',None,2],'MajorVersion':[-1,'1',None,1.5],
               'MinorVersion':[-1,'0',None],
               'TimeLastModified':['not-a-date','2026-02-30T00:00:00Z','2026-10-16T00:00:00','2026-10-16T10:00:00+10:00']}
        for key,values in cases.items():
            for value in values:
                with self.subTest(key=key,value=value):
                    r=self.run_reader('success',overrides={key:value})
                    self.assertEqual(len(r['calls']),1)
                    self.assertEqual(r['result']['sources'][0]['status'],'unsupported')
                    self.assertNotIn('text',r['result']['sources'][0])

    def test_second_metadata_validation_and_version_changes_discard_content(self):
        for key,value in [('UniqueId',None),('Length','NaN'),('MajorVersion',2),
                          ('MinorVersion',1),('Name','other.txt'),('TimeLastModified','invalid')]:
            with self.subTest(key=key):
                r=self.run_reader('success',overrides={key:value},after_only=True)
                self.assertEqual(len(r['calls']),3)
                self.assertEqual(r['result']['sources'],[{'sourceId':'fictional-1','status':'changed-during-read'}])

    def test_declared_length_must_match_downloaded_bytes(self):
        r=self.run_reader('success',overrides={'Length':14})
        self.assertEqual(r['result']['sources'][0]['status'],'unsupported')
        self.assertNotIn('text',r['result']['sources'][0])

    def test_string_length_and_utc_offset_are_supported(self):
        r=self.run_reader('success',overrides={'Length':'15','TimeLastModified':'2026-10-16T00:00:00+00:00'})
        self.assertEqual(r['result']['sources'][0]['status'],'retrieved')


if __name__=='__main__':unittest.main()
