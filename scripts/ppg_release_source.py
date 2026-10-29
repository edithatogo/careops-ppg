#!/usr/bin/env python3
"""Verify and materialise the bounded PPG solution source; never deploy or send mail."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re

import sys
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from powerplatform_validation import loads as strict_loads, validate_flow, validate_members, dependency_checks, report, inspect_zip, component_map

try:
    from .check_email_safety import email_actions
except ImportError:  # Direct script execution uses the scripts directory.
    from check_email_safety import email_actions

TOKEN = re.compile(r'__PPG_BINDING_\d{5}__')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative_path(name: str) -> Path:
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or '..' in p.parts or '\\' in name
            or ':' in name or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise ValueError('Unsafe release path')
    return Path(*p.parts)


def target_is_workflow(name: str) -> bool:
    return name.lower().startswith('workflows/') and name.lower().endswith('.json')


def verify(source: Path) -> dict:
    if source.is_symlink():
        raise ValueError('Symlink source refused')
    source = source.resolve()
    manifest = strict_loads((source / 'release.json').read_text())
    if (manifest.get('schemaVersion') != 1 or not manifest.get('files')
            or not manifest.get('releaseId') or not manifest.get('solutionVersion')):
        raise ValueError('Invalid release manifest')
    declared = set()
    used = set()
    targets = set()
    for item in manifest['files']:
        name = relative_path(item['template'])
        path = source / name
        if (str(name) in declared or path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(source)):
            raise ValueError('Missing, duplicate or unsafe release member')
        declared.add(str(name))
        content = path.read_bytes()
        if len(content) > 5 * 1024 * 1024 or digest(content) != item['sha256']:
            raise ValueError('Release source hash mismatch')
        target = item['target']
        relative_path(target)
        if target.casefold() in targets:
            raise ValueError('Duplicate release target')
        targets.add(target.casefold())
        used.update(TOKEN.findall(content.decode('utf-8') + target))
    actual = {str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
    if actual != declared | {'release.json'} or any(p.is_symlink() for p in source.rglob('*')):
        raise ValueError('Unexpected release member or symlink')
    if any(not isinstance(v, dict) or set(v) != {'kind', 'private'}
           or v.get('private') is not True or not isinstance(v.get('kind'), str)
           for v in manifest.get('bindings', {}).values()):
        raise ValueError('Invalid private binding declaration')
    if used != set(manifest.get('bindings', {})) or any(not TOKEN.fullmatch(k) for k in used):
        raise ValueError('Binding declaration differs from source')
    return manifest


def current_dependency_checks():
    root = Path(__file__).resolve().parents[1]
    source_manifest = strict_loads((root / '.careops/module.json').read_bytes())
    return dependency_checks(source_manifest.get('authoringAssurance', {}).get('externalDependencies', []), root)


def materialise(source: Path, settings: Path, output: Path, *, package_type: str = 'Unmanaged') -> dict:
    manifest = verify(source)
    if package_type not in ('Unmanaged', 'Managed'):
        raise ValueError('Invalid package type')
    # These exact target values are intentionally kept outside version control.
    if settings.is_symlink() or '.local' not in settings.resolve().parts:
        raise ValueError('Private bindings must stay under .local')
    values = strict_loads(settings.read_text())
    if (values.get('schemaVersion') != 1 or values.get('releaseId') != manifest['releaseId']
            or set(values.get('values', {})) != set(manifest['bindings'])):
        raise ValueError('Wrong release or incomplete private bindings')
    bindings = values['values']
    if any(not isinstance(v, str) or TOKEN.search(v) for v in bindings.values()):
        raise ValueError('Invalid private binding value')
    if output.exists() or output.is_symlink() or '.local' not in output.resolve().parts:
        raise ValueError('Use a new private output directory')
    outputs = {}
    for item in manifest['files']:
        substitute = lambda text: TOKEN.sub(lambda match: bindings[match.group()], text)
        name = str(relative_path(substitute(item['target'])))
        key = name.casefold()
        if key in outputs:
            raise ValueError('Private bindings collide at output')
        content = substitute((source / relative_path(item['template'])).read_bytes().decode('utf-8')).encode()
        if TOKEN.search(content.decode()):
            raise ValueError('Unresolved private binding')
        if name == 'Other/Solution.xml' and package_type == 'Managed':
            if content.count(b'<Managed>0</Managed>') != 1:
                raise ValueError('Unexpected managed flag in common source')
            content = content.replace(b'<Managed>0</Managed>', b'<Managed>1</Managed>')
        # Hydrated source must be valid PAC XML/JSON before any pack/import step.
        if name.endswith('.json'):
            flow = strict_loads(content)
            if email_actions(flow):
                raise ValueError('Email-capable flow refused by release route')
            if target_is_workflow(name) and validate_flow(flow)['status'] == 'FAIL':
                raise ValueError('Invalid workflow structure')
        elif name.endswith('.xml'):
            import xml.etree.ElementTree as ET
            ET.fromstring(content)
        else:
            raise ValueError('Unexpected hydrated member type')
        outputs[key] = (name, content)
    if package_type == 'Managed' and not any(n == 'Other/Solution.xml' for n, _ in outputs.values()):
        raise ValueError('Missing solution manifest for managed package')
    members = {name: content for name, content in outputs.values()}
    assurance = validate_members(members) if any(n.lower().startswith('workflows/') for n in members) else report([])
    assurance['checks'].extend(current_dependency_checks())
    if 'externalDependencies' in manifest:
        assurance['checks'].extend(dependency_checks(manifest['externalDependencies'], source))
    if assurance['status'] == 'FAIL' or any(c['outcome'] == 'fail' for c in assurance['checks']):
        raise ValueError('Solution or external dependency validation failed')
    output.mkdir(parents=True, mode=0o700)
    hashes = {}
    for name, content in outputs.values():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(content)
        hashes[name] = digest(content)
    return {'releaseId': manifest['releaseId'], 'solutionVersion': manifest['solutionVersion'],
            'files': hashes, 'packageType': package_type, 'private': True, 'nativeWrites': 0, 'emailsSent': 0,
            'deploymentOrRuntimeAccepted': False, 'assurance': assurance,
            'componentMap': [{'source': name, **component_map(strict_loads(content))} for name, content in members.items() if target_is_workflow(name)]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--bindings', type=Path)
    p.add_argument('--package', type=Path, help='Validate an existing solution ZIP without materialising or importing')
    p.add_argument('--deployment-settings', type=Path)
    p.add_argument('--component-map', action='store_true', help='Emit sanitized source component map; no native claims')
    p.add_argument('--output', type=Path)
    p.add_argument('--package-type', choices=('Unmanaged', 'Managed'), default='Unmanaged')
    args = p.parse_args()
    if args.package:
        if args.bindings or args.output:
            p.error('--package cannot be combined with materialisation')
        result = inspect_zip(args.package, args.deployment_settings)
        print(json.dumps(result))
        return int(result['status'] == 'FAIL')
    if args.bindings is None and args.output is None:
        m = verify(args.source)
        components = [{'source': item['template'], 'target': item['target'], 'sha256': item['sha256']} for item in m['files']]
        checks = current_dependency_checks()
        result = report(checks, releaseId=m['releaseId'], files=len(m['files']), bindings=len(m['bindings']), nativeWrites=0)
        if args.component_map:
            result['components'] = components
        print(json.dumps(result))
        return int(result['status'] == 'FAIL')
    elif args.bindings is not None and args.output is not None:
        receipt = args.output.parent / (args.output.name + '-receipt.json')
        if receipt.exists() or receipt.is_symlink():
            raise ValueError('Existing private receipt retained; choose a new output')
        result = materialise(args.source, args.bindings, args.output, package_type=args.package_type)
        with os.fdopen(os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            json.dump(result, stream, indent=2)
        print(json.dumps({'releaseId': result['releaseId'], 'files': len(result['files']), 'nativeWrites': 0}))
    else:
        p.error('--bindings and --output must be used together')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
