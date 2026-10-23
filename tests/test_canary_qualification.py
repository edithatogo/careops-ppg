"""Run the actual workflow receipt; failures and missing evidence never qualify."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGES = ['source', 'policy', 'python', 'node', 'bootstrap', 'resolve', 'qualification']


class CanaryQualificationTests(unittest.TestCase):
    def test_canary_uses_only_the_exact_qualified_python_pin(self):
        workflow = (ROOT / '.github/workflows/development-canary.yml').read_text()
        python_pins = [line.split(':', 1)[1].strip() for line in workflow.splitlines()
                       if line.strip().startswith('python-version:')]
        self.assertEqual(python_pins, ["'3.15.1'"])
        self.assertNotIn('allow-prereleases:', workflow)
        self.assertNotIn('steps.discover.outputs.version', workflow)
        self.assertIn('global-json-file: tools/native-document-template/global.json', workflow)
        self.assertIn('dotnet restore --locked-mode', workflow)
        self.assertIn('scripts/run_portable_tests.py --python-only', workflow)
        self.assertNotIn('unittest discover -s tests', workflow)
        self.assertIn('requirements-xlsb.lock', workflow)
        self.assertIn('--require-hashes --only-binary=:all: -r requirements-xlsb.lock', workflow)
        self.assertIn('m.version("pyxlsb") == "1.0.10"', workflow)
        self.assertIn('pip_audit --disable-pip --no-deps -r requirements-xlsb.lock', workflow)

    def test_python_checks_use_the_repo_local_verified_interpreter(self):
        for relative in ['.github/workflows/development-canary.yml',
                         '.github/workflows/package-release.yml',
                         '.github/workflows/security.yml']:
            workflow = (ROOT / relative).read_text()
            self.assertNotRegex(workflow, r'(?m)^\s+python3\s')
            self.assertNotRegex(workflow, r'(?m)^\s+python (?!-m venv )')
            self.assertIn("assert sys.version_info[:3] == (3, 15, 1)", workflow)

    def test_repository_commit_hook_uses_repo_local_python(self):
        hook_path = ROOT / '.githooks/pre-commit'
        if not hook_path.exists():
            self.skipTest('Portable consumer packages intentionally omit repository-only Git hooks.')
        hook = hook_path.read_text()
        self.assertIn('repo_python=.venv/bin/python', hook)
        self.assertIn('sys.version_info[:3] == (3, 15, 1)', hook)
        self.assertNotIn('python3 ', hook)

    def test_actual_receipt_preserves_failures_and_requires_bound_runtime_evidence(self):
        workflow = (ROOT / '.github/workflows/development-canary.yml').read_text()
        step = workflow.split('      - name: Record actual tool qualification outcomes\n', 1)[1].split('\n      - ', 1)[0]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1]).replace('.venv/bin/python', shlex.quote(sys.executable), 1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); evidence = root / '.local/tool-canary'; evidence.mkdir(parents=True)
            for pin in ['.python-version', '.node-version']:
                (root / pin).write_text((ROOT / pin).read_text())
            def execute(outcomes, expect_failure=False):
                env = dict(os.environ, GITHUB_SHA='a' * 40, **{name.upper() + '_OUTCOME': outcomes.get(name, 'success') for name in STAGES})
                result = subprocess.run(['/bin/bash', '-euc', script], cwd=root, env=env, check=False, capture_output=True)
                self.assertEqual(result.returncode != 0, expect_failure, result.stderr.decode())
                receipt = json.loads((evidence / 'qualification.json').read_text())
                self.assertFalse(receipt['promoted']); self.assertFalse(receipt['nativeWrites'])
                return receipt
            for position, stage in enumerate(STAGES):
                outcomes = {name: 'success' if i < position else 'failure' if i == position else 'skipped' for i, name in enumerate(STAGES)}
                receipt = execute(outcomes)
                self.assertEqual(receipt['stages'], outcomes)
                self.assertEqual(receipt['failedStage'], stage)
                self.assertEqual(receipt['state'], 'setup-blocked' if position < 5 else 'executed-failure')
            self.assertEqual(execute({'qualification': 'cancelled'})['state'], 'cancelled')
            self.assertEqual(execute({'qualification': 'skipped'})['state'], 'not-executed')
            self.assertEqual(execute({}, expect_failure=True)['state'], 'evidence-mismatch')
            lock = b'fictional==1.0 --hash=sha256:fixture\n'
            (evidence / 'requirements.lock').write_bytes(lock)
            (evidence / 'candidate.json').write_text(json.dumps({'lockSha256': hashlib.sha256(lock).hexdigest()}))
            for name, value in [('python-version', 'Python ' + (ROOT / '.python-version').read_text().strip() + ' (fixture)'), ('node-version', 'v' + (ROOT / '.node-version').read_text().strip()), ('tool-python-version', 'Python 3.15.1 (fixture)')]:
                (evidence / (name + '.txt')).write_text(value)
            self.assertEqual(execute({})['state'], 'qualified-tool-candidate')
            for old_runtime in ['3.13.0', '3.14.8']:
                (evidence / 'tool-python-version.txt').write_text('Python ' + old_runtime + ' (fixture)')
                self.assertEqual(execute({}, expect_failure=True)['state'], 'runtime-mismatch')
            (evidence / 'candidate.json').write_text('{broken')
            self.assertEqual(execute({}, expect_failure=True)['state'], 'evidence-invalid')
