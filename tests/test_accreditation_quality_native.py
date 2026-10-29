# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
import copy
import hashlib
import json
from pathlib import Path
import unittest
from uuid import UUID
from scripts.ppg_accreditation_quality_native import project_example

class ProjectionTests(unittest.TestCase):
    def setUp(self):
        x=json.loads(Path('tests/fixtures/accreditation/second-example.json').read_text())
        self.p,self.g=x['package'],x['graph']
        self.source=json.dumps(dict(fixtureOnly=True,realServiceActivity=False,humanReviewClaimed=False,
                                   observation=self.p['indicatorObservation'])).encode()
        self.receipt=dict(sha256=hashlib.sha256(self.source).hexdigest(),uniqueId=str(UUID(int=1, version=4)),
                          version='1.0',url='https://example.invalid/site/fictional.json')
    def test_projection_preserves_independent_unknowns_and_input(self):
        before=copy.deepcopy((self.p,self.g))
        result=project_example(self.p,self.g,self.source,self.receipt)
        self.assertEqual([r['Outcome'] for r in result['assessments']],['Unknown','Unknown'])
        self.assertEqual(len(result['mappings']),2)
        self.assertNotIn('CycleKey',result['context'][0])
        self.assertFalse(result['nativeWorkflowQualified'])
        self.assertEqual(before,(self.p,self.g))
    def test_observation_and_file_integrity_are_required(self):
        self.p['indicatorObservation']['Numerator']=3
        with self.assertRaisesRegex(ValueError,'captured source'):project_example(self.p,self.g,self.source,self.receipt)
        self.receipt['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'bytes mismatch'):project_example(self.p,self.g,self.source,self.receipt)
    def test_existing_decisions_and_nonfictional_evidence_are_not_relabelled(self):
        for state in ('reviewed', 'rejected', 'superseded', 'needs-review'):
            graph = copy.deepcopy(self.g)
            selected = next(row for row in graph['mappings']
                            if row['EvidenceVersionKey'] == self.p['EvidenceVersionKey'])
            selected.update(reviewState=state, decisionRef='fixture:human-decision')
            before = copy.deepcopy(graph)
            with self.subTest(state=state):
                with self.assertRaisesRegex(ValueError, 'decisions must not be replaced'):
                    project_example(self.p, graph, self.source, self.receipt)
                self.assertEqual(graph, before)
        for access in ('ordinary', 'restricted'):
            graph = copy.deepcopy(self.g)
            next(row for row in graph['evidenceVersions']
                 if row['EvidenceVersionKey'] == self.p['EvidenceVersionKey'])['accessClass'] = access
            with self.assertRaisesRegex(ValueError, 'explicitly fictional'):
                project_example(self.p, graph, self.source, self.receipt)

    def test_cli_outputs_private_payload_and_refuses_overwrite(self):
        import os
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source.json').write_bytes(self.source)
            (root / 'receipt.json').write_text(json.dumps(self.receipt))
            command = [sys.executable, '-m', 'scripts.ppg_accreditation_quality_native',
                       '--fixture', 'tests/fixtures/accreditation/second-example.json',
                       '--source', str(root / 'source.json'),
                       '--file-receipt', str(root / 'receipt.json'),
                       '--output', str(root / 'rows.json')]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(json.loads(first.stdout)['counts'],
                             dict(context=1, evidence=1, mappings=2, assessments=2, cases=1))
            output = root / 'rows.json'
            before = output.read_bytes()
            self.assertEqual(json.loads(before), project_example(self.p, self.g, self.source, self.receipt))
            if os.name == 'posix':
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            repeat = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(repeat.returncode, 2)
            self.assertEqual(output.read_bytes(), before)
            invalid_output = root / 'invalid.json'
            (root / 'source.json').write_text('[]')
            failed = subprocess.run(command[:-1] + [str(invalid_output)], capture_output=True, text=True)
            self.assertEqual(failed.returncode, 2)
            self.assertIn('must be objects', failed.stderr)
            self.assertFalse(invalid_output.exists())

    def test_missing_data_stays_null(self):
        self.p['indicatorObservation'].update(Numerator=None,MissingDataReason='Fictional unavailable sample')
        source=json.loads(self.source);source['observation']=self.p['indicatorObservation'];self.source=json.dumps(source).encode()
        self.receipt['sha256']=hashlib.sha256(self.source).hexdigest()
        out=project_example(self.p,self.g,self.source,self.receipt)
        self.assertIsNone(json.loads(out['cases'][0]['CaseDetailsJSON'])['observation']['Numerator'])
