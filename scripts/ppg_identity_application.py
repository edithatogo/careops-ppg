"""Compile evidenced identity decisions for the sole importer; never write records.

A package is bound to exact source bytes, base aliases, allowed fields and every
unknown source record. New UUIDs are supplied by an operator with separate evidence;
this module never mints them. Installation and serial application belong to QW3.
"""
from __future__ import annotations

import copy
from uuid import UUID
from ppg_identity_triage import inspect, validate, normalise_inputs
from ppg_source_sync import digest, prepare, SyncError


def compile_application(snapshot: dict, ledger: dict, allowed: set[str],
                        proposals: list[dict], new_identity_authorisations: list[dict]) -> dict:
    report = inspect(snapshot, ledger['sourceSystemId'], ledger, allowed)
    if not proposals:
        raise SyncError('accepted_proposals_required')
    auths = {}
    for authorisation in new_identity_authorisations:
        key = authorisation.get('exceptionKey')
        if not key or key in auths:
            raise SyncError('duplicate_or_missing_new_identity_authorisation')
        uid = authorisation.get('DocumentUID')
        try:
            if str(UUID(uid)) != uid:
                raise ValueError('noncanonical_uuid')
        except (ValueError, TypeError, AttributeError):
            raise SyncError('invalid_authorised_new_uid')
        if any(not isinstance(authorisation.get(k), str) or not authorisation[k].strip()
               for k in ('actor', 'evidenceReference')):
            raise SyncError('new_identity_authorisation_evidence_required')
        auths[key] = copy.deepcopy(authorisation)
    revised = copy.deepcopy(ledger)
    seen_keys, seen_new_uids, consumed_auths = set(), set(), set()
    current_uids = {a['DocumentUID'] for a in ledger['aliases']}
    amendments = []
    for proposed in proposals:
        checked = validate(proposed, report, ledger)
        if not checked['validForReview']:
            raise SyncError(','.join(checked['issues']))
        if proposed['status'] != 'accepted':
            raise SyncError('explicit_acceptance_required')
        # A status string alone is not an explicit recorded operator transition.
        decisions = [h for h in proposed['history'] if h.get('from') == 'proposed'
                     and h.get('to') == 'accepted' and h.get('evidence') == proposed['decisionEvidence']
                     and isinstance(h.get('actor'), str) and h['actor'].strip() and h.get('at')]
        if len(decisions) != 1:
            raise SyncError('recorded_operator_acceptance_required')
        key = proposed['exceptionKey']
        if key in seen_keys:
            raise SyncError('duplicate_exception_decision')
        seen_keys.add(key)
        matches = [e for e in report['exceptions'] if e['exceptionKey'] == key]
        if len(matches) != 1 or matches[0]['code'] != 'unknown_alias':
            raise SyncError('unknown_alias_decision_required')
        item = matches[0]
        if proposed['resolution'] == 'existing_uid':
            uid = proposed['existingUID']
            if key in auths:
                raise SyncError('unexpected_new_identity_authorisation')
        elif proposed['resolution'] == 'request_new_uid':
            if key not in auths:
                raise SyncError('explicit_new_identity_authorisation_required')
            uid = auths[key]['DocumentUID']
            if uid in current_uids or uid in seen_new_uids:
                raise SyncError('new_uid_collision')
            seen_new_uids.add(uid)
            consumed_auths.add(key)
        else:
            raise SyncError('unresolved_identity')
        revised['aliases'].append({'source': report['source'], 'alias': item['sourceAlias'],
                                   'DocumentUID': uid})
        amendments.append({'exceptionKey': key, 'alias': item['sourceAlias'], 'DocumentUID': uid,
                           'sourceFingerprint': item['sourceFingerprint'],
                           'proposalHash': digest(proposed), 'kind': proposed['resolution']})
    if consumed_auths != set(auths):
        raise SyncError('unused_new_identity_authorisation')
    plan = prepare(snapshot, report['source'], revised['aliases'], allowed)
    if plan['exceptions'] or plan['missingUIDs']:
        raise SyncError('amendment_leaves_identity_exceptions')
    expected_uids = sorted({op['DocumentUID'] for op in plan['operations']})
    if len(expected_uids) != len(current_uids) + len(seen_new_uids):
        raise SyncError('unauthorised_identity_count_change')
    package = {'schemaVersion': 1, 'source': report['source'],
               'sourceSha256': report['sourceSha256'], 'baseContractHash': report['contractHash'],
               'resultContractHash': plan['contractHash'], 'allowed': sorted(allowed),
               'baseUIDs': sorted(current_uids), 'expectedUIDs': expected_uids,
               'newUIDs': sorted(seen_new_uids), 'inputCount': plan['inputCount'],
               'amendments': amendments, 'acceptedProposals': copy.deepcopy(proposals),
               'newIdentityAuthorisations': copy.deepcopy(new_identity_authorisations),
               'resultLedger': revised, 'status': 'accepted-awaiting-importer'}
    package['packageHash'] = digest(package)
    return package


