import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from scripts.ppg_content_inventory import inventory, save_inventory


class ContentInventory(unittest.TestCase):
    def test_preserves_all_parts_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'fictional.docx'
            with ZipFile(source, 'w') as package:
                package.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:ins><w:r><w:t>Example</w:t></w:r></w:ins></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
                package.writestr('word/media/image.png', b'fictional-image')
                package.writestr('customXml/item1.xml', '<retained/>')
            before = source.read_bytes()
            output = Path(directory)/'output'
            result = save_inventory(source, output)
            self.assertEqual(len(result['parts']), 3)
            self.assertEqual(len(result['elements']), 2)
            self.assertTrue(result['elements'][0]['containsRevisions'])
            self.assertFalse(result['contentMappingComplete'])
            self.assertEqual((output/'original.docx').read_bytes(), before)
            with self.assertRaises(FileExistsError): save_inventory(source, output)
            self.assertEqual(source.read_bytes(), before)

    def test_non_ooxml_is_retained_not_silently_extracted(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'fictional.doc'; source.write_bytes(b'legacy example')
            result = inventory(source)
            self.assertEqual(result['elements'][0]['disposition'], 'retained_unmapped')
            self.assertTrue(result['warnings'])


if __name__ == '__main__':
    unittest.main()
