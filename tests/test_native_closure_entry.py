"""Evaluate emitted binding guards with labelled synthetic native observations."""
import base64
import copy
import hashlib
import json
import unittest

from build_native_closure_entry import build_binding_reads, build_initial_transition, build_initial_entry, build_historical_frame, build_entry_with_history, FILES, HISTORIES, CONTENTS
from build_operator_entry import _flatten, action_references
from build_selected_event_routes import audit_actions
from test_native_completed_review import Expressions


def fixture(number=1):
    uid = lambda n: '00000000-0000-4000-8000-' + str(n).zfill(12)
    site = 'https://example.invalid/site'
    collection = "_api/web/lists(guid'" + uid(1) + "')/items"
    template = {'type': 'OpenApiConnection', 'runAfter': {}, 'inputs': {
        'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
                 'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
        'parameters': {'dataset': site, 'parameters/method': 'GET',
            'parameters/uri': "@concat('" + collection.replace("'", "''") + "(',string(outputs('Resolved_case_item_id')),')')"}}}
    nodes = {'Read_selected_case': template}
    for prefix in ('Preparation_', 'SelectedPreparation_'):
        nodes[prefix+'Verified_preparation_ownership'] = {'type':'Compose', 'runAfter':{}, 'inputs':{'ownershipProjectionVerified':True}}
        nodes[prefix+'Read_projection_commit_after'] = copy.deepcopy(template)
    nodes.pop('Read_selected_case')
    nodes['Resolve_context']={'type':'Scope','runAfter':{},'actions':{'Read_selected_case':template}}
    context = {'properties': {'definition': {'actions': nodes,
        'triggers':{'manual':{'inputs':{'schema':{'properties':{'text_7':{'type':'string'}}}}}}}}}
    binding = {'siteUrl': site, 'caseListUri': collection, 'proofFolder': '/site/evidence',
               'journalFolder':'/site/evidence','closureReferenceField':'text_7'}
    for index, kind in enumerate(HISTORIES, 2):
        binding[kind+'CollectionUri'] = "_api/web/lists(guid'" + uid(index) + "')/items"
    graph = build_binding_reads(context, binding); actions = _flatten(graph)
    file_uids = {kind: uid(20 + index + number*100) for index, kind in enumerate(FILES)}
    file_uids['draft'] = file_uids['source']
    source = site + '/draft-' + str(number) + '.docx'
    issued = site + '/evidence/issued-' + str(number) + '.docx'
    proof = site + '/evidence/proof-' + str(number) + '.json'
    raw = b'FICTIONAL full document bytes'
    scope = {'CaseUID':'LC-FICTIONAL-OP-CURRENT-'+str(number), 'DocumentReference':source,
             'ReviewedVersionRef':'prepared-v2', 'DocumentSHA256':hashlib.sha256(raw).hexdigest()}
    meta = {}
    for kind in FILES:
        row = {'UniqueId':file_uids[kind], 'ETag':'"'+kind+',1"', 'UIVersionLabel':'2.0', 'Length':str(len(raw))}
        if kind in ('source','draft'): row['ETag']='"prepared,2"'
        if kind in ('source','issued','proof','date'):
            row['ServerRelativeUrl'] = {'source':source, 'issued':issued, 'proof':proof,
                'date':site+'/evidence/date.json'}[kind].removeprefix('https://example.invalid')
        meta[kind] = row
    case = {'Id': number, 'GUID':uid(90+number), 'CaseUID':scope['CaseUID'],
            'caseStatus':'Ownership accepted — FICTIONAL', 'unknownHumanField':'Preserve this edit'}
    date = {'FictionalTest':True, 'scope':scope, 'reviewDate':'2099-01-01', 'ruleReference':'fictional://existing-rule'}
    bodies = {'ClosureEntry_case':case, 'ClosureEntry_case_after':copy.deepcopy(case),
              'ClosureEntry_proof_locator':copy.deepcopy(meta['proof']),
              'Closure_final_date':copy.deepcopy(meta['date']),
              'Closure_selected_publication':[{'EvidenceReference':proof,'PublicationURL':issued,'EventUID':'FICTIONAL-publication'}],
              'SelectedPreparation_Read_projection_commit_after':copy.deepcopy(meta['ownershipCommit'])}
    outputs = {'Selected_case_context':{'contextValid':True, 'CaseUID':scope['CaseUID'], 'nativeItemId':number,
        'caseETag':'"case,3"', 'sourcePins':meta['originalSource'],
        'baselineUniqueId':file_uids['sourceBaseline'], 'baselineETag':meta['sourceBaseline']['ETag']},
        'Native_prepared_revision':{'preparationQualified':True, 'originalSourceIsPreparedRevision':False,
            'currentCaseETag':'"case,3"', 'preparedRevision':{'scope':scope,
                'file':{'UniqueId':file_uids['source'],'ETag':meta['source']['ETag'],'nativeVersion':'2.0','Length':len(raw)},
                'template':meta['template'],'qualificationReceipt':meta['generationReceipt']}},
        'Native_closure_observation':{'closureEvidenceConsistent':True,'nextReviewDateProvenanceConsistent':True,
            'nextOccurrencePrerequisitesConsistent':True,'closurePerformed':False,'nextOccurrenceCreated':False,
            'actorAuthorityQualified':False,'realPolicyEffects':False,'progressionGranted':False,'writeCount':0,'issuedFile':meta['issued'],
            'nextReviewEvidenceFileUID':file_uids['date'],'preparedScope':scope,
            'selectedEvents':{role:'FICTIONAL-'+role for role in ('committee','officer','coordinator','authorisation','publication','implementation','verification')},
            'nextReviewDate':date['reviewDate'],'nextReviewRuleReference':date['ruleReference']},
        'Action_Preparation_Verified_preparation_ownership':{'status':'Skipped'},
        'Action_SelectedPreparation_Verified_preparation_ownership':{'status':'Succeeded'},
        'ClosureEntry_case':{'headers':{'ETag':'"case,3"'}},
        'ClosureEntry_case_after':{'headers':{'ETag':'"case,3"'}},'Closure_date_record':date}
    for kind in HISTORIES:
        history = {'value':[{'Id':1,'CaseUID':scope['CaseUID'],'odata.etag':'"1"','unknownFinding':'Keep'}], 'unknownWrapper':None}
        bodies['ClosureEntry_read_'+kind] = history
        bodies['ClosureEntry_check_'+kind] = copy.deepcopy(history)
    for kind in FILES:
        bodies['ClosureEntry_read_'+kind] = copy.deepcopy(meta[kind])
        bodies['ClosureEntry_check_'+kind] = copy.deepcopy(meta[kind])
    for kind in CONTENTS:
        content = json.dumps(date).encode() if kind=='dateContent' else raw
        bodies['ClosureEntry_read_'+kind] = {'$content':base64.b64encode(content).decode()}
    return context, binding, actions, Expressions(bodies, outputs)


