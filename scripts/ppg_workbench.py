"""Guided entrypoint over existing PPG commands; no shell, client or runtime."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
# Fixed allowlist: plans cannot provide executables, shell fragments or new tools.
STEPS = {
    'prepare-sources': ('python', 'scripts/ppg_source_preparation.py', ['prepare'], 'publish-sources'),
    'publish-sources': ('node', 'tools/cited-evidence/publish-sources.mjs', [], 'lookup'),
    'lookup': ('python', 'scripts/ppg_evidence_cli.py', ['lookup'], 'excerpt or evaluate-sources'),
    'excerpt': ('python', 'scripts/ppg_evidence_cli.py', ['excerpt'], 'validate'),
    'validate': ('python', 'scripts/ppg_evidence_cli.py', ['validate'], 'Inspect the validation report; no semantic approval is implied'),
    'evaluate-sources': ('python', 'scripts/ppg_source_preparation.py', ['evaluate'], 'Inspect qualification and search results separately'),
    'select-case': ('python', 'scripts/ppg_package_selection.py', [], 'prepare-package'),
    'prepare-package': ('node', 'tools/unattended-package/prepare-selected.cjs', [], 'assemble-package'),
    'assemble-package': ('node', 'tools/unattended-package/run.cjs', [], 'publish-package'),
    'publish-package': ('node', 'tools/unattended-package/publish-sharepoint.mjs', [], 'Inspect native package and receipt; DRAFT / human check required'),
    'assurance-report': ('python', 'scripts/ppg_assurance_report.py', [], 'Review technical flags separately from human acceptance'),
}


def command(step, arguments):
    runtime, script, prefix, _ = STEPS[step]
    exe = str(ROOT / '.venv/bin/python') if runtime == 'python' else shutil.which('node')
    if not exe or not Path(exe).is_file():
        raise ValueError('Required existing runtime unavailable: ' + runtime)
    return [exe, str(ROOT / script), *prefix, *arguments]


def _json_line(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def _output_digest(path):
    """Fingerprint a declared output; refuse symlinks and missing results."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Declared output may not be a symlink: ' + str(path))
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if path.is_dir():
        digest = hashlib.sha256()
        for child in sorted(path.rglob('*')):
            if child.is_symlink():
                raise ValueError('Declared output tree contains a symlink: ' + str(child))
            if child.is_file():
                digest.update(child.relative_to(path).as_posix().encode())
                digest.update(b'\0')
                digest.update(hashlib.sha256(child.read_bytes()).digest())
        return digest.hexdigest()
    raise ValueError('Declared output is missing: ' + str(path))


def _load_plan(path):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if not isinstance(plan, dict) or plan.get('schemaVersion') != 1 or not isinstance(plan.get('steps'), list) or not plan['steps']:
        raise ValueError('Plan must have schemaVersion 1 and a non-empty steps array')
    produced = set()
    for index, item in enumerate(plan['steps']):
        if not isinstance(item, dict) or not isinstance(item.get('step'), str) or item.get('step') not in STEPS or not isinstance(item.get('arguments'), list) or not all(isinstance(x, str) for x in item['arguments']):
            raise ValueError(f'Invalid step definition at index {index}')
        outputs = item.get('outputs')
        if not isinstance(outputs, list) or not outputs or not all(isinstance(x, str) and x for x in outputs):
            raise ValueError(f'Step {index} must declare its expected output paths')
        if len(set(outputs)) != len(outputs) or produced.intersection(outputs):
            raise ValueError(f'Step {index} reuses an output path declared by another step')
        produced.update(outputs)
        if item.get('stdoutArtifact') is not None and item['stdoutArtifact'] not in outputs:
            raise ValueError(f'Step {index} stdoutArtifact must also be declared in outputs')
    return plan, hashlib.sha256(raw).hexdigest()


def _append_state(path, event):
    with Path(path).open('ab') as receipt:
        receipt.write(_json_line({'utc': datetime.now(timezone.utc).isoformat(), **event}))
        receipt.flush()
        os.fsync(receipt.fileno())


