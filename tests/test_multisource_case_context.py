"""Exercise actual emitted eligible-source lookup and current-source checks offline."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/lifecycle'))
from build_selected_case_context import build as context_build
from build_case_reference_entry import build as manual_build, definition_digest
from build_multisource_case_context import (
    with_eligible_sources, with_ownership_projection_source, with_additional_context_sources,
    digest, _check_context_shape, with_additional_ownership_projection_sources,
)
from build_operator_entry import _flatten
from test_prepared_closure_check import Expressions
from test_case_reference_entry import fixture as manual_fixture, TABLE, COLLECTION


def fixture():
    flow,button,_=manual_fixture()
    profiles=[]
    for number in (1,2):
        content='FICTIONAL policy '+str(number)+'\n'
        profiles.append({'DocumentUID':'FICTIONAL-POLICY-'+str(number),
            'UniqueId':'00000000-0000-4000-8000-00000000000'+str(number),
            'DocumentReference':'https://example.invalid/site/source'+str(number)+'.txt',
            'ReviewedVersionRef':'fictional-v1','ETag':'"1"','content':content,
            'sha256':hashlib.sha256(content.encode()).hexdigest()})
    context=context_build(flow,{'qualificationOnly':True,'siteUrl':'https://example.invalid/site',
        'caseListUri':COLLECTION,'evidenceFolder':'/site/evidence','source':profiles[0]})
    context['properties']['definition']['triggers']['manual']['inputs']['schema']={'rows':{'items':{
        'properties':{'text':{'type':'string','title':'Operation'}},'required':['text']}}}
    binding={'qualificationOnly':True,'approvedDefinitionSHA256':definition_digest(context['properties']['definition']),
        'approvedButtonTriggerSHA256':definition_digest(button['properties']['definition']['triggers']['manual'])}
    return manual_build(context,button,binding),profiles


def candidate():
    flow,profiles=fixture()
    return with_eligible_sources(flow,profiles,digest(flow['properties']['definition'])),profiles


class MultisourceCaseContextTests(unittest.TestCase):
    def extra_profile(self, profiles):
        return {**profiles[1], 'UniqueId': '00000000-0000-4000-8000-000000000003',
                'DocumentUID': 'FICTIONAL-POLICY-3',
                'DocumentReference': 'https://example.invalid/site/source3.txt'}

    def projection_append_fixture(self):
        original,profiles=candidate()
        extras=[self.extra_profile(profiles)]
        extras.append({**extras[0], 'UniqueId':profiles[0]['UniqueId'][:-1]+'4',
                       'DocumentUID':'FICTIONAL-POLICY-4',
                       'DocumentReference':'https://example.invalid/site/source4.txt'})
        original=with_additional_context_sources(original,extras,digest(original['properties']['definition']))
        original=with_ownership_projection_source(original,profiles[1]['UniqueId'],digest(original['properties']['definition']))
        return original,profiles+extras

    def test_append_projection_preserves_prior_scopes_and_all_other_nodes(self):
        original,profiles=self.projection_append_fixture();original['properties']['state']='Started'
        before=copy.deepcopy(original)
        out=with_additional_ownership_projection_sources(original,[p['UniqueId'] for p in profiles[2:]],digest(original['properties']['definition']))
        self.assertEqual(original,before);self.assertEqual(out['properties']['state'],'Stopped')
        self.assertEqual(_check_context_shape(out['properties']['definition']),profiles)
        nodes=_flatten(out['properties']['definition']['actions']);expression=nodes['SourceProfiles_operation']['expression'].replace("triggerBody()?['text']","outputs('Test_operation')")
        for index,profile in enumerate(profiles):
            for operation in ('Check context','Project ownership','Check preparation','Check readiness','Close review','Ownership response'):
                result=Expressions(outputs={'Test_operation':operation,'SourceProfiles_selected':profile}).evaluate(expression)
                self.assertEqual(result,index==0 or operation in ('Check context','Project ownership'))
        old=_flatten(original['properties']['definition']['actions'])
        nodes['SourceProfiles_operation']['expression']=old['SourceProfiles_operation']['expression']
        del nodes['Selected_case_context']['inputs']['limits']['additionalOwnershipProjectionSources']
        out['properties']['state']='Started';self.assertEqual(out,original)

    def test_append_projection_refuses_duplicates_seed_unknown_digest_and_guard_drift(self):
        original,profiles=self.projection_append_fixture();pin=digest(original['properties']['definition'])
        for additions in ([],[profiles[0]['UniqueId']],[profiles[1]['UniqueId']],['unknown'],[None],
                          [profiles[2]['UniqueId']]*2):
            with self.subTest(additions=additions),self.assertRaises(ValueError):
                with_additional_ownership_projection_sources(original,additions,pin)
        with self.assertRaises(ValueError):
            with_additional_ownership_projection_sources(original,[profiles[2]['UniqueId']],'0'*64)
        changed=copy.deepcopy(original)
        _flatten(changed['properties']['definition']['actions'])['SourceProfiles_operation']['expression']='@true'
        with self.assertRaises(ValueError):
            with_additional_ownership_projection_sources(changed,[profiles[2]['UniqueId']],digest(changed['properties']['definition']))
        once=with_additional_ownership_projection_sources(original,[profiles[2]['UniqueId']],pin)
        with self.assertRaises(ValueError):
            with_additional_ownership_projection_sources(once,[profiles[2]['UniqueId']],digest(once['properties']['definition']))
        twice=with_additional_ownership_projection_sources(once,[profiles[3]['UniqueId']],digest(once['properties']['definition']))
        self.assertEqual(_flatten(twice['properties']['definition']['actions'])['Selected_case_context']['inputs']['limits']['additionalOwnershipProjectionSources'],[p['UniqueId'] for p in profiles[2:]])

    def test_append_context_source_changes_only_table_and_stopped_state(self):
        original, profiles = candidate(); original['properties']['state'] = 'Started'
        before = copy.deepcopy(original); addition = self.extra_profile(profiles)
        out = with_additional_context_sources(original, [addition], digest(original['properties']['definition']))
        self.assertEqual(original, before)
        self.assertEqual(_check_context_shape(out['properties']['definition']), profiles + [addition])
        self.assertEqual(out['properties']['state'], 'Stopped')
        _flatten(out['properties']['definition']['actions'])['SourceProfiles_configured']['inputs'] = profiles
        out['properties']['state'] = 'Started'
        self.assertEqual(out, original)

    def test_appended_source_does_not_gain_projection_or_preparation(self):
        original, profiles = candidate(); addition = self.extra_profile(profiles)
        out = with_additional_context_sources(original, [addition], digest(original['properties']['definition']))
        expression = _flatten(out['properties']['definition']['actions'])['SourceProfiles_operation']['expression']
        expression = expression.replace("triggerBody()?['text']", "outputs('Test_operation')")
        for operation in ('Check context', 'Project ownership', 'Check preparation', 'Check readiness', 'Close review'):
            ev = Expressions(outputs={'Test_operation': operation, 'SourceProfiles_selected': addition})
            self.assertEqual(ev.evaluate(expression), operation == 'Check context')

    def test_append_rejects_duplicate_bad_digest_content_and_changed_guard(self):
        original, profiles = candidate(); addition = self.extra_profile(profiles)
        for additions in ([], [profiles[1]], [{**addition, 'content': 'changed bytes'}],
                          [{**addition, 'DocumentReference': 'https://other.invalid/source3.txt'}]):
            with self.assertRaises(ValueError):
                with_additional_context_sources(original, additions, digest(original['properties']['definition']))
        with self.assertRaises(ValueError):
            with_additional_context_sources(original, [addition], '0' * 64)
        tampered = copy.deepcopy(original)
        _flatten(tampered['properties']['definition']['actions'])['SourceProfiles_operation']['expression'] = '@true'
        with self.assertRaises(ValueError):
            with_additional_context_sources(tampered, [addition], digest(tampered['properties']['definition']))

    def test_composition_preserves_original_and_remains_stopped_read_only(self):
        flow,profiles=fixture();before=copy.deepcopy((flow,profiles))
        out=with_eligible_sources(flow,profiles,digest(flow['properties']['definition']))
        self.assertEqual(before,(flow,profiles));self.assertEqual(out['properties']['state'],'Stopped')
        self.assertEqual(out['properties']['connectionReferences'],flow['properties']['connectionReferences'])
        nodes=_flatten(out['properties']['definition']['actions'])
        self.assertEqual(_check_context_shape(out['properties']['definition']),profiles)
        for action in nodes.values():
            if action['type']=='OpenApiConnection':
                self.assertEqual(action['inputs']['parameters']['parameters/method'],'GET')
        self.assertEqual(nodes['Read_source_before']['runAfter'],{'SourceProfiles_verify':['Succeeded']})

    def test_exact_request_scope_selects_each_source_and_mixed_or_unknown_scope_holds(self):
        out,profiles=candidate();nodes=_flatten(out['properties']['definition']['actions'])
        for profile in profiles:
            request={k:profile[s] for k,s in [('DocumentUID','DocumentUID'),('DocumentReference','DocumentReference'),
                ('ReviewedVersionRef','ReviewedVersionRef'),('DocumentSHA256','sha256')]}
            for changed in (None,*request):
                actual=copy.deepcopy(request)
                if changed:actual[changed]='unknown'
                ev=Expressions(outputs={'Parse_baseline':{'request':actual}})
                matches=[]
                for row in profiles:
                    ev.current=row
                    if ev.evaluate(nodes['SourceProfiles_matches']['inputs']['where']):matches.append(row)
                ev.bodies['SourceProfiles_matches']=matches
                self.assertEqual(ev.evaluate(nodes['SourceProfiles_verify']['expression']),changed is None)
                if changed is None:self.assertEqual(ev.evaluate(nodes['SourceProfiles_selected']['inputs']),profile)

    def test_other_operations_stay_on_original_source(self):
        out,profiles=candidate();guard=_flatten(out['properties']['definition']['actions'])['SourceProfiles_operation']
        for number,profile in enumerate(profiles):
            for operation in ('Check context','Prepare review','Close review'):
                # The existing test evaluator has no triggerBody; substitute only that leaf.
                expr=guard['expression'].replace("triggerBody()?['text']","outputs('Test_operation')")
                ev=Expressions(outputs={'Test_operation':operation,'SourceProfiles_selected':profile})
                self.assertEqual(ev.evaluate(expr),operation=='Check context' or number==0)
        self.assertEqual(guard['else']['actions']['SourceProfiles_operation_refused']['type'],'Terminate')

    def test_explicit_projection_exception_is_operation_and_source_specific(self):
        original,profiles=candidate()
        out=with_ownership_projection_source(original,profiles[1]['UniqueId'],
                                             digest(original['properties']['definition']))
        nodes=_flatten(out['properties']['definition']['actions'])
        expression=nodes['SourceProfiles_operation']['expression'].replace(
            "triggerBody()?['text']","outputs('Test_operation')")
        for index,profile in enumerate(profiles):
            for operation in ('Check context','Project ownership','Check preparation','Check readiness'):
                actual=Expressions(outputs={'Test_operation':operation,
                    'SourceProfiles_selected':profile}).evaluate(expression)
                self.assertEqual(actual,index==0 or operation in ('Check context','Project ownership'))
        unknown={**profiles[1],'UniqueId':'00000000-0000-4000-8000-000000000009'}
        self.assertFalse(Expressions(outputs={'Test_operation':'Project ownership',
            'SourceProfiles_selected':unknown}).evaluate(expression))
        self.assertEqual(_check_context_shape(out['properties']['definition']),profiles)

    def test_projection_exception_preserves_every_other_node_and_input(self):
        original,profiles=candidate();original['properties']['state']='Started'
        before=copy.deepcopy(original)
        out=with_ownership_projection_source(original,profiles[1]['UniqueId'],
                                             digest(original['properties']['definition']))
        self.assertEqual(original,before)
        self.assertEqual(out['properties']['state'],'Stopped')
        old=_flatten(original['properties']['definition']['actions'])
        new=_flatten(out['properties']['definition']['actions'])
        self.assertEqual(old.keys(),new.keys())
        # Restore only the two deliberate edits, then compare the entire flow.
        new['SourceProfiles_operation']['expression']=old['SourceProfiles_operation']['expression']
        del new['Selected_case_context']['inputs']['limits']['additionalOwnershipProjectionSource']
        out['properties']['state']='Started'
        self.assertEqual(out,original)

    def test_projection_exception_rejects_unreviewed_unknown_or_repeated_scope(self):
        original,profiles=candidate();pin=digest(original['properties']['definition'])
        for source,approved in [(profiles[1]['UniqueId'],'0'*64),
                (profiles[0]['UniqueId'],pin),('unknown',pin),('@utcNow()',pin)]:
            with self.subTest(source=source),self.assertRaises(ValueError):
                with_ownership_projection_source(original,source,approved)
        out=with_ownership_projection_source(original,profiles[1]['UniqueId'],pin)
        with self.assertRaisesRegex(ValueError,'existing projection exception'):
            with_ownership_projection_source(out,profiles[1]['UniqueId'],digest(out['properties']['definition']))

    def test_projection_fresh_reads_follow_each_verified_context_not_the_original_source(self):
        original,profiles=candidate();nodes=_flatten(original['properties']['definition']['actions'])
        names=('Selected_Projection_before_source','Selected_Projection_after_source')
        for name in names:
            reader=copy.deepcopy(nodes['Read_source_before'])
            reader['inputs']['parameters']['parameters/uri']="_api/web/GetFileById('"+profiles[0]['UniqueId']+"')?$select=UniqueId,ETag,Length"
            original['properties']['definition']['actions'][name]=reader
        before=copy.deepcopy(original)
        out=with_ownership_projection_source(original,profiles[1]['UniqueId'],digest(original['properties']['definition']))
        self.assertEqual(original,before);updated=_flatten(out['properties']['definition']['actions'])
        for name in names:
            for profile in profiles:
                uri=Expressions(outputs={'Selected_case_context':{'sourcePins':profile}}).evaluate(
                    updated[name]['inputs']['parameters']['parameters/uri'])
                self.assertEqual(uri,"_api/web/GetFileById('"+profile['UniqueId']+"')?$select=UniqueId,ETag,Length")
            for key in ('host','retryPolicy'):
                self.assertEqual(updated[name]['inputs'].get(key),nodes['Read_source_before']['inputs'].get(key))
        _check_context_shape(out['properties']['definition'])
        updated[names[0]]['inputs']['parameters']['parameters/uri']=before['properties']['definition']['actions'][names[0]]['inputs']['parameters']['parameters/uri']
        with self.assertRaisesRegex(ValueError,'follow the verified selected context'):
            _check_context_shape(out['properties']['definition'])

    def test_projection_exception_refuses_unknown_or_writing_metadata_readers(self):
        for change in ('source','method','site'):
            original,profiles=candidate();nodes=_flatten(original['properties']['definition']['actions'])
            reader=copy.deepcopy(nodes['Read_source_before']);params=reader['inputs']['parameters']
            params['parameters/uri']="_api/web/GetFileById('"+profiles[0]['UniqueId']+"')?$select=UniqueId,ETag,Length"
            if change=='source':params['parameters/uri']='_api/web/unknown'
            elif change=='method':params['parameters/method']='POST'
            else:params['dataset']='https://other.invalid/site'
            original['properties']['definition']['actions']['Selected_Projection_before_source']=reader
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'reviewed projection metadata reader'):
                with_ownership_projection_source(original,profiles[1]['UniqueId'],digest(original['properties']['definition']))

    def test_projection_exception_shape_rejects_broader_operation_or_metadata_tampering(self):
        original,profiles=candidate()
        out=with_ownership_projection_source(original,profiles[1]['UniqueId'],
                                             digest(original['properties']['definition']))
        for change in ('operation','unknown_source','seed_source','frame'):
            modified=copy.deepcopy(out);nodes=_flatten(modified['properties']['definition']['actions'])
            if change=='operation':
                nodes['SourceProfiles_operation']['expression']=nodes['SourceProfiles_operation']['expression'].replace(
                    "'Project ownership'","'Check preparation'")
            elif change=='unknown_source':
                nodes['Selected_case_context']['inputs']['limits']['additionalOwnershipProjectionSource']='unknown'
            elif change=='seed_source':
                nodes['Selected_case_context']['inputs']['limits']['additionalOwnershipProjectionSource']=profiles[0]['UniqueId']
            else:nodes['Verify_source_and_case']['expression']='@true'
            with self.subTest(change=change),self.assertRaises(ValueError):
                _check_context_shape(modified['properties']['definition'])

    def test_invalid_or_ambiguous_profiles_and_unreviewed_definition_are_refused(self):
        flow,profiles=fixture();pin=digest(flow['properties']['definition'])
        for change in ('duplicate','hash','site','wildcard','missing_seed','expression_content','pin'):
            values=copy.deepcopy(profiles);approved=pin
            if change=='duplicate':values.append(copy.deepcopy(values[0]))
            elif change=='hash':values[1]['content']='changed'
            elif change=='site':values[1]['DocumentReference']='https://other.invalid/source.txt'
            elif change=='wildcard':values[1]['ETag']='*'
            elif change=='missing_seed':values=values[1:]
            elif change=='expression_content':
                values[1]['content']="@utcNow()"
                values[1]['sha256']=hashlib.sha256(values[1]['content'].encode()).hexdigest()
            else:approved='0'*64
            with self.subTest(change=change),self.assertRaises(ValueError):with_eligible_sources(flow,values,approved)

    def test_source_metadata_content_and_frame_remain_native_checks(self):
        out,profiles=candidate();nodes=_flatten(out['properties']['definition']['actions'])
        expression=nodes['Verify_source_and_case']['expression']
        # Native case/baseline frame and selected profile source checks stay combined.
        for name in ('Recheck_case','Recheck_baseline','Read_source_before','Read_source_after','Read_source_content'):
            self.assertIn(name,expression)
        for name in ('Read_source_before','Read_source_after'):
            for key in ('ETag','UniqueId','ServerRelativeUrl'):self.assertIn("body('"+name+"')?['"+key+"']",expression)
        for key in ('ETag','UniqueId','content','DocumentReference'):
            self.assertIn("outputs('SourceProfiles_selected')?['"+key+"']",expression)
        for name in ('Read_source_before','Read_source_content','Read_source_after'):
            uri=nodes[name]['inputs']['parameters']['parameters/uri']
            for profile in profiles:
                ev=Expressions(outputs={'SourceProfiles_selected':profile})
                self.assertIn(profile['UniqueId'],ev.evaluate(uri))

    def test_actual_final_guard_rejects_source_drift_and_case_or_baseline_changes(self):
        out,profiles=candidate();nodes=_flatten(out['properties']['definition']['actions'])
        for profile in profiles:
            metadata={'ETag':profile['ETag'],'UniqueId':profile['UniqueId'],
                'ServerRelativeUrl':'/site/'+profile['DocumentReference'].rsplit('/',1)[1]}
            baseline={'ETag':'"7"','UniqueId':'baseline-fixture'}
            bodies={name:copy.deepcopy(baseline) for name in
                ('Read_baseline_before','Read_baseline_after','Recheck_baseline')}
            bodies.update(Read_source_before=copy.deepcopy(metadata),Read_source_after=copy.deepcopy(metadata),
                Read_source_content=profile['content'])
            outputs={'SourceProfiles_selected':profile,'Read_selected_case':{'headers':{'ETag':'"9"'}},
                'Recheck_case':{'headers':{'ETag':'"9"'}}}
            for change in (None,'etag','uid','path','content','case','baseline'):
                b=copy.deepcopy(bodies);o=copy.deepcopy(outputs)
                if change in ('etag','uid','path'):
                    key={'etag':'ETag','uid':'UniqueId','path':'ServerRelativeUrl'}[change]
                    b['Read_source_after'][key]='changed'
                elif change=='content':b['Read_source_content']='changed content'
                elif change=='case':o['Recheck_case']['headers']['ETag']='"10"'
                elif change=='baseline':b['Recheck_baseline']['ETag']='"8"'
                with self.subTest(source=profile['DocumentUID'],change=change):
                    self.assertEqual(Expressions(bodies=b,outputs=o).evaluate(
                        nodes['Verify_source_and_case']['expression']),change is None)


if __name__=='__main__':unittest.main()
