"""Evaluate emitted parity checks against actual bytes and independently sized metadata."""
import base64
import copy
import unittest

from build_reusable_publication_route import parity_checks, metadata_checks, download_witness_checks
from test_prepared_closure_check import Expressions


def parity(draft, issued, draft_length=None, issued_length=None):
    ev = Expressions(bodies={
        'NativeParity_read_draft': {'$content': base64.b64encode(draft).decode()},
        'NativeParity_read_issued': {'$content': base64.b64encode(issued).decode()},
        'Read_issued': {'Length': len(issued) if issued_length is None else issued_length},
    }, outputs={'Native_prepared_revision': {'preparedRevision': {'file': {
        'Length': len(draft) if draft_length is None else draft_length}}}})
    return ev.evaluate('@and(' + ','.join(parity_checks()) + ')')


class ReusablePublicationTests(unittest.TestCase):
    def test_download_witness_uses_scope_hash_when_source_is_metadata_only(self):
        file = {'UniqueId': 'draft-id', 'ETag': 'token', 'nativeVersion': '2.0',
                'Length': 17, 'DocumentReference': 'https://example.invalid/draft.docx'}
        proof = {'scope': {'DocumentSHA256': 'actual-hash'}, 'source': file,
                 'issued': {**file, 'UniqueId': 'issued-id', 'SHA256': 'actual-hash'}, 'downloadEvidence': {}}
        for label in ('source', 'issued'):
            snapshot = {k: v for k, v in proof[label].items() if k != 'SHA256'}
            proof['downloadEvidence'][label] = {'SHA256': 'actual-hash', 'Length': 17,
                'metadataBefore': snapshot, 'metadataAfter': copy.deepcopy(snapshot)}
        expression = '@and(' + ','.join(download_witness_checks()) + ')'
        self.assertNotIn('SHA256', proof['source'])
        self.assertTrue(Expressions(outputs={'Parse_binary_proof': proof}).evaluate(expression))
        for label in ('source', 'issued'):
            for frame in ('metadataBefore', 'metadataAfter'):
                changed = copy.deepcopy(proof)
                changed['downloadEvidence'][label][frame]['ETag'] = 'wrong'
                self.assertFalse(Expressions(outputs={'Parse_binary_proof': changed}).evaluate(expression))
        proof['downloadEvidence']['source']['SHA256'] = 'wrong'
        self.assertFalse(Expressions(outputs={'Parse_binary_proof': proof}).evaluate(expression))

    def test_equal_actual_bytes_cover_all_base64_padding_lengths(self):
        for size in (1, 2, 3, 4, 31, 32, 33, 27262):
            content = bytes(i % 256 for i in range(size))
            with self.subTest(size=size): self.assertTrue(parity(content, content))

    def test_different_bytes_equal_length_or_equal_truncation_cannot_pass(self):
        self.assertFalse(parity(b'PK\x03\x04prepared', b'PK\x03\x04changed!'))
        self.assertFalse(parity(b'PK\x03', b'PK\x03', draft_length=4, issued_length=4))
        self.assertFalse(parity(b'PK\x03\x04', b'PK\x03\x04', draft_length=3))
        self.assertFalse(parity(b'', b''))

    def test_missing_binary_envelope_refuses_without_a_length_expression_error(self):
        ev = Expressions(bodies={'NativeParity_read_draft': {}, 'NativeParity_read_issued': {},
            'Read_issued': {'Length': 4}}, outputs={'Native_prepared_revision': {'preparedRevision': {'file': {'Length': 4}}}})
        self.assertFalse(ev.evaluate('@and(' + ','.join(parity_checks()) + ')'))

    def test_each_dynamic_case_version_identity_and_hash_relationship_is_retained(self):
        scope = {'CaseUID': 'FICTIONAL-case', 'DocumentReference': 'https://example.invalid/site/draft.docx',
                 'ReviewedVersionRef': 'draft@2', 'DocumentSHA256': 'hash'}
        source = {'UniqueId': 'draft-id', 'ETag': 'draft-token', 'nativeVersion': '2.0',
                  'Length': 123, 'DocumentReference': scope['DocumentReference']}
        issued = {'UniqueId': 'issued-id', 'ETag': 'issued-token', 'UIVersionLabel': '1.0', 'Length': 123}
        proof = {'kind': 'local-downloaded-binary-parity-v1', 'independentByteParity': True,
                 'publicationEventCreated': False, 'scope': scope, 'source': source,
                 'issued': {'UniqueId': 'issued-id', 'ETag': 'issued-token', 'nativeVersion': '1.0',
                            'Length': 123, 'DocumentReference': 'https://example.invalid/site/issued.docx', 'SHA256': 'hash'}}
        expression = '@and(' + ','.join(metadata_checks('https://example.invalid/site')) + ')'
        outputs = {'Parse_binary_proof': copy.deepcopy(proof),
                   'Native_prepared_revision': {'preparedRevision': {'scope': scope, 'file': source}},
                   'Issued_path': '/site/issued.docx'}
        self.assertTrue(Expressions({'Read_issued': issued}, outputs).evaluate(expression))
        for group in ('scope', 'source', 'issued'):
            for key in proof[group]:
                changed = copy.deepcopy(outputs)
                changed['Parse_binary_proof'][group][key] = 'wrong'
                with self.subTest(group=group, key=key):
                    self.assertFalse(Expressions({'Read_issued': issued}, changed).evaluate(expression))
        for key in ('kind', 'independentByteParity', 'publicationEventCreated'):
            changed = copy.deepcopy(outputs); changed['Parse_binary_proof'][key] = 'wrong'
            with self.subTest(key=key):
                self.assertFalse(Expressions({'Read_issued': issued}, changed).evaluate(expression))


if __name__ == '__main__': unittest.main()
