"""Read-only identity triage. No network client, ledger writer or UID minting."""
from __future__ import annotations

import argparse
import json
import html
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from ppg_source_sync import digest, prepare
from ppg_workspace import validate_structure


def normalise_inputs(snapshot: dict, ledger: dict) -> tuple[dict, dict]:
    """Accept retained native snapshots and the checkpoint's active contract.

    Does not regenerate source values, choose identities or change caller data.
    The bootstrap ledger is valid only until the checkpoint has an active ledger.
    """
    import copy
    if 'identitySnapshot' in snapshot:
        snapshot = snapshot['identitySnapshot']
    elif 'rawRecords' in snapshot:
        snapshot = {**snapshot, 'records': snapshot['rawRecords']}
    if 'identityLedger' in ledger:
        if ledger.get('status') != 'completed' or not ledger['identityLedger']:
            raise ValueError('completed_active_contract_required')
        ledger = ledger['identityLedger']
    source = ledger['sourceSystemId']
    aliases = []
    for alias in ledger['aliases']:
        if 'documentUID' in alias and 'sourceDocumentId' in alias:
            aliases.append({'source': source, 'alias': alias['sourceDocumentId'],
                            'DocumentUID': alias['documentUID']})
        elif set(('source', 'alias', 'DocumentUID')) <= set(alias):
            aliases.append(copy.deepcopy(alias))
        else:
            raise ValueError('unsupported_identity_ledger_shape')
    return copy.deepcopy(snapshot), {'sourceSystemId': source, 'aliases': aliases}


def inspect(snapshot: dict, source: str, ledger: dict, allowed: set[str]) -> dict:
    if ledger['sourceSystemId'] != source:
        raise ValueError('source_namespace_mismatch')
    plan = prepare(snapshot, source, ledger['aliases'], allowed)
    by_row = {r['sourceRow']: r for r in snapshot['records']}
    cases = []
    for exception in plan['exceptions']:
        row = by_row[exception['row']]
        fingerprint = digest({'source': source, 'sourceSha256': plan['sourceSha256'],
                              'fields': row['fields']})
        cases.append({'exceptionKey': digest({'code': exception['code'],
                                             'sourceFingerprint': fingerprint}),
                      'code': exception['code'], 'sourceRowForNavigation': row['sourceRow'],
                      'sourceFingerprint': fingerprint, 'sourceAlias': row['fields']['sourceDocumentId'],
                      'sourceFields': row['fields'],
                      'candidateUIDs': plan['missingUIDs'] if exception['code'] == 'unknown_alias' else [],
                      'candidateBasis': 'Missing source-qualified UIDs only; these are investigation leads, never identity matches.', 'status': 'unresolved',
                      'nextAction': 'Compare authoritative identity evidence; record a proposal. Never infer identity from title or row.'})
    return {'schemaVersion': 1, 'mode': 'read-only', 'source': source,
            'sourceSha256': plan['sourceSha256'], 'contractHash': plan['contractHash'],
            'inputCount': plan['inputCount'], 'matchedCount': len(plan['operations']),
            'exceptions': cases, 'missingUIDs': plan['missingUIDs'],
            'matchedUIDs': [op['DocumentUID'] for op in plan['operations']],
            'sourceProvenance': plan['provenance'],
            'writesPermitted': False, 'applyAvailable': False}


def proposal(report: dict, exception_key: str) -> dict:
    matches = [e for e in report['exceptions'] if e['exceptionKey'] == exception_key]
    if len(matches) != 1:
        raise ValueError('unknown_or_ambiguous_exception_key')
    item = matches[0]
    return {'schemaVersion': 1, 'status': 'proposed', 'exceptionKey': exception_key,
            'source': report['source'], 'sourceSha256': report['sourceSha256'],
            'sourceFingerprint': item['sourceFingerprint'], 'contractHash': report['contractHash'],
            'resolution': 'unresolved', 'existingUID': None, 'rationale': '',
            'evidenceReferences': [], 'decisionEvidence': None,
            'applyAvailable': False, 'history': []}


