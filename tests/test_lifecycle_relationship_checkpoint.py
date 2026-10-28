import copy
import unittest

from scripts.ppg_relationship_versions import empty, append, head, freeze, native_history_plan, PREFIX
from scripts.ppg_lifecycle_relationship_checkpoint import freeze_context, recover_context, scoped_manifest, PURPOSES


def fixture():
    policy = dict(DocumentUID=PREFIX+'policy', policyEdition='qualification-A', sha256='a'*64, sourceRef='fixture:native-source')
    request = dict(requestId=PREFIX+'add', operation='add-policy', body=policy,
        recordedAt='2026-01-01T00:00:00Z', effectiveFrom='2026-01-01T00:00:00Z',
        decisionRef='fixture:technical', actorRef='FICTIONAL actor', rationale='Fictional test', FictionalTest=True)
    journal, _ = append(empty(), request, head(empty()))
    other = {**policy, 'DocumentUID':PREFIX+'other', 'sha256':'c'*64}
    journal, _ = append(journal, {**request, 'requestId':PREFIX+'other', 'body':other}, head(journal))
    edge = dict(RelationshipKey=PREFIX+'reference', type='references', state='active', rationale='Fictional dependency', **{'from':other, 'to':policy})
    journal, _ = append(journal, {**request, 'requestId':PREFIX+'edge', 'operation':'set-relationship', 'body':edge}, head(journal))
    scope = dict(CaseUID='LC-FICTIONAL-OP-A', DocumentReference='fixture:draft', ReviewedVersionRef='fixture:draft-v3', DocumentSHA256='b'*64)
    source = dict(DocumentUID='FICTIONAL-original-policy', policyEdition=policy['policyEdition'],
        UniqueId='source-id', ETag='"source,2"', nativeVersion='1.0', sha256='a'*64, DocumentReference='fixture:source')
    original = dict(CaseUID=scope['CaseUID'], DocumentReference=source['DocumentReference'],
        ReviewedVersionRef='sharepoint:source-id:"source,2"', DocumentSHA256='a'*64)
    def row(uid, identity, **values):
        return dict(scope, EventUID=uid, Id=identity, GUID='fictional-'+str(identity), FictionalTest=True,
            **{'odata.etag':'"1"'}, **values)
    consultation = [row('request', 1, RecordState='Pending response'), row('response', 2, RecordState='Responded', ParentEventUID='request')]
    readiness = [row('ready', 1, Finding='Ready for decision', ConditionsState='None recorded')]
    decisions = [row(code, i+1, Stage='Decision', RecordState='Recorded', ConditionsState='None recorded',
        ReadinessEventUID='ready', DecisionOutcome='Approved (recorded)' if i==3 else 'Endorsed (recorded)',
        DecisionReference='fictional://route/1/hash/'+code, ParentEventUID=PURPOSES[i-1] if i else None)
        for i, code in enumerate(PURPOSES)]
    issued = dict(DocumentReference='fixture:issued', PublishedVersionRef='fixture:issued-v1',
        UniqueId='issued-id', ETag='"issued,1"', sha256='b'*64, bytes=12)
    publication = row('published', 5, Stage='Publication', RecordState='Recorded', ParentEventUID='authorisation',
        PublicationURL=issued['DocumentReference'], PublishedVersionRef=issued['PublishedVersionRef'])
    frames = {name:dict(before=dict(value=rows), after=dict(value=copy.deepcopy(rows))) for name, rows in
        [('consultation', consultation), ('readiness', readiness), ('assurance', decisions+[publication])]}
    context = dict(FictionalTest=True, scope=scope, sourceBinding=dict(journalPin=policy, source=source),
        sourceContext=dict(scope=original,sourcePins={k:source[k] for k in ('UniqueId','ETag','DocumentUID')}),
        preparedRevision=dict(scope=scope, originalSourceScope=original, file=dict(UniqueId='draft-id', ETag='"draft,6"')),
        frames=frames, selected=dict(request='request', response='response', readiness='ready',
        purposes=dict(zip(PURPOSES, PURPOSES)), publication='published'), issued=issued,
        binaryProof=dict(sourceSHA256='b'*64, issuedSHA256='b'*64, bytes=12, receiptReference='fixture:binary-proof',
            sourcePin=dict(UniqueId='draft-id', ETag='"draft,6"'), issuedPin=dict(UniqueId='issued-id', ETag='"issued,1"')))
    rows = [r['versions'][-1]['record'] for r in native_history_plan(journal)['records']]
    return freeze(journal), rows, context


