"""Offline evidence corruption checks; fictional data only, no service calls."""
import base64
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ppg_cited_reader_proof as proof_module
from ppg_cited_reader_proof import ACTIONS, BOUNDARY, LABELS, verify_evidence
from test_cited_reader_flow import binding as reader_binding


def sample():
    source = 'Fictional retained source — unapproved.\n'.encode()
    binding = reader_binding(); binding['pin']['Length'] = len(source)
    pin = {k: str(v) for k, v in binding['pin'].items()}
    payload = {'$content-type': 'application/octet-stream', '$content': base64.b64encode(source).decode()}
    result = {
        'schemaVersion': 1, 'sourceId': binding['sourceId'],
        'canonicalUrl': 'https://example.sharepoint.com' + pin['ServerRelativeUrl'],
        'nativeUniqueId': pin['UniqueId'], 'nativeVersionRef': '1.0', 'nativePin': pin,
        'authorityLabel': binding['authorityLabel'], 'contentBoundary': BOUNDARY,
        'sha256': None, 'binarySHA256': None, 'textExtractionQualified': False,
        'nativeAssistantRuntimeQualified': False, 'status': 'selected-source-read',
        'content': payload,
    }
    bundle = {}
    for i, label in enumerate(LABELS):
        start = datetime(2026, 10, 24, tzinfo=timezone.utc) + timedelta(minutes=i)
        stamp = lambda offset: (start + timedelta(seconds=offset)).isoformat().replace('+00:00', 'Z')
        run = {'name': 'fictional-' + label, 'id': '/environments/fictional/flows/reader/runs/fictional-' + label,
               'properties': {'status': 'Failed' if label == 'refusal' else 'Succeeded',
                              'startTime': stamp(0), 'endTime': stamp(2)}}
        statuses = {k: 'Succeeded' for k in ACTIONS}
        statuses.update(Refuse_SOURCE_PIN='Skipped', Refuse_SOURCE_CHANGED='Skipped')
        if label == 'refusal':
            run['properties']['error'] = {'code': 'SOURCE_PIN'}
            statuses = {k: 'Skipped' for k in ACTIONS}
            statuses.update(Metadata_before='Succeeded', Refuse_SOURCE_PIN='Succeeded',
                            Require_expected_source='Cancelled')
        rows = [{'name': k, 'id': run['id'] + '/actions/' + k, 'properties': {'status': statuses[k]}}
                for k in sorted(ACTIONS)]
        outputs = {'Metadata_before': {'body': copy.deepcopy(pin)}}
        if label != 'refusal':
            outputs.update(Metadata_after={'body': copy.deepcopy(pin)}, Read_content={'body': copy.deepcopy(payload)},
                           Selected_source_result={**copy.deepcopy(result), 'retrievedAtUtc': stamp(1)})
        bundle[label] = {'run': run, 'actions': {'value': rows, 'nativePages': [{'value': copy.deepcopy(rows)}],
                                               'complete': True}, 'outputs': outputs}
    return binding, source, bundle


