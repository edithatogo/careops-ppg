import copy
import json
import subprocess
import unittest
from pathlib import Path

CONTRACT=json.loads(Path('config/followup-native-registers.json').read_text())
MAPS={r['key']:{f['name']:f['name'] for f in r['fields']} for r in CONTRACT['registers']}
SCOPE=dict(CaseUID='F-case',DocumentReference='fictional://source',ReviewedVersionRef='v1',DocumentSHA256='a'*64)
STAMP='2026-10-21T00:00:00Z'

def fixture():
    context=dict(SCOPE,Id=1,OData__UIVersionString='1.0',SourceAsOf=STAMP,SourceCheckedAt=STAMP,SourceFreshness='Current',SourceEvidence='fictional://baseline',RecipientRole='F-role',RecipientAddress='fictional@example.invalid',RecipientEligibility='Verified',RecipientEvidence='fictional://recipient')
    proposal=dict(SCOPE,Id=1,EventUID='F-proposal',EventKind='Ownership handoff',RecordState='Proposed',SubjectRole='F-role',FromRole='F-origin',ConditionsState='None recorded')
    acceptance=dict(proposal,Id=2,EventUID='F-accepted',RecordState='Accepted',ParentEventUID='F-proposal',ActorName='F-operator',OccurredOn=STAMP,Summary='F-acceptance',EvidenceReference='fictional://evidence')
    request=dict(Id=1,OData__UIVersionString='1.0',Author={'Title':'F-operator'},RequestKey='F-request',Operation='Record follow-up',AsOf=STAMP,CaseUID='F-case',ContextVersion='1.0',EventUID='F-event',Stage='Preparation',FollowupState='Open',OccurredOn=STAMP,Rationale='F-reason',NextAction='Prepare evidence')
    return dict(requestId=1,maps=MAPS,native={k:{'value':v} for k,v in dict(contexts=[context],requests=[request],events=[],digests=[],ownership=[proposal,acceptance],cases=[dict(Id=1,CaseUID='F-case',caseStatus='Open',OData__UIVersionString='1.0')]).items()})

def run(inputs):
    p=subprocess.run(['node','tools/followup/test_followup.mjs'],input=json.dumps(inputs),text=True,capture_output=True,check=True)
    return json.loads(p.stdout)

def apply(value,plan,complete=True):
    value=copy.deepcopy(value)
    for w in plan['writes']+([plan['completion']] if complete else []):
        if w['create']:
            rows=value['native'][w['target']]['value'];rows.append(dict(w['payload'],Id=len(rows)+1,OData__UIVersionString='1.0'))
    return value

