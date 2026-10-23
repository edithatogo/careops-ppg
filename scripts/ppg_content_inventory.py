"""Loss-aware source inventory. Retains original bytes; never generates/rewrites Word."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, is_zipfile
import xml.etree.ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(source):
    source = Path(source)
    raw = source.read_bytes()
    result = {'schemaVersion': 1, 'sourceName': source.name, 'sourceSha256': sha(raw),
              'sourceBytes': len(raw), 'sourceAuthority': 'unverified',
              'parts': [], 'elements': [], 'warnings': [], 'contentMappingComplete': False}
    if not is_zipfile(source):
        result['elements'].append({'elementId': sha(raw)+':file', 'kind': 'whole_file',
                                   'disposition': 'retained_unmapped', 'sourceLocator': 'original-file',
                                   'targetModule': None})
        result['warnings'].append('Non-OOXML source retained whole; format-specific extraction and visual verification required.')
        return result
    with ZipFile(source) as package:
        names = package.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Ambiguous duplicate package member')
        if sum(i.file_size for i in package.infolist()) > 100_000_000:
            raise ValueError('Package exceeds bounded inventory size')
        for name in names:
            content = package.read(name)
            result['parts'].append({'part': name, 'bytes': len(content), 'sha256': sha(content),
                                    'preservation': 'inside_unchanged_original'})
            if not (name.startswith('word/') and name.endswith('.xml')):
                continue
            if b'<!DOCTYPE' in content or b'<!ENTITY' in content:
                raise ValueError('Unsupported XML declarations')
            try:
                xml = ET.fromstring(content)
            except ET.ParseError:
                result['warnings'].append('Unparseable XML retained: '+name)
                continue
            if name == 'word/document.xml':
                container = xml.find(W+'body')
                nodes = list(container) if container is not None else []
            elif any(name.startswith('word/'+prefix) for prefix in ['header','footer','comments','footnotes','endnotes']):
                nodes = list(xml)
            else:
                continue
            for index, node in enumerate(nodes):
                text = ''.join(node.itertext())
                result['elements'].append({
                    'elementId': sha(raw)+':'+name+':'+str(index),
                    'kind': node.tag.rsplit('}', 1)[-1],
                    'sourceLocator': name+'#child='+str(index),
                    'xmlSha256': sha(ET.tostring(node)), 'text': text,
                    'containsRevisions': any(e.tag in {W+'ins', W+'del'} for e in node.iter()),
                    'containsDrawing': any(e.tag in {W+'drawing', W+'pict', W+'object'} for e in node.iter()),
                    'disposition': 'retained_unmapped', 'targetModule': None})
    result['warnings'].append('Package parts are preserved, not semantically mapped. Verify layout, embedded objects, comments/revisions and source currency before claiming parity.')
    return result


def save_inventory(source, directory):
    result = inventory(source)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    original = directory / ('original'+Path(source).suffix)
    with original.open('xb') as stream:
        stream.write(Path(source).read_bytes())
    if sha(original.read_bytes()) != result['sourceSha256']:
        raise ValueError('Source changed during capture; output is incomplete')
    result['preservedOriginal'] = original.name
    with (directory/'content-inventory.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('new_output_directory', type=Path)
    args = parser.parse_args()
    result = save_inventory(args.source, args.new_output_directory)
    print(json.dumps({'parts': len(result['parts']), 'elements': len(result['elements']),
                      'contentMappingComplete': result['contentMappingComplete']}))
