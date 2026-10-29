# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
import copy
import unittest
from scripts.ppg_selected_recovery import reconcile


class RecoveryCoverageTests(unittest.TestCase):
    def bundle(self):
        fields=[dict(InternalName=k,TypeAsString='Text',Hidden=False,ReadOnlyField=False,Required=False) for k in ('Key','HumanText')]
        rows=[dict(Id=1,Key='fictional-record',HumanText='Preserve this edit')]
        return dict(pairs=[dict(source=dict(Id='source'),target=dict(Id='target'),key='Key',sourceRows=copy.deepcopy(rows),targetRows=copy.deepcopy(rows))],snapshots={s:dict(fields=copy.deepcopy(fields),rows=copy.deepcopy(rows)) for s in ('source','target')},files=[])

    def test_complete_fields_preserve_input(self):
        bundle=self.bundle();before=copy.deepcopy(bundle)
        result=reconcile(bundle)
        self.assertTrue(result['selectedCoverageComplete'])
        self.assertFalse(result['nativeReadbackPerformed'])
        self.assertEqual(result['counts']['fields'],2)
        self.assertEqual(bundle,before)
        bundle['pairs'][0]['targetRows'][0]['HumanText']='Changed'
        with self.assertRaisesRegex(ValueError,'value differs'):reconcile(bundle)

    def test_missing_duplicate_and_schema_coverage(self):
        for mutation in ('missing','duplicate','schema','same-target'):
            b=self.bundle()
            if mutation=='missing':b['pairs'][0]['targetRows']=[]
            elif mutation=='duplicate':b['pairs'][0]['targetRows']*=2
            elif mutation=='schema':b['snapshots']['target']['fields'].pop()
            else:b['pairs'][0]['target']['Id']='source'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):reconcile(b)

    def test_lookup_must_resolve_to_independent_same_business_key(self):
        b=self.bundle()
        for side,parent in [('source','parent-source'),('target','parent-target')]:
            b['snapshots'][side]['fields'].append(dict(InternalName='Parent',TypeAsString='Lookup',LookupList=parent,LookupField='Key',Hidden=False,ReadOnlyField=False,Required=False))
            b['snapshots'][parent]=dict(rows=[dict(Id=7,Key='parent-key')])
            b['pairs'][0][side+'Rows'][0]['ParentId']=7
        self.assertEqual(reconcile(b)['counts']['lookups'],1)
        b['snapshots']['parent-target']['rows'][0]['Key']='different-parent'
        with self.assertRaisesRegex(ValueError,'resolve independently'):reconcile(b)

    def test_archival_types_are_lossless_and_choices_still_checked(self):
        b=self.bundle()
        a=b['snapshots']['source']['fields'][1]
        a.update(TypeAsString='Choice',Choices=['Preserve this edit'],Required=True)
        result=reconcile(b)
        self.assertEqual(len(result['archiveSchemaCompatibility']),2)
        b['pairs'][0]['targetRows'][0]['HumanText']='Not a source choice'
        with self.assertRaisesRegex(ValueError,'outside source choices'):reconcile(b)
        b=self.bundle();b['snapshots']['target']['fields'][1]['TypeAsString']='Number'
        with self.assertRaisesRegex(ValueError,'Lossy'):reconcile(b)

    def test_logical_reference_and_missing_source_values_are_explicit(self):
        b=self.bundle()
        b['referenceBindings']={'HumanText':dict(source='source',target='target',key='HumanText')}
        self.assertEqual(reconcile(b)['counts']['logicalReferences'],1)
        b['snapshots']['target']['rows']=[]
        with self.assertRaisesRegex(ValueError,'Unresolved logical'):reconcile(b)
        b=self.bundle()
        for side in ('source','target'):
            b['snapshots'][side]['fields'][1]['Required']=True
            b['pairs'][0][side+'Rows'][0]['HumanText']=None
        self.assertEqual(reconcile(b)['sourceMissingRequired'],[dict(key='fictional-record',field='HumanText')])

    def test_empty_manifest_and_wrong_file_version_cannot_pass(self):
        with self.assertRaisesRegex(ValueError,'nonempty'):reconcile(dict(pairs=[],snapshots={},files=[]))
        b=self.bundle();p=b['pairs'][0];p['key']='EvidenceVersionKey'
        for side in ('source','target'):
            b['snapshots'][side]['fields'][0]['InternalName']='EvidenceVersionKey'
            p[side+'Rows'][0]['EvidenceVersionKey']=p[side+'Rows'][0].pop('Key')
            p[side+'Rows'][0]['ExactVersion']='Native file version 1.0; SHA-256 '+'a'*64
        b['files']=[dict(key='fictional-record',source=dict(UniqueId='source-file'),recovered=dict(UniqueId='recovered-file'),sourceVersion='1.0',sourceSHA256='a'*64,targetSHA256='a'*64,bytes=7,independent=True)]
        self.assertEqual(reconcile(b)['counts']['files'],1)
        b['files'][0]['sourceVersion']='2.0'
        with self.assertRaisesRegex(ValueError,'file/version'):reconcile(b)
