# SPDX-License-Identifier: Apache-2.0
"""Saved-edit preservation and explicit navigation; no native requests."""
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

PATH = Path(__file__).resolve().parents[1] / 'tools/lifecycle/add_prepared_navigation_links.py'
spec = importlib.util.spec_from_file_location('prepared_navigation', PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SITE = 'https://example.invalid/site'
LINKS = [{'label': 'Source & evidence', 'url': SITE + '/source?a=1&b=2'},
         {'label': 'Baseline', 'url': SITE + '/baseline.json'}]


def package(document=None, relationships=None):
    stream = io.BytesIO()
    document = document or (f'<w:document xmlns:w="{m.W}" xmlns:r="{m.R}"><w:body>'
        '<w:p><w:sdt><w:sdtPr><w:tag w:val="OptionalContent"/></w:sdtPr>'
        '<w:sdtContent><w:r><w:t>Saved human edit — retained</w:t></w:r>'
        '</w:sdtContent></w:sdt></w:p><w:sectPr/></w:body></w:document>')
    relationships = relationships or f'<Relationships xmlns="{m.P}"></Relationships>'
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('word/document.xml', document)
        z.writestr('word/_rels/document.xml.rels', relationships)
        z.writestr('customXml/item1.xml', '<private>Existing metadata &amp; edits</private>')
        z.comment = b'retained comment'
    return stream.getvalue()


class NavigationTests(unittest.TestCase):
    def test_saved_xml_controls_other_members_and_final_section_preserved(self):
        raw = package()
        out, receipt = m.build_copy(raw, m.sha(raw), SITE, LINKS)
        with zipfile.ZipFile(io.BytesIO(raw)) as before, zipfile.ZipFile(io.BytesIO(out)) as after:
            self.assertIsNone(after.testzip())
            self.assertEqual(before.namelist(), after.namelist())
            self.assertEqual(before.comment, after.comment)
            self.assertEqual(before.read('customXml/item1.xml'), after.read('customXml/item1.xml'))
            old = before.read('word/document.xml').decode()
            new = after.read('word/document.xml').decode()
            self.assertEqual(new.split('<!--' + m.MARKER + '-->')[0], old.split('<w:sectPr')[0])
            self.assertTrue(new.endswith(old[old.index('<w:sectPr'):]))
            body = ET.fromstring(new).find(f'{{{m.W}}}body')
            self.assertEqual(list(body)[-1].tag, f'{{{m.W}}}sectPr')
            tags = body.findall(f'.//{{{m.W}}}tag')
            self.assertEqual([x.get(f'{{{m.W}}}val') for x in tags], ['OptionalContent'])
            rels = list(ET.fromstring(after.read('word/_rels/document.xml.rels')))
            self.assertEqual([r.get('Target') for r in rels], [r['url'] for r in LINKS])
            self.assertEqual([r.get('TargetMode') for r in rels], ['External'] * 2)
            for properties in body.findall(f'.//{{{m.W}}}hyperlink/{{{m.W}}}r/{{{m.W}}}rPr'):
                self.assertEqual([x.tag for x in properties], [f'{{{m.W}}}color', f'{{{m.W}}}u'])
        self.assertFalse(receipt['workingLinkAccessQualified'])
        self.assertFalse(receipt['preparationAdmissionQualified'])

    def test_same_inputs_replay_without_overwrite_and_edited_output_refuses(self):
        raw = package()
        with tempfile.TemporaryDirectory() as d:
            source, output = Path(d)/'saved.docx', Path(d)/'navigation.docx'
            source.write_bytes(raw)
            self.assertTrue(m.write_copy(source, output, m.sha(raw), SITE, LINKS)['outputCreated'])
            observed = output.stat().st_mtime_ns
            self.assertFalse(m.write_copy(source, output, m.sha(raw), SITE, LINKS)['outputCreated'])
            self.assertEqual(output.stat().st_mtime_ns, observed)
            output.write_bytes(b'human changed output')
            with self.assertRaisesRegex(ValueError, 'Existing output changed'):
                m.write_copy(source, output, m.sha(raw), SITE, LINKS)
            self.assertEqual(output.read_bytes(), b'human changed output')
            self.assertEqual(source.read_bytes(), raw)
            with self.assertRaisesRegex(ValueError, 'Separate output'):
                m.write_copy(source, source, m.sha(raw), SITE, LINKS)

    def test_changed_source_and_already_derived_source_refuse(self):
        raw = package()
        with self.assertRaisesRegex(ValueError, 'hash changed'):
            m.build_copy(raw, '0'*64, SITE, LINKS)
        derived, _ = m.build_copy(raw, m.sha(raw), SITE, LINKS)
        with self.assertRaisesRegex(ValueError, 'unmodified source'):
            m.build_copy(derived, m.sha(derived), SITE, LINKS)

    def test_external_credentials_traversal_and_unsafe_labels_refuse(self):
        for url in ['http://example.invalid/site/source', 'https://evil.invalid/site/source',
                    SITE+'/../escape', SITE+'/%252e%252e/escape',
                    'https://user:pass@example.invalid/site/source',
                    SITE+'/%5c..%5cescape', SITE+'/%0dheader', 'javascript:alert(1)']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.validate_links(SITE, [{'label':'Source', 'url':url}])
        for links in [[], LINKS*2, [{'label':'x','url':SITE+'/saved file'}, {'label':'y','url':SITE+'/saved%20file'}], [{'label':'\n', 'url':SITE+'/x'}],
                      [{'label':'x', 'url':SITE+'/x', 'extra':True}]]:
            with self.subTest(links=links), self.assertRaises(ValueError):
                m.validate_links(SITE, links)

    def test_duplicate_relationship_ids_and_reserved_navigation_ids_refuse(self):
        for ids in [['rId1','rId1'], ['ppgNavigation1']]:
            rels = f'<Relationships xmlns="{m.P}">' + ''.join(
                f'<Relationship Id="{rid}" Type="x" Target="x"/>' for rid in ids) + '</Relationships>'
            raw = package(relationships=rels)
            with self.assertRaises(ValueError):
                m.build_copy(raw, m.sha(raw), SITE, LINKS)

    def test_newer_manually_linked_source_refuses_duplicate_target(self):
        for target, requested in [(SITE+'/source', SITE+'/source'),
                                  (SITE+'/saved file', SITE+'/saved%20file')]:
            relationships = (f'<Relationships xmlns="{m.P}"><Relationship Id="existingLink" '
                             f'Type="{m.R}/hyperlink" Target="{target}" TargetMode="External"/>'
                             '</Relationships>')
            raw = package(relationships=relationships)
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'already linked'):
                m.build_copy(raw, m.sha(raw), SITE, [{'label':'Source','url':requested}])

    def test_unrelated_existing_hyperlink_is_preserved_with_new_navigation(self):
        relationships = (f'<Relationships xmlns="{m.P}"><Relationship Id="existingLink" '
                         f'Type="{m.R}/hyperlink" Target="{SITE}/earlier" TargetMode="External"/>'
                         '</Relationships>')
        raw = package(relationships=relationships)
        out, _ = m.build_copy(raw, m.sha(raw), SITE, LINKS)
        with zipfile.ZipFile(io.BytesIO(out)) as z:
            relationships = list(ET.fromstring(z.read('word/_rels/document.xml.rels')))
            self.assertEqual(relationships[0].get('Id'), 'existingLink')
            self.assertEqual(relationships[0].get('Target'), SITE+'/earlier')
            self.assertEqual(len(relationships), 3)

    def test_package_crc_and_missing_namespace_refuse(self):
        raw = package(document=f'<w:document xmlns:w="{m.W}"><w:body/></w:document>')
        with self.assertRaises(ValueError):
            m.build_copy(raw, m.sha(raw), SITE, LINKS)
        with self.assertRaises(zipfile.BadZipFile):
            m.build_copy(b'not a package', m.sha(b'not a package'), SITE, LINKS)

    def test_tracked_section_history_stays_inside_original_final_section(self):
        document = (f'<w:document xmlns:w="{m.W}"><w:body><w:p><w:r>'
                    '<w:t>Saved Unicode — edit</w:t></w:r></w:p><w:sectPr>'
                    '<w:sectPrChange><w:sectPr/></w:sectPrChange>'
                    '</w:sectPr></w:body></w:document>')
        raw = package(document=document)
        out, _ = m.build_copy(raw, m.sha(raw), SITE, LINKS)
        with zipfile.ZipFile(io.BytesIO(out)) as z:
            body = ET.fromstring(z.read('word/document.xml')).find(f'{{{m.W}}}body')
            section = list(body)[-1]
            self.assertEqual(section.tag, f'{{{m.W}}}sectPr')
            self.assertEqual(len(section.findall(f'.//{{{m.W}}}hyperlink')), 0)
            self.assertEqual(len(body.findall(f'{{{m.W}}}p')), 3)

    def test_word_removed_unused_relationship_namespace_is_not_rewritten(self):
        document = f'<w:document xmlns:w="{m.W}"><w:body><w:p/><w:sectPr/></w:body></w:document>'
        raw = package(document=document)
        out, _ = m.build_copy(raw, m.sha(raw), SITE, LINKS)
        with zipfile.ZipFile(io.BytesIO(out)) as z:
            new = z.read('word/document.xml').decode()
            self.assertTrue(new.startswith(document.split('<w:sectPr')[0]))
            self.assertEqual(len(ET.fromstring(new).findall(f'.//{{{m.W}}}hyperlink')), 2)

    def test_document_without_section_properties_and_prefixed_relationships(self):
        document = f'<w:document xmlns:w="{m.W}" xmlns:r="{m.R}"><w:body><w:p/></w:body></w:document>'
        raw = package(document=document, relationships=f'<p:Relationships xmlns:p="{m.P}"></p:Relationships>')
        out, _ = m.build_copy(raw, m.sha(raw), SITE, LINKS)
        with zipfile.ZipFile(io.BytesIO(out)) as z:
            rels = ET.fromstring(z.read('word/_rels/document.xml.rels'))
            self.assertEqual(len(rels), 2)
            self.assertTrue(all(r.tag == f'{{{m.P}}}Relationship' for r in rels))


if __name__ == '__main__':
    unittest.main()
