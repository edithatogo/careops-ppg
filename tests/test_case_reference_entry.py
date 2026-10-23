import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/lifecycle'))
from build_case_reference_entry import build,definition_digest
from build_selected_event_routes import build as event_build,audit_actions
from test_selected_event_routes import fixtures,success

TABLE='11111111-1111-4111-8111-111111111111'
COLLECTION="_api/web/lists(guid'"+TABLE+"')/items"
ENTITY="triggerBody()?['entity']?['ID']"

def fixture():
    flow=event_build('request',*fixtures());d=flow['properties']['definition'];trigger=d['triggers']['manual']
    trigger['inputs'].update(operationId='GetItemHybridTriggerSchema',parameters={'dataset':'https://example.invalid/site','table':TABLE})
    uri="@concat('_api/web/lists(guid''"+TABLE+"'')/items(',string(int("+ENTITY+")),')?$select=Id,CaseUID')"
    reader=d['actions']['Resolve_context']['actions']['Read_selected_case'];reader['inputs']['parameters']['parameters/uri']=uri
    d['actions']['Observe_external_case_read']=copy.deepcopy(reader)
    success(flow)['Selected_case_context']['inputs']['selectedTriggerItemId']='@int('+ENTITY+')'
    button={'properties':{'definition':{'triggers':{'manual':{'type':'Request','kind':'Button','inputs':{'schema':{'type':'object','properties':{'text':{'type':'string'}}}}}}},'connectionReferences':copy.deepcopy(flow['properties']['connectionReferences'])}}
    binding={'qualificationOnly':True,'approvedDefinitionSHA256':definition_digest(d),'approvedButtonTriggerSHA256':definition_digest(button['properties']['definition']['triggers']['manual'])}
    return flow,button,binding


class CaseReferenceEntryTests(unittest.TestCase):
    def test_manual_form_preserves_fields_and_resolves_identity_server_side(self):
        flow,button,binding=fixture();before=copy.deepcopy((flow,button,binding));out=build(flow,button,binding);d=out['properties']['definition'];t=d['triggers']['manual']
        self.assertEqual(before,(flow,button,binding));self.assertEqual(t['kind'],'Button');self.assertEqual(out['properties']['state'],'Stopped')
        fields=t['inputs']['schema']['properties'];self.assertEqual(set(fields),{'text','text_6'});self.assertEqual(t['inputs']['schema']['required'],['text','text_6']);self.assertNotIn('enum',fields['text'])
        self.assertNotIn(ENTITY,json.dumps(d));self.assertNotIn('selectedTriggerItemId',json.dumps(d))
        self.assertIn("outputs('Resolved_case_item_id')",d['actions']['Observe_external_case_read']['inputs']['parameters']['parameters/uri'])
        context=d['actions']['Resolve_context']['actions'];self.assertEqual(context['Read_selected_case']['runAfter'],{'Verify_case_reference':['Succeeded']})
        self.assertEqual(context['Find_case_reference']['runAfter'],{'Validate_case_reference':['Succeeded']})
        self.assertIn('CaseUID eq',context['Find_case_reference']['inputs']['parameters']['parameters/uri']);self.assertNotIn('$orderby',json.dumps(context))
        output=success(out)['Selected_case_context']['inputs'];self.assertEqual(output['contextOrigin'],'manual_case_reference_lookup');self.assertFalse(output['limits']['selectedRowProvenanceClaimed'])
        self.assertLessEqual(audit_actions(d)['maximumActionDepth'],8)
        self.assertEqual(out['properties']['connectionReferences'],flow['properties']['connectionReferences'])

    def test_invalid_locator_and_missing_duplicate_truncated_or_wrong_case_hold_before_full_read(self):
        out=build(*fixture());context=out['properties']['definition']['actions']['Resolve_context']['actions'];syntax=context['Validate_case_reference']['expression']
        self.assertIn("equals(triggerBody()?['text_6'],outputs('Case_reference_value'))",syntax)
        self.assertIn("'LC-FICTIONAL-OP-'",syntax);self.assertIn('128',syntax);self.assertIn('uriComponent',syntax)
        self.assertEqual(context['Validate_case_reference']['else']['actions']['Refuse_case_reference']['type'],'Terminate')
        lookup=context['Verify_case_reference']['expression'];self.assertIn("length(body('Find_case_reference')?['value']),1",lookup);self.assertIn('odata.nextLink',lookup);self.assertIn('@odata.nextLink',lookup)
        self.assertIn("?['CaseUID'],outputs('Case_reference_value')",lookup);self.assertIn("?['Id'],0)),0",lookup)
        self.assertEqual(context['Verify_baseline_boundary']['runAfter'],{'Verify_case_reference_identity':['Succeeded']})
        boundary=context['Verify_case_reference_identity']['expression'];self.assertIn("body('Read_selected_case')?['CaseUID'],outputs('Case_reference_value')",boundary)
        self.assertIn("body('Read_selected_case')?['Id'],outputs('Resolved_case_item_id')",boundary)
        self.assertEqual(context['Verify_case_reference']['else']['actions']['Refuse_case_lookup']['type'],'Terminate')

    def test_stale_review_pins_unqualified_connection_and_unexpected_reader_are_refused(self):
        for change in ('digest','button','connection','reader'):
            flow,button,binding=fixture()
            if change=='digest':binding['approvedDefinitionSHA256']='0'*64
            elif change=='button':binding['approvedButtonTriggerSHA256']='0'*64
            elif change=='connection':button['properties']['connectionReferences']['shared_sharepointonline']['connectionName']='other'
            else:
                flow['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']['inputs']['parameters']['dataset']='https://other.invalid'
                binding['approvedDefinitionSHA256']=definition_digest(flow['properties']['definition'])
            with self.assertRaises(ValueError):build(flow,button,binding)

    def test_reserved_names_cannot_overwrite_existing_actions(self):
        flow,button,binding=fixture();flow['properties']['definition']['actions']['Case_reference_value']={'type':'Compose','inputs':'existing','runAfter':{}}
        binding['approvedDefinitionSHA256']=definition_digest(flow['properties']['definition'])
        with self.assertRaisesRegex(ValueError,'namespace collision'):build(flow,button,binding)

    def test_caller_entity_variants_are_not_silently_retained(self):
        flow,button,binding=fixture();flow['properties']['definition']['actions']['Unexpected_entity']={'type':'Compose','inputs':"@triggerBody()?['entity']?['otherId']",'runAfter':{}}
        binding['approvedDefinitionSHA256']=definition_digest(flow['properties']['definition'])
        with self.assertRaisesRegex(ValueError,'caller-entity'):build(flow,button,binding)
