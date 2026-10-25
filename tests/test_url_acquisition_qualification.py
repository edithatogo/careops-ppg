import contextlib
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppg_url_acquisition_qualification import build, main, verify_readback, API, MAX_BYTES, POLL_COUNT


def profile():
    raw = b'%PDF-1.4\nFICTIONAL qualification fixture\n%%EOF\n'
    return {'qualificationId': '11111111-2222-4333-8444-555555555555',
            'sourceKey': 'fictional-framework-source', 'frameworkEditionId': 'fictional-published-edition',
            'sourceURL': 'https://publisher.example/edition.pdf',
            'allowedOrigins': ['https://publisher.example'],
            'stagingRoot': '/Fictional URL qualification',
            'ownershipEvidence': 'FICTIONAL staging and new-flow assignment; not a native receipt',
            'connectionReference': {'id': API, 'connectionName': 'fictional-existing-connection', 'source': 'Embedded'},
            'expectedBytes': len(raw), 'expectedSHA256': hashlib.sha256(raw).hexdigest()}


def nodes(value):
    if isinstance(value, dict):
        if 'type' in value and 'runAfter' in value:
            yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def source_actions(flow):
    return flow['properties']['definition']['actions']['Select_fixed_source']['actions']


def readback_fixture():
    p = profile()
    raw = b'%PDF-1.4\nFICTIONAL qualification fixture\n%%EOF\n'
    actions = source_actions(build(p))['Require_ready']['actions']['Require_expected_metadata']['actions']
    report = copy.deepcopy(actions['Require_stable_metadata']['actions']['Report_candidate']['inputs'])
    metadata = {'Id': 'fictional-file', 'ETag': 'fictional-etag', 'Size': len(raw), 'IsFolder': False}
    report.update(metadataBefore=metadata, metadataAfter=copy.deepcopy(metadata),
                  content={'$content-type': 'application/octet-stream',
                           '$content': base64.b64encode(raw).decode('ascii')},
                  runName='fictional-run', uploadAttempted=True, pollAttempts=2)
    return p, report, raw


