#!/usr/bin/env python3
"""Reject organisation-specific content and operational artefacts in Git inputs."""
import argparse
import re
import subprocess
from pathlib import PurePosixPath

# These terms are policy checks only, never published source data.
BLOCKED = re.compile(r"chhhs|cairns|hinterland|queensland|healthqld|health\.qld|\bpsqu\b|\bietp\b|/Users/|/Volumes/", re.I)
SHAREPOINT = re.compile(r"https?://([^/\s\"'<>]+\.sharepoint\.com)", re.I)
FORMATS = {'.xls', '.xlsx', '.xlsb', '.xlsm', '.msg', '.eml', '.pdf', '.docx', '.zip', '.bundle', '.pem', '.pfx', '.p12', '.key'}
PRIVATE_DIRS = {'.local', 'private', 'receipts', 'outputs', 'local-only', '.flowagent'}


def check(staged=False):
    names = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
    problems = []
    for name in filter(None, names):
        path = PurePosixPath(name)
        if path.suffix.lower() in FORMATS or PRIVATE_DIRS.intersection(path.parts) or path.name.startswith('.env'):
            problems.append(name + ': operational file or credential format')
        # Inspect the index, so unstaged changes cannot mask committed content.
        data = subprocess.check_output(['git', 'show', ':' + name])
        if name == 'scripts/check_portable_content.py':
            continue  # The deny-list itself contains the blocked terms.
        if b'\0' in data:
            problems.append(name + ': unexpected binary content')
            continue
        text = data.decode('utf-8', errors='replace')
        if BLOCKED.search(name + '\n' + text):
            problems.append(name + ': organisation-specific content')
        for match in SHAREPOINT.finditer(text):
            if match.group(1).lower() not in {'example.sharepoint.com', 'contoso.sharepoint.com'}:
                problems.append(name + ': non-example SharePoint binding')
    if problems:
        raise SystemExit('Portable content check failed:\n' + '\n'.join(problems))
    print('Portable content check passed (tracked index).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Check the staged index (also the default)')
    check(parser.parse_args().staged)
