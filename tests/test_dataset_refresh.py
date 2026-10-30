import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_dataset_refresh import extend
from ppg_public_dataset_flows import build, OD, SP

class RefreshTests(unittest.TestCase):
    def test_serial_conditional_refresh_and_capture_checkpoint(self):
        binding={'site':'https://contoso.sharepoint.com/sites/ppg','listId':'00000000-0000-0000-0000-000000000001','rowLists':{'example-facilities':'00000000-0000-0000-0000-000000000002'},'attribution':'Fictional publisher','onedrive':{'id':OD,'connectionName':'fictional','source':'Embedded'},'sharepoint':{'id':SP,'connectionName':'fictional','source':'Embedded'}}
        contracts=[{'key':'example-facilities','keyFields':['FacilityCode'],'fields':[{'source':'FacilityCode','name':'FacilityCode'},{'source':'Value','name':'Value'}]}]
        original=build(binding,[{'key':'example-facilities','name':'Example','url':'https://example.com/api'}])
        flow=extend(original,binding,contracts)
        a=flow['properties']['definition']['actions']['Collect_datasets']['actions']['example_facilities_dataset']['actions']
        prefix='example_facilities_sync_'
        self.assertEqual(a[prefix+'pages']['runAfter'],{prefix+'valid_keys':['Succeeded']})
        self.assertEqual(a[prefix+'batches']['runtimeConfiguration']['concurrency']['repetitions'],1)
        self.assertEqual(a[prefix+'done']['runAfter'],{prefix+'batches':['Succeeded']})
        expression=a[prefix+'requests']['inputs']['select']
        self.assertIn('IF-MATCH: ',expression)
        self.assertIn("'POST ','MERGE '",expression)
        self.assertNotIn('X-HTTP-Method',expression)
        self.assertIn("guid''00000000-0000-0000-0000-000000000002''",expression)
        self.assertNotIn('DELETE',expression)
        self.assertIn('HTTP/1.1 201',json.dumps(a[prefix+'batches']))
        self.assertIn('HTTP/1.1 204',json.dumps(a[prefix+'batches']))
        self.assertIn("base64ToString(body('example_facilities_sync_send')?['$content'])",json.dumps(a[prefix+'batches']))
        self.assertEqual(a[prefix+'removals']['inputs']['select']['SourcePresent'],False)
        self.assertNotIn('Initialise_row_reads',original['properties']['definition']['actions'])
