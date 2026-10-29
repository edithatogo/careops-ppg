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
    def test_missing_data_stays_null(self):
        self.p['indicatorObservation'].update(Numerator=None,MissingDataReason='Fictional unavailable sample')
        source=json.loads(self.source);source['observation']=self.p['indicatorObservation'];self.source=json.dumps(source).encode()
        self.receipt['sha256']=hashlib.sha256(self.source).hexdigest()
        out=project_example(self.p,self.g,self.source,self.receipt)
        self.assertIsNone(json.loads(out['cases'][0]['CaseDetailsJSON'])['observation']['Numerator'])
