#!/usr/bin/env python3
"""Compile additive view requests; no network, record writes or authentication."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

from ppg_guided_workspace import formatter_json, row_formatter

ROOT = Path(__file__).resolve().parents[1]


def validate_paths(site, paths):
    """Require safe expression bindings and server-relative in-site paths."""
    parsed = urlsplit(site)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('Expected an HTTPS site without credentials, query or fragment')
    for value in [site, *paths]:
        if any(c in value for c in "'\"\\") or any(ord(c) < 32 for c in value) or '..' in value:
            raise ValueError('Unsafe expression binding')
    for value in paths:
        if value.startswith('//') or not value.startswith(parsed.path.rstrip('/') + '/') or '?' in value or '#' in value:
            raise ValueError('Expected a server-relative path within the site')


def compile_views(site, queue_path, readiness_path, assurance_path, fields):
    """Validate retained/current schema and bind presentation to private paths."""
    validate_paths(site, [queue_path, readiness_path, assurance_path])
    config = json.loads((ROOT / 'config/followup-views.json').read_text())
    types = {f['InternalName']: f['TypeAsString'] for f in fields}
    missing = set(config['fields']) - types.keys()
    if missing:
        raise ValueError('Missing view fields: ' + ', '.join(sorted(missing)))
    for name in ['nextAction', 'accountableRole', 'targetDate', 'caseStatus']:
        if types[name] not in ['Text', 'Note']:
            raise ValueError('Unexpected field type: ' + name)
    result = []
    focus_labels = {'action': ['Next action:', 'Source snapshot:', 'Draft/evidence reference:'],
                    'ownership': ['Recorded role:'],
                    'date': ['Target as recorded:', 'Date check:']}
    for view in config['views']:
        formatter = row_formatter(site, queue_path, readiness_path, assurance_path)
        children = formatter['rowFormatter']['children']
        def priority(child):
            label = child.get('children', [{}])[0].get('txtContent', '').strip()
            return 0 if label in focus_labels[view['focus']] else 1
        children.sort(key=priority)
        children.insert(0, {'elmType': 'div', 'style': {'margin-bottom': '12px'}, 'txtContent': view['guidance']})
        result.append({'create': {'parameters': {'Title': view['title'], 'ViewFields': config['fields'],
                       'Query': config['query'], 'PersonalView': False, 'SetAsDefaultView': False,
                       'Paged': True, 'RowLimit': 30}},
                       'formatter': {'CustomFormatter': formatter_json(formatter)}})
    return result


def verify_views(bundle, native_views):
    """Verify saved presentation properties; does not claim browser rendering."""
    def query(value):
        # SharePoint may change insignificant XML whitespace/empty-tag spelling.
        return ElementTree.canonicalize('<Query>' + value + '</Query>', strip_text=True)

    for expected in bundle:
        params = expected['create']['parameters']
        matches = [view for view in native_views if view.get('Title') == params['Title']]
        if len(matches) != 1:
            raise ValueError('Missing or duplicate follow-up view: ' + params['Title'])
        view = matches[0]
        fields = view.get('ViewFields', {}).get('Items')
        if (view.get('DefaultView') is not False
                or view.get('PersonalView') is not False
                or view.get('Paged') is not True
                or view.get('RowLimit') != params['RowLimit']
                or fields != params['ViewFields']
                or query(view.get('ViewQuery', '')) != query(params['Query'])
                or json.loads(view.get('CustomFormatter') or '{}') !=
                   json.loads(expected['formatter']['CustomFormatter'])):
            raise ValueError('Saved follow-up view drift: ' + params['Title'])
    return {'verifiedViews': len(bundle)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings', type=Path, required=True)
    parser.add_argument('--fields', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--verify-readback', type=Path, help='Check saved native view export; no network or writes.')
    args = parser.parse_args()
    bindings = json.loads(args.bindings.read_text())
    schema = json.loads(args.fields.read_text())
    bundle = compile_views(**bindings, fields=schema.get('value', schema) if isinstance(schema, dict) else schema)
    if args.verify_readback:
        native = json.loads(args.verify_readback.read_text())
        print(json.dumps(verify_views(bundle, native['value'] if isinstance(native, dict) else native)))
        return
    with args.output.open('x') as handle:
        json.dump(bundle, handle, indent=2)
        handle.write('\n')


if __name__ == '__main__':
    main()
