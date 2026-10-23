"""Summarise explicit CLI receipts without inferring human acceptance."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

MAX_INPUTS = 100
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
QUALIFICATION_KEY = re.compile(r'(?:qualified|qualification)$', re.I)
SUCCESS_EVENTS = {'complete', 'completed', 'published', 'replayed', 'generated', 'command-exited'}
SUCCESS_STATES = {'complete', 'completed', 'published', 'replayed', 'generated', 'supported', 'success', 'succeeded'}
REFUSAL_MARKERS = ('REFUS', 'DENIED', 'FORBIDDEN', 'CONFLICT', 'MISMATCH', 'NOT_SELECTED', 'NOT_QUALIFIED', 'ALREADY_EXISTS', 'OUTPUT_EDITED', 'INVALID', 'HTTP_401', 'HTTP_403', 'STATUS_401', 'STATUS_403')


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _qualification(records):
    flags = {}
    for record in records:
        for key, value in record.items():
            if QUALIFICATION_KEY.search(key) and isinstance(value, bool):
                flags[key] = value
    if not flags:
        return 'not stated', flags
    values = set(flags.values())
    return ('partial' if len(values) > 1 else 'qualified' if values == {True} else 'not qualified'), flags


def _refusal_signal(record):
    for key in ('event', 'state', 'status', 'code', 'errorCode'):
        value = record.get(key)
        if isinstance(value, (str, int)):
            normalized = str(value).upper().replace(' ', '_').replace('-', '_')
            if any(marker in normalized for marker in REFUSAL_MARKERS) or normalized in {'REFUSED', 'DENIED', 'FORBIDDEN'}:
                return True
    return record.get('status') in (401, 403)


def _outcome(records, is_jsonl, top_level=None):
    if not records:
        return 'incomplete', 'empty input'
    last = records[-1] if is_jsonl else (top_level or records[0])
    if _refusal_signal(last):
        return 'refused', 'explicit refusal/conflict/denial signal'
    if is_jsonl and records[0].get('event') == 'created' and 'planSHA256' in records[0]:
        total = records[0].get('totalSteps')
        if type(total) is not int or total < 1:
            return 'incomplete', 'plan stage count missing or invalid; inspect the original plan'
        events = records[1:]
        complete = len(events) == total * 2 and all(
            event.get('index') == index // 2 and
            event.get('event') == ('started' if index % 2 == 0 else 'completed')
            for index, event in enumerate(events)
        )
        return ('successful', 'all declared plan stages recorded complete') if complete else ('incomplete', 'not every declared plan stage recorded complete')
    event = last.get('event')
    state = last.get('state')
    status = last.get('status')
    if any(isinstance(value, str) and value.lower() == 'command-exited' for value in (event, state)):
        return ('successful', 'command exit 0') if last.get('exitCode') == 0 else ('incomplete', 'non-zero or missing exit code')
    if is_jsonl:
        if isinstance(event, str) and event.lower() in SUCCESS_EVENTS - {'command-exited'}:
            return 'successful', 'explicit terminal event: ' + event
        if isinstance(state, str) and state.lower() in SUCCESS_STATES:
            return 'successful', 'explicit terminal state: ' + state
        return 'incomplete', 'no successful terminal event'
    values = [v.lower() for v in (event, state, status) if isinstance(v, str)]
    if any(v in SUCCESS_STATES or 'assembled draft' in v or 'evidence preparation only' in v for v in values):
        return 'successful', 'explicit successful/draft status'
    if any(v in {'failed', 'failure', 'error', 'incomplete', 'partial', 'started', 'running', 'pending'} for v in values):
        return 'incomplete', 'explicit non-terminal/failure status'
    if any(isinstance(r.get(k), bool) for r in records for k in ('deterministicChecksPassed', 'checksPassed', 'completed')):
        bools = [r[k] for r in records for k in ('deterministicChecksPassed', 'checksPassed', 'completed') if isinstance(r.get(k), bool)]
        return ('successful', 'explicit checks completed') if all(bools) else ('incomplete', 'one or more explicit checks false')
    return 'incomplete', 'no recognised terminal result'


def inspect_input(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Input is not a regular non-symlink file: {path}')
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f'Input exceeds {MAX_FILE_BYTES} byte limit: {path}')
    raw = path.read_bytes()
    is_jsonl = path.suffix.lower() in {'.jsonl', '.ndjson'}
    top_level = None
    if is_jsonl:
        records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        if not all(isinstance(record, dict) for record in records):
            raise ValueError(f'JSONL records must be objects: {path}')
    elif path.suffix.lower() == '.json':
        parsed = json.loads(raw)
        if not isinstance(parsed, (dict, list)):
            raise ValueError(f'JSON receipt must contain an object or array: {path}')
        records = list(_walk(parsed))
        top_level = parsed[-1] if isinstance(parsed, list) and parsed and isinstance(parsed[-1], dict) else parsed if isinstance(parsed, dict) else None
    else:
        raise ValueError(f'Input must be .json or .jsonl: {path}')
    outcome, basis = _outcome(records, is_jsonl, top_level)
    technical, flags = _qualification(records)
    operation = next((r.get('kind') for r in records if isinstance(r.get('kind'), str)), None)
    if not operation:
        operation = next((r.get('step') for r in reversed(records) if isinstance(r.get('step'), str)), path.stem)
    terminal_event = next((r.get('event') or r.get('state') for r in reversed(records) if r.get('event') or r.get('state')), 'none')
    return {
        'path': str(path), 'format': 'JSONL' if is_jsonl else 'JSON', 'bytes': size,
        'sha256': hashlib.sha256(raw).hexdigest(), 'recordCount': len(records),
        'recordLabel': 'records' if is_jsonl else 'JSON objects inspected',
        'operation': operation, 'outcome': outcome, 'outcomeBasis': basis,
        'lastEvent': str(terminal_event), 'technicalQualification': technical,
        'qualificationFlags': flags,
        'humanAcceptance': 'not assessed by CLI receipts',
    }


def build_report(paths):
    if not paths or len(paths) > MAX_INPUTS:
        raise ValueError(f'Provide between 1 and {MAX_INPUTS} explicit receipt paths')
    entries = [inspect_input(path) for path in paths]
    total = sum(item['bytes'] for item in entries)
    if total > MAX_TOTAL_BYTES:
        raise ValueError(f'Combined input size exceeds {MAX_TOTAL_BYTES} bytes')
    counts = {status: sum(e['outcome'] == status for e in entries) for status in ('successful', 'incomplete', 'refused')}
    lines = [
        '# CLI assurance and status report', '',
        f'Generated: {datetime.now(timezone.utc).isoformat()}',
        f'Inputs: {len(entries)} explicit JSON/JSONL receipts; {total} bytes total.', '',
        '| Recorded outcome | Count |', '|---|---:|',
        f'| Successful | {counts["successful"]} |',
        f'| Incomplete | {counts["incomplete"]} |',
        f'| Refused | {counts["refused"]} |', '',
        'Successful means the receipt records a successful terminal operation; it does not by itself qualify the native service or prove business acceptance.', '',
    ]
    for index, item in enumerate(entries, 1):
        lines.extend([
            f'## {index}. {item["operation"]}', '',
            f'- Receipt: `{item["path"]}` ({item["format"]}, {item["bytes"]} bytes, SHA-256 `{item["sha256"]}`)',
            f'- Recorded outcome: **{item["outcome"]}** — {item["outcomeBasis"]}; final event: `{item["lastEvent"]}` ({item["recordCount"]} {item["recordLabel"]}).',
            f'- Explicit technical qualification: **{item["technicalQualification"]}**.',
        ])
        if item['qualificationFlags']:
            lines.append('- Qualification flags: ' + ', '.join(f'`{key}={str(value).lower()}`' for key, value in sorted(item['qualificationFlags'].items())) + '.')
        lines.append('- Human acceptance: **not assessed**; no reviewer, content approval or operational acceptance is inferred.')
        lines.append('')
    lines.extend([
        '## Scope', '',
        'This report reads only the explicitly supplied receipt files. It does not inspect native services, revalidate output bytes beyond hashing the supplied receipt, or infer omitted operations. Refused and incomplete entries remain evidence; correct the cause and retain a new receipt rather than overwriting them.',
    ])
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', action='append', required=True, help='Explicit JSON or JSONL receipt; repeat for each receipt')
    parser.add_argument('--output', type=Path, required=True, help='New private Markdown report path (exclusive create, mode 0600)')
    args = parser.parse_args(argv)
    try:
        report = build_report(args.input)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write(report)
            output.flush()
            os.fsync(output.fileno())
        print(report, end='')
        return 0
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f'Report refused: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
