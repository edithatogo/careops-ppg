"""Freeze a fictional lifecycle's exact relationship and retained-record context.

Offline evidence reconciliation only. Native collection/authenticity and binary
proof remain responsibilities of the existing collectors; this grants no writer,
approval or publication authority. Missing stages cannot produce a checkpoint.
"""
import copy
import json

from scripts.ppg_relationship_versions import recover, head, pin, journal_from_native_records, append, freeze, native_history_plan, PREFIX
from scripts.ppg_source_standards import digest

SCOPE = ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')
PURPOSES = ('committee', 'officer', 'coordinator', 'authorisation')


def _token(row):
    token = row.get('odata.etag')
    if (not isinstance(token, str) or not token.strip() or token.strip() == '*'
            or not isinstance(row.get('GUID'), str) or not row['GUID'].strip()
            or type(row.get('Id')) is not int or row['Id'] < 1):
        raise ValueError('Exact retained native row identity and token required')


def _frame(frame):
    if (not isinstance(frame, dict) or not isinstance(frame.get('value'), list)
            or any(v for k, v in frame.items() if 'nextlink' in k.lower())):
        raise ValueError('Complete native collection required')
    rows = frame['value']
    for row in rows:
        _token(row)
    if len({r['Id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate native row identity')
    # OData representation identity is not the record identity. Keep ETags,
    # business fields, audit fields and every unknown human field intact.
    return sorted(({k: v for k, v in r.items() if k != 'odata.id'} for r in rows), key=lambda r: r['Id'])


def freeze_context(snapshot, native_relationships, context):
    """Return an immutable evidence envelope after all exact stages are retained.

    Context contains stable before/after consultation/readiness/assurance frames,
    explicit selected UIDs, prepared scope, source-to-journal binding, and issued
    binary proof. Never select a latest row or infer missing purpose decisions.
    """
    journal = recover(snapshot)
    if journal_from_native_records(native_relationships, head(journal), snapshot) != journal:
        raise ValueError('Native relationship projection disagrees with checkpoint')
    if context.get('FictionalTest') is not True or not context.get('scope', {}).get('CaseUID', '').startswith('LC-FICTIONAL-OP-'):
        raise ValueError('Reserved fictional lifecycle only')
    scope = context['scope']
    if set(scope) != set(SCOPE) or any(not isinstance(scope[k], str) or not scope[k].strip() for k in SCOPE):
        raise ValueError('Exact prepared revision scope required')
    binding = context['sourceBinding']; key = pin(binding['journalPin'])
    prepared = context['preparedRevision']
    original = prepared['originalSourceScope']
    native_source = context['sourceContext']
    if native_source['scope'] != original or any(native_source['sourcePins'].get(k) != binding['source'][k]
            for k in ('UniqueId','ETag','DocumentUID')):
        raise ValueError('Native source identity/context mismatch')
    if (prepared['scope'] != scope or original['CaseUID'] != scope['CaseUID']
            or original['DocumentSHA256'] != binding['source']['sha256']
            or original['DocumentReference'] != binding['source']['DocumentReference']
            or original['ReviewedVersionRef'] != 'sharepoint:' + binding['source']['UniqueId'] + ':' + binding['source']['ETag']):
        raise ValueError('Prepared receipt/source identity mismatch')
    policies = [e['body'] for e in journal['events'] if e['operation'] == 'add-policy']
    if binding['journalPin'] not in policies or binding['source']['sha256'] != key[2]:
        raise ValueError('Exact source edition must exist in retained journal')
    for k in ('DocumentUID', 'policyEdition', 'UniqueId', 'ETag', 'nativeVersion', 'sha256'):
        if not isinstance(binding['source'].get(k), str) or not binding['source'][k].strip():
            raise ValueError('Distinct native source and policy edition pins required')
    if binding['source']['policyEdition'] != binding['journalPin']['policyEdition'] or binding['source']['ETag'].strip() == '*':
        raise ValueError('Source edition/token mismatch')
    selected = context['selected']; records = {}
    for name in ('consultation', 'readiness', 'assurance'):
        bracket = context['frames'][name]
        before, after = _frame(bracket['before']), _frame(bracket['after'])
        if before != after:
            raise ValueError('Native lifecycle frame changed: ' + name)
        ids = [r.get('EventUID') for r in after]
        if any(not isinstance(uid, str) or not uid for uid in ids) or len(set(ids)) != len(ids):
            raise ValueError('Missing/duplicate event identity')
        records[name] = {r['EventUID']: r for r in after}

    def choose(collection, uid):
        row = records[collection].get(uid)
        if row is None or row.get('FictionalTest') is not True or any(row.get(k) != scope[k] for k in SCOPE):
            raise ValueError('Missing or cross-revision lifecycle event')
        if row.get('SupersedesEventUID') or any(r.get('SupersedesEventUID') == uid for r in records[collection].values()):
            raise ValueError('Corrected event requires explicit resolution')
        return row

    request = choose('consultation', selected['request'])
    response = choose('consultation', selected['response'])
    if request.get('RecordState') != 'Pending response' or response.get('RecordState') != 'Responded' or response.get('ParentEventUID') != request['EventUID']:
        raise ValueError('Exact consultation request/response chain required')
    ready = choose('readiness', selected['readiness'])
    scoped_ready = [r for r in records['readiness'].values() if all(r.get(k) == scope[k] for k in SCOPE)]
    if len(scoped_ready) != 1:
        raise ValueError('Ambiguous readiness findings require explicit resolution')
    if ready.get('Finding') != 'Ready for decision' or ready.get('ConditionsState') not in ('None recorded', 'Resolved'):
        raise ValueError('Explicit own readiness finding required')
    if set(selected['purposes']) != set(PURPOSES):
        raise ValueError('Four separate purpose decisions required')
    decisions = [choose('assurance', selected['purposes'][k]) for k in PURPOSES]
    scoped_decisions = [r['EventUID'] for r in records['assurance'].values()
        if r.get('Stage') == 'Decision' and all(r.get(k) == scope[k] for k in SCOPE)]
    if set(scoped_decisions) != {r['EventUID'] for r in decisions}:
        raise ValueError('Unresolved additional decision evidence')
    if len({r['EventUID'] for r in decisions}) != 4:
        raise ValueError('Purpose decisions cannot share one event')
    route_prefixes = {str(r.get('DecisionReference', '')).rsplit('/', 1)[0] for r in decisions}
    if len(route_prefixes) != 1 or not next(iter(route_prefixes)).startswith('fictional://'):
        raise ValueError('One exact fictional purpose route required')
    for ordinal, (code, row) in enumerate(zip(PURPOSES, decisions)):
        outcome = 'Approved (recorded)' if code == 'authorisation' else 'Endorsed (recorded)'
        if (row.get('Stage') != 'Decision' or row.get('RecordState') != 'Recorded'
                or row.get('ReadinessEventUID') != ready['EventUID'] or row.get('DecisionOutcome') != outcome
                or row.get('ParentEventUID') != (decisions[ordinal-1]['EventUID'] if ordinal else None)
                or row.get('ConditionsState') not in ('None recorded', 'Resolved')
                or not str(row.get('DecisionReference', '')).endswith('/' + code)):
            raise ValueError('Purpose-bound exact-revision decision required')
    published = choose('assurance', selected['publication'])
    issued = context['issued']; binary = context['binaryProof']
    if (published.get('Stage') != 'Publication' or published.get('RecordState') != 'Recorded'
            or published.get('ParentEventUID') != decisions[-1]['EventUID']
            or published.get('PublicationURL') != issued['DocumentReference']
            or published.get('PublishedVersionRef') != issued['PublishedVersionRef']
            or issued['sha256'] != scope['DocumentSHA256']
            or binary['sourceSHA256'] != issued['sha256'] or binary['issuedSHA256'] != issued['sha256']
            or binary['sourcePin'] != {k: prepared['file'][k] for k in ('UniqueId', 'ETag')}
            or binary['issuedPin'] != {k: issued[k] for k in ('UniqueId', 'ETag')}
            or type(binary.get('bytes')) is not int or type(issued.get('bytes')) is not int or binary['bytes'] < 1
            or binary['bytes'] != issued['bytes'] or not binary.get('receiptReference')):
        raise ValueError('Actual own purpose-bound issued binary evidence required')
    payload = dict(kind='fictional-lifecycle-relationship-checkpoint-v1',
        relationshipSnapshot=copy.deepcopy(snapshot), context=copy.deepcopy(context),
        retainedRelationshipHead=head(journal), nativeWriterEnabled=False,
        realPolicyAuthority=False, humanAcceptance=False)
    return dict(payload=payload, sha256=digest(payload))


def recover_context(checkpoint, native_relationships):
    payload = checkpoint['payload']
    if digest(payload) != checkpoint['sha256']:
        raise ValueError('Changed lifecycle/relationship checkpoint')
    rebuilt = freeze_context(payload['relationshipSnapshot'], native_relationships, payload['context'])
    if rebuilt != checkpoint:
        raise ValueError('Incomplete lifecycle/relationship reconstruction')
    return copy.deepcopy(payload)


def scoped_manifest(checkpoint, native_relationships):
    """Select only this fictional case for native package evidence storage.

    Complete collection snapshots stay in the private checkpoint. Their hashes
    are retained here, without copying unrelated cases into a package artifact.
    This projection does not authenticate a complete current tenant history.
    """
    payload = recover_context(checkpoint, native_relationships)
    context = payload['context']; selected = context['selected']
    wanted = dict(consultation={selected['request'],selected['response']}, readiness={selected['readiness']},
        assurance=set(selected['purposes'].values()) | {selected['publication']})
    records = {}; references = {}
    for name, ids in wanted.items():
        rows = _frame(context['frames'][name]['before'])
        records[name] = [copy.deepcopy(r) for r in rows if r['EventUID'] in ids]
        references[name] = dict(rows=len(rows), sha256=digest(rows))
    result = dict(kind='fictional-scoped-lifecycle-relationship-manifest-v1',
        privateCheckpointSHA256=checkpoint['sha256'], relationshipSnapshot=payload['relationshipSnapshot'],
        scope=context['scope'], sourceBinding=context['sourceBinding'], preparedRevision=context['preparedRevision'],
        selected=selected, records=records, issued=context['issued'], binaryProof=context['binaryProof'],
        frameReferences=references, completeCurrentHistoryAuthenticated=False,
        realPolicyAuthority=False, humanAcceptance=False)
    return dict(payload=copy.deepcopy(result), sha256=digest(result))


def prepare_reference_transition(snapshot, native_relationships, checkpoints, stored_manifests, request):
    """Prepare one proposed source-edition reference after both fictional cycles.

    No native I/O or acceptance. Caller-owned native collectors must authenticate
    every stored-manifest pin/content before a separately guarded writer runs.
    Source-edition hashes remain distinct from prepared and issued hashes.
    """
    if set(checkpoints) != {'A', 'B'} or set(stored_manifests) != {'A', 'B'}:
        raise ValueError('Both complete fictional lifecycle checkpoints required')
    contexts = {}; references = {}
    for label in ('A', 'B'):
        checked = recover_context(checkpoints[label], native_relationships)
        if checked['relationshipSnapshot'] != snapshot:
            raise ValueError('Same complete relationship snapshot required')
        contexts[label] = checked['context']
        manifest = scoped_manifest(checkpoints[label], native_relationships)
        stored = stored_manifests[label]
        if (set(stored) != {'file', 'contentSHA256'} or stored['contentSHA256'] != digest(manifest)
                or set(stored['file']) != {'UniqueId', 'ETag', 'DocumentReference'}
                or any(not isinstance(v, str) or not v.strip() for v in stored['file'].values())
                or stored['file']['ETag'].strip() == '*'):
            raise ValueError('Exact separately verified native scoped-manifest binding required')
        references[label] = copy.deepcopy(stored)
    if (contexts['A']['scope']['CaseUID'] == contexts['B']['scope']['CaseUID']
            or pin(contexts['A']['sourceBinding']['journalPin']) == pin(contexts['B']['sourceBinding']['journalPin'])
            or contexts['A']['issued']['UniqueId'] == contexts['B']['issued']['UniqueId']
            or contexts['A']['preparedRevision']['file']['UniqueId'] == contexts['B']['preparedRevision']['file']['UniqueId']
            or references['A']['file']['UniqueId'] == references['B']['file']['UniqueId']):
        raise ValueError('Distinct cases, source editions and issued objects required')
    for name in ('consultation', 'readiness', 'assurance'):
        if _frame(contexts['A']['frames'][name]['before']) != _frame(contexts['B']['frames'][name]['before']):
            raise ValueError('Same complete native lifecycle frame required for both cases')
    if (set(request) != {'requestId', 'recordedAt', 'effectiveFrom', 'actorRef'}
            or not isinstance(request['actorRef'], str) or not request['actorRef'].startswith('FICTIONAL ')):
        raise ValueError('Explicit fictional reference request and times required')
    journal = recover(snapshot)
    key = PREFIX + 'LC07-printed-B-reference-A'
    body = {'RelationshipKey': key, 'from': contexts['B']['sourceBinding']['journalPin'],
        'to': contexts['A']['sourceBinding']['journalPin'], 'type': 'references', 'state': 'active',
        'rationale': 'FICTIONAL source-edition reference only; separately verified A/B issued evidence; no supersession or policy authority.'}
    event = dict(request, operation='set-relationship', body=body,
        decisionRef='fixture:lifecycle-pair:' + digest(references), rationale=body['rationale'], FictionalTest=True)
    result, created = append(journal, event, head(journal))
    return dict(snapshot=freeze(result), nativePlan=native_history_plan(result),
        expectedPreviousHead=head(journal), eventAppended=created, nativeManifestBindings=references,
        nativeWriterEnabled=False, realPolicyAuthority=False, humanAcceptance=False)


def main():
    import argparse
    import os
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--relationship-snapshot', required=True)
    parser.add_argument('--native-relationships', required=True)
    parser.add_argument('--context', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    read = lambda name: json.loads(Path(name).read_bytes())
    result = freeze_context(read(args.relationship_snapshot), read(args.native_relationships), read(args.context))
    raw = json.dumps(result, sort_keys=True, separators=(',', ':')).encode()
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(raw)
    print('Frozen fictional lifecycle/relationship evidence; no native writes or authority granted.')


if __name__ == '__main__':
    main()
