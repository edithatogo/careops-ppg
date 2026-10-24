import sys,unittest,io,zipfile,hashlib
from pathlib import Path
from xml.sax.saxutils import escape
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_sharepoint_cover import FIELDS,inspect_cover,admit_cover,build_qualification_flow


def fixture(rendered=True,changed=False):
    values={name: 'Accepted café — '+name for name in FIELDS}
    values['PPGCoverReviewDate']='2026-10-19'
    values['PPGCoverRecordedOwner']='Unresolved'
    props='<p:properties xmlns:p="http://schemas.microsoft.com/office/2006/metadata/properties"><documentManagement>'+''.join('<f:'+k+' xmlns:f="urn:fictional">'+escape(v)+'</f:'+k+'>' for k,v in values.items())+'</documentManagement></p:properties>'
    controls=''
    for k,v in values.items():
        text='[Unresolved]' if not rendered else v
        if changed and k=='PPGCoverTitle':text='Human edit'
        controls+=f'''<w:sdt><w:sdtPr><w:tag w:val="{k}"/><w:dataBinding w:storeItemID="{{TEST}}" w:prefixMappings="xmlns:p='http://schemas.microsoft.com/office/2006/metadata/properties' xmlns:f='urn:fictional'" w:xpath="/p:properties[1]/documentManagement[1]/f:{k}[1]"/></w:sdtPr><w:sdtContent><w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p></w:sdtContent></w:sdt>'''
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+controls+'</w:body></w:document>')
        z.writestr('customXml/item1.xml',props)
        z.writestr('customXml/itemProps1.xml','<ds:datastoreItem xmlns:ds="http://schemas.openxmlformats.org/officeDocument/2006/customXml" ds:itemID="{TEST}"/>')
        z.writestr('customXml/_rels/item1.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXmlProps" Target="itemProps1.xml"/></Relationships>')
    return stream.getvalue(),values

