import copy
import unittest
from scripts.ppg_review_outcomes import report


class Outcomes(unittest.TestCase):
    def fixture(self):
        binding=dict(reviewRunId='fictional-run',documentUID='fictional-document',documentSha256='a'*64)
        return dict(schemaVersion=1,datasetKind='fictional',judgments=[dict(binding,findingRef='fictional-finding',usefulAccepted=True,falsePositive=False,judgedAt='2026-10-20T10:00:00+10:00',decisionRef='fictional://judgment'),dict(binding,findingRef='fictional-unknown',usefulAccepted=None,falsePositive=None)],decisions=[dict(binding,startedAt='2026-10-20T09:00:00+10:00',decidedAt='2026-10-20T10:00:00+10:00',decisionRef='fictional://decision')])

    def test_unknowns_are_not_zero_observations_and_input_preserved(self):
        blank=report(dict(schemaVersion=1,datasetKind=None,judgments=[],decisions=[]))
        self.assertEqual(blank['measurementStatus'],'not_measured')
        self.assertIsNone(blank['falsePositive']['fraction'])
        self.assertIsNone(blank['decisionElapsed']['medianSeconds'])
        data=self.fixture();before=copy.deepcopy(data);result=report(data)
        self.assertEqual(data,before)
        self.assertEqual(result['usefulAccepted'],dict(yesCount=1,knownJudgmentCount=1,unknownJudgmentCount=1,fraction=1))
        self.assertEqual(result['falsePositive']['fraction'],0)
        self.assertEqual(result['decisionElapsed']['medianSeconds'],3600)
        self.assertFalse(result['clinicalAuthorityVerified'])

    def test_duplicate_conflicting_unbound_and_unreferenced_observations_refused(self):
        for mutate in [lambda d:d['judgments'].append(copy.deepcopy(d['judgments'][0])),lambda d:d['judgments'][0].update(falsePositive=True),lambda d:d['judgments'][0].update(usefulAccepted='yes'),lambda d:d['judgments'][0].update(decisionRef=''),lambda d:d['decisions'][0].update(documentSha256='b'*64),lambda d:d['decisions'][0].update(decidedAt='2026-10-20T08:00:00+10:00'),lambda d:d['decisions'][0].update(startedAt='2026-10-20T09:00:00'),lambda d:d.update(datasetKind=None),lambda d:d['judgments'][0].update(datasetKind='operational')]:
            data=self.fixture();mutate(data)
            with self.assertRaises(ValueError):report(data)

    def test_zero_interval_and_missing_interval_remain_distinct(self):
        data=self.fixture();data['decisions'][0]['decidedAt']=data['decisions'][0]['startedAt'];self.assertEqual(report(data)['decisionElapsed']['medianSeconds'],0)
        data['decisions'][0]['decidedAt']=None
        result=report(data)['decisionElapsed'];self.assertEqual(result['sampleCount'],0);self.assertEqual(result['missingIntervalCount'],1);self.assertIsNone(result['medianSeconds'])
