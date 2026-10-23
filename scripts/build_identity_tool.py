"""Build the bounded, credential-free operator tool; never include native bindings."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MEMBERS = [
    'scripts/ppg_identity_triage.py', 'scripts/ppg_identity_application.py',
    'scripts/ppg_source_sync.py', 'scripts/ppg_workspace.py',
    'config/identity-proposal.schema.json', 'config/identity-application-fields.json',
    'docs/identity-triage.md',
]


def build(output: Path) -> dict:
    members = MEMBERS + [str(p.relative_to(ROOT)) for p in
                         sorted((ROOT/'templates/identity-resolution').iterdir()) if p.is_file()]
    hashes = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in members}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name in members:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, (ROOT/name).read_bytes())
        info = zipfile.ZipInfo('tool-members.json', (1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o600 << 16
        archive.writestr(info, json.dumps(hashes, indent=2)+'\n')
    return {'members': hashes, 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))


if __name__ == '__main__':
    main()
