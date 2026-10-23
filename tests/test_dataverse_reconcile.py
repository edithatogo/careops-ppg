import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_dataverse_reconcile import reconcile,KEYS,load_export
D='00000000-0000-4000-8000-000000000001'
C='00000000-0000-4000-8000-000000000002'
E='00000000-0000-4000-8000-000000000003'


def fixture():
    datasets={k:[] for k in KEYS}
    datasets['catalogue']=[dict(DocumentUID=D,sourceNextReviewMonth='2026-10',sourceNextReviewDateRaw=46300,sourceTitle='Fictional')]
    datasets['cases']=[dict(CaseUID=C,linkedDocumentUIDs=[D],caseStatus='Awaiting human review',targetDate=None)]
    for k in ['readiness','assurance','consultation']:datasets[k]=[dict(EventUID=E,CaseUID=C,ReviewedVersionRef='fictional-v1',DocumentSHA256='a'*64,Finding='Not performed')]
    datasets['evidence']=[dict(NativeFileUniqueId=E,PPGDocumentUID='',PPGCurrency='Unconfirmed',nativeVersion='1.0',sha256='a'*64)]
    return dict(schemaVersion=1,identityExceptions=[],datasets=datasets)


class MigrationReconcileTests(unittest.TestCase):
    def test_exact_parity_never_authorises_cutover(self):
        a=fixture();r=reconcile(a,copy.deepcopy(a));self.assertTrue(r['structurallyReconciled']);self.assertFalse(r['cutoverAuthorised']);self.assertFalse(r['securityParityVerified'])
    def test_nil_persistent_and_reference_identities_are_rejected(self):
        nil='00000000-0000-0000-0000-000000000000'
        for dataset,key in KEYS.items():
            a=fixture();a['datasets'][dataset][0][key]=nil
            with self.subTest(dataset=dataset),self.assertRaisesRegex(ValueError,'nil UUID'):
                reconcile(a,copy.deepcopy(a))
        for dataset,field in [('cases','linkedDocumentUIDs'),('assurance','ReadinessEventUID'),('evidence','PPGDocumentUID')]:
            a=fixture();a['datasets'][dataset][0][field]=[nil] if field=='linkedDocumentUIDs' else nil
            with self.subTest(dataset=dataset,field=field),self.assertRaisesRegex(ValueError,'nil UUID'):
                reconcile(a,copy.deepcopy(a))

    def test_duplicate_and_orphan_fail_closed(self):
        for mode in ['duplicate','orphan-case','orphan-event']:
            a=fixture()
            if mode=='duplicate':a['datasets']['catalogue']*=2
            elif mode=='orphan-case':a['datasets']['catalogue']=[]
            else:a['datasets']['cases']=[]
            with self.assertRaises(ValueError):reconcile(a,fixture())
    def test_missing_extra_and_unexpected_fields_are_differences(self):
        a=fixture();b=copy.deepcopy(a);b['datasets']['evidence']=[];self.assertEqual(reconcile(a,b)['differences'][0]['kind'],'missing-target')
        b=copy.deepcopy(a);b['datasets']['cases'][0]['approved']=True;self.assertFalse(reconcile(a,b)['structurallyReconciled'])
    def test_absent_null_dates_and_boolean_number_remain_distinct(self):
        for field,value in [('sourceNextReviewMonth','2026-10-01'),('sourceNextReviewDateRaw',True)]:
            a=fixture();b=copy.deepcopy(a);b['datasets']['catalogue'][0][field]=value;self.assertFalse(reconcile(a,b)['structurallyReconciled'])
        a=fixture();b=copy.deepcopy(a);del b['datasets']['cases'][0]['targetDate'];self.assertFalse(reconcile(a,b)['structurallyReconciled'])
    def test_exceptions_and_incomplete_datasets_hold_reconciliation(self):
        a=fixture();a['identityExceptions']=[dict(kind='missing-uid')];self.assertFalse(reconcile(a,a)['structurallyReconciled'])
        del a['datasets']['assurance']
        with self.assertRaises(ValueError):reconcile(a,fixture())
    def test_source_inputs_remain_unchanged(self):
        a=fixture();original=copy.deepcopy(a);reconcile(a,copy.deepcopy(a));self.assertEqual(a,original)

    def test_duplicate_json_keys_rejected_at_every_depth(self):
        for raw in ['{"schemaVersion":1,"schemaVersion":1}', '{"datasets":{"cases":[{"CaseUID":"a","CaseUID":"b"}]}}']:
            with self.assertRaisesRegex(ValueError,'duplicate JSON key'):load_export(raw)

    def test_matching_exports_with_broken_references_are_rejected(self):
        missing='00000000-0000-4000-8000-000000000099'
        for dataset,field in [('readiness','SupersedesEventUID'),('assurance','ParentEventUID'),('assurance','ReadinessEventUID'),('consultation','SupersedesEventUID'),('evidence','PPGDocumentUID')]:
            a=fixture();a['datasets'][dataset][0][field]=missing
            with self.subTest(dataset=dataset,field=field),self.assertRaisesRegex(ValueError,'orphan'):reconcile(a,copy.deepcopy(a))

    def test_self_cross_case_and_duplicate_links_rejected(self):
        a=fixture();a['datasets']['cases'][0]['linkedDocumentUIDs']=[D,D]
        with self.assertRaisesRegex(ValueError,'duplicate case'):reconcile(a,a)
        a=fixture();a['datasets']['consultation'][0]['ParentEventUID']=E
        with self.assertRaisesRegex(ValueError,'self event'):reconcile(a,a)
        a=fixture();other='00000000-0000-4000-8000-000000000004'
        a['datasets']['cases'].append(dict(CaseUID=other,linkedDocumentUIDs=[D]))
        a['datasets']['readiness'][0]['CaseUID']=other
        a['datasets']['assurance'][0]['ReadinessEventUID']=E
        with self.assertRaisesRegex(ValueError,'cross-case'):reconcile(a,a)

    def test_valid_cross_dataset_and_history_references(self):
        a=fixture();prior=copy.deepcopy(a['datasets']['assurance'][0]);prior['EventUID']='00000000-0000-4000-8000-000000000005'
        a['datasets']['assurance'].append(prior)
        a['datasets']['assurance'][0].update(ParentEventUID=prior['EventUID'],ReadinessEventUID=E)
        a['datasets']['evidence'][0]['PPGDocumentUID']=D
        self.assertTrue(reconcile(a,copy.deepcopy(a))['structurallyReconciled'])

    def test_only_null_or_empty_text_can_be_blank_optional_reference(self):
        for dataset,field in [('assurance','ReadinessEventUID'),('consultation','ParentEventUID'),('readiness','SupersedesEventUID'),('evidence','PPGDocumentUID')]:
            for value in [False,0,[],{}]:
                a=fixture();a['datasets'][dataset][0][field]=value
                with self.subTest(dataset=dataset,value=value),self.assertRaises(ValueError):reconcile(a,a)
            for value in [None,'']:
                a=fixture();a['datasets'][dataset][0][field]=value
                self.assertTrue(reconcile(a,a)['structurallyReconciled'])

    def test_circular_histories_fail_even_when_exports_match(self):
        for dataset in ('readiness','assurance','consultation'):
            a=fixture();row=a['datasets'][dataset][0];prior=copy.deepcopy(row)
            prior['EventUID']='00000000-0000-4000-8000-000000000099'
            row['SupersedesEventUID']=prior['EventUID'];prior['SupersedesEventUID']=E
            a['datasets'][dataset].append(prior)
            with self.subTest(dataset=dataset),self.assertRaisesRegex(ValueError,'cyclic'):reconcile(a,a)

    def test_shared_ancestor_and_long_history_are_valid(self):
        a=fixture();rows=a['datasets']['assurance'];previous=E
        for i in range(1000):
            row=copy.deepcopy(rows[0]);row['EventUID']=f'00000000-0000-4000-8000-{i+100:012d}'
            row.update(ParentEventUID=previous,SupersedesEventUID=previous)
            rows.append(row);previous=row['EventUID']
        self.assertTrue(reconcile(a,a)['structurallyReconciled'])


if __name__=='__main__':unittest.main()