class ReadbackVerificationTests(unittest.TestCase):
    def test_actual_bytes_verified_without_promoting_expected_values_or_native_acceptance(self):
        p, report, raw = readback_fixture()
        before = copy.deepcopy((p, report))
        result = verify_readback(p, report, raw)
        self.assertTrue(result['independentByteParityVerified'])
        self.assertEqual(result['actualRawSHA256'], hashlib.sha256(raw).hexdigest())
        for key in ('nativeAcquisitionQualified', 'checkpointAdvanced', 'redirectsVerified',
                    'representationVerified', 'runProvenanceAuthenticated'):
            self.assertIs(result[key], False)
        self.assertEqual(result['catalogueWrites'], 0)
        self.assertEqual((p, report), before)

    def test_same_size_wrong_bytes_cannot_pass_expected_digest(self):
        p, report, raw = readback_fixture()
        changed = raw.replace(b'FICTIONAL', b'DIFFERENT')
        report['content']['$content'] = base64.b64encode(changed).decode('ascii')
        with self.assertRaisesRegex(ValueError, 'pinned source digest'):
            verify_readback(p, report, changed)
        with self.assertRaisesRegex(ValueError, 'connector bytes differ'):
            verify_readback(p, report, raw)

    def test_different_profile_or_stage_refuses(self):
        for key in ('qualificationId', 'sourceKey', 'frameworkEditionId', 'requestedSourceURL',
                    'stagingPath', 'expectedRawSHA256', 'state'):
            p, report, raw = readback_fixture(); report[key] = 'different'
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_readback(p, report, raw)

    def test_unstable_file_or_boolean_size_refuses(self):
        for key, value in [('Id', 'another-file'), ('ETag', 'changed'), ('Size', True),
                           ('Size', 0), ('IsFolder', True)]:
            p, report, raw = readback_fixture(); report['metadataAfter'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_readback(p, report, raw)

    def test_unverified_producer_cannot_smuggle_acceptance_assertions(self):
        for key, value in [('actualRawSHA256', 'a'*64), ('finalSourceURL', 'https://publisher.example/'),
                           ('byteIntegrityVerified', True), ('redirectsVerified', True),
                           ('nativeAcquisitionQualified', True), ('catalogueWrites', False),
                           ('checkpointAdvanced', True), ('notificationsEnabled', True)]:
            p, report, raw = readback_fixture(); report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify_readback(p, report, raw)

    def test_unknown_representation_and_malformed_or_large_encoding_refuse(self):
        for content in ['plain text', {'$content': 'AA=='},
                        {'$content-type': 'application/pdf', '$content': '!'*64},
                        {'$content-type': 'application/pdf', '$content': 'A'*(MAX_BYTES*2)}]:
            p, report, raw = readback_fixture(); report['content'] = content
            with self.subTest(kind=type(content)), self.assertRaises(ValueError):
                verify_readback(p, report, raw)

    def test_missing_run_and_invalid_poll_observations_refuse(self):
        for key, value in [('runName', ''), ('runName', '@workflow()'),
                           ('uploadAttempted', 1), ('pollAttempts', True),
                           ('pollAttempts', POLL_COUNT+1), ('pollAttempts', -1)]:
            p, report, raw = readback_fixture(); report[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify_readback(p, report, raw)

    def test_invalid_and_noncanonical_base64_with_expected_length_refuse(self):
        for encoded in ('!!!!', 'Zh=='):
            p, report, _ = readback_fixture(); raw = b'f'
            p.update(expectedBytes=1, expectedSHA256=hashlib.sha256(raw).hexdigest())
            report['expectedRawSHA256'] = p['expectedSHA256']
            report['metadataBefore']['Size'] = report['metadataAfter']['Size'] = 1
            report['content']['$content'] = encoded
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                verify_readback(p, report, raw)

    def test_cli_requires_paired_readback_inputs_before_any_file_access(self):
        for option in ('--report', '--download'):
            with patch.object(sys, 'argv', ['verify', '--profile', 'absent', '--output',
                                            '.local/absent', option, 'absent']), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main()

    def test_cli_verifies_saved_inputs_without_replacing_receipt(self):
        p, report, raw = readback_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'.local'; root.mkdir()
            for name, data in [('profile.json', p), ('report.json', report)]:
                (root/name).write_text(json.dumps(data))
            (root/'download.bin').write_bytes(raw)
            args = ['verify', '--profile', str(root/'profile.json'), '--report', str(root/'report.json'),
                    '--download', str(root/'download.bin'), '--output', str(root/'receipt.json')]
            with patch.object(sys, 'argv', args), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 0)
                self.assertTrue(json.loads((root/'receipt.json').read_text())['independentByteParityVerified'])
                with self.assertRaises(FileExistsError):
                    main()
            (root/'download.bin').write_bytes(b'x'*(MAX_BYTES+1))
            args[-1] = str(root/'rejected.json')
            with patch.object(sys, 'argv', args), self.assertRaises(ValueError):
                main()
            self.assertFalse((root/'rejected.json').exists())


class URLQualificationTests(unittest.TestCase):
    def test_stopped_fixed_source_profile_never_claims_runtime_acceptance(self):
        original = profile()
        before = copy.deepcopy(original)
        flow = build(original)
        self.assertEqual(original, before)
        props = flow['properties']
        self.assertEqual(props['state'], 'Stopped')
        self.assertIs(props['flowFailureAlertSubscribed'], False)  # Desired state, not readback proof.
        trigger = props['definition']['triggers']['manual']
        self.assertEqual((trigger['type'], trigger['kind']), ('Request', 'Button'))
        self.assertEqual(trigger['inputs']['schema']['properties']['sourceKey']['enum'], [original['sourceKey']])
        manifest = source_actions(flow)['Profile']['inputs']
        self.assertTrue(manifest['priorNativeRunsMustBeZero'])
        self.assertTrue(manifest['singleInvocationQualificationOnly'])
        self.assertFalse(manifest['nativeAcceptanceEstablished'])

    def test_missing_extra_and_nonobject_profiles_refuse(self):
        for candidate in [None, [], {}, {**profile(), 'arbitraryURL': 'https://other.example/file'}]:
            with self.assertRaises(ValueError):
                build(candidate)
        for field in profile():
            candidate = profile(); candidate.pop(field)
            with self.assertRaises(ValueError):
                build(candidate)

    def test_source_host_credentials_scheme_fragment_and_expressions_refuse(self):
        for url in ['http://publisher.example/a.pdf', 'https://other.example/a.pdf',
                    'https://user:secret@publisher.example/a.pdf', 'https://publisher.example:444/a.pdf',
                    'https://publisher.example/a.pdf#page=1', 'https://publisher.example/@{variables(\'url\')}',
                    'https://publisher.example/bad\npath.pdf', 'https://publisher.example/bad\\path.pdf']:
            candidate = profile(); candidate['sourceURL'] = url
            with self.assertRaises(ValueError):
                build(candidate)
        for origins in [[], [None], ['https://publisher.example/'], ['https://publisher.example']*2]:
            candidate = profile(); candidate['allowedOrigins'] = origins
            with self.assertRaises(ValueError):
                build(candidate)

    def test_unallocated_or_unsafe_staging_and_missing_owner_refuse(self):
        for root in [None, '/', '/Documents', 'relative', '/a/../b', '/a//b', '/a/', '/a/%2e%2e', '/a:bad']:
            candidate = profile(); candidate['stagingRoot'] = root
            with self.assertRaises(ValueError):
                build(candidate)
        candidate = profile(); candidate['ownershipEvidence'] = None
        with self.assertRaises(ValueError):
            build(candidate)

    def test_dynamic_or_wrong_existing_connection_refuses(self):
        for ref in [None, {}, {'id': API, 'connectionName': '@triggerBody()', 'source': 'Embedded'},
                    {'id': API, 'connectionName': 'fixture', 'source': 'Invoker'},
                    {'id': '/providers/Microsoft.PowerApps/apis/shared_http', 'connectionName': 'fixture', 'source': 'Embedded'}]:
            candidate = profile(); candidate['connectionReference'] = ref
            with self.assertRaises(ValueError):
                build(candidate)

    def test_expected_digest_size_and_qualification_identity_are_bounded(self):
        for field, values in [('expectedBytes', [0, -1, True, MAX_BYTES+1, '123']),
                              ('expectedSHA256', ['unknown', 'A'*64, None]),
                              ('qualificationId', ['not-a-uuid', '00000000-0000-0000-0000-000000000000']),
                              ('sourceKey', ['@triggerBody()', "source'", 'with spaces'])]:
            for value in values:
                candidate = profile(); candidate[field] = value
                with self.assertRaises(ValueError):
                    build(candidate)

    def test_upload_is_fixed_create_only_and_has_no_automatic_retry(self):
        flow = build(profile())
        operations = [x for x in nodes(flow) if x['type'] == 'OpenApiConnection']
        uploads = [x for x in operations if x['inputs']['host']['operationId'] == 'CopyFile']
        self.assertEqual(len(uploads), 1)
        params = uploads[0]['inputs']['parameters']
        self.assertEqual(params['source'], profile()['sourceURL'])
        self.assertIs(params['overwrite'], False)
        self.assertEqual(params['destination'], profile()['stagingRoot']+'/'+profile()['qualificationId']+'.captured')
        for action in operations:
            self.assertEqual(action['inputs']['retryPolicy'], {'type': 'none'})
            self.assertEqual(action['inputs']['host']['apiId'], API)
        self.assertFalse(any(x['type'] in ('Http', 'Workflow', 'OpenApiConnectionWebhook') for x in nodes(flow)))

    def test_existing_stage_reads_without_copy_and_failed_probe_must_be_404(self):
        resolve = source_actions(build(profile()))['Resolve_stage']
        self.assertFalse(any(x.get('inputs', {}).get('host', {}).get('operationId') == 'CopyFile'
                             for x in nodes(resolve['actions'])))
        allow = resolve['else']['actions']['Allow_create']
        self.assertEqual(allow['expression'], "@equals(outputs('Probe_stage')?['statusCode'],404)")
        self.assertEqual(allow['else']['actions']['Hold_probe_failure']['type'], 'Terminate')

    def test_bounded_polling_does_not_treat_upload_ack_as_completion(self):
        create = source_actions(build(profile()))['Resolve_stage']['else']['actions']['Allow_create']['actions']
        self.assertNotIn('acquisition_ready', json.dumps(create['Upload_fixed_source']))
        loop = create['Poll_for_completion']
        self.assertEqual(loop['limit'], {'count': POLL_COUNT, 'timeout': 'PT2M'})
        poll = loop['actions']['Observe_poll']
        self.assertEqual(poll['expression'], "@equals(actions('Poll_metadata')?['status'],'Succeeded')")
        self.assertIn("['Size']", poll['actions']['Check_size']['expression'])
        self.assertNotIn("body('Poll_metadata')", json.dumps(poll['else']))
        classify = poll['else']['actions']['Classify_failure']
        self.assertEqual(classify['expression'], "@not(equals(outputs('Poll_metadata')?['statusCode'],404))")
        self.assertIs(classify['actions']['Mark_error']['inputs']['value'], True)
        self.assertIn("variables('acquisition_error')", loop['expression'])

    def test_content_is_bracketed_by_id_etag_size_checks_not_digest_assertions(self):
        gate = source_actions(build(profile()))['Require_ready']['actions']['Require_expected_metadata']
        self.assertEqual(gate['runAfter'], {'Metadata_before': ['Succeeded']})
        for field in ['Id', 'ETag', 'Size', 'IsFolder']:
            self.assertIn("['"+field+"']", gate['expression'])
        self.assertEqual(gate['else']['actions']['Hold_before_content']['type'], 'Terminate')
        self.assertFalse(any(x['type'] == 'OpenApiConnection' for x in nodes(gate['else'])))
        actions = gate['actions']
        self.assertEqual(actions['Read_content']['runAfter'], {})
        self.assertEqual(actions['Metadata_after']['runAfter'], {'Read_content': ['Succeeded']})
        guard = actions['Require_stable_metadata']
        for field in ['Id', 'ETag', 'Size', 'IsFolder']:
            self.assertIn("['"+field+"']", guard['expression'])
        result = guard['actions']['Report_candidate']['inputs']
        self.assertEqual(result['expectedRawSHA256'], profile()['expectedSHA256'])
        self.assertIsNone(result['actualRawSHA256'])
        self.assertIsNone(result['finalSourceURL'])
        for field in ['byteIntegrityVerified', 'redirectsVerified', 'representationVerified',
                      'checkpointAdvanced', 'nativeAcquisitionQualified', 'clinicalApplicabilityAccepted']:
            self.assertIs(result[field], False)
        self.assertEqual(result['catalogueWrites'], 0)
        self.assertEqual(guard['else']['actions']['Hold_changed_stage']['type'], 'Terminate')

    def test_profile_is_not_mutated_through_returned_references(self):
        original = profile(); flow = build(original)
        flow['properties']['connectionReferences']['shared_onedriveforbusiness']['connectionName'] = 'changed'
        self.assertEqual(original['connectionReference']['connectionName'], 'fictional-existing-connection')

    def test_cli_preserves_existing_output_and_writes_private_file_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); private = root/'.local'; private.mkdir()
            source = private/'profile.json'; source.write_text(json.dumps(profile()))
            dest = private/'flow.json'
            with patch.object(sys, 'argv', ['builder', '--profile', str(source), '--output', str(dest)]):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(), 0)
                before = dest.read_bytes()
                with self.assertRaises(FileExistsError):
                    main()
                self.assertEqual(dest.read_bytes(), before)
            if os.name != 'nt':
                self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
            outside = root/'outside.json'
            with patch.object(sys, 'argv', ['builder', '--profile', str(source), '--output', str(outside)]):
                with self.assertRaises(SystemExit):
                    main()
            self.assertFalse(outside.exists())

    def test_cli_oversize_profile_refuses_without_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'.local'; root.mkdir()
            source = root/'profile.json'; source.write_bytes(b' '*(64*1024+1))
            dest = root/'flow.json'
            with patch.object(sys, 'argv', ['builder', '--profile', str(source), '--output', str(dest)]):
                with self.assertRaises(SystemExit):
                    main()
            self.assertFalse(dest.exists())

    def test_cli_refuses_an_external_interpreter_before_profile_access(self):
        with patch.object(sys, 'prefix', '/fictional-external-environment'):
            with self.assertRaisesRegex(SystemExit, 'repo-local Python'):
                main()


if __name__ == '__main__':
    unittest.main()
