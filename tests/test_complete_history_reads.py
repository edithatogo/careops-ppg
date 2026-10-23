"""The 101st record is included without weakening incomplete-history refusal."""
import copy
import unittest
from urllib.parse import parse_qs

from bind_complete_history_reads import build, rebind_consumer_locator, bind_closure_contract_reads
from build_multisource_case_context import digest


SITE = 'https://example.invalid/site'
URI = "_api/web/lists(guid'00000000-0000-4000-8000-000000000001')/items"


def fixture():
    return {'properties': {'state': 'Started', 'connectionReferences': {'retained': {}},
        'definition': {'triggers': {'manual': {'type': 'Request'}}, 'actions': {
            'Read': {'type': 'OpenApiConnection', 'runAfter': {}, 'inputs': {'parameters': {
                'dataset': SITE, 'parameters/method': 'GET', 'parameters/uri': URI}}},
            'Complete': {'type': 'Compose', 'runAfter': {'Read': ['Succeeded']},
                'inputs': "@empty(body('Read')?['odata.nextLink'])"},
            'Write': {'type': 'OpenApiConnection', 'runAfter': {}, 'inputs': {'parameters': {
                'dataset': SITE, 'parameters/method': 'POST', 'parameters/uri': URI}}},
        }}}}


def binding(flow):
    return {'approvedDefinitionSHA256': digest(flow['properties']['definition']),
        'site': SITE, 'readers': {'Read': URI}, 'pageSize': 5000}


def page(uri, count):
    limit = int(parse_qs(uri.partition('?')[2]).get('$top', ['100'])[0])
    return {'value': list(range(min(count, limit))),
        **({'odata.nextLink': 'actual-native-continuation'} if count > limit else {})}


