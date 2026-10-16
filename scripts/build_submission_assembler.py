#!/usr/bin/env python3
"""Build the self-contained download; no tenant access or real data embedded."""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parents[1]

def build(output):
    source = ROOT / 'tools/submission-package'
    page = (source / 'page.html').read_text()
    code = (source / 'assembler.js').read_text()
    if '</script' in code.lower():
        raise ValueError('Unsafe inline source boundary')
    output.parent.mkdir(parents=True, exist_ok=True)
    prefill = (source / 'prefill.js').read_text()
    template = (ROOT / 'templates/review-package.md').read_text()
    if '</script' in prefill.lower() or '</script' in template.lower():
        raise ValueError('Unsafe inline prefill/template boundary')
    output.write_text(page.replace('/*ASSEMBLER*/', code).replace('/*PREFILL*/', prefill).replace('/*REVIEW_TEMPLATE*/', json.dumps(template)))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.local/submission-package/PPG-submission-assembler.html')
    build(parser.parse_args().output)
