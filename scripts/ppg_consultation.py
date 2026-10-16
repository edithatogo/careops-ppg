"""Check recorded consultation and ownership assertions; never assign or notify."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import datetime, date
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / 'config/consultation-handoff.json'
SCOPE = ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')
TERMINAL = {'Responded', 'Accepted', 'Declined', 'Withdrawn', 'Not required'}
STATES = {'Consultation': {'Unknown', 'Pending response', 'Responded', 'Declined', 'Not required'},
          'Ownership handoff': {'Unknown', 'Proposed', 'Accepted', 'Declined', 'Withdrawn'}}


def validate(event: dict, history: list[dict] | None = None) -> list[str]:
    config = json.loads(CONFIG.read_text())
    issues = []
    for f in config['fields']:
        v = event.get(f['name'])
        if f['required'] and (not isinstance(v, str) or not v.strip()):
            issues.append('required:' + f['name'])
        if v is not None and f['type'] in ('Text', 'Note', 'DateTime', 'Choice') and not isinstance(v, str):
            issues.append('invalid_type:' + f['name'])
        if f['type'] == 'Text' and isinstance(v, str) and len(v) > 255:
            issues.append('too_long:' + f['name'])
    if issues:
        return issues
    for name, choices in config['choices'].items():
        if event.get(name) not in choices:
            issues.append('invalid:' + name)
    if event.get('RecordState') not in STATES.get(event.get('EventKind'), set()):
        issues.append('state_kind_mismatch')
    if not re.fullmatch('[0-9a-fA-F]{64}', event.get('DocumentSHA256', '')):
        issues.append('invalid:DocumentSHA256')
    required = []
    if event.get('RecordState') in TERMINAL:
        required += ['ActorName', 'OccurredOn', 'Summary', 'EvidenceReference']
    if event.get('EventKind') == 'Ownership handoff':
        required += ['FromRole']
        if event.get('RecordState') == 'Accepted':
            required += ['ParentEventUID']
    if event.get('RecordState') == 'Responded':
        required += ['ResponseSummary']
    if event.get('ConditionsState') == 'Open':
        required += ['ConditionsNotes']
    if event.get('ConditionsState') == 'Resolved':
        required += ['EvidenceReference']
    for name in required:
        if not (event.get(name) or '').strip():
            issues.append('required:' + name)
    if event.get('OccurredOn'):
        try:
            value = event['OccurredOn']
            date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            issues.append('invalid:OccurredOn')
    if history is not None and any(e.get('EventUID') == event.get('EventUID') for e in history):
        issues.append('duplicate:EventUID')
    for name in ('ParentEventUID', 'SupersedesEventUID'):
        uid = event.get(name)
        if not uid:
            continue
        if history is None:
            issues.append('history_required:' + name)
            continue
        matches = [e for e in history if e.get('EventUID') == uid]
        if uid == event.get('EventUID') or len(matches) != 1:
            issues.append('missing_ambiguous_or_self:' + name)
            continue
        parent = matches[0]
        if any(parent.get(k) != event.get(k) for k in SCOPE + ('EventKind', 'SubjectRole')):
            issues.append('scope_mismatch:' + name)
        if event.get('EventKind') == 'Ownership handoff' and parent.get('FromRole') != event.get('FromRole'):
            issues.append('role_mismatch:' + name)
        if name == 'ParentEventUID':
            allowed = {'Proposed'} if event.get('EventKind') == 'Ownership handoff' else {'Unknown', 'Pending response'}
            if parent.get('RecordState') not in allowed:
                issues.append('parent_not_pending_proposal')
            if any(e.get('SupersedesEventUID') == uid for e in history):
                issues.append('parent_superseded')
    return issues


def for_version(event: dict, case_uid: str, document_ref: str, version_ref: str,
                sha256: str, history: list[dict] | None = None) -> dict:
    issues = validate(event, history)
    matches = all(event.get(k) == v for k, v in zip(SCOPE[:3], (case_uid, document_ref, version_ref))) and str(event.get('DocumentSHA256', '')).lower() == sha256.lower()
    superseded = bool(history and any(e.get('SupersedesEventUID') == event.get('EventUID') for e in history))
    usable = matches and not issues and not superseded
    return {'validRecord': not issues, 'issues': issues, 'appliesToRequestedVersion': matches,
            'superseded': superseded, 'recordedState': event.get('RecordState') if usable else 'Unknown',
            'recordedOwnershipAcceptance': bool(usable and event.get('EventKind') == 'Ownership handoff' and event.get('RecordState') == 'Accepted'),
            'ownershipTransferred': False, 'assignmentPerformed': False, 'notificationSent': False,
            'policyApproved': False, 'notice': 'Recorded human assertion only; verify authority, evidence and version before operational reliance.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--event', type=Path, required=True)
    p.add_argument('--history', type=Path)
    p.add_argument('--case-uid', required=True)
    p.add_argument('--document-ref', required=True)
    p.add_argument('--version-ref', required=True)
    p.add_argument('--document', type=Path, required=True)
    a = p.parse_args()
    result = for_version(json.loads(a.event.read_text()), a.case_uid, a.document_ref, a.version_ref,
                         hashlib.sha256(a.document.read_bytes()).hexdigest(),
                         json.loads(a.history.read_text()) if a.history else None)
    print(json.dumps(result, indent=2))
    return 0 if result['validRecord'] and result['appliesToRequestedVersion'] and not result['superseded'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
