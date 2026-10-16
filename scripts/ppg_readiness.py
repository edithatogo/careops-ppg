"""Validate recorded human findings; never perform a readiness assessment."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

FINDINGS = {'Not assessed', 'Needs changes', 'Ready for decision', 'Not applicable'}
CONDITIONS = {'Unknown', 'None recorded', 'Open', 'Resolved'}


def validate(event: dict) -> list[str]:
    errors = []
    for field in ('EventUID', 'CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256'):
        if not isinstance(event.get(field), str) or not event[field].strip():
            errors.append('required:' + field)
    if not re.fullmatch(r'[0-9a-fA-F]{64}', str(event.get('DocumentSHA256', ''))):
        errors.append('invalid:DocumentSHA256')
    if event.get('Finding') not in FINDINGS:
        errors.append('invalid:Finding')
    if event.get('ConditionsState') not in CONDITIONS:
        errors.append('invalid:ConditionsState')
    if event.get('Finding') != 'Not assessed':
        for field in ('AssessorName', 'AssessedOn', 'FindingSummary', 'EvidenceReference'):
            if not isinstance(event.get(field), str) or not event[field].strip():
                errors.append('required:' + field)
        try:
            date.fromisoformat(str(event.get('AssessedOn', ''))[:10])
        except ValueError:
            errors.append('invalid:AssessedOn')
    if event.get('ConditionsState') == 'Open' and not str(event.get('ConditionsNotes') or '').strip():
        errors.append('required:ConditionsNotes')
    return errors


def for_version(event: dict, version_ref: str, sha256: str) -> dict:
    errors = validate(event)
    matches = (event.get('ReviewedVersionRef') == version_ref and
               str(event.get('DocumentSHA256', '')).lower() == sha256.lower())
    return {'validRecord': not errors, 'issues': errors,
            'appliesToRequestedVersion': matches,
            'finding': event.get('Finding') if matches and not errors else 'Not assessed',
            'conditionsState': event.get('ConditionsState') if matches and not errors else 'Unknown',
            'policyApproved': False,
            'notice': 'Human assertion for the named version only; not a policy approval or operative-currency judgement.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', type=Path, required=True)
    parser.add_argument('--version-ref', required=True)
    parser.add_argument('--document', type=Path, required=True, help='Exact reviewed bytes, read-only')
    args = parser.parse_args()
    result = for_version(json.loads(args.event.read_text()), args.version_ref,
                         hashlib.sha256(args.document.read_bytes()).hexdigest())
    print(json.dumps(result, indent=2))
    return 0 if result['validRecord'] and result['appliesToRequestedVersion'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
