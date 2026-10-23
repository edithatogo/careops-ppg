"""Runtime handoff guards for optional integration helpers."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from qualify_atlas_adapter import require_atlas_runtime, require_repo_runtime
from ppg_atlas_adapter import AdapterError


class PythonRuntimeTests(unittest.TestCase):
    def test_atlas_source_runtime_must_be_explicitly_qualified(self):
        require_atlas_runtime({'project': {'requires-python': '>=3.15,<3.16'}})
        for metadata in ({}, {'project': {}},
                         {'project': {'requires-python': '>=3.14,<3.15'}},
                         {'project': {'requires-python': '>=3.14'}}):
            with self.subTest(metadata=metadata):
                with self.assertRaisesRegex(AdapterError, 'consumer_python315_constraint_unqualified'):
                    require_atlas_runtime(metadata)

    def test_atlas_helper_accepts_only_the_repo_python_pin_and_interpreter(self):
        version = tuple(int(part) for part in (ROOT / '.python-version').read_text().strip().split('.'))
        repo_python = (ROOT / ('.venv/Scripts/python.exe' if sys.platform == 'win32'
                               else '.venv/bin/python')).resolve()
        require_repo_runtime(version, repo_python)
        with self.assertRaisesRegex(RuntimeError, 'Requires repository Python'):
            require_repo_runtime((3, 14, 9), repo_python)
        with self.assertRaisesRegex(RuntimeError, 'Requires repository interpreter'):
            require_repo_runtime(version, ROOT / 'ATLAS/.venv/bin/python')

    def test_atlas_helper_help_starts_under_the_selected_repo_interpreter(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/qualify_atlas_adapter.py'), '--help'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('fictional Atlas -> PPG package', result.stdout)


if __name__ == '__main__':
    unittest.main()
