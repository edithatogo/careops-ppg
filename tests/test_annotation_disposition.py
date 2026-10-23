import copy
import unittest
from tests.test_review_snapshot_delta import export
from scripts.ppg_annotation_disposition import prepare

OP = '00000000-0000-4000-8000-000000000102'


class Disposition(unittest.TestCase):
    def fixture(self):
        data = export()
        data['annotationItems']['value'][0]['@odata.etag'] = '"1"'
        return data

    def test_requires_rationale_version_and_exact_concurrency(self):
        data = self.fixture()
        for target, rationale, version in [('Deferred', '', None), ('Approved', 'why', None), ('Incorporated', 'why', None), ('Deferred', 'why', '2')]:
            with self.assertRaises(ValueError): prepare(data, 1, target, rationale, OP, version)
        data['annotationItems']['value'][0]['@odata.etag'] = '*'
        with self.assertRaises(ValueError): prepare(data, 1, 'Deferred', 'why', OP)

    def test_patch_preserves_original_binding_and_replay_preserves_later_edit(self):
        data = self.fixture();before = copy.deepcopy(data)
        result = prepare(data, 1, 'Incorporated', 'Fictional technical test', OP, '2')
        self.assertEqual(data, before)
        self.assertEqual(result['ifMatch'], '"1"')
        self.assertEqual(set(result['changes']), {'ReviewState', 'DecisionRationale', 'IncorporatedVersion'})
        version = dict(data['histories'][0]['versions']['value'][0], VersionId=1024, VersionLabel='2.0', DecisionRationale=result['changes']['DecisionRationale'])
        data['histories'][0]['versions']['value'].append(version)
        data['annotationItems']['value'][0]['ReviewState'] = 'Superseded'
        replay = prepare(data, 1, 'Incorporated', 'Fictional technical test', OP, '2')
        self.assertEqual(replay['action'], 'already_recorded')
        self.assertEqual(replay['currentStatus'], 'superseded')
        self.assertNotIn('changes', replay)
        with self.assertRaises(ValueError): prepare(data, 1, 'Incorporated', 'Different rationale', OP, '2')

    def test_web_summary_is_explicit_and_detailed_rationale_is_not_truncated(self):
        data=self.fixture();data['binding']['DispositionSummary']='SummaryInternal'
        for summary in ['', '   ', 'x'*256]:
            with self.assertRaises(ValueError):
                prepare(data,1,'Deferred','Detailed reason',OP,summary=summary)
        with self.assertRaises(ValueError):prepare(data,1,'Deferred','x'*256,OP)
        result=prepare(data,1,'Deferred','x'*300,OP,summary='Short explicit reason')
        self.assertEqual(result['changes']['SummaryInternal'],'Short explicit reason')
        self.assertIn('x'*300,result['changes']['DecisionRationale'])
        with self.assertRaises(ValueError):prepare(self.fixture(),1,'Deferred','reason',OP,summary='unknown field')
