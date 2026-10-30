import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as E
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_source_installation import build,schemas


def fixture():
    conn=lambda api:{'id':'/providers/Microsoft.PowerApps/apis/shared_'+api,'connectionName':'fictional-'+api,'source':'Embedded'}
    lists={key:f'00000000-0000-4000-8000-{i:012d}' for i,key in enumerate(schemas(),1)}
    source={'key':'fictional-feed','publisher':'Example','name':'Updates','feedUrl':'https://example.org/feed','fallbackUrl':'https://example.org','linkDomains':['example.org']}
    contracts=json.loads((Path(__file__).resolve().parents[1]/'config/hospital-datasets.json').read_text())
    return {'schemaVersion':1,'solutionName':'PPGSourceCollection','publisherPrefix':'ppg',
            'bindings':{'site':'https://example.sharepoint.com/sites/ppg','lists':lists,
                        'connections':{'sharepoint':conn('sharepointonline'),'rss':conn('rss'),'outlook':conn('office365'),'onedrive':conn('onedriveforbusiness')}},
            'collectors':[{'key':'example-feed','type':'rss','source':source},
                          {'key':'example-news','type':'newsletter','source':{**source,'key':'fictional-news'},'binding':{'folderId':'fictional-folder','senders':['publisher@example.org'],'subjectContains':'Example newsletter'}},
                          {'key':'example-internal','type':'sharepoint','source':{**source,'key':'fictional-internal'},'binding':{'sourceSite':'https://example.sharepoint.com/sites/source','sourceListId':'00000000-0000-4000-8000-000000000099','sourceTitle':'Fictional safety register'}},
                          {'key':'hospital','type':'hospital','attribution':'Fictional fixture only','sources':[{'key':x['key'],'name':x['title'],'url':'https://example.org/'+x['key']} for x in contracts]}]}


class InstallationTests(unittest.TestCase):
    def test_stopped_complete_package_and_stable_ids(self):
        with tempfile.TemporaryDirectory() as t:
            a=Path(t)/'.local/a';b=Path(t)/'.local/b';settings=fixture()
            one=build(settings,a);two=build(settings,b)
            self.assertEqual(one['files'],two['files'])
            self.assertEqual(len(one['datasets']),5)
            self.assertEqual(len(one['flows']),4)
            for p in (a/'Workflows').glob('*.json'):
                f=json.loads(p.read_text());self.assertEqual(f['properties']['state'],'Stopped')
                self.assertFalse(f['properties']['flowFailureAlertSubscribed'])
                actions=json.dumps(f['properties']['definition']['actions'])
                self.assertNotIn(settings['bindings']['site'],actions)
                self.assertIn('connectionReferenceLogicalName',json.dumps(f))
                meta=E.parse(str(p)+'.data.xml');self.assertEqual(meta.findtext('StateCode'),'0')
            with self.assertRaises(ValueError):build(settings,a)
    def test_duplicate_collector_refused_before_output(self):
        s=fixture();s['collectors'].append(s['collectors'][0])
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'.local/out'
            with self.assertRaises(ValueError):build(s,p)
            self.assertFalse(p.exists())
    def test_schema_preserves_source_types_and_human_notes(self):
        s=schemas();self.assertEqual(len(s),5)
        for key,d in s.items():
            self.assertTrue(d['enableVersioning'])
            if key.startswith('qh-'):
                fields={f['name']:f for f in d['fields']}
                self.assertTrue(fields['SourceKey']['unique'])
                self.assertEqual(fields['FacilityCode']['type'],'Text')
                self.assertEqual(fields['Notes']['type'],'Note')

if __name__=='__main__':unittest.main()
