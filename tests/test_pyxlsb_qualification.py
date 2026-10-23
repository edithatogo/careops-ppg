"""Read-only smoke coverage for the optional pyxlsb parser on Python 3.15."""
import base64
import hashlib
from pathlib import Path
import tempfile
import unittest

FIXTURE = Path(__file__).parent / 'fixtures/pyxlsb-test1-v2.2.3.b64'
FIXTURE_SHA256 = 'ab0c0a28a93a9174a4052446f61c21a626f7411f269e72af1d258569f8b533c2'


class PyxlsbQualificationTests(unittest.TestCase):
    def test_opens_workbook_and_reads_cached_cells_without_mutation(self):
        try:
            from pyxlsb import open_workbook
        except ImportError:
            self.skipTest('Optional pyxlsb dependency is not installed; the isolated XLSB canary runs this test.')

        encoded = FIXTURE.read_bytes()
        workbook_bytes = base64.b64decode(encoded, validate=True)
        self.assertEqual(hashlib.sha256(workbook_bytes).hexdigest(), FIXTURE_SHA256)
        with tempfile.TemporaryDirectory() as directory:
            workbook_path = Path(directory) / 'fixture.xlsb'
            workbook_path.write_bytes(workbook_bytes)
            before = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
            with open_workbook(str(workbook_path)) as workbook:
                self.assertEqual(workbook.sheets, ['Sheet1', 'Sheet2', 'Sheet3', 'Sheet4'])
                with workbook.get_sheet('Sheet1') as sheet:
                    self.assertEqual((sheet.dimension.h, sheet.dimension.w), (8, 5))
                    rows = list(sheet.rows())
                with workbook.get_sheet('Sheet4') as sheet:
                    text_rows = list(sheet.rows())
            self.assertEqual([cell.v for cell in rows[0]], [None, 'A', 'B', 'C', 'D'])
            self.assertEqual([cell.v for cell in rows[1]], [36528.0, 0.980268513777,
                                                             3.68573087906, -0.364216805298,
                                                             -1.15973806169])
            self.assertEqual([cell.v for cell in text_rows[-1]], ['i2', 'b', 'y'])
            self.assertEqual(hashlib.sha256(workbook_path.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
