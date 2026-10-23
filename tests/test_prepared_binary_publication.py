"""Local emitted-graph checks; no native fixture or invocation."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/policy-editions'))
sys.path.insert(0,str(ROOT/'tools/lifecycle'))
from build_prepared_binary_publication import build, CODES
from binary_publication import digest
from build_prepared_purpose_events import build as purpose_build
from build_selected_event_routes import audit_actions
from test_prepared_purpose_events import fixture as purpose_fixture, rows, SCOPE, PROFILE
from test_prepared_closure_check import Expressions
import test_prepared_closure_check as expression_harness


def fixture():
    c,t,b=purpose_fixture();p=purpose_build(c,t,b)
    site=p['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']['inputs']['parameters']['dataset']
    from urllib.parse import urlsplit
    binding={'qualificationOnly':True,'approvedPurposeDefinitionSHA256':digest(p['properties']['definition']),
        'approvedTargetDefinitionSHA256':digest(t['properties']['definition']),
        'approvedPurposeModuleSHA256':hashlib.sha256((ROOT/'tools/lifecycle/build_prepared_purpose_events.py').read_bytes()).hexdigest(),
        'fictionalRouteProfile':PROFILE,'eventUIDUnique':True,'assuranceCollectionUri':b['assuranceCollectionUri'],
        'qualificationFolder':urlsplit(site).path+'/qualification','reviewedBinaryProof':None}
    return p,t,binding


def flatten(group):
    result={}
    for n,a in group.items():
        result[n]=a;result.update(flatten(a.get('actions',{})));result.update(flatten(a.get('else',{}).get('actions',{})))
    return result


def history(history):
    graph=build(*fixture())['properties']['definition']['actions']
    outputs={'Native_prepared_revision':{'preparedRevision':{'scope':SCOPE}},
        'Native_readiness_observation':{'selectedEventUID':'FICTIONAL-ready'},
        'Chosen_purpose':{'ordinal':3,'EventUID':'FICTIONAL-purpose-authorisation'},'Publication_uid':'LOCAL-current-publication'}
    outputs.update({'Purpose_uid_'+code:'FICTIONAL-purpose-'+code for code in CODES})
    ev=Expressions({'Purpose_before_assurance':{'value':history},'Readiness_scope':[{'AssessedOn':'2026-10-18T14:00:00Z'}]},outputs)
    active=False
    for name,action in graph.items():
        if name=='Purpose_before_assurance':active=True;continue
        if not active:continue
        if action['type']=='Query':
            out=[]
            for row in ev.evaluate(action['inputs']['from']):
                ev.current=row
                if ev.evaluate(action['inputs']['where']):out.append(row)
            ev.bodies[name]=out
        elif action['type']=='Compose':ev.outputs[name]=ev.evaluate(action['inputs'])
        else:raise AssertionError(name)
        if name=='Purpose_before_selected':
            return ev.outputs['Purpose_before_history_consistent'] and all(len(ev.bodies['Purpose_before_rows_'+c])==1 and ev.outputs['Purpose_before_valid_'+c] for c in CODES)
    raise AssertionError('Missing complete history')


class PreparedBinaryPublicationTests(unittest.TestCase):
    def test_partial_destination_lookup_never_qualifies_copy_or_replay(self):
        actions = build(*fixture())['properties']['definition']['actions']
        expression = actions['Verify_target_cardinality']['expression']
        for rows in ([], [{'UniqueId': 'existing-destination'}]):
            self.assertTrue(Expressions({'Find_issued': {'value': rows}}).evaluate(expression))
            for marker in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink'):
                with self.subTest(rows=len(rows), marker=marker):
                    page = {'value': rows, marker: 'https://example.invalid/continuation'}
                    self.assertFalse(Expressions({'Find_issued': page}).evaluate(expression))
        self.assertFalse(Expressions({'Find_issued': {'value': [{}, {}]}}).evaluate(expression))

    def test_first_occurrence_uses_native_whole_seconds_without_rounding_or_replay_reformat(self):
        actions=build(*fixture())['properties']['definition']['actions']
        expression=actions['Publication_payload']['inputs']['OccurredOn']
        self.assertIn("formatDateTime(utcNow(),'yyyy-MM-ddTHH:mm:ssZ')",expression)
        for clock,expected in [('2026-10-17T22:30:49.6799185Z','2026-10-17T22:30:49Z'),
                               ('2026-10-17T23:59:59.9999999Z','2026-10-17T23:59:59Z')]:
            with patch.object(expression_harness,'NOW',clock):
                self.assertEqual(Expressions({'Find_existing_publication':[]}).evaluate(expression),expected)
                # Existing native values are returned exactly, including a
                # different retained precision; they are never silently edited.
                retained='2026-10-17T21:00:01.1234567Z'
                self.assertEqual(Expressions({'Find_existing_publication':[{'OccurredOn':retained}]}).evaluate(expression),retained)

    def test_actual_shaped_first_readback_exact_equality_and_chronology_hold(self):
        actions=build(*fixture())['properties']['definition']['actions']
        expression=actions['Publication_payload']['inputs']['OccurredOn']
        equality="equals(first(body('Read_retained_publication'))?['OccurredOn'],outputs('Publication_payload')?['OccurredOn'])"
        past="lessOrEquals(ticks(first(body('Read_retained_publication'))?['OccurredOn']),ticks(utcNow()))"
        parent="greaterOrEquals(ticks(first(body('Read_retained_publication'))?['OccurredOn']),ticks(first(body('Purpose_before_rows_authorisation'))?['OccurredOn']))"
        emitted=' '.join(a['inputs'] for name,a in actions.items() if name.startswith('Verify_publication_after_check_'))
        for predicate in (equality,past,parent):self.assertIn(predicate,emitted)
        with patch.object(expression_harness,'NOW','2026-10-17T22:30:49.6799185Z'):
            payload={'OccurredOn':Expressions({'Find_existing_publication':[]}).evaluate(expression)}
            def evaluate(stored,expected=None):
                ev=Expressions({'Read_retained_publication':[{'OccurredOn':stored}],
                    'Purpose_before_rows_authorisation':[{'OccurredOn':'2026-10-17T22:30:48Z'}]},
                    {'Publication_payload':payload if expected is None else {'OccurredOn':expected}})
                return [ev.evaluate('@'+p) for p in (equality,past,parent)]
            self.assertEqual(evaluate('2026-10-17T22:30:49Z'),[True,True,True])
            self.assertFalse(evaluate('2026-10-17T22:30:50Z')[0])
            self.assertFalse(evaluate('2026-10-18T22:30:49Z')[0])
            self.assertFalse(evaluate('2026-10-17T22:30:50Z','2026-10-17T22:30:50Z')[1])
            self.assertFalse(evaluate('2026-10-17T22:30:47Z','2026-10-17T22:30:47Z')[2])

    def test_exact_source_and_stopped_preimage_pins(self):
        p,t,b=fixture();before=copy.deepcopy((p,t,b));out=build(p,t,b)
        self.assertEqual((p,t,b),before)
        self.assertEqual(out['properties']['state'],'Stopped')
        self.assertEqual(out['properties']['connectionReferences'],t['properties']['connectionReferences'])
        for key in ('approvedPurposeDefinitionSHA256','approvedPurposeModuleSHA256','approvedTargetDefinitionSHA256'):
            bad=copy.deepcopy(b);bad[key]='0'*64
            with self.assertRaises(ValueError):build(p,t,bad)

    def test_only_two_retry_disabled_writers_and_no_binary_text_body(self):
        graph=flatten(build(*fixture())['properties']['definition']['actions'])
        writers={n:a for n,a in graph.items() if a['type']=='OpenApiConnection' and a['inputs']['parameters']['parameters/method']!='GET'}
        self.assertEqual(set(writers),{'Copy_binary_absent_only','Create_binary_publication'})
        for a in writers.values():self.assertEqual(a['inputs']['retryPolicy'],{'type':'none'})
        copy_=writers['Copy_binary_absent_only']['inputs']['parameters']
        self.assertNotIn('parameters/body',copy_)
        self.assertIn('bOverWrite=false',copy_['parameters/uri'])
        self.assertIn("equals(length(body('Find_issued')?['value']),0)",graph['Copy_if_absent']['expression'])

    def test_current_full_chain_profile_readiness_and_chronology_reused(self):
        self.assertTrue(history(rows()))
        for edit in [lambda r:r.pop(),lambda r:r.append(dict(r[0],EventUID='adverse',DecisionOutcome='Deferred',ConditionsState='Open')),
                     lambda r:r[1].update(DecisionReference='fictional://wrong/profile'),
                     lambda r:r[2].update(ParentEventUID='wrong'),lambda r:r[1].update(ReadinessEventUID='wrong'),
                     lambda r:r[1].update(OccurredOn='2099-01-01T00:00:00Z'),lambda r:r[1].update(**{'odata.etag':'*'})]:
            value=rows();edit(value);self.assertFalse(history(value))

    def test_excludes_only_own_publication_identity_not_other_later_records(self):
        own=dict(rows()[0],EventUID='LOCAL-current-publication',Stage='Publication')
        self.assertTrue(history(rows()+[own]))
        self.assertFalse(history(rows()+[dict(own,EventUID='OTHER-publication')]))
        graph=build(*fixture())['properties']['definition']['actions']
        self.assertIn("outputs('Publication_uid')",graph['Find_publication_corrections']['inputs']['where'])
        self.assertIn("item()?['SupersedesEventUID']",graph['Read_retained_corrections']['inputs']['where'])
        self.assertIn("outputs('Publication_payload')",json.dumps(graph['Verify_publication_replay_check_0']))
        self.assertIn('Find_corrections_before_copy',graph)
        early=' '.join(a.get('inputs','') for n,a in graph.items() if n.startswith('Verify_all_retained_purposes_check_'))
        self.assertIn("equals(length(body('Find_publication_before_copy')),0)",early)

    def test_copy_stops_before_record_and_untrusted_producer_always_holds_record(self):
        graph=build(*fixture())['properties']['definition']['actions']
        self.assertEqual(graph['Stop_copy_phase']['actions']['Copy_phase_finished']['inputs']['runStatus'],'Succeeded')
        self.assertEqual(graph['Verify_record_producer_trust']['expression'],'@and(false)')
        self.assertEqual(graph['Binary_proof_path']['runAfter'],{'Verify_record_producer_trust':['Succeeded']})
        p,t,b=fixture();b['reviewedBinaryProof']={'qualified':True}
        with self.assertRaises(ValueError):build(p,t,b)

    def test_record_cannot_trust_supplied_digest_without_actual_producer_evidence(self):
        p,t,b=fixture()
        b['reviewedBinaryProof']={'receipt':{},'content':{},'producerEvidenceSHA256':'a'*64}
        with self.assertRaisesRegex(ValueError,'Actual separately reviewed producer evidence bytes'):
            build(p,t,b)

    def test_fresh_brackets_both_sides_source_issued_proof_and_complete_history(self):
        graph=build(*fixture())['properties']['definition']['actions']
        for prefix in ('Before_event','After_event'):
            self.assertIn(prefix+'_issued',graph)
            self.assertIn(prefix+'_proof',graph)
            for label in ('case','draft','receipt','template','source','baseline'):
                self.assertIn(prefix+'_Purpose_'+label+'_before',graph)
            self.assertIn(prefix+'_Purpose_before_assurance',graph)
        self.assertIn('reconcileBeforeRetry',graph['Unknown_final_publication_evidence']['inputs'])
        self.assertIsNone(graph['Unknown_final_publication_evidence']['inputs']['publicationCreatedCount'])
        self.assertIsNone(graph['Unknown_copy_readback']['inputs']['copyCreatedCount'])
        self.assertIsNone(graph['Observe_copy_phase']['actions']['Verify_copy_frame']['else']['actions']['Held_Verify_copy_frame']['inputs']['copyCreatedCount'])
        self.assertIsNone(graph['Verify_issued_metadata']['else']['actions']['Held_issued_metadata_mismatch']['inputs']['copyCreatedCount'])

    def test_depth_dependencies_references_and_expression_budget(self):
        out=build(*fixture());d=out['properties']['definition'];flat=flatten(d['actions'])
        audit=audit_actions(d);self.assertLessEqual(audit['maximumActionDepth'],8)
        refs=set(re.findall(r"(?:body|outputs|actions)\('([^']+)'\)",json.dumps(d)))
        self.assertFalse(refs-set(flat))
        def strings(v):
            if isinstance(v,str):yield v
            elif isinstance(v,dict):
                for x in v.values():yield from strings(x)
            elif isinstance(v,list):
                for x in v:yield from strings(x)
        self.assertTrue(all(len(s)<8192 for s in strings(d) if s.startswith('@')))
        self.assertEqual(d['triggers']['manual']['runtimeConfiguration']['concurrency']['runs'],1)


if __name__=='__main__':unittest.main()
