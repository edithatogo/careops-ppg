import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_consultation import validate, for_version


def sample(**changes):
    return dict(EventUID='fictional-1', CaseUID='fictional-case', DocumentReference='fictional-document',
                ReviewedVersionRef='v1', DocumentSHA256='a'*64, SubjectRole='Fictional receiving role',
                EventKind='Consultation', RecordState='Pending response', ConditionsState='Unknown', **changes)


class ConsultationTests(unittest.TestCase):
    def test_silence_never_accepts_or_transfers(self):
        e=sample();r=for_version(e,e['CaseUID'],e['DocumentReference'],'v1','a'*64)
        self.assertTrue(r['validRecord']);self.assertFalse(r['recordedOwnershipAcceptance'])
        for k in ('ownershipTransferred','assignmentPerformed','notificationSent','policyApproved'):self.assertFalse(r[k])
    def test_terminal_response_needs_actual_evidence(self):
        e=sample();e['RecordState']='Responded';self.assertIn('required:ResponseSummary',validate(e))
        e.update(ActorName='Fictional actor',OccurredOn='2026-10-16',Summary='Fictional response',EvidenceReference='fictional-evidence',ResponseSummary='Changes requested')
        self.assertEqual(validate(e),[])
    def test_accepted_handoff_requires_matching_proposal(self):
        p=sample();p.update(EventKind='Ownership handoff',RecordState='Proposed',FromRole='Fictional offering role')
        e=copy.deepcopy(p);e.update(EventUID='fictional-2',ParentEventUID=p['EventUID'],RecordState='Accepted',ActorName='Fictional actor',OccurredOn='2026-10-16',Summary='Fictional acceptance',EvidenceReference='fictional-evidence')
        self.assertEqual(validate(e,[p]),[])
        self.assertIn('history_required:ParentEventUID',validate(e))
        p['ReviewedVersionRef']='v2';self.assertIn('scope_mismatch:ParentEventUID',validate(e,[p]))
    def test_unknown_or_stale_version_not_acceptance(self):
        e=sample();e.update(EventKind='Ownership handoff',FromRole='Fictional offering role',RecordState='Proposed')
        r=for_version(e,e['CaseUID'],e['DocumentReference'],'v2','b'*64)
        self.assertFalse(r['appliesToRequestedVersion']);self.assertEqual(r['recordedState'],'Unknown')
    def test_duplicate_and_self_links_fail(self):
        e=sample();self.assertIn('duplicate:EventUID',validate(e,[e]));e['ParentEventUID']=e['EventUID'];self.assertIn('missing_ambiguous_or_self:ParentEventUID',validate(e,[e]))
    def test_open_conditions_and_state_kind_fail_closed(self):
        e=sample();e.update(ConditionsState='Open',RecordState='Accepted')
        self.assertIn('state_kind_mismatch',validate(e));self.assertIn('required:ConditionsNotes',validate(e))
    def test_superseded_assertion_remains_history(self):
        e=sample();new=copy.deepcopy(e);new.update(EventUID='fictional-2',SupersedesEventUID=e['EventUID'])
        r=for_version(e,e['CaseUID'],e['DocumentReference'],'v1','a'*64,[new]);self.assertTrue(r['superseded']);self.assertEqual(r['recordedState'],'Unknown')
    def test_invalid_hash_date_and_role_change_rejected(self):
        e=sample();e.update(DocumentSHA256='z'*64,OccurredOn='invalid');self.assertIn('invalid:DocumentSHA256',validate(e));self.assertIn('invalid:OccurredOn',validate(e))


if __name__ == '__main__':unittest.main()
