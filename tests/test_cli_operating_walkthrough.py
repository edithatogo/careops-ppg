"""Exercise the documented offline route using actual child processes."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / '.venv/bin/python'
EXAMPLE = ROOT / 'templates/operator-usability/cli-walkthrough'


class OperatingWalkthrough(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([str(PYTHON), str(ROOT / 'scripts/ppg_workbench.py'),
                               *map(str, args)], cwd=ROOT, text=True,
                              capture_output=True, timeout=30)

    def test_actual_prepare_report_resume_and_changed_output_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = json.loads((EXAMPLE / 'plan.json').read_text())
            # Substitute only example paths; the committed plan remains immutable.
            for step in plan['steps']:
                step['arguments'] = [str(ROOT / value) if value.startswith('templates/')
                                     else str(root / value.removeprefix('.local/cli-walkthrough/'))
                                     if value.startswith('.local/cli-walkthrough/') else value
                                     for value in step['arguments']]
                step['outputs'] = [str(root / Path(value).name) for value in step['outputs']]
            plan_path = root / 'plan.json'
            plan_path.write_text(json.dumps(plan))
            journal = root / 'run.jsonl'
            original = (EXAMPLE / 'source.txt').read_bytes()
            result = self.cli('--plan', plan_path, '--state', journal)
            self.assertEqual(result.returncode, 0, result.stderr)
            events = [json.loads(line) for line in journal.read_text().splitlines()]
            self.assertEqual(events[0]['totalSteps'], 2)
            self.assertEqual([row['event'] for row in events],
                             ['created', 'started', 'completed', 'started', 'completed'])
            manifest = json.loads((root / 'prepared/manifest.json').read_text())
            copy = root / 'prepared/sources' / manifest['sources'][0]['name']
            self.assertEqual(copy.read_bytes(), original)
            self.assertEqual((EXAMPLE / 'source.txt').read_bytes(), original)
            self.assertFalse(manifest['conversationalRetrievalQualified'])
            before = journal.read_bytes()
            report_before = (root / 'source-status.md').read_bytes()
            resumed = self.cli('--plan', plan_path, '--state', journal, '--resume')
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertIn('all 2 stages already complete', resumed.stderr)
            self.assertEqual(journal.read_bytes(), before)
            self.assertEqual((root / 'source-status.md').read_bytes(), report_before)
            status = self.cli('assurance-report', '--input', journal,
                              '--output', root / 'run-status.md')
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn('| Successful | 1 |', (root / 'run-status.md').read_text())
            # A completed first stage is insufficient evidence for the whole plan.
            partial = root / 'partial.jsonl'
            partial.write_text(''.join(json.dumps(row) + '\n' for row in events[:3]))
            status = self.cli('assurance-report', '--input', partial,
                              '--output', root / 'partial-status.md')
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn('| Incomplete | 1 |', (root / 'partial-status.md').read_text())
            copy.write_bytes(b'FICTIONAL deliberate edit\n')
            edited_hash = hashlib.sha256(copy.read_bytes()).hexdigest()
            refused = self.cli('--plan', plan_path, '--state', journal, '--resume')
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn('changed or disappeared', refused.stderr)
            self.assertEqual(hashlib.sha256(copy.read_bytes()).hexdigest(), edited_hash)
            self.assertEqual(journal.read_bytes(), before)

    def test_actual_single_step_receipt_and_missing_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for missing in (False, True):
                receipt = root / ('missing.jsonl' if missing else 'success.jsonl')
                output = root / ('missing' if missing else 'prepared')
                job = root / 'absent.json' if missing else EXAMPLE / 'job.json'
                result = self.cli('--receipt', receipt, 'prepare-sources', '--job', job,
                                  '--input', EXAMPLE, '--output', output)
                self.assertEqual(result.returncode, 1 if missing else 0, result.stderr)
                status = root / ('missing-status.md' if missing else 'success-status.md')
                report = self.cli('assurance-report', '--input', receipt, '--output', status)
                self.assertEqual(report.returncode, 0, report.stderr)
                self.assertIn('| Incomplete | 1 |' if missing else '| Successful | 1 |', status.read_text())
                self.assertIn('Human acceptance: **not assessed**', status.read_text())
                if missing:
                    self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
