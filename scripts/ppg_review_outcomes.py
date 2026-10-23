"""Summarise explicit review observations; never infer usefulness or decisions."""
import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from statistics import median


def report(data):
    if data.get('schemaVersion') != 1:
        raise ValueError('Unknown outcome observation schema')
    judgments, decisions = data['judgments'], data['decisions']
    kind = data.get('datasetKind')
    if kind not in {'fictional', 'operational'} and (kind is not None or judgments or decisions):
        raise ValueError('Observed outcomes require one explicit dataset kind')
    bindings, seen = {}, set()

    def bind(row):
        if row.get('datasetKind', kind) != kind:
            raise ValueError('Fictional and operational observations must stay separate')
        for key in ['reviewRunId', 'documentUID', 'documentSha256']:
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError('Missing review/document binding')
        if not re.fullmatch('[a-f0-9]{64}', row['documentSha256']):
            raise ValueError('Document SHA256 required')
        value = (row['documentUID'], row['documentSha256'])
        if bindings.setdefault(row['reviewRunId'], value) != value:
            raise ValueError('Review run has conflicting document binding')

    def instant(value):
        if not isinstance(value, str):
            raise ValueError('Timestamp required')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError('Timestamp timezone required')
        return parsed

    for row in judgments:
        bind(row)
        if not isinstance(row.get('findingRef'), str) or not row['findingRef'].strip():
            raise ValueError('Finding reference required')
        key = (row['reviewRunId'], row['findingRef'])
        if key in seen:
            raise ValueError('Duplicate finding/run judgment')
        seen.add(key)
        for name in ['usefulAccepted', 'falsePositive']:
            if row.get(name) is not None and type(row[name]) is not bool:
                raise ValueError('Judgment must be boolean or unknown')
        if row.get('usefulAccepted') is True and row.get('falsePositive') is True:
            raise ValueError('Conflicting usefulness and false-positive judgment')
        if any(row.get(k) is not None for k in ['usefulAccepted', 'falsePositive']):
            instant(row.get('judgedAt'))
            if not isinstance(row.get('decisionRef'), str) or not row['decisionRef'].strip():
                raise ValueError('Observed judgment needs decision evidence reference')
    runs, durations, missing = set(), [], 0
    for row in decisions:
        bind(row)
        if row['reviewRunId'] in runs:
            raise ValueError('Duplicate decision interval')
        runs.add(row['reviewRunId'])
        start = instant(row['startedAt']) if row.get('startedAt') is not None else None
        end = instant(row['decidedAt']) if row.get('decidedAt') is not None else None
        if end is not None:
            if start is None or not isinstance(row.get('decisionRef'), str) or not row['decisionRef'].strip():
                raise ValueError('Decision interval needs start and evidence reference')
            seconds = (end-start).total_seconds()
            if seconds < 0:
                raise ValueError('Decision precedes review start')
            durations.append(seconds)
        else:
            missing += 1
    def fraction(name):
        values = [r[name] for r in judgments if r.get(name) is not None]
        return dict(yesCount=sum(values), knownJudgmentCount=len(values),
                    unknownJudgmentCount=len(judgments)-len(values),
                    fraction=sum(values)/len(values) if values else None)
    measured = any(r.get(k) is not None for r in judgments for k in ['usefulAccepted','falsePositive']) or bool(durations)
    return dict(schemaVersion=1, datasetKind=kind or 'unobserved-template',
                measurementStatus='observed_inputs_supplied' if measured else 'not_measured',
                judgmentUnit='finding within a review run; not unique suggestions across runs',
                usefulAccepted=fraction('usefulAccepted'), falsePositive=fraction('falsePositive'),
                decisionElapsed=dict(sampleCount=len(durations), missingIntervalCount=missing,
                                     medianSeconds=median(durations) if durations else None,
                                     totalSeconds=sum(durations) if durations else None),
                reviewRunCount=len(bindings), clinicalAuthorityVerified=False,
                ordinaryUserAccessVerified=False, causalBenefitEstablished=False,
                limitations=['Decision elapsed time is calendar time, not hands-on effort or a saving.',
                             'Use existing matched task observation kit for reviewer effort.',
                             'Supplied operational labels/evidence references do not verify observation or authority.',
                             'Read dated coverage receipts separately; no catalogue coverage inferred from judgments.'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    raw = args.input.read_bytes()
    result = report(json.loads(raw))
    result['inputSHA256'] = hashlib.sha256(raw).hexdigest()
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(measurementStatus=result['measurementStatus'], datasetKind=result['datasetKind'], nativeWrites=0)))
