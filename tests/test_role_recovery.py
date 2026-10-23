import copy,json,unittest
from scripts.ppg_role_recovery import prepare,SLOTS


class RoleRecovery(unittest.TestCase):
    def fixture(self):
        definitions=[dict(title='PPG Fictional '+slot,fields=[dict(name='RecordKey',unique=True,required=True),dict(name='Value',unique=False,required=True)]) for slot in SLOTS]
        registers={}
        for slot,spec in zip(SLOTS,definitions):
            first=dict(Title='Fictional record',RecordKey=slot,Value='original')
            final=dict(first,Value='final')
            item=dict(final,Id=1,GUID='fictional-native-guid',OData__UIVersionString='2.0',AuthorId=123)
            registers[slot]=dict(definition=spec,sourceList=dict(Id='fictional-'+slot,Title=spec['title'],EnableVersioning=True),items={'value':[item]},histories=[dict(id=1,versions={'value':[dict(final,VersionLabel='2.0'),dict(first,VersionLabel='1.0')]})],views=[])
        return dict(registers=registers),definitions

    def test_versions_and_business_identity_retained_without_platform_impersonation(self):
        source,defs=self.fixture();before=copy.deepcopy(source);plan=prepare(json.dumps(source).encode(),defs)
        self.assertEqual((plan['recordCount'],plan['versionCount']),(5,10));self.assertEqual(source,before)
        for register in plan['registers']:
            row=register['records'][0];self.assertEqual(row['sourcePlatform']['AuthorId'],123)
            self.assertNotIn('AuthorId',row['versions'][0]['record'])
            self.assertEqual([v['record']['Value'] for v in row['versions']],['original','final'])
            self.assertTrue(register['definition']['title'].startswith('PPG Recovery '))
        self.assertFalse(plan['productionBindingsChanged']);self.assertFalse(plan['originalPlatformStampsRecreated'])

    def test_partial_export_missing_original_or_latest_drift_refused(self):
        for kind in ['page','original','latest','inventory','identity']:
            source,defs=self.fixture();r=source['registers']['roles']
            if kind=='page':r['items']['@odata.nextLink']='more'
            if kind=='original':r['histories'][0]['versions']['value'].pop()
            if kind=='latest':r['items']['value'][0]['Value']='changed'
            if kind=='inventory':r['histories']=[]
            if kind=='identity':r['histories'][0]['versions']['value'][1]['RecordKey']='different'
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):prepare(json.dumps(source).encode(),defs)

    def test_schema_and_duplicate_key_or_version_refused(self):
        for kind in ['schema','key','version']:
            source,defs=self.fixture();r=source['registers']['roles']
            if kind=='schema':r['definition']=dict(r['definition'],title='Unexpected')
            if kind=='key':
                item=dict(r['items']['value'][0],Id=2);r['items']['value'].append(item)
                r['histories'].append(dict(id=2,versions=copy.deepcopy(r['histories'][0]['versions'])))
            if kind=='version':r['histories'][0]['versions']['value'].append(copy.deepcopy(r['histories'][0]['versions']['value'][0]))
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):prepare(json.dumps(source).encode(),defs)

    def test_cli_accepts_explicit_archived_definitions_without_migrating_schema(self):
        import subprocess, sys, tempfile
        from pathlib import Path
        source, definitions = self.fixture()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); inp=root/'source.json'; defs=root/'definitions.json'; out=root/'plan.json'
            inp.write_text(json.dumps(source)); defs.write_text(json.dumps({'registers':definitions}))
            args=[sys.executable,'-m','scripts.ppg_role_recovery','--input',str(inp),'--output',str(out),'--definitions',str(defs)]
            subprocess.run(args, check=True, capture_output=True)
            result=json.loads(out.read_text()); self.assertEqual(result['recordCount'],5)
            self.assertEqual(result['versionCount'],10); self.assertEqual(result['nativeWrites'],0)
            before=out.read_bytes(); retry=subprocess.run(args,capture_output=True)
            self.assertNotEqual(retry.returncode,0); self.assertEqual(out.read_bytes(),before)
            definitions[0]['title']='PPG Different schema'; defs.write_text(json.dumps(definitions)); out.unlink()
            mismatch=subprocess.run(args,capture_output=True)
            self.assertNotEqual(mismatch.returncode,0); self.assertFalse(out.exists())
