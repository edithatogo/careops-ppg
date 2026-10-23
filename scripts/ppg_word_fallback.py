"""Verify the maintained Word/metadata/section-map fallback without rewriting Word."""
import hashlib
import io
from collections import Counter
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from scripts.ppg_structured_content import prepare

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def package_facts(raw):
    with ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip() is not None:
            raise ValueError('Invalid or ambiguous Word package')
        if sum(i.file_size for i in archive.infolist()) > 100_000_000:
            raise ValueError('Word package exceeds inventory bound')
        parts = {name: archive.read(name) for name in names}
    roots = {}
    for name, value in parts.items():
        if name.startswith('word/') and name.endswith('.xml'):
            if b'<!DOCTYPE' in value or b'<!ENTITY' in value:
                raise ValueError('Unsupported XML declarations')
            roots[name] = ET.fromstring(value)
    body = roots['word/document.xml']
    containers = [r.find(W+'body') if name == 'word/document.xml' else r
                  for name, r in roots.items() if name == 'word/document.xml' or
                  name.startswith(('word/header', 'word/footer', 'word/comments', 'word/footnotes', 'word/endnotes'))]
    return {'revisionBearingElements': sum(any(n.tag in {W+'ins', W+'del'} for n in child.iter())
                                          for container in containers if container is not None for child in container),
            'sha256': digest(raw), 'partHashes': {n: digest(v) for n, v in parts.items()},
            'mediaHashes': sorted(digest(v) for n, v in parts.items() if n.startswith('word/media/')),
            'bodyTables': len(list(body.iter(W+'tbl'))),
            'tables': sum(len(list(r.iter(W+'tbl'))) for r in roots.values()),
            'comments': sum(len(list(r.iter(W+'comment'))) for r in roots.values()),
            'revisionRuns': sum(sum(n.tag in {W+'ins', W+'del'} for n in r.iter()) for r in roots.values()),
            'bodyText': ''.join(n.text or '' for n in body.iter(W+'t'))}


def verify(document_uid, source_inventory, template_inventory, modules, inspection,
           template, maintained_word, prior_maintained_word, provenance):
    if (digest(inspection) != source_inventory['sourceSha256']
            or digest(template) != template_inventory['sourceSha256']):
        raise ValueError('Source/template bytes differ from inventory')
    source = prepare(document_uid, source_inventory, modules, provenance)
    candidate = prepare('template-candidate', template_inventory, modules,
                        {'originalSourceSha256': digest(template)})
    records = source['records']
    source_ids = [e['elementId'] for e in source_inventory['elements']]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError('Duplicate source element')
    section_map = [dict(sourceElementId=r['record']['SourceElementId'],
                        sourceOrdinal=r['record']['SourceOrdinal'],
                        sourceLocator=source_inventory['elements'][i]['sourceLocator'],
                        proposedModule=r['record']['ProposedModule'],
                        disposition='retained_in_original_with_proposed_module',
                        authority='unverified', wordLocator=None,
                        locatorStatus='source inspection locator; native conversion requires reconciliation')
                   for i, r in enumerate(records)]
    matrix = []
    for module in modules['modules']:
        key = module['key']
        ids = [r['record']['SourceElementId'] for r in records if r['record']['ProposedModule'] == key]
        template_ids = [r['record']['SourceElementId'] for r in candidate['records'] if r['record']['ProposedModule'] == key]
        matrix.append(dict(module=key, sourceElementIds=ids, templateElementIds=template_ids,
                           mappingStatus='heading_based_proposal', mandatoryRuleVerified=False))
    current, prior = package_facts(maintained_word), package_facts(prior_maintained_word)
    inspection_facts = package_facts(inspection)
    return dict(schemaVersion=1, kind='maintained_word_fallback_verification',
                route='maintained Word plus structured metadata and separate section map',
                generationPerformed=False, wordRewritten=False,
                currentVersionVerification='open_nonblocking',
                sourceSha256=digest(inspection), templateSha256=digest(template),
                maintainedWord=current, previousMaintainedWordSha256=prior['sha256'],
                maintainedWordUnchanged=current['sha256'] == prior['sha256'],
                inspectionMediaAllRetained=not (Counter(inspection_facts['mediaHashes'])-Counter(current['mediaHashes'])),
                inspectionTableCount=inspection_facts['tables'],
                sourceElementCount=len(source_ids), accountedSourceElements=len(section_map),
                templateElementCount=candidate['elementCount'],
                sourceSectionMap=section_map, candidateModuleCrosswalk=matrix,
                templateCapture=candidate, requiredness='unverified',
                sourceAndTemplateAuthorityVerified=False, completeVisualParityVerified=False,
                regeneratedOutputParityVerified=False,
                limitations=[
                    'The maintained Word is retained exactly; source inspection locators are not asserted to be native Word bookmarks.',
                    'Heading-based module correspondence is a proposal, not an accepted complete template remap.',
                    'Original binary source and inspection remain preserved separately; conversion text/field-order and revision-segmentation exceptions remain open.',
                    'No field refresh, link interaction, complete visual parity or regeneration is inferred from package equality.',
                    'Human edits remain in Word and reviewer-owned List fields; no regeneration or write-back occurs.'])
