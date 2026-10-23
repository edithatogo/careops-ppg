import unittest
from scripts.ppg_annotation_adapter import field_binding, normalise_annotation, annotations_from_export
from scripts.ppg_review_intelligence import carry_annotations


class AnnotationAdapter(unittest.TestCase):
    def test_actual_internal_name_mapping_and_drift(self):
        spec=[dict(name='DocumentUID',type='Text',required=True)]
        native=[dict(StaticName='DocumentUID',InternalName='Document_x0020_UID',TypeAsString='Text',Required=True)]
        self.assertEqual(field_binding(spec,native),{'DocumentUID':'Document_x0020_UID'})
        with self.assertRaises(ValueError): field_binding(spec,native+native)
        native[0]['Required']=False
        with self.assertRaises(ValueError): field_binding(spec,native)

    def test_original_is_not_replaced_by_latest_note(self):
        names=['ReviewState','DocumentUID','DocumentVersion','SectionId','OriginalSuggestion','EvidenceRef','DecisionRationale','IncorporatedVersion']
        binding={n:n for n in names}
        item=dict(Id=1,ReviewState='Triaged',DocumentUID='fictional',DocumentVersion='1',SectionId='s',OriginalSuggestion='Later note',Created='2026-10-18T00:00:00Z',AuthorId=1)
        result=normalise_annotation(item,binding,'Original suggestion','fictional-list')
        self.assertEqual(result['originalText'],'Original suggestion')
        self.assertEqual(result['latestAddition'],'Later note')
        self.assertTrue(carry_annotations([result],'fictional','2',['s'])[0]['requiresReconciliation'])
        with self.assertRaises(ValueError):normalise_annotation(item,binding,'','fictional-list')

    def test_complete_history_required_and_all_additions_retained(self):
        names=['ReviewState','DocumentUID','DocumentVersion','SectionId','OriginalSuggestion','EvidenceRef','DecisionRationale','IncorporatedVersion']
        binding={n:n for n in names}
        item=dict(Id=1,ReviewState='Triaged',DocumentUID='fictional',DocumentVersion='1',SectionId='s',OriginalSuggestion='Later',Created='2026-10-18T00:00:00Z',AuthorId=1)
        first=dict(VersionId=512,VersionLabel='1.0',Created=item['Created'],OriginalSuggestion='Original',EvidenceRef=None,DecisionRationale=None)
        later=dict(first,VersionId=1024,VersionLabel='2.0',OriginalSuggestion='Later')
        export=dict(binding=binding,listId='fictional-list',annotationItems={'value':[item]},histories=[{'id':1,'versions':{'value':[later,first]}}])
        annotation=annotations_from_export(export)[0]
        self.assertEqual(annotation['originalText'],'Original')
        self.assertEqual([v['suggestion'] for v in annotation['versionHistory']],['Original','Later'])
        export['histories'][0]['versions']['value']=[later]
        with self.assertRaises(ValueError):annotations_from_export(export)

    def test_historical_context_is_preserved_without_using_current_binding_or_actor(self):
        import copy
        names=['ReviewState','DocumentUID','DocumentVersion','SectionId','OriginalSuggestion','EvidenceRef','DecisionRationale','IncorporatedVersion']
        binding={n:n for n in names}
        item=dict(Id=1,ReviewState='Incorporated',DocumentUID='fictional',DocumentVersion='2',SectionId='new',OriginalSuggestion='Later',Created='2026-10-18T00:00:00Z',AuthorId=1)
        first=dict(VersionId=512,VersionLabel='1.0',Created=item['Created'],OriginalSuggestion='Original',EvidenceRef=None,DecisionRationale=None,ReviewState='Received',DocumentUID='fictional',DocumentVersion='1',SectionId='old',IncorporatedVersion=None,Author={'LookupId':1},Editor={'LookupId':1},Modified=item['Created'])
        later=dict(first,VersionId=1024,VersionLabel='2.0',ReviewState='Incorporated',DocumentVersion='2',SectionId='new',IncorporatedVersion='2',Editor={'LookupId':2},DecisionRationale='Fictional test rationale')
        export=dict(binding=binding,listId='fictional-list',annotationItems={'value':[item]},histories=[{'id':1,'versions':{'value':[later,first]}}]);before=copy.deepcopy(export)
        history=annotations_from_export(export)[0]['versionHistory']
        self.assertEqual([v['status'] for v in history],['received','incorporated'])
        self.assertEqual([v['documentVersion'] for v in history],['1','2'])
        self.assertEqual([v['sectionId'] for v in history],['old','new'])
        self.assertEqual(history[1]['editor'],{'LookupId':2})
        self.assertEqual(history[0]['missingHistoryFields'],[])
        self.assertEqual(export,before)
        history[0]['author']['LookupId']=99
        self.assertEqual(export,before)
        del first['Editor']
        result=annotations_from_export(export)[0]['versionHistory'][0]
        self.assertIsNone(result['editor']);self.assertIn('Editor',result['missingHistoryFields'])
        first['ReviewState']='Approved'
        with self.assertRaises(ValueError):annotations_from_export(export)
        first['ReviewState']='Received';export['histories'][0]['versions']['value'].append(first)
        with self.assertRaises(ValueError):annotations_from_export(export)

    def test_optional_web_summary_keeps_historical_versions_distinct(self):
        binding={n:n for n in ['ReviewState','DocumentUID','DocumentVersion','SectionId',
            'OriginalSuggestion','EvidenceRef','DecisionRationale','IncorporatedVersion','DispositionSummary']}
        item=dict(Id=1,ReviewState='Accepted',DocumentUID='fictional',DocumentVersion='1',
            SectionId='s',Created='2026-10-21T00:00:00Z',AuthorId=1,DispositionSummary='Later summary')
        first=dict(VersionId=512,VersionLabel='1.0',Created=item['Created'],
            OriginalSuggestion='Original',EvidenceRef=None,DecisionRationale=None)
        later=dict(first,VersionId=1024,VersionLabel='2.0',DispositionSummary='Later summary')
        export=dict(binding=binding,listId='fictional',annotationItems={'value':[item]},
            histories=[{'id':1,'versions':{'value':[later,first]}}])
        value=annotations_from_export(export)[0]
        self.assertEqual(value['dispositionSummary'],'Later summary')
        self.assertIsNone(value['versionHistory'][0]['dispositionSummary'])
        self.assertIn('DispositionSummary',value['versionHistory'][0]['missingHistoryFields'])
        self.assertEqual(value['versionHistory'][1]['dispositionSummary'],'Later summary')
        self.assertEqual(value['originalText'],'Original')


if __name__ == '__main__': unittest.main()
