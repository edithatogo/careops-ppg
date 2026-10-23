import io
import unittest
from zipfile import ZipFile
from scripts.ppg_manual_review_notes import MARKER, prepare, verify_append


def package(text, header='Preserved header', link='https://example.org/original'):
    stream = io.BytesIO()
    with ZipFile(stream, 'w') as z:
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p></w:body></w:document>')
        z.writestr('word/header1.xml', header)
        z.writestr('word/_rels/document.xml.rels', '<Relationships><Relationship Id="r1" Target="'+link+'" Type="hyperlink" TargetMode="External"/></Relationships>')
    return stream.getvalue()


class ManualReviewNotesTests(unittest.TestCase):
    def test_exact_append_preserves_prior_edit_and_refuses_changed_text(self):
        notes = MARKER+'\nUnresolved question'
        old = package('Saved human edit')
        new = package('Saved human edit'+notes.replace('\n', ''))
        self.assertTrue(verify_append(old, new, notes)['exactPriorTextAndNotes'])
        with self.assertRaisesRegex(ValueError, 'exact append-only'):
            verify_append(old, package('Replaced edit'+notes.replace('\n', '')), notes)
        with self.assertRaisesRegex(ValueError, 'Protected'):
            verify_append(old, package('Saved human edit'+notes.replace('\n', ''), 'Changed header'), notes)

    def test_duplicate_append_refused(self):
        notes = MARKER+'\nQuestion'
        with self.assertRaisesRegex(ValueError, 'exact append-only'):
            verify_append(package('Existing'), package('Existing'+notes.replace('\n', '')*2), notes)

    def test_changed_reviewer_state_refused(self):
        with self.assertRaisesRegex(ValueError, 'Reviewer state changed'):
            prepare({'currentSubjectAnnotations': []}, [{'annotationId':'changed'}], 'https://example.org/pack')

    def test_changed_link_target_refused_even_when_text_is_preserved(self):
        notes = MARKER+'\nQuestion'
        with self.assertRaisesRegex(ValueError, 'link/relationship changed'):
            verify_append(package('Existing'), package('Existing'+notes.replace('\n', ''), link='https://example.org/changed'), notes)
