import io
import unittest
from zipfile import ZipFile
from scripts.ppg_word_parity import inventory, compare

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def doc(body, rels=''):
    stream = io.BytesIO()
    with ZipFile(stream, 'w') as z:
        z.writestr('word/document.xml', f'<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>')
        z.writestr('word/_rels/document.xml.rels', f'<Relationships>{rels}</Relationships>')
    return stream.getvalue()


class WordParityTests(unittest.TestCase):
    def test_split_field_instruction_and_cache(self):
        raw = doc('<w:p><w:fldChar w:fldCharType="begin"/><w:instrText>NUM</w:instrText><w:instrText>PAGES</w:instrText><w:fldChar w:fldCharType="separate"/><w:t>10</w:t><w:fldChar w:fldCharType="end"/></w:p>')
        result = inventory(raw)
        self.assertEqual(result['fields'][0]['instruction'], 'NUMPAGES')
        self.assertEqual(result['fields'][0]['cachedResult'], '10')
        self.assertFalse(result['renderedFieldsVerified'])

    def test_changed_target_not_hidden_by_same_visible_text(self):
        body = '<w:hyperlink r:id="r1"><w:r><w:t>Example</w:t></w:r></w:hyperlink>'
        a = doc(body, '<Relationship Id="r1" Target="https://example.org/a" TargetMode="External"/>')
        b = doc(body, '<Relationship Id="r1" Target="https://example.org/b" TargetMode="External"/>')
        self.assertTrue(compare(a, b)['bodyTextEqual'])
        self.assertFalse(compare(a, b)['linksEqual'])

    def test_missing_relationship_anchor_and_unclosed_field(self):
        result = inventory(doc('<w:hyperlink r:id="missing" w:anchor="absent"/><w:fldChar w:fldCharType="begin"/>'))
        self.assertFalse(result['anchors'][0]['resolved'])
        self.assertEqual(len(result['structuralExceptions']), 2)

    def test_exact_copy_does_not_claim_rendering_or_generation(self):
        raw = doc('<w:p><w:r><w:t>Human edit</w:t></w:r></w:p>')
        result = compare(raw, raw)
        self.assertTrue(result['exactBytes'])
        self.assertFalse(result['visualParityVerified'])
        self.assertFalse(result['regenerationParityVerified'])
