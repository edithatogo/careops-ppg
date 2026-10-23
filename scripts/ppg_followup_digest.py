#!/usr/bin/env python3
"""Append-only local follow-up recording and send-free manual digest preview."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from ppg_consultation import for_version, SCOPE


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError('UTC timestamp required')
    return result


def calendar(value):
    if value is None or value == '':
        return None
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Date must be YYYY-MM-DD or null')
    return date.fromisoformat(value)


def append_event(history, event, current):
    """Pure compare-and-append preparation; no native writes or in-place edits."""
    if not isinstance(history, list) or not isinstance(event, dict):
        raise ValueError('History array and event object required')
    if any(event.get(k) != current.get(k) for k in SCOPE):
        raise ValueError('Stale document scope')
    required = ('EventUID', *SCOPE, 'Stage', 'OccurredOn', 'Actor', 'Rationale')
    if any(not isinstance(event.get(k), str) or not event[k].strip() for k in required):
        raise ValueError('Missing event identity, stage or dated human rationale')
    if not re.fullmatch('[0-9a-f]{64}', event['DocumentSHA256']):
        raise ValueError('Invalid document hash')
    occurred = timestamp(event['OccurredOn'])
    calendar(event.get('SourceDueDate'))
    calendar(event.get('AgreedTargetDate'))
    if event.get('AgreedTargetDate') and not event.get('TargetAgreementEvidence'):
        raise ValueError('Agreed target requires evidence')
    for key in ('NextAction', 'WaitingReason', 'Priority', 'TargetAgreementEvidence'):
        if event.get(key) is not None and not isinstance(event[key], str):
            raise ValueError('Invalid text field: ' + key)
    if event.get('State') not in {'Open', 'Completed', 'Declined', 'Superseded'}:
        raise ValueError('Unknown follow-up state')
    matches = [old for old in history if old.get('EventUID') == event['EventUID']]
    if matches:
        if len(matches) == 1 and matches[0] == event:
            return list(history), 'unchanged'
        raise ValueError('Conflicting event identity')
    previous = [old for old in history if old.get('CaseUID') == event['CaseUID']]
    head = previous[-1] if previous else None
    if event.get('PreviousEventUID') != (head['EventUID'] if head else None):
        raise ValueError('Stale follow-up head')
    if head and occurred < timestamp(head['OccurredOn']):
        raise ValueError('Event precedes current head')
    return [*history, dict(event)], 'appended'


def preview(payload, now, previous=None):
    """Unknown/stale/conflicting inputs are exception rows, never recipients."""
    now = timestamp(now)
    history = payload['events']
    rebuilt = []
    scopes = payload['currentScopes']
    if len({s['CaseUID'] for s in scopes}) != len(scopes):
        raise ValueError('Ambiguous current case scope')
    scope_by_case = {s['CaseUID']: s for s in scopes}
    # Validate each historical event against its own recorded scope; latest scope
    # applicability is checked separately so old versions remain preserved.
    for event in history:
        rebuilt, disposition = append_event(rebuilt, event, event)
        if disposition != 'appended':
            raise ValueError('Duplicate event in history')
    latest = {event['CaseUID']: event for event in rebuilt}
    candidates, exceptions, suppressed = [], [], []
    old_hashes = set((previous or {}).get('candidateFingerprints', []))
    for case, event in latest.items():
        reason = None
        current = scope_by_case.get(case)
        if not current or any(event[k] != current.get(k) for k in SCOPE):
            reason = 'stale_or_missing_document_scope'
        elif timestamp(event['OccurredOn']) > now:
            reason = 'future_event'
        elif event['State'] != 'Open':
            suppressed.append({'CaseUID': case, 'reason': event['State']})
            continue
        elif not (event.get('NextAction') or '').strip():
            reason = 'missing_next_action'
        else:
            try:
                fresh = timestamp(current['SourceAsOf'])
                checked = timestamp(current['SourceCheckedAt'])
                # Freshness is an explicit snapshot assertion, never an age heuristic.
                if fresh > checked or checked > now or current.get('SourceFreshness') != 'Current':
                    reason = 'source_freshness_unconfirmed'
            except (KeyError, ValueError, TypeError, AttributeError):
                reason = 'source_freshness_unknown'
        ownership = []
        if reason is None:
            events = payload.get('ownershipEvents', [])
            for assertion in events:
                try:
                    if timestamp(assertion.get('OccurredOn')) > now:
                        continue
                except (ValueError, TypeError, AttributeError):
                    continue
                result = for_version(assertion, *(current[k] for k in SCOPE), history=[e for e in events if e is not assertion])
                if result['recordedOwnershipAcceptance'] and assertion.get('ConditionsState') in {'None recorded', 'Resolved'}:
                    ownership.append(assertion)
            if len(ownership) != 1:
                reason = 'ownership_unresolved'
        recipient = current.get('Recipient') if current else None
        if reason is None and (not isinstance(recipient, dict) or recipient.get('Eligibility') != 'Verified'
                               or recipient.get('Role') != ownership[0]['SubjectRole']
                               or not isinstance(recipient.get('Address'), str)
                               or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', recipient['Address'])
                               or not recipient.get('EvidenceReference')):
            reason = 'recipient_unresolved'
        if reason:
            exceptions.append({'CaseUID': case, 'reason': reason})
            continue
        stage_entry = event['OccurredOn']
        for older in reversed([e for e in rebuilt if e['CaseUID'] == case][:-1]):
            if older['Stage'] != event['Stage'] or any(older[k] != event[k] for k in SCOPE):
                break
            stage_entry = older['OccurredOn']
        row = {'stageEnteredOn': stage_entry, 'CaseUID': case, 'event': event, 'acceptedRole': ownership[0]['SubjectRole'],
               'recipient': recipient, 'sourceAsOf': current['SourceAsOf'],
               'sourceCheckedAt': current['SourceCheckedAt'], 'sourceFreshness': current['SourceFreshness']}
        key = fingerprint(row)
        row.update(fingerprint=key, unchangedSincePrevious=key in old_hashes)
        candidates.append(row)
    return {'schemaVersion': 1, 'mode': 'manual-preview-only', 'asOf': now.isoformat(),
            'candidates': candidates, 'exceptions': exceptions, 'suppressed': suppressed,
            'candidateFingerprints': [r['fingerprint'] for r in candidates],
            'notificationSent': False, 'deliveryEligible': False, 'nativeWrites': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--append-event', type=Path, help='Prepare a new payload copy with one compare-and-append event')
    args = parser.parse_args()
    payload = json.loads(args.input.read_text())
    if args.append_event:
        if args.previous:
            parser.error('--previous is for preview only')
        preview(payload, args.as_of)  # Validate retained history before extending it.
        event = json.loads(args.append_event.read_text())
        scopes = [s for s in payload['currentScopes'] if s['CaseUID'] == event.get('CaseUID')]
        if len(scopes) != 1:
            raise ValueError('Missing or ambiguous current scope')
        events, disposition = append_event(payload['events'], event, scopes[0])
        report = dict(payload, events=events)
        preview(report, args.as_of)
        counts = {'events': len(events), 'disposition': disposition, 'nativeWrites': 0}
    else:
        report = preview(payload, args.as_of, json.loads(args.previous.read_text()) if args.previous else None)
        counts = {'candidates': len(report['candidates']), 'exceptions': len(report['exceptions']),
                  'suppressed': len(report['suppressed']), 'nativeWrites': 0}
    # Exclusive output prevents overwriting an earlier observation or human edits.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