def validate(proposed: dict, report: dict, ledger: dict) -> dict:
    """Preflight only. Even an accepted proposal cannot change the contract here."""
    issues = []
    schema = json.loads((Path(__file__).resolve().parents[1] / 'config/identity-proposal.schema.json').read_text())
    try:
        validate_structure(proposed, schema)
    except (ValueError, TypeError, KeyError):
        return {'validForReview': False, 'issues': ['proposal_schema_invalid'],
                'applyAvailable': False, 'writesPermitted': False, 'nextAction': 'Repair proposal structure.'}
    for k in ('source', 'sourceSha256', 'contractHash'):
        if proposed.get(k) != report[k]:
            issues.append('stale_or_conflicting_' + k)
    item = next((e for e in report['exceptions']
                 if e['exceptionKey'] == proposed.get('exceptionKey')), None)
    if not item or proposed.get('sourceFingerprint') != item['sourceFingerprint']:
        issues.append('stale_or_unknown_exception')
    if ledger['sourceSystemId'] != report['source']:
        issues.append('source_namespace_mismatch')
    if digest(ledger['aliases']) != report['contractHash']:
        issues.append('ledger_changed')
    if proposed.get('schemaVersion') != 1:
        issues.append('unsupported_schema_version')
    if not isinstance(proposed.get('evidenceReferences'), list) or any(not isinstance(r, str) or not r.strip() for r in proposed.get('evidenceReferences', [])):
        issues.append('invalid_evidence_references')
    resolution = proposed.get('resolution')
    if resolution not in ('existing_uid', 'request_new_uid', 'unresolved', 'ambiguous'):
        issues.append('unsupported_resolution')
    if resolution == 'existing_uid':
        try:
            UUID(proposed.get('existingUID'))
        except (ValueError, TypeError, AttributeError):
            issues.append('invalid_uid')
        uids = {a['DocumentUID'] for a in ledger['aliases'] if a['source'] == report['source']}
        if proposed.get('existingUID') not in uids:
            issues.append('unknown_existing_uid')
    elif proposed.get('existingUID') is not None:
        issues.append('unexpected_uid')
    if proposed.get('status') not in ('proposed', 'accepted', 'applied', 'verified', 'rejected'):
        issues.append('unsupported_status')
    if proposed.get('status') in ('accepted', 'applied', 'verified'):
        if resolution in ('unresolved', 'ambiguous'):
            issues.append('unresolved_identity')
        if not proposed.get('rationale', '').strip() or not proposed.get('evidenceReferences') or not (proposed.get('decisionEvidence') or '').strip():
            issues.append('decision_evidence_required')
    if proposed.get('status') in ('applied', 'verified') and not proposed.get('applicationEvidence'):
        issues.append('application_evidence_required')
    if proposed.get('status') == 'verified' and not proposed.get('verificationEvidence'):
        issues.append('verification_evidence_required')
    return {'validForReview': not issues, 'issues': issues,
            'applyAvailable': False, 'writesPermitted': False,
            'nextAction': 'Compile accepted decisions against current inputs and use the existing guarded importer; this check grants no write authority.'}



def transition(proposed: dict, status: str, evidence: str, actor: str) -> dict:
    """Record a human decision; never grant catalogue or ledger write authority."""
    import copy
    if status not in {'accepted', 'rejected'} or proposed['status'] != 'proposed':
        raise ValueError('invalid_transition')
    if not actor.strip() or not evidence.strip():
        raise ValueError('decision_evidence_required')
    result = copy.deepcopy(proposed)
    result['status'] = status
    result['decisionEvidence'] = evidence
    result.setdefault('history', []).append({'from': 'proposed', 'to': status,
        'actor': actor, 'evidence': evidence,
        'at': datetime.now(timezone.utc).isoformat()})
    return result


def amendment(proposed: dict, report: dict, ledger: dict) -> dict:
    """Export an owner handoff, never modify the ledger or invoke an importer.

    An existing-UID alias must leave one record per UID in the complete snapshot.
    New UIDs require the existing owner to qualify creation and count guards first.
    """
    checked = validate(proposed, report, ledger)
    if not checked['validForReview']:
        raise ValueError(','.join(checked['issues']))
    if proposed['status'] != 'accepted':
        raise ValueError('explicit_acceptance_required')
    item = next(e for e in report['exceptions'] if e['exceptionKey'] == proposed['exceptionKey'])
    if item['code'] != 'unknown_alias':
        raise ValueError('exception_requires_owner_investigation')
    if proposed['resolution'] == 'existing_uid' and proposed['existingUID'] in report['matchedUIDs']:
        raise ValueError('uid_collision_in_snapshot')
    aliases = ledger['aliases']
    if any(a['source'] == report['source'] and a['alias'] == item['sourceAlias'] for a in aliases):
        raise ValueError('alias_already_registered')
    return {'schemaVersion': 1, 'status': 'accepted-awaiting-owner',
        'proposalHash': digest(proposed), 'exceptionKey': proposed['exceptionKey'],
        'source': report['source'], 'sourceSha256': report['sourceSha256'],
        'contractHash': report['contractHash'], 'sourceFingerprint': item['sourceFingerprint'],
        'alias': item['sourceAlias'], 'resolution': proposed['resolution'],
        'existingUID': proposed['existingUID'], 'decisionEvidence': proposed['decisionEvidence'],
        'writesPermitted': False, 'applyAvailable': False,
        'nextAction': 'Compile an application package for the sole importer; a new UID needs a separate explicit operator authorisation.'}



