# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ppg_reconstruction_unpack import unpack


class ReconstructionUnpackTests(unittest.TestCase):
    def test_direct_cli_help(self):
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'ppg_reconstruction_unpack.py'
        result = subprocess.run([sys.executable, str(script), '--help'], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--chain-head', result.stdout)

    def test_unsafe_member_and_wrong_hash_leave_no_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'packet.tar'
            with tarfile.open(archive, 'w') as packet:
                item = tarfile.TarInfo('../outside')
                item.size = 1
                packet.addfile(item, io.BytesIO(b'x'))
            sha = hashlib.sha256(archive.read_bytes()).hexdigest()
            for pin in ('0' * 64, sha):
                with self.assertRaises(ValueError):
                    unpack(archive, root / 'out', pin, '0' * 64)
                self.assertFalse((root / 'out').exists())
                self.assertFalse((root / 'outside').exists())

    def test_undeclared_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'packet.tar'
            manifest = json.dumps({'files': [{'path': 'data'}]}).encode()
            with tarfile.open(archive, 'w') as packet:
                for name, data in [('reconstruction-package-v1/package-manifest.json', manifest), ('reconstruction-package-v1/data', b'x'), ('extra', b'y')]:
                    item = tarfile.TarInfo(name)
                    item.size = len(data)
                    packet.addfile(item, io.BytesIO(data))
            sha = hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch('scripts.ppg_reconstruction_unpack.audit', return_value={'extensions': 0, 'artifactsChecked': 1}):
                with self.assertRaises(ValueError):
                    unpack(archive, root / 'out', sha, '0' * 64)
            self.assertFalse((root / 'out').exists())


if __name__ == '__main__':
    unittest.main()
