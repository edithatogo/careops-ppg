# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
"""Unpack and verify a pinned private reconstruction packet; no native writes."""
import argparse
import json
import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

if __package__:
    from .ppg_reconstruction_chain_audit import audit, digest, verify_selected_index, verify_workflow_lookups, verify_requirement_corpus, verify_custody_navigation
else:
    from ppg_reconstruction_chain_audit import audit, digest, verify_selected_index, verify_workflow_lookups, verify_requirement_corpus, verify_custody_navigation


def unpack(archive, destination, archive_sha256, chain_head):
    archive, destination = Path(archive), Path(destination)
    if not re.fullmatch(r'[0-9a-f]{64}', archive_sha256) or digest(archive) != archive_sha256:
        raise ValueError('Archive hash mismatch')
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise ValueError('Destination must be a new directory in an existing parent')
    temp = Path(tempfile.mkdtemp(prefix='.reconstruction-unpack-', dir=destination.parent))
    try:
        seen = set()
        with tarfile.open(archive, 'r') as packet:
            for member in packet:
                name = member.name
                path = PurePosixPath(name)
                if (not member.isfile() or not name or '\\' in name or path.is_absolute()
                        or path.as_posix() != name or any(p in ('.', '..') for p in path.parts)
                        or name in seen):
                    raise ValueError('Unsafe or duplicate archive member')
                seen.add(name)
                output = temp.joinpath(*path.parts)
                output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with packet.extractfile(member) as src, os.fdopen(fd, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
        result = audit(temp, chain_head)
        declared = set()
        for index in range(result['extensions'] + 1):
            folder = ('reconstruction-package-v1' if index == 0 else
                      f'reconstruction-package-extension-v{index}')
            manifest_name = 'package-manifest.json' if index == 0 else 'extension-manifest.json'
            declared.add(f'{folder}/{manifest_name}')
            entries = json.loads((temp / folder / manifest_name).read_bytes())['files']
            if isinstance(entries, dict):
                entries = [{'path': name} for name in entries]
            declared.update(f"{folder}/{entry['path']}" for entry in entries)
        if seen != declared:
            raise ValueError('Archive members differ from declared chain')
        verify_selected_index(temp)
        verify_workflow_lookups(temp)
        verify_requirement_corpus(temp)
        verify_custody_navigation(temp)
        if digest(archive) != archive_sha256:
            raise ValueError('Archive changed during extraction')
        # Hard-link-free rename is safe only when a competing destination cannot
        # be replaced. Reserve the directory and move entries into it instead.
        os.mkdir(destination, 0o700)
        try:
            for child in temp.iterdir():
                child.rename(destination / child.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
        return {'members': len(seen), 'extensions': result['extensions'], 'artifacts': result['artifactsChecked'], 'nativeWrites': 0}
    finally:
        shutil.rmtree(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--archive-sha256', required=True)
    parser.add_argument('--chain-head', required=True)
    args = parser.parse_args()
    print(unpack(args.archive, args.destination, args.archive_sha256, args.chain_head))


if __name__ == '__main__':
    main()
