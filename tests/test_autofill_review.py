"""Preservation, atomic concurrency and retry behavior of reviewed metadata."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('review', ROOT/'scripts/ppg_autofill_review.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT/'config/autofill-suggestions.json').read_text())
        self.snapshot = dict(contractVersion=self.config['reviewContractVersion'],
            configSHA256=m.fingerprint(self.config), promptVersion=self.config['promptVersion'],
            target=dict(site='https://example.invalid/pilot',libraryId='test',itemId=1),
            itemETag='"5"', source={'UniqueId':'fictional','version':'5.0','sha256':'a'*64},
            rawSuggestions=dict(zip(m.RAW,['equipment','stated purpose','Procedure'])),
            processing={'status':'Finished','classifiedAt':'2026-10-17T00:00:00Z'},
            item={k:None for k in (*m.REVIEWED,'ReviewOperationId','ReviewProvenance')})
        self.values=dict(zip(m.REVIEWED,['Human correction','Corrected fictional purpose','Procedure']))
        self.operation='00000000-0000-4000-8000-000000000101'

    def plan(self, current=None, values=None):
        return m.plan(self.snapshot, current or self.snapshot, values or self.values,
                      'fictional operator',self.operation,self.config)

    def test_payload_never_writes_machine_or_source_fields_and_keeps_provenance(self):
        result=self.plan()
        self.assertEqual(set(result),set(m.REVIEWED)|{'ReviewOperationId','ReviewProvenance'})
        proof=json.loads(result['ReviewProvenance'])
        self.assertEqual(proof['source'],self.snapshot['source'])
        self.assertEqual(proof['rawSuggestions'],self.snapshot['rawSuggestions'])
        self.assertEqual(proof['expectedItemETag'],'"5"')

    def test_item_source_raw_and_processing_changes_refuse(self):
        for key,value in [('itemETag','"6"'),('source',{'sha256':'b'*64}),
                          ('rawSuggestions',{}),('processing',{'status':'Running'})]:
            with self.subTest(key=key):
                current=copy.deepcopy(self.snapshot);current[key]=value
                with self.assertRaisesRegex(ValueError,'stale_'): self.plan(current)

    def test_pending_not_reviewable_even_if_stable(self):
        self.snapshot['processing']['status']='Running'
        with self.assertRaisesRegex(ValueError,'processing_not_finished'):self.plan()

    def test_no_canonical_fields_or_oversized_values(self):
        for values in [dict(self.values,DocumentUID='not-authorised'),
                       dict(self.values,ReviewedTopic='x'*121),
                       dict(self.values,ReviewedDocumentKind='Approved')]:
            with self.subTest(values=values),self.assertRaises(ValueError):self.plan(values=values)

    def test_unknown_response_recovery_is_read_only_and_request_bound(self):
        written=self.plan();current=copy.deepcopy(self.snapshot)
        current['item'].update(written);current['itemETag']='"6"'
        self.assertIsNone(self.plan(current))
        with self.assertRaisesRegex(ValueError,'operation_conflict'):
            self.plan(current,dict(self.values,ReviewedTopic='different'))

    def test_racing_change_reaches_native_exact_if_match_and_does_not_retry(self):
        client=object.__new__(m.Pilot);client.base='https://example.invalid/items'
        calls=[]
        client.capture=lambda *args:copy.deepcopy(self.snapshot)
        def conflict(url,**kwargs):
            calls.append(kwargs)
            raise RuntimeError('native_request_failed:412 Precondition Failed')
        client.request=conflict
        with self.assertRaisesRegex(RuntimeError,'412'):
            client.apply(self.snapshot,self.values,'fictional operator',self.operation,self.config)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['etag'],'"5"')
        self.assertFalse(set(calls[0]['payload']) & set(m.RAW))

    def test_request_requires_exact_etag(self):
        client=object.__new__(m.Pilot)
        for etag in [None,'*']:
            with self.assertRaisesRegex(ValueError,'exact_etag_required'):
                client.request('https://example.invalid',payload={},etag=etag)

    def test_reviewed_autofill_ownership_and_raw_prompt_drift_refused(self):
        fields=[]
        for col in self.config['columns']:
            fields.append(dict(InternalName=col['internalName'],TypeAsString=col['type'],
                               AutofillInfo=json.dumps({'LLM':{'Prompt':col['prompt']}})))
        for col in self.config['reviewedFields']:
            fields.append(dict(InternalName=col['internalName'],TypeAsString=col['type'],AutofillInfo=None))
        client=object.__new__(m.Pilot);client.base='https://example.invalid'
        client.request=lambda *args:{'value':fields}
        client.ownership(self.config)
        fields[-1]['AutofillInfo']='{"LLM":{"IsEnabled":false}}'
        with self.assertRaisesRegex(ValueError,'reviewed_field_not_separate'):client.ownership(self.config)
        fields[-1]['AutofillInfo']=None;fields[0]['AutofillInfo']='{"LLM":{"Prompt":"drift"}}'
        with self.assertRaisesRegex(ValueError,'raw_prompt_contract_changed'):client.ownership(self.config)

    def test_native_request_transmits_if_match_and_merge(self):
        client=object.__new__(m.Pilot)
        with patch.object(m.subprocess,'run') as run:
            run.return_value.returncode=0;run.return_value.stdout='';run.return_value.stderr=''
            client.request('https://example.invalid',payload={'ReviewedTopic':'x'},etag='"5"')
            args=run.call_args.args[0]
            self.assertEqual(args[args.index('--if-match')+1],'"5"')
            self.assertEqual(args[args.index('--x-http-method')+1],'MERGE')


if __name__ == '__main__': unittest.main()
