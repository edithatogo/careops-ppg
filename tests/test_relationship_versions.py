import copy
import hashlib
import unittest
from scripts.ppg_relationship_versions import empty,append,head,reconstruct,freeze,recover,native_history_plan,journal_from_native_records,checkpoint_bytes,PREFIX


def policy(name,edition='1'):
    return dict(DocumentUID=PREFIX+name,policyEdition=edition,
        sha256=hashlib.sha256((name+edition).encode()).hexdigest(),sourceRef='fixture:'+name+edition)


def request(name,op,body,recorded='2026-01-01T00:00:00Z',effective='2026-01-01T00:00:00Z'):
    return dict(requestId=PREFIX+name,operation=op,body=body,recordedAt=recorded,effectiveFrom=effective,
        decisionRef='fixture:technical-decision',actorRef='FICTIONAL technical operator',
        rationale='Fictional behaviour qualification only',FictionalTest=True)


def edge(name,left,right,kind='references',**kwargs):
    return dict(RelationshipKey=PREFIX+name,**{'from':left,'to':right},type=kind,state='active',
        rationale='Fictional relationship source',**kwargs)


def fixture():
    j=empty()
    for name in ['a','b','c','consumer']:
        j,_=append(j,request('add-'+name,'add-policy',policy(name)),head(j))
    r=edge('ref',policy('consumer'),policy('a'))
    j,_=append(j,request('reference','set-relationship',r),head(j))
    return j


