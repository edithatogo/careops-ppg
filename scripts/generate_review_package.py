#!/usr/bin/env python3
"""Populate the review template offline; preserve source bytes and draft status."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def generate(template: Path, inputs: Path, output: Path) -> dict:
    template_bytes, input_bytes = template.read_bytes(), inputs.read_bytes()
    text = template_bytes.decode('utf-8')
    statuses = [line.strip() for line in text.splitlines()
                if line.strip().startswith('Status:')]
    if statuses != ['Status: DRAFT / AWAITING REVIEW']:
        raise ValueError('Template must retain exactly one draft status line')
    data = json.loads(input_bytes)
    if not isinstance(data, dict):
        raise ValueError('Inputs must be a JSON object of template fields')
    keys = set(re.findall(r'\{\{([A-Za-z_][A-Za-z_0-9]*)\}\}', text))
    if set(data) != keys or not all(isinstance(value, str) for value in data.values()):
        raise ValueError('Supply exactly the template fields, each as a string')
    if any('{{' in value or '}}' in value for value in data.values()):
        raise ValueError('Unresolved template markers in inputs')
    if not all(data[key].strip() for key in ('case_title', 'CaseUID', 'source_snapshot', 'version')):
        raise ValueError('Existing case, baseline and candidate references are required')
    if output.resolve() in (template.resolve(), inputs.resolve()):
        raise ValueError('Output must be separate from template and inputs')
    rendered = re.sub(r'\{\{([A-Za-z_][A-Za-z_0-9]*)\}\}', lambda m: data[m[1]], text)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation: replay cannot overwrite an existing candidate or user edit.
    with output.open('x', encoding='utf-8') as stream:
        stream.write(rendered)
    if template.read_bytes() != template_bytes or inputs.read_bytes() != input_bytes:
        raise RuntimeError('Input changed during generation; inspect the candidate before use')
    result = output.read_bytes()
    if result != rendered.encode('utf-8'):
        raise RuntimeError('Output readback mismatch')
    return {'status': 'DRAFT / AWAITING REVIEW', 'output': str(output),
            'outputSha256': hashlib.sha256(result).hexdigest(),
            'templateSha256': hashlib.sha256(template_bytes).hexdigest(),
            'inputsSha256': hashlib.sha256(input_bytes).hexdigest(),
            'inputsUnchanged': True, 'humanReadinessObtained': False,
            'nativeWrites': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template', required=True, type=Path)
    parser.add_argument('--inputs', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(generate(args.template, args.inputs, args.output), indent=2))
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f'Package not generated: {error}\n')
