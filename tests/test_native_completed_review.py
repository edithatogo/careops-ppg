"""Emitted resolver/observer/writer checks; local evidence is not native acceptance."""
import base64
import copy
import hashlib
import json
import unittest
import re
import datetime
from urllib.parse import quote, unquote
from build_native_completed_review import (
    build_actions, _reader_actions, build_runtime_closure_observer, build_current_closure_observer,
    build_historical_prepared_reader, build_runtime_next_writer, _linearize_refusing_pipeline, NativeProducerRouteUnavailable)
from build_selected_event_routes import audit_actions
from test_prepared_decision_outcome import flatten


class Expressions:
    """Small independent evaluator of the emitted WDL primitive subset."""
    def __init__(self,bodies,outputs):self.bodies=bodies;self.outputs=outputs
    @staticmethod
    def empty(value):
        if value is not None and not isinstance(value, (str, list, dict)):
            raise TypeError('WDL empty requires a collection, string or null')
        return value is None or value == '' or value == [] or value == {}
    def evaluate(self,expression):
        tokens=re.findall(r"'(?:[^']|'')*'|\?\[|[A-Za-z_][A-Za-z_0-9]*|-?\d+|[(),\]]",expression[1:]);position=0
        def parse():
            nonlocal position
            token=tokens[position];position+=1
            if token.startswith("'"):node=('value',token[1:-1].replace("''","'"))
            elif re.fullmatch(r'-?\d+',token):node=('value',int(token))
            elif token in ['true','false','null']:node=('value',{'true':True,'false':False,'null':None}[token])
            else:
                assert tokens[position]=='(';position+=1;args=[]
                while tokens[position]!=')':
                    args.append(parse())
                    if tokens[position]!=')':assert tokens[position]==',';position+=1
                position+=1;node=('call',token,args)
            while position<len(tokens) and tokens[position]=='?[':
                position+=1;key=parse();assert tokens[position]==']';position+=1;node=('get',node,key)
            return node
        tree=parse();assert position==len(tokens)
        def run(node):
            if node[0]=='value':return node[1]
            if node[0]=='get':
                obj=run(node[1]);return obj.get(run(node[2])) if isinstance(obj,dict) else None
            name,args=node[1:]
            if name=='if':return run(args[1] if run(args[0]) else args[2])
            values=[run(v) for v in args]
            functions={'item':lambda:self.outputs.get('Current_item'),'body':lambda n:self.bodies.get(n),'outputs':lambda n:self.outputs.get(n),
                'equals':lambda a,b:a==b,'and':lambda *v:all(v),'or':lambda *v:any(v),'not':lambda v:not v,
                'empty':self.empty,'coalesce':lambda *v:next((x for x in v if x is not None),None),
                'string':str,'trim':lambda v:v.strip(),'length':len,'int':int,'greater':lambda a,b:a>b,
                'lessOrEquals':lambda a,b:a<=b,'greaterOrEquals':lambda a,b:a>=b,'startsWith':lambda a,b:a.startswith(b),
                'contains':lambda a,b:b in a,'replace':lambda v,a,b:v.replace(a,b),'concat':lambda *v:''.join(v),
                'createArray':lambda *v:list(v),
                'substring':lambda v,start,length=None:v[start:] if length is None else v[start:start+length],
                'endsWith':lambda v,suffix:v.endswith(suffix),
                'actions':lambda name:self.outputs.get('Action_'+name),
                'workflow':lambda:self.outputs.get('Test_workflow'),
                'sub':lambda a,b:a-b,'mul':lambda a,b:a*b,'div':lambda a,b:a//b,'mod':lambda a,b:a%b,
                'triggerBody':lambda:self.outputs.get('Test_trigger'),
                'json':json.loads,'union':lambda a,b:{**a,**b},'setProperty':lambda obj,key,value:{**obj,key:value},'first':lambda v:v[0],
                'uriComponent':lambda v:quote(v,safe="~()*!.'-"),'decodeUriComponent':unquote,
                'base64ToString':lambda v:base64.b64decode(v).decode(),
                'formatDateTime':lambda v,f:datetime.date.fromisoformat(v).isoformat()}
            return functions[name](*values)
        return run(tree)


def fixture(number=1):
    uid=lambda n:'00000000-0000-4000-8000-'+str(n).zfill(12)
    source={'DocumentUID':'FICTIONAL-SOURCE','UniqueId':uid(1),'ETag':'"source,1"',
        'DocumentReference':'https://example.invalid/site/source.txt','ReviewedVersionRef':'source-v1',
        'content':'FICTIONAL retained original source'}
    source['sha256']=hashlib.sha256(source['content'].encode()).hexdigest()
    b={'qualificationOnly':True,'siteUrl':'https://example.invalid/site',
       'closureFolder':'/site/evidence','caseListUri':"_api/web/lists(guid'"+uid(8)+"')/items",'allowedSources':[source]}
    scope={'CaseUID':'LC-FICTIONAL-OP-CLOSED-'+str(number),'DocumentReference':'https://example.invalid/site/prepared.docx','ReviewedVersionRef':'prepared-v2','DocumentSHA256':'a'*64}
    parent={'Id':number,'GUID':uid(100+number),'Created':'2026-10-17T00:00:00Z','CaseUID':scope['CaseUID'],
            'caseStatus':'Review closed — FICTIONAL','sourceBaselineRef':'https://example.invalid/site/baseline.json','nextAction':'Preserve human note'}
    date={'FictionalTest':True,'notOperational':True,'policyAuthorityGranted':False,'scope':scope,
          'reviewDate':'2099-01-'+str(number).zfill(2),'ruleReference':'fictional://recorded-rule'}
    meta=lambda n,length:{'UniqueId':uid(n),'ETag':'"file'+str(n)+',1"','UIVersionLabel':'1.0','Length':length}
    evidence={'originalSource':meta(1,len(source['content'])),'sourceBaseline':meta(2,30),'date':meta(3,50),'dateContent':date}
    evidence['originalSource']['ETag']=source['ETag']
    contract={'kind':'fictional-prepared-closure-contract-v1','requestReference':'LC04-CLOSED-'+str(number),
        'CaseUID':scope['CaseUID'],'caseItemUri':b['caseListUri']+'('+str(number)+')',
        'initialCaseETag':'"case,3"','initialCaseStatus':'Ownership accepted — FICTIONAL',
        'observation':{'closureEvidenceConsistent':True,'nextReviewDateProvenanceConsistent':True,
            'nextOccurrencePrerequisitesConsistent':True,'preparedScope':scope,'nextReviewDate':date['reviewDate'],
            'nextReviewRuleReference':date['ruleReference'],'nextReviewEvidenceFileUID':uid(3)}}
    record={'kind':'fictional-prepared-closure-commit-v1','contract':contract,'runId':'SYNTHETIC-PRODUCER-'+str(number),
        'realPolicyEffects':False,'beforeProof':{'kind':'fictional-prepared-closure-before-v1','contract':contract,
            'beforeCaseETag':'"case,3"','beforeCase':{**parent,'caseStatus':contract['initialCaseStatus']},'evidence':evidence,'runId':'SYNTHETIC-PRODUCER-'+str(number)},
        'afterProof':{'kind':'fictional-prepared-closure-after-v1','contract':contract,'afterCase':parent,
            'afterCaseETag':'"opaque-case,4"','evidence':evidence,'runId':'SYNTHETIC-PRODUCER-'+str(number)}}
    raw=json.dumps(record).encode();cm=meta(9,len(raw));ctx={'qualified':True,'flowId':'SYNTHETIC-PRODUCER-FLOW','runId':record['runId'],
        'commit':record,'commitContentBase64':base64.b64encode(raw).decode(),'commitMetadata':cm}
    bodies={'Completed_commit_before':copy.deepcopy(cm),'Completed_commit_after':copy.deepcopy(cm),
        'Completed_commit_content':{'$content':ctx['commitContentBase64']},'Completed_case_before':copy.deepcopy(parent),
        'Completed_case_after':copy.deepcopy(parent),'Completed_source_profiles':[source],
        'Completed_originalSource_content':{'$content':base64.b64encode(source['content'].encode()).decode()},
        'Completed_unique_field':{'InternalName':'CaseUID','TypeAsString':'Text','EnforceUniqueValues':True},
        'Completed_date_field':{'InternalName':'targetDate','TypeAsString':'Text','MaxLength':255}}
    for kind in ['originalSource','sourceBaseline','date']:
        for side in ['before','after']:bodies['Completed_'+kind+'_'+side]=copy.deepcopy(evidence[kind])
    bodies['Completed_sourceBaseline_after']['ServerRelativeUrl']='/site/baseline.json'
    bodies['Completed_originalSource_after']['ServerRelativeUrl']='/site/source.txt'
    outputs={'Trusted_context':ctx,'Completed_record':record,'Completed_reference':contract['requestReference'],
        'Completed_date':date,'Completed_calendar_date_valid':True,'Completed_baseline':{'kind':'fictional-operator-initiation-request','request':{'CaseUID':parent['CaseUID'],'qualificationOnly':True,'realPolicyEffects':False,'DocumentUID':source['DocumentUID'],
            'DocumentReference':source['DocumentReference'],'ReviewedVersionRef':source['ReviewedVersionRef'],'DocumentSHA256':source['sha256']}},
        'Completed_case_before':{'headers':{'ETag':'"opaque-case,4"'}},'Completed_case_after':{'headers':{'ETag':'"opaque-case,4"'}},
        'Trigger':{'text_6':contract['requestReference']}}
    return b,bodies,outputs


