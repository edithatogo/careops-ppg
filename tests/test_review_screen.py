import copy
import unittest
from scripts.ppg_review_screen import digest, screen, identifiers


def source(text, sha='a'*64):
    return {'text':text,'textSha256':digest(text),'sourceSha256':sha}


class ReviewScreen(unittest.TestCase):
    def fixture(self):
        text='Shared words one two three four five six seven eight nine ten eleven twelve.'
        catalogue={'sourceSha256':'c'*64,'catalogueCount':2,'records':[
            {'documentUID':'one','sourceDocumentId':'TEST-Proc-1-V2-01/26','title':'Fictional'},
            {'documentUID':'two','sourceDocumentId':'TEST-Proc-2-V1-01/26','title':'Missing'}]}
        other='Document Number: TEST-Proc-1-V1-01/25\n'+text
        return source(text), catalogue, [source(other,'b'*64)]

    def test_edition_conflict_preserved_and_passages_reproducible(self):
        subject,catalogue,sources=self.fixture();before=copy.deepcopy(sources)
        result=screen(subject,catalogue,sources)
        self.assertEqual(result['records'][0]['coverage'],'other_edition_candidate')
        self.assertEqual(result['records'][1]['coverage'],'metadata_only')
        self.assertFalse(result['requestedEditionVerified'])
        self.assertIsNone(result['humanDecision'])
        pair=result['corpus'][0]['literalOverlapCandidates'][0]
        for key,original in [('subject',subject),('comparator',sources[0])]:
            e=pair[key];self.assertEqual(e['passage'],original['text'][e['start']:e['end']])
        self.assertEqual(before,sources)

    def test_reference_is_not_own_identity(self):
        self.assertEqual(identifiers('References\nTEST-Proc-1-V2-01/26'),[])
        self.assertEqual(identifiers('Cover page\fDocument Number: TEST-Proc-1-V2-01/26'),[])
        subject,catalogue,sources=self.fixture()
        sources=[source('References: TEST-Proc-1-V2-01/26')]
        self.assertEqual(screen(subject,catalogue,sources)['records'][0]['coverage'],'metadata_only')

    def test_tampered_text_and_incomplete_ledger_refused(self):
        subject,catalogue,sources=self.fixture();sources[0]['text']+=' changed'
        with self.assertRaises(ValueError):screen(subject,catalogue,sources)
        subject,catalogue,sources=self.fixture();catalogue['catalogueCount']=3
        with self.assertRaises(ValueError):screen(subject,catalogue,sources)

    def test_ambiguous_header_remains_unbound(self):
        subject,catalogue,sources=self.fixture()
        t=sources[0]['text']+'\nDocument Number: TEST-Proc-2-V1-01/26'
        result=screen(subject,catalogue,[source(t)])
        self.assertEqual(result['records'][0]['coverage'],'metadata_only')
        self.assertEqual(result['sourceCount'],1)

    def test_common_and_reference_text_retained_outside_priority_leads(self):
        subject,catalogue,_=self.fixture()
        sources=[source(subject['text'],hex(i)[2:].zfill(64)) for i in range(1,7)]
        result=screen(subject,catalogue,sources)
        self.assertEqual(len(result['corpus'][0]['literalOverlapCandidates']),0)
        self.assertTrue(result['corpus'][0]['commonTextMatches'])

    def test_sampled_ocr_does_not_bind_a_first_page_identity(self):
        subject,catalogue,sources=self.fixture();sources[0]['textCoverage']='sampled_ocr'
        result=screen(subject,catalogue,sources)
        self.assertEqual(result['records'][0]['coverage'],'metadata_only')
        self.assertEqual(result['corpus'][0]['textCoverage'],'sampled_ocr')

    def test_matching_edition_does_not_hide_other_retained_editions(self):
        subject,catalogue,sources=self.fixture()
        sources.append(source('Document Number: TEST-Proc-1-V2-01/26\nMore text','c'*64))
        row=screen(subject,catalogue,sources)['records'][0]
        self.assertEqual(row['coverage'],'matching_catalogue_identifier')
        self.assertEqual(row['matchingIdentifierSourceIndexes'],[1])
        self.assertEqual(row['otherEditionSourceIndexes'],[0])
        self.assertEqual(row['sourceIndexes'],[1,0])
