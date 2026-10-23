"""Committed retention is not authority to ignore arbitrary missing identities."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_source_sync import digest, prepare, retention_contract

A='11111111-1111-4111-8111-111111111111'
B='22222222-2222-4222-8222-222222222222'
C='33333333-3333-4333-8333-333333333333'

class RetentionContractTests(unittest.TestCase):
    def setUp(self):
        self.aliases=[{'source':'example','alias':alias,'DocumentUID':uid} for alias,uid in [('A',A),('B',B)]]
        self.plan=prepare({'sourceSha256':'a'*64,'records':[{'sourceRow':2,'fields':{'sourceDocumentId':'A'}}]},'example',self.aliases,{'sourceDocumentId'})
        self.plan['acknowledgedMissingUIDs']=[B]
        self.ack={'DocumentUID':B,'sourceSha256':'a'*64,'baseContractHash':'b'*64,'actor':'Fictional operator','evidenceReference':'fictional://archive','decisionEvidence':'fictional://decision','effect':'retain_unchanged'}
        self.check={'status':'completed','runId':'fictional-run','sourceSha256':'a'*64,'identityContractHash':self.plan['contractHash'],'readbackCount':1,'catalogueReadbackCount':2,'retainedAbsentUIDs':[B],'retainedAbsentReadbackCount':1,'retainedAbsentUnchanged':True,'lastIdentityApplicationHash':'c'*64,'identityLedger':{'sourceSystemId':'example','aliases':[{'documentUID':u,'sourceDocumentId':a} for a,u in [('A',A),('B',B)]],'sourceAbsenceAcknowledgements':[self.ack]}}
        self.rows=[{'DocumentUID':A,'sourceDocumentId':'A'},{'DocumentUID':B,'sourceDocumentId':'B','sourceStatus':'OVERDUE','localDecision':'retain human note'}]
    def test_verified_exact_source_retention_accounts_every_identity_without_mutation(self):
        before=copy.deepcopy((self.plan,self.check,self.rows));result=retention_contract(self.plan,self.check,self.rows)
        self.assertEqual(result['activeUIDs'],[A]);self.assertEqual(result['retainedUIDs'],[B]);self.assertEqual(result['catalogueUIDs'],[A,B]);self.assertEqual(before,(self.plan,self.check,self.rows))
    def test_unacknowledged_stale_duplicate_unknown_and_unverified_fail(self):
        mutations=[lambda p,c,r:p.pop('acknowledgedMissingUIDs'),lambda p,c,r:c['identityLedger']['sourceAbsenceAcknowledgements'][0].update(sourceSha256='d'*64),lambda p,c,r:p.update(missingUIDs=[B,B]),lambda p,c,r:r.append({'DocumentUID':C}),lambda p,c,r:c.update(retainedAbsentUnchanged=False),lambda p,c,r:c.update(status='failed'),lambda p,c,r:c.update(catalogueReadbackCount=1),lambda p,c,r:c['identityLedger']['aliases'][0].update(sourceDocumentId='changed'),lambda p,c,r:c['identityLedger']['sourceAbsenceAcknowledgements'].append(copy.deepcopy(self.ack)),lambda p,c,r:p['operations'].append(copy.deepcopy(p['operations'][0]))]
        for mutate in mutations:
            p,c,r=copy.deepcopy((self.plan,self.check,self.rows));mutate(p,c,r)
            with self.assertRaises(ValueError):retention_contract(p,c,r)
    def test_comparison_keeps_retained_cases_unresolved_and_stale_absence_held(self):
        from ppg_source_comparison import compare, render
        cases=[{'CaseUID':'fictional-case','linkedDocumentUIDs':[B]}]
        report=compare(self.plan,self.plan,cases,self.check,self.rows)
        self.assertEqual(report['identityAccounting'],{'baselineActive':1,'candidateActive':1,'retained':1,'baselineCatalogue':2})
        self.assertEqual(report['unresolvedCases'][0]['reason'],'retained-source-absence')
        self.assertEqual(report['retainedAbsences'][0]['recordedSourceFields']['sourceStatus'],'OVERDUE')
        self.assertEqual(report['missingUIDs'],[])
        self.assertNotIn('held',report['status'])
        self.assertIn('OVERDUE',render(report))
        later=copy.deepcopy(self.plan);later['sourceSha256']='d'*64
        held=compare(self.plan,later,cases,self.check,self.rows)
        self.assertIn('held',held['status']);self.assertEqual(held['missingUIDs'],[B])
        with self.assertRaises(ValueError):compare(self.plan,self.plan,cases,self.check)
        returned=copy.deepcopy(later);returned['operations'].append({'DocumentUID':B,'sourceRow':3,'fields':{'sourceDocumentId':'B'}})
        returned['rawRecords'].append({'sourceRow':3,'fields':{'sourceDocumentId':'B'}})
        returned.update(inputCount=2,missingUIDs=[],acknowledgedMissingUIDs=[])
        result=compare(self.plan,returned,cases,self.check,self.rows)
        self.assertNotIn('held',result['status']);self.assertEqual(result['unresolvedCases'],[])
        self.assertEqual(result['retainedAbsences'][0]['observedPresence'],'present-active-candidate')

    def test_saved_retained_csv_rejects_missing_duplicate_and_changed_fields(self):
        from verify_monthly_report import verify_retained, safe_text
        from ppg_monthly_report import SOURCE_FIELDS
        row={k:safe_text(self.rows[1].get(k)) for k in SOURCE_FIELDS}
        row.update(DocumentUID=B,Accounting='Retained source absence; current clinical status unresolved; original recorded fields preserved')
        self.assertEqual(verify_retained(self.plan,self.check,self.rows,[row])['totalCatalogueIdentities'],2)
        for saved in [[],[row,row],[dict(row,sourceStatus='CHANGED')],[dict(row,DocumentUID=C)]]:
            with self.assertRaises(ValueError):verify_retained(self.plan,self.check,self.rows,saved)
    def test_boolean_float_string_negative_and_missing_counts_are_refused(self):
        for container, key in [('plan','inputCount'),('check','readbackCount'),('check','catalogueReadbackCount'),('check','retainedAbsentReadbackCount')]:
            for bad in [True,False,1.0,'1',-1,None]:
                p,c,r=copy.deepcopy((self.plan,self.check,self.rows))
                (p if container=='plan' else c)[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):retention_contract(p,c,r)
    def test_returned_identity_preserves_historical_ack_without_consuming_stale_authority(self):
        self.plan['operations'].append({'DocumentUID':B,'sourceRow':3,'fields':{'sourceDocumentId':'B'}});self.plan.update(inputCount=2,sourceSha256='d'*64,missingUIDs=[],acknowledgedMissingUIDs=[])
        self.check.update(sourceSha256='d'*64,readbackCount=2,retainedAbsentUIDs=[],retainedAbsentReadbackCount=0)
        result=retention_contract(self.plan,self.check,self.rows)
        self.assertEqual(result['retainedUIDs'],[]);self.assertEqual(len(self.check['identityLedger']['sourceAbsenceAcknowledgements']),1)
    def test_legacy_complete_contract_still_supported(self):
        p=copy.deepcopy(self.plan);p['operations'].append({'DocumentUID':B,'sourceRow':3,'fields':{'sourceDocumentId':'B'}});p.update(inputCount=2,missingUIDs=[]);p.pop('acknowledgedMissingUIDs')
        c={k:self.check[k] for k in ['status','sourceSha256','identityContractHash']};c['readbackCount']=2
        self.assertEqual(retention_contract(p,c,self.rows)['retainedUIDs'],[])

if __name__=='__main__':unittest.main()