def _open_state(path, plan, plan_hash, resume):
    path = Path(path)
    if not resume:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as receipt:
            receipt.write(_json_line({'schemaVersion': 1, 'planSHA256': plan_hash, 'cwd': str(Path.cwd()), 'event': 'created', 'utc': datetime.now(timezone.utc).isoformat()}))
            receipt.flush()
            os.fsync(receipt.fileno())
        return path, 0

    events = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not events or events[0].get('schemaVersion') != 1 or events[0].get('planSHA256') != plan_hash:
        raise ValueError('Resume state is empty or belongs to a different plan')
    if events[0].get('cwd') != str(Path.cwd()):
        raise ValueError('Resume must use the same working directory as the original run')
    if events[-1].get('event') == 'started':
        raise ValueError('The last stage has an unknown outcome. Reconcile its child/native evidence, then start a fresh plan at the first incomplete stage.')
    if events[-1].get('event') in {'failed', 'refused'}:
        raise ValueError('The last stage failed or was refused. Reconcile its child evidence, then start a fresh plan at the first incomplete stage.')
    next_index = 0
    cursor = 1
    while cursor < len(events):
        started = events[cursor]
        if started.get('event') != 'started' or started.get('index') != next_index or cursor + 1 >= len(events):
            raise ValueError('Resume receipt has a non-sequential or invalid event history')
        event = events[cursor + 1]
        if event.get('event') != 'completed' or event.get('index') != next_index:
            raise ValueError('Resume receipt has a non-sequential or invalid event history')
        outputs = event.get('outputs')
        expected_paths = plan['steps'][next_index]['outputs'] if next_index < len(plan['steps']) else []
        if not isinstance(outputs, dict) or set(outputs) != set(expected_paths):
            raise ValueError('Completed stage has no output fingerprints')
        for output, expected in outputs.items():
            if _output_digest(output) != expected:
                raise ValueError('A completed output changed or disappeared: ' + output)
        next_index += 1
        cursor += 2
    return path, next_index


