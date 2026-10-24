"""Bounded reader preparation: source scope, effect isolation and pin guards."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_cited_reader_flow import build_flow, checked_binding, PIN_FIELDS


def binding():
    return {'siteUrl': 'https://example.sharepoint.com/sites/ppg',
            'folder': '/sites/ppg/evidence', 'sourceId': 'fictional-edition-1',
            'authorityLabel': 'captured-reference-unconfirmed', 'pin': {
                'UniqueId': '11111111-1111-4111-8111-111111111111', 'Name': 'edition-1.txt',
                'Length': 220, 'ETag': '"1"', 'MajorVersion': 1, 'MinorVersion': 0,
                'TimeLastModified': '2026-10-17T08:00:00Z',
                'ServerRelativeUrl': '/sites/ppg/evidence/edition-1.txt'}}


def existing():
    return {'properties': {'state': 'Started', 'plan': 'not-to-be-copied',
            'definition': {'actions': {'Old_send': {'type': 'SendEmail'}}},
            'connectionReferences': {
                'shared_sharepointonline': {'connectionReferenceLogicalName': 'fictional_sp', 'source': 'Invoker'},
                'shared_office365': {'connectionName': 'do-not-copy'}}}}


class ReaderFlowTests(unittest.TestCase):
    def test_preparation_preserves_inputs_and_excludes_old_effects_and_billing(self):
        old, selected = existing(), binding()
        before = copy.deepcopy((old, selected))
        result = build_flow(old, selected)
        self.assertEqual((old, selected), before)
        self.assertEqual(result['properties']['state'], 'Stopped')
        self.assertNotIn('plan', result['properties'])
        self.assertEqual(result['properties']['connectionReferences'], {
            'shared_sharepointonline': old['properties']['connectionReferences']['shared_sharepointonline']})
        self.assertNotIn('Old_send', json.dumps(result))
        result['properties']['connectionReferences']['shared_sharepointonline']['source'] = 'Embedded'
        self.assertEqual(old['properties']['connectionReferences']['shared_sharepointonline']['source'], 'Invoker')

    def test_no_caller_source_selection_schedule_agent_or_mutating_operation(self):
        definition = build_flow(existing(), binding())['properties']['definition']
        trigger = definition['triggers']['manual']
        self.assertEqual((trigger['type'], trigger['kind']), ('Request', 'Button'))
        self.assertEqual(trigger['inputs']['schema']['properties'], {})
        self.assertFalse(trigger['inputs']['schema']['additionalProperties'])
        connectors = [a['inputs'] for a in definition['actions'].values() if a['type'] == 'OpenApiConnection']
        self.assertEqual(len(connectors), 3)
        for action in connectors:
            self.assertEqual(action['host']['connectionName'], 'shared_sharepointonline')
            self.assertEqual(action['retryPolicy'], {'type': 'none'})
            if action['host']['operationId'] == 'HttpRequest':
                self.assertEqual(action['parameters']['parameters/method'], 'GET')
            else:
                self.assertEqual(action['host']['operationId'], 'GetFileContentByPath')
                self.assertEqual(action['parameters']['path'], '/evidence/edition-1.txt')
                self.assertFalse(action['parameters']['inferContentType'])

    def test_complete_expected_pin_is_checked_before_content_and_after_it(self):
        actions = build_flow(existing(), binding())['properties']['definition']['actions']
        self.assertEqual(actions['Read_content']['runAfter'], {'Require_expected_source': ['Succeeded']})
        self.assertEqual(actions['Metadata_after']['runAfter'], {'Read_content': ['Succeeded']})
        self.assertEqual(actions['Selected_source_result']['runAfter'], {'Require_unchanged_source': ['Succeeded']})
        for name, code in [('Require_expected_source', 'SOURCE_PIN'), ('Require_unchanged_source', 'SOURCE_CHANGED')]:
            guard = actions[name]
            self.assertEqual(len(guard['expression']['and']), len(PIN_FIELDS))
            for field in PIN_FIELDS:
                self.assertIn("['" + field + "']", json.dumps(guard['expression']))
            refusal = guard['else']['actions']['Refuse_' + code]
            self.assertEqual(refusal['inputs']['runStatus'], 'Failed')
            self.assertEqual(refusal['inputs']['runError']['code'], code)
            self.assertNotIn('content', json.dumps(refusal))

    def test_result_keeps_raw_bytes_distinct_from_unqualified_extraction_and_hashes(self):
        result = build_flow(existing(), binding())['properties']['definition']['actions']['Selected_source_result']['inputs']
        self.assertEqual(result['nativeVersionRef'], '1.0')
        self.assertEqual(result['nativePin']['Length'], '220')
        self.assertEqual(result['authorityLabel'], 'captured-reference-unconfirmed')
        self.assertIsNone(result['sha256'])
        self.assertIsNone(result['binarySHA256'])
        self.assertFalse(result['textExtractionQualified'])
        self.assertFalse(result['nativeAssistantRuntimeQualified'])
        self.assertNotIn('startLine', result)
        self.assertEqual(result['content'], "@body('Read_content')")

    def test_expression_looking_source_metadata_remains_literal(self):
        selected = binding()
        selected['sourceId'] = '@parameters(secret)'
        selected['pin']['Name'] = '@source.txt'
        selected['pin']['ETag'] = '@malicious()'
        selected['pin']['ServerRelativeUrl'] = selected['folder'] + '/@source.txt'
        actions = build_flow(existing(), selected)['properties']['definition']['actions']
        result = actions['Selected_source_result']['inputs']
        self.assertEqual(result['sourceId'], '@@parameters(secret)')
        self.assertEqual(result['nativePin']['Name'], '@@source.txt')
        self.assertEqual(result['nativePin']['ETag'], '@@malicious()')
        comparisons = actions['Require_expected_source']['expression']['and']
        self.assertIn({'equals': ["@string(body('Metadata_before')?['ETag'])", '@@malicious()']}, comparisons)

    def test_site_and_folder_cannot_redirect_or_escape(self):
        for site in ['http://example.sharepoint.com/sites/ppg', 'https://example.invalid/sites/ppg',
                     'https://example.sharepoint.com.evil.invalid/sites/ppg',
                     'https://example.sharepoint.com/sites/ppg'.replace('://', '://user@'),
                     'https://example.sharepoint.com/sites/ppg?x=1',
                     'https://example.sharepoint.com/sites/ppg/../other',
                     'https://example.sharepoint.com:443/sites/ppg']:
            selected = binding(); selected['siteUrl'] = site
            with self.subTest(site=site), self.assertRaises(ValueError):
                checked_binding(selected)
        for folder in ['/sites/other/evidence', '/sites/ppg/evidence/../other',
                       '/sites/ppg/evidence%2fother', '/sites/ppg/evidence/']:
            selected = binding(); selected['folder'] = folder
            with self.subTest(folder=folder), self.assertRaises(ValueError):
                checked_binding(selected)

    def test_source_cannot_escape_or_silently_change_format(self):
        for path in ['/sites/ppg/evidence-other/edition-1.txt', '/sites/other/edition-1.txt',
                     '/sites/ppg/evidence/../edition-1.txt', '/sites/ppg/evidence/%2e%2e/edition-1.txt',
                     '/sites/ppg/evidence/edition-1.txt?query', '/sites/ppg/evidence/edition-1.txt\n']:
            selected = binding(); selected['pin']['ServerRelativeUrl'] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                checked_binding(selected)
        for suffix in ['.docx', '.pdf', '.captured', '.html']:
            selected = binding()
            selected['pin']['Name'] = 'edition-1' + suffix
            selected['pin']['ServerRelativeUrl'] = selected['folder'] + '/' + selected['pin']['Name']
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, 'separate_extraction'):
                checked_binding(selected)

    def test_incomplete_or_invalid_native_pins_and_authority_are_refused(self):
        for field in PIN_FIELDS:
            selected = binding(); del selected['pin'][field]
            with self.subTest(missing=field), self.assertRaisesRegex(ValueError, 'incomplete_native_pin'):
                checked_binding(selected)
        for field, value in [('UniqueId', '00000000-0000-0000-0000-000000000000'),
                             ('Length', True), ('Length', -1), ('Length', 2_000_001),
                             ('MajorVersion', True), ('MinorVersion', -1),
                             ('ETag', ''), ('TimeLastModified', '2026-10-17'), ('Name', 'other.txt')]:
            selected = binding(); selected['pin'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                checked_binding(selected)
        selected = binding(); selected['authorityLabel'] = 'approved'
        with self.assertRaisesRegex(ValueError, 'authority_label'):
            checked_binding(selected)


if __name__ == '__main__':
    unittest.main()
