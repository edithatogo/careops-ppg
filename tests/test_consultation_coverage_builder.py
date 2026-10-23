import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/lifecycle'))
from build_consultation_coverage import build


class ConsultationCoverageBuilderTests(unittest.TestCase):
    def setUp(self):
        self.base = "_api/web/lists/getbytitle('PPG Consultation and Handoff Events')/items"
        self.reader = {'type': 'OpenApiConnection', 'runAfter': {}, 'inputs': {'host': {
            'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
            'operationId': 'HttpRequest', 'connectionName': 'shared_sharepointonline'},
            'parameters': {'dataset': 'https://example.invalid/site', 'parameters/method': 'GET', 'parameters/uri': self.base}}}
        self.original = {'CaseUID': 'LC-FICTIONAL-OP-CASE-1', 'DocumentReference': 'fictional://source',
            'ReviewedVersionRef': 'source-version', 'DocumentSHA256': 'a' * 64}
        self.prepared = {**self.original, 'DocumentReference': 'fictional://prepared',
            'ReviewedVersionRef': 'prepared-version', 'DocumentSHA256': 'b' * 64}

    def compile(self, reader=None, prepared=None, roles=None):
        return build('Read_consultation', reader or self.reader, prepared or self.prepared,
            self.original, ['FICTIONAL content-review role'] if roles is None else roles,
            qualified_reader=self.reader, collection_uri=self.base)

    def test_complete_and_case_only_readers_preserve_original_descriptor(self):
        before = copy.deepcopy(self.reader); self.compile()
        scoped = copy.deepcopy(self.reader)
        scoped['inputs']['parameters']['parameters/uri'] += "?$filter=CaseUID eq 'LC-FICTIONAL-OP-CASE-1'"
        self.compile(scoped)
        self.assertEqual(self.reader, before)

    def test_filters_cannot_hide_adverse_or_conflicting_history(self):
        for query in ["?$filter=ConditionsState ne 'Open'", "?%24filter=ConditionsState%20ne%20%27Open%27",
                      "?$FILTER=ConditionsState ne 'Open'", "?%2524filter=ConditionsState%20ne%20%27Open%27",
                      '?$top=2', '?$select=EventUID,RecordState',
                      "?$filter=CaseUID eq 'OTHER-CASE'"]:
            with self.subTest(query=query):
                reader = copy.deepcopy(self.reader); reader['inputs']['parameters']['parameters/uri'] += query
                with self.assertRaises(ValueError): self.compile(reader)
        dynamic = copy.deepcopy(self.reader)
        dynamic['inputs']['parameters']['parameters/uri'] = "@concat('" + self.base + "','?$filter=ConditionsState ne Open')"
        with self.assertRaises(ValueError): self.compile(dynamic)

    def test_reader_cannot_change_identity_resource_or_method(self):
        for section, key, value in [('host', 'apiId', 'other-provider'), ('host', 'connectionName', 'other-connection'),
                                    ('parameters', 'dataset', 'https://other.invalid/site'), ('parameters', 'parameters/method', 'POST')]:
            reader = copy.deepcopy(self.reader); reader['inputs'][section][key] = value
            with self.assertRaises(ValueError): self.compile(reader)

    def test_source_scope_other_case_and_empty_required_plan_are_not_prepared_coverage(self):
        for prepared in [self.original, {**self.prepared, 'CaseUID': 'LC-FICTIONAL-OP-OTHER'},
                         {**self.prepared, 'DocumentSHA256': ''}]:
            with self.assertRaises(ValueError): self.compile(prepared=prepared)
        for roles in [[], ['FICTIONAL role', 'FICTIONAL role'], ['Real implied reviewer']]:
            with self.assertRaises(ValueError): self.compile(roles=roles)


if __name__ == '__main__':
    unittest.main()
