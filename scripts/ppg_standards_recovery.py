"""Plan copied recovery of the five known standards registers; no native writes."""
import argparse
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from scripts.ppg_role_recovery import complete, prepare as prepare_records

SLOTS = ['frameworks', 'requirements', 'mappings', 'crosswalks', 'relationships']


def prepare(source_bytes):
    source = json.loads(source_bytes)
    if source.get('schemaVersion') != 1 or source.get('kind') != 'standards_recovery_export':
        raise ValueError('Known standards recovery export required')
    definitions = json.loads(Path('config/standards-registers.json').read_text())['registers']
    if set(source['registers']) != set(SLOTS):
        raise ValueError('Complete five-register export required')
    for slot, definition in zip(SLOTS, definitions):
        register = source['registers'][slot]
        fields = complete(register['fields'])
        known_names = {f['name'] for f in definition['fields']}
        source_id = register['sourceList']['Id'].strip('{}').lower()
        for field in fields:
            xml = ET.fromstring(field['SchemaXml'])
            if (xml.get('SourceID', '').strip('{}').lower() == source_id
                    and field['StaticName'] not in known_names):
                raise ValueError('Additional list-owned field needs recovery mapping')
        for expected in definition['fields']:
            found = [f for f in fields if f['StaticName'] == expected['name']]
            if (len(found) != 1 or found[0]['InternalName'] != expected['name']
                    or found[0]['TypeAsString'] != expected['type']
                    or found[0]['Required'] != expected['required']
                    or found[0]['EnforceUniqueValues'] != expected['unique']):
                raise ValueError('Native standards field contract differs')
            actual_xml = ET.fromstring(found[0]['SchemaXml'])
            expected_xml = ET.fromstring(expected['schemaXml'])
            if expected['type'] == 'Choice':
                if actual_xml.get('FillInChoice', 'FALSE').upper() != 'FALSE':
                    raise ValueError('Unexpected open choice field')
                if ([e.text for e in actual_xml.findall('.//CHOICE')]
                        != [e.text for e in expected_xml.findall('.//CHOICE')]
                        or actual_xml.findtext('Default') != expected_xml.findtext('Default')):
                    raise ValueError('Native choice/default differs')
            if expected['type'] == 'Note' and actual_xml.get('RichText', 'FALSE').upper() != 'FALSE':
                raise ValueError('Unexpected rich-text standards field')
        for view in register['views']:
            if not isinstance(view['fields'].get('Items'), list):
                raise ValueError('View field inventory missing')
        if any(item.get('Attachments') for item in complete(register['items'])):
            raise ValueError('Attachments require separate recovery qualification')
    return prepare_records(source_bytes, definitions, slots=SLOTS,
        kind='isolated_standards_recovery_plan',
        description='Isolated standards recovery qualification. Original platform provenance remains in evidence; not live mappings, obligations or decisions.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.input.read_bytes())
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ['recordCount', 'versionCount', 'nativeWrites']}))