def stage_amendment(proposed: dict, snapshot: dict, ledger: dict, allowed: set[str]) -> dict:
    """Prepare an isolated owner package through the existing planner, no writes.

    Rebuild report from current inputs rather than trusting an old report export.
    Only a source-qualified alias for an existing UID can be staged. Creation of
    a new UID or adjustment of native extractor/count guards remains unsupported.
    """
    import copy
    report = inspect(snapshot, ledger['sourceSystemId'], ledger, allowed)
    handoff = amendment(proposed, report, ledger)
    if proposed['resolution'] == 'request_new_uid':
        handoff['blockedReason'] = 'explicit_new_identity_authorisation_required_before_package_compilation'
        return handoff
    revised = copy.deepcopy(ledger)
    revised['aliases'].append({'source': report['source'], 'alias': handoff['alias'],
                               'DocumentUID': proposed['existingUID']})
    plan = prepare(snapshot, report['source'], revised['aliases'], allowed)
    if plan['exceptions'] or plan['missingUIDs']:
        raise ValueError('amendment_leaves_identity_exceptions')
    handoff.update(stagedLedger=revised, stagedPlan=plan,
                   stagedContractHash=plan['contractHash'],
                   blockedReason='preparation_only_compile_and_verify_an_application_package')
    return handoff

def render(report: dict) -> str:
    """Portable, escaped read-only report. No scripts or external resources."""
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for item in report['exceptions']:
        cards.append('<section><h2>'+esc(item['code'])+'</h2><p>Exception: <code>'+esc(item['exceptionKey'])+
            '</code></p><p>Row (navigation only): '+esc(item['sourceRowForNavigation'])+
            '</p><p>Alias: '+esc(item['sourceAlias'])+'</p><pre>'+esc(json.dumps(item['sourceFields'], indent=2, ensure_ascii=False))+
            '</pre><p>Candidate UIDs: '+esc(item['candidateUIDs'])+'</p><p>'+esc(item['nextAction'])+'</p></section>')
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>Identity resolution — unresolved</title><h1>Identity resolution</h1><p>Read-only preparation. This report grants no write authority. No identity decision, ledger change or reconciliation has occurred.</p><p>Source hash: <code>'+esc(report['sourceSha256'])+'</code></p><p>Contract hash: <code>'+esc(report['contractHash'])+'</code></p><p>Source rows: '+esc(report['inputCount'])+'; matched: '+esc(report['matchedCount'])+'.</p><p>Missing source-qualified UIDs: '+esc(report['missingUIDs'])+'. Investigate missing records; never retire them automatically.</p>'+''.join(cards)+'<p>Export a proposal with the guided command, record evidence and explicit acceptance, then hand it to the existing contract/importer owner. New UID requests need a separately evidenced operator-supplied UID before application.</p></html>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--allowed', type=Path, required=True, help='JSON array of importer field names')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--action', choices=['report', 'html', 'propose', 'check', 'accept', 'reject', 'handoff'], default='report')
    parser.add_argument('--exception-key')
    parser.add_argument('--proposal', type=Path)
    parser.add_argument('--actor', default='')
    parser.add_argument('--decision-evidence', default='')
    args = parser.parse_args()
    snapshot, ledger = normalise_inputs(json.loads(args.snapshot.read_text()), json.loads(args.ledger.read_text()))
    report = inspect(snapshot, ledger['sourceSystemId'], ledger,
                     set(json.loads(args.allowed.read_text())))
    result = report
    if args.action == 'html':
        result = render(report)
    elif args.action == 'propose':
        if not args.exception_key:
            parser.error('--exception-key is required')
        result = proposal(report, args.exception_key)
    elif args.action in ('check', 'accept', 'reject', 'handoff'):
        if not args.proposal:
            parser.error('--proposal is required')
        proposed = json.loads(args.proposal.read_text())
        if args.action in ('accept', 'reject'):
            result = transition(proposed, 'accepted' if args.action == 'accept' else 'rejected',
                                args.decision_evidence, args.actor)
            checked = validate(result, report, ledger)
            if not checked['validForReview']:
                raise ValueError(','.join(checked['issues']))
        elif args.action == 'handoff':
            result = stage_amendment(proposed, snapshot, ledger,
                                     set(json.loads(args.allowed.read_text())))
        else:
            result = validate(proposed, report, ledger)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'x', encoding='utf-8', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        stream.write(result if isinstance(result, str) else json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
