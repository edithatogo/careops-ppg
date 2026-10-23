import json
import unittest
from scripts.ppg_projection_library_metadata import properties, decode_description


class ProjectionLibraryMetadata(unittest.TestCase):
    def run_record(self,date):
        return dict(manifest=dict(asOf=date,runKey=('a' if date.endswith('01') else 'b')*64,sourceSha256='c'*64,projectionLogicSha256='d'*64,roleContractSha256='e'*64,sourceModified=False,grantsAccess=False,grantsClinicalAuthority=False),projection=dict(asOf=date))

    def test_bundle_retains_each_date_source_and_run_without_claiming_live_state(self):
        raw=json.dumps([self.run_record('2026-06-01'),self.run_record('2026-06-02')]).encode()
        result=properties(raw);description=json.loads(result['_ExtendedDescription'])
        self.assertEqual(len(description['runs']),2)
        self.assertFalse(description['liveResponsibility'])
        self.assertNotIn('PPGCoverReviewDate',result)
        self.assertEqual(result,properties(raw))

    def test_bad_date_binding_duplicate_identity_and_authority_refused(self):
        r=self.run_record('2026-06-01')
        with self.assertRaises(ValueError):properties(json.dumps([r,r]).encode())
        r['projection']['asOf']='2026-01-01'
        with self.assertRaises(ValueError):properties(json.dumps([r]).encode())
        r=self.run_record('2026-06-01');r['manifest']['grantsAccess']=True
        with self.assertRaises(ValueError):properties(json.dumps([r]).encode())

    def test_encoded_description_is_decoded_once_and_missing_read_is_not_an_update(self):
        value='&#123;&quot;liveResponsibility&quot;&#58; false&#125;'
        self.assertEqual(decode_description(value),{'liveResponsibility':False})
        with self.assertRaises(ValueError):decode_description(None)
        with self.assertRaises(ValueError):decode_description('&amp;#123;')