def value(expression, ev):
    if isinstance(expression, dict): return {k:value(v,ev) for k,v in expression.items()}
    if isinstance(expression, list): return [value(v,ev) for v in expression]
    # Native action outputs are retained JSON values, not mutable Python aliases.
    return copy.deepcopy(ev.evaluate(expression)) if isinstance(expression,str) and expression.startswith('@') else expression


def collect(actions, ev):
    for name in ('ClosureEntry_initial',):
        if not ev.evaluate(actions[name]['expression']): return False
    ev.outputs['ClosureEntry_ownership_metadata'] = value(actions['ClosureEntry_ownership_metadata']['inputs'], ev)
    for name in ('ClosureEntry_case_verified','ClosureEntry_proof_path'):
        if not ev.evaluate(actions[name]['expression']): return False
    for kind in FILES:
        name = 'ClosureEntry_key_'+kind; ev.outputs[name] = value(actions[name]['inputs'],ev)
    if not ev.evaluate(actions['ClosureEntry_file_keys']['expression']): return False
    for kind in HISTORIES:
        for prefix in ('read','check'):
            name = 'ClosureEntry_'+prefix+'_'+kind+'_stable'; rows=[]
            for row in ev.evaluate(actions[name]['inputs']['from']):
                ev.outputs['Current_item']=row; rows.append(ev.evaluate(actions[name]['inputs']['select']))
            ev.bodies[name]=rows
    ev.outputs['ClosureEntry_snapshot']=value(actions['ClosureEntry_snapshot']['inputs'],ev)
    for name, action in actions.items():
        if name.startswith('ClosureEntry_frame_') and name!='ClosureEntry_frame_valid':
            ev.outputs[name]=value(action['inputs'],ev)
    return ev.evaluate(actions['ClosureEntry_frame_valid']['expression'])


