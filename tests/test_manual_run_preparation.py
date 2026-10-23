import copy
import hashlib
import json
from pathlib import Path
import unittest
from scripts.ppg_manual_run_preparation import prepare, MODULES


class ManualPreparationTests(unittest.TestCase):
    def fixture(self):
        template=b'fictional retained candidate'
        pack=dict(developmentEligible=True,humanDecision=None,policyApproved=False,
                  publicationAuthorised=False,notificationsEnabled=False,
                  developmentBasis=dict(templateSha256=hashlib.sha256(template).hexdigest(),inspectionSha256='a'*64),
                  inspectedSourceSha256='a'*64,requestedSubject={'documentUID':'fictional-doc'},
                  preparation={'criteriaVersion':'1.0.0'},preparedReviewRuns={'schemaVersion':1,'runs':[]})
        prompts={key:dict(version='1.0.0',bytes=(Path('templates/review-intelligence/v1.0.0')/(key+'.md')).read_bytes()) for key in MODULES}
        for p in prompts.values():p['sha256']=hashlib.sha256(p['bytes']).hexdigest()
        return pack,template,prompts

    def test_preparation_cannot_claim_execution_or_rewrite_prior_runs(self):
        pack,t,p=self.fixture();first=prepare(json.dumps(pack).encode(),t,p)
        prior=copy.deepcopy(first['runs'][0]);prior.update(status='held_missing_evidence',runId='fictional-held')
        pack['preparedReviewRuns']['runs']=[prior];before=copy.deepcopy(pack)
        a=prepare(json.dumps(pack).encode(),t,p);b=prepare(json.dumps(pack).encode(),t,p)
        self.assertEqual(a,b);self.assertEqual(pack,before);self.assertEqual(a['priorRuns'],pack['preparedReviewRuns'])
        self.assertEqual(len(a['runs']),7);self.assertEqual(len({r['runId'] for r in a['runs']}),7)
        for r in a['runs']:
            self.assertEqual(r['status'],'prepared');self.assertIsNone(r['completedAt']);self.assertIsNone(r['humanDisposition'])
            self.assertFalse(r['productionPromptApproved']);self.assertEqual(r['findings'][0]['claimType'],'unknown')
        self.assertFalse(a['manualReviewCompleted']);self.assertEqual(a['nativeAIInvocations'],0)

    def test_refuses_changed_pins_partial_modules_and_decision_state(self):
        pack,t,p=self.fixture()
        with self.assertRaises(ValueError):prepare(json.dumps(pack).encode(),b'changed',p)
        altered=copy.deepcopy(p);altered['duplication']['bytes']+=b'changed'
        with self.assertRaises(ValueError):prepare(json.dumps(pack).encode(),t,altered)
        with self.assertRaises(ValueError):prepare(json.dumps(pack).encode(),t,{})
        pack['humanDecision']='approved'
        with self.assertRaises(ValueError):prepare(json.dumps(pack).encode(),t,p)
