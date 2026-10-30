# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
"""Prepare explicit cross-tenant bindings for a sealed selected-record export.

Offline only: no authentication, native mutation, ACL copying or implied access.
"""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, unquote
from uuid import UUID


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def site_url(value):
    p = urlsplit(value)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.query or p.fragment or any(x in ('.', '..') for x in unquote(p.path).split('/'))):
        raise ValueError('Explicit HTTPS destination site required')
    return p


def prepare(envelope, destination=None):
    payload = envelope['payload']
    if envelope.get('sha256') != digest(payload) or payload.get('schemaVersion') != 1:
        raise ValueError('Sealed export integrity conflict')
    source_tenant = UUID(payload['sourceTenantId'])
    entities = payload['entities']
    files = payload['files']
    for key, file in files.items():
        if (not isinstance(key,str) or not key or not isinstance(file,dict)
                or not re.fullmatch(r'[a-f0-9]{64}',file.get('sha256',''))
                or type(file.get('bytes')) is not int or file['bytes'] < 0):
            raise ValueError('Valid sealed file hash and byte length required')
    record_keys = set()
    for entity, group in entities.items():
        if not group.get('fields') or not isinstance(group.get('records'), list):
            raise ValueError('Exported field contracts and records required')
        names = {f['name'] for f in group['fields']}
        typed = {f['name']: f['type'] for f in group['fields']}
        if len(names) != len(group['fields']):
            raise ValueError('Duplicate field contract')
        for row in group['records']:
            key = entity+':'+row['key']
            if key in record_keys or not row['key'] or not set(row['values']) <= names:
                raise ValueError('Duplicate identity or unknown field')
            record_keys.add(key)
            for field, value in row['values'].items():
                if value is not None and typed[field] in ('Lookup', 'User') and field not in row.get('references', {}):
                    raise ValueError('Native lookup or identity requires explicit remapping')
            if any(k in row['values'] for k in ('Id','ID','AuthorId','EditorId','Created','Modified','__metadata')):
                raise ValueError('Platform identities must remain provenance, not copied fields')
    for entity, group in entities.items():
        for row in group['records']:
            for field, ref in row.get('references', {}).items():
                if field not in row['values'] or ref.get('kind') not in ('lookup','file','identity'):
                    raise ValueError('Explicit supported reference required')
                if ref['kind'] == 'lookup' and ref['key'] not in record_keys:
                    raise ValueError('Lookup outside declared export')
                if ref['kind'] == 'file':
                    if ref['key'] not in files:
                        raise ValueError('File outside declared export')
                    if ref.get('part') not in ('url', 'sourceItemKey', 'exactVersion'):
                        raise ValueError('Unsupported file reference part')
    result = dict(exportSHA256=envelope['sha256'], nativeWrites=0, nativeRestoreVerified=False,
                  readyForNativeQualification=False, copyPermissions=False, activateAutomation=False,
                  sourcePreserved=True, unresolved=[], records=[], files=[], sourceTenantId=str(source_tenant))
    if destination is None:
        result['unresolved'] = ['destination tenant, site and bindings required']
        return result
    if UUID(destination['tenantId']) == source_tenant:
        raise ValueError('Cross-tenant destination must differ from source')
    site = site_url(destination['siteUrl'])
    def file_binding(key):
        source = files[key]
        target = destination.get('files', {}).get(key)
        if target is None:
            return None
        url = site_url(target['url'])
        if (url.netloc.lower() != site.netloc.lower()
                or not unquote(url.path).startswith(unquote(site.path).rstrip('/')+'/')
                or type(target.get('bytes')) is not int
                or target['sha256'] != source['sha256'] or target['bytes'] != source['bytes']):
            raise ValueError('Destination file location or bytes conflict')
        UUID(target['uniqueId'])
        if not isinstance(target.get('version'), str) or not target['version'].strip():
            raise ValueError('Destination file version required')
        return target
    result['destinationTenantId'] = str(UUID(destination['tenantId']))
    result['destinationSiteUrl'] = destination['siteUrl']
    for key, source in files.items():
        target = file_binding(key)
        if target is None:
            result['unresolved'].append('file:'+key)
        else:
            result['files'].append(dict(key=key, source=deepcopy(source), destination=deepcopy(target)))
    for entity, group in entities.items():
        list_id = destination.get('lists', {}).get(entity)
        if list_id is None:
            result['unresolved'].append('list:'+entity)
        else:
            UUID(list_id)
        for row in group['records']:
            values = deepcopy(row['values'])
            for field, ref in row.get('references', {}).items():
                kind, key = ref['kind'], ref['key']
                target = None
                if kind == 'lookup':
                    target = destination.get('items', {}).get(key)
                    if target is not None and (type(target) is not int or target <= 0):
                        raise ValueError('Positive destination item ID required')
                elif kind == 'identity':
                    target = destination.get('identities', {}).get(key)
                    if target is not None and (not isinstance(target, str) or not target.strip()):
                        raise ValueError('Explicit destination identity required')
                else:
                    file = file_binding(key)
                    if file:
                        part = ref['part']
                        if part == 'url': target = file['url']
                        elif part == 'sourceItemKey': target = 'fileUniqueId:'+file['uniqueId']
                        elif part == 'exactVersion':
                            target = 'SharePoint file version '+file['version']+'; SHA-256 '+file['sha256']
                        else: raise ValueError('Unsupported file reference part')
                if target is None:
                    result['unresolved'].append(entity+':'+row['key']+':'+field)
                    values[field] = None  # Never leave a source physical reference in a destination plan.
                else:
                    values[field] = target
            result['records'].append(dict(entity=entity, key=row['key'], listId=list_id, fields=values,
                provenance=dict(sourceTenantId=str(source_tenant), sourceEntity=entity, sourceKey=row['key'],
                                sourceReferences=deepcopy(row.get('references',{})),
                                retained=deepcopy(row.get('provenance',{})))))
    result['readyForNativeQualification'] = not result['unresolved']
    return result


def main():
    import argparse
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(json.loads(args.export.read_text()),
                     json.loads(args.destination.read_text()) if args.destination else None)
    fd = os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k:result[k] for k in ('nativeWrites','nativeRestoreVerified','readyForNativeQualification','unresolved')}))

if __name__ == '__main__':
    main()
