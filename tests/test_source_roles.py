import copy
import unittest
from scripts.ppg_source_roles import inventory, FIELDS, STATES


class SourceRoles(unittest.TestCase):
    def candidate(self):
        fields = {k: '' for k in FIELDS + STATES}
        fields.update(sourceCustodian=' CMO ', sourceAuthorisingOfficer='CMO')
        return dict(sourceSha256='a'*64, inputCount=1, exceptions=[],
                    rawRecords=[dict(sourceRow=2, fields=fields)],
                    operations=[dict(sourceRow=2, DocumentUID='fictional-doc')])

    def test_exact_assertions_preserved_without_equivalence_or_assignment(self):
        c = self.candidate(); before = copy.deepcopy(c); r = inventory(c)
        self.assertEqual(c, before)
        self.assertEqual(r['records'][0]['assertions']['sourceCustodian']['rawValue'], ' CMO ')
        self.assertEqual(len(r['labels']), 6)
        self.assertFalse(r['acceptedMappings']); self.assertEqual(r['assignmentsCreated'], 0)
        self.assertEqual(r['summary']['sourceServiceDirector']['missing'], 1)
        self.assertIn('author', r['absentSourceCapabilities'])

    def test_duplicate_identity_missing_field_and_partial_inputs_refused(self):
        for mutation in ['duplicate', 'missing', 'partial', 'exception']:
            c = self.candidate()
            if mutation == 'duplicate':
                c['operations'] *= 2; c['rawRecords'] *= 2; c['inputCount'] = 2
            elif mutation == 'missing': del c['rawRecords'][0]['fields']['sourceCustodian']
            elif mutation == 'partial': c['operations'] = []
            else: c['exceptions'] = ['unresolved']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): inventory(c)

    def test_nontext_not_converted_to_person_or_role(self):
        c = self.candidate(); c['rawRecords'][0]['fields']['sourceCustodian'] = 4
        r = inventory(c)
        self.assertEqual(r['summary']['sourceCustodian']['nonText'], 1)
        self.assertIsNone(next(x for x in r['labels'] if x['field']=='sourceCustodian')['confirmedHolderId'])

    def test_row_movement_preserves_stable_document_binding(self):
        c = self.candidate(); c['rawRecords'][0]['sourceRow'] = 50; c['operations'][0]['sourceRow'] = 50
        self.assertEqual(inventory(c)['records'][0]['documentUID'], 'fictional-doc')

    def test_malformed_row_and_non_scalar_assertion_refused(self):
        for place in ['operation', 'raw', 'value']:
            c = self.candidate()
            if place == 'operation': c['operations'][0]['sourceRow'] = []
            elif place == 'raw': c['rawRecords'][0]['sourceRow'] = True
            else: c['rawRecords'][0]['fields']['sourceCustodian'] = ['unstructured']
            with self.subTest(place=place), self.assertRaises(ValueError): inventory(c)