class NativeCompletedReviewTests(unittest.TestCase):
    def test_skipped_observer_refuses_before_current_history_queries(self):
        from test_operator_entry import legacy_fixture
        reference = legacy_fixture()
        reference['properties']['connectionReferences'] = self.reference()['properties']['connectionReferences']
        graph = flatten(build_actions(reference, self.complete_binding()))
        gate = graph['Completed_require_observer']
        self.assertEqual(gate['runAfter'], {'Closure_check_chain': ['Succeeded']})
        self.assertEqual(graph['Completed_retained_committee']['runAfter'],
                         {'Completed_require_observer': ['Succeeded']})
        self.assertFalse(Expressions({}, {}).evaluate(gate['expression']))
        self.assertEqual(gate['else']['actions']['Completed_observer_unavailable_now']['type'], 'Terminate')
        valid = {'closureEvidenceConsistent': True, 'nextReviewDateProvenanceConsistent': True,
                 'nextOccurrencePrerequisitesConsistent': True}
        self.assertTrue(Expressions({}, {'Native_closure_observation': valid}).evaluate(gate['expression']))
        for key in valid:
            self.assertFalse(Expressions({}, {'Native_closure_observation': {**valid, key: False}})
                             .evaluate(gate['expression']))

    def test_calendar_refusal_precedes_final_gate_without_oversized_expression(self):
        b, bodies, outputs = fixture()
        graph = self.graph(b)
        self.assertEqual(graph['Completed_validate_current']['runAfter'],
                         {'Completed_calendar_date_valid': ['Succeeded']})
        self.assertEqual(graph['Completed_calendar_date_valid']['runAfter'],
                         {'Completed_case_after': ['Succeeded']})
        for value, expected in [('2099-01-01', True), ('2000-02-29', True),
                                ('2099-02-30', False), ('2099-W06-7', False),
                                ('20990101', False), ('2099-01-01T00:00:00Z', False)]:
            with self.subTest(value=value):
                outputs['Completed_date']['reviewDate'] = value
                outputs['Completed_record']['contract']['observation']['nextReviewDate'] = value
                outputs['Completed_calendar_date_valid'] = self.evaluate(
                    graph['Completed_calendar_date_valid']['inputs'], bodies, outputs)
                self.assertEqual(outputs['Completed_calendar_date_valid'], expected)
                self.assertEqual(self.evaluate(graph['Completed_validate_current']['expression'],
                                               bodies, outputs), expected)
        for action in graph.values():
            expression = action.get('expression')
            if isinstance(expression, str):
                self.assertLessEqual(len(expression), 8192)

    def test_empty_rejects_numeric_and_boolean_values_like_native_wdl(self):
        evaluator = Expressions({}, {})
        for expression in ['@empty(1)', '@empty(0)', '@empty(true)']:
            with self.subTest(expression=expression), self.assertRaises(TypeError):
                evaluator.evaluate(expression)
    def graph(self,b):return flatten(_reader_actions(b,'Trusted_context','SYNTHETIC-PRODUCER-FLOW'))
    def evaluate(self,expr,bodies,outputs):
        return Expressions(bodies,outputs).evaluate(expr.replace('triggerBody()',"outputs('Trigger')").replace('encodeUriComponent(','uriComponent('))
    def test_missing_or_self_asserted_route_never_emits_graph(self):
        for route in [None,{}, {'qualified':True}, {'state':'native-qualified'}]:
            with self.subTest(route=route),self.assertRaises(ValueError):build_actions({},fixture()[0],route)
    def runtime_binding(self):
        b, _, _ = fixture()
        for index, key in enumerate(('assuranceCollectionUri', 'readinessCollectionUri', 'consultationCollectionUri'), 20):
            b[key] = "_api/web/lists(guid'00000000-0000-4000-8000-" + str(index).zfill(12) + "')/items"
        return b

    def reference(self):
        return {'properties': {'connectionReferences': {'shared_sharepointonline': {
            'id': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
            'connectionName': 'existing-fictional-connection'}}}}

    def test_public_candidate_route_has_no_historical_connector_or_qualification_bypass(self):
        b = self.runtime_binding()
        graph = flatten(build_actions(self.reference(), b))
        self.assertFalse(graph['Completed_candidate']['inputs']['qualified'])
        self.assertTrue(graph['Completed_candidate']['inputs']['candidateOnly'])
        self.assertEqual(graph['Completed_observer_unavailable']['type'], 'Terminate')
        for action in graph.values():
            if action['type'] == 'OpenApiConnection':
                self.assertEqual(action['inputs']['parameters']['parameters/method'], 'GET')
                self.assertEqual(action['inputs']['retryPolicy'], {'type': 'none'})
        self.assertNotIn('shared_powerplatformadminv2', json.dumps(graph))
        for extra in [{'qualified': True}, {'actions': {}}, {'completedReview': {'qualified': True}}]:
            with self.assertRaises(ValueError):
                build_actions(self.reference(), {**b, **extra})
        with self.assertRaises(ValueError):
            build_actions(self.reference(), {**b, 'assuranceCollectionUri': b['caseListUri']})

    def refresh_candidate_selects(self, graph, bodies, outputs):
        for kind in ['assurance', 'readiness', 'consultation']:
            for side in ['before', 'after']:
                name = 'Completed_authoritative_' + kind + '_' + side + '_stable'
                values = []
                for row in Expressions(bodies, outputs).evaluate(graph[name]['inputs']['from']):
                    outputs['Current_item'] = row
                    values.append(Expressions(bodies, outputs).evaluate(graph[name]['inputs']['select']))
                bodies[name] = values

    def test_candidate_runtime_paths_and_complete_history_stability(self):
        b = self.runtime_binding(); graph = flatten(build_actions(self.reference(), b))
        _, bodies, outputs = fixture()
        bodies['Completed_candidate_before'] = bodies['Completed_commit_before']
        bodies['Completed_candidate_after'] = bodies['Completed_commit_after']
        outputs['Completed_candidate_record'] = outputs['Completed_record']
        for side in ('before', 'after'):
            bodies['Completed_authoritative_case_' + side] = bodies['Completed_case_' + side]
            outputs['Completed_authoritative_case_' + side] = outputs['Completed_case_' + side]
            for key in ('assurance', 'readiness', 'consultation'):
                bodies['Completed_authoritative_' + key + '_' + side] = {'value': []}
        self.refresh_candidate_selects(graph, bodies, outputs)
        for name in ('Completed_selection', 'Completed_candidate_shape', 'Completed_authoritative_stable'):
            self.assertTrue(self.evaluate(graph[name]['expression'], bodies, outputs), name)
        path = self.evaluate(graph['Completed_candidate_content']['inputs']['parameters']['parameters/uri'], bodies, outputs)
        self.assertTrue(path.endswith("LC04-closure-LC04-CLOSED-1-commit.json')/$value"), path)
        for key in ('odata.nextLink', '@odata.nextLink', 'nextLink'):
            changed = copy.deepcopy(bodies)
            changed['Completed_authoritative_assurance_after'][key] = 'next'
            self.refresh_candidate_selects(graph, changed, outputs)
            self.assertFalse(self.evaluate(graph['Completed_authoritative_stable']['expression'], changed, outputs))
        changed = copy.deepcopy(bodies)
        changed['Completed_authoritative_case_after']['nextAction'] = 'Human edit'
        self.assertFalse(self.evaluate(graph['Completed_authoritative_stable']['expression'], changed, outputs))
        changed = copy.deepcopy(bodies)
        changed['Completed_authoritative_assurance_after']['value'] = [{'ParentEventUID': 'changed'}]
        self.refresh_candidate_selects(graph, changed, outputs)
        self.assertFalse(self.evaluate(graph['Completed_authoritative_stable']['expression'], changed, outputs))

    def test_only_transport_row_identifiers_are_ignored_complete_wrappers_survive(self):
        graph = flatten(build_actions(self.reference(), self.runtime_binding()))
        _, bodies, outputs = fixture()
        outputs['Completed_candidate_record'] = outputs['Completed_record']
        for side in ['before', 'after']:
            bodies['Completed_authoritative_case_' + side] = {**bodies['Completed_case_' + side], 'odata.id': side}
            outputs['Completed_authoritative_case_' + side] = copy.deepcopy(outputs['Completed_case_' + side])
            for kind in ['assurance', 'readiness', 'consultation']:
                bodies['Completed_authoritative_' + kind + '_' + side] = {
                    'odata.metadata': 'unchanged-metadata', 'FutureWrapper': {'mode': 'retain'},
                    'value': [{'Id': 1, 'GUID': 'unchanged-guid', 'EventUID': 'FICTIONAL-' + kind,
                               'odata.etag': '"1"', 'odata.id': side,
                               'Summary': 'Preserve human finding', 'Business': {'odata.id': 'human-data'}}]}
        raw = copy.deepcopy(bodies)
        self.refresh_candidate_selects(graph, bodies, outputs)
        expr = graph['Completed_authoritative_stable']['expression']
        self.assertTrue(self.evaluate(expr, bodies, outputs))
        # Raw inputs remain intact; only separately named Select outputs exist.
        for name, value in raw.items(): self.assertEqual(bodies[name], value)
        for mutation in ['case-human', 'case-token', 'unknown-case-null', 'row-human', 'row-token',
                         'unknown-row-null', 'nested-business-id', 'wrapper-change', 'unknown-wrapper-null']:
            changed = copy.deepcopy(raw); changed_outputs = copy.deepcopy(outputs)
            case = changed['Completed_authoritative_case_after']
            wrapper = changed['Completed_authoritative_assurance_after']; row = wrapper['value'][0]
            if mutation == 'case-human': case['nextAction'] = 'Human changed action'
            elif mutation == 'case-token': changed_outputs['Completed_authoritative_case_after']['headers']['ETag'] = 'changed'
            elif mutation == 'unknown-case-null': case['FutureHumanField'] = None
            elif mutation == 'row-human': row['Summary'] = 'Human edited finding'
            elif mutation == 'row-token': row['odata.etag'] = 'changed'
            elif mutation == 'unknown-row-null': row['FutureHumanField'] = None
            elif mutation == 'nested-business-id': row['Business']['odata.id'] = 'changed human data'
            elif mutation == 'wrapper-change': wrapper['FutureWrapper']['mode'] = 'changed'
            else: wrapper['FutureWrapperNull'] = None
            self.refresh_candidate_selects(graph, changed, changed_outputs)
            self.assertFalse(self.evaluate(expr, changed, changed_outputs), mutation)
        self.assertIn('setProperty(', expr)
        for kind in ['assurance', 'readiness', 'consultation']:
            for side in ['before', 'after']:
                name = 'Completed_authoritative_' + kind + '_' + side + '_stable'
                self.assertEqual(graph[name]['inputs']['select'], "@union(item(),json('{\"odata.id\":null}'))")

    def historical_fixture(self, number=1):
        b, bodies, outputs = fixture(number)
        graph = flatten(build_actions(self.reference(), self.runtime_binding()))
        outputs['Completed_candidate_record'] = copy.deepcopy(outputs['Completed_record'])
        outputs['Completed_proof_before'] = copy.deepcopy(outputs['Completed_record']['beforeProof'])
        outputs['Completed_proof_after'] = copy.deepcopy(outputs['Completed_record']['afterProof'])
        bodies['Completed_authoritative_case_after'] = copy.deepcopy(bodies['Completed_case_after'])
        outputs['Completed_authoritative_case_after'] = copy.deepcopy(outputs['Completed_case_after'])
        for record in [outputs['Completed_candidate_record']['contract'],
                       outputs['Completed_candidate_record']['beforeProof']['contract'],
                       outputs['Completed_candidate_record']['afterProof']['contract'],
                       outputs['Completed_proof_before']['contract'], outputs['Completed_proof_after']['contract']]:
            record['patch'] = {'caseStatus': 'Review closed — FICTIONAL'}
        for kind in ['before', 'after']:
            for side in ['before', 'after']:
                bodies['Completed_proof_' + kind + '_metadata_' + side] = {'UniqueId': kind, 'ETag': '"proof,1"', 'UIVersionLabel': '1.0', 'Length': 100}
        return graph, bodies, outputs

    def test_historical_continuity_preserves_original_status_and_two_occurrences(self):
        for number in [1, 2]:
            graph, bodies, outputs = self.historical_fixture(number)
            self.assertTrue(self.evaluate(graph['Completed_verify_historical_continuity']['expression'], bodies, outputs))
            self.assertEqual(outputs['Completed_proof_before']['beforeCase']['caseStatus'], 'Ownership accepted — FICTIONAL')
            self.assertEqual(outputs['Completed_proof_after']['afterCase']['caseStatus'], 'Review closed — FICTIONAL')
            result = graph['Completed_historical_continuity']['inputs']
            self.assertFalse(result['nativeObserverQualified'])
            self.assertEqual(result['beforeCase'], "@outputs('Completed_proof_before')?['beforeCase']")

    def test_historical_proof_human_unknown_field_and_token_changes_hold(self):
        for mutation in ['separate-proof', 'human-current', 'unknown-field', 'status', 'token', 'metadata']:
            graph, bodies, outputs = self.historical_fixture()
            if mutation == 'separate-proof': outputs['Completed_proof_before']['runId'] = 'changed'
            elif mutation == 'human-current': bodies['Completed_authoritative_case_after']['nextAction'] = 'human edit'
            elif mutation == 'unknown-field':
                outputs['Completed_proof_before']['beforeCase']['FutureHumanField'] = 'original'
                outputs['Completed_candidate_record']['beforeProof']['beforeCase']['FutureHumanField'] = 'original'
            elif mutation == 'status':
                outputs['Completed_proof_before']['beforeCase']['caseStatus'] = 'Unaccepted'
                outputs['Completed_candidate_record']['beforeProof']['beforeCase']['caseStatus'] = 'Unaccepted'
            elif mutation == 'token': outputs['Completed_authoritative_case_after']['headers']['ETag'] = 'changed'
            else: bodies['Completed_proof_after_metadata_after']['ETag'] = 'changed'
            self.assertFalse(self.evaluate(graph['Completed_verify_historical_continuity']['expression'], bodies, outputs), mutation)

    def test_opt_in_runtime_trace_keeps_legacy_and_distinguishes_recovery_committer(self):
        from build_native_completed_review import _historical_continuity_actions
        for committer in ('SYNTHETIC-PRODUCER-1','RECOVERY-B'):
            _,bodies,outputs=self.historical_fixture()
            binding=fixture()[0];binding['runtimeClosureTraceVersion']=1
            graph=flatten(_historical_continuity_actions(binding))
            record=outputs['Completed_candidate_record'];origin=record['beforeProof']['runId']
            record.update(runtimeTraceVersion=1,originRunId=origin,committedByRun=committer,runId=committer)
            for contract in (record['contract'],record['beforeProof']['contract'],record['afterProof']['contract'],
                             outputs['Completed_proof_before']['contract'],outputs['Completed_proof_after']['contract']):
                contract['runtimeTraceVersion']=1
            expression=graph['Completed_verify_historical_continuity']['expression']
            self.assertTrue(self.evaluate(expression,bodies,outputs),committer)
            for mutation in ('beforeOrigin','afterOrigin','commitActor','noTrace','noVersion','foreignCase','foreignSource'):
                changed=copy.deepcopy(outputs);r=changed['Completed_candidate_record']
                if mutation=='beforeOrigin':
                    changed['Completed_proof_before']['runId']='OTHER';r['beforeProof']=copy.deepcopy(changed['Completed_proof_before'])
                elif mutation=='afterOrigin':
                    changed['Completed_proof_after']['runId']='OTHER';r['afterProof']=copy.deepcopy(changed['Completed_proof_after'])
                elif mutation=='commitActor':r['committedByRun']='OTHER'
                elif mutation=='noTrace':r.pop('originRunId')
                elif mutation=='noVersion':r.pop('runtimeTraceVersion')
                elif mutation=='foreignCase':bodies2=copy.deepcopy(bodies);bodies2['Completed_authoritative_case_after']['CaseUID']='OTHER'
                else:
                    changed['Completed_proof_before']['beforeCase']['sourceBaselineRef']='https://other.invalid/source'
                    r['beforeProof']=copy.deepcopy(changed['Completed_proof_before'])
                self.assertFalse(self.evaluate(expression,bodies2 if mutation=='foreignCase' else bodies,changed),mutation)
            # The legacy default must still refuse recovered run B, even if
            # arbitrary extra origin fields are present on its JSON record.
            legacy=flatten(_historical_continuity_actions(fixture()[0]))
            self.assertEqual(self.evaluate(legacy['Completed_verify_historical_continuity']['expression'],bodies,outputs),committer==origin)
        graph,bodies,outputs=self.historical_fixture()
        binding=fixture()[0];binding['runtimeClosureTraceVersion']=1
        opt=flatten(_historical_continuity_actions(binding))
        self.assertTrue(self.evaluate(opt['Completed_verify_historical_continuity']['expression'],bodies,outputs))
        for bad in (True,False,0,2,'1'):
            with self.assertRaises(ValueError):_historical_continuity_actions({**binding,'runtimeClosureTraceVersion':bad})

    def test_historical_prepared_reader_preserves_all_but_explicit_status_continuity(self):
        from test_selected_event_routes import fixtures as prepared_fixture
        from build_prepared_revision_check import build_actions as canonical_reader
        context, _, _ = prepared_fixture()
        actions = context['properties']['definition']['actions']['Resolve_context']['actions']
        baseline = actions['Verify_baseline_boundary']['actions']
        baseline['Read_baseline_before'] = copy.deepcopy(actions['Read_selected_case'])
        baseline['Verify_request']['actions']['Read_source_before'] = copy.deepcopy(actions['Read_selected_case'])
        binding = {'artifactFolderRelative': '/site/evidence', 'caseEvidenceFieldType': 'Note',
                   'templateFileUniqueId': '00000000-0000-4000-8000-000000000098'}
        graph = build_historical_prepared_reader(context, binding)
        baseline = canonical_reader(context, binding, "outputs('Completed_historical_continuity')")
        changed = flatten(graph); original = flatten(baseline)
        expected = {'Check_prepared_ownership', 'Verify_prepared_revision'}
        for name in original:
            if name not in expected:
                self.assertEqual({k: v for k, v in changed[name].items() if k not in ('actions', 'else')},
                                 {k: v for k, v in original[name].items() if k not in ('actions', 'else')}, name)
        expr = changed['Verify_prepared_revision']['expression']
        self.assertIn("?['beforeCase']?['caseStatus']", expr)
        self.assertIn("?['currentCase']", expr)
        self.assertIn("?['caseSnapshot']?['snapshot']?['caseStatus']", expr)
        self.assertNotIn("?['snapshot']?['caseStatus'],body('Read_prepared_case')", expr)

    def complete_binding(self):
        binding = self.runtime_binding()
        binding['caseListUri'] = "_api/web/lists(guid'00000000-0000-4000-8000-000000000001')/items"
        binding['evidenceFolder'] = '/site/PPG Review Evidence/Templates'
        binding['closureFolder'] = '/site/PPG Review Evidence/Templates/Retained closure history'
        binding.update(requiredFictionalRoles=['FICTIONAL content-review role'],
                       purposeReferences={role: 'fictional://purpose/' + role for role in ('committee', 'officer', 'coordinator', 'authorisation')},
                       artifactFolderRelative='/site/PPG Review Evidence/Templates', caseEvidenceFieldType='Note',
                       templateFileUniqueId='00000000-0000-4000-8000-000000000098')
        return binding

    def test_connected_origin_prepared_and_authoritative_observer_geometry(self):
        from build_operator_entry import build, action_references, _flatten
        from test_operator_entry import legacy_fixture
        legacy = legacy_fixture()
        legacy['properties']['connectionReferences'] = self.reference()['properties']['connectionReferences']
        graph = build(legacy, self.complete_binding())
        actions = graph['properties']['definition']['actions']; nodes = flatten(actions)
        self.assertIn('Origin_Completed_context', nodes)
        self.assertIn('Native_prepared_revision', nodes)
        self.assertIn('Native_closure_observation', nodes)
        self.assertIn('Completed_evidence_ready', nodes)
        self.assertNotIn('Completed_observer_unavailable', nodes)
        self.assertIn('NextOccurrence_Native_initiation_receipt', nodes)
        self.assertNotIn('Completed_writer_unavailable', nodes)
        self.assertFalse(action_references(actions) - _flatten(actions).keys())
        audit = audit_actions(graph['properties']['definition'])
        self.assertLessEqual(audit['maximumActionDepth'], 8)
        self.assertLessEqual(audit['actionCount'], 500)
        new = flatten(nodes['NextReview_Entry']['actions'])
        writers = []
        for name, action in new.items():
            if action['type'] == 'OpenApiConnection' and action['inputs']['parameters']['parameters/method'] != 'GET':
                writers.append(name)
                self.assertEqual(action['inputs']['retryPolicy'], {'type': 'none'})
        self.assertEqual(set(writers), {'NextOccurrence_Create_request', 'NextOccurrence_Next_create_intent',
                                       'NextOccurrence_Create_case', 'NextOccurrence_Next_create_receipt'})
        text = json.dumps(new)
        self.assertNotIn('Unused_runtime_comparison', text)
        self.assertNotIn('SYNTHETIC-PRODUCER', text)

    def writer_context(self):
        from test_operator_entry import legacy_fixture
        from test_next_review_occurrence import NextReviewTests, fixture as canonical_fixture
        from test_prepared_closure_check import Expressions as CanonicalExpressions
        legacy = legacy_fixture()
        legacy['properties']['connectionReferences'] = self.reference()['properties']['connectionReferences']
        binding = self.complete_binding()
        graph = flatten(build_runtime_next_writer(legacy, binding))
        _, old = NextReviewTests().receipt_context()
        bodies = {'NextOccurrence_' + k: copy.deepcopy(v) for k, v in old.bodies.items()}
        outputs = {'NextOccurrence_' + k: copy.deepcopy(v) for k, v in old.outputs.items()}
        _, frozen = canonical_fixture()
        outputs['Origin_Completed_context'] = {'closedCase': frozen['completedReview']['case'],
            'closedCaseETag': frozen['completedCaseETag'], 'date': frozen['date']['record'],
            'dateMetadata': frozen['date']['metadata'], 'originalSource': binding['allowedSources'][0]}
        bodies['Completed_candidate_after'] = frozen['closureCommit']['metadata']
        bodies['NextOccurrence_Recheck_source']['ETag'] = binding['allowedSources'][0]['ETag']
        outputs['Test_trigger'] = {'text': 'LC02-OP-NEW-A', 'text_1': 'OCC-NEW-A'}
        outputs['NextOccurrence_Next_history_before_receipt_consistent'] = True
        outputs['NextOccurrence_Next_history_after_receipt_consistent'] = True
        ev = CanonicalExpressions(bodies, outputs)
        payload = graph['NextOccurrence_Next_receipt_payload']['inputs']
        outputs['NextOccurrence_Next_receipt_payload'] = {k: ev.evaluate(v) for k, v in payload.items()}
        outputs['NextOccurrence_Next_saved_receipt'] = copy.deepcopy(outputs['NextOccurrence_Next_receipt_payload'])
        outputs['NextOccurrence_Next_completion_verified'] = ev.evaluate(graph['NextOccurrence_Next_completion_verified']['inputs'])
        return graph, ev

    def test_runtime_writer_replay_recovery_changed_request_and_stale_guards(self):
        for cases, receipts, expected_count, recovery in [(0, 0, 1, False), (1, 0, 0, True), (1, 1, 0, False)]:
            graph, ev = self.writer_context()
            ev.bodies['NextOccurrence_Find_case'] = {'value': [{}] * cases}
            ev.bodies['NextOccurrence_Next_find_receipt'] = {'value': [{}] * receipts}
            result = graph['NextOccurrence_Native_initiation_receipt']['inputs']
            self.assertTrue(ev.evaluate(graph['NextOccurrence_Final_source_guard']['expression']))
            self.assertTrue(ev.evaluate(result['qualified']))
            self.assertEqual(ev.evaluate(result['caseCreatedCount']), expected_count)
            self.assertEqual(ev.evaluate(result['recoveredExistingCase']), recovery)
        graph, ev = self.writer_context()
        request = {'requestReference': 'LC02-OP-A', 'proposedRole': 'FICTIONAL proposed role'}
        ev.outputs['NextOccurrence_Request'] = request
        ev.outputs['NextOccurrence_Retained_request'] = {'request': copy.deepcopy(request)}
        self.assertTrue(ev.evaluate(graph['NextOccurrence_Verify_request']['expression']))
        ev.outputs['NextOccurrence_Retained_request']['request']['proposedRole'] = 'changed'
        self.assertFalse(ev.evaluate(graph['NextOccurrence_Verify_request']['expression']))
        ev.outputs['NextOccurrence_Next_parent_final']['headers']['ETag'] = 'stale'
        self.assertFalse(ev.evaluate(graph['NextOccurrence_Final_source_guard']['expression']))
        ev.bodies['NextOccurrence_Next_find_intent'] = {'value': [{}]}
        self.assertFalse(ev.evaluate(graph['NextOccurrence_Next_require_new_intent']['expression']))

    def test_writer_runtime_paths_and_origin_frame_are_not_compiled_occurrence_pins(self):
        graph, ev = self.writer_context()
        for suffix in ['NEW-A', 'SECOND-B']:
            ev.outputs['Test_trigger']['text'] = 'LC02-OP-' + suffix
            uri = ev.evaluate(graph['NextOccurrence_Next_find_intent']['inputs']['parameters']['parameters/uri'])
            self.assertIn('LC02-next-case-intent-LC02-OP-' + suffix + '.json', uri)
        frame = graph['NextOccurrence_Next_write_frame_current']['expression']
        self.assertTrue(ev.evaluate(frame))
        ev.bodies['NextOccurrence_Next_date_before']['ETag'] = 'changed'
        self.assertFalse(ev.evaluate(frame))
        self.assertEqual(graph['NextOccurrence_Next_date_before']['type'], 'OpenApiConnection')
        self.assertEqual(graph['NextOccurrence_Request_name']['runAfter'], {'NextOccurrence_Next_write_frame_current': ['Succeeded']})

    def runtime_chain_result(self, rows, candidate_selections=None, scope=None):
        from test_prepared_closure_check import fixture as closure_fixture, SCOPE, Expressions as ChainExpressions
        context, binding, _ = closure_fixture(True)
        graph = build_runtime_closure_observer(context, binding)['Closure_check_chain']['actions']
        ev = ChainExpressions({'Closure_assurance_before': {'value': rows},
                               'Closure_Readiness_scope': [{'AssessedOn': '2026-10-18T14:00:00Z'}]}, {
            'Native_prepared_revision': {'preparedRevision': {'scope': scope or SCOPE}},
            'Closure_Native_readiness_observation': {'selectedEventUID': 'FICTIONAL-ready'},
            'Completed_candidate_record': {'contract': {'observation': {'selectedEvents': candidate_selections or binding['selectedEvents']}}}})
        for name, action in graph.items():
            if name == 'Closure_assurance_before': continue
            if action['type'] in ['Query', 'Select']:
                result = []
                for row in ev.evaluate(action['inputs']['from']):
                    ev.current = row
                    if action['type'] == 'Select': result.append(ev.evaluate(action['inputs']['select']))
                    elif ev.evaluate(action['inputs']['where']): result.append(row)
                ev.bodies[name] = result
            elif action['type'] == 'Compose': ev.outputs[name] = ev.evaluate(action['inputs'])
            else: raise AssertionError('Unexpected action before chain result')
            if name == 'Closure_chain_consistent': return ev.outputs[name]
        raise AssertionError('Missing chain result')

    def test_runtime_chain_recomputes_two_occurrences_and_rejects_altered_selection(self):
        from test_prepared_closure_check import fixture as closure_fixture, SCOPE
        from build_prepared_closure_check import CHAIN
        _, binding, rows = closure_fixture(True)
        self.assertTrue(self.runtime_chain_result(rows))
        other = copy.deepcopy(rows); selections = {}
        scope = {**SCOPE, 'CaseUID': 'LC-FICTIONAL-OP-OTHER-COMPLETED'}
        for index, role in enumerate(CHAIN):
            selections[role] = 'FICTIONAL-OTHER-' + role
            other[index].update(scope, EventUID=selections[role],
                                ParentEventUID=None if index == 0 else selections[CHAIN[index - 1]])
        self.assertTrue(self.runtime_chain_result(other, selections, scope))
        bad = dict(binding['selectedEvents']); bad['verification'] = 'FICTIONAL-NONEXISTENT'
        self.assertFalse(self.runtime_chain_result(rows, bad))
        for mutation in ['parent', 'duplicate', 'adverse', 'stale']:
            changed = copy.deepcopy(rows)
            if mutation == 'parent': changed[3]['ParentEventUID'] = rows[0]['EventUID']
            elif mutation == 'duplicate': changed.append(copy.deepcopy(rows[2]))
            elif mutation == 'adverse': changed[-1]['VerificationResult'] = 'Failed'
            else: changed[1]['odata.etag'] = '*'
            self.assertFalse(self.runtime_chain_result(changed), mutation)

    def test_selected_snapshot_row_edits_and_candidate_pin_changes_hold_writer(self):
        from test_operator_entry import legacy_fixture
        from test_prepared_closure_check import fixture as closure_fixture, SCOPE
        from build_operator_entry import build
        _, binding, rows = closure_fixture(True)
        legacy = legacy_fixture(); legacy['properties']['connectionReferences'] = self.reference()['properties']['connectionReferences']
        graph = flatten(build(legacy, self.complete_binding())['properties']['definition']['actions'])
        observation = {'closureEvidenceConsistent': True, 'nextReviewDateProvenanceConsistent': True,
            'nextOccurrencePrerequisitesConsistent': True, 'preparedScope': SCOPE, 'selectedEvents': binding['selectedEvents'],
            'issuedFile': {'UniqueId': 'issued', 'ETag': '"issued,1"'}, 'nextReviewEvidenceFileUID': 'date',
            'nextReviewDate': '2099-01-01', 'nextReviewRuleReference': 'fictional://rule'}
        outputs = {'Completed_prewrite_history_consistent': True, 'Native_closure_observation': observation,
                   'Completed_candidate_record': {'contract': {'observation': copy.deepcopy(observation)}}}
        bodies = {}
        for role, row in zip(('committee', 'officer', 'coordinator', 'authorisation', 'publication', 'implementation', 'verification'), rows):
            bodies['Closure_selected_' + role] = [copy.deepcopy(row)]
            bodies['Completed_retained_' + role] = [copy.deepcopy(row)]
        for kind in ['readiness', 'consultation']:
            for side in ['retained', 'current']: bodies['Completed_' + side + '_' + kind + '_stable'] = [{'EventUID': kind}]
        expr = graph['Completed_evidence_ready']['expression']
        self.assertTrue(self.evaluate(expr, bodies, outputs))
        changed = copy.deepcopy(bodies); changed['Closure_selected_officer'][0]['Summary'] = 'Altered human finding'
        self.assertFalse(self.evaluate(expr, changed, outputs))
        changed = copy.deepcopy(bodies); changed['Closure_selected_officer'][0]['odata.etag'] = 'changed'
        self.assertFalse(self.evaluate(expr, changed, outputs))
        changed = copy.deepcopy(outputs); changed['Completed_candidate_record']['contract']['observation']['preparedScope']['DocumentSHA256'] = '0' * 64
        self.assertFalse(self.evaluate(expr, bodies, changed))

    def test_recorded_closure_path_is_distinct_from_new_output_folder(self):
        from test_operator_entry import legacy_fixture
        from build_operator_entry import build
        legacy = legacy_fixture(); legacy['properties']['connectionReferences'] = self.reference()['properties']['connectionReferences']
        binding = self.complete_binding()
        graph = flatten(build(legacy, binding)['properties']['definition']['actions'])
        # Regression for the actual 404 shape: commit was retained below the
        # output folder. Use two arbitrary references with the SAME emitted graph.
        for reference in ['LC04-RETAINED-A', 'LC04-OTHER-COMPLETED-B']:
            outputs = {'Completed_reference': reference, 'Origin_Completed_reference': reference,
                       'Trigger': {'text': 'LC02-OP-NEW-A'}}
            for name in ['Completed_candidate_before', 'Origin_Completed_commit_before']:
                uri = self.evaluate(graph[name]['inputs']['parameters']['parameters/uri'], {}, outputs)
                recorded = binding['closureFolder'] + '/LC04-closure-' + reference + '-commit.json'
                self.assertIn("decodedurl='" + binding['closureFolder'] + "'", uri)
                self.assertIn("Files('" + recorded.rsplit('/', 1)[1] + "')", uri)
            for kind in ['before', 'after']:
                name = 'Completed_proof_' + kind + '_metadata_before'
                uri = self.evaluate(graph[name]['inputs']['parameters']['parameters/uri'], {}, outputs)
                self.assertIn("decodedurl='" + binding['closureFolder'] + "'", uri)
                self.assertIn(reference + '-' + kind + '.json', uri)
        # The new request/intent/receipt stay in the existing output folder.
        writer, ev = self.writer_context()
        for name in ['NextOccurrence_Next_find_intent', 'NextOccurrence_Next_create_intent',
                     'NextOccurrence_Next_read_intent', 'NextOccurrence_Next_find_receipt',
                     'NextOccurrence_Next_create_receipt', 'NextOccurrence_Next_read_receipt']:
            uri = ev.evaluate(writer[name]['inputs']['parameters']['parameters/uri'])
            self.assertIn("decodedurl='" + binding['evidenceFolder'] + "'", uri)
            self.assertNotIn(binding['closureFolder'], uri)
        for folder in ['/other-site/history', '/site/PPG Review Evidence/Templates/../outside',
                       '/site/PPG Review Evidence/Templates/bad%2fpath']:
            bad = {**binding, 'closureFolder': folder}
            with self.assertRaises(ValueError): build(legacy, bad)
        bad = dict(binding); bad.pop('evidenceFolder')
        with self.assertRaises(ValueError): build(legacy, bad)
        bad = {**binding, 'caseListUri': "_api/web/lists(guid'00000000-0000-4000-8000-000000000099')/items"}
        with self.assertRaisesRegex(ValueError, 'existing native case site/list'):
            build(legacy, bad)

    def test_history_drift_and_pagination_hold_at_all_three_effect_boundaries(self):
        from test_operator_entry import legacy_fixture
        from build_operator_entry import build
        legacy = legacy_fixture(); legacy['properties']['connectionReferences'] = self.reference()['properties']['connectionReferences']
        graph = flatten(build(legacy, self.complete_binding())['properties']['definition']['actions'])
        expected = {'assurance': 'Closure_assurance_stable_after',
                    'readiness': 'Closure_Readiness_stable_after',
                    'consultation': 'Closure_Readiness_consultation_stable_after'}
        for prefix in ['Completed_prewrite_history', 'NextOccurrence_Next_history_before_receipt',
                       'NextOccurrence_Next_history_after_receipt']:
            bodies = {}; outputs = {}
            for kind, snapshot in expected.items():
                row = {'Id': 1, 'EventUID': 'FICTIONAL-' + kind, 'odata.etag': '"1"',
                       'HumanFinding': 'Preserve complete recorded text', 'odata.id': None}
                bodies[snapshot] = [copy.deepcopy(row)]
                bodies[prefix + '_' + kind] = {'value': [copy.deepcopy(row)]}
            def evaluate():
                for kind in expected:
                    action = prefix + '_' + kind + '_stable'
                    values = []
                    for row in bodies[prefix + '_' + kind]['value']:
                        outputs['Current_item'] = row
                        values.append(self.evaluate(graph[action]['inputs']['select'], bodies, outputs))
                    bodies[action] = values
                return self.evaluate(graph[prefix + '_consistent']['inputs'], bodies, outputs)
            self.assertTrue(evaluate(), prefix)
            for kind in expected:
                for key, value in [('odata.etag', 'changed'), ('HumanFinding', 'altered'), ('FutureHumanField', 'new')]:
                    row = bodies[prefix + '_' + kind]['value'][0]
                    saved = copy.deepcopy(row); row[key] = value
                    self.assertFalse(evaluate(), (prefix, kind, key))
                    bodies[prefix + '_' + kind]['value'][0] = saved
                for key in ['odata.nextLink', '@odata.nextLink', 'nextLink']:
                    bodies[prefix + '_' + kind][key] = 'next'
                    self.assertFalse(evaluate(), (prefix, kind, key))
                    bodies[prefix + '_' + kind].pop(key)
            self.assertTrue(evaluate(), prefix)
        self.assertIn("equals(outputs('Completed_prewrite_history_consistent'),true)", graph['Completed_evidence_ready']['expression'])
        self.assertEqual(graph['NextOccurrence_Final_source_guard']['runAfter'],
                         {'NextOccurrence_Next_history_before_receipt_consistent': ['Succeeded']})

    def test_post_receipt_drift_keeps_saved_effects_but_fails_completion_and_replay(self):
        graph, ev = self.writer_context()
        ev.bodies['NextOccurrence_Find_case'] = {'value': [{}]}
        ev.bodies['NextOccurrence_Next_find_receipt'] = {'value': [{}]}
        saved = copy.deepcopy(ev.outputs['NextOccurrence_Next_saved_receipt'])
        ev.outputs['NextOccurrence_Next_history_before_receipt_consistent'] = False
        self.assertFalse(ev.evaluate(graph['NextOccurrence_Final_source_guard']['expression']))
        ev.outputs['NextOccurrence_Next_history_before_receipt_consistent'] = True
        ev.outputs['NextOccurrence_Next_history_after_receipt_consistent'] = False
        ev.outputs['NextOccurrence_Next_completion_verified'] = ev.evaluate(graph['NextOccurrence_Next_completion_verified']['inputs'])
        result = graph['NextOccurrence_Native_initiation_receipt']['inputs']
        self.assertFalse(ev.evaluate(result['qualified']))
        self.assertIsNone(ev.evaluate(result['caseCreatedCount']))
        self.assertIsNone(ev.evaluate(result['requestCreatedCount']))
        self.assertTrue(ev.evaluate(result['reconcileBeforeRetry']))
        ev.outputs['NextOccurrence_Native_initiation_receipt'] = {'qualified': ev.evaluate(result['qualified'])}
        guard = graph['NextOccurrence_Next_require_verified_completion']
        self.assertFalse(ev.evaluate(guard['expression']))
        hold = graph['NextOccurrence_Next_post_receipt_hold']
        self.assertEqual(hold['type'], 'Terminate')
        self.assertEqual(hold['inputs']['runStatus'], 'Failed')
        self.assertEqual(ev.outputs['NextOccurrence_Next_saved_receipt'], saved)
        # A later unchanged, fully revalidated replay can qualify without create.
        ev.outputs['NextOccurrence_Next_history_after_receipt_consistent'] = True
        ev.outputs['NextOccurrence_Next_completion_verified'] = ev.evaluate(graph['NextOccurrence_Next_completion_verified']['inputs'])
        self.assertTrue(ev.evaluate(result['qualified']))
        self.assertEqual(ev.evaluate(result['caseCreatedCount']), 0)
        self.assertFalse(ev.evaluate(graph['NextOccurrence_Ensure_case']['expression']))

    def test_pipeline_linearization_keeps_refusal_before_all_hoisted_reads(self):
        graph = build_actions(self.reference(), self.runtime_binding())
        self.assertEqual(graph['Completed_reference']['runAfter'], {'Completed_selection': ['Succeeded']})
        self.assertEqual(graph['Completed_authoritative_case_before']['runAfter'], {'Completed_candidate_shape': ['Succeeded']})
        self.assertEqual(graph['Completed_proof_before_metadata_before']['runAfter'], {'Completed_authoritative_stable': ['Succeeded']})
        self.assertEqual(graph['Completed_historical_continuity']['runAfter'], {'Completed_verify_historical_continuity': ['Succeeded']})
        for action in graph.values():
            if action['type'] == 'If':
                self.assertTrue(all(a['type'] == 'Terminate' for a in action['else']['actions'].values()))
        self.assertLessEqual(audit_actions({'actions': graph})['maximumActionDepth'], 2)
        unsafe = {'Gate': {'type': 'If', 'expression': '@false', 'actions': {},
                          'else': {'actions': {'Silent': {'type': 'Compose', 'inputs': False, 'runAfter': {}}}}, 'runAfter': {}}}
        with self.assertRaises(ValueError):
            _linearize_refusing_pipeline(unsafe)

    def test_runtime_observer_reuses_canonical_chain_with_node_scoped_selection(self):
        from test_prepared_closure_check import fixture as closure_fixture
        context, binding, _ = closure_fixture(True)
        original = copy.deepcopy((context, binding))
        graph = build_runtime_closure_observer(context, binding)
        nodes = flatten(graph)
        self.assertEqual((context, binding), original)
        for role in ('committee', 'officer', 'coordinator', 'authorisation', 'publication', 'implementation', 'verification'):
            self.assertIn("outputs('Completed_candidate_record')", nodes['Closure_selected_' + role]['inputs']['where'])
            self.assertIn("outputs('Completed_candidate_record')", nodes['Closure_superseders_' + role]['inputs']['where'])
        for name in ('Closure_date_before', 'Closure_date_content', 'Closure_date_after', 'Closure_final_date'):
            uri = nodes[name]['inputs']['parameters']['parameters/uri']
            self.assertTrue(uri.startswith('@concat('))
            self.assertIn("?['nextReviewEvidenceFileUID']", uri)
        # Still a real seven-stage/full-history observer, with no mutations.
        self.assertIn('Closure_chain_consistent', nodes)
        self.assertIn('Closure_frame_consistent', nodes)
        for action in nodes.values():
            if action['type'] == 'OpenApiConnection':
                self.assertEqual(action['inputs']['parameters']['parameters/method'], 'GET')
        combined = copy.deepcopy(context['properties']['definition'])
        combined['actions'].update(graph)
        self.assertLessEqual(audit_actions(combined)['maximumActionDepth'], 8)

    def test_two_runtime_closures_use_same_graph_without_case_snapshot_compilation(self):
        first=None
        for number in [1,2]:
            b,bodies,outputs=fixture(number);graph=self.graph(b)
            if first is None:first=graph
            self.assertEqual(graph,first)
            for name in ['Completed_select','Completed_validate_record','Completed_validate_current']:
                self.assertTrue(self.evaluate(graph[name]['expression'],bodies,outputs),name)
            text=json.dumps(graph);self.assertNotIn(outputs['Completed_record']['afterProof']['afterCase']['CaseUID'],text)
            self.assertNotIn(outputs['Completed_record']['runId'],text)
    def test_native_uris_preserve_guid_quotes_and_selected_path(self):
        b,bodies,outputs=fixture();g=self.graph(b)
        uri=self.evaluate(g['Completed_commit_content']['inputs']['parameters']['parameters/uri'],bodies,outputs)
        self.assertEqual(uri,"_api/web/GetFolderByServerRelativePath(decodedurl='/site/evidence')/Files('LC04-closure-LC04-CLOSED-1-commit.json')/$value")
        uri=self.evaluate(g['Completed_case_before']['inputs']['parameters']['parameters/uri'],bodies,outputs)
        self.assertEqual(uri,b['caseListUri']+'(1)')
    def test_input_path_injection_and_unqualified_producer_refuse_before_reads(self):
        b,bodies,outputs=fixture();g=self.graph(b)
        for value in ['LC04-','../commit',"LC04-a'",'LC04-a/b','LC04-a%2fb','LC04-..-x']:
            changed=copy.deepcopy(outputs);changed['Trigger']['text_6']=value
            self.assertFalse(self.evaluate(g['Completed_select']['expression'],bodies,changed),value)
        changed=copy.deepcopy(outputs);changed['Trusted_context']['qualified']=False
        self.assertFalse(self.evaluate(g['Completed_select']['expression'],bodies,changed))
    def test_coherent_forged_record_does_not_replace_independent_native_context(self):
        b,bodies,outputs=fixture();g=self.graph(b);changed=copy.deepcopy(outputs)
        changed['Completed_record']['runId']='SYNTHETIC-FORGED'
        self.assertFalse(self.evaluate(g['Completed_validate_record']['expression'],bodies,changed))
    def test_raw_bytes_metadata_and_current_case_drift_refuse(self):
        for name,key,value in [('Completed_commit_content','$content','Y2hhbmdlZA=='),('Completed_commit_after','ETag','changed')]:
            b,bodies,outputs=fixture();bodies[name][key]=value
            self.assertFalse(self.evaluate(self.graph(b)['Completed_validate_record']['expression'],bodies,outputs))
        for name,key,value in [('Completed_case_after','nextAction','human edit'),('Completed_date_after','ETag','changed'),('Completed_unique_field','EnforceUniqueValues',False),('Completed_date_field','TypeAsString','DateTime')]:
            b,bodies,outputs=fixture();bodies[name][key]=value
            self.assertFalse(self.evaluate(self.graph(b)['Completed_validate_current']['expression'],bodies,outputs))
    def test_unknown_or_multiple_source_profiles_do_not_qualify(self):
        for profiles in [[],[fixture()[0]['allowedSources'][0]]*2]:
            b,bodies,outputs=fixture();bodies['Completed_source_profiles']=profiles
            self.assertFalse(self.evaluate(self.graph(b)['Completed_validate_current']['expression'],bodies,outputs))
    def test_record_tokens_and_date_evidence_are_not_guessed(self):
        b,bodies,outputs=fixture();g=self.graph(b)
        outputs['Completed_date']={**outputs['Completed_date'],'reviewDate':'2099-02-01'}
        self.assertFalse(self.evaluate(g['Completed_validate_current']['expression'],bodies,outputs))
        b,bodies,outputs=fixture();outputs['Completed_case_after']['headers']['ETag']='*'
        self.assertFalse(self.evaluate(self.graph(b)['Completed_validate_current']['expression'],bodies,outputs))
    def test_incomplete_or_ambiguous_build_time_source_profiles_refuse(self):
        b, _, _ = fixture()
        invalid = [None, {}, [], [None], [dict(b['allowedSources'][0])] * 2]
        for key in ['DocumentUID', 'UniqueId', 'ETag', 'DocumentReference',
                    'ReviewedVersionRef', 'content', 'sha256']:
            profile = copy.deepcopy(b['allowedSources'][0])
            profile.pop(key)
            invalid.append([profile])
        for key, value in [('UniqueId', '000000000000000000000000000000000000'),
                           ('ETag', '*'), ('DocumentUID', 'REAL-SOURCE'),
                           ('DocumentReference', 'https://user:secret@example.invalid/source'),
                           ('DocumentReference', 'https://example.invalid/source?token=value'),
                           ('sha256', '0' * 64)]:
            profile = copy.deepcopy(b['allowedSources'][0])
            profile[key] = value
            invalid.append([profile])
        for profiles in invalid:
            changed = copy.deepcopy(b)
            changed['allowedSources'] = profiles
            with self.subTest(profiles=profiles), self.assertRaises(ValueError):
                self.graph(changed)

    def test_only_supported_sharepoint_gets_no_writer_or_fake_history_api(self):
        b,_,_=fixture();g=self.graph(b)
        for a in g.values():
            if a['type']=='OpenApiConnection':
                self.assertEqual(a['inputs']['parameters']['parameters/method'],'GET')
                self.assertEqual(a['inputs']['host']['operationId'],'HttpRequest')
                self.assertEqual(a['inputs']['retryPolicy'],{'type':'none'})
        audit=audit_actions({'actions':_reader_actions(b,'Trusted_context','SYNTHETIC-PRODUCER-FLOW')})
        self.assertLessEqual(audit['maximumActionDepth'],8)
        self.assertLess(max(len(a.get('expression','')) for a in g.values()),8192)


