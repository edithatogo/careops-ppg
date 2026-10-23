"""Read-only mechanical citation checks; never establish semantic or policy authority."""
from __future__ import annotations
import argparse
import hashlib
import json
import posixpath
import re
from datetime import datetime, timedelta
from uuid import UUID
from pathlib import Path
from urllib.parse import urlsplit, unquote


CONTRACT = json.loads((Path(__file__).resolve().parents[1] / 'config/cited-evidence.json').read_text())


def valid_utc_time(value):
    if not isinstance(value, str) or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)', value):
        return False
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).utcoffset() == timedelta(0)
    except ValueError:
        return False


def valid_native_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value):
        return False
    return UUID(value).int != 0


def in_scope(url: str, prefix: str) -> bool:
    try:
        u, p = urlsplit(url), urlsplit(prefix)
        path = posixpath.normpath(unquote(u.path))
        root = posixpath.normpath(unquote(p.path))
        return (u.scheme == p.scheme == 'https' and u.netloc == p.netloc and
                not u.username and not u.password and not u.query and not u.fragment and
                (path == root or path.startswith(root.rstrip('/') + '/')))
    except (TypeError, ValueError):
        return False


def check_answer(answer: dict, sources: list[dict], allowed_prefix: str) -> dict:
    issues = []
    indexed = {}
    statuses = CONTRACT['answerStatuses']
    if answer.get('status') not in statuses:
        issues.append('invalid_answer_status')
    if answer.get('actionsPerformed') != [] or answer.get('policyApproved') is not False:
        issues.append('write_or_approval_claim')
    if not isinstance(answer.get('claims'), list):
        issues.append('claims_must_be_array')
        claims = []
    else:
        claims = answer['claims']
    if answer.get('status') in {'unknown', 'refused'} and claims:
        issues.append('unknown_or_refused_must_not_assert_claims')
    if answer.get('status') in {'supported', 'partial', 'conflict'} and not claims:
        issues.append('supported_answer_needs_claims')
    for source in sources:
        uid = source.get('sourceId')
        if not uid or uid in indexed:
            issues.append('missing_or_duplicate_source_id')
        indexed[uid] = source
        if source.get('status') not in CONTRACT['sourceStatuses']:
            issues.append('invalid_source_status:' + str(uid))
        if source.get('status') != 'retrieved':
            if source.get('text'):
                issues.append('unreadable_source_contains_content:' + str(uid))
            continue
        if not in_scope(source.get('canonicalUrl', ''), allowed_prefix):
            issues.append('source_outside_selected_scope:' + str(uid))
        text = source.get('text')
        if not isinstance(text, str):
            issues.append('retrieved_text_missing:' + str(uid))
        elif hashlib.sha256(text.encode()).hexdigest() != source.get('sha256'):
            issues.append('source_hash_mismatch:' + str(uid))
        for key in ('nativeUniqueId', 'nativeVersionRef', 'retrievedAtUtc', 'authorityLabel'):
            if not isinstance(source.get(key), str) or not source[key].strip():
                issues.append('source_receipt_missing:' + key)
        if not valid_native_id(source.get('nativeUniqueId')):
            issues.append('invalid_native_unique_id:' + str(uid))
        if source.get('authorityLabel') not in CONTRACT['authorityLabels']:
            issues.append('invalid_authority_label:' + str(uid))
        if not valid_utc_time(source.get('retrievedAtUtc')):
            issues.append('invalid_retrieval_time:' + str(uid))
    checked = 0
    claim_ids = set()
    for claim in claims:
        uid = claim.get('claimId')
        if not uid or uid in claim_ids or not isinstance(claim.get('text'), str) or not claim['text'].strip():
            issues.append('invalid_or_duplicate_claim')
        claim_ids.add(uid)
        if claim.get('assertsCurrentAuthority') is not False:
            issues.append('authority_assertion_not_qualified')
        citations = claim.get('citations')
        if not isinstance(citations, list) or not citations:
            issues.append('uncited_claim:' + str(uid))
            continue
        for cite in citations:
            source = indexed.get(cite.get('sourceId'))
            if not source or source.get('status') != 'retrieved':
                issues.append('citation_source_not_retrieved')
                continue
            for key in ('canonicalUrl', 'nativeVersionRef', 'sha256', 'authorityLabel'):
                if cite.get(key) != source.get(key):
                    issues.append('citation_receipt_mismatch:' + key)
            start, end = cite.get('startLine'), cite.get('endLine')
            lines = source.get('text', '').splitlines()
            if type(start) is not int or type(end) is not int or not (1 <= start <= end <= len(lines)):
                issues.append('invalid_citation_locator')
                continue
            exact = '\n'.join(lines[start - 1:end])
            if cite.get('quote') != exact:
                issues.append('citation_quote_mismatch')
            else:
                checked += 1
    return {'mechanicallyValid': not issues, 'issues': issues, 'citationsChecked': checked,
            'semanticEntailment': 'not assessed by this checker',
            'nativePermissionTrimming': 'not proved by supplied receipt assertions',
            'policyApproved': False, 'writesPerformed': 0,
            'promotionReady': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--answer', type=Path, required=True)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--allowed-prefix', required=True)
    a = p.parse_args()
    result = check_answer(json.loads(a.answer.read_text()), json.loads(a.sources.read_text()), a.allowed_prefix)
    print(json.dumps(result, indent=2))
    return 0 if result['mechanicallyValid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