def run_plan(plan_path, state_path, resume=False):
    plan, plan_hash = _load_plan(plan_path)
    state_path, start = _open_state(state_path, plan, plan_hash, resume)
    total = len(plan['steps'])
    print(f'Plan: {plan_path}\nRun receipt: {state_path}\nResume point: stage {start + 1} of {total}', file=sys.stderr)
    for index in range(start, total):
        item = plan['steps'][index]
        outputs = [Path(p) for p in item['outputs']]
        existing = [str(path) for path in outputs if path.exists()]
        if existing:
            _append_state(state_path, {'event': 'refused', 'index': index, 'step': item['step'], 'reason': 'declared output already exists'})
            print(f'[{index + 1}/{total}] Refused existing output(s): ' + ', '.join(existing), file=sys.stderr)
            return 1
        _append_state(state_path, {'event': 'started', 'index': index, 'step': item['step'], 'outputs': [str(path) for path in outputs]})
        print(f'[{index + 1}/{total}] Running {item["step"]}; outputs: ' + ', '.join(map(str, outputs)), file=sys.stderr, flush=True)
        try:
            cmd = command(item['step'], item['arguments'])
            artifact = item.get('stdoutArtifact')
            if artifact:
                fd = os.open(artifact, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as stdout_file:
                    result = subprocess.run(cmd, shell=False, stdout=stdout_file)
            else:
                result = subprocess.run(cmd, shell=False)
            code = result.returncode if result.returncode >= 0 else 128 - result.returncode
            if code:
                _append_state(state_path, {'event': 'failed', 'index': index, 'step': item['step'], 'exitCode': code})
                print(f'[{index + 1}/{total}] Stopped with exit {code}; preserve partial outputs and reconcile child/native evidence before retry.', file=sys.stderr)
                return code
            fingerprints = {str(path): _output_digest(path) for path in outputs}
            _append_state(state_path, {'event': 'completed', 'index': index, 'step': item['step'], 'outputs': fingerprints})
            print(f'[{index + 1}/{total}] Complete; outputs fingerprinted. Next: {STEPS[item["step"]][3]}', file=sys.stderr)
        except (OSError, ValueError) as exc:
            _append_state(state_path, {'event': 'failed', 'index': index, 'step': item['step'], 'errorType': type(exc).__name__})
            print(f'[{index + 1}/{total}] Stopped safely: {exc}. Preserve outputs and reconcile before a fresh plan.', file=sys.stderr)
            return 1
    print(f'Plan complete. Receipt: {state_path}', file=sys.stderr)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, epilog='Plan paths and child paths are relative to the current working directory.')
    p.add_argument('--plan', type=Path, help='Run every declared stage from a schemaVersion 1 JSON plan')
    p.add_argument('--state', type=Path, help='New private JSONL run receipt; required with --plan')
    p.add_argument('--resume', action='store_true', help='Resume at the next clean stage boundary after verifying prior outputs')
    p.add_argument('--receipt', type=Path, help='New private single-step attempt receipt')
    p.add_argument('step', nargs='?', choices=['guide', *STEPS])
    p.add_argument('arguments', nargs=argparse.REMAINDER)
    a = p.parse_args(argv)
    if a.plan:
        if not a.state or a.step or a.arguments or a.receipt:
            p.error('--plan requires --state and cannot be combined with a single step or --receipt')
        if a.resume and not a.state.exists():
            p.error('--resume requires an existing run receipt')
        if not a.resume and a.state.exists():
            p.error('run receipt already exists; use --resume only after a clean completed-stage boundary')
        try:
            return run_plan(a.plan, a.state, a.resume)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f'Plan refused: {exc}', file=sys.stderr)
            return 1
    if a.resume or a.state:
        p.error('--resume and --state require --plan')
    if not a.step:
        p.error('a step, guide, or --plan is required')
    if a.step == 'guide':
        print('Sources: prepare-sources -> publish-sources -> lookup -> excerpt -> validate; qualification: lookup -> evaluate-sources; packages: select-case -> prepare-package -> assemble-package -> publish-package; status: assurance-report --input RECEIPT.jsonl --output NEW_REPORT.md. For one guided run use --plan PLAN.json --state PRIVATE_RECEIPT.jsonl; add --resume only at a clean completed-stage boundary. Read docs/guided-cli.md for plans and docs/cli-assurance-report.md for report scope. Existing single-step commands remain available; there are no background runs or automatic retries, and native receipts stay authoritative.')
        return 0
    if a.arguments[:1] == ['--']:
        a.arguments = a.arguments[1:]
    if not a.arguments:
        p.error('Step arguments required; use guide or STEP --help')
    handle = None
    try:
        cmd = command(a.step, a.arguments)
        if a.receipt:
            fd = os.open(a.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            handle = os.fdopen(fd, 'w', encoding='utf-8')

        def record(state, **extra):
            if handle:
                handle.write(json.dumps({'schemaVersion': 1, 'utc': datetime.now(timezone.utc).isoformat(), 'step': a.step, 'state': state, **extra}) + '\n')
                handle.flush()
                os.fsync(handle.fileno())

        record('started')
        print('Running ' + a.step + '; existing tool guards and receipts remain authoritative.', file=sys.stderr, flush=True)
        result = subprocess.run(cmd, shell=False)
        code = result.returncode if result.returncode >= 0 else 128 - result.returncode
        record('command-exited', exitCode=code)
        if code == 0:
            print('Next: ' + STEPS[a.step][3] + '. Inspect the child report before proceeding.', file=sys.stderr)
        else:
            print('Stopped. Preserve partial artifacts; reconcile the child journal before a fresh retry attempt.', file=sys.stderr)
        return code
    except (OSError, ValueError):
        print('Entrypoint failed; check runtime, arguments and new receipt path. Preserve any started attempt and child evidence.', file=sys.stderr)
        return 1
    finally:
        if handle:
            handle.close()


if __name__ == '__main__':
    raise SystemExit(main())
