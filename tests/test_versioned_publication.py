import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools/lifecycle'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_versioned_publication import build
from build_prepared_decision_outcome import digest
from tests.test_prepared_binary_publication import fixture as publication_fixture, build as publication_build, flatten
from tests.test_lifecycle_relationship_checkpoint import fixture as checkpoint_fixture
from tests.test_prepared_closure_check import Expressions


def fixture():
    profile=publication_build(*publication_fixture())
    snapshot, rows, context=checkpoint_fixture()
    rows=[dict(r,Id=i+1,GUID='fictional-row-'+str(i),**{'odata.etag':'"1"'}) for i,r in enumerate(rows)]
    binding=dict(qualificationOnly=True,approvedDefinitionSHA256=digest(profile['properties']['definition']),
        snapshot=snapshot,graphRows=rows,graphCollectionUri="_api/web/lists(guid'00000000-0000-4000-8000-000000000001')/items",
        checkpoint=dict(UniqueId='00000000-0000-4000-8000-000000000002',ETag='"checkpoint,1"',Length=123,UIVersionLabel='1.0'),
        originalSourceScope=context['preparedRevision']['originalSourceScope'],sourceBinding=context['sourceBinding'])
    return profile,binding


class VersionedPublicationTests(unittest.TestCase):
    def test_get_only_binding_preserves_writers_and_places_guards_at_effect_boundaries(self):
        profile,binding=fixture();before=copy.deepcopy((profile,binding));out=build(profile,binding)
        original=flatten(profile['properties']['definition']['actions']);actions=flatten(out['properties']['definition']['actions'])
        for name,action in original.items():
            if action['type']=='OpenApiConnection' and action['inputs']['parameters']['parameters/method']!='GET':
                self.assertEqual(actions[name],action)
        added={k:v for k,v in actions.items() if k not in original}
        self.assertTrue(all(v['inputs']['parameters']['parameters/method']=='GET' for v in added.values() if v['type']=='OpenApiConnection'))
        for target,label in [('Copy_if_absent','before_copy'),('Ensure_publication','before_event'),
                ('Native_binary_copy_observation','after_copy'),('Native_binary_publication_receipt','after_event')]:
            self.assertEqual(actions[target]['runAfter'],{'RV_'+label+'_guard':['Succeeded']})
        self.assertFalse(actions['Native_binary_publication_receipt']['inputs']['generalRelationshipWriterQualified'])
        self.assertEqual((profile,binding),before)

    def test_changed_graph_checkpoint_source_and_paging_refuse(self):
        profile,binding=fixture();actions=flatten(build(profile,binding)['properties']['definition']['actions'])
        expected=[{**r,'odata.id':None} for r in binding['graphRows']]
        bodies={'RV_before_copy_graph':{'value':binding['graphRows']},'RV_before_copy_clean':expected,
            'RV_before_copy_meta':binding['checkpoint']}
        outputs={'RV_expected_rows':expected,'RV_expected_checkpoint':binding['snapshot'],
            'RV_before_copy_parsed':copy.deepcopy(binding['snapshot']),'Native_prepared_revision':{'preparedRevision':{'originalSourceScope':binding['originalSourceScope']}},
            'Selected_case_context':{'sourcePins':{k:binding['sourceBinding']['source'][k] for k in ('UniqueId','ETag','DocumentUID')}}}
        expression=actions['RV_before_copy_guard']['expression']
        self.assertTrue(Expressions(bodies,outputs).evaluate(expression))
        for change in ('token','graph','source','content','continuation'):
            b,o=copy.deepcopy(bodies),copy.deepcopy(outputs)
            if change=='token':b['RV_before_copy_meta']['ETag']='"new"'
            elif change=='graph':b['RV_before_copy_clean'][0]['Rationale']='human edit'
            elif change=='source':o['Native_prepared_revision']['preparedRevision']['originalSourceScope']['DocumentSHA256']='d'*64
            elif change=='content':o['RV_before_copy_parsed']['journalSha256']='d'*64
            else:b['RV_before_copy_graph']['odata.nextLink']='fixture:more'
            with self.subTest(change=change):self.assertFalse(Expressions(b,o).evaluate(expression))

    def test_unreviewed_or_incomplete_graph_refused(self):
        for change in ('hash','missing','wildcard','snapshot'):
            p,b=fixture()
            if change=='hash':b['approvedDefinitionSHA256']='0'*64
            elif change=='missing':b['graphRows']=[]
            elif change=='wildcard':b['graphRows'][0]['odata.etag']=' * '
            else:b['snapshot']['journalSha256']='0'*64
            with self.subTest(change=change),self.assertRaises(ValueError):build(p,b)

    def test_boolean_record_identity_is_not_a_native_row(self):
        for field in ('Id', 'GUID'):
            profile, binding = fixture()
            binding['graphRows'][0][field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                build(profile, binding)


if __name__=='__main__':unittest.main()

class VersionedLiteralTests(unittest.TestCase):
    def test_long_and_expression_shaped_evidence_is_reconstructed_exactly(self):
        from build_versioned_publication import _bounded_literals
        raw={'evidence':"@outputs('not_executed')\\n"+('quoted\' text\n雪'*1700),
             'unchanged':{'id':7,'empty':''},'array':['@literal',None,True]}
        chunks={};prepared=_bounded_literals(raw,chunks);ev=Expressions()
        for name,node in chunks.items():
            self.assertLessEqual(len(node['inputs'].encode('utf-8')),8192)
            ev.outputs[name]=ev.evaluate(node['inputs'])
        def resolve(value):
            if isinstance(value,dict):return {k:resolve(v) for k,v in value.items()}
            if isinstance(value,list):return [resolve(v) for v in value]
            return ev.evaluate(value) if isinstance(value,str) else value
        self.assertEqual(resolve(prepared),raw)
        self.assertGreater(len(chunks),1)

    def test_relationship_binding_cannot_be_applied_twice(self):
        profile,binding=fixture();out=build(profile,binding)
        binding['approvedDefinitionSHA256']=digest(out['properties']['definition'])
        with self.assertRaises(ValueError):build(out,binding)
