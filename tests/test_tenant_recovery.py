# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from uuid import UUID
from scripts.ppg_tenant_recovery import prepare,digest

class TenantRecoveryTests(unittest.TestCase):
    def setUp(self):
        fields=[dict(name=x,type={'ParentId':'Lookup','Owner':'User'}.get(x,'Text')) for x in ['Key','SourceURI','ParentId','Owner']]
        self.payload=dict(schemaVersion=1,sourceTenantId=str(UUID(int=1, version=4)),
          entities={'examples':dict(fields=fields,records=[dict(key='a',values=dict(Key='a',SourceURI='https://source.invalid/file',ParentId=7,Owner='source-person'),references={'SourceURI':dict(kind='file',key='file',part='url'),'ParentId':dict(kind='lookup',key='examples:a'),'Owner':dict(kind='identity',key='source-person')})])},
          files={'file':dict(sha256='a'*64,bytes=5)})
        self.destination=dict(tenantId=str(UUID(int=2, version=4)),siteUrl='https://destination.invalid/sites/recovery',
          lists={'examples':str(UUID(int=3, version=4))},items={'examples:a':9},identities={'source-person':'destination-person'},
          files={'file':dict(url='https://destination.invalid/sites/recovery/file',uniqueId=str(UUID(int=4, version=4)),version='1.0',sha256='a'*64,bytes=5)})
    def envelope(self):return dict(payload=self.payload,sha256=digest(self.payload))
    def test_explicit_remapping_preserves_source_and_never_claims_native_success(self):
        before=copy.deepcopy((self.payload,self.destination));r=prepare(self.envelope(),self.destination)
        self.assertTrue(r['readyForNativeQualification']);self.assertFalse(r['nativeRestoreVerified'])
        self.assertEqual(r['records'][0]['fields']['ParentId'],9)
        self.assertEqual(before,(self.payload,self.destination))
    def test_missing_destination_and_identity_are_explicit_holds(self):
        self.assertFalse(prepare(self.envelope())['readyForNativeQualification'])
        self.destination['identities']={};r=prepare(self.envelope(),self.destination)
        self.assertFalse(r['readyForNativeQualification']);self.assertIsNone(r['records'][0]['fields']['Owner'])
    def test_source_tenant_and_wrong_file_bytes_refuse(self):
        original=copy.deepcopy(self.destination)
        for mutate in [lambda d:d.update(tenantId=self.payload['sourceTenantId']),lambda d:d['files']['file'].update(sha256='b'*64),lambda d:d['files']['file'].update(url='https://elsewhere.invalid/file'),lambda d:d['items'].update({'examples:a':True})]:
            self.destination=copy.deepcopy(original);mutate(self.destination)
            with self.assertRaises(ValueError):prepare(self.envelope(),self.destination)
    def test_corruption_and_lookup_outside_export_refuse(self):
        e=self.envelope();e['payload']['files']['file']['bytes']=6
        with self.assertRaisesRegex(ValueError,'integrity'):prepare(e,self.destination)
        self.payload['entities']['examples']['records'][0]['references']['ParentId']['key']='missing:key'
        with self.assertRaisesRegex(ValueError,'outside'):prepare(self.envelope(),self.destination)

    def test_unannotated_native_reference_refuses(self):
        del self.payload['entities']['examples']['records'][0]['references']['ParentId']
        with self.assertRaisesRegex(ValueError,'explicit remapping'):prepare(self.envelope(),self.destination)
