import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/lifecycle'))
from build_consultation_coverage import build_runtime
from test_selected_event_routes import fixtures

URI="_api/web/lists/getbytitle('PPG Consultation and Handoff Events')/items"
class RuntimeCoverageTests(unittest.TestCase):
    def fixture(self):
        context,_,_=fixtures();reader=copy.deepcopy(context['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case'])
        reader['inputs']['parameters']['parameters/uri']=URI
        return reader
    def test_scope_comes_from_native_reader_and_never_from_form_pins(self):
        reader=self.fixture();before=copy.deepcopy(reader)
        out=build_runtime('Read_runtime_coverage',reader,['FICTIONAL content-review role'],qualified_reader=reader,collection_uri=URI)
        raw=json.dumps(out);guard=out['Consultation_coverage_Runtime_guard']
        self.assertIn("outputs('Native_prepared_revision')?['preparationQualified'],true",guard['expression'])
        self.assertEqual(reader,before)
        self.assertNotIn('RUNTIME-COVERAGE',raw);self.assertNotIn('fictional://runtime',raw);self.assertNotIn('triggerBody()',raw)
        scope=guard['actions']['Consultation_coverage_Scope']['inputs']['where']
        for key in ('CaseUID','DocumentReference','ReviewedVersionRef','DocumentSHA256'):
            self.assertIn("outputs('Native_prepared_revision')?['preparedRevision']?['scope']?['"+key+"']",scope)
        receipt=guard['actions']['Consultation_coverage_Receipt']['inputs']
        self.assertNotIn('technicalCoverageComplete',receipt)
        self.assertIn('coverageHistoryComplete',receipt);self.assertFalse(receipt['nativeContextRevalidated']);self.assertFalse(receipt['progressionGranted'])
        self.assertEqual(guard['else']['actions']['Consultation_coverage_Held']['inputs']['writeCount'],0)
    def test_case_filter_cannot_be_reused_as_runtime_complete_history(self):
        reader=self.fixture();reader['inputs']['parameters']['parameters/uri'] += "?$filter=CaseUID eq 'LC-FICTIONAL-OP-RUNTIME-COVERAGE'"
        with self.assertRaisesRegex(ValueError,'complete literal'):
            build_runtime('Read_runtime_coverage',reader,['FICTIONAL content-review role'],qualified_reader=self.fixture(),collection_uri=URI)
