"""Offline generated-document handoff to the retained real packaging kernel."""
import base64
import copy
import io
import json
from pathlib import Path
import subprocess
import unittest
import zipfile

from test_generation_contract import fixture, g

ROOT = Path(__file__).resolve().parents[1]


def package_fixture():
    values = list(fixture())
    baseline = b'FICTIONAL retained baseline bytes'
    source = values[0]['sourceBindings']['sources'][0]
    source['sha256'] = values[0]['sourceSHA256'] = g.sha(baseline)
    source['nativePin']['Length'] = len(baseline)
    values[1]['requestSHA256'] = g.fingerprint(values[0])
    values[5]['requestSHA256'] = g.fingerprint(values[0])
    values[5]['sourceBindingsBefore'] = copy.deepcopy(values[0]['sourceBindings'])
    values[5]['sourceBindingsAfter'] = copy.deepcopy(values[0]['sourceBindings'])
    selection = dict(schemaVersion=1, kind='existing-case-artifact-selection',
                     **copy.deepcopy(values[0]['sourceBindings']))
    values[1] = json.dumps(values[1]).encode()
    return values, baseline, json.dumps(selection).encode()


def prepare(values, baseline, selection):
    return g.prepare_package_inputs(*values, baseline, selection,
                                    'job-fictional-generated-1', '2026-10-18T00:00:00Z')


class GenerationPackageTests(unittest.TestCase):
    def test_actual_kernel_and_independent_zip_reader_preserve_all_four_roles(self):
        values, baseline, selection = package_fixture()
        prepared = prepare(values, baseline, selection)
        result = subprocess.run(['node', '-e', """
const fs=require('node:fs'), vm=require('node:vm');
const {stripTypeScriptTypes}=require('node:module');
const p=JSON.parse(fs.readFileSync(0,'utf8')),ctx={};vm.createContext(ctx);
vm.runInContext(stripTypeScriptTypes(fs.readFileSync('scripts/ppg_cloud_package.ts','utf8')),ctx);
process.stdout.write(ctx.packageJob(JSON.stringify(p.job),JSON.stringify(p.members)));
"""], cwd=ROOT, input=json.dumps(prepared), text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(result.stdout)
        raw = base64.b64decode(actual['zipBase64'])
        self.assertEqual(actual['packageSHA256'], g.sha(raw))
        self.assertEqual(actual['memberCount'], 5)
        with zipfile.ZipFile(io.BytesIO(raw)) as package:
            self.assertIsNone(package.testzip())
            expected = {'sources/recorded-baseline.zip': baseline,
                        'drafts/generated.docx': values[4],
                        'generation/generation-receipt.json': values[1],
                        'selection/selection.json': selection}
            self.assertEqual(set(package.namelist()), set(expected) | {'package-provenance.json'})
            for path, content in expected.items():
                self.assertEqual(package.read(path), content)
            provenance = json.loads(package.read('package-provenance.json'))
            binding = provenance['job']['generationBinding']
            self.assertEqual(binding['receiptSHA256'], g.sha(values[1]))
            self.assertEqual(binding['occurrenceKey'], values[0]['occurrenceKey'])
            self.assertEqual(binding['template'], values[0]['template'])
            self.assertEqual(binding['invocation'], values[5]['invocation'])
            self.assertTrue(binding['productionQualificationRequired'])
            self.assertFalse(provenance['policyApproved'])
        self.assertEqual({m['role'] for m in prepared['job']['members']},
                         set(binding['requiredPackageRoles']))
        self.assertTrue(prepared['productionQualificationRequired'])
        self.assertFalse(prepared['nativeWrites'])

    def test_changed_selection_baseline_or_generated_document_refuses(self):
        for change, code in [('selection', 'selection_generation_binding_mismatch'),
                             ('baseline', 'package_baseline_changed'),
                             ('length', 'package_baseline_length_changed'),
                             ('output', 'generated_output_changed')]:
            values, baseline, selection = package_fixture()
            if change == 'selection':
                selected = json.loads(selection)
                selected['caseBinding']['odata.etag'] = '"changed"'
                selection = json.dumps(selected).encode()
            elif change == 'baseline':
                baseline += b'edited'
            elif change == 'output':
                values[4] += b'human edit'
            else:
                values[0]['sourceBindings']['sources'][0]['nativePin']['Length'] += 1
                receipt = json.loads(values[1]); receipt['requestSHA256'] = g.fingerprint(values[0])
                values[1] = json.dumps(receipt).encode()
                values[5]['requestSHA256'] = g.fingerprint(values[0])
                for key in ('sourceBindingsBefore', 'sourceBindingsAfter'):
                    values[5][key] = copy.deepcopy(values[0]['sourceBindings'])
                selection = json.dumps(dict(schemaVersion=1, kind='existing-case-artifact-selection',
                                            **values[0]['sourceBindings'])).encode()
            with self.subTest(change=change), self.assertRaisesRegex(g.GenerationError, code):
                prepare(values, baseline, selection)

    def test_duplicate_selection_json_and_invalid_job_time_are_rejected(self):
        values, baseline, selection = package_fixture()
        with self.assertRaisesRegex(g.GenerationError, 'duplicate_json_key'):
            prepare(values, baseline, b'{"schemaVersion":1,"schemaVersion":1}')
        for job, date in [('bad job', '2026-10-18T00:00:00Z'),
                          ('job-fictional', '2026-02-30T00:00:00Z')]:
            with self.subTest(job=job, date=date), self.assertRaises(g.GenerationError):
                g.prepare_package_inputs(*values, baseline, selection, job, date)

    def test_inputs_remain_unchanged_and_repeat_is_deterministic(self):
        values, baseline, selection = package_fixture()
        original = copy.deepcopy(values)
        self.assertEqual(prepare(values, baseline, selection), prepare(values, baseline, selection))
        self.assertEqual(values, original)
