"""Offline preparation guards; requires the existing built .NET template utility."""
import hashlib
import io
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
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def add_document_paragraph(path, value):
    """Add a fictional human edit to the DOCX body without changing its other parts."""
    out = io.BytesIO()
    with zipfile.ZipFile(path, 'r') as source, zipfile.ZipFile(out, 'w') as edited:
        for info in source.infolist():
            raw = source.read(info.filename)
            if info.filename == 'word/document.xml':
                marker = b'<w:sectPr'
                assert marker in raw
                paragraph = ('<w:p><w:r><w:t>' + value + '</w:t></w:r></w:p>').encode()
                raw = raw.replace(marker, paragraph + marker, 1)
            edited.writestr(info, raw)
    Path(path).write_bytes(out.getvalue())


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
                          sourceSHA256=sha((self.p / 'source.txt').read_bytes()), templateVersion='review-template-v1',
                          includedRecordIDs=['TEST-DOC'],
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

    def prepare(self, rows=1, name='output', same_path=False, revision=1,
                job_id='TEST-JOB', request_id='TEST-REQUEST', source_uri=None):
        self.input['comparison_rows'] = [self.row] * rows
        self.input['source_snapshot'] = source_uri or (
            'https://example.invalid/LC02-operator-request-' + request_id + '.json')
        self.input['source_manifest'] = job_id
        self.input['outputRevision'] = job_id + '/revision' + str(revision)
        raw = json.dumps(self.input, sort_keys=True, separators=(',', ':')).encode()
        (self.p / 'input.json').write_bytes(raw)
        binding = {k: self.input[k] for k in ('CaseUID', 'occurrenceID', 'documentKind', 'templateSHA256')}
        binding.update(inputSHA256=sha(raw), template={'Length': str((self.p / 'template.docx').stat().st_size)},
                       sourceScope={'DocumentSHA256': self.input['sourceSHA256']}, jobId=job_id,
                       outputRevision=revision, requestId=request_id)
        raw_binding = json.dumps(binding).encode()
        (self.p / 'binding.json').write_bytes(raw_binding)
        out = str(self.p / (name + '.docx'))
        return self.call('populate-manual', str(self.p / 'binding.json'), sha(raw_binding),
                         str(self.p / 'input.json'), str(self.p / 'template.docx'), str(self.p / 'source.txt'),
                         out, out if same_path else str(self.p / (name + '.json')))

    def assert_source_snapshot_link(self, package, expected_target):
        document = ET.fromstring(package.read('word/document.xml'))
        links = document.findall('.//w:hyperlink', NS)
        self.assertEqual(len(links), 1)
        self.assertEqual(''.join(links[0].itertext()).strip(), 'Open source snapshot')
        relation_id = links[0].get('{' + R_NS + '}id')
        relationships = ET.fromstring(package.read('word/_rels/document.xml.rels'))
        matches = [relationship for relationship in relationships.findall('pkg:Relationship',
                   {'pkg': PKG_REL_NS}) if relationship.get('Id') == relation_id]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].get('TargetMode'), 'External')
        self.assertEqual(matches[0].get('Target'), expected_target)

    def test_shapes_parts_values_and_retry(self):
        for count in (0, 1, 3):
            name = 'rows' + str(count)
            r = self.prepare(count, name)
            self.assertEqual(r.returncode, 0, r.stderr)
            with zipfile.ZipFile(self.p / (name + '.docx')) as z, zipfile.ZipFile(self.p / 'template.docx') as src:
                self.assertEqual(z.namelist(), src.namelist())
                for part in z.namelist():
                    if part not in {'word/document.xml', 'word/_rels/document.xml.rels'}:
                        self.assertEqual(z.read(part), src.read(part), part)
                self.assert_source_snapshot_link(z, self.input['source_snapshot'])
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

    def test_non_https_source_link_is_refused_without_output(self):
        result = self.prepare(source_uri='http://example.invalid/LC02-operator-request-TEST-REQUEST.json')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('HTTPS source snapshot link required', result.stderr)
        self.assertFalse((self.p / 'output.docx').exists())
        self.assertFalse((self.p / 'output.json').exists())

    def test_new_revision_preserves_human_edit_identity_and_issued_history(self):
        first = self.prepare(name='draft-r1')
        self.assertEqual(first.returncode, 0, first.stderr)
        first_doc = self.p / 'draft-r1.docx'
        first_receipt = self.p / 'draft-r1.json'
        with zipfile.ZipFile(first_doc) as package:
            self.assert_source_snapshot_link(package,
                'https://example.invalid/LC02-operator-request-TEST-REQUEST.json')
        first_proof = json.loads(first_receipt.read_text())
        self.assertEqual(first_proof['CaseUID'], 'FICTIONAL-TEST')
        self.assertEqual(first_proof['occurrenceReference'], 'TEST-OCC')
        self.assertEqual(first_proof['documentKind'], 'fictional-review-draft')
        self.assertEqual(first_proof['templateSHA256'], self.input['templateSHA256'])
        self.assertEqual(first_proof['originalSourceScope']['DocumentSHA256'], self.input['sourceSHA256'])
        self.assertEqual(first_proof['outputRevision'], 1)

        # Retain a separate, explicitly fictional prior issued artifact and receipt.
        issued_doc = self.p / 'issued-history-r0.docx'
        issued_receipt = self.p / 'issued-history-r0.json'
        issued_bytes = (self.p / 'template.docx').read_bytes()
        issued_doc.write_bytes(issued_bytes)
        issued_record = {
            'fixtureState': 'FICTIONAL_ISSUED_HISTORY',
            'CaseUID': 'FICTIONAL-TEST',
            'occurrenceID': 'TEST-OCC',
            'documentKind': 'fictional-review-draft',
            'sourceSHA256': self.input['sourceSHA256'],
            'templateVersion': self.input['templateVersion'],
            'templateSHA256': self.input['templateSHA256'],
            'outputRevision': 'issued-r0',
            'includedRecordIDs': ['TEST-DOC'],
            'artifactSHA256': sha(issued_bytes),
        }
        issued_receipt.write_text(json.dumps(issued_record, sort_keys=True))
        issued_before = issued_doc.read_bytes()
        issued_receipt_before = issued_receipt.read_bytes()

        add_document_paragraph(first_doc, 'FICTIONAL HUMAN EDIT — preserve this revision')
        first_edited = first_doc.read_bytes()
        first_receipt_before = first_receipt.read_bytes()
        with zipfile.ZipFile(first_doc) as edited:
            self.assertIn(b'FICTIONAL HUMAN EDIT', edited.read('word/document.xml'))
        valid = self.call('validate-docx', str(first_doc))
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)

        # A new source snapshot and output revision produce a separate file.
        source_v2 = b'Fictional source revision two.'
        (self.p / 'source.txt').write_bytes(source_v2)
        self.input.update(
            sourceSHA256=sha(source_v2),
            source_snapshot='https://example.invalid/LC02-operator-request-TEST-REQUEST-2.json',
            source_manifest='TEST-JOB-V2',
            outputRevision='TEST-JOB-V2/revision2',
            version='fictional-v2',
            includedRecordIDs=['TEST-DOC-2'],
        )
        second = self.prepare(rows=2, name='draft-r2', revision=2,
                              job_id='TEST-JOB-V2', request_id='TEST-REQUEST-2')
        self.assertEqual(second.returncode, 0, second.stderr)
        with zipfile.ZipFile(self.p / 'draft-r2.docx') as package:
            self.assert_source_snapshot_link(package,
                'https://example.invalid/LC02-operator-request-TEST-REQUEST-2.json')

        second_proof = json.loads((self.p / 'draft-r2.json').read_text())
        self.assertEqual(second_proof['CaseUID'], first_proof['CaseUID'])
        self.assertEqual(second_proof['occurrenceReference'], first_proof['occurrenceReference'])
        self.assertEqual(second_proof['documentKind'], first_proof['documentKind'])
        self.assertNotEqual(second_proof['jobId'], first_proof['jobId'])
        self.assertNotEqual(second_proof['outputRevision'], first_proof['outputRevision'])
        self.assertNotEqual(second_proof['outputSHA256'], first_proof['outputSHA256'])
        self.assertEqual(second_proof['templateSHA256'], first_proof['templateSHA256'])
        self.assertNotEqual(second_proof['originalSourceScope']['DocumentSHA256'],
                            first_proof['originalSourceScope']['DocumentSHA256'])
        self.assertEqual(second_proof['outputRevision'], 2)
        populated = {entry['field']: entry.get('value') for entry in second_proof['populatedFields']}
        self.assertEqual(populated['sourceSHA256'], self.input['sourceSHA256'])
        self.assertEqual(populated['templateVersion'], 'review-template-v1')
        self.assertEqual(populated['outputRevision'], 'TEST-JOB-V2/revision2')
        self.assertEqual(populated['includedRecordIDs'], 'TEST-DOC-2')
        with zipfile.ZipFile(self.p / 'draft-r2.docx') as current:
            body = current.read('word/document.xml')
        self.assertIn(b'TEST-DOC-2', body)
        self.assertNotIn(b'FICTIONAL HUMAN EDIT', body)

        self.assertEqual(first_doc.read_bytes(), first_edited)
        self.assertEqual(first_receipt.read_bytes(), first_receipt_before)
        self.assertEqual(issued_doc.read_bytes(), issued_before)
        self.assertEqual(issued_receipt.read_bytes(), issued_receipt_before)


if __name__ == '__main__':
    unittest.main()
