"""Complete proof histories across actual cursors; no Microsoft calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import produce_binary_publication_proof as m
from test_binary_proof_producer import complete_fixture, CompleteTransport


URL = "https://example.invalid/sites/test/_api/web/lists(guid'00000000-0000-4000-8000-000000000001')/items"
NEXT = URL + '?$skiptoken=Paged%3dTRUE%26p_ID%3d100'


def row(i):
    return {'Id': i, 'GUID': 'fictional-row-'+str(i), 'odata.etag': '"opaque-'+str(i)+'"',
        'Summary': 'Preserve the entire recorded text '+str(i)}


class ReadOnly:
    def __init__(self, pages): self.pages=pages; self.calls=[]
    def get_json(self, url): self.calls.append(url); return copy.deepcopy(self.pages[url])


class ProofHistoryPaging(unittest.TestCase):
    def test_complete_single_page_preserves_native_metadata_exactly(self):
        native={'value':[row(1)],'odata.nextLink':None,'odata.metadata':'unchanged native context'}
        self.assertEqual(m.read_history(ReadOnly({URL:native}),URL),native)

    def test_all_103_records_and_original_pages_are_retained(self):
        first={'value':[row(i) for i in range(1,101)], 'odata.nextLink':NEXT}
        last={'value':[row(i) for i in range(101,104)]}
        t=ReadOnly({URL:first,NEXT:last})
        with tempfile.TemporaryDirectory() as directory:
            c=m.Capture(Path(directory)/'capture')
            result=m.read_history(t,URL,c,'assurance')
            self.assertEqual(result['value'],first['value']+last['value'])
            self.assertEqual(t.calls,[URL,NEXT])
            self.assertEqual(json.loads((c.path/'assurance-page1.json').read_bytes()),first)
            self.assertEqual(json.loads((c.path/'assurance-page2.json').read_bytes()),last)
            self.assertNotIn('odata.nextLink',result)

    def test_foreign_collection_filter_projection_and_fragment_refused_before_following(self):
        for link in ['https://foreign.invalid/items?$skiptoken=opaque',
                URL.replace('000000000001','000000000002')+'?$skiptoken=opaque',
                NEXT+'&$filter=Id gt 100', NEXT+'&$select=Id', NEXT+'#fragment',
                URL+'?$top=100', URL+'?$skiptoken=a&$skiptoken=b',
                URL+'?$skiptoken=opaque&$top=10000']:
            with self.subTest(link=link):
                t=ReadOnly({URL:{'value':[row(1)],'odata.nextLink':link}})
                with self.assertRaises(ValueError): m.read_history(t,URL)
                self.assertEqual(t.calls,[URL])

    def test_conflicting_cyclic_and_duplicate_identities_hold(self):
        variants=[{URL:{'value':[row(1)],'nextLink':NEXT,'@nextLink':NEXT+'other'}},
            {URL:{'value':[row(1)],'odata.nextLink':NEXT},NEXT:{'value':[row(2)],'odata.nextLink':NEXT}},
            {URL:{'value':[row(1)],'odata.nextLink':NEXT},NEXT:{'value':[row(1)]}},
            {URL:{'value':[row(1)],'odata.nextLink':NEXT},
                NEXT:{'value':[{**row(2),'GUID':row(1)['GUID'].upper()}]}}]
        for pages in variants:
            with self.subTest(pages=pages):
                with self.assertRaises(ValueError): m.read_history(ReadOnly(pages),URL)

    def test_caller_pagination_query_and_malformed_native_identity_refused(self):
        t=ReadOnly({})
        with self.assertRaises(ValueError): m.read_history(t,URL+'?$top=5000')
        self.assertEqual(t.calls,[])
        with self.assertRaises(ValueError): m.read_history(ReadOnly({URL:{'value':[{'Id':1}]}}),URL)

    def test_row_bound_holds_instead_of_returning_favorable_subset(self):
        with self.assertRaisesRegex(ValueError,'proof bound'):
            m.read_history(ReadOnly({URL:{'value':[row(i) for i in range(1,5002)]}}),URL)

    def test_protected_frame_detects_a_changed_record_beyond_first_page(self):
        b,definition,frame,raw,_=complete_fixture()
        originals=copy.deepcopy(frame['assuranceHistory']['value'])
        extras=[row(i) for i in range(1001,1101)]
        frame['assuranceHistory']['value']=extras+originals
        b['frame']['assuranceHistory']['expected']=copy.deepcopy(frame['assuranceHistory'])
        url=b['frame']['assuranceHistory']['url'];next_url=url+'?$skiptoken=actual-native-cursor'
        for changed in [False,True]:
            t=CompleteTransport(b,definition,frame,raw);base_read=t.get_json
            def read(target):
                if target==url:return {'value':copy.deepcopy(extras),'odata.nextLink':next_url}
                if target==next_url:
                    values=copy.deepcopy(originals)
                    if changed:values[-1]['Summary']='Changed after the reviewed snapshot'
                    return {'value':values}
                return base_read(target)
            t.get_json=read
            with tempfile.TemporaryDirectory() as directory:
                c=m.Capture(Path(directory)/'capture')
                if changed:
                    with self.assertRaisesRegex(ValueError,'Protected frame changed'):
                        m.read_frame(b,t,c,'before')
                else:
                    actual=m.read_frame(b,t,c,'before')
                    self.assertEqual(len(actual['assuranceHistory']['value']),104)
                    self.assertEqual(actual['assuranceHistory'],b['frame']['assuranceHistory']['expected'])


if __name__=='__main__':unittest.main()