class ReaderProofTests(unittest.TestCase):
    def test_four_run_proof_and_inputs_preserved(self):
        binding, source, bundle = sample(); before = copy.deepcopy((binding, bundle))
        result = verify_evidence(binding, source, bundle)
        self.assertTrue(result['offlineEvidenceConsistent'])
        self.assertEqual(result['returnedBytes'], len(source))
        self.assertEqual(len(result['runs']), 4)
        self.assertFalse(result['nativeEvidenceAuthenticityQualified'])
        self.assertFalse(result['currentNativeStateVerified'])
        self.assertFalse(result['nativeAssistantRuntimeQualified'])
        self.assertFalse(result['callerPermissionTrimmingQualified'])
        self.assertFalse(result['clinicalAcceptance'])
        self.assertEqual((binding, bundle), before)

    def rejects(self, edit):
        binding, source, bundle = sample(); edit(binding, bundle)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            verify_evidence(binding, source, bundle)

    def test_each_pin_field_before_and_after_must_match(self):
        for position in ('Metadata_before', 'Metadata_after'):
            for field in reader_binding()['pin']:
                with self.subTest(position=position, field=field):
                    self.rejects(lambda b, e: e['recovery']['outputs'][position]['body'].__setitem__(field, 'changed'))

    def test_same_length_read_and_result_edits_refuse(self):
        for action in ('Read_content', 'Selected_source_result'):
            def edit(b, e):
                value = e['replay']['outputs'][action]
                value = value['body'] if action == 'Read_content' else value['content']
                original = base64.b64decode(value['$content'])
                value['$content'] = base64.b64encode(b'X' + original[1:]).decode()
            with self.subTest(action=action):self.rejects(edit)

    def test_hash_claims_and_acceptance_flags_cannot_be_promoted(self):
        for key, value in [('sha256', 'copied-expected-digest'), ('binarySHA256', 'copied-expected-digest'),
                           ('textExtractionQualified', True), ('nativeAssistantRuntimeQualified', True),
                           ('textExtractionQualified', 0), ('schemaVersion', True)]:
            with self.subTest(key=key, value=value):
                self.rejects(lambda b, e: e['first']['outputs']['Selected_source_result'].__setitem__(key, value))

    def test_result_identity_authority_and_extra_fields_refuse(self):
        for field in ('sourceId', 'canonicalUrl', 'nativeUniqueId', 'nativeVersionRef', 'authorityLabel', 'status'):
            with self.subTest(field=field):
                self.rejects(lambda b, e: e['first']['outputs']['Selected_source_result'].__setitem__(field, 'changed'))
        self.rejects(lambda b, e: e['first']['outputs']['Selected_source_result'].__setitem__('clinicalAcceptance', True))

    def test_refusal_cannot_execute_content_or_result(self):
        for action in ('Read_content', 'Selected_source_result'):
            def edit(b, e):
                h = e['refusal']['actions']
                for rows in (h['value'], h['nativePages'][0]['value']):
                    next(x for x in rows if x['name'] == action)['properties']['status'] = 'Succeeded'
            with self.subTest(action=action):self.rejects(edit)
        self.rejects(lambda b, e: e['refusal']['outputs'].__setitem__('Read_content', {'body': 'unexpected'}))
        self.rejects(lambda b, e: e['refusal']['run']['properties']['error'].__setitem__('code', 'OTHER'))

    def test_complete_flag_does_not_substitute_for_exhausted_native_pages(self):
        self.rejects(lambda b, e: e['first']['actions']['nativePages'][-1].__setitem__('nextLink', 'https://example.invalid/next'))
        self.rejects(lambda b, e: e['first']['actions'].__setitem__('nativePages', []))
        self.rejects(lambda b, e: e['first']['actions']['value'].pop())
        self.rejects(lambda b, e: e['first']['actions'].__setitem__('complete', False))

    def test_duplicate_missing_and_cross_run_actions_refuse(self):
        def duplicate(b, e):
            h=e['first']['actions'];h['value'].append(copy.deepcopy(h['value'][0]));h['nativePages'][0]['value']=copy.deepcopy(h['value'])
        self.rejects(duplicate)
        def cross_run(b, e):
            h=e['first']['actions'];h['value'][0]['id']='another-run/actions/Metadata_after';h['nativePages'][0]['value']=copy.deepcopy(h['value'])
        self.rejects(cross_run)

    def test_nonserial_mixed_or_duplicate_runs_refuse(self):
        self.rejects(lambda b, e: e['replay']['run']['properties'].__setitem__('startTime', e['first']['run']['properties']['startTime']))
        self.rejects(lambda b, e: e['replay']['run'].__setitem__('id', '/flows/other/runs/fictional-replay'))
        self.rejects(lambda b, e: e.__setitem__('replay', copy.deepcopy(e['first'])))

    def test_result_timestamp_must_be_utc_and_within_its_actual_run(self):
        for stamp in ('2026-10-23T00:00:00Z', '2026-10-24T00:00:01', 'not-a-time'):
            with self.subTest(stamp=stamp):
                self.rejects(lambda b, e: e['first']['outputs']['Selected_source_result'].__setitem__('retrievedAtUtc', stamp))

    def test_invalid_binary_shape_base64_or_retained_length_refuses(self):
        self.rejects(lambda b, e: e['first']['outputs']['Selected_source_result']['content'].__setitem__('$content', '%%%'))
        self.rejects(lambda b, e: e['first']['outputs']['Read_content']['body'].__setitem__('unverified', True))
        self.rejects(lambda b, e: b['pin'].__setitem__('Length', 1))

    def test_malformed_container_types_fail_closed(self):
        binding, source, bundle = sample()
        with self.assertRaises(ValueError):verify_evidence([], source, bundle)
        self.rejects(lambda b, e: e['refusal']['run']['properties'].__setitem__('error', []))
        self.rejects(lambda b, e: e['first']['run'].__setitem__('properties', []))
        self.rejects(lambda b, e: e['first'].__setitem__('outputs', []))
        def broken_row(b, e):
            h=e['first']['actions'];h['value'][0]='invalid';h['nativePages'][0]['value']=copy.deepcopy(h['value'])
        self.rejects(broken_row)

    def test_real_cli_shape_succeeds_and_private_error_content_is_not_echoed(self):
        binding, source, bundle = sample()
        with tempfile.TemporaryDirectory() as root:
            p=Path(root);(p/'binding.json').write_text(json.dumps(binding));(p/'source.txt').write_bytes(source)
            for label, item in bundle.items():
                for kind in ('run','actions'):(p/(label+'-'+kind+'.json')).write_text(json.dumps(item[kind]))
                for key, value in item['outputs'].items():(p/(label+'-'+key+'-outputs.json')).write_text(json.dumps(value))
            args=[sys.executable,str(Path(proof_module.__file__)),'--binding',str(p/'binding.json'),'--source',str(p/'source.txt'),'--evidence-directory',str(p)]
            run=subprocess.run(args,capture_output=True,text=True,check=False)
            self.assertEqual(run.returncode,0,run.stderr);self.assertTrue(json.loads(run.stdout)['offlineEvidenceConsistent'])
            (p/'binding.json').write_text('PRIVATE-CORRUPT-BINDING')
            run=subprocess.run(args,capture_output=True,text=True,check=False)
            self.assertEqual(run.returncode,1);self.assertNotIn('PRIVATE-CORRUPT-BINDING',run.stdout+run.stderr)
            self.assertFalse(json.loads(run.stdout)['offlineEvidenceConsistent'])
            (p/'binding.json').write_text('[]')
            run=subprocess.run(args,capture_output=True,text=True,check=False)
            self.assertEqual(run.returncode,1);self.assertNotIn('Traceback',run.stdout+run.stderr)
            self.assertFalse(json.loads(run.stdout)['offlineEvidenceConsistent'])


if __name__ == '__main__':unittest.main()
