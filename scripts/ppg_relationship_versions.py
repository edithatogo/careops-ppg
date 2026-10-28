"""Fictional, append-only policy relationship revisions and as-of reconstruction.

Uses existing relationship fields/history; never accepts policy authority. This
module performs no native I/O. The bounded native adapter qualifies persistence
separately. Endpoint changes require a new relationship identity.
"""
import copy
import datetime as dt
import hashlib
import json
import re

from scripts.ppg_source_standards import digest

PREFIX = 'FICTIONAL-RV25-'
TYPES = {'references', 'depends_on', 'supplements', 'supersedes', 'proposed_consolidation_with'}
ZERO = '0' * 64


def stamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z',value):
        raise ValueError('Explicit UTC timestamp required; unknown dates cannot enter an as-of graph')
    try:
        result = dt.datetime.fromisoformat(value[:-1]+'+00:00')
    except ValueError:
        raise ValueError('Invalid calendar timestamp') from None
    return result


def text(row, *keys):
    for key in keys:
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError('Missing text '+key)


def pin(row):
    if set(row)!={'DocumentUID','policyEdition','sha256','sourceRef'}:raise ValueError('Exact edition pin shape required')
    text(row, 'DocumentUID', 'policyEdition', 'sha256', 'sourceRef')
    if not row['DocumentUID'].startswith(PREFIX):
        raise ValueError('Only reserved fictional identities allowed')
    if len(row['sha256']) != 64 or any(c not in '0123456789abcdef' for c in row['sha256']):
        raise ValueError('Exact source hash required')
    if not row['sourceRef'].startswith('fixture:'):
        raise ValueError('Fictional source references required')
    return (row['DocumentUID'], row['policyEdition'], row['sha256'])


def empty():
    return dict(schemaVersion=1, kind='fictional_relationship_revision_journal', events=[])


def head(journal):
    return journal['events'][-1]['eventHash'] if journal['events'] else ZERO


def _validate(journal):
    if journal.get('schemaVersion') != 1 or journal.get('kind') != 'fictional_relationship_revision_journal':
        raise ValueError('Explicit fictional journal required')
    if not isinstance(journal.get('events'),list) or len(journal['events'])>100:raise ValueError('Bounded complete event list required')
    previous = ZERO; seen = set(); recorded = None
    for seq, event in enumerate(journal['events'], 1):
        if set(event)!={'requestId','operation','body','recordedAt','effectiveFrom','decisionRef','actorRef','rationale','FictionalTest','sequence','previousHash','eventHash'}:raise ValueError('Unknown/missing event fields')
        payload = {k:v for k,v in event.items() if k != 'eventHash'}
        if event['sequence'] != seq or event['previousHash'] != previous or digest(payload) != event['eventHash']:
            raise ValueError('Incomplete, reordered or changed journal')
        if event['requestId'] in seen:
            raise ValueError('Duplicate request identity')
        seen.add(event['requestId']); now=stamp(event['recordedAt'])
        if recorded is not None and now < recorded:
            raise ValueError('Recorded time cannot move backwards')
        recorded=now; previous=event['eventHash']
        stamp(event['effectiveFrom'])
        text(event, 'requestId', 'decisionRef', 'actorRef', 'rationale')
        if (not event['requestId'].startswith(PREFIX) or not event['decisionRef'].startswith('fixture:')
                or not event['actorRef'].startswith('FICTIONAL ') or event.get('FictionalTest') is not True):
            raise ValueError('Real decisions/identities forbidden in this qualification route')
    _fold(journal['events'])
    return True


