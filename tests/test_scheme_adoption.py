# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from scripts.ppg_scheme_adoption import adoption_action, project_scheme
from scripts.ppg_accreditation_contract import REQUIREMENT_KINDS


class SchemeAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.contract = dict(contractVersion=2, graphContractVersion=1,
                             requirementKinds=sorted(REQUIREMENT_KINDS),
                             ratingVocabulary=dict(universalScore=False),
                             promotionRules={k:False for k in ['automaticAcceptance','crosswalkTransfersAcceptance',
                             'scopeInheritance','nativeWritesImplemented','emailEnabled','premiumConnectors']})
        self.vocabulary = dict(schemaVersion=1, authorities=[dict(authorityKey='publisher'),dict(authorityKey='assessor')],
            schemes=[dict(schemeKey='fixture-scheme',schemeAuthorityKey='publisher',assessmentDecisionAuthorityKey='assessor',frameworkKeys=['fixture-framework'])],
            ratingVocabularies=[dict(vocabularyKey='fixture-ratings',vocabularyVersion='1',schemeKey='fixture-scheme',frameworkKey='fixture-framework',use='external-accrediting-assessor-rating-only',values=['Fixture outcome'],source=dict(publicationKey='fixture-publication',captureKey='fixture-capture',sha256='a'*64,locator='Fictional table',editionKey='fixture-edition'))],
            internalReviewStates=dict(externalRatingCopy=False,ratingVocabularyKey=None,applicability=['Unknown','Applicable','Not applicable'],outcome=['Unknown','Human-recorded']),
            invariants={k:True for k in ['ratingDoesNotImplyAccreditationDecision','evidencePresenceDoesNotAssignRating','mappingDoesNotAssignRating','noUniversalScore','unknownRemainsExplicit']})

    def test_independent_rating_and_cycle_free_configuration(self):
        before=copy.deepcopy((self.contract,self.vocabulary))
        a=project_scheme('fixture-framework',self.contract,self.vocabulary,scheme_key='fixture-scheme')
        b=project_scheme('fixture-quality',self.contract,self.vocabulary)
        self.assertEqual(len(a['payload']['ratingVocabularies']),1)
        self.assertEqual(b['payload']['ratingVocabularies'],[])
        self.assertIsNone(b['payload']['SchemeKey'])
        self.assertFalse(a['payload']['accreditationCycleRequired'])
        self.assertEqual(before,(self.contract,self.vocabulary))
        with self.assertRaises(ValueError):project_scheme('wrong-framework',self.contract,self.vocabulary,scheme_key='fixture-scheme')

    def test_replay_and_conflicting_configuration(self):
        a=project_scheme('fixture-framework',self.contract,self.vocabulary,scheme_key='fixture-scheme')
        self.assertEqual(adoption_action(None,a),'create')
        self.assertEqual(adoption_action(copy.deepcopy(a),a),'reuse')
        changed=copy.deepcopy(a);changed['payload']['automaticAward']=True
        with self.assertRaises(ValueError):adoption_action(a,changed)
        with self.assertRaises(ValueError):adoption_action(changed,a)
