"""Propose version-bound template correspondences; never migrate reviewer records.

Output contains source text and link targets: store privately, not in Git.
"""
import re
import xml.etree.ElementTree as ET
from collections import Counter
from zipfile import ZipFile
from scripts.ppg_content_inventory import inventory

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
HYPERLINK = re.compile(r'\bHYPERLINK\s+"([^"]+)"')


def normalise(text):
    return ' '.join(text.split())


def own_text(node):
    """Exclude nested paragraphs, which receive their own locator."""
    return ''.join((child.text or '') if child.tag in {W+'t', W+'instrText', W+'delText'}
                   else own_text(child) if child.tag != W+'p' else '' for child in node)


def reconcile(flattened, native):
    source, target = inventory(flattened), inventory(native)
    if source['sourceSha256'] == target['sourceSha256']:
        raise ValueError('Reconciliation requires distinct representations')
    units = []
    with ZipFile(native) as archive:
        for element in target['elements']:
            part, ordinal = element['sourceLocator'].split('#child=')
            root = ET.fromstring(archive.read(part))
            container = root.find(W+'body') if part == 'word/document.xml' else root
            node = list(container)[int(ordinal)]
            relpath = part.rsplit('/', 1)[0]+'/_rels/'+part.rsplit('/', 1)[1]+'.rels'
            rels = {}
            if relpath in archive.namelist():
                raw_rels = archive.read(relpath)
                if b'<!DOCTYPE' in raw_rels or b'<!ENTITY' in raw_rels:
                    raise ValueError('Unsupported relationship XML declarations')
                rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(raw_rels)}
            paragraph_indexes = {id(p): i for i, p in enumerate(node.iter(W+'p'))}
            for kind in ['p', 'tr']:
                for index, sub in enumerate(node.iter(W+kind)):
                    text = own_text(sub) if kind == 'p' else ''.join(own_text(p) for p in sub.iter(W+'p'))
                    if not normalise(text):
                        continue
                    links = sorted({rels[h.get(R+'id')] for h in sub.iter(W+'hyperlink') if h.get(R+'id') in rels})
                    units.append({'targetElementId': element['elementId'],
                                  'locator': element['sourceLocator']+f'/{kind}[{index}]',
                                  'kind': kind, 'text': text, 'links': links,
                                  'paragraphIndexes': [paragraph_indexes[id(p)] for p in sub.iter(W+'p')]})
                    if kind == 'tr':
                        paragraphs = list(sub.iter(W+'p'))
                        # The retained conversion also combines adjacent cells.
                        # Check bounded, exact spans; larger unmatched blocks stay
                        # retained rather than being approximated or truncated.
                        for length in range(2, min(4, len(paragraphs)-1)+1):
                            for start in range(len(paragraphs)-length+1):
                                selected = paragraphs[start:start+length]
                                span_links = sorted({rels[h.get(R+'id')] for p in selected
                                                     for h in p.iter(W+'hyperlink') if h.get(R+'id') in rels})
                                units.append({'targetElementId': element['elementId'],
                                              'locator': element['sourceLocator']+f'/tr[{index}]/paragraphs[{start}:{start+length}]',
                                              'kind': 'span', 'text': ''.join(own_text(p) for p in selected),
                                              'links': span_links,
                                              'paragraphIndexes': [paragraph_indexes[id(p)] for p in selected]})
    rows = []
    for element in source['elements']:
        raw = element.get('text', '')
        # textutil flattens field instructions; only the known hyperlink syntax
        # is normalised, and its target must also occur on the native unit.
        required = sorted(set(HYPERLINK.findall(raw)))
        visible = normalise(HYPERLINK.sub('', raw))
        matches = [u for u in units if visible and normalise(u['text']) == visible
                   and set(required).issubset(u['links'])]
        # Only collapse two locators covering the identical paragraph nodes.
        # Text repeated in another row/span of the same table is still ambiguous.
        distinct = {}
        for unit in matches:
            key = unit['targetElementId'], tuple(unit['paragraphIndexes'])
            distinct.setdefault(key, unit)
        matches = list(distinct.values())
        status = ('retained_blank_or_structural' if not visible else
                  'proposed_exact_correspondence' if len(matches) == 1 else
                  'retained_ambiguous' if matches else 'retained_unmatched')
        rows.append({'sourceElementId': element['elementId'], 'sourceLocator': element['sourceLocator'],
                     'sourceXmlSha256': element['xmlSha256'], 'sourceText': raw,
                     'status': status, 'candidates': matches, 'requiredLinkTargets': required,
                     'normalisation': 'whitespace_and_hyperlink_instruction_with_target_check' if required else 'whitespace_only',
                     'disposition': 'preserved_in_unchanged_source', 'accepted': False})
    reverse = []
    for element in target['elements']:
        reverse.append({'targetElementId': element['elementId'], 'targetLocator': element['sourceLocator'],
                        'sourceCandidates': [row['sourceElementId'] for row in rows
                                             if any(u['targetElementId'] == element['elementId'] for u in row['candidates'])],
                        'disposition': 'preserved_in_unchanged_native_derivative'})
    return {'schemaVersion': 1, 'sourceSha256': source['sourceSha256'], 'targetSha256': target['sourceSha256'],
            'sourceCount': len(rows), 'targetCount': len(reverse), 'sourceRows': rows, 'targetRows': reverse,
            'counts': dict(Counter(row['status'] for row in rows)),
            'allSourceElementsAccounted': len(rows) == len(source['elements']),
            'allNativeElementsAccounted': len(reverse) == len(target['elements']),
            'sourceParts': source['parts'], 'targetParts': target['parts'],
            'acceptedMapping': False, 'reviewerRecordsChanged': False, 'currentTemplateVerified': False,
            'limitations': ['Exact text correspondence is not approved semantic mapping or visual parity.',
                           'Ambiguous, blank and unmatched elements remain in their original packages.',
                           'No source IDs, reviewer sections, held-run pins or template references are migrated.',
                           'Embedded graphics require retained binary and visual evidence; text matching does not qualify them.']}