class NativeFollowupTests(unittest.TestCase):
    def test_future_or_unqualified_acceptance_is_not_current(self):
        x=fixture();saved=apply(x,run([x])[0]['value'])
        saved['native']['requests']['value'][0].update(RequestKey='F-future-owner',Operation='Preview digest')
        for value in ['2026-10-22T00:00:00Z', 'not-a-time', '2026-10-20T00:00:00', None]:
            candidate=copy.deepcopy(saved);candidate['native']['ownership']['value'][1]['OccurredOn']=value
            result=run([candidate])[0]
            self.assertTrue(result['ok'],result)
            self.assertEqual(result['value']['report']['candidates'], [])
            self.assertEqual(result['value']['report']['exceptions'][0]['reason'], 'ownership_unresolved')

    def test_first_replay_and_commit_verification(self):
        x=fixture();result=run([x])[0];self.assertTrue(result['ok'],result)
        p=result['value'];saved=apply(x,p)
        replay=run([saved])[0];self.assertTrue(replay['ok'],replay)
        self.assertFalse(any(w['create'] for w in replay['value']['writes']+[replay['value']['completion']]))
        verified=run([dict(saved,phase='verify',originalPlan=p,verifyCompletion=True)])[0]
        self.assertTrue(verified['ok'],verified)
        self.assertEqual(x['native']['events']['value'],[])

    def test_stale_scope_fork_and_identity_conflict(self):
        x=fixture();p=run([x])[0]['value'];saved=apply(x,p)
        stale=copy.deepcopy(x);stale['native']['requests']['value'][0]['ContextVersion']='old'
        fork=copy.deepcopy(saved);fork['native']['requests']['value'][0].update(RequestKey='F-new',EventUID='F-fork')
        changed=copy.deepcopy(saved);changed['native']['requests']['value'][0]['Rationale']='different'
        self.assertEqual([r['ok'] for r in run([stale,fork,changed])],[False,False,False])

    def test_changed_stage_and_source_dates_preserved(self):
        x=fixture();x['native']['contexts']['value'][0]['SourceDueDate']='2026-11-01';saved=apply(x,run([x])[0]['value'])
        saved['native']['requests']['value'][0].update(RequestKey='F-next',EventUID='F-event2',PreviousEventUID='F-event',Stage='Consultation',AgreedTargetDate='2026-11-02',TargetAgreementEvidence='fictional://agreement')
        r=run([saved])[0];self.assertTrue(r['ok'],r);event=json.loads(r['value']['writes'][0]['payload']['EventJSON'])
        self.assertEqual(event['SourceDueDate'],'2026-11-01');self.assertEqual(event['AgreedTargetDate'],'2026-11-02')

    def test_digest_unknown_closed_empty_and_repeat(self):
        x=fixture();saved=apply(x,run([x])[0]['value']);request=saved['native']['requests']['value'][0];request.update(RequestKey='F-preview',Operation='Preview digest')
        first=run([saved])[0];self.assertTrue(first['ok'],first);report=first['value']['report'];self.assertEqual(len(report['candidates']),1);self.assertFalse(report['deliveryEligible'])
        previous=apply(saved,first['value']);previous['native']['requests']['value'][0].update(RequestKey='F-preview2',PreviousPreviewKey=first['value']['runKey'])
        repeated=run([previous])[0];self.assertTrue(repeated['value']['report']['candidates'][0]['unchangedSincePrevious'])
        unknown=copy.deepcopy(saved);unknown['native']['contexts']['value'][0]['RecipientEligibility']='Unknown'
        stale=copy.deepcopy(saved);stale['native']['contexts']['value'][0]['SourceFreshness']='Unknown'
        closed=copy.deepcopy(saved);closed['native']['cases']['value'][0]['caseStatus']='Review closed — FICTIONAL'
        empty=fixture();empty['native']['requests']['value'][0].update(RequestKey='F-empty',Operation='Preview digest')
        rs=run([unknown,stale,closed,empty]);self.assertEqual(rs[0]['value']['report']['exceptions'][0]['reason'],'recipient_unresolved');self.assertEqual(len(rs[1]['value']['report']['exceptions']),1);self.assertEqual(len(rs[2]['value']['report']['suppressed']),1);self.assertEqual(rs[3]['value']['report']['candidates'],[])

    def test_incidental_completed_word_is_not_a_closed_case(self):
        x=fixture();saved=apply(x,run([x])[0]['value']);saved['native']['requests']['value'][0].update(RequestKey='F-active-review',Operation='Preview digest');saved['native']['cases']['value'][0]['caseStatus']='Draft completed — awaiting review'
        r=run([saved])[0];self.assertTrue(r['ok'],r);self.assertEqual(len(r['value']['report']['candidates']),1);self.assertEqual(r['value']['report']['suppressed'],[])

    def test_preview_before_recorded_event_does_not_include_future_state(self):
        x=fixture();saved=apply(x,run([x])[0]['value']);saved['native']['requests']['value'][0].update(RequestKey='F-past-preview',Operation='Preview digest',AsOf='2026-10-20T00:00:00Z')
        result=run([saved])[0];self.assertTrue(result['ok'],result);self.assertEqual(result['value']['report']['candidates'],[]);self.assertEqual(result['value']['report']['exceptions'][0]['reason'],'future_event')

    def test_partial_output_edited_history_and_source_drift_hold(self):
        x=fixture();p=run([x])[0]['value'];partial=apply(x,p,complete=False);partial['native']['requests']['value'][0].update(RequestKey='F-preview',Operation='Preview digest')
        edited=apply(x,p);edited['native']['events']['value'][0]['OData__UIVersionString']='2.0'
        drift=apply(x,p);drift['native']['contexts']['value'][0]['SourceFreshness']='Stale'
        rs=run([partial,edited,dict(drift,phase='verify',originalPlan=p)]);self.assertFalse(any(r['ok'] for r in rs))

    def test_human_edited_digest_is_preserved_and_exact_retry_refused(self):
        x=fixture();saved=apply(x,run([x])[0]['value'])
        saved['native']['requests']['value'][0].update(RequestKey='F-preview-edit',Operation='Preview digest')
        preview=run([saved])[0]['value'];saved=apply(saved,preview)
        candidate=next(r for r in saved['native']['digests']['value'] if r.get('RowKind')=='Candidate')
        candidate.update(Reason='Human observation retained',OData__UIVersionString='2.0')
        before=copy.deepcopy(saved)
        refused=run([saved])[0]
        self.assertFalse(refused['ok']);self.assertIn('preserve edits',refused['error'])
        self.assertEqual(saved,before)
        saved['native']['requests']['value'][0]['RequestKey']='F-new-observation'
        self.assertTrue(run([saved])[0]['ok'])

    def test_native_candidate_exposes_stage_entry_and_human_priority(self):
        x=fixture();x['native']['requests']['value'][0]['Priority']='Human: high value, low effort'
        saved=apply(x,run([x])[0]['value'])
        saved['native']['requests']['value'][0].update(RequestKey='F-visible-preview',Operation='Preview digest')
        result=run([saved])[0];self.assertTrue(result['ok'],result)
        row=next(w['payload'] for w in result['value']['writes'] if w['payload'].get('RowKind')=='Candidate')
        self.assertEqual(row['StageEnteredOn'],STAMP)
        self.assertEqual(row['Priority'],'Human: high value, low effort')
        self.assertIsNone(row['SourceDueDate']);self.assertIsNone(row['AgreedTargetDate'])

    def test_same_stage_action_update_keeps_original_entry_time(self):
        x=fixture();saved=apply(x,run([x])[0]['value'])
        saved['native']['requests']['value'][0].update(RequestKey='F-action-update',EventUID='F-event2',PreviousEventUID='F-event',OccurredOn='2026-10-22T00:00:00Z',AsOf='2026-10-22T00:00:00Z',Priority='Human revised priority',NextAction='Check the response')
        saved=apply(saved,run([saved])[0]['value'])
        saved['native']['requests']['value'][0].update(RequestKey='F-stage-entry-preview',Operation='Preview digest')
        result=run([saved])[0];self.assertTrue(result['ok'],result)
        row=next(w['payload'] for w in result['value']['writes'] if w['payload'].get('RowKind')=='Candidate')
        self.assertEqual(row['StageEnteredOn'],STAMP)
        self.assertEqual(row['Priority'],'Human revised priority')
        self.assertEqual(row['NextAction'],'Check the response')

    def test_each_terminal_state_is_suppressed_and_unknown_ownership_is_an_exception(self):
        for state in ['Completed','Declined','Superseded']:
            x=fixture();x['native']['requests']['value'][0]['FollowupState']=state
            saved=apply(x,run([x])[0]['value'])
            saved['native']['requests']['value'][0].update(RequestKey='F-preview-'+state,Operation='Preview digest')
            report=run([saved])[0]['value']['report']
            self.assertEqual(report['candidates'],[]);self.assertEqual(report['suppressed'][0]['reason'],state)
        x=fixture();saved=apply(x,run([x])[0]['value'])
        saved['native']['requests']['value'][0].update(RequestKey='F-missing-owner',Operation='Preview digest')
        saved['native']['ownership']['value']=[]
        report=run([saved])[0]['value']['report']
        self.assertEqual(report['candidates'],[]);self.assertEqual(report['exceptions'][0]['reason'],'ownership_unresolved')

    def test_dates_author_evidence_and_pagination_refused(self):
        variations=[]
        for patch in [dict(AgreedTargetDate='2026-02-30'),dict(AgreedTargetDate='2026-11-01'),dict(OccurredOn='2026-02-30T00:00:00Z')]:
            x=fixture();x['native']['requests']['value'][0].update(patch);variations.append(x)
        x=fixture();x['native']['requests']['value'][0]['Author']={};variations.append(x)
        x=fixture();x['native']['events']['@odata.nextLink']='fictional://next';variations.append(x)
        self.assertFalse(any(r['ok'] for r in run(variations)))

