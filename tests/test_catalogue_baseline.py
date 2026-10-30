import copy
import unittest
from scripts.ppg_catalogue_baseline import prepare

class CatalogueBaselineTests(unittest.TestCase):
    def setUp(self):
        self.uid='10000000-0000-4000-8000-000000000001'
        self.rows=[{'DocumentUID':self.uid,'Title':'Fictional','sourceTitle':'Fictional'}]
        self.cp={'status':'completed','sourceSha256':'a'*64,'identityLedger':{'aliases':[{'documentUID':self.uid,'sourceDocumentId':'EX1'}]},'readbackCount':1,'catalogueReadbackCount':1,'asOfUtc':'2026-01-01T00:00:00Z'}
        self.candidate={'sourceSha256':'a'*64,'operations':[{'DocumentUID':self.uid,'fields':{'sourceTitle':'Fictional'}}]}
    def test_retains_date_and_does_not_claim_current_reconciliation(self):
        out=prepare(self.rows,self.cp,self.candidate)
        self.assertEqual(out['baselineAsOf'],self.cp['asOfUtc'])
        self.assertFalse(out['currentSourceReconciled'])
        self.assertFalse(out['absenceAcknowledgementsExtended'])
    def test_changed_source_or_unaccounted_identity_refused(self):
        self.rows[0]['sourceTitle']='Changed'
        with self.assertRaises(ValueError):prepare(self.rows,self.cp,self.candidate)
        self.rows[0]['sourceTitle']='Fictional'
        with self.assertRaises(ValueError):prepare(self.rows*2,self.cp,self.candidate)
    def test_retained_absent_identity_is_not_deleted_or_renewed(self):
        uid='20000000-0000-4000-8000-000000000002'
        self.rows.append({'DocumentUID':uid});self.cp['identityLedger']['aliases'].append({'documentUID':uid})
        self.cp.update(retainedAbsentUIDs=[uid],catalogueReadbackCount=2)
        out=prepare(self.rows,self.cp,self.candidate)
        self.assertEqual((out['activeCount'],out['retainedAbsentCount']),(1,1))

    def test_checkpoint_rebinding_keeps_existing_fixture_path_distinct(self):
        from scripts.ppg_installation_paths import bind_checkpoint
        value={'read':"/Evidence/qw3-last-successful.json')/$value",'other':'old-qw3-last-successful.json'}
        result=bind_checkpoint(value,'commissioned-baseline.json')
        self.assertEqual(result['read'],"/Evidence/commissioned-baseline.json')/$value")
        self.assertEqual(result['other'],value['other'])
        with self.assertRaises(ValueError):bind_checkpoint(value,'../old.json')
