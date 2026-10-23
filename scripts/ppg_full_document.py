"""One-time compilation of the maintained review DOCX for the Standard kernel.

Does not populate a case or call M365. Runtime inputs and output stay native.
"""
import base64
import hashlib
import io
import zipfile
from xml.dom import minidom

SCALARS = ('case_title CaseUID source_snapshot version intended_result source_manifest '
           'draft_links_and_changes ownership_and_implementation decision_route '
           'candidate_reference reviewer_response operative_confirmation role_acceptance '
           'review_findings decision_evidence next_action measures documentKind '
           'sourceSHA256 templateVersion outputRevision includedRecordIDs OptionalContent').split()
GROUPS = {
    'comparison_rows': ['ComparisonSource', 'ComparisonGoverningSource', 'ComparisonControl', 'ComparisonChange', 'ComparisonGap'],
    'consultation_rows': ['ConsultationRole', 'ConsultationQuestion', 'ConsultationVersion', 'ConsultationResponse'],
}
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def compile_template(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        if len(infos) > 100 or sum(i.file_size for i in infos) > 300000 or len({i.filename.casefold() for i in infos}) != len(infos) or z.testzip():
            raise ValueError('unsafe_full_template')
        if any(i.filename.startswith('/') or '..' in i.filename.split('/') or '\\' in i.filename for i in infos):
            raise ValueError('unsafe_full_template_path')
        doc = minidom.parseString(z.read('word/document.xml'))
        controls = list(doc.getElementsByTagNameNS(W, 'sdt'))
        expected = SCALARS + list(GROUPS) + sum(GROUPS.values(), [])
        seen = []
        slots = {}
        for control in controls:
            props = next(n for n in control.childNodes if n.nodeType == n.ELEMENT_NODE and n.localName == 'sdtPr')
            tags = props.getElementsByTagNameNS(W, 'tag')
            if not tags:  # Only the two unnamed repeat-item wrappers may exist.
                if not props.getElementsByTagName('w15:repeatingSectionItem'):
                    raise ValueError('unexpected_unnamed_control')
                continue
            name = tags[0].getAttributeNS(W, 'val')
            if name not in expected or name in seen or props.getElementsByTagNameNS(W, 'dataBinding'):
                raise ValueError('full_control_inventory')
            seen.append(name)
            if name in GROUPS:
                continue
            content = next(n for n in control.childNodes if n.nodeType == n.ELEMENT_NODE and n.localName == 'sdtContent')
            text = ''.join(n.firstChild.data if n.firstChild else '' for n in content.getElementsByTagNameNS(W, 't'))
            if text != '[' + name + ']':
                raise ValueError('blank_full_template_required')
            is_block = bool(content.getElementsByTagNameNS(W, 'p'))
            ppr = content.getElementsByTagNameNS(W, 'pPr')
            slots[name] = {'block': is_block, 'paragraphProperties': ppr[0].toxml() if ppr else ''}
            for child in list(content.childNodes):
                content.removeChild(child)
            content.appendChild(doc.createComment('PPG_VALUE:' + name))
        if sorted(seen) != sorted(expected):
            raise ValueError('full_control_inventory')
        repeats = {}
        for control in controls:
            props = next(n for n in control.childNodes if n.nodeType == n.ELEMENT_NODE and n.localName == 'sdtPr')
            tags = props.getElementsByTagNameNS(W, 'tag')
            name = tags[0].getAttributeNS(W, 'val') if tags else ''
            if name not in GROUPS:
                continue
            content = next(n for n in control.childNodes if n.nodeType == n.ELEMENT_NODE and n.localName == 'sdtContent')
            items = [n for n in content.childNodes if n.nodeType == n.ELEMENT_NODE]
            if len(items) != 1 or items[0].localName != 'sdt':
                raise ValueError('repeat_prototype_invalid')
            item = items[0].toxml()
            control.parentNode.replaceChild(doc.createComment('PPG_REPEAT:' + name), control)
            content.replaceChild(doc.createComment('PPG_ITEMS'), items[0])
            repeats[name] = {'fields': GROUPS[name], 'wrapper': control.toxml(), 'item': item}
        xml = doc.toxml()
        if 'DRAFT' not in xml or 'PPG_' not in xml or '<!DOCTYPE' in xml:
            raise ValueError('full_template_shape')
        return {'kind': 'PPG-full-review-template-v1', 'templateSHA256': hashlib.sha256(raw).hexdigest(),
                'mainXml': xml, 'slots': slots, 'repeats': repeats,
                'parts': [{'path': i.filename, 'base64': base64.b64encode(z.read(i)).decode(),
                           'sha256': hashlib.sha256(z.read(i)).hexdigest()} for i in infos]}
