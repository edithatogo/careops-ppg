import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_followup_digest import append_event, preview

NOW = '2026-10-18T00:00:00Z'

def fixture():
    scope = dict(CaseUID='FICTIONAL-case', DocumentReference='FICTIONAL-document',
                 ReviewedVersionRef='v1', DocumentSHA256='a'*64)
    event = dict(scope, EventUID='FICTIONAL-followup', Stage='Preparation', State='Open',
                 OccurredOn=NOW, Actor='Fictional operator', Rationale='Fictional priority rationale',
                 Priority='Normal', NextAction='Prepare fictional evidence', WaitingReason='',
                 SourceDueDate=None, AgreedTargetDate=None, PreviousEventUID=None)
    proposal = dict(scope, EventUID='FICTIONAL-proposal', EventKind='Ownership handoff',
                    RecordState='Proposed', SubjectRole='Fictional role', FromRole='Fictional requester',
                    ConditionsState='None recorded')
    accepted = dict(proposal, EventUID='FICTIONAL-accepted', RecordState='Accepted',
                    ParentEventUID=proposal['EventUID'], ActorName='Fictional operator',
                    OccurredOn=NOW, Summary='Fictional acceptance', EvidenceReference='fictional://acceptance')
    current = dict(scope, SourceAsOf=NOW, SourceCheckedAt=NOW, SourceFreshness='Current',
                   Recipient={'Role':'Fictional role','Address':'fictional@example.invalid',
                              'Eligibility':'Verified','EvidenceReference':'fictional://directory-check'})
    return {'events':[event], 'currentScopes':[current], 'ownershipEvents':[proposal,accepted]}


class FollowupTests(unittest.TestCase):
    def test_future_or_unqualified_acceptance_is_not_current(self):
        for value in ['2026-10-22T00:00:00Z', 'not-a-time', '2026-10-17T00:00:00', None]:
            data=fixture();data['ownershipEvents'][1]['OccurredOn']=value
            result=preview(data,NOW)
            self.assertEqual(result['candidates'], [])
            self.assertEqual(result['exceptions'][0]['reason'], 'ownership_unresolved')

    def test_empty(self):
        self.assertEqual(preview({'events':[], 'currentScopes':[]}, NOW)['candidates'], [])

    def test_preview_and_repeat(self):
        data=fixture(); before=copy.deepcopy(data)
        first=preview(data,NOW); second=preview(data,NOW,first)
        self.assertEqual(len(first['candidates']),1)
        self.assertTrue(second['candidates'][0]['unchangedSincePrevious'])
        self.assertFalse(second['deliveryEligible'])
        self.assertEqual(data,before)
        self.assertIsNone(first['candidates'][0]['event']['AgreedTargetDate'])

    def test_suppress_closed(self):
        for state in ('Completed','Declined','Superseded'):
            data=fixture(); data['events'][0]['State']=state
            result=preview(data,NOW)
            self.assertEqual(len(result['suppressed']),1)
            self.assertEqual(result['candidates'],[])

    def test_unknown_stale_recipient(self):
        for field,value,reason in [('SourceFreshness','Unknown','source_freshness_unconfirmed'),
                                   ('ReviewedVersionRef','v2','stale_or_missing_document_scope'),
                                   ('Recipient',None,'recipient_unresolved')]:
            data=fixture(); data['currentScopes'][0][field]=value
            self.assertEqual(preview(data,NOW)['exceptions'][0]['reason'],reason)

    def test_proposed_is_not_accepted(self):
        data=fixture(); data['ownershipEvents'].pop()
        self.assertEqual(preview(data,NOW)['exceptions'][0]['reason'],'ownership_unresolved')

    def test_transition_retry_conflict_preserves(self):
        data=fixture(); history=data['events']; event=copy.deepcopy(history[0])
        event.update(EventUID='FICTIONAL-next', PreviousEventUID=history[0]['EventUID'],Stage='Consultation')
        updated,status=append_event(history,event,data['currentScopes'][0])
        self.assertEqual(status,'appended'); self.assertEqual(len(history),1)
        self.assertEqual(append_event(updated,event,data['currentScopes'][0])[1],'unchanged')
        event['Rationale']='Changed'
        with self.assertRaises(ValueError): append_event(updated,event,data['currentScopes'][0])
        event['EventUID']='FICTIONAL-third';event['PreviousEventUID']=None
        with self.assertRaises(ValueError): append_event(updated,event,data['currentScopes'][0])

    def test_stale_write_and_date_validation(self):
        data=fixture(); event=data['events'][0];current=data['currentScopes'][0]
        current['ReviewedVersionRef']='v2'
        with self.assertRaises(ValueError): append_event([],event,current)
        current['ReviewedVersionRef']='v1';event['AgreedTargetDate']='2026-02-30'
        with self.assertRaises(ValueError): append_event([],event,current)
        event['AgreedTargetDate']='2026-10-20'
        with self.assertRaises(ValueError): append_event([],event,current)

    def test_ambiguous_ownership_and_future(self):
        data=fixture(); accepted=copy.deepcopy(data['ownershipEvents'][-1]);accepted['EventUID']='FICTIONAL-other'
        data['ownershipEvents'].append(accepted)
        self.assertEqual(preview(data,NOW)['exceptions'][0]['reason'],'ownership_unresolved')
        data=fixture();data['currentScopes'][0]['SourceCheckedAt']='2027-01-01T00:00:00Z'
        self.assertEqual(preview(data,NOW)['exceptions'][0]['reason'],'source_freshness_unconfirmed')

if __name__=='__main__': unittest.main()
