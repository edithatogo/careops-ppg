"""Opaque-token recovery uses two actual run observations; no native calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_binary_proof_producer import CompleteTransport, complete_fixture, FixedClock
import produce_binary_publication_proof as m


class ReconciliationTransport(CompleteTransport):
    def __init__(self,b,d,f,raw):
        super().__init__(b,d,f,raw)
        self.replay_rows=copy.deepcopy(self.rows)
        for row in self.replay_rows:
            row['runName']='run2'
            if row['name']=='Copy_binary_absent_only':row['properties']['status']='Skipped'
        self.replay_body={'text':'Prepare binary copy','text_6':b['scope']['CaseUID']}
        self.replay_changes={}
    def run(self,b):
        rid=b['copy']['runId'];second=rid=='run2'
        return {'name':rid,'properties':{'status':'Succeeded',
            'startTime':'2026-10-17T20:01:00Z' if second else '2026-10-17T19:59:00Z',
            'endTime':'2026-10-17T20:02:00Z' if second else '2026-10-17T20:00:00Z',
            'trigger':{'fixtureTrigger':'replay' if second else 'first'}}}
    def actions(self,b):return {'value':self.replay_rows if b['copy']['runId']=='run2' else self.rows}
    def action_content(self,row,kind):
        trigger=row.get('properties',{}).get('fixtureTrigger')
        if trigger:return {'body':self.replay_body if trigger=='replay' else
                           {'text':'Prepare binary copy','text_6':self.b['scope']['CaseUID']}}
        value=super().action_content(row,kind)
        if kind=='outputs':
            if row.get('runName')=='run2':value.update(runId='run2',copyCreatedCount=0,**self.replay_changes)
            else:value['issued']=self.native(self.b['copy']['reconciliation']['initialIssued'])
        return value


def fixture():
    b,d,f,raw,_=complete_fixture();initial=copy.deepcopy(b['issued']);initial['ETag']='"initial-native-token"'
    b['copy']['reconciliation']={'runId':'run2','initialIssued':initial}
    return b,d,f,raw


class CopyReconciliationTests(unittest.TestCase):
    def inspect(self,b,d,t):
        with tempfile.TemporaryDirectory() as directory:
            return m.inspect_copy(b,d,t,m.Capture(Path(directory)/'evidence'))
    def test_current_byte_proof_preserves_first_copy_and_explicit_token_transition(self):
        b,d,f,raw=fixture();t=ReconciliationTransport(b,d,f,raw)
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'datetime',FixedClock):
            target=Path(directory)/'stage';m.stage(b,d,t,target,m.digest(b))
            audit=json.loads((target/'copy-reconciliation-audit.json').read_bytes())
            self.assertFalse(audit['oldTokenBytesVerified'])
            self.assertNotEqual(audit['initialIssued']['ETag'],audit['currentIssued']['ETag'])
            first=json.loads((target/'copy-terminal-receipt.json').read_bytes())
            replay=json.loads((target/'copy-reconciliation-receipt.json').read_bytes())
            self.assertEqual(first['copyCreatedCount'],1);self.assertEqual(replay['copyCreatedCount'],0)
            proof=json.loads((target/'binary-proof.json').read_bytes())
            self.assertEqual(proof['issued']['ETag'],b['issued']['ETag'])
            self.assertEqual((target/'source.docx').read_bytes(),(target/'issued.docx').read_bytes())
    def test_replay_writes_missing_action_and_boolean_zero_refused(self):
        for mode in ['writer','missing','boolean','effect','scope','authorisation']:
            with self.subTest(mode=mode):
                b,d,f,raw=fixture();t=ReconciliationTransport(b,d,f,raw)
                if mode=='writer':t.replay_rows[0]['properties']['status']='Succeeded'
                if mode=='missing':t.replay_rows.pop()
                if mode=='boolean':t.replay_changes['publicationCreatedCount']=False
                if mode=='effect':t.replay_changes['caseWrites']=1
                if mode=='scope':t.replay_changes['preparedScope']={}
                if mode=='authorisation':t.replay_changes['purposeAuthorisation']={}
                with self.assertRaises(ValueError):self.inspect(b,d,t)
    def test_changed_input_different_object_version_length_or_run_refused(self):
        for key in ['input','UniqueId','nativeVersion','Length','runId','ETag']:
            with self.subTest(key=key):
                b,d,f,raw=fixture();t=ReconciliationTransport(b,d,f,raw)
                if key=='input':t.replay_body['text']='Record publication'
                elif key=='runId':b['copy']['reconciliation']['runId']='run1'
                else:
                    old=b['copy']['reconciliation']['initialIssued']
                    old[key]=b['source']['UniqueId'] if key=='UniqueId' else b['issued']['ETag'] if key=='ETag' else 1 if key=='Length' else 'other'
                with self.assertRaises(ValueError):self.inspect(b,d,t)
    def test_current_bytes_still_mandatory_after_zero_effect_replay(self):
        b,d,f,raw=fixture();t=ReconciliationTransport(b,d,f,raw);t.files[b['issued']['DocumentReference']]=b'X'*len(raw)
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'datetime',FixedClock):
            with self.assertRaises(ValueError):m.stage(b,d,t,Path(directory)/'stage',m.digest(b))


if __name__=='__main__':unittest.main()
