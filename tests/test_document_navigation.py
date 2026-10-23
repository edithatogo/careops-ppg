"""Synthetic document-control navigation and authority-boundary checks."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from ppg_document_navigation import compile_navigation, authority_label, authority_expression


class DocumentNavigationTests(unittest.TestCase):
    def setUp(self):
        self.bindings = dict(site='https://example.test/sites/demo', queue_path='/sites/demo/Lists/Cases',
                             readiness_path='/sites/demo/Lists/Ready/AllItems.aspx', assurance_path='/sites/demo/Lists/Assurance/AllItems.aspx',
                             library_path='/sites/demo/Evidence', current_view_path='/sites/demo/Evidence/current.aspx',
                             historical_view_path='/sites/demo/Evidence/history.aspx')
        self.library_fields = [{'InternalName':name,'TypeAsString':'Text'} for name in json.loads((ROOT/'config/document-navigation.json').read_text())['referenceFields']]
        types = dict(PPGCaptureKind='Choice', PPGCurrency='Choice', PPGAuthorityLink='URL', PPGCurrencyChecked='DateTime', PPGCurrencyEvidence='Note', PPGReplacesEdition='URL')
        for field in self.library_fields: field['TypeAsString'] = types.get(field['InternalName'],'Text')
        self.case_fields = [{'InternalName':name,'TypeAsString':'Text'} for name in json.loads((ROOT/'config/followup-views.json').read_text())['fields']]

    def bundle(self):
        return compile_navigation(self.bindings,self.library_fields,self.case_fields)

    def test_additive_views_keep_missing_drafts_and_unconfirmed_references(self):
        bundle = self.bundle()
        for view in bundle.values():
            self.assertFalse(view['create']['parameters']['SetAsDefaultView'])
            self.assertFalse(view['create']['parameters']['PersonalView'])
        children = json.loads(bundle['case']['formatter']['CustomFormatter'])['rowFormatter']['children']
        self.assertEqual(children[1]['children'][0]['txtContent'],'Draft/evidence reference: ')
        self.assertNotIn('<Where>',bundle['case']['create']['parameters']['Query'])
        text = bundle['library']['formatter']['CustomFormatter']
        self.assertIn('including unresolved conflicts',text)
        self.assertIn('not source edition',text)
        self.assertIn('not issue authority',text)
        self.assertNotIn('onclick',text.lower())

    def test_capture_query_includes_root_and_children_but_not_adjacent_folders(self):
        where = ElementTree.fromstring('<Query>'+self.bundle()['library']['create']['parameters']['Query']+'</Query>').find('Where')[0]
        def match(node,row):
            if node.tag == 'And':return all(match(c,row) for c in node)
            if node.tag == 'Or':return any(match(c,row) for c in node)
            value = row.get(node.find('FieldRef').attrib['Name'])
            if node.tag == 'IsNotNull':return value not in [None,'']
            expected = node.find('Value').text
            return str(value)==expected if node.tag=='Eq' else str(value).startswith(expected)
        root = '/sites/demo/Evidence/Captured Policy Archive'
        for path,expected in [(root,True),(root+'/subfolder',True),(root+'-other',False),('/sites/demo/Evidence/Templates',False)]:
            row = dict(FileDirRef=path,FSObjType=0,PPGCaptureSHA256='fictional-hash')
            self.assertEqual(match(where,row),expected)
        self.assertFalse(match(where,dict(FileDirRef=root,FSObjType=0)))
        self.assertFalse(match(where,dict(FileDirRef=root,FSObjType=1,PPGCaptureSHA256='fictional-hash')))

    def test_recorded_currency_never_proves_issuance(self):
        rows = [{},{'PPGCaptureKind':'Supporting source page','PPGCurrency':'Verified current'},
                {'PPGCurrency':'unexpected'}, {'PPGCurrency':'Verified current'},
                {'PPGCurrency':'Verified superseded'}]
        for currency in ['Verified current','Verified superseded','Verified withdrawn']:
            rows.append(dict(PPGCurrency=currency, PPGAuthorityLink='https://example.test/policy', PPGCurrencyChecked='2026-10-18', PPGCurrencyEvidence='Fictional finding'))
        payload=[dict(formatter={'rowFormatter':{'elmType':'span','txtContent':authority_expression()}}, row=row, now='2026-10-18') for row in rows]
        result=subprocess.run(['node',str(ROOT/'tests/status_formatter_probe.cjs')],input=json.dumps(payload),text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout),[authority_label(row) for row in rows])
        self.assertEqual(authority_label({}),'Captured reference — authority unconfirmed')
        self.assertIn('unresolved',authority_label({'PPGCurrency':'Verified current'}))
        self.assertIn('verify issued source',authority_label(rows[-3]))

    def test_schema_and_cross_site_bindings_refuse(self):
        self.bindings['historical_view_path']='//elsewhere.test/history'
        with self.assertRaises(ValueError): self.bundle()
        self.setUp();self.library_fields.pop()
        with self.assertRaises(ValueError): self.bundle()
        self.setUp();self.library_fields[0]['TypeAsString']='URL'
        # ID is not a new metadata field; explicitly checked types are semantic ones.
        next(f for f in self.library_fields if f['InternalName']=='PPGCurrency')['TypeAsString']='Text'
        with self.assertRaises(ValueError): self.bundle()


if __name__ == '__main__':unittest.main()
