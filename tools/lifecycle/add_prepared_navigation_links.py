# SPDX-License-Identifier: Apache-2.0
"""Append explicit navigation to a separate pinned DOCX copy; no native I/O.

Existing text, controls and saved edits remain byte-preserved in document.xml.
Only appended paragraphs and external hyperlink relationships are introduced.
This does not qualify Word rendering, link access or native preparation admission.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from xml.sax.saxutils import escape, quoteattr
import xml.etree.ElementTree as ET
import xml.parsers.expat
import zipfile

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
MARKER = 'PPGPreparedNavigationV1'
CHANGED = {'word/document.xml', 'word/_rels/document.xml.rels'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def target_key(url):
    value = urlsplit(url)
    return (value.scheme.lower(), value.netloc.lower(),
            unquote(unquote(value.path)), value.query, value.fragment)


def validate_links(site_url: str, links: list[dict]) -> list[dict]:
    site = urlsplit(site_url)
    if (site.scheme != 'https' or not site.hostname or site.username or site.password
            or site.query or site.fragment or site.port not in (None, 443)
            or not site.path.startswith('/') or site.path.endswith('/')
            or unquote(site.path) != site.path
            or any(part in ('.', '..') for part in site.path.split('/'))
            or any(ord(c) < 32 for c in site_url)):
        raise ValueError('Exact HTTPS site without credentials/query/trailing slash required')
    if not isinstance(links, list) or not 1 <= len(links) <= 8:
        raise ValueError('One to eight explicit navigation links required')
    out = []
    for link in links:
        if not isinstance(link, dict) or set(link) != {'label', 'url'}:
            raise ValueError('Exact label/url link contract required')
        label, url = link['label'], link['url']
        if (not isinstance(label, str) or not label.strip() or len(label) > 160
                or any(ord(c) < 32 for c in label)):
            raise ValueError('Nonempty single-line label required')
        if not isinstance(url, str) or any(ord(c) < 32 for c in url):
            raise ValueError('Literal HTTPS link required')
        target = urlsplit(url)
        decoded = unquote(unquote(target.path))
        if (target.scheme != site.scheme or target.netloc != site.netloc
                or target.username or target.password
                or not target.path.startswith(site.path + '/')
                or any(part in ('.', '..') for part in decoded.split('/'))
                or '\\' in decoded or any(ord(c) < 32 for c in decoded)
                or not decoded.startswith(site.path + '/')):
            raise ValueError('Navigation target must stay within the exact site')
        out.append(dict(label=label, url=url))
    if len({target_key(x['url']) for x in out}) != len(out):
        raise ValueError('Duplicate navigation targets refused')
    return out


def build_copy(raw: bytes, expected_sha256: str, site_url: str, links: list[dict]):
    if sha(raw) != expected_sha256:
        raise ValueError('Saved source hash changed')
    links = validate_links(site_url, links)
    with zipfile.ZipFile(io.BytesIO(raw)) as source:
        entries = source.infolist()
        names = [x.filename for x in entries]
        if (len(names) != len(set(names)) or len(names) > 4096
                or sum(x.file_size for x in entries) > 64 * 1024 * 1024
                or any(x.flag_bits & 1 for x in entries)
                or not CHANGED <= set(names)):
            raise ValueError('Incomplete, duplicated, encrypted or oversized package')
        if source.testzip() is not None:
            raise ValueError('Invalid package CRC')
        parts = {name: source.read(name) for name in names}
        if any('vbaProject' in name for name in names):
            raise ValueError('Macro packages unsupported')
        document = parts['word/document.xml'].decode('utf-8')
        relationships = parts['word/_rels/document.xml.rels'].decode('utf-8')
        root = ET.fromstring(document)
        relroot = ET.fromstring(relationships)
        body = root.find(f'{{{W}}}body')
        if (root.tag != f'{{{W}}}document' or body is None
                or relroot.tag != f'{{{P}}}Relationships'
                or f'xmlns:w="{W}"' not in document
                or MARKER in document):
            raise ValueError('Reviewed Word namespace/body or unmodified source required')
        ids = [x.get('Id') for x in relroot]
        if None in ids or len(ids) != len(set(ids)):
            raise ValueError('Relationship identities incomplete or duplicated')
        existing_targets = {target_key(x.get('Target', '')) for x in relroot
                            if x.get('Type') == R + '/hyperlink'}
        if any(target_key(link['url']) in existing_targets for link in links):
            raise ValueError('Target already linked; request only missing navigation')
        # Locate the direct body child, not a historical sectPr nested inside
        # tracked section changes. Expat reports byte offsets without rewriting XML.
        parser = xml.parsers.expat.ParserCreate(namespace_separator='}')
        stack, offsets = [], {}
        def start(name, attrs):
            if stack == [W + '}document', W + '}body'] and name == W + '}sectPr':
                offsets['section'] = parser.CurrentByteIndex
            stack.append(name)
        def end(name):
            if name == W + '}body':
                offsets['bodyEnd'] = parser.CurrentByteIndex
            stack.pop()
        parser.StartElementHandler, parser.EndElementHandler = start, end
        parser.Parse(parts['word/document.xml'], True)
        key = 'section' if list(body) and list(body)[-1].tag == f'{{{W}}}sectPr' else 'bodyEnd'
        bytepoint = offsets.get(key)
        if bytepoint is None or (key == 'bodyEnd' and not parts['word/document.xml'][bytepoint:].startswith(b'</w:body>')):
            raise ValueError('Exact body insertion point unavailable')
        point = len(parts['word/document.xml'][:bytepoint].decode('utf-8'))
        closing = re.search(r'</(?P<prefix>[A-Za-z_][\w.-]*:)?Relationships>\s*$', relationships)
        if closing is None:
            raise ValueError('Exact relationship insertion point unavailable')
        prefix = closing['prefix'] or ''
        paragraphs = [f'<!--{MARKER}-->']
        added_rels = []
        for index, link in enumerate(links, 1):
            rid = f'ppgNavigation{index}'
            if rid in ids:
                raise ValueError('Navigation relationship identity already exists')
            paragraphs.append('<w:p><w:hyperlink xmlns:r=' + quoteattr(R) + ' r:id=' + quoteattr(rid)
                + ' w:history="1"><w:r><w:rPr><w:color w:val="0563C1"/>'
                + '<w:u w:val="single"/></w:rPr><w:t>'
                + escape(link['label']) + '</w:t></w:r></w:hyperlink></w:p>')
            added_rels.append('<' + prefix + 'Relationship Id=' + quoteattr(rid)
                + ' Type=' + quoteattr(R + '/hyperlink') + ' Target='
                + quoteattr(link['url']) + ' TargetMode="External"/>')
        addition = ''.join(paragraphs)
        new_document = document[:point] + addition + document[point:]
        new_relationships = (relationships[:closing.start()] + ''.join(added_rels)
                             + relationships[closing.start():])
        ET.fromstring(new_document)
        ET.fromstring(new_relationships)
        assert new_document.replace(addition, '', 1) == document
        parts['word/document.xml'] = new_document.encode('utf-8')
        parts['word/_rels/document.xml.rels'] = new_relationships.encode('utf-8')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as output:
            output.comment = source.comment
            for entry in entries:
                output.writestr(entry, parts[entry.filename])
    result = stream.getvalue()
    return result, {'sourceSHA256': sha(raw), 'outputSHA256': sha(result),
        'linksAdded': len(links), 'originalDocumentBytesPreservedAroundAddition': True,
        'otherMembersPreserved': len(parts) - 2, 'nativeRequests': 0,
        'nativeRenderingQualified': False, 'workingLinkAccessQualified': False,
        'preparationAdmissionQualified': False}


def write_copy(source: Path, output: Path, expected_sha256: str, site_url: str, links):
    if source.resolve() == output.resolve():
        raise ValueError('Separate output required; never overwrite saved edits')
    result, receipt = build_copy(source.read_bytes(), expected_sha256, site_url, links)
    try:
        with output.open('xb') as stream:
            stream.write(result)
        receipt['outputCreated'] = True
    except FileExistsError:
        if output.is_symlink() or output.read_bytes() != result:
            raise ValueError('Existing output changed; preserve it') from None
        receipt['outputCreated'] = False
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    if set(contract) != {'sourceSHA256', 'siteUrl', 'links'}:
        raise ValueError('Exact sourceSHA256/siteUrl/links contract required')
    print(json.dumps(write_copy(args.source, args.output, contract['sourceSHA256'],
                               contract['siteUrl'], contract['links']), indent=2))


if __name__ == '__main__':
    main()
