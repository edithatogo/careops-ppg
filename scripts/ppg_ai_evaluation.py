"""Evaluate captured AI runs without invoking a model or changing Microsoft resources."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timedelta
import re
from pathlib import Path
from urllib.parse import urlsplit
from ppg_evidence_check import check_answer, in_scope


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def utc_time(value):
    """Require an ISO-8601 UTC event time with an explicit timezone."""
    if not isinstance(value, str) or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)', value):
        raise ValueError('Expected ISO-8601 UTC timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() != timedelta(0):
        raise ValueError('Expected UTC timestamp')
    return parsed


def validate_cases(cases):
    """Require explicit source expectations and a source-review rubric per case."""
    ids = []
    for case in cases:
        uid = case['caseId']
        if not isinstance(uid, str) or not uid.strip():
            raise ValueError('Evaluation caseId must be a nonempty string')
        ids.append(uid)
        selected = case['selectedSources']
        if not isinstance(selected, list) or not all(isinstance(s, str) and s.strip() for s in selected):
            raise ValueError('selectedSources must contain source IDs')
        if len(selected) != len(set(selected)):
            raise ValueError('Duplicate selected source ID')
        expected = case['expectedSources']
        if not isinstance(expected, dict) or set(expected) != set(selected):
            raise ValueError('Expected sources must exactly cover selectedSources')
        for source in expected.values():
            if source['status'] not in {'retrieved', 'denied', 'missing', 'unsupported', 'changed-during-read'}:
                raise ValueError('Invalid expected source status')
            if source['status'] == 'retrieved':
                if not re.fullmatch(r'[0-9a-f]{64}', source.get('sha256', '')):
                    raise ValueError('Expected retrieved source needs exact SHA-256')
                if source.get('authorityLabel') not in {'captured-reference-unconfirmed', 'draft-unapproved',
                                                       'authority-recorded-not-independently-verified'}:
                    raise ValueError('Invalid expected authority label')
        criteria = case['reviewCriteria']
        if not isinstance(criteria, list) or not criteria or not all(
                isinstance(c, str) and c.strip() for c in criteria):
            raise ValueError('Each case needs explicit human source-review criteria')
        if not isinstance(case['question'], str) or not case['question'].strip():
            raise ValueError('Each case needs a question')
        if case['expectedStatus'] not in {'supported', 'partial', 'unknown', 'conflict', 'refused'}:
            raise ValueError('Invalid expected answer status')
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Evaluation case IDs must be unique and nonempty')
    return ids


def evaluate(pack, runs):
    cases = pack['cases']
    ids = validate_cases(cases)
    indexed = {}
    for run in runs:
        uid = run['caseId']
        if uid not in ids or uid in indexed:
            raise ValueError('Unknown or duplicate run caseId: ' + uid)
        indexed[uid] = run
    configuration_fields = ('runtime', 'model', 'configurationRevision')
    configurations = {tuple(run.get(k) for k in configuration_fields) for run in runs}
    if len(configurations) > 1:
        raise ValueError('All cases must use the same runtime, model and configurationRevision')
    configuration = (dict(zip(configuration_fields, next(iter(configurations))))
                     if configurations else None)
    rows = []
    for case in cases:
        run = indexed.get(case['caseId'])
        row = {'caseId': case['caseId'], 'state': 'not-run', 'issues': [],
               'reviewCriteria': case['reviewCriteria']}
        if run is None:
            rows.append(row)
            continue
        issues = row['issues']
        required = ('runtime', 'model', 'configurationRevision', 'executedAtUtc', 'rawResponseEvidence',
                    'retrievalEvidence', 'actionAuditEvidence', 'allowedPrefix')
        for key in required:
            if not isinstance(run.get(key), str) or not run[key].strip():
                issues.append('missing_run_evidence:' + key)
        executed = None
        try:
            executed = utc_time(run.get('executedAtUtc'))
        except ValueError:
            issues.append('invalid_utc_time:executedAtUtc')
        if run.get('question') != case['question']:
            issues.append('question_mismatch')
        prefix = run.get('allowedPrefix', '')
        if not in_scope(prefix, prefix) or not urlsplit(prefix).hostname:
            issues.append('invalid_allowed_prefix')
        sources = run.get('sources', [])
        actual_ids = [s['sourceId'] for s in sources]
        if sorted(actual_ids) != sorted(case['selectedSources']):
            issues.append('selected_scope_mismatch')
        for source in sources:
            uid = source['sourceId']
            expected = case['expectedSources'].get(uid)
            if expected is None:
                continue  # Scope mismatch is reported above.
            for key, value in expected.items():
                if source.get(key) != value:
                    issues.append('expected_source_mismatch:' + uid + ':' + key)
            if source.get('status') == 'retrieved':
                try:
                    utc_time(source.get('retrievedAtUtc'))
                except ValueError:
                    issues.append('invalid_source_utc_time:' + uid)
                if not isinstance(source.get('nativeVersionRef'), str) or not source['nativeVersionRef'].strip():
                    issues.append('invalid_source_version:' + uid)
        answer = run.get('answer', {})
        mechanical = check_answer(answer, sources, run.get('allowedPrefix', ''))
        issues.extend(mechanical['issues'])
        if answer.get('status') != case['expectedStatus']:
            issues.append('unexpected_answer_status')
        if run.get('observedActions') != []:
            issues.append('actions_not_verified_empty')
        mechanically_valid = not issues
        # Bind the separate reviewer record to these exact inputs and output.
        fingerprint = digest({'case': case, 'answer': answer, 'sources': sources,
                              'runEvidence': {k: run.get(k) for k in required},
                              'observedActions': run.get('observedActions')})
        review = run.get('humanReview', {})
        if review.get('result') == 'fail':
            issues.append('human_review_failed')
        review_time_valid = False
        if review.get('result') == 'pass':
            try:
                reviewed = utc_time(review.get('reviewedAtUtc'))
                review_time_valid = executed is not None and reviewed >= executed
                if executed is not None and reviewed < executed:
                    issues.append('review_precedes_execution')
            except ValueError:
                issues.append('invalid_utc_time:reviewedAtUtc')
        review_pass = (review.get('result') == 'pass' and review_time_valid and
                       review.get('subjectSha256') == fingerprint and
                       all(isinstance(review.get(k), str) and review[k].strip()
                           for k in ('reviewer', 'reviewedAtUtc', 'evidence', 'findings')))
        row.update(subjectSha256=fingerprint, mechanicallyValid=mechanically_valid,
                   humanReviewAccepted=review_pass,
                   state='failed' if issues else ('reviewed-pass' if review_pass else 'awaiting-human-review'))
        rows.append(row)
    passed = all(r['state'] == 'reviewed-pass' for r in rows)
    return {'schemaVersion': 1, 'packSha256': digest(pack), 'configuration': configuration, 'cases': rows,
            'counts': {s: sum(r['state'] == s for r in rows) for s in
                       ('not-run', 'failed', 'awaiting-human-review', 'reviewed-pass')},
            'evaluationComplete': passed, 'promotionReady': False,
            'permissionTrimming': 'Requires separate native principal evidence',
            'operationalAcceptance': 'Separate runtime/data-scope and human decision required',
            'writesPerformedByEvaluator': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, default=Path('templates/cited-evidence/evaluation-cases.json'))
    parser.add_argument('--runs', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = evaluate(json.loads(args.pack.read_text()), json.loads(args.runs.read_text()))
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        parser.exit(2, 'Invalid evaluation input: ' + str(exc) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['evaluationComplete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
