"""Validate version-specific human assurance records; never decide or publish."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'assurance-recording.json'
PARENTS = {'Decision': {'Decision'}, 'Publication': {'Decision'},
           'Implementation': {'Decision', 'Publication', 'Implementation'},
           'Verification': {'Implementation'}}


def validate(event: dict, history: list[dict] | None = None,
             readiness: list[dict] | None = None) -> list[str]:
    config = json.loads(CONFIG.read_text())
    issues = []
    for field in config['fields']:
        name = field['name']
        value = event.get(name)
        if field['required'] and (not isinstance(value, str) or not value.strip()):
            issues.append('required:' + name)
        if value is not None and field['type'] in ('Text', 'Note', 'DateTime', 'Choice') and not isinstance(value, str):
            issues.append('invalid_type:' + name)
        if field['type'] == 'Text' and isinstance(value, str) and len(value) > 255:
            issues.append('too_long:' + name)
    if issues:
        return issues
    for name, choices in config['choices'].items():
        if event.get(name) not in choices:
            issues.append('invalid:' + name)
    if event.get('Stage') != 'Decision' and event.get('DecisionOutcome') != 'Unknown':
        issues.append('unexpected:DecisionOutcome')
    if event.get('Stage') != 'Verification' and event.get('VerificationResult') != 'Not verified':
        issues.append('unexpected:VerificationResult')
    if not re.fullmatch('[0-9a-fA-F]{64}', event.get('DocumentSHA256', '')):
        issues.append('invalid:DocumentSHA256')
    present = lambda field: bool((event.get(field) or '').strip())
    if event.get('ConditionsState') == 'Open' and not present('ConditionsNotes'):
        issues.append('required:ConditionsNotes')
    if event.get('RecordState') in ('Recorded', 'Not applicable'):
        required = ['ActorName', 'OccurredOn', 'Summary', 'EvidenceReference']
        if event['RecordState'] == 'Recorded':
            required += {'Decision': ['DecisionReference'],
                         'Publication': ['ParentEventUID', 'PublicationURL', 'PublishedVersionRef'],
                         'Implementation': ['ParentEventUID', 'ImplementationActions'],
                         'Verification': ['ParentEventUID', 'VerificationMethod']}.get(event.get('Stage'), [])
            if event.get('Stage') == 'Decision' and event.get('DecisionOutcome') == 'Unknown':
                issues.append('required:DecisionOutcome')
            if event.get('Stage') == 'Verification' and event.get('VerificationResult') == 'Not verified':
                issues.append('required:VerificationResult')
        for field in required:
            if not present(field):
                issues.append('required:' + field)
        if present('OccurredOn'):
            try:
                value = event['OccurredOn']
                date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                issues.append('invalid:OccurredOn')
        if event.get('Stage') == 'Publication' and event['RecordState'] == 'Recorded':
            u = urlparse(event.get('PublicationURL', ''))
            if u.scheme not in ('https', 'http') or not u.netloc:
                issues.append('invalid:PublicationURL')
    if history is not None:
        matches = [e for e in history if e.get('EventUID') == event.get('EventUID')]
        if matches:
            issues.append('duplicate:EventUID')
        for field in ('ParentEventUID', 'SupersedesEventUID'):
            uid = event.get(field)
            if not uid:
                continue
            parents = [e for e in history if e.get('EventUID') == uid]
            if len(parents) != 1:
                issues.append('missing_or_ambiguous:' + field)
                continue
            parent = parents[0]
            if any(parent.get(k) != event.get(k) for k in ('CaseUID', 'DocumentReference')):
                issues.append('identity_mismatch:' + field)
            if field == 'ParentEventUID':
                if any(parent.get(k) != event.get(k) for k in ('ReviewedVersionRef', 'DocumentSHA256')):
                    issues.append('version_mismatch:' + field)
                if parent.get('Stage') not in PARENTS.get(event.get('Stage'), set()):
                    issues.append('stage_mismatch:' + field)
                if event.get('RecordState') == 'Recorded' and parent.get('RecordState') != 'Recorded':
                    issues.append('parent_evidence_pending')
    if event.get('ReadinessEventUID') and readiness is not None:
        related = [e for e in readiness if e.get('EventUID') == event['ReadinessEventUID']]
        if len(related) != 1 or any(related[0].get(k) != event.get(k) for k in
                                  ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')):
            issues.append('readiness_identity_or_version_mismatch')
    return issues


def for_version(event: dict, case_uid: str, document_ref: str,
                version_ref: str, sha256: str, history: list[dict] | None = None,
                readiness: list[dict] | None = None) -> dict:
    errors = validate(event, history, readiness)
    matches = (event.get('CaseUID') == case_uid and event.get('DocumentReference') == document_ref and
               event.get('ReviewedVersionRef') == version_ref and
               str(event.get('DocumentSHA256', '')).lower() == sha256.lower())
    applicable = matches and not errors
    return {'validRecord': not errors, 'issues': errors, 'appliesToRequestedVersion': matches,
            'stage': event.get('Stage'), 'recordState': event.get('RecordState') if applicable else 'Unknown',
            'recordedDecisionOutcome': event.get('DecisionOutcome') if applicable and event.get('RecordState') == 'Recorded' and event.get('Stage') == 'Decision' else 'Unknown',
            'recordedVerificationResult': event.get('VerificationResult') if applicable and event.get('RecordState') == 'Recorded' and event.get('Stage') == 'Verification' else 'Not verified',
            'policyApproved': False, 'publicationPerformed': False, 'implementationPerformed': False,
            'notice': 'Recorded assertion for this exact case/document/version only. No assessment, authority or completed action is inferred.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--event', type=Path, required=True)
    p.add_argument('--history', type=Path)
    p.add_argument('--readiness', type=Path)
    p.add_argument('--case-uid', required=True)
    p.add_argument('--document-ref', required=True)
    p.add_argument('--version-ref', required=True)
    p.add_argument('--document', type=Path, required=True)
    a = p.parse_args()
    event = json.loads(a.event.read_text())
    result = for_version(event, a.case_uid, a.document_ref, a.version_ref,
                         hashlib.sha256(a.document.read_bytes()).hexdigest(),
                         json.loads(a.history.read_text()) if a.history else None,
                         json.loads(a.readiness.read_text()) if a.readiness else None)
    print(json.dumps(result, indent=2))
    return 0 if result['validRecord'] and result['appliesToRequestedVersion'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
