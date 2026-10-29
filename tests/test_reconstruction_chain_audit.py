# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.ppg_reconstruction_chain_audit import audit, pointer, verify_custody_navigation, verify_decision_contracts, verify_improvement_fixture, verify_improvement_technical_case, verify_legacy_request_histories, verify_legacy_request_record_history, verify_narrative_citations, verify_request_chains, verify_requirement_corpus, verify_selected_index, verify_workflow_lookups


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, obj):
    data = json.dumps(obj).encode()
    path.write_bytes(data)
    return sha(data)


class ChainAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'reconstruction-package-v1'
        self.ext = self.root / 'reconstruction-package-extension-v1'
        self.base.mkdir()
        self.ext.mkdir()
        (self.base / 'data').write_bytes(b'base')
        base_sha = write(self.base / 'package-manifest.json', {'files': [{'path': 'data', 'sha256': sha(b'base'), 'bytes': 4}]})
        (self.ext / 'result').write_bytes(b'extension')
        self.head = write(self.ext / 'extension-manifest.json', {'basePackageManifestSha256': base_sha,
                           'files': [{'path': 'result', 'sha256': sha(b'extension'), 'bytes': 9}]})

    def test_full_chain(self):
        result = audit(self.root, self.head)
        self.assertEqual((result['extensions'], result['artifactsChecked'], result['nativeWrites']), (1, 2, 0))

    def test_changed_artifact_and_head_fail(self):
        (self.ext / 'result').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            audit(self.root, self.head)
        (self.ext / 'result').write_bytes(b'extension')
        with self.assertRaises(ValueError):
            audit(self.root, '0' * 64)

    def test_symlink_and_path_traversal_fail(self):
        (self.ext / 'result').unlink()
        (self.ext / 'result').symlink_to(self.base / 'data')
        with self.assertRaises(ValueError):
            audit(self.root, self.head)
        manifest = json.loads((self.base / 'package-manifest.json').read_text())
        manifest['files'][0]['path'] = '../outside'
        write(self.base / 'package-manifest.json', manifest)
        with self.assertRaises(ValueError):
            audit(self.root, self.head)

    def test_extension_gap_fails(self):
        (self.root / 'reconstruction-package-extension-v3').mkdir()
        with self.assertRaises(ValueError):
            audit(self.root, self.head)

    def test_request_chain_preserves_legacy_ids_and_rejects_broken_parent(self):
        ext10 = self.root / 'reconstruction-package-extension-v10'
        ext10.mkdir()
        (self.base / 'evidence').mkdir()
        mapping = {'RequirementKey': 'r', 'ReviewContextKey': 'scope', 'EvidenceVersionKey': 'v'}
        for side in ('live', 'recovery'):
            write(self.base / 'evidence' / (side + '.json'), {'mapping': mapping})
        write(self.ext / 'selected-reconstruction-index-v4.json', {'workflowCohort': {'liveReadback': 'live.json',
              'recoveryReadback': 'recovery.json', 'nodes': [{'kind': 'mappings', 'key': 'm',
              'livePointer': '/mapping', 'recoveryPointer': '/mapping'}]}})
        request = {'RequestKey': 'req', 'RequestState': 'open', 'ClosureDetailsJSON': None,
                   'RequirementKey': 'r', 'ReviewContextKey': 'scope'}
        assignment = {'EventKey': 'outer-assignment', 'RequestKey': 'req', 'EventKind': 'Assignment',
                      'EventPayloadJSON': json.dumps({'AssignmentEventKey': 'inner-assignment', 'RequestKey': 'req'})}
        payload = {'ResponseEventKey': 'inner-response', 'RequestKey': 'req', 'State': 'received',
                   'OccurredAt': '2026-01-01', 'EvidenceVersionKey': 'v', 'MappingKey': 'm', 'PreviousResponseEventKey': None}
        response = {'EventKey': 'outer-response', 'RequestKey': 'req', 'EventKind': 'Response', 'ResponseState': 'received',
                    'OccurredAt': '2026-01-01T00:00:00Z', 'EvidenceVersionKey': 'v', 'MappingKey': 'm',
                    'EventPayloadJSON': json.dumps(payload)}
        support = []
        for side in ('live', 'recovery'):
            support.extend([{'side': side, 'group': 'requests', 'key': 'req', 'row': copy.deepcopy(request)},
                            {'side': side, 'group': 'events', 'key': 'outer-assignment', 'row': copy.deepcopy(assignment)},
                            {'side': side, 'group': 'events', 'key': 'outer-response', 'row': copy.deepcopy(response)}])
        path = ext10 / 'workflow-lookup-evidence-v2-20261029.json'
        write(path, {'support': support})
        self.assertEqual(verify_request_chains(self.root)['bySide']['live']['responses'], 1)
        payload['PreviousResponseEventKey'] = 'missing'
        for item in support:
            if item['key'] == 'outer-response':
                item['row']['EventPayloadJSON'] = json.dumps(payload)
        write(path, {'support': support})
        with self.assertRaisesRegex(ValueError, 'history chain mismatch'):
            verify_request_chains(self.root)

    def test_legacy_event_creation_and_lookup_history(self):
        ext10 = self.root / 'reconstruction-package-extension-v10'
        ext18 = self.root / 'reconstruction-package-extension-v18'
        ext10.mkdir()
        ext18.mkdir()
        fields = ('EventKey', 'RequestKey', 'EventKind', 'ResponseState', 'MappingKey', 'EvidenceVersionKey',
                  'SourceLocator', 'ActorRoleRef', 'OccurredAt', 'PreviousEventKey', 'EventPayloadJSON',
                  'AssignmentEventKey', 'ResponseEventKey', 'OwnerIdentityRef', 'DelegateRoleRefsJSON',
                  'EffectiveAt', 'Reason', 'ActorIdentityRef', 'DecisionRef', 'Rationale', 'ContractEventJSON')
        baseline, support, records = [], [], []
        for key in ('one', 'two'):
            row = {field: None for field in fields}
            row['EventKey'] = key
            baseline.append(row)
            for side in ('live', 'recovery'):
                selected = dict(row, OData__UIVersionString='1.0', RequestLinkId=None, MappingLinkId=None, EvidenceVersionLinkId=None)
                support.append({'side': side, 'group': 'events', 'key': key, 'row': selected})
                version = dict(row, VersionLabel='1.0', IsCurrentVersion=True)
                records.append({'side': side, 'kind': 'event', 'key': key, 'pages': 1, 'history': [version]})
        history_name = 'legacy-request-event-history-readback-20261029.json'
        baseline_name = 'query-response-pilot-reconciliation-v3.json'
        write(ext10 / 'workflow-lookup-evidence-v2-20261029.json', {'support': support})
        write(ext18 / history_name, {'nativeWrites': 0, 'records': records})
        write(ext18 / baseline_name, {'readOnly': True, 'events': baseline})
        write(ext18 / 'extension-manifest.json', {'files': [{'path': history_name}, {'path': baseline_name}]})
        self.assertEqual(verify_legacy_request_histories(self.root)['histories'], 4)
        records[0]['history'][0]['EventPayloadJSON'] = 'changed'
        write(ext18 / history_name, {'nativeWrites': 0, 'records': records})
        with self.assertRaisesRegex(ValueError, 'business history mismatch'):
            verify_legacy_request_histories(self.root)

    def test_legacy_request_history_rejects_changed_creation_fields(self):
        ext10 = self.root / 'reconstruction-package-extension-v10'
        ext18 = self.root / 'reconstruction-package-extension-v18'
        ext19 = self.root / 'reconstruction-package-extension-v19'
        for path in (ext10, ext18, ext19):
            path.mkdir()
        fields = ('Title', 'RequestKey', 'ReviewContextKey', 'AssessmentKey', 'ExpectationVersionKey', 'RequirementKey',
                  'ScopeKey', 'DueDate', 'RequestState', 'RequestDedupeKey', 'ResponsibleRoleRef', 'RequestedAt',
                  'RequestFingerprint', 'DelegateRoleRefsJSON', 'ClosureDetailsJSON')
        baseline = {field: None for field in fields}
        baseline['RequestKey'] = 'req'
        baseline['ResponsibleRoleRef'] = 'role'
        write(ext18 / 'query-response-pilot-reconciliation-v3.json', {'readOnly': True, 'request': baseline})
        support, records = [], []
        for side in ('live', 'recovery'):
            selected = dict(baseline, OData__UIVersionString='1.0', ReviewContextLinkId=None, AssessmentLinkId=None,
                            RequirementLinkId=None, ExpectationVersionLinkId=None)
            support.append({'side': side, 'group': 'requests', 'key': 'req', 'row': selected})
            records.append({'side': side, 'kind': 'request', 'key': 'req', 'pages': 1,
                            'history': [dict(baseline, VersionLabel='1.0', IsCurrentVersion=True)]})
        write(ext10 / 'workflow-lookup-evidence-v2-20261029.json', {'support': support})
        name = 'legacy-request-history-readback-20261029.json'
        write(ext19 / name, {'nativeWrites': 0, 'records': records})
        write(ext19 / 'extension-manifest.json', {'files': [{'path': name}]})
        self.assertEqual(verify_legacy_request_record_history(self.root)['histories'], 2)
        records[0]['history'][0]['ResponsibleRoleRef'] = 'changed'
        write(ext19 / name, {'nativeWrites': 0, 'records': records})
        with self.assertRaisesRegex(ValueError, 'business history mismatch'):
            verify_legacy_request_record_history(self.root)

    def test_pointer_decoding_and_invalid_index(self):
        self.assertEqual(pointer({'a/b': {'~key': [4]}}, '/a~1b/~0key/0'), 4)
        with self.assertRaises(ValueError):
            pointer({'a': [4]}, '/a/-1')
        with self.assertRaises(ValueError):
            pointer({'a': 1}, '/a~2')

    def test_narrative_citation_provenance_and_locator_bounds(self):
        def extension(number, name, data):
            directory = self.root / f'reconstruction-package-extension-v{number}'
            directory.mkdir(exist_ok=True)
            write(directory / name, data)
            write(directory / 'extension-manifest.json', {'files': [{'path': name}]})
        evidence = self.base / 'evidence'
        evidence.mkdir()
        blob = b'first\nsecond\n'
        digest = sha(blob)
        (self.base / 'bytes').mkdir()
        (self.base / 'bytes' / (digest + '.bin')).write_bytes(blob)
        citations = [{'kind': 'requirement-source', 'requirementKey': 'r', 'editionKey': 'edition', 'captureKey': 'capture',
                      'fileUniqueId': 'source-file', 'itemId': 8, 'locator': 'PDF page 4'},
                     {'kind': 'synthetic-evidence', 'mappingKey': 'm', 'evidenceVersionKey': 'v', 'locator': 'Fixture lines 1–2', 'sha256': digest}]
        row = {'RequirementKey': 'r', 'CitationsJSON': json.dumps(citations)}
        lookup = {'support': [{'side': side, 'group': 'narratives', 'key': 'n', 'row': copy.deepcopy(row)}
                              for side in ('live', 'recovery')]}
        extension(10, 'workflow-lookup-evidence-v2-20261029.json', lookup)
        extension(11, 'expected-node-manifest-v1.json', {'edition': {'fileUniqueId': 'source-file', 'CaptureKey': 'capture',
                  'EditionKey': 'edition', 'SourceSHA256': 'capture-sha'}})
        req = {'RequirementKey': 'r', 'CaptureKey': 'capture', 'EditionKey': 'edition', 'SourceLocator': 'PDF page 4'}
        extension(14, 'corpus-capture-link-postflight-20261029.json', {'snapshots': {side: {'inventory': {'rows': [req]}}
                  for side in ('source', 'recovery')}})
        extension(15, 'capture-source-copy-owner-readback-20261029.json', {'results': [{'side': 'source', 'id': 'source-file', 'sha256': 'capture-sha'}]})
        extension(16, 'narrative-citation-source-native-20261029.json', {'nativeWrites': 0, 'fileUniqueId': 'source-file', 'itemId': 8,
                  'expectedCaptureKey': 'capture', 'expectedSourceSha256': 'capture-sha'})
        document = {'mapping': {'RequirementKey': 'r', 'EvidenceVersionKey': 'v'}, 'version': {'OData__x0053_HA256': digest}}
        write(evidence / 'live.json', document)
        write(evidence / 'recovery.json', document)
        nodes = [{'kind': 'mappings', 'key': 'm', 'livePointer': '/mapping', 'recoveryPointer': '/mapping'},
                 {'kind': 'versions', 'key': 'v', 'livePointer': '/version', 'recoveryPointer': '/version'}]
        extension(1, 'selected-reconstruction-index-v4.json', {'workflowCohort': {'liveReadback': 'live.json',
                  'recoveryReadback': 'recovery.json', 'nodes': nodes}})
        self.assertEqual(verify_narrative_citations(self.root)['citationsPerSide'], 2)
        lookup['support'][1]['row']['CitationsJSON'] = '[]'
        extension(10, 'workflow-lookup-evidence-v2-20261029.json', lookup)
        with self.assertRaisesRegex(ValueError, 'citation JSON changed'):
            verify_narrative_citations(self.root)
        lookup['support'][1]['row']['CitationsJSON'] = lookup['support'][0]['row']['CitationsJSON']
        citations[1]['locator'] = 'Fixture lines 1–3'
        for item in lookup['support']:
            item['row']['CitationsJSON'] = json.dumps(citations)
        extension(10, 'workflow-lookup-evidence-v2-20261029.json', lookup)
        with self.assertRaisesRegex(ValueError, 'locator outside'):
            verify_narrative_citations(self.root)

    def test_decision_contract_rejects_changed_state_and_real_authority(self):
        ext10 = self.root / 'reconstruction-package-extension-v10'
        ext17 = self.root / 'reconstruction-package-extension-v17'
        ext10.mkdir()
        ext17.mkdir()
        decision = {'DecisionKey': 'd', 'SourceLocator': 'JSON Pointer /package/decisions/0'}
        condition = {'ConditionKey': 'c', 'DecisionKey': 'd', 'ConditionState': 'outstanding'}
        change = {'ChangeKey': 'ch', 'DecisionKey': 'd', 'SubmissionState': 'not-submitted'}
        package = {'fixtureOnly': True, 'submissionEnabled': False, 'notificationsEnabled': False,
                   'decisions': [decision], 'conditions': [condition], 'changes': [change]}
        blob = json.dumps({'package': package}).encode()
        digest = sha(blob)
        (self.base / 'bytes').mkdir()
        (self.base / 'bytes' / (digest + '.bin')).write_bytes(blob)
        details = json.dumps({'fixtureOnly': True, 'realIssuerAuthorityVerified': False})
        page = lambda rows: {'rows': rows, 'pages': 1, 'terminalPageReached': True}
        native = {'readOnly': True, 'identityVerified': True, 'siteAdminVerified': True, 'nativeWrites': 0, 'scope': 'scope',
                  'queries': {'decisions': page([{'DecisionKey': 'd', 'ReviewContextKey': 'scope', 'SourceEvidenceVersionKey': 'v',
                              'SourceLocator': decision['SourceLocator'], 'DecisionDetailsJSON': details}]),
                              'events': page([{'DecisionEventKey': 'c', 'ConditionKey': 'c', 'DecisionKey': 'd', 'EventKind': 'condition',
                                               'EventState': 'outstanding', 'EventDetailsJSON': details},
                                              {'DecisionEventKey': 'ch', 'ConditionKey': None, 'DecisionKey': 'd', 'EventKind': 'change',
                                               'EventState': 'not-submitted', 'EventDetailsJSON': details}]),
                              'versions': page([{'EvidenceVersionKey': 'v', 'SourceItemKey': 'fileUniqueId:file',
                              'ExactVersion': 'file version 1.0; UniqueId file; SHA-256 ' + digest}])}}
        native_name, source_name = 'condition-source-native-readback-20261029.json', 'condition-source-file-readback-20261029.json'
        native_hash = write(ext17 / native_name, native)
        write(ext17 / source_name, {'nativeWrites': 0, 'inputSha256': native_hash, 'fileId': 'file', 'fileVersion': '1.0',
                                   'sha256': digest, 'byteCount': len(blob), 'package': package})
        write(ext17 / 'extension-manifest.json', {'files': [{'path': native_name}, {'path': source_name}]})
        support = []
        for side in ('live', 'recovery'):
            support += [{'side': side, 'group': 'decisions', 'key': 'd', 'row': {'ContractDecisionJSON': json.dumps(decision)}},
                        {'side': side, 'group': 'decisionEvents', 'key': 'c', 'row': {'EventKind': 'condition', 'DecisionKey': 'd',
                         'EventState': 'outstanding', 'ContractEventJSON': json.dumps(condition)}},
                        {'side': side, 'group': 'decisionEvents', 'key': 'ch', 'row': {'EventKind': 'change', 'DecisionKey': 'd',
                         'EventState': 'not-submitted', 'ContractEventJSON': json.dumps(change)}}]
        support_name = 'workflow-lookup-evidence-v2-20261029.json'
        write(ext10 / support_name, {'support': support})
        self.assertEqual(verify_decision_contracts(self.root)['bySide']['recovery']['conditions'], 1)
        support[-2]['row']['EventState'] = 'externally-cleared'
        write(ext10 / support_name, {'support': support})
        with self.assertRaisesRegex(ValueError, 'event parent or state'):
            verify_decision_contracts(self.root)
        support[-2]['row']['EventState'] = 'outstanding'
        write(ext10 / support_name, {'support': support})
        native['queries']['decisions']['rows'][0]['DecisionDetailsJSON'] = json.dumps({'fixtureOnly': True, 'realIssuerAuthorityVerified': True})
        native_hash = write(ext17 / native_name, native)
        write(ext17 / source_name, {'nativeWrites': 0, 'inputSha256': native_hash, 'fileId': 'file', 'fileVersion': '1.0',
                                   'sha256': digest, 'byteCount': len(blob), 'package': package})
        with self.assertRaisesRegex(ValueError, 'authority mismatch'):
            verify_decision_contracts(self.root)

    def test_improvement_fixture_checks_source_counts_and_unknown_outcome(self):
        ext10 = self.root / 'reconstruction-package-extension-v10'
        ext10.mkdir()
        action_source = {'recordKey': 'action', 'recordVersion': '1', 'recordType': 'FictionalAction',
                         'ownerRoleRef': 'role', 'state': 'completed', 'dueDate': '2026-01-01', 'completedAt': '2026-01-01'}
        source = {'fixtureOnly': True, 'realServiceActivity': False, 'humanReviewClaimed': False, 'action': action_source,
                  'baseline': {'start': '2026-01-01', 'end': '2026-01-02', 'records': [{'fieldPresent': False}]},
                  'followUp': {'start': '2026-01-03', 'end': '2026-01-04', 'records': [{'fieldPresent': True}]}}
        raw = json.dumps(source).encode()
        digest = sha(raw)
        (self.base / 'bytes').mkdir()
        (self.base / 'bytes' / (digest + '.bin')).write_bytes(raw)
        reps = [{'role': role, 'sha256': digest, 'bytes': len(raw), 'fileUniqueId': 'file', 'nativeVersion': '1.0'}
                for role in ('improvement_files', 'improvement_replica')]
        (self.base / 'evidence').mkdir()
        version = {'EvidenceVersionKey': 'v', 'ExactVersion': f'file version 1.0; UniqueId file; SHA-256 {digest}',
                   'SourceURI': 'https://example.test/source.json'}
        write(self.base / 'evidence' / 'live.json', {'version': version})
        write(self.base / 'evidence' / 'recovery.json', {'version': version})
        write(self.ext / 'selected-reconstruction-index-v4.json', {'checkedFileRepresentations': reps,
              'workflowCohort': {'liveReadback': 'live.json', 'recoveryReadback': 'recovery.json',
                                 'nodes': [{'kind': 'versions', 'key': 'v', 'livePointer': '/version', 'recoveryPointer': '/version'}]}})
        action = {k[0].upper() + k[1:]: v for k, v in action_source.items()}
        action.update(ActionReferenceKey='a', FindingKey='f', SourceLocator='JSON Pointer /action',
                      CompletionEvidenceVersionKey='v', SourceDocumentURI='https://example.test/source.json',
                      SourceDocumentExactVersion=f'file version 1.0; UniqueId file; SHA-256 {digest}')
        finding = {'FindingKey': 'f', 'ObservationKey': 'o', 'ReviewContextKey': 'c', 'AssessmentKey': 'a1', 'RequirementKey': 'r', 'ScopeKey': 's'}
        def measurement(key, phase, period, count):
            return {'MeasurementKey': key, 'FindingKey': 'f', 'ActionReferenceKey': 'a', 'IndicatorVersionKey': 'i',
                    'EvidenceVersionKey': 'v', 'Phase': phase, 'PeriodStart': source[period]['start'], 'PeriodEnd': source[period]['end'],
                    'Numerator': count, 'Denominator': 1, 'SourceLocator': f'JSON Pointer /{period}/records'}
        case = {'fixtureOnly': True, 'nativeWrites': False, 'humanReviewClaimed': False,
                'observations': [{'ObservationKey': 'o', 'EvidenceVersionKey': 'v'}], 'findings': [finding], 'actionReferences': [action],
                'measurements': [measurement('b', 'baseline', 'baseline', 0), measurement('fup', 'follow-up', 'followUp', 1)],
                'effectivenessJudgements': [{'JudgementKey': 'j', 'FindingKey': 'f', 'ActionReferenceKey': 'a',
                   'BaselineMeasurementKey': 'b', 'FollowUpMeasurementKey': 'fup', 'Outcome': 'unknown', 'JudgementState': 'not-performed',
                   'ActorIdentityRef': None, 'JudgedAt': None}]}
        row = {'ContractCaseJSON': json.dumps(case), 'ObservationKey': 'o', 'ObsEvidenceVersionKey': 'v', 'FindingKey': 'f',
               'ReviewContextKey': 'c', 'AssessmentKey': 'a1', 'RequirementKey': 'r', 'ScopeKey': 's', 'ActionReferenceKey': 'a',
               'JudgementKey': 'j', 'IndicatorVersionKey': 'i', 'MeasurementKeysJSON': json.dumps(['b', 'fup']), 'EffectivenessOutcome': 'unknown'}
        support = [{'side': side, 'group': 'improvement', 'row': copy.deepcopy(row)} for side in ('live', 'recovery')]
        path = ext10 / 'workflow-lookup-evidence-v2-20261029.json'
        write(path, {'support': support})
        self.assertEqual(verify_improvement_fixture(self.root)['bySide']['live']['measurements'], 2)
        case['measurements'][0]['Numerator'] = 1
        for item in support:
            item['row']['ContractCaseJSON'] = json.dumps(case)
        write(path, {'support': support})
        with self.assertRaisesRegex(ValueError, 'measurement source mismatch'):
            verify_improvement_fixture(self.root)
        case['measurements'][0]['Numerator'] = 0
        case['effectivenessJudgements'][0]['Outcome'] = 'effective'
        for item in support:
            item['row']['ContractCaseJSON'] = json.dumps(case)
        write(path, {'support': support})
        with self.assertRaisesRegex(ValueError, 'outcome or measurement'):
            verify_improvement_fixture(self.root)

    def test_technical_improvement_rejects_inferred_outcome_and_bad_locator(self):
        ext10 = self.root / 'reconstruction-package-extension-v10'
        ext14 = self.root / 'reconstruction-package-extension-v14'
        ext10.mkdir()
        ext14.mkdir()
        (self.base / 'bytes').mkdir()
        (self.base / 'evidence').mkdir()
        raw = b'first\nsecond\n'
        digest = sha(raw)
        (self.base / 'bytes' / (digest + '.bin')).write_bytes(raw)
        version = {'OData__x0053_HA256': digest}
        for side in ('live', 'recovery'):
            write(self.base / 'evidence' / (side + '.json'), {'version': version})
        write(self.ext / 'selected-reconstruction-index-v4.json', {'workflowCohort': {'liveReadback': 'live.json',
              'recoveryReadback': 'recovery.json', 'nodes': [{'kind': 'versions', 'key': 'v',
              'livePointer': '/version', 'recoveryPointer': '/version'}]}})
        req = {'RequirementKey': 'r', 'SourceLocator': 'PDF page 4'}
        write(ext14 / 'corpus-capture-link-postflight-20261029.json', {'snapshots': {side: {'inventory': {'rows': [req]}}
              for side in ('source', 'recovery')}})
        finding = {'FindingKey': 'f', 'ObservationKey': 'o', 'AssessmentKey': 'a', 'RequirementKey': 'r', 'ScopeKey': 's',
                   'EvidenceLocators': ['Synthetic fixture lines 1–2', 'Requirement register source capture page 4']}
        case = {'syntheticFixture': True, 'readinessScoreComputed': False, 'assessmentOutcomeInferred': False,
                'actionReference': None, 'measurements': [], 'reviewContextKey': 'c', 'assessmentKey': 'a',
                'requirementKey': 'r', 'scopeKey': 's', 'observation': {'ObservationKey': 'o', 'EvidenceVersionKey': 'v',
                'AccessClass': 'synthetic-non-personal'}, 'finding': finding, 'effectivenessJudgement': {'JudgementKey': 'j',
                'Outcome': 'unknown', 'ActorIdentityRef': None, 'JudgedAt': None}}
        row = {'ContractCaseJSON': json.dumps(case), 'MeasurementKeysJSON': '[]', 'EffectivenessOutcome': 'unknown',
               'ReviewContextKey': 'c', 'AssessmentKey': 'a', 'RequirementKey': 'r', 'ScopeKey': 's', 'ObservationKey': 'o',
               'ObsEvidenceVersionKey': 'v', 'FindingKey': 'f', 'JudgementKey': 'j'}
        support = [{'side': side, 'group': 'improvement', 'row': copy.deepcopy(row)} for side in ('live', 'recovery')]
        file = ext10 / 'workflow-lookup-evidence-v2-20261029.json'
        write(file, {'support': support})
        self.assertEqual(verify_improvement_technical_case(self.root)['bySide']['live']['outcome'], 'unknown')
        case['assessmentOutcomeInferred'] = True
        for item in support:
            item['row']['ContractCaseJSON'] = json.dumps(case)
        write(file, {'support': support})
        with self.assertRaisesRegex(ValueError, 'infers outcome'):
            verify_improvement_technical_case(self.root)
        case['assessmentOutcomeInferred'] = False
        case['finding']['EvidenceLocators'][0] = 'Synthetic fixture lines 1–3'
        for item in support:
            item['row']['ContractCaseJSON'] = json.dumps(case)
        write(file, {'support': support})
        with self.assertRaisesRegex(ValueError, 'locator mismatch'):
            verify_improvement_technical_case(self.root)

    def test_lookup_capture_requires_matching_schema_and_target(self):
        ext = self.root / 'reconstruction-package-extension-v10'
        ext.mkdir()
        name = 'workflow-lookup-evidence-v2-20261029.json'
        check = {'side': 'live', 'group': 'requests', 'key': 'req', 'field': 'ReviewContextLink',
                 'targetKind': 'contexts', 'targetKey': 'ctx', 'itemId': 1}
        evidence = {'nativeWrites': 0, 'nulls': [], 'checks': [check],
                    'summary': [{'side': 'live', 'group': 'requests', 'selected': 1, 'listCount': 1, 'pages': 1}],
                    'support': [{'side': 'live', 'group': 'requests', 'key': 'req',
                                 'row': {'RequestKey': 'req', 'ReviewContextKey': 'ctx', 'ReviewContextLinkId': 1,
                                         'AssessmentKey': None, 'AssessmentLinkId': None,
                                         'ExpectationVersionKey': None, 'ExpectationVersionLinkId': None,
                                         'RequirementKey': None, 'RequirementLinkId': None},
                                 'fields': [{'InternalName': 'ReviewContextLink', 'TypeAsString': 'Lookup',
                                             'LookupField': 'ReviewContextKey', 'LookupList': '{list}'},
                                            {'InternalName': 'AssessmentLink', 'TypeAsString': 'Lookup', 'LookupField': 'AssessmentKey', 'LookupList': '{other}'},
                                            {'InternalName': 'ExpectationVersionLink', 'TypeAsString': 'Lookup', 'LookupField': 'ExpectationVersionKey', 'LookupList': '{other}'},
                                            {'InternalName': 'RequirementLink', 'TypeAsString': 'Lookup', 'LookupField': 'RequirementKey', 'LookupList': '{other}'}]}],
                    'targetSnapshots': [{'side': 'live', 'kind': 'contexts', 'listId': 'list', 'itemId': 1,
                                         'targetKeyField': 'ReviewContextKey', 'row': {'Id': 1, 'ReviewContextKey': 'ctx'}}]}
        evidence['support'][0]['row']['Id'] = 7
        for field in ('support', 'checks', 'summary', 'targetSnapshots'):
            recovery = copy.deepcopy(evidence[field][0])
            recovery['side'] = 'recovery'
            evidence[field].append(recovery)
        index_name = 'selected-reconstruction-index-v4.json'
        write(self.ext / index_name, {'workflowCohort': {'nodes': [
            {'kind': 'requests', 'keyField': 'RequestKey', 'key': 'req',
             'liveItemId': 7, 'recoveryItemId': 7}]}})
        write(self.ext / 'extension-manifest.json', {'files': [{'path': index_name}]})
        (ext / name).write_text(json.dumps(evidence))
        write(ext / 'extension-manifest.json', {'files': [{'path': name}]})
        self.assertEqual(verify_workflow_lookups(self.root)['resolvedLookups'], 2)
        for groups in (('support', 'checks', 'summary', 'targetSnapshots'), ('support',)):
            omitted = copy.deepcopy(evidence)
            for group in groups:
                omitted[group] = []
            (ext / name).write_text(json.dumps(omitted))
            with self.assertRaisesRegex(ValueError, 'cohort coverage mismatch'):
                verify_workflow_lookups(self.root)
        changed = copy.deepcopy(evidence)
        changed['support'][0]['row']['Id'] = 8
        (ext / name).write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'item identity mismatch'):
            verify_workflow_lookups(self.root)

        evidence['targetSnapshots'][0]['row']['ReviewContextKey'] = 'wrong'
        (ext / name).write_text(json.dumps(evidence))
        with self.assertRaises(ValueError):
            verify_workflow_lookups(self.root)
        evidence['targetSnapshots'][0]['row']['ReviewContextKey'] = 'ctx'
        removed_field = evidence['support'][0]['fields'].pop()
        (ext / name).write_text(json.dumps(evidence))
        with self.assertRaises(ValueError):
            verify_workflow_lookups(self.root)
        evidence['support'][0]['fields'].append(removed_field)
        evidence['support'][0]['row']['ReviewContextLinkId'] = None
        (ext / name).write_text(json.dumps(evidence))
        with self.assertRaises(ValueError):
            verify_workflow_lookups(self.root)

    def test_requirement_corpus_matches_keys_sources_and_human_text(self):
        evidence = self.base / 'evidence'
        evidence.mkdir()
        ext11 = self.root / 'reconstruction-package-extension-v11'
        ext11.mkdir()
        node = {k: 'x' for k in ('FrameworkKey', 'RequirementCode', 'RequirementKind', 'ParentRequirementKey',
                                  'PublisherCode', 'RequirementNodeKind', 'PublicationKey', 'EditionKey',
                                  'SourceSHA256', 'SourceURL', 'SourceLocator')}
        node.update(RequirementKey='r', CaptureKey='capture', ParentRequirementKey=None)
        row = dict(node, Title='title', RequirementText='human text',
                   SourceCaptureLink={'Url': 'https://example.test/source.pdf#page=1'},
                   RecoveryCopyURI={'Url': 'https://example.test/copy.pdf'},
                   SourceCaptureSHA256='sha', SourceFileVersion='1.0')
        snapshot = {'expectedKeys': 1, 'snapshots': {side: {'metadata': {'EnableVersioning': True},
                    'inventory': {'pages': 1, 'rows': [copy.deepcopy(row)]}} for side in ('source', 'recovery')}}
        snapshot['snapshots']['recovery']['inventory']['rows'][0]['SourceCaptureLink']['Url'] = 'https://example.test/copy.pdf#page=1'
        (evidence / 'corpus.json').write_text(json.dumps(snapshot))
        write(self.base / 'package-manifest.json', {'files': [{'path': 'evidence/corpus.json'}]})
        write(self.ext / 'selected-reconstruction-index-v4.json', {'requirementSnapshot': 'corpus.json',
              'expectedRequirementKeys': 1, 'captureIdentity': 'capture'})
        write(ext11 / 'expected-node-manifest-v1.json', {'edition': {'CaptureKey': 'capture',
              'nativeCaptureURL': 'https://example.test/source.pdf', 'SourceSHA256': 'sha',
              'fileUniqueId': 'file-id', 'nativeFileVersion': '1.0', 'sourceBytes': 4}, 'expectedNodes': [node]})
        write(ext11 / 'extension-manifest.json', {'files': [{'path': 'expected-node-manifest-v1.json'}]})
        self.assertEqual(verify_requirement_corpus(self.root)['populatedSummaries'], 1)
        self.assertEqual(verify_requirement_corpus(self.root)['recoveryLinksToCopy'], 1)
        ext15 = self.root / 'reconstruction-package-extension-v15'
        ext15.mkdir()
        file_name = 'capture-source-copy-owner-readback-20261029.json'
        readback = {'nativeWrites': 0, 'results': [
            {'side': 'source', 'id': 'file-id', 'url': 'https://example.test/source.pdf', 'sha256': 'sha', 'bytes': 4,
             'terminalPageReached': True, 'pages': 1, 'versions': [], 'currentNativeVersion': '1.0'},
            {'side': 'recovery', 'id': 'copy-id', 'url': 'https://example.test/copy.pdf', 'sha256': 'sha', 'bytes': 4,
             'terminalPageReached': True, 'pages': 1, 'versions': [], 'currentNativeVersion': '1.0'}]}
        write(ext15 / file_name, readback)
        write(ext15 / 'extension-manifest.json', {'files': [{'path': file_name}]})
        self.assertEqual(verify_requirement_corpus(self.root)['captureFiles']['recoveryNativeVersion'], '1.0')
        readback['results'][1]['sha256'] = 'wrong'
        write(ext15 / file_name, readback)
        with self.assertRaisesRegex(ValueError, 'Capture file identity'):
            verify_requirement_corpus(self.root)
        readback['results'][1]['sha256'] = 'sha'
        write(ext15 / file_name, readback)
        snapshot['snapshots']['recovery']['inventory']['rows'][0]['SourceCaptureLink']['Url'] = 'https://example.test/source.pdf#page=1'
        (evidence / 'corpus.json').write_text(json.dumps(snapshot))
        self.assertEqual(verify_requirement_corpus(self.root)['recoveryLinksToOriginal'], 1)
        ext14 = self.root / 'reconstruction-package-extension-v14'
        ext14.mkdir()
        postflight_name = 'corpus-capture-link-postflight-20261029.json'
        write(ext14 / postflight_name, snapshot)
        write(ext14 / 'extension-manifest.json', {'files': [{'path': postflight_name}]})
        with self.assertRaisesRegex(ValueError, 'Postflight recovery capture links'):
            verify_requirement_corpus(self.root)
        snapshot['snapshots']['recovery']['inventory']['rows'][0]['SourceCaptureLink']['Url'] = 'https://example.test/copy.pdf#page=1'
        write(ext14 / postflight_name, snapshot)
        self.assertEqual(verify_requirement_corpus(self.root)['recoveryLinksToCopy'], 1)
        (ext14 / postflight_name).unlink()
        (ext14 / 'extension-manifest.json').unlink()
        ext14.rmdir()
        snapshot['snapshots']['recovery']['inventory']['rows'][0]['SourceCaptureLink']['Url'] = 'https://example.test/copy.pdf#page=2'
        (evidence / 'corpus.json').write_text(json.dumps(snapshot))
        with self.assertRaises(ValueError):
            verify_requirement_corpus(self.root)
        snapshot['snapshots']['recovery']['inventory']['rows'][0]['SourceCaptureLink']['Url'] = 'https://example.test/copy.pdf#page=1'
        snapshot['snapshots']['recovery']['inventory']['rows'][0]['RequirementText'] = 'changed'
        (evidence / 'corpus.json').write_text(json.dumps(snapshot))
        with self.assertRaises(ValueError):
            verify_requirement_corpus(self.root)
        snapshot['snapshots']['recovery']['inventory']['rows'][0]['RequirementText'] = 'human text'
        snapshot['snapshots']['recovery']['inventory']['rows'][0]['SourceLocator'] = 'wrong'
        (evidence / 'corpus.json').write_text(json.dumps(snapshot))
        with self.assertRaises(ValueError):
            verify_requirement_corpus(self.root)
        snapshot['snapshots']['recovery']['inventory']['rows'].clear()
        (evidence / 'corpus.json').write_text(json.dumps(snapshot))
        with self.assertRaises(ValueError):
            verify_requirement_corpus(self.root)
        node['ParentRequirementKey'] = 'r'
        write(ext11 / 'expected-node-manifest-v1.json', {'edition': {'CaptureKey': 'capture',
              'nativeCaptureURL': 'https://example.test/source.pdf', 'SourceSHA256': 'sha'}, 'expectedNodes': [node]})
        with self.assertRaisesRegex(ValueError, 'cyclic requirement parent'):
            verify_requirement_corpus(self.root)

    def test_selected_index_reconciles_keys_and_item_ids(self):
        evidence = self.base / 'evidence'
        evidence.mkdir()
        data = json.dumps({'live': [{'Id': 1, 'Key': 'key', 'file': {'UniqueId': 'file', 'UIVersionLabel': '1.0'},
                                     'sha256': sha(b'blob'), 'bytes': 4}], 'recovery': [{'Id': 2, 'Key': 'key'}]}).encode()
        (evidence / 'records.json').write_bytes(data)
        (self.base / 'bytes').mkdir()
        (self.base / 'bytes' / (sha(b'blob') + '.bin')).write_bytes(b'blob')
        base = {'files': [{'path': 'data', 'sha256': sha(b'base'), 'bytes': 4},
                          {'path': 'evidence/records.json', 'sha256': sha(data), 'bytes': len(data)},
                          {'path': 'bytes/' + sha(b'blob') + '.bin', 'sha256': sha(b'blob'), 'bytes': 4}]}
        base_sha = write(self.base / 'package-manifest.json', base)
        node = {'kind': 'sample', 'keyField': 'Key', 'key': 'key', 'livePointer': '/live/0',
                'recoveryPointer': '/recovery/0', 'liveItemId': 1, 'recoveryItemId': 2}
        index = {'artifacts': [{'path': 'records.json', 'sha256': sha(data), 'bytes': len(data)}],
                 'checkedFileRepresentations': [{'role': 'source', 'source': 'records.json', 'jsonPointer': '/live/0',
                                                  'fileUniqueId': 'file', 'nativeVersion': '1.0', 'sha256': sha(b'blob'), 'bytes': 4}],
                 'selectedRecords': [{'source': 'records.json', 'jsonPointer': '/recovery/0', 'nativeItemId': 2, 'keys': {'Key': 'key'}}],
                 'coreCase': {'readback': 'records.json', 'sha256': sha(data), 'nodes': [node],
                              'edges': [{'side': 'live', 'sourceKind': 'sample', 'sourceKey': 'key', 'field': 'Key', 'targetKind': 'sample', 'targetKey': 'key'}]},
                 'workflowCohort': {'liveReadback': 'records.json', 'recoveryReadback': 'records.json', 'nodes': [node]}}
        index_bytes = json.dumps(index).encode()
        (self.ext / 'selected-reconstruction-index-v4.json').write_bytes(index_bytes)
        head = write(self.ext / 'extension-manifest.json', {'basePackageManifestSha256': base_sha,
                     'files': [{'path': 'result', 'sha256': sha(b'extension'), 'bytes': 9},
                               {'path': 'selected-reconstruction-index-v4.json', 'sha256': sha(index_bytes), 'bytes': len(index_bytes)}]})
        audit(self.root, head)
        self.assertEqual(verify_selected_index(self.root)['workflowNodes'], 1)
        self.assertEqual(verify_selected_index(self.root)['coreEdges'], 1)
        self.assertEqual(verify_selected_index(self.root)['fileRepresentations'], 1)
        index['checkedFileRepresentations'][0]['nativeVersion'] = '2.0'
        (self.ext / 'selected-reconstruction-index-v4.json').write_text(json.dumps(index))
        with self.assertRaises(ValueError):
            verify_selected_index(self.root)
        index['checkedFileRepresentations'][0]['nativeVersion'] = '1.0'
        index['coreCase']['edges'][0]['targetKey'] = 'missing'
        (self.ext / 'selected-reconstruction-index-v4.json').write_text(json.dumps(index))
        with self.assertRaises(ValueError):
            verify_selected_index(self.root)
        index['coreCase']['edges'][0]['targetKey'] = 'key'
        index['selectedRecords'][0]['keys']['Key'] = 'different'
        (self.ext / 'selected-reconstruction-index-v4.json').write_text(json.dumps(index))
        with self.assertRaises(ValueError):
            verify_selected_index(self.root)


