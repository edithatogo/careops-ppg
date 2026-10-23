"""Protect the sole-writer and checkpoint boundaries of the native adapter."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_identity_flow import extend_importer, extend_absence_retention


def fictional_export():
    uid='00000000-0000-4000-8000-000000000001'
    site='https://example.invalid/fictional'
    def http(uri,method='GET',body=None):
        params={'dataset':site,'parameters/uri':uri,'parameters/method':method,'parameters/headers':{}}
        if body is not None:params['parameters/body']=body
        return {'type':'OpenApiConnection','runAfter':{},'inputs':{'parameters':params}}
    read=http("_api/web/GetFileByServerRelativePath(decodedurl='/fictional/identity-ledger.json')/$value")
    current=http("_api/web/lists(guid'"+uid+"')/items?$select=Id,DocumentUID,sourceTitle")
    patch=http('@native-item-id','POST',"@string(outputs('Whitelisted_fields'))")
    patch['inputs']['parameters']['parameters/headers']={'X-HTTP-Method':'MERGE','If-Match':"@first(body('Find_native'))?['__metadata']?['etag']"}
    save={'type':'OpenApiConnection','runAfter':{},'inputs':{'parameters':{'dataset':site,'name':'fictional','body':'fictional'}}}
    writer={'Patch_source':patch,'Count_write':{'runAfter':{'Patch_source':['Succeeded']}},
            'Read_written':http("@concat('item(',id,')', '?$select=Id,DocumentUID,sourceTitle')"),
            'Verify_written':{'expression':"@equals(body('Read_written')?['d']?['sourceTitle'],outputs('Current_operation')?['fields']?['sourceTitle'])"}}
    compare={'expression':"@equals(first(body('Find_native'))?['sourceTitle'],'fictional')",'else':{'actions':writer}}
    guard={'runAfter':{'Current_UIDs':['Succeeded']},'expression':"@and(equals(outputs('Parse_candidate')?['contractHash'],'"+'a'*64+"'),equals(length(outputs('Parse_candidate')?['operations']),985),equals(length(body('Read_current')?['d']?['results']),985),equals(length(union(body('Current_UIDs'),body('Current_UIDs'))),985),empty(outputs('Parse_candidate')?['exceptions']),empty(outputs('Parse_candidate')?['missingUIDs']))",
           'actions':{'Write_changes':{'actions':{'Serial_check':{'actions':{'Row_work':{'actions':{'Compare_source':compare}}}}}}}}
    reconciliation={'Guard_input':guard,'Read_current':current,'Read_current_after':copy.deepcopy(current),
                    'Guard_readback':{'expression':"@and(equals(length(body('Read_current_after')?['d']?['results']),985),equals(body('Read_source_metadata')?['ETag'],body('Read_source_metadata_after')?['ETag']))",
                                     'actions':{'Set_full_readback_count':{'inputs':{'value':985}},'Completed_summary':{'inputs':{'identityContractHash':"@outputs('Parse_candidate')?['contractHash']"}}}}}
    acquisition={'Read_identity_ledger':read,'Extract_copy':{'inputs':{'parameters':{}}},'Save_extraction':save,'Save_records':copy.deepcopy(save)}
    daily={'Acquire_fresh':{'actions':acquisition},'Selected_candidate':{'inputs':{}},'Reconcile':{'actions':reconciliation},
           'Commit_checkpoint':{'runAfter':{'Success_receipt':['Succeeded']},'inputs':{'parameters':{'parameters/body':"@string(outputs('Completed_summary'))"}}},
           'Success_receipt':{'runAfter':{'Reconcile':['Succeeded']}}}
    actions={'Daily_due':{'runAfter':{},'expression':"@equals(outputs('Source_state')?['dailyDue'],true)",'actions':daily},
             'Read_success_checkpoint':copy.deepcopy(read),'Parse_success_checkpoint':{'inputs':"@json(string(body('Read_success_checkpoint')))"},'Untouched':{'type':'Compose','inputs':'preserve'}}
    return {'properties':{'definition':{'triggers':{'hourly':{'runtimeConfiguration':{'concurrency':{'runs':1}}}},'actions':actions}}}


class IdentityFlowTests(unittest.TestCase):
    def test_absent_rows_preserved_and_full_identity_set_verified(self):
        original = extend_importer(fictional_export())
        r = original['properties']['definition']['actions']['Daily_due']['actions']['Reconcile']['actions']
        r['Canonical_after'] = {'type': 'Select', 'runAfter': {'Read_current_after': ['Succeeded']},
                                'inputs': {'from': "@body('Read_current_after')?['d']?['results']", 'select': {'DocumentUID': "@item()?['DocumentUID']"}}}
        union = "equals(length(union(body('Candidate_UIDs'),body('Current_UIDs'))),length(outputs('Parse_candidate')?['operations']))"
        r['Guard_input']['expression'] = '@and(' + r['Guard_input']['expression'][1:] + ',' + union + ')'
        before = copy.deepcopy(original)
        revised = extend_absence_retention(original)
        self.assertEqual(original, before)
        after = revised['properties']['definition']['actions']['Daily_due']['actions']['Reconcile']['actions']
        self.assertEqual(after['Read_current'], r['Read_current'])
        self.assertEqual(after['Read_current_after'], r['Read_current_after'])
        self.assertEqual(after['Guard_input']['actions'], r['Guard_input']['actions'])
        self.assertEqual(after['Canonical_after']['inputs']['from'], "@body('Active_current_after')")
        self.assertIn("union(body('Canonical_retained_before'),body('Canonical_retained_after'))", after['Guard_readback']['expression'])
        projection = after['Canonical_retained_before']['inputs']['select']
        self.assertIn('retainedETag', projection)
        self.assertIn('div(1,0)', projection['retainedETag'])
        self.assertNotIn('__metadata', projection)
        self.assertIn('acknowledgedMissingUIDs', after['Guard_input']['expression'])
        self.assertIn('add(length', after['Guard_input']['expression'])
        summary = after['Guard_readback']['actions']['Completed_summary']['inputs']
        self.assertIn('retainedAbsentUnchanged', summary)
        # Execute the emitted predicate's small WDL subset against value fixtures.
        # The projection separately refuses a missing ETag before this predicate.
        import json
        def union(left, right):
            result = []
            for value in left + right:
                if value not in result:
                    result.append(value)
            return result
        one = {'Id': 1, 'DocumentUID': 'fictional-a', 'sourceTitle': 'A', 'retainedETag': '"1"'}
        two = {'Id': 2, 'DocumentUID': 'fictional-b', 'sourceTitle': 'B', 'retainedETag': '"1"'}
        expression = summary['retainedAbsentUnchanged'][1:].replace('and(', 'all_checks(')
        def evaluate(rows):
            values = {'Canonical_retained_before': [one, two], 'Canonical_retained_after': rows}
            return eval(expression, {'__builtins__': {}}, {'body': values.__getitem__,
                'all_checks': lambda *args: all(args), 'equals': lambda a, b: a == b,
                'length': len, 'union': union})
        self.assertTrue(evaluate([two, one]))
        self.assertFalse(evaluate([one, one]))
        self.assertFalse(evaluate([one]))
        self.assertFalse(evaluate([one, {**two, 'retainedETag': '"2"'}]))
        self.assertFalse(evaluate([one, {**two, 'retainedETag': None}]))
        self.assertFalse(evaluate([one, {**two, 'sourceTitle': 'changed'}]))
        with self.assertRaisesRegex(ValueError, 'already_present'):
            extend_absence_retention(revised)

    def test_conditional_patches_creation_stamp_and_commit_last(self):
        original=fictional_export();before=copy.deepcopy(original)
        result=extend_importer(original)
        self.assertEqual(original,before)
        actions=result['properties']['definition']['actions'];daily=actions['Daily_due']['actions']
        self.assertEqual(actions['Untouched'],before['properties']['definition']['actions']['Untouched'])
        writer=daily['Reconcile']['actions']['Guard_input']['actions']['Write_changes']['actions']['Serial_check']['actions']['Row_work']['actions']['Compare_source']['else']['actions']
        patch=writer['Write_source']['else']['actions']['Patch_source']['inputs']['parameters']
        self.assertEqual(patch['parameters/headers']['If-Match'],"@first(body('Find_native'))?['__metadata']?['etag']")
        create=writer['Write_source']['actions']['Create_identity']
        body=create['inputs']['parameters']['parameters/body']
        self.assertIn("['newUIDs']",body)
        self.assertIn('div(1,0)',body)
        self.assertIn('sourceIdentityDecisionRef',body)
        self.assertIn("['packageHash']",body)
        self.assertNotIn('localDecision',body)
        self.assertEqual(daily['Commit_checkpoint']['runAfter'],{'Success_receipt':['Succeeded']})
        self.assertEqual(daily['Success_receipt']['runAfter'],{'Reconcile':['Succeeded']})
        summary=daily['Reconcile']['actions']['Guard_readback']['actions']['Completed_summary']['inputs']
        self.assertIn('identityLedger',summary)
        # No separate canonical-ledger write can commit an unverified contract.
        self.assertEqual(daily['Acquire_fresh']['actions']['Read_identity_ledger']['inputs']['parameters']['parameters/method'],'GET')
    def test_missing_collision_source_and_replay_guards_survive(self):
        actions=extend_importer(fictional_export())['properties']['definition']['actions']
        daily=actions['Daily_due']['actions'];r=daily['Reconcile']['actions']
        guard=r['Guard_input']['expression']
        for required in ('Missing_base_identities','Unqualified_new_identities','identityContractHash',"['exceptions']","['missingUIDs']","['inputCount']"):
            self.assertIn(required,guard)
        self.assertNotIn(',985)',guard)
        self.assertIn('Read_source_metadata_after',r['Guard_readback']['expression'])
        self.assertIn('lastIdentityApplicationHash',actions['Daily_due']['expression'])
        self.assertIn('identityContractHash',daily['Selected_candidate']['inputs']['reusedCandidate'])
        self.assertIn('sourceIdentityDecisionRef',r['Unqualified_new_identities']['inputs']['where'])
        self.assertEqual(r['Current_identity_values']['inputs']['select'],"@item()?['DocumentUID']")
        self.assertIn('Current_identity_values',r['Missing_base_identities']['inputs']['where'])
        self.assertIn('Save_identity_snapshot',daily['Acquire_fresh']['actions'])
    def test_refuses_parallel_importer_unknown_writer_or_double_extension(self):
        original=fictional_export();original['properties']['definition']['triggers']['hourly']['runtimeConfiguration']['concurrency']['runs']=2
        with self.assertRaisesRegex(ValueError,'sole_serial_importer'):extend_importer(original)
        original=fictional_export();result=extend_importer(original)
        with self.assertRaisesRegex(ValueError,'already_present'):extend_importer(result)
        del original['properties']['definition']['actions']['Daily_due']['actions']['Reconcile']['actions']['Guard_input']['actions']['Write_changes']['actions']['Serial_check']['actions']['Row_work']['actions']['Compare_source']['else']['actions']['Patch_source']['inputs']['parameters']['parameters/headers']['If-Match']
        with self.assertRaisesRegex(ValueError,'conditional_source_writer'):extend_importer(original)


if __name__=='__main__':unittest.main()
