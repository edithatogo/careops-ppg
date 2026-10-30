import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_public_dataset_flows import build,OD,SP
class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.binding={'site':'https://contoso.sharepoint.com/sites/ppg','listId':'00000000-0000-0000-0000-000000000001','onedrive':{'id':OD,'source':'Embedded','connectionName':'fictional'},'sharepoint':{'id':SP,'source':'Embedded','connectionName':'fictional'}}
    def test_capture_is_immutable_and_complete_before_staging(self):
        flow=build(self.binding,[{'key':'example-data','name':'Example data','url':'https://example.com/data.json'}])
        a=flow['properties']['definition']['actions']['Collect_datasets']['actions']
        self.assertFalse(flow['properties']['flowFailureAlertSubscribed'])
        self.assertEqual(a['example_data_poll']['limit'],{'count':12,'timeout':'PT2M'})
        self.assertEqual(a['example_data_poll']['actions']['example_data_metadata']['inputs']['retryPolicy'],{'type':'none'})
        self.assertFalse(a['example_data_download']['inputs']['parameters']['overwrite'])
        self.assertEqual(a['example_data_read']['runAfter'],{'example_data_ready':['Succeeded']})
        self.assertEqual(a['example_data_payload']['runAfter'],{'example_data_complete':['Succeeded']})
        self.assertEqual(a['example_data_complete']['inputs']['schema']['properties']['complete']['enum'],[True])
        self.assertEqual(a['example_data_download']['inputs']['retryPolicy'],{'type':'none'})
        self.assertEqual(flow['properties']['definition']['triggers']['Scheduled_collection']['recurrence']['schedule']['hours'],[7])
    def test_duplicate_sources_rejected(self):
        source={'key':'example-data','name':'Example','url':'https://example.com/data.json'}
        with self.assertRaises(ValueError):build(self.binding,[source,source])