def verify_application(package: dict, snapshot: dict, ledger: dict, allowed: set[str]) -> dict:
    """Rebuild from current authoritative inputs; never trust staged ledger/counts."""
    expected = compile_application(snapshot, ledger, allowed, package['acceptedProposals'],
                                   package['newIdentityAuthorisations'])
    if package != expected:
        raise SyncError('application_package_changed')
    return prepare(snapshot, ledger['sourceSystemId'], expected['resultLedger']['aliases'], allowed)


def inspect_outcome(package: dict, receipt: dict, checkpoint: dict) -> dict:
    """Keep accepted, applied and checkpoint-verified states distinct.

    Consume retained native evidence, never an operator's proposed status. The
    native receipt must prove complete source readback for this exact package.
    A later checkpoint requires the archived checkpoint from the application run.
    """
    unsigned = copy.deepcopy(package)
    claimed = unsigned.pop('packageHash', None)
    if not claimed or digest(unsigned) != claimed:
        raise SyncError('application_package_changed')
    base = {'schemaVersion': 1, 'packageHash': claimed,
            'sourceSha256': package['sourceSha256'], 'status': 'accepted',
            'applicationVerified': False, 'policyApproved': False,
            'runId': receipt.get('runId'), 'writesPermitted': False}
    def matches(evidence):
        try:
            _, ledger = normalise_inputs({'records': []}, evidence)
            return (evidence.get('status') == 'completed'
                    and evidence.get('sourceSha256') == package['sourceSha256']
                    and evidence.get('lastIdentityApplicationHash') == claimed
                    and evidence.get('identityContractHash') == package['resultContractHash']
                    and digest(ledger['aliases']) == package['resultContractHash']
                    and evidence.get('readbackCount') == package['inputCount']
                    and bool(evidence.get('runId')))
        except (KeyError, TypeError, ValueError):
            return False
    if not matches(receipt):
        return {**base, 'reason': 'complete_package_specific_native_readback_missing'}
    base.update(status='applied', reason='matching_success_checkpoint_required')
    if matches(checkpoint) and checkpoint['runId'] == receipt['runId']:
        base.update(status='verified', applicationVerified=True,
                    reason='native_readback_and_commit_last_checkpoint_match')
    return base


def main():
    import argparse
    import json
    import os
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot', 'ledger', 'allowed', 'output'):
        parser.add_argument('--'+name, type=Path, required=name == 'output')
    parser.add_argument('--proposals', type=Path, help='JSON array of accepted proposals')
    parser.add_argument('--new-authorisations', type=Path, help='JSON array; empty for alias-only changes')
    parser.add_argument('--verify-package', type=Path)
    parser.add_argument('--verify-outcome', type=Path, help='Application package; requires native receipt and its checkpoint')
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--checkpoint', type=Path)
    args = parser.parse_args()
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    if args.verify_outcome:
        if not args.receipt or not args.checkpoint:
            parser.error('--receipt and --checkpoint are required for outcome verification')
        result = inspect_outcome(read(args.verify_outcome), read(args.receipt), read(args.checkpoint))
    else:
        if not args.snapshot or not args.ledger or not args.allowed:
            parser.error('--snapshot, --ledger and --allowed are required')
        snapshot, ledger = normalise_inputs(read(args.snapshot), read(args.ledger))
        allowed = set(read(args.allowed))
    if args.verify_outcome:
        pass
    elif args.verify_package:
        package = read(args.verify_package)
        plan = verify_application(package, snapshot, ledger, allowed)
        result = {'status': 'locally-verified-awaiting-importer', 'packageHash': package['packageHash'],
                  'contractHash': plan['contractHash'], 'inputCount': plan['inputCount'],
                  'nativeApplied': False}
    else:
        if not args.proposals or not args.new_authorisations:
            parser.error('--proposals and --new-authorisations are required for compilation')
        proposed = read(args.proposals)
        proposals = proposed if isinstance(proposed, list) else [proposed]
        result = compile_application(snapshot, ledger, allowed, proposals,
                                     read(args.new_authorisations))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'x', encoding='utf-8', opener=lambda p,f:os.open(p,f,0o600)) as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
