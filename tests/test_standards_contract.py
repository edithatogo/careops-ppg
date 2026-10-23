import unittest
from scripts.ppg_standards_contract import validate


class StandardsContract(unittest.TestCase):
    def fixture(self):
        return ([dict(frameworkEditionId='v2',status='published'),dict(frameworkEditionId='v3',status='draft')],
                [dict(requirementId='v2-1',frameworkEditionId='v2',parentRequirementId=None),dict(requirementId='v3-a',frameworkEditionId='v3',parentRequirementId=None)],
                [dict(mappingId='m',documentUID='fictional',documentVersion='1',requirementId='v3-a',rationale='Fictional applicability candidate',status='proposed',establishesCompliance=False)],[])

    def test_draft_is_not_current_obligation(self):
        args=self.fixture();self.assertTrue(validate(*args))
        args[2][0]['currentObligation']=True
        with self.assertRaises(ValueError):validate(*args)

    def test_cross_edition_parent_and_cycle_refused(self):
        args=self.fixture();args[1][0]['parentRequirementId']='v3-a'
        with self.assertRaises(ValueError):validate(*args)
        args[1][0]['parentRequirementId']='v2-1'
        with self.assertRaises(ValueError):validate(*args)

    def test_review_requires_evidence_and_crosswalk_requires_target(self):
        args=self.fixture();args[2][0]['status']='reviewed'
        with self.assertRaises(ValueError):validate(*args)
        args[2][0]['reviewEvidenceRef']='fictional://decision'
        self.assertTrue(validate(*args))
        args[3].append(dict(crosswalkId='x',fromRequirementId='v2-1',toRequirementId='missing',correspondence='uncertain',rationale='Unknown'))
        with self.assertRaises(ValueError):validate(*args)


if __name__ == '__main__':unittest.main()