class CustodyNavigationTests(unittest.TestCase):
    def test_parent_and_reverse_links_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ext1 = root / 'reconstruction-package-extension-v1'
            ext14 = root / 'reconstruction-package-extension-v14'
            ext20 = root / 'reconstruction-package-extension-v20'
            for ext in (ext1, ext14, ext20):
                ext.mkdir()
            write(ext1 / 'selected-reconstruction-index-v4.json', {'captureIdentity': 'cap'})
            rows = [{'RequirementKey': 'req', 'Id': 4}]
            write(ext14 / 'corpus-capture-link-postflight-20261029.json', {'snapshots': {side: {'inventory': {'rows': rows}} for side in ('source', 'recovery')}})
            fields = ('ResponsibilityKey', 'ExpectationVersionKey', 'RequirementKey', 'ScopeKey', 'ResponsibilityType', 'AssignmentState', 'IdentityRef', 'IdentityKind', 'UnknownReason', 'EffectiveFrom', 'EffectiveTo', 'SourceItemKey', 'SourceVersion', 'SourceLocator', 'AuthorIdentityRef')
            actual = dict.fromkeys(fields)
            actual.update(Id=1, ResponsibilityKey='cust', ExpectationVersionKey='expect', RequirementKey='req', ScopeKey='scope', ExpectationVersionLinkId=3, RequirementLinkId=4)
            def parent(key, value, number, guid, link, extra):
                return {'parent': {'Id': number, key: value, '__metadata': {'uri': f"https://example.test/_api/Web/Lists(guid'{guid}')/Items({number})"}, **extra}, 'schema': {'InternalName': link, 'TypeAsString': 'Lookup', 'LookupField': key, 'LookupList': '{' + guid + '}'}}
            result = {'actual': actual, 'resolved': {'expectation': parent('ExpectationVersionKey', 'expect', 3, '11111111-1111-1111-1111-111111111111', 'ExpectationVersionLink', {'RequirementKey': 'req', 'ScopeKey': 'scope'}), 'requirement': parent('RequirementKey', 'req', 4, '22222222-2222-2222-2222-222222222222', 'RequirementLink', {'CaptureKey': 'cap'})}, 'reverse': {'pages': 1, 'rows': [{'Id': 1, 'ResponsibilityKey': 'cust'}]}, 'indexField': {'InternalName': 'ExpectationVersionKey', 'Indexed': True}}
            name = 'responsibility-navigation-evidence-20261029.json'
            data = {'nativeWrites': 0, 'output': {'source': result, 'destination': copy.deepcopy(result)}}
            write(ext20 / name, data)
            write(ext20 / 'extension-manifest.json', {'files': [{'path': name}]})
            self.assertEqual(verify_custody_navigation(root)['forwardParentLinks'], 4)
            data['output']['destination']['resolved']['requirement']['schema']['LookupList'] = '{33333333-3333-3333-3333-333333333333}'
            write(ext20 / name, data)
            with self.assertRaises(ValueError):
                verify_custody_navigation(root)
            data['output']['destination'] = copy.deepcopy(result)
            data['output']['destination']['reverse']['rows'] = []
            write(ext20 / name, data)
            with self.assertRaises(ValueError):
                verify_custody_navigation(root)


if __name__ == '__main__':
    unittest.main()
