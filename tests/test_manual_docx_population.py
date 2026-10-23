"""Offline preparation guards; requires the existing built .NET template utility."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DLL = ROOT / 'tools/native-document-template/bin/Debug/net10.0/TemplateBuilder.dll'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'w15': 'http://schemas.microsoft.com/office/word/2012/wordml'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


@unittest.skipUnless(shutil.which('dotnet') and DLL.exists(), 'Build existing template utility first')
class ManualPopulationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name)
        template = ROOT / 'templates/review-package.md'
        self.call(str(template), sha(template.read_bytes()), str(self.p / 'template.docx'), ok=True)
        (self.p / 'source.txt').write_text('Fictional source only.')
        self.input = {k: 'Unknown' for k in (
            'case_title CaseUID source_snapshot version intended_result source_manifest '
            'draft_links_and_changes ownership_and_implementation decision_route candidate_reference '
            'reviewer_response operative_confirmation role_acceptance review_findings decision_evidence '
            'next_action measures documentKind sourceSHA256 templateVersion outputRevision OptionalContent'
        ).split()}
        self.input.update(CaseUID='FICTIONAL-TEST', occurrenceID='TEST-OCC', documentKind='fictional-review-draft',
                          source_snapshot='https://example.invalid/LC02-operator-request-TEST-REQUEST.json',
                          source_manifest='TEST-JOB', outputRevision='TEST-JOB/revision1', OptionalContent='',
                          sourceSHA256=sha((self.p / 'source.txt').read_bytes()), includedRecordIDs=['TEST-DOC'],
                          templateSHA256=sha((self.p / 'template.docx').read_bytes()), consultation_rows=[])
        self.row = {k: 'Fictional ' + k for k in ('ComparisonSource', 'ComparisonGoverningSource',
                    'ComparisonControl', 'ComparisonChange', 'ComparisonGap')}

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *args, ok=False):
        result = subprocess.run(['dotnet', 'exec', str(DLL), *args],
                                capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def prepare(self, rows=1, name='output', same_path=False):
        self.input['comparison_rows'] = [self.row] * rows
        raw = json.dumps(self.input, sort_keys=True, separators=(',', ':')).encode()
        (self.p / 'input.json').write_bytes(raw)
        binding = {k: self.input[k] for k in ('CaseUID', 'occurrenceID', 'documentKind', 'templateSHA256')}
        binding.update(inputSHA256=sha(raw), template={'Length': str((self.p / 'template.docx').stat().st_size)},
                       sourceScope={'DocumentSHA256': self.input['sourceSHA256']}, jobId='TEST-JOB',
                       outputRevision=1, requestId='TEST-REQUEST')
        raw_binding = json.dumps(binding).encode()
        (self.p / 'binding.json').write_bytes(raw_binding)
        out = str(self.p / (name + '.docx'))
        return self.call('populate-manual', str(self.p / 'binding.json'), sha(raw_binding),
                         str(self.p / 'input.json'), str(self.p / 'template.docx'), str(self.p / 'source.txt'),
                         out, out if same_path else str(self.p / (name + '.json')))

    def test_shapes_parts_values_and_retry(self):
        for count in (0, 1, 3):
            name = 'rows' + str(count)
            r = self.prepare(count, name)
            self.assertEqual(r.returncode, 0, r.stderr)
            with zipfile.ZipFile(self.p / (name + '.docx')) as z, zipfile.ZipFile(self.p / 'template.docx') as src:
                self.assertEqual(z.namelist(), src.namelist())
                for part in z.namelist():
                    if part != 'word/document.xml':
                        self.assertEqual(z.read(part), src.read(part), part)
                root = ET.fromstring(z.read('word/document.xml'))
            ids = [e.get('{' + NS['w'] + '}val') for e in root.findall('.//w:sdtPr/w:id', NS)]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(len(root.findall('.//w15:repeatingSectionItem', NS)), count)
            aliases = [e.get('{' + NS['w'] + '}val') for e in root.findall('.//w:sdtPr/w:alias', NS)]
            self.assertNotIn('consultation_rows', aliases)
            self.assertNotIn('[OptionalContent]', ''.join(root.itertext()))
            if count:
                self.assertEqual(''.join(root.itertext()).count('Fictional ComparisonGap'), count)
            preserved = (self.p / (name + '.docx')).read_bytes()
            r = self.prepare(count, name)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('Existing output', r.stderr)
            self.assertEqual((self.p / (name + '.docx')).read_bytes(), preserved)

    def test_same_output_receipt_refused_without_orphan(self):
        result = self.prepare(same_path=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('paths must differ', result.stderr)
        self.assertFalse((self.p / 'output.docx').exists())


if __name__ == '__main__':
    unittest.main()
