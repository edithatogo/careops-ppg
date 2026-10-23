import copy
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree as ET

from scripts.ppg_standards_recovery import prepare, SLOTS


class StandardsRecovery(unittest.TestCase):
    def fixture(self):
        definitions=json.loads(Path('config/standards-registers.json').read_text())['registers']
        registers={}
        for slot,definition in zip(SLOTS,definitions):
            row={'Title':'Fictional standards recovery record'}
            fields=[]
            for f in definition['fields']:
                row[f['name']]=('fictional-'+slot+'-'+f['name']) if f['required'] else None
                if f['type']=='Choice':row[f['name']]=ET.fromstring(f['schemaXml']).findtext('.//CHOICE')
                fields.append(dict(StaticName=f['name'],InternalName=f['name'],TypeAsString=f['type'],
                                   Required=f['required'],EnforceUniqueValues=f['unique'],SchemaXml=f['schemaXml']))
            item=dict(row,Id=1,GUID='fictional-original-guid',AuthorId=123,Attachments=False,OData__UIVersionString='1.0')
            empty=slot=='crosswalks'
            registers[slot]=dict(definition=definition,sourceList=dict(Title=definition['title'],Id='fictional-'+slot,EnableVersioning=True),fields={'value':fields},
                items={'value':[] if empty else [item]},histories=[] if empty else [dict(id=1,versions={'value':[dict(row,VersionLabel='1.0')]})],views=[])
        return dict(schemaVersion=1,kind='standards_recovery_export',registers=registers)

    def test_five_schemas_and_empty_register_preserve_values_without_platform_impersonation(self):
        source=self.fixture();before=copy.deepcopy(source);plan=prepare(json.dumps(source).encode())
        self.assertEqual((plan['recordCount'],plan['versionCount']),(4,4));self.assertEqual(source,before)
        self.assertEqual(plan['kind'],'isolated_standards_recovery_plan')
        for r in plan['registers']:
            self.assertTrue(r['definition']['title'].startswith('PPG Recovery '))
            self.assertNotIn('Fictional',r['definition']['description'])
            for record in r['records']:
                self.assertEqual(record['sourcePlatform']['AuthorId'],123)
                self.assertNotIn('AuthorId',record['versions'][0]['record'])
        self.assertFalse(plan['productionBindingsChanged']);self.assertFalse(plan['permissionsChanged'])

    def test_native_schema_choices_rich_text_and_attachments_refused(self):
        for case in ['field','unique','choice','richtext','attachment','kind','extra']:
            s=self.fixture();r=s['registers']['frameworks']
            if case=='field':r['fields']['value'][0]['InternalName']='different'
            if case=='unique':r['fields']['value'][0]['EnforceUniqueValues']=False
            if case=='choice':
                f=next(f for f in r['fields']['value'] if f['TypeAsString']=='Choice');f['SchemaXml']=f['SchemaXml'].replace('Published','Unverified')
            if case=='richtext':
                f=next(f for f in r['fields']['value'] if f['TypeAsString']=='Note');f['SchemaXml']=f['SchemaXml'].replace('RichText="FALSE"','RichText="TRUE"')
            if case=='attachment':r['items']['value'][0]['Attachments']=True
            if case=='kind':s['kind']='different-export'
            if case=='extra':
                r['fields']['value'].append(dict(StaticName='Extra',SchemaXml=
                    '<Field SourceID="'+r['sourceList']['Id']+'" Name="Extra" Type="Text" />'))
            with self.subTest(case=case):
                with self.assertRaises(ValueError):prepare(json.dumps(s).encode())

    def test_partial_export_missing_history_and_changed_latest_refused(self):
        for case in ['page','history','latest']:
            s=self.fixture();r=s['registers']['requirements']
            if case=='page':r['items']['@odata.nextLink']='more'
            if case=='history':r['histories']=[]
            if case=='latest':r['items']['value'][0]['Title']='Human revision'
            with self.subTest(case=case):
                with self.assertRaises(ValueError):prepare(json.dumps(s).encode())