class LifecycleRelationshipCheckpointTests(unittest.TestCase):
    def test_complete_freeze_recovery_and_unchanged_replay(self):
        snapshot, rows, context = fixture(); before=copy.deepcopy(context)
        frozen = freeze_context(snapshot, rows, context)
        self.assertEqual(frozen, freeze_context(snapshot, rows, context))
        self.assertEqual(recover_context(frozen, rows)['context'], context)
        self.assertEqual(context, before)
        self.assertFalse(frozen['payload']['nativeWriterEnabled'])
        self.assertFalse(frozen['payload']['humanAcceptance'])

    def test_missing_purpose_and_cross_revision_refused(self):
        for change in ('missing', 'scope', 'parent', 'route', 'outcome'):
            snapshot, rows, context = fixture()
            if change=='missing':del context['selected']['purposes']['officer']
            else:
                for side in ('before','after'):
                    row=context['frames']['assurance'][side]['value'][1]
                    row[dict(scope='ReviewedVersionRef',parent='ParentEventUID',route='DecisionReference',outcome='DecisionOutcome')[change]]='changed'
            with self.subTest(change=change), self.assertRaises(ValueError):freeze_context(snapshot, rows, context)

    def test_partial_or_changed_native_frame_refused(self):
        for change in ('continuation', 'token', 'field', 'duplicate'):
            snapshot, rows, context = fixture(); after=context['frames']['readiness']['after']
            if change=='continuation':after['@odata.nextLink']='fixture:more'
            elif change=='token':after['value'][0]['odata.etag']='*'
            elif change=='field':after['value'][0]['HumanNote']='new edit'
            else:after['value'].append(copy.deepcopy(after['value'][0]))
            with self.subTest(change=change), self.assertRaises(ValueError):freeze_context(snapshot, rows, context)

    def test_source_and_binary_splicing_refused(self):
        for change in ('source', 'issued', 'draft', 'hash'):
            snapshot, rows, context=fixture()
            if change=='source':context['sourceBinding']['source']['UniqueId']='another-source'
            elif change=='issued':context['binaryProof']['issuedPin']['ETag']='"new"'
            elif change=='draft':context['binaryProof']['sourcePin']['UniqueId']='other-draft'
            else:context['binaryProof']['issuedSHA256']='c'*64
            with self.subTest(change=change), self.assertRaises(ValueError):freeze_context(snapshot, rows, context)

    def test_boolean_native_identity_and_size_do_not_count_as_evidence(self):
        for change in ('id', 'guid', 'bytes'):
            snapshot, rows, context = fixture()
            if change == 'bytes':
                context['binaryProof']['bytes'] = context['issued']['bytes'] = True
            else:
                for side in ('before', 'after'):
                    context['frames']['readiness'][side]['value'][0]['Id' if change == 'id' else 'GUID'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                freeze_context(snapshot, rows, context)

    def test_correction_and_tamper_refused(self):
        snapshot, rows, context=fixture()
        for side in ('before','after'):
            row=copy.deepcopy(context['frames']['readiness'][side]['value'][0]);row.update(Id=2, GUID='correction', EventUID='correction', SupersedesEventUID='ready')
            context['frames']['readiness'][side]['value'].append(row)
        with self.assertRaises(ValueError):freeze_context(snapshot, rows, context)
        snapshot, rows, context=fixture(); frozen=freeze_context(snapshot, rows, context)
        frozen['payload']['context']['issued']['sha256']='c'*64
        with self.assertRaises(ValueError):recover_context(frozen, rows)

    def test_native_manifest_retains_scope_and_hashes_without_unrelated_records(self):
        snapshot, rows, context=fixture()
        for side in ('before','after'):
            other=copy.deepcopy(context['frames']['assurance'][side]['value'][0])
            other.update(Id=99,GUID='other-row',EventUID='unrelated-event',CaseUID='other-case')
            context['frames']['assurance'][side]['value'].append(other)
        frozen=freeze_context(snapshot, rows, context)
        manifest=scoped_manifest(frozen, rows)['payload']
        self.assertEqual(manifest['frameReferences']['assurance']['rows'],6)
        self.assertEqual(len(manifest['records']['assurance']),5)
        self.assertNotIn('unrelated-event',str(manifest['records']))
        self.assertFalse(manifest['completeCurrentHistoryAuthenticated'])


if __name__=='__main__':unittest.main()
