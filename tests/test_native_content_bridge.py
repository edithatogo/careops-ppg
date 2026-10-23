import tempfile
import unittest
import io
from pathlib import Path
from zipfile import ZipFile
from scripts.ppg_content_inventory import inventory
from scripts.ppg_native_content_bridge import bridge


def doc(body):
    stream = io.BytesIO()
    with ZipFile(stream, 'w') as package:
        package.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+body+'</w:body></w:document>')
    return stream.getvalue()


class NativeContentBridgeTests(unittest.TestCase):
    def run_pair(self, a, b, invalid=False):
        with tempfile.TemporaryDirectory() as d:
            p, q = Path(d)/'source.docx', Path(d)/'maintained.docx'
            p.write_bytes(doc(a)); q.write_bytes(doc(b))
            before = p.read_bytes(), q.read_bytes()
            sections = [dict(sourceElementId=e['elementId'], proposedModule='procedure')
                        for e in inventory(p)['elements']]
            if invalid:
                sections.append(sections[0])
            result = bridge(p, q, sections)
            self.assertEqual(before, (p.read_bytes(), q.read_bytes()))
            return result

    def test_duplicates_and_empty_nodes_remain_unresolved(self):
        p = '<w:p><w:r><w:t>Repeated</w:t></w:r></w:p>'
        result = self.run_pair(p+'<w:p/>', p+p+'<w:p/>')
        self.assertEqual(result['rows'][0]['status'], 'retained_ambiguous')
        self.assertEqual(len(result['rows'][0]['candidates']), 2)
        self.assertEqual(result['rows'][1]['status'], 'retained_structural')
        self.assertEqual(len(result['nativeRows']), 3)
        self.assertFalse(result['acceptedMapping'] or result['wordRewritten'])

    def test_field_change_not_hidden_by_equal_text(self):
        p = '<w:p><w:r><w:instrText>PAGE</w:instrText><w:t>1</w:t></w:r></w:p>'
        result = self.run_pair(p, p.replace('PAGE', 'NUMPAGES'))
        self.assertEqual(result['rows'][0]['status'], 'proposed_exact_text_location')
        self.assertFalse(result['rows'][0]['candidates'][0]['fieldInstructionsEqual'])

    def test_wrong_or_duplicate_source_version_refused(self):
        with self.assertRaisesRegex(ValueError, 'exact source version once'):
            self.run_pair('<w:p/>', '<w:p/><w:p/>', invalid=True)