def _fold(events):
    policies = {}; relationships = {}; revisions = {}; effective_times = {}; policy_times = {}
    for e in events:
        body=e['body']; kind=e['operation']
        if kind == 'add-policy':
            key=pin(body)
            if any(k[:2]==key[:2] for k in policies): raise ValueError('Duplicate/conflicting policy edition')
            policies[key]=copy.deepcopy(body);policy_times[key]=stamp(e['effectiveFrom'])
        elif kind == 'deprecate-policy':
            if set(body)!={'subject'}:raise ValueError('Exact deprecation subject required')
            if pin(body['subject']) not in policies: raise ValueError('Unknown deprecated edition')
            if stamp(e['effectiveFrom']) < policy_times[pin(body['subject'])]:raise ValueError('Deprecation precedes edition')
        elif kind in {'set-relationship','consolidate'}:
            edges=[body] if kind=='set-relationship' else body['relationships']
            if kind=='consolidate':
                if set(body)!={'successor','predecessors','relationships'}:raise ValueError('Exact consolidation envelope required')
                successor=pin(body['successor']); predecessors=[pin(r) for r in body['predecessors']]
                if (len(predecessors)<2 or len(set(predecessors))!=len(predecessors)
                        or successor in predecessors or successor not in policies
                        or any(k not in policies for k in predecessors)):
                    raise ValueError('Distinct known consolidation editions required')
                pairs={(pin(r['from']),pin(r['to'])) for r in edges}
                if len(edges)!=len(predecessors) or pairs!={(successor,k) for k in predecessors} or any(r['type']!='supersedes' for r in edges):
                    raise ValueError('Exact multi-predecessor consolidation edges required')
            for row in edges:
                if set(row)-{'RelationshipKey','from','to','type','state','rationale','previousRevision','predecessorRelationshipKey'}:raise ValueError('Unknown relationship revision fields')
                text(row,'RelationshipKey','rationale')
                key=row['RelationshipKey']
                if not key.startswith(PREFIX) or row['type'] not in TYPES or row['state'] not in {'active','ended'}:
                    raise ValueError('Reserved identity, known type and explicit state required')
                left,right=pin(row['from']),pin(row['to'])
                if left not in policies or right not in policies or left==right:
                    raise ValueError('Unknown or self endpoint')
                if any(stamp(e['effectiveFrom']) < policy_times[k] for k in (left,right)):
                    raise ValueError('Relationship predates an endpoint')
                predecessor=row.get('predecessorRelationshipKey')
                if predecessor is not None and (predecessor not in relationships or predecessor==key):
                    raise ValueError('Unknown predecessor relationship identity')
                old=relationships.get(key)
                if old:
                    if any(old[k]!=row[k] for k in ['from','to','type']):
                        raise ValueError('Endpoint/type change requires a new relationship key')
                    if stamp(e['effectiveFrom']) < effective_times[key]:
                        raise ValueError('Revision effective time precedes retained predecessor')
                    if row.get('previousRevision')!=revisions[key]:
                        raise ValueError('Exact predecessor revision required')
                elif row.get('previousRevision') is not None:
                    raise ValueError('Unexpected predecessor revision')
                relationships[key]=copy.deepcopy(row);revisions[key]=e['eventHash'];effective_times[key]=stamp(e['effectiveFrom'])
            # Supersession is directional/acyclic. Mutual references remain valid.
            adjacency={}
            for row in relationships.values():
                if row['type']=='supersedes' and row['state']=='active':
                    adjacency.setdefault(pin(row['from']),[]).append(pin(row['to']))
            visiting=set();done=set()
            for start in adjacency:
                stack=[(start,False)]
                while stack:
                    node,exit=stack.pop()
                    if exit:visiting.discard(node);done.add(node);continue
                    if node in visiting:raise ValueError('Supersession cycle')
                    if node in done:continue
                    visiting.add(node);stack.append((node,True))
                    stack.extend((target,False) for target in adjacency.get(node,[]))
        else:raise ValueError('Unknown relationship change operation')
    return policies,relationships,revisions