class NativeClosureBindingTests(unittest.TestCase):
    def test_two_runtime_occurrences_resolve_all_sixteen_reads_without_case_enrollment(self):
        for number in (1,27):
            _,_,actions,ev=fixture(number); self.assertTrue(collect(actions,ev))
            result=value(actions['ClosureEntry_binding_result']['inputs'],ev)
            self.assertEqual(set(result['evidence']),set(HISTORIES)|set(FILES)|set(CONTENTS))
            self.assertEqual(result['case']['Id'],number); self.assertFalse(result['closureWriteReady'])
            self.assertEqual(result['case']['unknownHumanField'],'Preserve this edit')
            self.assertIn('('+str(number)+')',result['caseItemUri'])
            for kind,spec in result['evidenceReads'].items():
                self.assertEqual(spec['collection'],kind in HISTORIES)
                if kind not in HISTORIES:self.assertIn("GetFileById('",spec['uri'])

    def test_every_file_binding_refuses_changed_identity_or_opaque_token(self):
        for kind in FILES:
            for key in ('UniqueId','ETag'):
                _,_,actions,ev=fixture()
                for prefix in ('read','check'):ev.bodies['ClosureEntry_'+prefix+'_'+kind][key]='00000000-0000-4000-8000-000000009999' if key=='UniqueId' else '"different"'
                self.assertFalse(collect(actions,ev),(kind,key))

    def test_case_token_unknown_human_edit_and_full_history_wrapper_changes_hold(self):
        for kind in ('caseToken','human','historyRow','wrapper','pagination'):
            _,_,actions,ev=fixture()
            if kind=='caseToken':ev.outputs['ClosureEntry_case_after']['headers']['ETag']='"case,4"'
            elif kind=='human':ev.bodies['ClosureEntry_case_after']['unknownHumanField']='Overwritten'
            elif kind=='historyRow':ev.bodies['ClosureEntry_check_assurance']['value'][0]['unknownFinding']='Changed'
            elif kind=='wrapper':ev.bodies['ClosureEntry_check_readiness']['unknownWrapper']='Changed'
            else:ev.bodies['ClosureEntry_read_consultation']['nextLink']='more'
            self.assertFalse(collect(actions,ev),kind)

    def test_matching_hash_assertions_do_not_hide_binary_or_date_change(self):
        for kind in ('sourceBytes','issuedBytes','bothTruncated','date','sourceVersion','sourceLength'):
            _,_,actions,ev=fixture()
            if kind in ('sourceBytes','issuedBytes'):
                key='sourceContent' if kind=='sourceBytes' else 'issuedContent'
                ev.bodies['ClosureEntry_read_'+key]['$content']=base64.b64encode(b'other bytes').decode()
            elif kind=='bothTruncated':
                for key in ('sourceContent','issuedContent'):
                    ev.bodies['ClosureEntry_read_'+key]['$content']=base64.b64encode(b'truncated').decode()
            elif kind=='date':
                row={**ev.outputs['Closure_date_record'],'reviewDate':'2099-02-01'}
                ev.bodies['ClosureEntry_read_dateContent']['$content']=base64.b64encode(json.dumps(row).encode()).decode()
            else:
                key='UIVersionLabel' if kind=='sourceVersion' else 'Length'
                for prefix in ('read','check'):ev.bodies['ClosureEntry_'+prefix+'_source'][key]='3'
            self.assertFalse(collect(actions,ev),kind)

    def test_complete_binary_length_check_handles_all_base64_padding_cases(self):
        for raw in (b'a',b'ab',b'abc',b'abcd'):
            _,_,actions,ev=fixture()
            ev.outputs['Native_prepared_revision']['preparedRevision']['file']['Length']=len(raw)
            for kind in ('source','draft','issued'):
                for prefix in ('read','check'):ev.bodies['ClosureEntry_'+prefix+'_'+kind]['Length']=str(len(raw))
            for kind in ('sourceContent','issuedContent'):
                ev.bodies['ClosureEntry_read_'+kind]['$content']=base64.b64encode(raw).decode()
            self.assertTrue(collect(actions,ev),len(raw))

    def test_unqualified_or_ambiguous_ownership_and_unsafe_proof_path_hold(self):
        for change in ('bothOwnership','missingOwnership','prepared','authority','unsafeProof','foreignProof','closedCase'):
            _,_,actions,ev=fixture()
            if change=='bothOwnership':ev.outputs['Action_Preparation_Verified_preparation_ownership']['status']='Succeeded'
            elif change=='missingOwnership':ev.outputs['Action_SelectedPreparation_Verified_preparation_ownership']['status']='Skipped'
            elif change=='prepared':ev.outputs['Native_prepared_revision']['preparationQualified']=False
            elif change=='authority':ev.outputs['Native_closure_observation']['actorAuthorityQualified']=True
            elif change=='closedCase':ev.bodies['ClosureEntry_case']['caseStatus']='Review closed — FICTIONAL'
            else:ev.bodies['Closure_selected_publication'][0]['EvidenceReference']='https://other.invalid/proof.json' if change=='foreignProof' else "https://example.invalid/site/evidence/../proof.json"
            self.assertFalse(collect(actions,ev),change)

    def test_qualified_observer_for_other_scope_event_date_or_rule_does_not_bind(self):
        for key in ('preparedScope','publication','date','rule'):
            _,_,actions,ev=fixture()
            if key=='preparedScope':ev.outputs['Native_closure_observation']['preparedScope']={**ev.outputs['Native_closure_observation']['preparedScope'],'CaseUID':'OTHER'}
            elif key=='publication':ev.outputs['Native_closure_observation']['selectedEvents']['publication']='OTHER'
            elif key=='date':ev.outputs['Native_closure_observation']['nextReviewDate']='2099-02-01'
            else:ev.outputs['Native_closure_observation']['nextReviewRuleReference']='fictional://OTHER'
            self.assertFalse(collect(actions,ev),key)

    def test_get_only_geometry_dependencies_and_wrong_target_refusal(self):
        context,binding,_,_=fixture();original=copy.deepcopy((context,binding));graph=build_binding_reads(context,binding)
        self.assertEqual((context,binding),original)
        for action in _flatten(graph).values():
            if action['type']=='OpenApiConnection':
                self.assertEqual(action['inputs']['parameters']['parameters/method'],'GET')
                self.assertNotIn('parameters/body',action['inputs']['parameters'])
        audit=audit_actions({'actions':graph});self.assertLessEqual(audit['maximumActionDepth'],8);self.assertLessEqual(audit['actionCount'],500)
        external = action_references(graph)-_flatten(graph).keys()
        self.assertEqual(external, {'Selected_case_context','Native_prepared_revision','Native_closure_observation',
            'Closure_selected_publication','Closure_final_date','Closure_date_record',
            'Preparation_Verified_preparation_ownership','Preparation_Read_projection_commit_after',
            'SelectedPreparation_Verified_preparation_ownership','SelectedPreparation_Read_projection_commit_after'})
        self.assertNotIn('triggerBody(',json.dumps(graph))
        for key in ('siteUrl','caseListUri','proofFolder'):
            changed=copy.deepcopy(binding);changed[key]='https://other.invalid'
            with self.subTest(key=key),self.assertRaises(ValueError):build_binding_reads(context,changed)


def runtime_writer(number=1):
    context,binding,collector,ev=fixture(number)
    assert collect(collector,ev)
    ev.outputs['ClosureEntry_binding_result']=value(collector['ClosureEntry_binding_result']['inputs'],ev)
    ev.outputs['Test_trigger']={'text_7':'LC04-CLOSE-RUNTIME-'+str(number)}
    graph=build_initial_transition(context,binding);nodes=_flatten(graph)
    contract=value(nodes['ClosureEntry_write_contract']['inputs'],ev)
    ev.outputs['ClosureEntry_write_contract']=contract;ev.outputs['Cycle_contract']=contract
    ev.outputs['Cycle_expected_evidence']=ev.outputs['ClosureEntry_binding_result']['evidence']
    return context,binding,graph,nodes,ev


