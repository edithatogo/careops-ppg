import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_assurance import validate, for_version

class AssuranceTests(unittest.TestCase):
    def setUp(self):
        self.event={'EventUID':'fictional-decision-1','CaseUID':'fictional-case','DocumentReference':'fictional-document','ReviewedVersionRef':'fictional-v1','DocumentSHA256':'a'*64,'Stage':'Decision','RecordState':'Recorded','ConditionsState':'None recorded','DecisionOutcome':'Approved (recorded)','VerificationResult':'Not verified','ActorName':'Fictional actor','OccurredOn':'2026-10-16','Summary':'Fictional assertion; no real approval','EvidenceReference':'fictional://decision-proof','DecisionReference':'fictional://decision-1'}
    def test_recording_never_approves_or_inherits_version(self):
        self.assertEqual(validate(self.event),[])
        r=for_version(self.event,'fictional-case','fictional-document','fictional-v1','a'*64)
        self.assertEqual(r['recordedDecisionOutcome'],'Approved (recorded)');self.assertFalse(r['policyApproved'])
        for case,doc,version,sha in [('other','fictional-document','fictional-v1','a'*64),('fictional-case','other','fictional-v1','a'*64),('fictional-case','fictional-document','fictional-v2','a'*64),('fictional-case','fictional-document','fictional-v1','b'*64)]:
            r=for_version(self.event,case,doc,version,sha);self.assertEqual(r['recordState'],'Unknown');self.assertFalse(r['policyApproved'])
    def test_unknown_pending_and_missing_evidence(self):
        for state in ['Unknown','Pending evidence']:
            e=copy.deepcopy(self.event);e.update(RecordState=state,ActorName='',OccurredOn='',Summary='',EvidenceReference='');self.assertEqual(validate(e),[])
        e=copy.deepcopy(self.event);e['EvidenceReference']='';self.assertIn('required:EvidenceReference',validate(e))
    def test_conditions_and_not_applicable_require_rationale(self):
        e=copy.deepcopy(self.event);e.update(ConditionsState='Open');self.assertIn('required:ConditionsNotes',validate(e));e['ConditionsNotes']='Fictional unresolved condition';self.assertEqual(validate(e),[])
        e.update(RecordState='Not applicable',Summary='');self.assertIn('required:Summary',validate(e))
    def test_version_linked_chain_and_second_decision_history(self):
        first=copy.deepcopy(self.event);first['DecisionOutcome']='Deferred'
        second=copy.deepcopy(self.event);second.update(EventUID='fictional-decision-2',SupersedesEventUID=first['EventUID'])
        self.assertEqual(validate(second,[first]),[])
        pub=copy.deepcopy(second);pub.update(EventUID='fictional-pub',Stage='Publication',DecisionOutcome='Unknown',ParentEventUID=second['EventUID'],PublicationURL='https://example.invalid/fictional/v1',PublishedVersionRef='fictional-v1');pub.pop('SupersedesEventUID')
        impl=copy.deepcopy(pub);impl.update(EventUID='fictional-impl',Stage='Implementation',ParentEventUID=pub['EventUID'],ImplementationActions='Fictional action evidence')
        verify=copy.deepcopy(impl);verify.update(EventUID='fictional-verify',Stage='Verification',ParentEventUID=impl['EventUID'],VerificationMethod='Fictional readback',VerificationResult='Verified (recorded)')
        history=[first,second]
        for e in [pub,impl,verify]:self.assertEqual(validate(e,history),[]);history.append(e)
        self.assertEqual(len([e for e in history if e['Stage']=='Decision']),2)
        bad=copy.deepcopy(pub);bad['ReviewedVersionRef']='fictional-v2';self.assertIn('version_mismatch:ParentEventUID',validate(bad,[second]))
        self.assertIn('duplicate:EventUID',validate(second,history))
    def test_readiness_link_must_match_version(self):
        e=copy.deepcopy(self.event);e['ReadinessEventUID']='finding-1';r={k:e[k] for k in ['CaseUID','DocumentReference','ReviewedVersionRef','DocumentSHA256']};r['EventUID']='finding-1';self.assertEqual(validate(e,readiness=[r]),[]);r['DocumentSHA256']='b'*64;self.assertIn('readiness_identity_or_version_mismatch',validate(e,readiness=[r]))
    def test_stage_specific_evidence_and_format(self):
        for stage,missing in [('Publication','PublicationURL'),('Implementation','ImplementationActions'),('Verification','VerificationMethod')]:
            e=copy.deepcopy(self.event);e.update(Stage=stage,ParentEventUID='fictional-parent');self.assertIn('required:'+missing,validate(e))
        e=copy.deepcopy(self.event);e['DocumentSHA256']='z'*64;self.assertIn('invalid:DocumentSHA256',validate(e));e['OccurredOn']='2026-13-55';self.assertIn('invalid:OccurredOn',validate(e))
    def test_wrong_parent_and_pending_parent_are_explicit(self):
        p=copy.deepcopy(self.event);p['RecordState']='Pending evidence';e=copy.deepcopy(self.event);e.update(EventUID='next',Stage='Publication',ParentEventUID=p['EventUID'],PublicationURL='https://example.invalid/fictional',PublishedVersionRef='fictional-v1');self.assertIn('parent_evidence_pending',validate(e,[p]));p['Stage']='Verification';self.assertIn('stage_mismatch:ParentEventUID',validate(e,[p]))

    def test_pending_assertions_do_not_project_as_recorded_results(self):
        e=copy.deepcopy(self.event);e.update(RecordState='Pending evidence',EvidenceReference='')
        r=for_version(e,'fictional-case','fictional-document','fictional-v1','a'*64)
        self.assertTrue(r['validRecord']);self.assertEqual(r['recordedDecisionOutcome'],'Unknown')
        e.update(Stage='Verification',DecisionOutcome='Unknown',VerificationResult='Verified (recorded)')
        r=for_version(e,'fictional-case','fictional-document','fictional-v1','a'*64)
        self.assertTrue(r['validRecord']);self.assertEqual(r['recordedVerificationResult'],'Not verified')

if __name__=='__main__':unittest.main()
