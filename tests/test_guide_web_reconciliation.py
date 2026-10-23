import importlib.util
import json
import unittest

spec = importlib.util.spec_from_file_location('guide_builder', 'tools/guide-reconciliation/build.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def actions(tree):
    for name, action in tree.items():
        yield name, action
        yield from actions(action.get('actions', {}))
        yield from actions(action.get('else', {}).get('actions', {}))


class WebReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.flow = module.build('https://example.invalid/review', 'F-source',
                                 'F-contexts', 'F-guides', {'connectionName': 'F-existing'})

    def test_writes_are_additive_and_source_never_written(self):
        mutations=[]
        for _, a in actions(self.flow['properties']['definition']['actions']):
            if a['type'] != 'OpenApiConnection':
                continue
            p=a['inputs']['parameters']
            self.assertEqual(a['inputs']['retryPolicy'], {'type':'none'})
            if p['parameters/method'] != 'GET':
                mutations.append(p)
                self.assertEqual(p['parameters/method'],'POST')
                self.assertNotIn('F-source',p['parameters/uri'])
                self.assertIn(p['parameters/uri'], ["_api/web/lists(guid'F-contexts')/items", "_api/web/lists(guid'F-guides')/items"])
        self.assertEqual(len(mutations),2)

    def test_no_premium_notifications_schedule_or_duplicate_action_names(self):
        d=self.flow['properties']['definition'];names=[n for n,_ in actions(d['actions'])]
        self.assertEqual(len(names),len(set(names)))
        self.assertEqual(set(self.flow['properties']['connectionReferences']),{'shared_sharepointonline'})
        self.assertEqual(d['triggers']['manual']['kind'],'Button')
        self.assertEqual(d['triggers']['manual']['runtimeConfiguration']['concurrency']['runs'],1)
        self.assertNotIn('Recurrence',json.dumps(d))

    def test_stale_scope_and_partial_results_are_held(self):
        d=json.dumps(self.flow)
        for requirement in ['SnapshotJSON','DocumentUID','ProposalRevision','Version',
                            'GuideText','Rationale','odata.nextLink','60000',
                            'Context_reused','Guide_reused','ReconciliationHeld']:
            self.assertIn(requirement,d)
        self.assertIn("equals(body('Read_context')?['SnapshotJSON'],string(body('Snapshot')))",d)
        self.assertIn("equals(first(body('Match_guide'))?['GuideText'],triggerBody()?['guideText'])",d)
