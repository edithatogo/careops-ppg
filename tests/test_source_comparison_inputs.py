import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_source_sync import prepare
from ppg_source_comparison_inputs import qualify

class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.aliases=[{'source':'example','alias':'A','DocumentUID':'11111111-1111-4111-8111-111111111111'}]
        self.records=[{'sourceRow':2,'fields':{'sourceDocumentId':'A'}}]
        self.base=prepare({'sourceSha256':'a'*64,'records':self.records},'example',self.aliases,{'sourceDocumentId'})
        self.old={'metadata':{'ETag':'old','UniqueId':'source'}}
        self.new={'metadata':{'ETag':'new','UniqueId':'source'},'acquiredAtUtc':'2026-10-16T03:12:59Z'}
        self.check={'status':'completed','sourceSha256':'a'*64,'readbackCount':1,'centralSourceETag':'old','identityContractHash':self.base['contractHash']}
        self.state={'sourceETag':'new','checkedUtc':'2026-10-16T03:13:00Z'}
        self.ledger={'sourceSystemId':'example','aliases':[{'sourceDocumentId':'A','documentUID':self.aliases[0]['DocumentUID']}]}

    def run_qualification(self, results=None):
        with patch('ppg_source_comparison_inputs.extract',side_effect=results or [('a'*64,self.records),('b'*64,self.records)]):
            return qualify(self.base,self.old,self.new,self.check,self.state,self.ledger,[],[{'mirror_field':'sourceDocumentId'}],'https://example.test/raw.json')

    def test_verified_baseline_and_retained_reference(self):
        candidate,report=self.run_qualification()
        self.assertEqual(report['qualification']['nativeBaselineParityCells'],1)
        self.assertEqual(candidate['provenance']['rawSnapshotRef'],'https://example.test/raw.json')
        self.assertFalse(report['checkpointAdvanced'])

    def test_wrong_observed_version_rejected(self):
        self.state['sourceETag']='other'
        with self.assertRaisesRegex(ValueError,'observed source'):
            self.run_qualification()

    def test_parser_drift_rejected(self):
        bad=copy.deepcopy(self.records);bad[0]['fields']['sourceDocumentId']='wrong'
        with self.assertRaisesRegex(ValueError,'parser'):
            self.run_qualification([('a'*64,bad),('b'*64,self.records)])

    def test_contract_or_checkpoint_drift_rejected(self):
        self.ledger['aliases'][0]['sourceDocumentId']='changed'
        with self.assertRaisesRegex(ValueError,'identity contract'):
            self.run_qualification()
        self.check['readbackCount']=2
        with self.assertRaisesRegex(ValueError,'baseline mismatch'):
            self.run_qualification()

if __name__=='__main__':unittest.main()
