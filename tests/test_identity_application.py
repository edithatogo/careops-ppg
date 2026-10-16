import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_identity_triage import inspect, proposal, transition
from ppg_identity_application import compile_application, verify_application

class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.a='00000000-0000-4000-8000-000000000001'
        self.b='00000000-0000-4000-8000-000000000002'
        self.ledger={'sourceSystemId':'fictional','aliases':[{'source':'fictional','alias':'A','DocumentUID':self.a}]}
        self.snapshot={'sourceSha256':'a'*64,'records':[
            {'sourceRow':2,'fields':{'sourceDocumentId':'A','sourceTitle':'existing'}},
            {'sourceRow':987,'fields':{'sourceDocumentId':'B','sourceTitle':'new'}}]}
        self.allowed={'sourceDocumentId','sourceTitle'}
        r=inspect(self.snapshot,'fictional',self.ledger,self.allowed)
        p=proposal(r,r['exceptions'][0]['exceptionKey'])
        p.update(resolution='request_new_uid',rationale='Fictional distinct source identity',evidenceReferences=['fictional://proof'])
        self.p=transition(p,'accepted','fictional://decision','Fictional operator')
        self.auth={'exceptionKey':self.p['exceptionKey'],'DocumentUID':self.b,'actor':'Fictional operator','evidenceReference':'fictional://new-identity-authorisation'}
    def compile(self):
        return compile_application(self.snapshot,self.ledger,self.allowed,[self.p],[self.auth])
    def test_explicit_new_identity_and_exact_verification(self):
        before=copy.deepcopy(self.ledger)
        pkg=self.compile()
        self.assertEqual(pkg['newUIDs'],[self.b])
        self.assertEqual(pkg['inputCount'],2)
        self.assertEqual(self.ledger,before)
        self.assertEqual(len(verify_application(pkg,self.snapshot,self.ledger,self.allowed)['operations']),2)
    def test_no_unattended_uid_creation(self):
        with self.assertRaisesRegex(ValueError,'explicit_new_identity'):
            compile_application(self.snapshot,self.ledger,self.allowed,[self.p],[])
        self.auth['DocumentUID']=self.a
        with self.assertRaisesRegex(ValueError,'new_uid_collision'): self.compile()
    def test_stale_source_contract_and_package_tampering(self):
        pkg=self.compile()
        changed=copy.deepcopy(self.snapshot);changed['sourceSha256']='b'*64
        with self.assertRaisesRegex(ValueError,'stale_or_conflicting'):
            verify_application(pkg,changed,self.ledger,self.allowed)
        changed=copy.deepcopy(self.ledger);changed['aliases'][0]['alias']='changed'
        with self.assertRaisesRegex(ValueError,'stale_or_conflicting'):
            verify_application(pkg,self.snapshot,changed,self.allowed)
        pkg['expectedUIDs']=[]
        with self.assertRaisesRegex(ValueError,'package_changed'):
            verify_application(pkg,self.snapshot,self.ledger,self.allowed)
    def test_fake_acceptance_duplicates_and_remaining_unknown_fail(self):
        self.p['history']=[]
        with self.assertRaisesRegex(ValueError,'recorded_operator'):self.compile()
        self.setUp()
        with self.assertRaisesRegex(ValueError,'duplicate_exception'):
            compile_application(self.snapshot,self.ledger,self.allowed,[self.p,self.p],[self.auth])
        self.snapshot['records'].append({'sourceRow':988,'fields':{'sourceDocumentId':'C','sourceTitle':'unknown'}})
        with self.assertRaisesRegex(ValueError,'leaves_identity_exceptions'):self.compile()
    def test_existing_alias_resolution_keeps_identity_count(self):
        self.snapshot['records']=self.snapshot['records'][1:]
        r=inspect(self.snapshot,'fictional',self.ledger,self.allowed)
        p=proposal(r,r['exceptions'][0]['exceptionKey'])
        p.update(resolution='existing_uid',existingUID=self.a,rationale='Fictional continuity',evidenceReferences=['fictional://proof'])
        p=transition(p,'accepted','fictional://decision','Fictional operator')
        pkg=compile_application(self.snapshot,self.ledger,self.allowed,[p],[])
        self.assertEqual(pkg['newUIDs'],[])
        self.assertEqual(pkg['expectedUIDs'],[self.a])
    def test_live_uid_collision_and_unowned_fields_fail(self):
        self.p.update(resolution='existing_uid',existingUID=self.a)
        with self.assertRaisesRegex(ValueError,'leaves_identity_exceptions'):
            compile_application(self.snapshot,self.ledger,self.allowed,[self.p],[])
        with self.assertRaisesRegex(ValueError,'source_field_contract_invalid'):
            compile_application(self.snapshot,self.ledger,self.allowed|{'localDecision'},[self.p],[])

