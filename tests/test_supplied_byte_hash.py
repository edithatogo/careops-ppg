"""Exercise the supplied-byte Office Script using the existing Node runtime."""
from pathlib import Path
import subprocess
import unittest


class SuppliedByteHashTests(unittest.TestCase):
    def test_binary_vectors_and_fail_closed_profile(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', str(root / 'tests/test_supplied_byte_hash.mjs')],
            cwd=root, capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('cases plus mismatch and request-limit checks passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
