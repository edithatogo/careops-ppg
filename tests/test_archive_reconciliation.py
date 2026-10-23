import importlib.util
import hashlib
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('archive_reconciliation', Path(__file__).resolve().parents[1] / 'scripts/ppg_archive_reconciliation.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class ReconciliationTests(unittest.TestCase):
    def test_same_url_different_bytes_retained_and_duplicate_provenance_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            for name, raw in [('old.pdf', b'old edition'), ('new.pdf', b'new edition')]:
                (root / name).write_bytes(raw)
                rows.append({'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                             'format': '.pdf', 'source_url': 'https://example.invalid/policy',
                             'local_copy': name})
            out = a.reconcile([rows[0], rows[0], rows[1]], {rows[0]['sha256']}, rows, root)
            self.assertEqual(out['documentDistinctCount'], 2)
            self.assertEqual(out['missingDocumentDistinctCount'], 1)
            self.assertEqual(out['missingDocumentsWithLocalBytes'], 1)
            self.assertEqual(sorted(len(r['occurrences']) for r in out['records']), [1, 2])

    def test_changed_local_bytes_stop_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.pdf').write_bytes(b'changed')
            row = {'sha256': hashlib.sha256(b'original').hexdigest(), 'bytes': 8,
                   'format': '.pdf', 'local_copy': 'a.pdf'}
            with self.assertRaises(ValueError):
                a.reconcile([row], set(), [row], root)
