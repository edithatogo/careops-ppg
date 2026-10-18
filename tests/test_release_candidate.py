"""Exercise the real packaging command in an isolated source repository."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class ReleaseCandidateTests(unittest.TestCase):
    def test_exact_source_generated_page_and_refusal_guards(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ['README.md', 'NOTICE.md', 'AGENTS.md']:
                (root / name).write_text('Fictional source fixture. No public licence is granted.\n')
            for name in ['scripts', 'tools/submission-package', 'templates', 'tests', '.github', 'config']:
                (root / name).mkdir(parents=True, exist_ok=True)
            for name in ['build_release_candidate.py', 'build_submission_assembler.py']:
                shutil.copyfile(ROOT / 'scripts' / name, root / 'scripts' / name)
            for name in ['page.html', 'assembler.js', 'prefill.js']:
                shutil.copyfile(ROOT / 'tools/submission-package' / name, root / 'tools/submission-package' / name)
            shutil.copyfile(ROOT / 'templates/review-package.md', root / 'templates/review-package.md')
            (root / 'tests/fixture.txt').write_text('Fictional test source\n')
            (root / 'config/fixture.json').write_text('{"fictional": true}\n')
            (root / '.github/fixture.txt').write_text('Fictional workflow source\n')
            for name in ['.careops/module.json', 'conductor/index.md', 'conductor/suite-delivery.md', '.python-version', '.node-version']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, path)
            (root / '.gitignore').write_text('.local/\n__pycache__/\n')
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args])
            git('init', '-q'); git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-qm', 'Fictional source')
            command = [sys.executable, str(root / 'scripts/build_release_candidate.py'), '--output']
            def run(name):
                return subprocess.run(command + [str(root / '.local' / name)], cwd=root, capture_output=True)
            first = run('one'); self.assertEqual(first.returncode, 0, first.stderr)
            second = run('two'); self.assertEqual(second.returncode, 0, second.stderr)
            output = root / '.local/one'; archive = output / 'careops-ppg-portable.zip'
            receipt = json.loads((output / 'package.json').read_text())
            self.assertEqual(receipt['sourceCommit'], git('rev-parse', 'HEAD').decode().strip())
            self.assertEqual(receipt['archiveSha256'], hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(archive.read_bytes(), (root / '.local/two/careops-ppg-portable.zip').read_bytes())
            self.assertFalse(receipt['nativeWrites']); self.assertFalse(receipt['publicLicenceGranted'])
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(bundle.read('PPG-submission-assembler.html'), (output / 'PPG-submission-assembler.html').read_bytes())
                self.assertEqual(bundle.read('config/fixture.json'), (root / 'config/fixture.json').read_bytes())
                self.assertEqual(bundle.read('NOTICE.md'), (root / 'NOTICE.md').read_bytes())
                self.assertEqual(bundle.read('templates/review-package.md'), (root / 'templates/review-package.md').read_bytes())
                for name in ['.careops/module.json', 'conductor/index.md', 'conductor/suite-delivery.md', '.python-version', '.node-version']:
                    self.assertEqual(bundle.read(name), (root / name).read_bytes())
                self.assertFalse(any(name.startswith('.git/') for name in bundle.namelist()))
            self.assertNotEqual(run('one').returncode, 0)
            self.assertEqual(receipt['archiveSha256'], hashlib.sha256(archive.read_bytes()).hexdigest())
            (root / 'README.md').write_text('Unreviewed edit\n')
            self.assertNotEqual(run('dirty').returncode, 0)
            self.assertFalse((root / '.local/dirty').exists())
