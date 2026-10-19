"""Compile a maintained seven-field cover for the existing Standard script.

This is one-time template preparation, not a local per-job document generator.
The native Office Script fills a new, detached snapshot and assembles the pack.
"""
import hashlib
import io
import json
import zipfile
import base64
from xml.etree import ElementTree as ET
from ppg_sharepoint_cover import FIELDS, W, accepted_values, inspect_cover


def compile_cover(raw, values):
    accepted_values(values)
    # Require the maintained, blank, genuinely bound cover; never human output.
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.infolist()) > 100 or sum(x.file_size for x in z.infolist()) > 300000 or len(z.namelist()) != len(set(z.namelist())) or z.testzip():
            raise ValueError('unsafe_template')
        root = ET.fromstring(z.read('word/document.xml'))
        seen = []
        for control in root.iter(W+'sdt'):
            tag = control.find(W+'sdtPr/'+W+'tag')
            name = None if tag is None else tag.get(W+'val')
            content = control.find(W+'sdtContent')
            if name not in FIELDS or control.find(W+'sdtPr/'+W+'dataBinding') is None or content is None or ''.join(x.text or '' for x in content.iter(W+'t')) != '[Unresolved]':
                raise ValueError('blank_maintained_template_required')
            seen.append(name)
        if sorted(seen) != sorted(FIELDS):
            raise ValueError('cover_fields_mismatch')
        # The native binding validator checks store relationships and XPath even
        # when blank properties correctly fail accepted-value comparison.
        inspection = inspect_cover(raw, values)
        if not all(check['propertyEmpty'] for check in inspection['fieldChecks'].values()):
            raise ValueError('blank_template_properties_required')
        return {'templateSHA256': hashlib.sha256(raw).hexdigest(),
                'parts': [{'path': i.filename, 'base64': base64.b64encode(z.read(i)).decode(),
                           'sha256': hashlib.sha256(z.read(i)).hexdigest()} for i in z.infolist()],
                'values': values}


def inspect_snapshot(raw, values):
    accepted_values(values)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if sum(i.file_size for i in z.infolist()) > 300000 or len(z.namelist()) > 100 or z.testzip() or len(z.namelist()) != len(set(z.namelist())):
            raise ValueError('unsafe_snapshot')
        root = ET.fromstring(z.read('word/document.xml'))
        checks = {}
        for control in root.iter(W+'sdt'):
            tag = control.find(W+'sdtPr/'+W+'tag')
            name = None if tag is None else tag.get(W+'val')
            if name not in FIELDS or name in checks or control.find(W+'sdtPr/'+W+'dataBinding') is not None:
                raise ValueError('snapshot_control_invalid')
            checks[name] = ''.join(x.text or '' for x in control.find(W+'sdtContent').iter(W+'t')) == values[name]
        if set(checks) != set(FIELDS) or not all(checks.values()):
            raise ValueError('snapshot_text_mismatch')
        if 'DRAFT' not in ''.join(x.text or '' for x in root.iter(W+'t')):
            raise ValueError('draft_label_required')
        return {'route': 'standard-office-script-fixed-cover-v1', 'sha256': hashlib.sha256(raw).hexdigest(),
                'fieldChecks': checks, 'savedTextVerified': True, 'liveBindingsRemoved': True,
                'packageEligible': True, 'visualLayoutVerified': False}
