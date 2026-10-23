import copy
import hashlib
import unittest
from scripts.ppg_interim_review import build


class InterimReviewTests(unittest.TestCase):
    def setUp(self):
        self.inventory = {'sourceSha256': 'inspection', 'elements': [
            {'elementId': 'p1', 'sourceLocator': 'word/document.xml/p1',
             'kind': 'paragraph', 'text': 'Purpose'}], 'parts': []}
        self.pack = {'historicalStructuredInventory': self.inventory,
                     'preparation': {'subject': {'documentUID': 'fictional', 'verifiedSource': False}},
                     'humanDecision': None, 'reviewerText': 'keep this edit'}
        self.modules = {'moduleVersion': '1', 'status': 'proposed', 'modules': [
            {'key': 'core.purpose', 'headings': ['Purpose']},
            {'key': 'evidence.unmapped', 'headings': []}]}
        self.template = {'sourceSha256': hashlib.sha256(b'template').hexdigest(),
                         'elements': [{'elementId': 'template1', 'disposition': 'retained_unmapped'}]}
        self.args = [self.pack, self.inventory, self.modules, self.template,
                     b'source', b'template', hashlib.sha256(b'source').hexdigest()]

    def test_preserves_inputs_and_separates_eligibility_from_authority(self):
        before = copy.deepcopy(self.args)
        result = build(*self.args)
        self.assertEqual(before, self.args)
        self.assertEqual(result['frozenPack'], self.pack)
        self.assertTrue(result['developmentEligible'])
        self.assertFalse(result['requestedEditionVerified'])
        self.assertFalse(result['publicationAuthorised'])
        self.assertEqual(result['structuredCapture']['elementCount'], 1)
        self.assertEqual(result['templateElementAccounting'], self.template)
        result['frozenPack']['reviewerText'] = 'changed copy'
        self.assertEqual(self.pack['reviewerText'], 'keep this edit')

    def test_refuses_changed_original_template_and_inspection(self):
        for index, value in [(4, b'wrong source'), (5, b'wrong template'),
                             (1, {**self.inventory, 'sourceSha256': 'wrong inspection'})]:
            args = copy.deepcopy(self.args)
            args[index] = value
            with self.assertRaises(ValueError):
                build(*args)
