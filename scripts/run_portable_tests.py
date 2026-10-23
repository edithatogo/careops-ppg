#!/usr/bin/env python3
"""Run offline Python and Node domain checks with explicit source search paths."""
import argparse
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main():
    expected = (ROOT / '.python-version').read_text().strip()
    if '.'.join(map(str, sys.version_info[:3])) != expected or sys.version_info.releaselevel != 'final':
        raise SystemExit('Use the explicitly selected Python ' + expected)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('modules', nargs='*', help='Exact unittest modules; empty runs the milestone suite')
    parser.add_argument('--python-only', action='store_true')
    args = parser.parse_args()
    if not args.modules or any('full_document' in n or 'native_case_intake' in n or 'manual_docx' in n for n in args.modules):
        sdk = subprocess.check_output(['dotnet', '--version'], cwd=ROOT / 'tools/native-document-template', text=True).strip()
        if sdk != '10.0.402':
            raise SystemExit('Select the pinned document SDK 10.0.402')
        subprocess.run(['dotnet', 'build', '--no-restore'], cwd=ROOT / 'tools/native-document-template', check=True)
    sys.path.insert(0, str(ROOT))
    for directory in ('scripts', 'tests', 'tools/lifecycle', 'tools/policy-editions'):
        sys.path.insert(0, str(ROOT / directory))
    suite = (unittest.defaultTestLoader.loadTestsFromNames(args.modules) if args.modules
             else unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_*.py'))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.testsRun or not result.wasSuccessful():
        return 1
    if not args.python_only:
        tests = sorted((ROOT / 'tests').glob('test_*.cjs')) + sorted((ROOT / 'tests').glob('test_*.mjs'))
        subprocess.run(['node', '--test', *map(str, tests)], cwd=ROOT, check=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
