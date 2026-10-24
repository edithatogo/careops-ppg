"""Bound the comparison request before any supporting-evidence lookup."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_atlas_adapter import AdapterError, capture_comparison, comparison_parameters, MAX_BYTES


def query():
    return {'concept_id': 'fictional:1', 'jurisdictions': ['NZ', 'AU', 'US'],
            'dimensions': ['regulatory', 'funding'],
            'valid_at': '2026-07-29T00:00:00Z', 'observed_at': '2026-07-29T00:00:00Z'}


class Client:
    base_url = 'http://testserver'
    status = 200
    content = b'fictional-response'

    def __init__(self):
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return type('Response', (), {'status_code': self.status, 'content': self.content})()


class AtlasComparisonTests(unittest.TestCase):
    def test_exact_read_route_filters_and_no_redirects(self):
        client = Client(); request = query(); original = query()
        result = capture_comparison(client, request)
        self.assertEqual(request, original)
        self.assertEqual(result['bytes'], client.content)
        self.assertEqual(client.calls, [('/api/v1/comparisons', {
            'params': {**request, 'limit': 50}, 'follow_redirects': False})])

    def test_private_ambiguous_and_malformed_queries_never_contact_client(self):
        invalid = [None, {}, {**query(), 'CaseUID': 'private'},
                   {**query(), 'assertion_id': 'fictional'}, {**query(), 'limit': 500},
                   {**query(), 'concept_id': ''}, {**query(), 'jurisdictions': 'NZ'},
                   {**query(), 'jurisdictions': []}, {**query(), 'jurisdictions': ['NZ', 'NZ']},
                   {**query(), 'jurisdictions': ['nz']}, {**query(), 'jurisdictions': [['NZ']]},
                   {**query(), 'dimensions': ['regulatory', 'regulatory']},
                   {**query(), 'dimensions': ['clinical_approval']},
                   {**query(), 'observed_at': '2026-07-29'}]
        for value in invalid:
            with self.subTest(value=value):
                client = Client()
                with self.assertRaises(AdapterError): capture_comparison(client, value)
                self.assertEqual(client.calls, [])

    def test_unqualified_origin_never_contacts_client(self):
        client = Client(); client.base_url = 'https://unqualified.example.test'
        with self.assertRaisesRegex(AdapterError, 'unqualified_origin'):
            capture_comparison(client, query())
        self.assertEqual(client.calls, [])

    def test_denials_redirects_and_oversized_results_fail_closed(self):
        for status, code in ((401, 'lookup_denied'), (403, 'lookup_denied'),
                             (302, 'lookup_unavailable'), (503, 'lookup_unavailable')):
            with self.subTest(status=status):
                client = Client(); client.status = status
                with self.assertRaisesRegex(AdapterError, code): capture_comparison(client, query())
                self.assertEqual(len(client.calls), 1)
        client = Client(); client.content = b'x' * (MAX_BYTES + 1)
        with self.assertRaisesRegex(AdapterError, 'response_oversize'):
            capture_comparison(client, query())


if __name__ == '__main__': unittest.main()
