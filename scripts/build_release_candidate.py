#!/usr/bin/env python3
"""Bundle exact portable source and the existing assembler without native access."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from build_submission_assembler import build

ROOT = Path(__file__).resolve().parents[1]


def package(output):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT)
    if git('status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('Commit the reviewed source before packaging.')
    revision = git('rev-parse', 'HEAD').decode().strip()
    epoch = int(git('show', '-s', '--format=%ct', 'HEAD'))
    output.mkdir(parents=True, exist_ok=False)
    archive = output / 'careops-ppg-portable.zip'
    subprocess.run(['git', 'archive', '--format=zip', '--output', str(archive.resolve()),
                    revision, 'README.md', 'NOTICE.md', 'AGENTS.md', '.github', 'config', 'scripts', 'tools', 'templates', 'tests'],
                   cwd=ROOT, check=True)
    page = output / 'PPG-submission-assembler.html'
    build(page)
    with zipfile.ZipFile(archive, 'a') as bundle:
        if page.name in bundle.namelist():
            raise ValueError('Generated artifact identity already exists in source.')
        info = zipfile.ZipInfo(page.name, datetime.fromtimestamp(epoch, timezone.utc).timetuple()[:6])
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        bundle.writestr(info, page.read_bytes())
    receipt = {'sourceCommit': revision,
               'archiveSha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
               'assemblerSha256': hashlib.sha256(page.read_bytes()).hexdigest(),
               'nativeWrites': False, 'publicLicenceGranted': False,
               'scope': 'Portable source and existing fallback assembler; no native qualification or content approval.'}
    (output / 'package.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    package(parser.parse_args().output.resolve())