class NativeClosureInitialWriterTests(unittest.TestCase):
    def test_runtime_contract_and_all_read_uris_follow_two_different_cases(self):
        for number in (1,27):
            _,_,graph,nodes,ev=runtime_writer(number)
            self.assertTrue(ev.evaluate(nodes['ClosureEntry_validate_write']['expression']))
            contract=ev.outputs['Cycle_contract'];self.assertEqual(contract['CaseUID'],'LC-FICTIONAL-OP-CURRENT-'+str(number))
            self.assertEqual(contract['initialCaseETag'],'"case,3"');self.assertEqual(contract['patch'],{'caseStatus':'Review closed — FICTIONAL'})
            self.assertEqual(contract['requestReference'],'LC04-CLOSE-RUNTIME-'+str(number))
            for prefix in ('Cycle_current','Cycle_prewrite','Cycle_after'):
                for kind in HISTORIES+FILES+tuple(CONTENTS):
                    self.assertEqual(ev.evaluate(nodes[prefix+'_'+kind]['inputs']['parameters']['parameters/uri']),contract['evidenceReads'][kind]['uri'])
            for name in ('Cycle_case','Cycle_case_prewrite','Cycle_case_after','Cycle_apply_closure'):
                self.assertEqual(ev.evaluate(nodes[name]['inputs']['parameters']['parameters/uri']),contract['caseItemUri'])
            self.assertNotIn('COMPILER_CLOSURE_ONLY',json.dumps(graph));self.assertNotIn('ffffffff-ffff-4fff-8fff-',json.dumps(graph))

    def test_unsafe_request_or_missing_collector_is_refused_before_canonical_reads(self):
        _,_,_,nodes,ev=runtime_writer()
        for ref in ['', 'LC04-', 'LC04-../escape', "LC04-'quote", 'LC04-/path', 'LC04-%41', 'LC04-Ā', 'LC04-!x', 'LC04-'+'A'*80]:
            ev.outputs['Test_trigger']['text_7']=ref
            self.assertFalse(ev.evaluate(nodes['ClosureEntry_validate_write']['expression']),ref)
        ev.outputs['Test_trigger']['text_7']='LC04-CLOSE-OK'
        ev.outputs['ClosureEntry_binding_result']['bindingsCollected']=False
        self.assertFalse(ev.evaluate(nodes['ClosureEntry_validate_write']['expression']))
        self.assertEqual(nodes['Cycle_contract']['runAfter'],{'ClosureEntry_validate_write':['Succeeded']})
        self.assertEqual(nodes['ClosureEntry_refuse_write']['type'],'Terminate')

    def test_canonical_initial_gate_preserves_exact_observation_and_opaque_token(self):
        _,_,_,nodes,ev=runtime_writer()
        ev.bodies.update(Cycle_find_before={'value':[]},Cycle_find_after={'value':[]})
        ev.outputs['Cycle_case']={'headers':{'ETag':'"case,3"'}}
        ev.bodies['Cycle_case']=copy.deepcopy(ev.outputs['ClosureEntry_binding_result']['case'])
        self.assertTrue(ev.evaluate(nodes['Cycle_validate_initial']['expression']))
        for key,new in [('closureEvidenceConsistent',False),('nextReviewDate','2099-02-01'),('nextReviewRuleReference','fictional://OTHER'),('actorAuthorityQualified',True)]:
            altered=copy.deepcopy(ev.outputs);altered['Native_closure_observation'][key]=new
            self.assertFalse(Expressions(ev.bodies,altered).evaluate(nodes['Cycle_validate_initial']['expression']),key)
        altered=copy.deepcopy(ev.outputs);altered['Cycle_case']['headers']['ETag']='"case,4"'
        self.assertFalse(Expressions(ev.bodies,altered).evaluate(nodes['Cycle_validate_initial']['expression']))

    def test_canonical_journals_are_create_only_and_merge_preserves_compare_and_swap(self):
        _,_,_,nodes,ev=runtime_writer()
        writers={k:a for k,a in nodes.items() if a['type']=='OpenApiConnection' and a['inputs']['parameters']['parameters/method']!='GET'}
        self.assertEqual(len(writers),5)  # before, MERGE, after, first/recovery commit
        for name,action in writers.items():
            self.assertEqual(action['inputs']['retryPolicy'],{'type':'none'})
            params=action['inputs']['parameters'];uri=ev.evaluate(params['parameters/uri'])
            if name=='Cycle_apply_closure':
                self.assertEqual(uri,ev.outputs['Cycle_contract']['caseItemUri'])
                self.assertEqual(params['parameters/headers']['IF-MATCH'],"@outputs('Cycle_case_prewrite')?['headers']?['ETag']")
            else:
                self.assertIn('overwrite=false',uri);self.assertIn('LC04-CLOSE-RUNTIME-1',uri)

    def test_prewrite_and_after_guards_keep_human_edits_and_full_wrappers_significant(self):
        _,_,_,nodes,ev=runtime_writer()
        row=ev.outputs['ClosureEntry_binding_result']['case'];snap=ev.outputs['Cycle_expected_evidence']
        ev.outputs.update(Cycle_first_stored_before={'durable':True},Cycle_before_payload={'durable':True},
            Cycle_prewrite_complete=True,Cycle_prewrite_snapshot=snap,Cycle_current_snapshot=snap,
            Cycle_case={'headers':{'ETag':'"case,3"'}},Cycle_case_prewrite={'headers':{'ETag':'"case,3"'}})
        ev.bodies.update(Cycle_case=row,Cycle_case_prewrite=copy.deepcopy(row))
        for kind in HISTORIES:
            ev.bodies['Cycle_prewrite_'+kind]=copy.deepcopy(ev.bodies['ClosureEntry_check_'+kind])
            ev.bodies['Cycle_prewrite_'+kind+'_stable']=copy.deepcopy(ev.bodies['ClosureEntry_check_'+kind+'_stable'])
        expression=nodes['Cycle_verify_prewrite']['expression'];self.assertTrue(ev.evaluate(expression))
        edited=copy.deepcopy(ev.bodies);edited['Cycle_case_prewrite']['unknownHumanField']='lost'
        self.assertFalse(Expressions(edited,ev.outputs).evaluate(expression))
        changed=copy.deepcopy(ev.bodies);changed['Cycle_prewrite_assurance']['unknownWrapper']='changed'
        self.assertFalse(Expressions(changed,ev.outputs).evaluate(expression))
        changed=copy.deepcopy(ev.outputs);changed['Cycle_case_prewrite']['headers']['ETag']='"case,4"'
        self.assertFalse(Expressions(ev.bodies,changed).evaluate(expression))

    def test_local_geometry_and_canonical_replay_guards_are_retained_without_claiming_entry(self):
        context,binding,graph,nodes,ev=runtime_writer()
        self.assertIn('Cycle_verify_replay',nodes);self.assertIn('Cycle_verify_recovery',nodes)
        self.assertIn('Cycle_hold_partial',nodes)
        self.assertFalse(any(a['type']=='OpenApiConnection' for a in _flatten(nodes['Cycle_verify_replay']['actions']).values()))
        combined={**build_binding_reads(context,binding),**graph}
        audit=audit_actions({'actions':combined});self.assertLessEqual(audit['maximumActionDepth'],8)
        self.assertLessEqual(audit['actionCount'],500)
        # Already-closed entry is still an explicit gap: the current collector
        # refuses it instead of relabelling the original initial contract.
        _,_,collector,closed=fixture();closed.bodies['ClosureEntry_case']['caseStatus']='Review closed — FICTIONAL'
        self.assertFalse(collect(collector,closed))

    def replay_frame(self):
        _,_,_,nodes,ev=runtime_writer()
        contract=copy.deepcopy(ev.outputs['Cycle_contract']);snap=copy.deepcopy(ev.outputs['Cycle_expected_evidence'])
        initial={**ev.outputs['ClosureEntry_binding_result']['case'],'odata.id':None}
        closed={**initial,'caseStatus':'Review closed — FICTIONAL'}
        before={'kind':'fictional-prepared-closure-before-v1','contract':copy.deepcopy(contract),
            'beforeCase':initial,'beforeCaseETag':contract['initialCaseETag'],'evidence':copy.deepcopy(snap),'runId':'ORIGIN-A'}
        after={'kind':'fictional-prepared-closure-after-v1','contract':copy.deepcopy(contract),
            'afterCase':closed,'afterCaseETag':'"case,4"','evidence':copy.deepcopy(snap),'runId':'ORIGIN-A'}
        commit={'kind':'fictional-prepared-closure-commit-v1','contract':copy.deepcopy(contract),
                'beforeProof':copy.deepcopy(before),'afterProof':copy.deepcopy(after)}
        ev.outputs.update(Cycle_replay_before=before,Cycle_replay_after=after,Cycle_commit_record=commit,
            Cycle_before_record=copy.deepcopy(before),Cycle_after_record=copy.deepcopy(after),
            Cycle_case={'headers':{'ETag':'"case,4"'}},Cycle_current_complete=True,Cycle_current_snapshot=snap)
        ev.bodies['Cycle_case']=closed
        for kind in ('before','after','commit'):ev.bodies['Cycle_find_'+kind]={'value':[{}]}
        for kind in HISTORIES:
            ev.bodies['Cycle_current_'+kind]=copy.deepcopy(ev.bodies['ClosureEntry_check_'+kind])
            ev.bodies['Cycle_current_'+kind+'_stable']=copy.deepcopy(ev.bodies['ClosureEntry_check_'+kind+'_stable'])
        return nodes,ev

    def test_preserved_canonical_replay_matches_original_contract_and_current_full_frame(self):
        nodes,ev=self.replay_frame()
        self.assertTrue(ev.evaluate(nodes['Cycle_reads_valid']['inputs']))
        self.assertTrue(ev.evaluate(nodes['Cycle_verify_replay']['expression']))
        for key in ('request','initialToken','human','proofKind','wrapper'):
            outputs,bodies=copy.deepcopy(ev.outputs),copy.deepcopy(ev.bodies)
            if key=='request':outputs['Cycle_contract']['requestReference']='LC04-OTHER'
            elif key=='initialToken':outputs['Cycle_contract']['initialCaseETag']='"case,4"'
            elif key=='human':bodies['Cycle_case']['unknownHumanField']='Changed after closure'
            elif key=='proofKind':outputs['Cycle_replay_before']['kind']='untrusted-proof'
            else:bodies['Cycle_current_assurance']['unknownWrapper']='changed'
            guard='Cycle_reads_valid' if key=='wrapper' else 'Cycle_verify_replay'
            field='inputs' if key=='wrapper' else 'expression'
            self.assertFalse(Expressions(bodies,outputs).evaluate(nodes[guard][field]),key)

    def test_preserved_recovery_never_repeats_merge_and_partial_journal_holds(self):
        nodes,ev=self.replay_frame();ev.bodies['Cycle_find_commit']={'value':[]}
        self.assertTrue(ev.evaluate(nodes['Cycle_verify_recovery']['expression']))
        recovery=_flatten(nodes['Cycle_verify_recovery']['actions'])
        self.assertNotIn('Cycle_apply_closure',recovery)
        for change in ('token','human'):
            altered=copy.deepcopy(ev.outputs)
            if change=='token':altered['Cycle_after_record']['afterCaseETag']='"case,5"'
            else:altered['Cycle_before_record']['beforeCase']['unknownHumanField']='lost'
            self.assertFalse(Expressions(ev.bodies,altered).evaluate(nodes['Cycle_verify_recovery']['expression']))
        ev.outputs['Cycle_reads_valid']=True;ev.bodies['Cycle_find_after']={'value':[]}
        self.assertTrue(ev.evaluate(nodes['Cycle_hold_partial']['expression']))
        self.assertFalse(ev.evaluate(nodes['Cycle_choose_initial']['expression']))

    def test_separate_candidate_preserves_preparation_and_existing_source_resource(self):
        context,binding,_,_=fixture();source=context['properties']['definition']
        context['properties'].update(state='Stopped',connectionReferences={'shared_sharepointonline':{'connectionName':'fictional-existing'}})
        fields={'text':{'type':'string','title':'Operation'},'text_6':{'type':'string','title':'Case reference'}}
        source['triggers']['manual'].update(kind='Button',type='Request',inputs={'schema':{'properties':fields,'required':['text','text_6']}})
        prep_nodes={k:source['actions'].pop(k) for k in list(source['actions']) if k!='Resolve_context'}
        prep_nodes['Native_prepared_revision']={'type':'Compose','runAfter':{},'inputs':{'preparationQualified':False}}
        source['actions']['Resolve_context']['actions']['Selected_case_context']={'type':'Compose','runAfter':{},'inputs':{'contextValid':False}}
        source['actions']['Resolve_context']['actions']['Resolved_case_item_id']={'type':'Compose','runAfter':{},'inputs':1}
        source['actions']['Route_preparation_check']={'type':'If','expression':'@false','runAfter':{'Resolve_context':['Succeeded']},'actions':prep_nodes,'else':{'actions':{}}}
        binding.update(dateEvidenceField='text_8',purposeReferences={role:'fictional://purpose/'+role for role in ('committee','officer','coordinator','authorisation')},requiredFictionalRoles=['FICTIONAL role'])
        original=copy.deepcopy(context);out=build_initial_entry(context,binding)
        operation=out['properties']['definition']['actions']['Validate_closure_operation']
        self.assertEqual(operation['expression'],"@equals(triggerBody()?['text'],'Close review')")
        self.assertEqual(operation['actions'],{})
        self.assertEqual(operation['else']['actions']['Closure_operation_refused']['inputs']['runStatus'],'Failed')
        self.assertEqual(out['properties']['definition']['actions']['Resolve_context']['runAfter'],
                         {'Validate_closure_operation':['Succeeded']})
        self.assertEqual(context,original);self.assertEqual(out['properties']['state'],'Stopped')
        self.assertEqual(out['properties']['connectionReferences'],context['properties']['connectionReferences'])
        actions=out['properties']['definition']['actions']
        self.assertEqual(actions['Route_preparation_check']['actions'],prep_nodes)
        self.assertEqual(actions['ClosureEntry_initial']['runAfter'],{'CurrentClosure_observe':['Succeeded']})
        self.assertEqual(set(out['properties']['definition']['triggers']['manual']['inputs']['schema']['required']),{'text','text_6','text_7','text_8'})
        self.assertFalse(action_references(actions)-_flatten(actions).keys())
        audit=audit_actions(out['properties']['definition']);self.assertLessEqual(audit['actionCount'],500);self.assertLessEqual(audit['maximumActionDepth'],8)

        binding['runtimeClosureTraceVersion']=1
        binding.update(artifactFolderRelative='/site/evidence',caseEvidenceFieldType='Note',
                       templateFileUniqueId='00000000-0000-4000-8000-000000000001')
        resolver=source['actions']['Resolve_context']['actions']
        resolver['Parse_baseline']={'type':'Compose','runAfter':{},'inputs':{}}
        resolver['Verify_baseline_boundary']={'type':'Scope','runAfter':{},'actions':{
            'Read_baseline_before':copy.deepcopy(resolver['Read_selected_case']),
            'Verify_request':{'type':'Scope','runAfter':{},'actions':{
                'Read_source_before':copy.deepcopy(resolver['Read_selected_case'])}}}}
        original=copy.deepcopy(context)
        complete=build_entry_with_history(context,binding)
        self.assertEqual(context,original)
        complete_actions=complete['properties']['definition']['actions']
        self.assertEqual(complete_actions['Resolve_context']['actions'],source['actions']['Resolve_context']['actions'])
        self.assertEqual(complete['properties']['connectionReferences'],out['properties']['connectionReferences'])
        self.assertEqual(complete_actions['CurrentClosure_validate']['runAfter'],{'Native_prepared_revision':['Succeeded']})
        self.assertEqual(complete_actions['Native_prepared_revision']['runAfter'],{
            'Route_preparation_check':['Succeeded'],'ClosureHistory_preparation':['Succeeded']})
        self.assertFalse(action_references(complete_actions)-_flatten(complete_actions).keys())
        self.assertEqual(complete_actions['ClosureHistory_entry']['else'],{'actions':{}})
        audit=audit_actions(complete['properties']['definition'])
        self.assertLessEqual(audit['actionCount'],500);self.assertLessEqual(audit['maximumActionDepth'],8)
        oversized=copy.deepcopy(context)
        oversized['properties']['definition']['actions']['Resolve_context']['actions']['Selected_case_context']['inputs']={'retained':"@concat('"+'x'*8193+"')"}
        with self.assertRaises(ValueError):build_entry_with_history(oversized,binding)
        expanded=copy.deepcopy(context)
        resolver=expanded['properties']['definition']['actions']['Resolve_context']['actions']
        for index in range(501):
            resolver['Retained_source_growth_'+str(index)]={'type':'Compose','runAfter':{},'inputs':False}
        for builder in (build_initial_entry,build_entry_with_history):
            with self.subTest(builder=builder.__name__):
                with self.assertRaisesRegex(ValueError,'exceeds 500 actions'):
                    builder(expanded,binding)

    def test_versioned_commit_trace_preserves_actual_origin_and_committer(self):
        _,_,_,nodes,ev=runtime_writer()
        before={'runId':'ORIGIN-A'};after={'runId':'ORIGIN-A'}
        for prefix,actor in [('First_','ORIGIN-A'),('Recovery_','RECOVERY-B')]:
            ev.outputs.update(Test_workflow={'run':{'name':actor}},Cycle_first_stored_before=before,Cycle_before_record=before,
                Cycle_first_stored_after=after,Cycle_after_record=after)
            payload=value(nodes[prefix+'Cycle_commit_payload']['inputs'],ev)
            self.assertEqual(payload['runId'],actor);self.assertEqual(payload['originRunId'],'ORIGIN-A')
            self.assertEqual(payload['committedByRun'],actor);self.assertEqual(payload['runtimeTraceVersion'],1)


