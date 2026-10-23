import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from scripts.ppg_template_reconciliation import reconcile

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def package(path, body, target='https://example.org/a'):
    with ZipFile(path, 'w') as z:
        z.writestr('word/document.xml', f'<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>')
        z.writestr('word/_rels/document.xml.rels', f'<Relationships><Relationship Id="r1" Target="{target}"/></Relationships>')


class ReconciliationTests(unittest.TestCase):
    def run_pair(self, a, b, target='https://example.org/a'):
        with tempfile.TemporaryDirectory() as d:
            p, q = Path(d)/'a.docx', Path(d)/'b.docx'
            package(p, a); package(q, b, target)
            before = p.read_bytes(), q.read_bytes()
            result = reconcile(p, q)
            self.assertEqual(before, (p.read_bytes(), q.read_bytes()))
            return result

    def test_combined_table_row_and_complete_accounting(self):
        r = self.run_pair('<w:p><w:r><w:t>RoleOwner</w:t></w:r></w:p><w:p/>',
                          '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Role</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Owner</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
        self.assertEqual(r['sourceRows'][0]['status'], 'proposed_exact_correspondence')
        self.assertEqual(r['sourceRows'][1]['status'], 'retained_blank_or_structural')
        self.assertTrue(r['allSourceElementsAccounted'] and r['allNativeElementsAccounted'])
        self.assertFalse(r['acceptedMapping'] or r['reviewerRecordsChanged'])

    def test_repeated_text_not_arbitrarily_assigned(self):
        p = '<w:p><w:r><w:t>Repeated</w:t></w:r></w:p>'
        r = self.run_pair(p, p+p)
        self.assertEqual(r['sourceRows'][0]['status'], 'retained_ambiguous')
        self.assertEqual(len(r['sourceRows'][0]['candidates']), 2)

    def test_link_visible_text_needs_same_target(self):
        a = '<w:p><w:r><w:t>HYPERLINK "https://example.org/a" Guidance</w:t></w:r></w:p>'
        b = '<w:p><w:hyperlink r:id="r1"><w:r><w:t>Guidance</w:t></w:r></w:hyperlink></w:p>'
        self.assertEqual(self.run_pair(a, b)['sourceRows'][0]['status'], 'proposed_exact_correspondence')
        self.assertEqual(self.run_pair(a, b, 'https://example.org/b')['sourceRows'][0]['status'], 'retained_unmatched')

    def test_changed_text_retained_not_fuzzy_matched(self):
        r = self.run_pair('<w:p><w:r><w:t>Must review</w:t></w:r></w:p>', '<w:p><w:r><w:t>May review</w:t></w:r></w:p>')
        self.assertEqual(r['sourceRows'][0]['status'], 'retained_unmatched')

    def test_partial_row_link_must_belong_to_selected_span(self):
        a = '<w:p><w:r><w:t>HYPERLINK "https://example.org/a" LabelValue</w:t></w:r></w:p>'
        b = '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Label</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc><w:tc><w:p><w:hyperlink r:id="r1"><w:r><w:t>Elsewhere</w:t></w:r></w:hyperlink></w:p></w:tc></w:tr></w:tbl>'
        self.assertEqual(self.run_pair(a, b)['sourceRows'][0]['status'], 'retained_unmatched')

    def test_same_table_distinct_paragraph_and_span_stay_ambiguous(self):
        a = '<w:p><w:r><w:t>AB</w:t></w:r></w:p>'
        cells = ''.join(f'<w:tc><w:p><w:r><w:t>{t}</w:t></w:r></w:p></w:tc>' for t in ['AB', 'A', 'B'])
        r = self.run_pair(a, '<w:tbl><w:tr>'+cells+'</w:tr></w:tbl>')
        self.assertEqual(r['sourceRows'][0]['status'], 'retained_ambiguous')
        self.assertEqual(len(r['sourceRows'][0]['candidates']), 2)

    def test_relationship_entity_declarations_refused(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d)/'a.docx', Path(d)/'b.docx'
            package(a, '<w:p/>'); package(b, '<w:p><w:r><w:t>Text</w:t></w:r></w:p>')
            with ZipFile(b) as z:
                parts = {n: z.read(n) for n in z.namelist()}
            parts['word/_rels/document.xml.rels'] = b'<!DOCTYPE Relationships [<!ENTITY x "value">]><Relationships/>'
            with ZipFile(b, 'w') as z:
                for name, content in parts.items():
                    z.writestr(name, content)
            with self.assertRaisesRegex(ValueError, 'relationship XML declarations'):
                reconcile(a, b)
