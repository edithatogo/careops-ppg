import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from scripts.ppg_preserve_source_bytes import preserve


class SourcePreservation(unittest.TestCase):
    def test_roundtrip_and_recreation_preserve_exact_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'fictional.doc';source.write_bytes(b'\x00\xffFICTIONAL source bytes')
            first=preserve([source],root/'one.zip');second=preserve([source],root/'two.zip')
            self.assertEqual(first['archiveSha256'],second['archiveSha256'])
            with ZipFile(root/'one.zip') as z:self.assertEqual(z.read(source.name),source.read_bytes())
    def test_existing_output_and_duplicate_names_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.doc';source.write_bytes(b'original')
            target=root/'out.zip';target.write_bytes(b'human revision')
            with self.assertRaises(FileExistsError):preserve([source],target)
            self.assertEqual(target.read_bytes(),b'human revision')
            with self.assertRaises(ValueError):preserve([source,source],root/'new.zip')
            self.assertFalse((root/'new.zip').exists())
