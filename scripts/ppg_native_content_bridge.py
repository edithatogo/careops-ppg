"""Read-only, version-bound source-to-maintained-Word navigation proposals.

Output includes document text and belongs in private evidence storage.
"""
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from scripts.ppg_content_inventory import inventory, W


def elements(path, captured):
    rows = []
    with ZipFile(path) as package:
        containers = {}
        for item in captured['elements']:
            part, ordinal = item['sourceLocator'].split('#child=')
            if part not in containers:
                root = ET.fromstring(package.read(part))
                container = root.find(W+'body') if part == 'word/document.xml' else root
                containers[part] = list(container)
            node = containers[part][int(ordinal)]
            text = ''.join(n.text or '' for n in node.iter()
                           if n.tag in {W+'t', W+'delText'})
            revisions = [(n.tag, tuple(sorted(n.attrib.items())), ET.tostring(n).decode())
                         for n in node.iter() if n.tag in {W+'ins', W+'del'}]
            rows.append(dict(item, part=part, visibleText=text,
                             fieldInstructions=''.join(n.text or '' for n in node.iter(W+'instrText')),
                             revisionXml=revisions))
    return rows


def bridge(source, maintained, section_map):
    """Never pick an arbitrary duplicate or treat text equality as formatting parity."""
    source, maintained = Path(source), Path(maintained)
    before = source.read_bytes(), maintained.read_bytes()
    old, new = inventory(source), inventory(maintained)
    if old['sourceSha256'] == new['sourceSha256']:
        raise ValueError('Expected distinct source and maintained representations')
    expected = [e['elementId'] for e in old['elements']]
    supplied = [r['sourceElementId'] for r in section_map]
    if len(supplied) != len(set(supplied)) or set(supplied) != set(expected):
        raise ValueError('Section map must account for the exact source version once')
    modules = {r['sourceElementId']: r.get('proposedModule') for r in section_map}
    targets = elements(maintained, new)
    rows = []
    for item in elements(source, old):
        candidates = [t for t in targets if
                      (t['part'], t['kind'], t['visibleText']) ==
                      (item['part'], item['kind'], item['visibleText'])]
        # Empty text is never sufficient to align structural/image-only nodes.
        status = ('retained_structural' if not item['visibleText'].strip() else
                  'proposed_exact_text_location' if len(candidates) == 1 else
                  'retained_ambiguous' if candidates else 'retained_difference')
        rows.append(dict(sourceElementId=item['elementId'], sourceLocator=item['sourceLocator'],
                         proposedModule=modules[item['elementId']], visibleText=item['visibleText'],
                         status=status, accepted=False,
                         candidates=[dict(nativeElementId=t['elementId'], nativeLocator=t['sourceLocator'],
                                          fieldInstructionsEqual=t['fieldInstructions'] == item['fieldInstructions'],
                                          revisionXmlEqual=t['revisionXml'] == item['revisionXml'],
                                          drawingPresenceEqual=t['containsDrawing'] == item['containsDrawing'])
                                     for t in candidates],
                         disposition='preserved_in_source_and_maintained_packages'))
    if before != (source.read_bytes(), maintained.read_bytes()):
        raise ValueError('Input changed during navigation preparation')
    return dict(schemaVersion=1, kind='source_to_maintained_word_navigation',
                sourceSha256=old['sourceSha256'], maintainedSha256=new['sourceSha256'],
                sourceCount=len(rows), nativeCount=len(targets), rows=rows,
                counts=dict(Counter(r['status'] for r in rows)),
                nativeRows=[dict(nativeElementId=t['elementId'], nativeLocator=t['sourceLocator'],
                                 sourceCandidates=[r['sourceElementId'] for r in rows if any(
                                     c['nativeElementId'] == t['elementId'] for c in r['candidates'])])
                            for t in targets],
                sourceParts=old['parts'], nativeParts=new['parts'],
                acceptedMapping=False, reviewerRecordsChanged=False, wordRewritten=False,
                limitations=['XML locators are package locations, not Word bookmarks or stable page numbers.',
                             'Exact visible text does not establish formatting, image, field or revision fidelity.',
                             'Duplicate and structural candidates remain unresolved; no positional pairing is inferred.',
                             'Current authority, saved field refresh and regeneration remain unverified.'])
