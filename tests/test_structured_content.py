import copy
import json
import unittest
from pathlib import Path
from scripts.ppg_structured_content import prepare, validate_modules


class StructuredContent(unittest.TestCase):
    def modules(self):return json.loads(Path('config/ppg-content-modules-v1.json').read_text())
    def inventory(self):
        return {'sourceSha256':'a'*64,'elements':[
            {'elementId':'a:1','kind':'p','sourceLocator':'word/document.xml#child=1','text':'Purpose'},
            {'elementId':'a:2','kind':'p','sourceLocator':'word/document.xml#child=2','text':'Fictional purpose','containsRevisions':True},
            {'elementId':'a:3','kind':'comment','sourceLocator':'word/comments.xml#child=0','text':'Preserve comment'}],
            'parts':[{'part':'word/media/image.png','sha256':'b'*64}]}
    def run_prepare(self, inventory=None):
        return prepare('fictional-document',inventory or self.inventory(),self.modules(),{'originalSourceSha256':'c'*64})
    def test_all_elements_parts_and_comments_retained_without_human_fields(self):
        out=self.run_prepare();self.assertEqual(out['elementCount'],3)
        self.assertEqual(out['records'][1]['record']['ProposedModule'],'core.purpose')
        self.assertEqual(out['records'][2]['record']['ProposedModule'],'evidence.annotations')
        self.assertTrue(out['retainedPackageParts'])
        for row in out['records']:
            self.assertFalse({'ReviewText','BlockReviewState','ReviewedModule','StableSectionId'} & set(row['record']))
        self.assertFalse(out['contentMappingComplete'])
    def test_retry_keys_stable_new_edition_distinct_and_input_preserved(self):
        data=self.inventory();before=copy.deepcopy(data);first=self.run_prepare(data)
        self.assertEqual(first,self.run_prepare(data));self.assertEqual(data,before)
        data['sourceSha256']='d'*64
        self.assertNotEqual(first['records'][0]['record']['ContentKey'],self.run_prepare(data)['records'][0]['record']['ContentKey'])
    def test_duplicate_element_and_unverified_mandatory_rule_refused(self):
        data=self.inventory();data['elements'].append(data['elements'][0])
        with self.assertRaises(ValueError):self.run_prepare(data)
        modules=self.modules();modules['rules']=[{'moduleKey':'core.purpose','status':'verified_required'}]
        with self.assertRaises(ValueError):validate_modules(modules)

    def test_empty_xml_element_uses_native_null_without_dropping_record(self):
        data=self.inventory();data['elements'][1]['text']=''
        result=self.run_prepare(data)
        self.assertEqual(result['elementCount'],3)
        self.assertIsNone(result['records'][1]['record']['SourceText'])
        self.assertEqual(result['records'][1]['record']['SourceElementId'],'a:2')
