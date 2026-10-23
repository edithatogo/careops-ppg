"""Prepare an isolated role-record recovery plan; no native writes or binding changes."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

SLOTS = ['roles', 'assignments', 'appointments', 'handovers', 'snapshots']


def complete(page):
    if any(page.get(k) for k in ['odata.nextLink', '@odata.nextLink', '__next', 'nextLink']):
        raise ValueError('Incomplete recovery export')
    return page['value']


def prepare(source_bytes, definitions=None, *, slots=None,
            kind='isolated_role_recovery_plan',
            description='Fictional isolated recovery qualification. Original platform provenance is retained in recovery evidence; not live responsibilities.'):
    selected_slots = SLOTS if slots is None else slots
    source = json.loads(source_bytes)
    if set(source['registers']) != set(selected_slots):
        raise ValueError('Complete five-register recovery export required')
    if definitions is None:
        definitions = (json.loads(Path('config/role-registers.json').read_text())['registers']
                       + json.loads(Path('config/responsibility-snapshots-register.json').read_text())['registers'])
    if len(definitions) != len(selected_slots):
        raise ValueError('Five known register schemas required')
    planned = []
    for slot, definition in zip(selected_slots, definitions):
        register = source['registers'][slot]
        if register['definition'] != definition or register['sourceList']['Title'] != definition['title']:
            raise ValueError('Recovery schema/source identity differs')
        if not register['sourceList']['EnableVersioning']:
            raise ValueError('Source versioning evidence required')
        key_fields = [f['name'] for f in definition['fields'] if f['unique']]
        if len(key_fields) != 1:
            raise ValueError('One stable record key required')
        key = key_fields[0]
        fields = ['Title']+[f['name'] for f in definition['fields']]
        required = {'Title', key}|{f['name'] for f in definition['fields'] if f['required']}

        def values(row):
            # Version APIs can encode underscores in field names; never discard data.
            normalized = {k.replace('_x005f_', '_'): v for k,v in row.items()}
            if len(normalized) != len(row):
                raise ValueError('Ambiguous version field identity')
            if any(not isinstance(normalized.get(k), str) or not normalized[k] for k in required):
                raise ValueError('Missing required recovery value')
            result = {k: normalized.get(k) for k in fields}
            if any(v is not None and not isinstance(v, str) for v in result.values()):
                raise ValueError('Unsupported role-register value type')
            return result

        items = complete(register['items'])
        histories = register['histories']
        ids = [r['Id'] for r in items]
        if len(ids) != len(set(ids)) or len(histories) != len(items) or {h['id'] for h in histories} != set(ids):
            raise ValueError('Incomplete or duplicate record/history inventory')
        history_map = {h['id']: h['versions'] for h in histories}
        keys, records = set(), []
        for item in items:
            current = values(item)
            if current[key] in keys:
                raise ValueError('Duplicate stable recovery key')
            keys.add(current[key]); states = []
            for version in complete(history_map[item['Id']]):
                label = version['VersionLabel']
                if not re.fullmatch(r'[1-9][0-9]*\.0', label):
                    raise ValueError('Unsupported native version label')
                record = values(version)
                if record[key] != current[key]:
                    raise ValueError('Stable identity changed in original history')
                states.append(dict(sourceVersionLabel=label, record=record))
            states.sort(key=lambda s: int(s['sourceVersionLabel'].split('.')[0]))
            if [s['sourceVersionLabel'] for s in states] != [str(n)+'.0' for n in range(1,len(states)+1)] or not states:
                raise ValueError('Original version or contiguous history missing')
            if states[-1]['record'] != current or item.get('OData__UIVersionString') != states[-1]['sourceVersionLabel']:
                raise ValueError('Latest source/history state differs')
            records.append(dict(keyField=key, keyValue=current[key], versions=states,
                sourcePlatform={k:item.get(k) for k in ['Id','GUID','Created','Modified','AuthorId','EditorId','OData__UIVersionString']}))
        title = 'PPG Recovery '+definition['title'][4:]
        target_definition = copy.deepcopy(definition)
        target_definition.update(title=title,description=description)
        planned.append(dict(slot=slot, sourceList=copy.deepcopy(register['sourceList']),
                            definition=target_definition, records=records, views=copy.deepcopy(register['views'])))
    return dict(schemaVersion=1,kind=kind,sourceSHA256=hashlib.sha256(source_bytes).hexdigest(),
                registers=planned,recordCount=sum(len(r['records']) for r in planned),
                versionCount=sum(len(a['versions']) for r in planned for a in r['records']),
                nativeWrites=0,productionBindingsChanged=False,permissionsChanged=False,
                originalPlatformStampsRecreated=False)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--definitions', type=Path, nargs='+',
                        help='Explicit verified archived definition files; otherwise use current schemas')
    args=parser.parse_args()
    definitions = None
    if args.definitions:
        definitions = []
        for path in args.definitions:
            value = json.loads(path.read_text())
            rows = value.get('registers') if isinstance(value, dict) else value
            if not isinstance(rows, list):
                raise ValueError('Definitions must be a list or a registers list')
            definitions.extend(rows)
    result=prepare(args.input.read_bytes(), definitions)
    with args.output.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['recordCount','versionCount','nativeWrites']}))