class CompleteHistoryReads(unittest.TestCase):
    def closure_fixture(self):
        flow = fixture(); nodes = flow['properties']['definition']['actions']
        reads = {}
        for index, kind in enumerate(('assurance', 'readiness', 'consultation'), 1):
            uri = URI.replace('000000000001', f'{index:012d}')
            reads[kind] = {'uri': uri, 'collection': True}
            node = copy.deepcopy(nodes['Read'])
            node['inputs']['parameters']['parameters/uri'] = uri + '?$top=5000'
            nodes['ClosureEntry_check_' + kind] = node
            node = copy.deepcopy(node)
            node['inputs']['parameters']['parameters/uri'] = "@outputs('ClosureEntry_write_contract')?['evidenceReads']?['"+kind+"']?['uri']"
            nodes['Cycle_current_' + kind] = node
        nodes['ClosureEntry_write_contract'] = {'type': 'Compose', 'inputs': {}}
        nodes['ClosureEntry_binding_result'] = {'type': 'Compose', 'inputs': {'evidenceReads': reads}}
        return flow

    def test_closure_contract_includes_103rd_row_without_weakening_guard(self):
        flow = self.closure_fixture(); out = bind_closure_contract_reads(flow, digest(flow['properties']['definition']))
        nodes = out['properties']['definition']['actions']
        for kind in ('assurance', 'readiness', 'consultation'):
            uri = nodes['ClosureEntry_binding_result']['inputs']['evidenceReads'][kind]['uri']
            self.assertEqual(len(page(uri, 103)['value']), 103)
            self.assertIn('odata.nextLink', page(uri, 5001))
            nodes['ClosureEntry_binding_result']['inputs']['evidenceReads'][kind]['uri'] = uri.removesuffix('?$top=5000')
        out['properties']['state'] = 'Started'
        self.assertEqual(out, flow)

    def test_closure_contract_refuses_unreviewed_or_unpaired_reads(self):
        for change in ('digest', 'bounded', 'dynamic', 'collection', 'duplicate'):
            with self.subTest(change=change):
                flow = self.closure_fixture(); nodes = flow['properties']['definition']['actions']
                if change == 'bounded': nodes['ClosureEntry_check_assurance']['inputs']['parameters']['parameters/uri'] = URI
                elif change == 'dynamic': nodes['Cycle_current_assurance']['inputs']['parameters']['parameters/uri'] = URI
                elif change == 'collection': nodes['ClosureEntry_binding_result']['inputs']['evidenceReads']['assurance']['collection'] = False
                elif change == 'duplicate':
                    nodes['ClosureEntry_binding_result']['inputs']['evidenceReads']['readiness']['uri'] = URI
                    nodes['ClosureEntry_check_readiness']['inputs']['parameters']['parameters/uri'] = URI + '?$top=5000'
                approved = 'stale' if change == 'digest' else digest(flow['properties']['definition'])
                with self.assertRaises(ValueError): bind_closure_contract_reads(flow, approved)

    def test_101st_record_is_visible_and_continuation_guard_unchanged(self):
        flow = fixture(); out = build(flow, binding(flow))
        uri = out['properties']['definition']['actions']['Read']['inputs']['parameters']['parameters/uri']
        self.assertIn('odata.nextLink', page(URI, 101))
        self.assertEqual(len(page(uri, 101)['value']), 101)
        self.assertNotIn('odata.nextLink', page(uri, 101))
        self.assertEqual(out['properties']['definition']['actions']['Complete'],
            flow['properties']['definition']['actions']['Complete'])
        self.assertIn('odata.nextLink', page(uri, 5001))

    def test_only_exact_read_uri_changes(self):
        flow = fixture(); original = copy.deepcopy(flow); out = build(flow, binding(flow))
        self.assertEqual(flow, original)
        out['properties']['definition']['actions']['Read']['inputs']['parameters']['parameters/uri'] = URI
        out['properties']['state'] = 'Started'
        self.assertEqual(out, flow)

    def test_changed_definition_is_refused(self):
        flow = fixture(); b = binding(flow)
        flow['properties']['definition']['actions']['Complete']['inputs'] = True
        with self.assertRaises(ValueError): build(flow, b)

    def test_writer_foreign_site_dynamic_filtered_or_single_item_target_refused(self):
        for change in ['writer', 'site', 'expression', 'filter', 'item', 'missing']:
            with self.subTest(change=change):
                flow = fixture(); b = binding(flow)
                if change == 'writer': b['readers'] = {'Write': URI}
                elif change == 'site': b['site'] = 'https://foreign.invalid/site'
                elif change == 'missing': b['readers'] = {'Absent': URI}
                else:
                    uri = {'expression': '@concat(\'unsafe\')', 'filter': URI+'?$filter=Id eq 1', 'item': URI+'(1)'}[change]
                    b['readers']['Read'] = uri
                    flow['properties']['definition']['actions']['Read']['inputs']['parameters']['parameters/uri'] = uri
                    b['approvedDefinitionSHA256'] = digest(flow['properties']['definition'])
                with self.assertRaises(ValueError): build(flow, b)

    def test_changed_bound_and_empty_readers_refused(self):
        for value in [100, 10000, None]:
            flow = fixture(); b = binding(flow); b['pageSize'] = value
            with self.assertRaises(ValueError): build(flow, b)
        flow = fixture(); b = binding(flow); b['readers'] = {}
        with self.assertRaises(ValueError): build(flow, b)

    def test_exact_title_collection_supported(self):
        flow = fixture(); uri = "_api/web/lists/getbytitle('Fictional history')/items"
        flow['properties']['definition']['actions']['Read']['inputs']['parameters']['parameters/uri'] = uri
        b = binding(flow); b['readers']['Read'] = uri
        out = build(flow, b)
        self.assertEqual(out['properties']['definition']['actions']['Read']['inputs']['parameters']['parameters/uri'], uri+'?$top=5000')

    def test_locator_overlay_refuses_changed_consumer_guard_form_or_connection(self):
        for change in ['guard', 'form', 'connection']:
            with self.subTest(change=change):
                previous = fixture(); b = binding(previous); current = build(previous, b)
                if change == 'guard': current['properties']['definition']['actions']['Complete']['inputs'] = True
                elif change == 'form': current['properties']['definition']['triggers']['manual']['type'] = 'Other'
                else: current['properties']['connectionReferences']['foreign'] = {}
                with self.assertRaisesRegex(ValueError, 'exactly the reviewed history-read overlay'):
                    rebind_consumer_locator({}, previous, current, b, 'unapproved')


if __name__ == '__main__': unittest.main()