class VersionTests(unittest.TestCase):
    def test_consolidation_preserves_incoming_reference(self):
        j=fixture();prior=copy.deepcopy(j)
        body=dict(successor=policy('c'),predecessors=[policy('a'),policy('b')],relationships=[edge('ca',policy('c'),policy('a'),'supersedes'),edge('cb',policy('c'),policy('b'),'supersedes')])
        j,_=append(j,request('consolidate','consolidate',body),head(j))
        graph=reconstruct(j,'2026-01-02T00:00:00Z','2026-01-02T00:00:00Z')
        self.assertEqual(len(graph['relationships']),3)
        self.assertEqual(graph['relationships'][0]['to'],policy('a'))
        self.assertEqual(prior['events'],j['events'][:5])
        self.assertFalse(graph['clinicalAcceptance'])

    def test_deprecation_leads_no_delete_or_repoint(self):
        j=fixture();j,_=append(j,request('deprecate','deprecate-policy',dict(subject=policy('a'))),head(j))
        g=reconstruct(j,'2026-01-02T00:00:00Z','2026-01-02T00:00:00Z')
        self.assertEqual(len(g['relationships']),1);self.assertEqual(len(g['reviewLeads']),1)
        self.assertEqual(g,reconstruct(j,'2026-01-02T00:00:00Z','2026-01-02T00:00:00Z'))

    def test_recorded_and_effective_time_distinct(self):
        j=fixture();r=copy.deepcopy(j['events'][-1]['body']);r.update(rationale='Corrected fictional rationale',previousRevision=head(j))
        j,_=append(j,request('correction','set-relationship',r,recorded='2026-03-01T00:00:00Z'),head(j))
        before=reconstruct(j,'2026-01-02T00:00:00Z','2026-02-01T00:00:00Z')
        after=reconstruct(j,'2026-01-02T00:00:00Z','2026-03-02T00:00:00Z')
        self.assertNotEqual(before['relationships'][0]['rationale'],after['relationships'][0]['rationale'])
        self.assertEqual(native_history_plan(j)['records'][0]['versions'][0],native_history_plan(fixture())['records'][0]['versions'][0])

    def test_replay_and_changed_request_and_stale_guard(self):
        j=fixture();r=j['events'][-1];q={k:v for k,v in r.items() if k not in {'eventHash','sequence','previousHash'}}
        self.assertEqual(append(j,q,'stale'),(j,False))
        q['rationale']='changed'
        with self.assertRaises(ValueError):append(j,q,head(j))
        with self.assertRaises(ValueError):append(j,request('new','deprecate-policy',dict(subject=policy('a'))),'stale')

    def test_endpoint_change_requires_new_identity(self):
        j=fixture();r=copy.deepcopy(j['events'][-1]['body']);r.update(previousRevision=head(j));r['to']=policy('b')
        with self.assertRaises(ValueError):append(j,request('repoint','set-relationship',r),head(j))

    def test_invalid_consolidation_and_unknown_endpoint_refused(self):
        j=fixture()
        for predecessors in [[policy('a')],[policy('a'),policy('a')],[policy('a'),policy('unknown')]]:
            q=request('bad','consolidate',dict(successor=policy('c'),predecessors=predecessors,relationships=[]))
            with self.assertRaises(ValueError):append(j,q,head(j))
        with self.assertRaises(ValueError):append(j,request('missing','set-relationship',edge('missing',policy('a'),policy('unknown'))),head(j))

    def test_supersession_cycle_refused_mutual_reference_allowed(self):
        j=fixture()
        for n,left,right,kind in [('ab',policy('a'),policy('b'),'supersedes'),('back-ref',policy('a'),policy('consumer'),'references')]:
            j,_=append(j,request(n,'set-relationship',edge(n,left,right,kind)),head(j))
        with self.assertRaises(ValueError):append(j,request('ba','set-relationship',edge('ba',policy('b'),policy('a'),'supersedes')),head(j))

    def test_snapshot_reconstruction_and_tamper_missing_reorder_refused(self):
        j=fixture();s=freeze(j);self.assertEqual(recover(s),j)
        for change in ['body','missing','reorder']:
            bad=copy.deepcopy(s)
            if change=='body':bad['journal']['events'][0]['body']['sourceRef']='changed'
            elif change=='missing':bad['journal']['events'].pop(0)
            else:bad['journal']['events'].reverse()
            with self.assertRaises(ValueError):recover(bad)

    def test_history_contains_exact_old_and_corrected_records(self):
        j=fixture();r=copy.deepcopy(j['events'][-1]['body']);r.update(previousRevision=head(j),state='ended')
        j,_=append(j,request('end','set-relationship',r),head(j));versions=native_history_plan(j)['records'][0]['versions']
        self.assertEqual([r['sourceVersionLabel'] for r in versions],['1.0','2.0'])
        self.assertEqual([r['record']['ReviewState'] for r in versions],['Proposed','Superseded'])
        self.assertTrue(all('nativeAuthority":false' in r['record']['EvidenceRef'] for r in versions))

    def test_native_snapshot_recovery_requires_complete_exact_rows(self):
        j=fixture();rows=[r['versions'][-1]['record'] for r in native_history_plan(j)['records']]
        self.assertEqual(journal_from_native_records(rows,head(j)),j)
        bad=copy.deepcopy(rows);bad[0]['Rationale']='human edit'
        with self.assertRaises(ValueError):journal_from_native_records(bad,head(j))
        with self.assertRaises(ValueError):journal_from_native_records([],head(j))
        with self.assertRaises(ValueError):journal_from_native_records(rows+rows,head(j))

    def test_policy_only_tail_cannot_be_lost_in_native_recovery(self):
        j=fixture();rows=[r['versions'][-1]['record'] for r in native_history_plan(j)['records']]
        j,_=append(j,request('tail','deprecate-policy',dict(subject=policy('a'))),head(j))
        self.assertFalse(native_history_plan(j)['nativeCheckpointComplete'])
        with self.assertRaises(ValueError):journal_from_native_records(rows,head(j))
        self.assertEqual(journal_from_native_records(rows,head(j),freeze(j)),j)

    def test_checkpoint_transport_is_deterministic_and_not_trim_sensitive(self):
        snapshot=freeze(fixture());raw=checkpoint_bytes(snapshot)
        self.assertEqual(raw,raw.strip());self.assertEqual(raw,checkpoint_bytes(snapshot))
        import json
        self.assertEqual(recover(json.loads(raw)),fixture())

    def test_future_deprecation_does_not_change_earlier_graph(self):
        j=fixture();j,_=append(j,request('future','deprecate-policy',dict(subject=policy('a')),effective='2026-02-01T00:00:00Z'),head(j))
        self.assertEqual(reconstruct(j,'2026-01-02T00:00:00Z','2026-01-02T00:00:00Z')['reviewLeads'],[])
        self.assertEqual(len(reconstruct(j,'2026-02-02T00:00:00Z','2026-02-02T00:00:00Z')['reviewLeads']),1)

    def test_real_ids_and_bad_dates_and_conflicting_edition_refused(self):
        j=fixture()
        for q in [request('bad','add-policy',{**policy('z'),'DocumentUID':'real-policy'}),
                  request('bad','add-policy',policy('z'),effective='unknown'),
                  request('bad','add-policy',{**policy('a'),'sha256':'b'*64})]:
            with self.assertRaises(ValueError):append(j,q,head(j))


if __name__=='__main__':unittest.main()
