"""Preserve exact source bytes inside a hash-verified ZIP; never overwrite output."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


def preserve(sources, target):
    paths = [Path(p) for p in sources]
    names = [p.name for p in paths]
    if not names or len(names) != len(set(names)) or 'SHA256-manifest.json' in names:
        raise ValueError('Source names must be nonempty, distinct and not the reserved manifest name')
    snapshots = [(p.name, p.read_bytes()) for p in paths]
    manifest = {'schemaVersion': 1, 'members': [dict(name=name, bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest()) for name, raw in sorted(snapshots)]}
    payloads = sorted(snapshots)+[('SHA256-manifest.json', (json.dumps(manifest, indent=2)+'\n').encode())]
    target = Path(target)
    created = False
    try:
        with target.open('xb') as output:
            created = True
            with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
                for name, raw in payloads:
                    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = ZIP_DEFLATED
                    info.external_attr = 0o600 << 16
                    archive.writestr(info, raw)
        with ZipFile(target) as archive:
            for record in manifest['members']:
                if hashlib.sha256(archive.read(record['name'])).hexdigest() != record['sha256']:
                    raise ValueError('Archive verification failed')
        return {'archiveSha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                'membersVerified': len(snapshots), 'manifest': manifest}
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('new_archive', type=Path)
    parser.add_argument('sources', nargs='+', type=Path)
    args = parser.parse_args()
    receipt = preserve(args.sources, args.new_archive)
    print(json.dumps({'archiveSha256': receipt['archiveSha256'],
                      'membersVerified': receipt['membersVerified']}))