def append(journal, request, expected_head):
    _validate(journal)
    # An exact request replay is allowed after later events; never re-applies it.
    for event in journal['events']:
        if event['requestId']==request.get('requestId'):
            original={k:v for k,v in event.items() if k not in {'sequence','previousHash','eventHash'}}
            if original!=request:raise ValueError('Changed request replay refused')
            return copy.deepcopy(journal),False
    if head(journal)!=expected_head:raise ValueError('Stale journal preimage')
    event=copy.deepcopy(request);event.update(sequence=len(journal['events'])+1,previousHash=head(journal));event['eventHash']=digest(event)
    result=copy.deepcopy(journal);result['events'].append(event);_validate(result)
    return result,True


def reconstruct(journal, effective_at, known_at):
    _validate(journal); effective=stamp(effective_at);known=stamp(known_at)
    eligible=[e for e in journal['events'] if stamp(e['recordedAt'])<=known and stamp(e['effectiveFrom'])<=effective]
    # Validate causal endpoint existence in recorded order, then choose effective
    # revisions by effective time, recorded time and sequence for as-of projection.
    policies,_,_=_fold(eligible)
    relationships={}; policy_states={}; revisions={}
    for e in sorted(eligible,key=lambda e:(stamp(e['effectiveFrom']),stamp(e['recordedAt']),e['sequence'])):
        if e['operation']=='deprecate-policy':policy_states[pin(e['body']['subject'])]=e
        edges=[e['body']] if e['operation']=='set-relationship' else e['body']['relationships'] if e['operation']=='consolidate' else []
        for row in edges:relationships[row['RelationshipKey']]=copy.deepcopy(row);revisions[row['RelationshipKey']]=e['eventHash']
    leads=[]
    for key,event in policy_states.items():
        for r in relationships.values():
            if r['state']=='active' and r['type']!='supersedes' and key in (pin(r['from']),pin(r['to'])):
                leads.append(dict(leadKey=digest([event['eventHash'],r['RelationshipKey'],revisions[r['RelationshipKey']]]),RelationshipKey=r['RelationshipKey'],reason='deprecated-endpoint-needs-human-review'))
    return dict(effectiveAt=effective_at,knownAt=known_at,policies=list(policies.values()),
        relationships=list(relationships.values()),policyDeprecations=[e['eventHash'] for e in policy_states.values()],
        relationshipRevisions=revisions,reviewLeads=sorted(leads,key=lambda r:r['leadKey']),
        clinicalAcceptance=False,realPolicyEffects=False,completeProductionGraph=False)


def native_history_plan(journal):
    """Existing native fields, immutable keys and explicit fictional evidence."""
    _validate(journal); rows={}; checkpoint_head=ZERO
    for index,event in enumerate(journal['events']):
        edges=[event['body']] if event['operation']=='set-relationship' else event['body']['relationships'] if event['operation']=='consolidate' else []
        for r in edges:
            checkpoint_head=event['eventHash']
            key=r['RelationshipKey']; versions=rows.setdefault(key,[])
            record=dict(Title='FICTIONAL relationship revision qualification',RelationshipKey=key,
                FromDocumentUID=r['from']['DocumentUID'],ToDocumentUID=r['to']['DocumentUID'],
                FromVersion=r['from']['policyEdition'],ToVersion=r['to']['policyEdition'],
                RelationshipType=r['type'],ReviewState='Proposed' if r['state']=='active' else 'Superseded',
                Rationale=r['rationale'],EvidenceRef=json.dumps(dict(FictionalTest=True,
                    revisionHash=event['eventHash'],previousRevision=r.get('previousRevision'),predecessorRelationshipKey=r.get('predecessorRelationshipKey'),
                    recordedAt=event['recordedAt'],effectiveFrom=event['effectiveFrom'],
                    decisionRef=event['decisionRef'],actorRef=event['actorRef'],fromPin=r['from'],toPin=r['to'],
                    journalHead=event['eventHash'],sourceJournal=dict(schemaVersion=1,kind=journal['kind'],events=journal['events'][:index+1]),nativeAuthority=False),sort_keys=True,separators=(',',':')))
            if len(record['EvidenceRef'])>60000:raise ValueError('Bounded native evidence payload exceeded; use a separately qualified archive binding')
            versions.append(dict(sourceVersionLabel=str(len(versions)+1)+'.0',record=record))
    return dict(records=[dict(keyField='RelationshipKey',keyValue=k,versions=v,
                sourcePlatform=dict(kind='fictional-logical-revision',originalAuditStampsRecreated=False)) for k,v in sorted(rows.items())],
                journalHead=head(journal),nativeCheckpointComplete=checkpoint_head==head(journal),realPolicyEffects=False)


