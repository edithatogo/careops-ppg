import copy
import json
import unittest
from pathlib import Path
from scripts.ppg_catalogue_flow_batches import build


class CatalogueBatchTests(unittest.TestCase):
    def fixture(self):
        source = Path('templates/installation/workflows/qw3source-onlyreconciliation.json').read_text()
        # Only the destination token needs a concrete UUID for binding discovery.
        import re
        source = re.sub(r"lists\(guid''__PPG_INSTALL_\d+__''\)",
                        "lists(guid''00000000-0000-4000-8000-000000000001'')", source)
        return json.loads(source)

    def test_preserves_guards_and_commit_last(self):
        source = self.fixture(); before = copy.deepcopy(source)
        out = build(source)
        self.assertEqual(source, before)
        old = before['properties']['definition']['actions']['Daily_due']['actions']
        new = out['properties']['definition']['actions']['Daily_due']['actions']
        for key in ['Success_receipt', 'Commit_checkpoint', 'Acquire_fresh']:
            self.assertEqual(old[key], new[key])
        for key in ['Guard_input', 'Guard_readback']:
            self.assertEqual(old['Reconcile']['actions'][key]['expression'],
                             new['Reconcile']['actions'][key]['expression'])

    def test_bounded_conditional_writes_and_failure_stop(self):
        out = build(self.fixture())
        branch = out['properties']['definition']['actions']['Daily_due']['actions']['Reconcile']['actions']['Guard_input']['actions']['Write_changes']
        guard = out['properties']['definition']['actions']['Daily_due']['actions']['Reconcile']['actions']['Guard_input']['actions']
        self.assertIn('Serial_identity_writes', guard)
        def depth(actions, level=0):
            return max([level] + [depth(a.get('actions', {}), level+1) for a in actions.values() if a.get('actions')] + [depth(a['else'].get('actions', {}), level+1) for a in actions.values() if a.get('else', {}).get('actions')])
        self.assertLessEqual(depth(out['properties']['definition']['actions']), 8)
        loop = branch['actions']['Catalogue_batches']
        self.assertEqual(loop['runtimeConfiguration']['concurrency']['repetitions'], 1)
        actions = loop['actions']['Continue_batches']['actions']['Batch_work']['actions']
        self.assertIn(',20)', actions['Batch_rows']['inputs'])
        wire = actions['Batch_parts']['inputs']['select']
        self.assertIn('MERGE ', wire); self.assertIn('If-Match: ', wire)
        self.assertNotIn('ownerAccepted', wire)
        self.assertEqual(actions['Send_catalogue_batch']['inputs']['retryPolicy'], {'type': 'none'})
        self.assertIn('204 No Content', actions['Batch_errors']['inputs']['where'])
        self.assertIn('length(outputs(\'Batch_rows\'))', actions['Require_batch_success']['expression'])
        self.assertEqual(actions['Batch_cooldown']['inputs']['interval']['count'], 10)
