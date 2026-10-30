import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_source_environment import parameterise
from ppg_newsletter_routing import routing_rule

class BindingTests(unittest.TestCase):
    def test_preserve_definition_and_expressions(self):
        flow={'properties':{'definition':{'parameters':{},'actions':{'read':{'dataset':'https://contoso.sharepoint.com/sites/ppg','uri':"lists(guid'fictional-list')/items",'expression':"@concat('fictional-list','/items')"}},'triggers':{}}}}
        actual,counts=parameterise(flow,{'ppg_Site':'https://contoso.sharepoint.com/sites/ppg','ppg_List':'fictional-list'})
        read=actual['properties']['definition']['actions']['read']
        self.assertEqual(read['uri'],"lists(guid'@{parameters('ppg_List')}')/items")
        self.assertEqual(read['expression'],"@concat(parameters('ppg_List'),'/items')")
        self.assertEqual(flow['properties']['definition']['actions']['read']['expression'],"@concat('fictional-list','/items')")
        self.assertEqual(counts,{'ppg_Site':1,'ppg_List':2})
        self.assertEqual(actual['properties']['definition']['parameters']['ppg_List']['metadata'],{'schemaName':'ppg_List'})
    def test_multiple_bindings_in_escaped_expression_literal(self):
        flow={'properties':{'definition':{'actions':{'uri':"@concat('https://example.com/_api/lists(guid''fictional-list'')/',string(item()?['ID']))"},'triggers':{}}}}
        actual,counts=parameterise(flow,{'ppg_Site':'https://example.com','ppg_List':'fictional-list'})
        self.assertEqual(actual['properties']['definition']['actions']['uri'],"@concat(concat(parameters('ppg_Site'),concat('/_api/lists(guid''',parameters('ppg_List'),''')/')),string(item()?['ID']))")
        self.assertEqual(counts,{'ppg_Site':1,'ppg_List':1})
    def test_routing_is_narrow_and_never_sends(self):
        rule=routing_rule('fictional',{'senders':['publisher@example.com'],'subjectContains':'Policy bulletin','folderId':'fictional-folder'},sequence=1)
        self.assertEqual(set(rule['actions']),{'moveToFolder','stopProcessingRules'})
        self.assertEqual(rule['conditions']['subjectContains'],['Policy bulletin'])
        self.assertIn('RE:',rule['exceptions']['subjectContains'])
        with self.assertRaises(ValueError):routing_rule('fictional',{'senders':[]},sequence=1)
        with self.assertRaises(ValueError):parameterise({'properties':{'definition':{'actions':{},'triggers':{}}}},{'ppg_Empty':''})