class CoverTests(unittest.TestCase):
    def test_existing_expression_actions_do_not_break_primitive_selection(self):
        import copy
        _,values=fixture()
        base={'properties':{'displayName':'Fictional','connectionReferences':{'shared_sharepointonline':{'tier':'Standard','id':'/providers/Microsoft.PowerApps/apis/shared_sharepointonline'}},'definition':{'actions':{
            'Compose':{'type':'Compose','inputs':'@triggerBody()'},
            'Empty':{'type':'Compose','inputs':None},
            'Read':{'type':'OpenApiConnection','inputs':{'host':{'operationId':'HttpRequest','connectionName':'shared_sharepointonline'},'authentication':"@parameters('$authentication')",'parameters':{}}}}}}}
        before=copy.deepcopy(base)
        pin={'ServerRelativeUrl':'/sites/test/template.docx','UniqueId':'22222222-2222-4222-8222-222222222222','ETag':'"1"'}
        args=('https://example.sharepoint.com/sites/test','11111111-1111-4111-8111-111111111111',pin,'/sites/test/outputs/template.docx',values)
        result=build_qualification_flow(base,*args)
        self.assertEqual(base,before)
        self.assertNotIn('Compose',result['properties']['definition']['actions'])
        self.assertEqual(result['properties']['definition']['actions']['Read_template']['inputs']['host']['operationId'],'HttpRequest')
        self.assertNotIn('authentication',result['properties']['definition']['actions']['Read_template']['inputs'])
        del base['properties']['definition']['actions']['Read']
        with self.assertRaisesRegex(ValueError,'qualified_sharepoint_primitive_required'):
            build_qualification_flow(base,*args)

    def test_metadata_alone_not_admitted(self):
        raw,v=fixture(False);r=inspect_cover(raw,v)
        self.assertTrue(r['propertiesVerified']);self.assertFalse(r['packageEligible'])
        with self.assertRaisesRegex(ValueError,'native_refresh'):admit_cover(raw,v,hashlib.sha256(raw).hexdigest())
    def test_exact_rendered_revision_admitted(self):
        raw,v=fixture();member=admit_cover(raw,v,hashlib.sha256(raw).hexdigest())
        import base64
        self.assertEqual(base64.b64decode(member['base64']),raw)
    def test_human_edit_preserved_by_refusal(self):
        raw,v=fixture(changed=True)
        with self.assertRaisesRegex(ValueError,'native_refresh'):admit_cover(raw,v,hashlib.sha256(raw).hexdigest())
    def test_changed_revision_refused(self):
        raw,v=fixture()
        with self.assertRaisesRegex(ValueError,'new_revision'):admit_cover(raw,v,'0'*64)
    def test_missing_and_oversize_values_refused(self):
        raw,v=fixture();v['PPGCoverTitle']=''
        with self.assertRaises(ValueError):inspect_cover(raw,v)
        v['PPGCoverTitle']='x'*256
        with self.assertRaises(ValueError):inspect_cover(raw,v)
    def test_probe_is_standard_copy_only_and_preserves_template(self):
        _,values=fixture();base={'properties':{'displayName':'Fictional','connectionReferences':{'shared_sharepointonline':{'tier':'Standard','id':'/providers/Microsoft.PowerApps/apis/shared_sharepointonline'}},'definition':{'actions':{'Read':{'type':'OpenApiConnection','inputs':{'host':{'operationId':'HttpRequest','connectionName':'shared_sharepointonline'},'parameters':{}}}}}}}
        pin={'ServerRelativeUrl':'/sites/test/template.docx','UniqueId':'22222222-2222-4222-8222-222222222222','ETag':'"1"'}
        flow=build_qualification_flow(base,'https://example.sharepoint.com/sites/test','11111111-1111-4111-8111-111111111111',pin,'/sites/test/outputs/template.docx',values)
        self.assertEqual(flow['properties']['state'],'Stopped')
        copy=flow['properties']['definition']['actions']['Copy_cover']['inputs']
        self.assertEqual(copy['host']['operationId'],'CopyFileAsync')
        self.assertEqual(copy['parameters']['parameters/nameConflictBehavior'],0)
        self.assertEqual(copy['parameters']['parameters/destinationFolderPath'],'/outputs')
        self.assertEqual(copy['retryPolicy'],{'type':'none'})
        actions=flow['properties']['definition']['actions']
        self.assertEqual(actions['Read_template_metadata']['inputs']['parameters']['path'],'/template.docx')
        self.assertEqual(actions['Copy_cover']['runAfter'],{'Read_template_metadata':['Succeeded']})
        self.assertEqual(actions['Read_template_after_copy']['runAfter'],{'Copy_cover':['Succeeded']})
        self.assertEqual(actions['Read_cover_item']['runAfter'],{'Require_same_template_revision':['Succeeded']})
        self.assertEqual(actions['Require_same_template_revision']['expression']['and'][1]['equals'],
            ["@body('Read_template_after_copy')?['ETag']",pin['ETag']])
        write=actions['Populate_cover_properties']
        self.assertEqual(write['runAfter'],{'Require_cover_item_etag':['Succeeded']})
        headers=write['inputs']['parameters']['parameters/headers']
        self.assertEqual(headers['IF-MATCH'],"@outputs('Read_cover_item')?['headers']?['ETag']")
        self.assertEqual(headers['X-HTTP-Method'],'MERGE')
        import json
        self.assertEqual(json.loads(write['inputs']['parameters']['parameters/body']),values)
        self.assertIn('Refuse_missing_etag',actions['Require_cover_item_etag']['else']['actions'])
        self.assertIn('Refuse_metadata_mismatch',actions['Require_saved_values']['else']['actions'])
        self.assertEqual(len(actions['Require_saved_values']['expression']['and']),len(FIELDS))
        self.assertEqual(actions['Require_saved_values']['runAfter'],{'Read_saved_properties':['Succeeded']})
        for a in actions.values():
            if a['type']=='OpenApiConnection':
                self.assertEqual(a['inputs']['retryPolicy'],{'type':'none'})
                self.assertEqual(a['inputs']['host']['connectionName'],'shared_sharepointonline')
        self.assertEqual(flow['properties']['connectionReferences'],base['properties']['connectionReferences'])
        self.assertEqual(list(flow['properties']['definition']['triggers']),['manual'])
        with self.assertRaisesRegex(ValueError,'preserve_template'):build_qualification_flow(base,'https://example.sharepoint.com/sites/test','11111111-1111-4111-8111-111111111111',pin,pin['ServerRelativeUrl'],values)
        for source,target,error in [
            ('/sites/test/Forms/template.docx','/sites/test/outputs/template.docx','ordinary_execution_template_required'),
            ('/sites/test/template.docx','/sites/test/outputs/renamed.docx','copy_requires_same_docx_filename'),
            ('/sites/test/template.pdf','/sites/test/outputs/template.pdf','copy_requires_same_docx_filename'),
            ('/sites/test/template.docx','/sites/other/template.docx','invalid_cover_path')]:
            with self.subTest(source=source,target=target):
                with self.assertRaisesRegex(ValueError,error):
                    build_qualification_flow(base,'https://example.sharepoint.com/sites/test','11111111-1111-4111-8111-111111111111',dict(pin,ServerRelativeUrl=source),target,values)
        with self.assertRaisesRegex(ValueError,'template_etag_required'):
            build_qualification_flow(base,'https://example.sharepoint.com/sites/test','11111111-1111-4111-8111-111111111111',dict(pin,ETag=''),'/sites/test/outputs/template.docx',values)

if __name__=='__main__':unittest.main()