class CurrentClosureObserverTests(unittest.TestCase):
    def fixture(self):
        from test_prepared_closure_check import fixture as closure_fixture, SCOPE, DATE_UID
        context, binding, rows = closure_fixture(True)
        schema = context['properties']['definition']['triggers']['manual']['inputs']['schema']
        schema['properties'] = {'text_8': {'type': 'string', 'title': 'Next review evidence file identity'}}
        binding['dateEvidenceField'] = 'text_8'
        outputs = {'Test_trigger': {'text_8': DATE_UID},
                   'Selected_case_context': {'contextValid': True, 'CaseUID': SCOPE['CaseUID']},
                   'Native_prepared_revision': {'preparationQualified': True,
                       'originalSourceIsPreparedRevision': False, 'preparedRevision': {'scope': copy.deepcopy(SCOPE)}}}
        return context, binding, rows, outputs

    def select(self, rows=None, mutate=None, wrapper=None):
        context, binding, default_rows, outputs = self.fixture()
        if mutate: mutate(outputs)
        nodes = flatten(build_current_closure_observer(context, binding))
        ev = Expressions({'CurrentClosure_history': wrapper or {'value': default_rows if rows is None else rows}}, outputs)
        if not ev.evaluate(nodes['CurrentClosure_validate']['expression']): return nodes, ev, None
        for name in ['CurrentClosure_scoped'] + ['CurrentClosure_select_' + role for role in
                ('committee','officer','coordinator','authorisation','publication','implementation','verification')]:
            values = []
            for row in ev.evaluate(nodes[name]['inputs']['from']):
                ev.outputs['Current_item'] = row
                if ev.evaluate(nodes[name]['inputs']['where']): values.append(row)
            ev.bodies[name] = values
        if not ev.evaluate(nodes['CurrentClosure_unique']['expression']): return nodes, ev, None
        if not ev.evaluate(nodes['CurrentClosure_parents']['expression']): return nodes, ev, None
        payload = nodes['Current_closure_selection']['inputs']
        selection = {**payload, 'selectedEvents': {role: ev.evaluate(value) for role, value in payload['selectedEvents'].items()},
                     'nextReviewEvidenceFileUID': ev.evaluate(payload['nextReviewEvidenceFileUID'])}
        ev.outputs['Current_closure_selection'] = selection
        return nodes, ev, selection

    def chain(self, nodes, selection, rows, scope=None):
        from test_prepared_closure_check import Expressions as CanonicalExpressions, SCOPE
        ev = CanonicalExpressions({'Closure_assurance_before': {'value': rows},
            'Closure_Readiness_scope': [{'AssessedOn': '2026-10-18T14:00:00Z'}]}, {
            'Native_prepared_revision': {'preparedRevision': {'scope': scope or SCOPE}},
            'Closure_Native_readiness_observation': {'selectedEventUID': 'FICTIONAL-ready'},
            'Current_closure_selection': selection})
        for name, action in nodes['Closure_check_chain']['actions'].items():
            if name == 'Closure_assurance_before': continue
            if action['type'] in ('Select', 'Query'):
                result = []
                for row in ev.evaluate(action['inputs']['from']):
                    ev.current = row
                    if action['type'] == 'Select': result.append(ev.evaluate(action['inputs']['select']))
                    elif ev.evaluate(action['inputs']['where']): result.append(row)
                ev.bodies[name] = result
            elif action['type'] == 'Compose': ev.outputs[name] = ev.evaluate(action['inputs'])
            else: raise AssertionError(name)
            if name == 'Closure_chain_consistent': return ev.outputs[name]
        raise AssertionError('Missing canonical chain check')

    def test_selection_and_canonical_chain_follow_two_different_occurrences(self):
        _, _, rows, outputs = self.fixture()
        for case in ['LC-FICTIONAL-OP-NEW-A', 'LC-FICTIONAL-OP-NEW-B']:
            changed = [{**row, 'CaseUID': case} for row in rows]
            def change(out):
                out['Selected_case_context']['CaseUID'] = case
                out['Native_prepared_revision']['preparedRevision']['scope']['CaseUID'] = case
            nodes, ev, result = self.select(changed, change)
            self.assertIsNotNone(result)
            self.assertTrue(ev.evaluate(nodes['CurrentClosure_observe']['expression']))
            self.assertTrue(self.chain(nodes, result, changed,
                ev.outputs['Native_prepared_revision']['preparedRevision']['scope']))
            self.assertFalse(result['closurePerformed']); self.assertTrue(result['lookupKeysOnly'])

    def test_missing_duplicate_extra_parent_and_pagination_hold_before_observer(self):
        _, _, rows, _ = self.fixture()
        broken = copy.deepcopy(rows); broken[3]['ParentEventUID'] = 'OTHER'
        for changed in [rows[:-1], rows + [rows[0]], rows + [{**rows[0], 'EventUID': 'parallel-adverse'}], broken]:
            with self.subTest(rows=len(changed)):
                self.assertIsNone(self.select(changed)[2])
        for key in ['nextLink', 'odata.nextLink', '@odata.nextLink']:
            self.assertIsNone(self.select(wrapper={'value': rows, key: 'more'})[2])

    def test_unqualified_context_and_unsafe_date_locator_hold_before_history_read(self):
        changes = [lambda o: o['Selected_case_context'].update(contextValid=False),
                   lambda o: o['Selected_case_context'].update(CaseUID='OTHER'),
                   lambda o: o['Native_prepared_revision'].update(preparationQualified=False),
                   lambda o: o['Native_prepared_revision'].update(originalSourceIsPreparedRevision=True)]
        for change in changes: self.assertIsNone(self.select(mutate=change)[2])
        for value in ['', 'x', "00000000-0000-4000-8000-00000000009'", '../date',
                      'https://example.invalid/date', '0' * 36, '000000000000-4000-8000-000000000099']:
            self.assertIsNone(self.select(mutate=lambda o: o['Test_trigger'].update(text_8=value))[2], value)

    def test_selection_never_substitutes_for_canonical_adverse_and_cross_scope_checks(self):
        _, _, rows, _ = self.fixture()
        for index, changes in [(0, {'odata.etag': '*'}), (3, {'DecisionOutcome': 'Deferred'}),
                               (3, {'ConditionsState': 'Open'}), (6, {'VerificationResult': 'Failed'}),
                               (5, {'EvidenceReference': ''})]:
            changed = copy.deepcopy(rows); changed[index].update(changes)
            nodes, _, selection = self.select(changed)
            self.assertIsNotNone(selection)  # Locators are not evidence approval.
            self.assertFalse(self.chain(nodes, selection, changed))
        nodes, _, selection = self.select()
        self.assertFalse(self.chain(nodes, selection, rows + [{**rows[0], 'CaseUID': 'OTHER',
            'EventUID': 'cross-scope-correction', 'SupersedesEventUID': rows[0]['EventUID']}]))

    def test_date_key_is_revalidated_against_actual_file_tokens_and_exact_scope(self):
        from test_prepared_closure_check import Expressions as CanonicalExpressions, SCOPE, DATE_UID
        nodes, _, selection = self.select()
        record = {'FictionalTest': True, 'notOperational': True, 'policyAuthorityGranted': False,
                  'scope': copy.deepcopy(SCOPE), 'reviewDate': '2030-10-20',
                  'ruleReference': 'fictional://explicit-rule', 'evidenceReference': 'fictional://date', 'recordedBy': 'FICTIONAL recorder'}
        ev = CanonicalExpressions({'Closure_date_before': {'UniqueId': DATE_UID, 'ETag': '"1"'},
            'Closure_date_after': {'UniqueId': DATE_UID, 'ETag': '"1"'}}, {
            'Current_closure_selection': selection, 'Closure_date_record': record,
            'Native_prepared_revision': {'preparedRevision': {'scope': SCOPE}}})
        expression = nodes['Closure_date_consistent']['inputs']
        self.assertTrue(ev.evaluate(expression))
        for key in ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256'):
            altered = copy.deepcopy(record); altered['scope'][key] = 'OTHER'; ev.outputs['Closure_date_record'] = altered
            self.assertFalse(ev.evaluate(expression), key)
        ev.outputs['Closure_date_record'] = record
        ev.bodies['Closure_date_after']['ETag'] = '"2"'; self.assertFalse(ev.evaluate(expression))

    def test_observer_only_geometry_and_original_completed_route_are_preserved(self):
        context, binding, _, _ = self.fixture(); original = copy.deepcopy((context, binding))
        graph = build_current_closure_observer(context, binding)
        self.assertEqual((context, binding), original)
        for node in flatten(graph).values():
            if node['type'] == 'OpenApiConnection':
                self.assertEqual(node['inputs']['parameters']['parameters/method'], 'GET')
                self.assertNotIn('parameters/body', node['inputs']['parameters'])
        audit = audit_actions({'actions': graph})
        self.assertLessEqual(audit['maximumActionDepth'], 8)
        self.assertLessEqual(audit['actionCount'], 500)
        receipt = flatten(graph)['Native_closure_observation']['inputs']
        for key in ('closurePerformed', 'nextOccurrenceCreated', 'progressionGranted', 'actorAuthorityQualified'):
            self.assertIs(receipt[key], False)
        self.assertIn("outputs('Current_closure_selection')", flatten(graph)['Closure_selected_committee']['inputs']['where'])
        self.assertIn("outputs('Completed_candidate_record')?['contract']?['observation']",
                      flatten(build_runtime_closure_observer(context, binding))['Closure_selected_committee']['inputs']['where'])


if __name__=='__main__':unittest.main()
