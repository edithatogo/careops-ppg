import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_native_package_flow import build_flow
import test_native_package_flow as native_tests


class SavedBodyFlowTests(unittest.TestCase):
    def test_default_unchanged_candidate_stopped_and_finalisation_precedes_pack(self):
        old,binding=native_tests.NativeFlowTests().fixture()
        original=build_flow(old,binding)
        before=copy.deepcopy(binding);binding['savedBodyFinalisation']=True
        candidate=build_flow(old,binding);a=candidate['properties']['definition']['actions']
        self.assertEqual(candidate['properties']['state'],'Stopped')
        self.assertNotIn('Finalise_saved_body',original['properties']['definition']['actions'])
        self.assertEqual(a['Ensure_cover'],original['properties']['definition']['actions']['Ensure_cover'])
        self.assertIn('saved-',str(a['Require_safe_revision']))
        self.assertEqual(a['Ensure_pack']['runAfter'],{'Require_saved_pack_unchanged':['Succeeded']})
        self.assertIn('Finalise_saved_body',str(a['Ensure_pack']))
        self.assertIn('Run_script_from_SharePoint_library',str(a['Require_saved_claim']))
        self.assertIn('Read_final_saved_body_claim',str(a['Require_final_pair']))
        self.assertIn('overwrite=false',str(a['Commit_saved_body_claim']))
        self.assertEqual(a['Read_saved_body_claim']['runAfter'],{'Read_existing_pack':['Succeeded','Failed']})
        self.assertEqual(a['Finalise_saved_body']['inputs']['retryPolicy'],{'type':'none'})
        self.assertEqual({k:v for k,v in binding.items() if k!='savedBodyFinalisation'},before)
        visited=set()
        def visit(name,stack):
            self.assertNotIn(name,stack)
            self.assertIn(name,a)
            if name in visited:return
            for prev in a[name].get('runAfter',{}):visit(prev,stack+[name])
            visited.add(name)
        for name in a:visit(name,[])

    def test_full_and_intake_candidates_keep_their_input_rechecks(self):
        for intake in [False,True]:
            old,b=native_tests.NativeFlowTests().fixture();b['fullReview']={'enginePin':copy.deepcopy(b['enginePin']),'scriptGraphId':'full'}
            if intake:b['caseIntake']={'enginePin':copy.deepcopy(b['enginePin']),'scriptGraphId':'intake','reviewQueueListId':'33333333-3333-4333-8333-333333333333','catalogueListId':'44444444-4444-4444-8444-444444444444'}
            b['savedBodyFinalisation']=True;a=build_flow(old,b)['properties']['definition']['actions']
            self.assertIn('saved_body',str(a['Ensure_pack']).lower())
            self.assertEqual(a['Finalise_saved_body']['inputs']['parameters']['scriptId'],'intake' if intake else 'full')
            self.assertIn('Read_full_input_pin_before_receipt',a)
            if intake:self.assertIn('Recheck_case_intake_before_receipt',a)

    def test_optional_pdf_or_implicit_candidate_is_refused(self):
        for value in ['yes',True]:
            old,b=native_tests.NativeFlowTests().fixture();b['savedBodyFinalisation']=value
            # A real PDF binding must never consume obsolete generated-byte pins.
            if value is True:b['pdfConnection']={'id':'fictional'}
            with self.assertRaises(ValueError):build_flow(old,b)

    def test_saved_body_metadata_drift_is_checked_before_receipt_and_at_terminal(self):
        old,b=native_tests.NativeFlowTests().fixture();b['savedBodyFinalisation']=True
        a=build_flow(old,b)['properties']['definition']['actions']
        for name in ['Require_saved_bytes','Require_final_pair']:
            raw=str(a[name])
            for field in ['UniqueId','ETag','Length','UIVersionLabel','ServerRelativeUrl']:
                self.assertIn(field,raw)
        self.assertIn("Read_claim",str(a['Require_unchanged_outputs']))
        self.assertIn('Run_script_from_SharePoint_library',str(a['Require_final_pair']))
