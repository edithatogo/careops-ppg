import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('editions', Path(__file__).resolve().parents[1] / 'scripts/ppg_archive_editions.py')
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


class EditionTests(unittest.TestCase):
    def setUp(self):
        self.alias = 'EXAMPLE-Clin-Proc-PSQ-815-V4-06/26'
        self.row = {'sourceDocumentId':self.alias, 'DocumentUID':'11111111-1111-4111-8111-111111111111', 'Id':7}
        self.header = f'Document Number {self.alias}\nVersion No. 4.0\n'

    def test_exact_header_links_only_existing_identity_and_printed_edition(self):
        out = e.propose(self.header, [self.row])
        self.assertEqual(out['existingDocumentUID'], self.row['DocumentUID'])
        self.assertEqual(out['sourceEdition'], '4.0')
        self.assertNotIn('currency', out)

    def test_absent_duplicate_and_changed_aliases_remain_unresolved(self):
        for rows in ([], [self.row,self.row], [{**self.row,'sourceDocumentId':self.alias.replace('V4','V5')} ]):
            with self.subTest(rows=rows):
                self.assertEqual(e.propose(self.header, rows)['state'], 'unresolved')

    def test_reference_only_conflicting_header_or_version_cannot_link(self):
        for text in (f'References: {self.alias}\nVersion 4.0', self.header+'Document Number EXAMPLE-Other-V1-01/26', self.header.replace('4.0','3.0'), self.header.replace('4.0','4.0.1'), self.header+'Version 5.0'):
            with self.subTest(text=text):
                self.assertEqual(e.propose(text,[self.row])['state'],'unresolved')

    def test_invalid_identity_is_not_replaced_or_minted(self):
        for uid in ('bad','00000000-0000-0000-0000-000000000000',None):
            self.assertEqual(e.propose(self.header,[{**self.row,'DocumentUID':uid}])['state'],'unresolved')

    def test_later_first_page_footer_conflict_is_not_hidden_by_header_window(self):
        page = self.header + ('x' * 1600) + '\nVersion No.: 3.0; Effective From: 01/01/2025'
        self.assertEqual(e.propose(page, [self.row])['reason'], 'printed_editions_conflict_on_first_page')

    def test_equivalent_footer_version_does_not_create_a_conflict(self):
        page = self.header + ('x' * 1600) + '\nVersion No.: 4; Effective From: 01/01/2025'
        self.assertEqual(e.propose(page, [self.row])['state'], 'exact')


    def test_later_first_page_identifier_conflict_cannot_select_header_identity(self):
        page = self.header + ('x' * 1600) + '\nDocument Number EXAMPLE-Other-V4-06/26'
        out = e.propose(page, [self.row])
        self.assertEqual(out['state'], 'unresolved')
        self.assertEqual(out['reason'], 'document_identifiers_conflict_on_first_page')
        self.assertNotIn('existingDocumentUID', out)

    def test_repeated_first_page_identifier_remains_exact(self):
        page = self.header + ('x' * 1600) + f'\nDocument No.: {self.alias}'
        self.assertEqual(e.propose(page, [self.row])['state'], 'exact')

    def test_identifier_only_outside_header_window_does_not_establish_identity(self):
        page = 'Version No. 4.0\n' + ('x' * 1600) + f'\nDocument Number {self.alias}'
        self.assertEqual(e.propose(page, [self.row])['reason'],
                         'missing_or_ambiguous_document_header')

    def test_window_truncated_identifier_cannot_match_catalogue_prefix(self):
        prefix = self.alias.split('-V')[0]
        start = 'Version No. 4.0\n'
        label = 'Document Number '
        page = start + (' ' * (1500 - len(start) - len(label) - len(prefix)))
        page += label + self.alias
        row = {**self.row, 'sourceDocumentId': prefix}
        out = e.propose(page, [row])
        self.assertEqual(out['state'], 'unresolved')
        self.assertEqual(out['reason'], 'document_identifiers_conflict_on_first_page')
        self.assertNotIn('existingDocumentUID', out)