if __name__=='__main__':unittest.main()

class FlowShapeTests(unittest.TestCase):
    def bindings(self):
        return dict(site='https://example.invalid',connectionReferences={k:{'source':'Embedded'} for k in ['shared_sharepointonline','shared_excelonlinebusiness']},registers={k:k+'-fictional' for k in ['requests','contexts','events','digests','ownership','cases']},maps=MAPS,scriptParameters={k:'fictional' for k in ['source','drive','file','scriptSource','scriptDrive','scriptId']},historyUrl='https://example.invalid/history',digestUrl='https://example.invalid/digest',scriptSHA256='a'*64)
    def test_manual_serial_standard_only_and_readonly_sources(self):
        from scripts.ppg_followup_web_flow import build
        candidate=build(self.bindings());definition=candidate['properties']['definition'];self.assertEqual(definition['triggers']['manual']['kind'],'Button');self.assertEqual(definition['triggers']['manual']['runtimeConfiguration']['concurrency']['runs'],1)
        writes=[]
        def walk(x):
            if isinstance(x,dict):
                params=x.get('inputs',{}).get('parameters',{}) if isinstance(x.get('inputs'),dict) else {}
                if params.get('parameters/method')=='POST':writes.append(x)
                for y in x.values():walk(y)
            elif isinstance(x,list):
                for y in x:walk(y)
        walk(candidate);self.assertEqual(len(writes),2)
        for write in writes:
            self.assertNotIn('ownership-fictional',write['inputs']['parameters']['parameters/uri']);self.assertEqual(write['inputs']['retryPolicy'],{'type':'none'})
        self.assertEqual(definition['actions']['Commit_completion']['runAfter'],{'Verified_plan':['Succeeded']});self.assertEqual(definition['actions']['Report_followup']['runAfter'],{'Verify_completion':['Succeeded']})
        self.assertFalse(definition['actions']['Report_followup']['inputs']['deliveryEligible'])
    def test_rejects_unqualified_connection_family(self):
        from scripts.ppg_followup_web_flow import build
        b=self.bindings();b['connectionReferences']['shared_office365']={'source':'Embedded'}
        with self.assertRaises(ValueError):build(b)