def historical_fixture(committed=True):
    context,binding,_,_,source=runtime_writer()
    context['properties']['definition']['triggers']['manual']['inputs']['schema']['properties']['text_8']={'type':'string'}
    binding.update(dateEvidenceField='text_8',runtimeClosureTraceVersion=1)
    graph=build_historical_frame(context,binding);nodes=_flatten(graph)
    original=copy.deepcopy(source.outputs['Cycle_contract']);scope=original['observation']['preparedScope']
    original['retainedHumanNote']={'odata.id':'business data must survive'}
    initial={**source.outputs['ClosureEntry_binding_result']['case'],'evidenceDraftLink':scope['DocumentReference'],
        'sourceBaselineRef':'https://example.invalid/site/evidence/request.json','accountableRole':'FICTIONAL role','nextAction':'Preserve current human instruction','odata.id':None}
    closed={**initial,'caseStatus':'Review closed — FICTIONAL'};snap=copy.deepcopy(source.outputs['Cycle_expected_evidence'])
    before={'kind':'fictional-prepared-closure-before-v1','contract':copy.deepcopy(original),'beforeCase':initial,
        'beforeCaseETag':original['initialCaseETag'],'evidence':copy.deepcopy(snap),'runId':'ORIGIN-A'}
    after={'kind':'fictional-prepared-closure-after-v1','contract':copy.deepcopy(original),'afterCase':closed,
        'afterCaseETag':'"case,4"','evidence':copy.deepcopy(snap),'runId':'ORIGIN-A'}
    commit={'kind':'fictional-prepared-closure-commit-v1','contract':copy.deepcopy(original),'beforeProof':copy.deepcopy(before),
        'afterProof':copy.deepcopy(after),'runId':'RECOVERY-B','originRunId':'ORIGIN-A','committedByRun':'RECOVERY-B','runtimeTraceVersion':1}
    selected=copy.deepcopy(source.outputs['Selected_case_context']);selected.update(caseETag='"case,4"',
        baselineReference=initial['sourceBaselineRef'],scope={**scope,'DocumentReference':'https://example.invalid/site/original.txt','ReviewedVersionRef':'source-v1'})
    owner={'kind':'fictional-ownership-projection-commit-v1','CaseUID':initial['CaseUID'],'afterCase':copy.deepcopy(initial),
        'context':{key:copy.deepcopy(selected[key]) for key in ('baselineReference','baselineUniqueId','baselineETag','scope')}}
    outputs={'Test_trigger':{'text_7':original['requestReference'],'text_8':original['observation']['nextReviewEvidenceFileUID']},
        'Selected_case_context':selected,'ClosureHistory_before_record':before,'ClosureHistory_after_record':after,
        'ClosureHistory_owner_record':owner,'ClosureHistory_current_case':{'headers':{'ETag':'"case,4"'}}}
    if committed:outputs['ClosureHistory_commit_record']=commit
    bodies={'Read_selected_case':closed,'ClosureHistory_current_case':closed,
        'ClosureHistory_owner_before':snap['ownershipCommit'],'ClosureHistory_owner_after':copy.deepcopy(snap['ownershipCommit'])}
    for index,(kind,record) in enumerate([('before',before),('after',after),('commit',commit)]):
        name='LC04-closure-'+original['requestReference']+'-'+kind+'.json'
        meta={'UniqueId':'00000000-0000-4000-8000-'+str(900+index).zfill(12),'ETag':'"journal-'+kind+',1"','UIVersionLabel':'1.0',
              'Length':str(len(json.dumps(record).encode())),'Name':name}
        bodies['ClosureHistory_find_'+kind]={'value':[meta] if kind!='commit' or committed else []}
        if kind!='commit' or committed:
            bodies['ClosureHistory_'+kind+'_before']=meta;bodies['ClosureHistory_'+kind+'_after']=copy.deepcopy(meta)
    return context,binding,graph,nodes,Expressions(bodies,outputs)


