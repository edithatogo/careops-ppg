import io
import unittest
from zipfile import ZipFile
from scripts.ppg_word_fallback import package_facts, verify, digest


def doc(text):
    output = io.BytesIO()
    with ZipFile(output, 'w') as z:
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p><w:tbl/></w:body></w:document>')
        z.writestr('word/media/image.bin', b'fictional media')
    return output.getvalue()


class WordFallbackTests(unittest.TestCase):
    def setUp(self):
        self.raw = doc('Purpose')
        self.inv = dict(sourceSha256=digest(self.raw), elements=[dict(elementId='e', kind='p', sourceLocator='word/document.xml#child=0', text='Purpose')], parts=[])
        self.modules = dict(moduleVersion='1', status='proposed', modules=[dict(key='core.purpose', headings=['Purpose']),dict(key='evidence.unmapped', headings=[])])
        self.args = ['fictional', self.inv, self.inv, self.modules, self.raw, self.raw, self.raw, self.raw, dict(originalSourceSha256='original')]

    def test_accounting_and_crosswalk_never_claim_generation_or_authority(self):
        result = verify(*self.args)
        self.assertTrue(result['maintainedWordUnchanged'])
        self.assertTrue(result['inspectionMediaAllRetained'])
        self.assertEqual(result['accountedSourceElements'], 1)
        self.assertEqual(result['candidateModuleCrosswalk'][0]['templateElementIds'], ['e'])
        self.assertIsNone(result['sourceSectionMap'][0]['wordLocator'])
        self.assertFalse(result['generationPerformed'])
        self.assertFalse(result['sourceAndTemplateAuthorityVerified'])
        self.assertFalse(result['completeVisualParityVerified'])

    def test_changed_word_is_preserved_as_change_not_regenerated_or_overwritten(self):
        self.args[6] = doc('Human edit')
        result = verify(*self.args)
        self.assertFalse(result['maintainedWordUnchanged'])
        self.assertEqual(result['maintainedWord']['bodyText'], 'Human edit')
        self.assertFalse(result['wordRewritten'])

    def test_changed_source_or_template_refused(self):
        for index in [4, 5]:
            args = self.args.copy(); args[index] = doc('Changed')
            with self.assertRaises(ValueError): verify(*args)
