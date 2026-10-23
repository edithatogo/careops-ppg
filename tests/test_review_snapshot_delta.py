import copy
import json
import unittest
from scripts.ppg_review_snapshot_delta import compare_exports, require_whole_export_claim


def export(count=1):
    names = ['ReviewState','DocumentUID','DocumentVersion','SectionId',
             'OriginalSuggestion','EvidenceRef','DecisionRationale','IncorporatedVersion']
    result = dict(binding={n:n for n in names}, listId='fictional-list',
                  annotationItems={'value':[]}, histories=[])
    for number in range(1, count+1):
        item = dict(Id=number,ReviewState='Received',DocumentUID='fictional',
                    DocumentVersion='1',SectionId='s',OriginalSuggestion='Original',
                    Created='2026-10-19T00:00:00Z',AuthorId=1)
        first = dict(VersionId=512,VersionLabel='1.0',Created=item['Created'],
                     OriginalSuggestion='Original',EvidenceRef=None,DecisionRationale=None)
        result['annotationItems']['value'].append(item)
        result['histories'].append({'id':number,'versions':{'value':[first]}})
    return result


def raw(value):
    return json.dumps(value).encode()


class SnapshotDelta(unittest.TestCase):
    def test_new_row_preserves_previous_rows_without_whole_snapshot_equality(self):
        delta = compare_exports(raw(export()),raw(export(2)),'fictional')
        self.assertTrue(delta['previousSubjectRowsUnchanged'])
        self.assertFalse(delta['wholeExportUnchanged'])
        self.assertEqual(delta['addedAnnotationIds'],['fictional-list:2'])
        with self.assertRaises(ValueError): require_whole_export_claim(delta,True)
        self.assertTrue(require_whole_export_claim(delta,False))

    def test_actual_change_or_missing_row_is_not_called_preserved(self):
        before = export(2); after = copy.deepcopy(before)
        after['annotationItems']['value'][0]['ReviewState'] = 'Triaged'
        delta = compare_exports(raw(before),raw(after),'fictional')
        self.assertFalse(delta['previousSubjectRowsUnchanged'])
        self.assertEqual(delta['changedAnnotationIds'],['fictional-list:1'])
        self.assertEqual(compare_exports(raw(before),raw(export()),'fictional')
                         ['missingAnnotationIds'],['fictional-list:2'])

    def test_partial_history_resource_drift_and_duplicate_identity_refused(self):
        before = export(); after = copy.deepcopy(before)
        with self.assertRaises(ValueError): compare_exports(raw(before),raw(after),None)
        after['histories'][0]['versions']['@odata.nextLink'] = 'more'
        with self.assertRaises(ValueError): compare_exports(raw(before),raw(after),'fictional')
        after = copy.deepcopy(before); after['listId'] = 'another-list'
        with self.assertRaises(ValueError): compare_exports(raw(before),raw(after),'fictional')
        after = copy.deepcopy(before)
        after['annotationItems']['value'].append(copy.deepcopy(after['annotationItems']['value'][0]))
        with self.assertRaises(ValueError): compare_exports(raw(before),raw(after),'fictional')

    def test_same_export_and_unrelated_document_change_are_distinct(self):
        before = export(); after = export(2)
        self.assertTrue(compare_exports(raw(before),raw(before),'fictional')['wholeExportUnchanged'])
        after['annotationItems']['value'][1]['DocumentUID'] = 'another-document'
        delta = compare_exports(raw(before),raw(after),'fictional')
        self.assertFalse(delta['wholeExportUnchanged'])
        self.assertTrue(delta['currentSubjectRowsUnchanged'])