def freeze(journal):
    _validate(journal)
    return dict(schemaVersion=1,journal=copy.deepcopy(journal),journalSha256=digest(journal),nativeRecoveryQualified=False)


def recover(snapshot):
    if snapshot.get('schemaVersion')!=1 or digest(snapshot['journal'])!=snapshot.get('journalSha256'):
        raise ValueError('Changed or incomplete snapshot')
    _validate(snapshot['journal']);return copy.deepcopy(snapshot['journal'])



def journal_from_native_records(rows, expected_head, journal_snapshot=None):
    """Recover the bounded fictional journal from actual native record payloads."""
    if not rows:raise ValueError('Native fixture rows required')
    snapshots=[]
    for row in rows:
        if not row.get('RelationshipKey','').startswith(PREFIX):raise ValueError('Unrelated native row')
        evidence=json.loads(row['EvidenceRef'])
        if evidence.get('FictionalTest') is not True or evidence.get('nativeAuthority') is not False:
            raise ValueError('Explicit fictional native evidence required')
        journal=evidence['sourceJournal'];_validate(journal);snapshots.append(journal)
    result=recover(journal_snapshot) if journal_snapshot is not None else max(snapshots,key=lambda j:len(j['events']))
    if head(result)!=expected_head:raise ValueError('Native checkpoint differs from the retained complete manifest head')
    if any(j['events']!=result['events'][:len(j['events'])] for j in snapshots):
        raise ValueError('Conflicting native journal prefixes')
    expected={r['keyValue']:r['versions'][-1]['record'] for r in native_history_plan(result)['records']}
    if len(rows)!=len(expected) or len({r['RelationshipKey'] for r in rows})!=len(rows):
        raise ValueError('Incomplete or duplicate native relationship population')
    for row in rows:
        record=expected.get(row['RelationshipKey'])
        if record is None or any(row.get(k)!=v for k,v in record.items()):raise ValueError('Changed native projection')
    return copy.deepcopy(result)


def checkpoint_bytes(snapshot):
    """Deterministic JSON transport with no trim-sensitive exterior whitespace."""
    recover(snapshot)
    return json.dumps(snapshot,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')

def main():
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal',type=Path,required=True)
    parser.add_argument('--request',type=Path)
    parser.add_argument('--expected-head')
    parser.add_argument('--effective-at',required=True)
    parser.add_argument('--known-at',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Preserve existing output and human edits')
    journal=json.loads(args.journal.read_text());created=False
    if args.request:
        if not args.expected_head:raise ValueError('Explicit journal preimage required')
        journal,created=append(journal,json.loads(args.request.read_text()),args.expected_head)
    snapshot=freeze(journal);view=reconstruct(journal,args.effective_at,args.known_at)
    plan=native_history_plan(journal)
    args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    for name,value in [('journal.json',journal),('snapshot.json',snapshot),('as-of.json',view),('native-history-plan.json',plan)]:
        target=args.output/name
        with target.open('x') as stream:
            target.chmod(0o600);stream.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    target=args.output/'native-checkpoint.json'
    with target.open('xb') as stream:
        target.chmod(0o600);stream.write(checkpoint_bytes(snapshot))
    print(json.dumps(dict(eventAppended=created,events=len(journal['events']),relationships=len(plan['records']),
        head=head(journal),reviewLeads=len(view['reviewLeads']),nativeWrites=0,realPolicyEffects=False)))


if __name__=='__main__':main()
