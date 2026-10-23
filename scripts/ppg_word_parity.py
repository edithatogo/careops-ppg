"""Read-only Word package parity; native rendering remains separate evidence.

Reports contain document text/link targets and belong in private evidence storage.
"""
import io
import posixpath
import xml.etree.ElementTree as ET
from collections import Counter
from zipfile import ZipFile
from scripts.ppg_word_fallback import package_facts

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def inventory(raw):
    facts = package_facts(raw)
    with ZipFile(io.BytesIO(raw)) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    roots = {}
    for name, value in parts.items():
        if name.endswith(('.xml', '.rels')):
            if b'<!DOCTYPE' in value or b'<!ENTITY' in value:
                raise ValueError('Unsupported XML declaration')
            roots[name] = ET.fromstring(value)
    links, fields, anchors, missing = [], [], [], []
    for name, root in roots.items():
        if not name.startswith('word/') or not name.endswith('.xml'):
            continue
        relname = posixpath.join(posixpath.dirname(name), '_rels', posixpath.basename(name)+'.rels')
        rels = {r.get('Id'): r for r in roots.get(relname, [])}
        bookmarks = {n.get(W+'name') for n in root.iter(W+'bookmarkStart')}
        stack = []
        for n in root.iter():
            if n.tag == W+'fldChar':
                kind = n.get(W+'fldCharType')
                if kind == 'begin':
                    stack.append({'part': name, 'instruction': '', 'cachedResult': '', 'result': False})
                elif kind == 'separate' and stack:
                    stack[-1]['result'] = True
                elif kind == 'end' and stack:
                    f = stack.pop(); f.pop('result'); fields.append(f)
                else:
                    missing.append({'part': name, 'kind': 'unbalanced_field', 'value': kind})
            elif n.tag == W+'instrText' and stack:
                stack[-1]['instruction'] += n.text or ''
            elif n.tag == W+'t' and stack and stack[-1]['result']:
                stack[-1]['cachedResult'] += n.text or ''
            elif n.tag == W+'fldSimple':
                fields.append({'part': name, 'instruction': n.get(W+'instr', ''),
                               'cachedResult': ''.join(t.text or '' for t in n.iter(W+'t'))})
            elif n.tag == W+'hyperlink':
                rid, anchor = n.get(R+'id'), n.get(W+'anchor')
                if rid:
                    rel = rels.get(rid)
                    if rel is None:
                        missing.append({'part': name, 'kind': 'missing_link_relationship', 'value': rid})
                    else:
                        links.append({'part': name, 'target': rel.get('Target'), 'mode': rel.get('TargetMode')})
                if anchor:
                    anchors.append({'part': name, 'anchor': anchor, 'resolved': anchor in bookmarks})
        if stack:
            missing.append({'part': name, 'kind': 'unclosed_fields', 'value': len(stack)})
    return {'sha256': facts['sha256'], 'fields': fields, 'links': links,
            'anchors': anchors, 'structuralExceptions': missing,
            'externalDestinationsVerified': False, 'renderedFieldsVerified': False}


def compare(before, after):
    a, b = package_facts(before), package_facts(after)
    ai, bi = inventory(before), inventory(after)
    ah, bh = a['partHashes'], b['partHashes']
    changed = sorted(n for n in ah.keys() & bh.keys() if ah[n] != bh[n])
    def counted(items):
        return Counter(tuple(sorted(item.items())) for item in items)
    return {'beforeSha256': a['sha256'], 'afterSha256': b['sha256'],
            'exactBytes': a['sha256'] == b['sha256'],
            'addedParts': sorted(bh.keys()-ah.keys()), 'removedParts': sorted(ah.keys()-bh.keys()),
            'changedParts': changed, 'fieldsEqual': counted(ai['fields']) == counted(bi['fields']),
            'linksEqual': counted(ai['links']) == counted(bi['links']),
            'anchorsEqual': counted(ai['anchors']) == counted(bi['anchors']),
            'mediaEqual': a['mediaHashes'] == b['mediaHashes'],
            'bodyTextEqual': a['bodyText'] == b['bodyText'],
            'structuralExceptions': bi['structuralExceptions'],
            'visualParityVerified': False, 'regenerationParityVerified': False}