def history_check(nodes,ev):
    if not ev.evaluate(nodes['ClosureHistory_entry']['expression']):return False
    for kind in ('before','after','commit'):
        name='ClosureHistory_key_'+kind;ev.outputs[name]=value(nodes[name]['inputs'],ev)
    if not ev.evaluate(nodes['ClosureHistory_pair']['expression']):return False
    if not ev.evaluate(nodes['ClosureHistory_owner_key']['expression']):return False
    for name,node in nodes.items():
        if name.startswith('ClosureHistory_check_'):ev.outputs[name]=value(node['inputs'],ev)
    return ev.evaluate(nodes['ClosureHistory_verified']['expression'])


class NativeClosureHistoricalFrameTests(unittest.TestCase):
    def test_separate_before_after_and_current_case_select_replay_or_recovery_without_rebasing(self):
        for committed in (True,False):
            _,_,_,nodes,ev=historical_fixture(committed);self.assertTrue(history_check(nodes,ev))
            frame=value(nodes['ClosureHistory_frame']['inputs'],ev)
            self.assertEqual(frame['originalContract']['initialCaseETag'],'"case,3"')
            self.assertEqual(frame['currentCaseETag'],'"case,4"')
            self.assertEqual(frame['mode'],'committed-replay' if committed else 'after-proof-recovery')
            self.assertFalse(frame['closurePerformed']);self.assertTrue(frame['freshEvidenceRevalidationRequired'])
            self.assertEqual(frame['commit'] is None,not committed)

    def test_missing_after_commit_metadata_ambiguity_or_changed_request_are_not_successful_replay(self):
        for change in ('missingBefore','missingAfter','duplicateCommit','pagination','changedRequest','foreignCase','foreignSource','changedOwner'):
            _,_,_,nodes,ev=historical_fixture()
            if change=='missingBefore':ev.bodies['ClosureHistory_find_before']['value']=[]
            elif change=='missingAfter':ev.bodies['ClosureHistory_find_after']['value']=[]
            elif change=='duplicateCommit':ev.bodies['ClosureHistory_find_commit']['value']*=2
            elif change=='pagination':ev.bodies['ClosureHistory_find_before']['nextLink']='more'
            elif change=='changedRequest':ev.outputs['Test_trigger']['text_7']='LC04-OTHER'
            elif change=='foreignCase':ev.bodies['ClosureHistory_current_case']={**ev.bodies['ClosureHistory_current_case'],'CaseUID':'OTHER'}
            elif change=='foreignSource':ev.outputs['Selected_case_context']['baselineUniqueId']='OTHER'
            else:ev.outputs['ClosureHistory_owner_record']['CaseUID']='OTHER'
            self.assertFalse(history_check(nodes,ev),change)

    def test_human_unknown_case_fields_original_token_and_versioned_trace_remain_significant(self):
        for change in ('human','beforeToken','proofOrigin','commitActor','absentTrace','version','metadataToken'):
            _,_,_,nodes,ev=historical_fixture()
            if change=='human':ev.bodies['ClosureHistory_current_case']['unknownHumanField']='Edited'
            elif change=='beforeToken':ev.outputs['ClosureHistory_before_record']['beforeCaseETag']='"case,4"'
            elif change=='proofOrigin':ev.outputs['ClosureHistory_after_record']['runId']='OTHER'
            elif change=='commitActor':ev.outputs['ClosureHistory_commit_record']['committedByRun']='OTHER'
            elif change=='absentTrace':ev.outputs['ClosureHistory_commit_record'].pop('originRunId')
            elif change=='version':ev.outputs['ClosureHistory_before_record']['contract'].pop('runtimeTraceVersion')
            else:ev.bodies['ClosureHistory_after_after']['ETag']='"changed"'
            self.assertFalse(history_check(nodes,ev),change)

    def test_frame_is_get_only_and_cannot_turn_partial_proofs_into_a_commit(self):
        _,_,graph,nodes,ev=historical_fixture(False)
        self.assertTrue(history_check(nodes,ev))
        for node in nodes.values():
            if node['type']=='OpenApiConnection':self.assertEqual(node['inputs']['parameters']['parameters/method'],'GET')
        audit=audit_actions({'actions':graph});self.assertLessEqual(audit['maximumActionDepth'],8)
        self.assertLessEqual(audit['actionCount'],500)

    def test_historical_collector_and_writer_preserve_original_contract_and_never_repeat_merge(self):
        for committed in (True,False):
            context,binding,_,history,ev=historical_fixture(committed)
            self.assertTrue(history_check(history,ev))
            frame=value(history['ClosureHistory_frame']['inputs'],ev)
            _,_,_,fresh=fixture();fresh.outputs['Selected_case_context']=copy.deepcopy(ev.outputs['Selected_case_context'])
            fresh.outputs['Native_prepared_revision']['currentCaseETag']=frame['currentCaseETag']
            fresh.outputs['ClosureHistory_frame']=frame
            for name in ('ClosureEntry_case','ClosureEntry_case_after'):
                fresh.bodies[name]=copy.deepcopy(frame['currentCase']);fresh.outputs[name]={'headers':{'ETag':frame['currentCaseETag']}}
            fresh.outputs['Action_SelectedPreparation_Verified_preparation_ownership']['status']='Skipped'
            collector=_flatten(build_binding_reads(context,binding,'ClosureHistory_frame'))
            self.assertTrue(collect(collector,fresh))
            fresh.outputs['ClosureEntry_binding_result']=value(collector['ClosureEntry_binding_result']['inputs'],fresh)
            fresh.outputs['Test_trigger']=copy.deepcopy(ev.outputs['Test_trigger'])
            writer=_flatten(build_initial_transition(context,binding,'ClosureHistory_frame'))
            self.assertTrue(fresh.evaluate(writer['ClosureEntry_validate_write']['expression']))
            fresh.outputs['ClosureEntry_fresh_contract']=value(writer['ClosureEntry_fresh_contract']['inputs'],fresh)
            contract=value(writer['ClosureEntry_write_contract']['inputs'],fresh)
            self.assertEqual(contract,frame['originalContract'])
            self.assertEqual(contract['initialCaseETag'],'"case,3"')
            self.assertEqual(contract['retainedHumanNote']['odata.id'],'business data must survive')
            fresh.outputs.update(Cycle_contract=contract,ClosureEntry_write_contract=contract,
                Cycle_current_snapshot=copy.deepcopy(fresh.outputs['ClosureEntry_binding_result']['evidence']),
                Cycle_current_complete=True,Cycle_case={'headers':{'ETag':frame['currentCaseETag']}},
                Cycle_before_record=frame['beforeProof'],Cycle_after_record=frame['afterProof'],
                Cycle_replay_before=frame['beforeProof'],Cycle_replay_after=frame['afterProof'],Cycle_commit_record=frame['commit'])
            fresh.outputs['Cycle_expected_evidence']=value(writer['Cycle_expected_evidence']['inputs'],fresh)
            fresh.bodies['Cycle_case']=frame['currentCase']
            for kind in HISTORIES:
                for suffix in ('','_stable'):fresh.bodies['Cycle_current_'+kind+suffix]=copy.deepcopy(fresh.bodies['ClosureEntry_check_'+kind+suffix])
            for kind in ('before','after','commit'):fresh.bodies['Cycle_find_'+kind]={'value':[{}] if kind!='commit' or committed else []}
            self.assertTrue(fresh.evaluate(writer['Cycle_reads_valid']['inputs']))
            fresh.outputs['Cycle_reads_valid']=True
            self.assertFalse(fresh.evaluate(writer['Cycle_choose_initial']['expression']))
            route='Cycle_replay_route' if committed else 'Cycle_choose_recovery'
            guard='Cycle_verify_replay' if committed else 'Cycle_verify_recovery'
            self.assertTrue(fresh.evaluate(writer[route]['expression']))
            self.assertTrue(fresh.evaluate(writer[guard]['expression']))
            self.assertNotIn('Cycle_apply_closure',_flatten(writer[route]['actions']))
            if not committed:
                fresh.outputs['Test_workflow']={'run':{'name':'RECOVERY-B'}}
                saved=value(writer['Recovery_Cycle_commit_payload']['inputs'],fresh)
                self.assertEqual((saved['originRunId'],saved['committedByRun'],saved['runId']),('ORIGIN-A','RECOVERY-B','RECOVERY-B'))
                fresh.outputs.update(Recovery_Cycle_commit_payload=saved,Recovery_Cycle_saved_commit=copy.deepcopy(saved))
                receipt=value(writer['Recovery_Native_closure_transition']['inputs'],fresh)
                self.assertTrue(receipt['qualified']);self.assertEqual(receipt['caseWriteCount'],0)
                fresh.outputs['Cycle_commit_record']=saved;fresh.bodies['Cycle_find_commit']={'value':[{}]}
                self.assertTrue(fresh.evaluate(writer['Cycle_verify_replay']['expression']))
                self.assertFalse(any(node['type']=='OpenApiConnection' for node in _flatten(writer['Cycle_verify_replay']['actions']).values()))
            changed=copy.deepcopy(fresh.bodies);changed['Cycle_current_assurance']['unknownWrapper']='changed after historical read'
            self.assertFalse(Expressions(changed,fresh.outputs).evaluate(writer['Cycle_reads_valid']['inputs']))


if __name__=='__main__':unittest.main()
