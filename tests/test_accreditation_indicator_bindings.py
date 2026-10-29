import hashlib
import json
import unittest
from scripts.ppg_accreditation_indicator_bindings import bind


class IndicatorBindingsTests(unittest.TestCase):
    def fixture(self):
        records = [dict(key='pub', kind='Publication', publicationKey='pub', editionKey=None),
                   dict(key='edition', kind='Edition', publicationKey='pub', editionKey='edition', frameworkKeys=['framework']),
                   dict(key='capture', kind='Capture', publicationKey='pub', editionKey='edition', data=dict(sha256='a'*64, sourceURL='https://example.test/item', nativeURL='https://example.test/capture'))]
        rows = []
        for i, r in enumerate(records, 1):
            raw = json.dumps(r)
            rows.append(dict(Id=i, RecordKey=r['key'], RecordKind=r['kind'], RecordJSON=raw, PayloadSHA256=hashlib.sha256(raw.encode()).hexdigest()))
        return dict(records=[dict(IndicatorKey='indicator', SourceSHA256='a'*64, SourceURL='https://example.test/item')], qualityStatements=[], summary={}), rows, dict(Id=4, FrameworkKey='framework')

    def test_exact_chain_binds_without_marking_native_population_complete(self):
        p, rows, framework = self.fixture()
        result = bind(p, rows, framework)
        self.assertEqual(result['records'][0]['IndicatorVersionKey'], 'indicator-version:indicator:capture')
        self.assertFalse(result['summary']['nativePersistenceVerified'])
        self.assertNotIn('CaptureKey', p['records'][0])

    def test_missing_changed_duplicate_or_wrong_framework_refuses(self):
        for change in ('missing', 'digest', 'duplicate', 'framework', 'source'):
            with self.subTest(change=change):
                p, rows, framework = self.fixture()
                if change == 'missing': rows.pop()
                if change == 'digest': rows[0]['RecordJSON'] += ' '
                if change == 'duplicate': rows.append(rows[-1])
                if change == 'framework': framework['FrameworkKey'] = 'other'
                if change == 'source': p['records'][0]['SourceURL'] += '/other'
                with self.assertRaises(ValueError): bind(p, rows, framework)
