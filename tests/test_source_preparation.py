import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppg_source_preparation import prepare,evaluate,read_file,verify_ingestion
from ppg_evidence_cli import EvidenceError,digest,extract
from test_evidence_cli import config,docx


class SourcePreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.input=self.root/'input';self.input.mkdir();self.output=self.root/'prepared'
        self.raw=b'FICTIONAL reference\nThe interval is 12 months.\n';(self.input/'source.txt').write_bytes(self.raw)
        self.job={'schemaVersion':1,'preparationId':'source-test-r1','sources':[{'sourceId':'edition-one','file':'source.txt','sha256':digest(self.raw),'expectedTextSHA256':digest(self.raw),'authorityLabel':'captured-reference-unconfirmed','originalReference':'fictional source','originalVersionRef':'edition 1','sourceEdition':'edition 1','evaluationNeedle':'12 months'}]}
        self.job_file=self.root/'job.json';self.save()
    def save(self):self.job_file.write_text(json.dumps(self.job))
    def test_preparation_preserves_original_and_metadata(self):
        r=prepare(self.job_file,self.input,self.output);self.assertEqual(r['preparedSources'],1)
        m=json.loads((self.output/'manifest.json').read_text());s=m['sources'][0]
        self.assertEqual((self.output/'sources'/s['name']).read_bytes(),self.raw);self.assertEqual(s['originalFileName'],'source.txt');self.assertEqual(s['originalVersionRef'],'edition 1');self.assertEqual((self.input/'source.txt').read_bytes(),self.raw)
        with self.assertRaises(EvidenceError):prepare(self.job_file,self.input,self.output)
    def test_hash_and_extraction_fail_without_manifest(self):
        for key in ['sha256','expectedTextSHA256']:
            with self.subTest(key=key):
                self.job['sources'][0][key]='0'*64;self.save();out=self.root/key
                with self.assertRaises(EvidenceError):prepare(self.job_file,self.input,out)
                self.assertFalse((out/'manifest.json').exists());self.assertTrue((out/'failure.json').exists())
                self.job['sources'][0][key]=digest(self.raw)
    def test_provenance_and_traversal_guard(self):
        self.job['sources'][0]['originalVersionRef']='';self.save()
        with self.assertRaises(EvidenceError):prepare(self.job_file,self.input,self.output)
        self.job['sources'][0]['originalVersionRef']='edition 1';self.job['sources'][0]['file']='../job.json';self.save()
        with self.assertRaisesRegex(EvidenceError,'unsafe_input_path'):prepare(self.job_file,self.input,self.output)
    def test_fictional_docx_is_copied_without_body_generation(self):
        raw=docx();(self.input/'source.docx').write_bytes(raw);s=self.job['sources'][0];s.update(file='source.docx',sha256=digest(raw),expectedTextSHA256=digest(extract(raw,'source.docx')[0].encode()));self.save()
        r=prepare(self.job_file,self.input,self.output);self.assertFalse(r['wordBodyGenerationPerformed'])
    def bundle(self):
        prepare(self.job_file,self.input,self.output);m=json.loads((self.output/'manifest.json').read_text());e=m['sources'][0]
        bundle=self.root/'bundle';bundle.mkdir();(bundle/'edition-one.raw').write_bytes(self.raw)
        path=config()['folder']+'/'+e['name'];native={'UniqueId':'11111111-1111-4111-8111-111111111111','Name':e['name'],'Length':str(len(self.raw)),'ETag':'"1"','MajorVersion':'1','MinorVersion':'0','TimeLastModified':'2026-10-22T00:00:00Z','ServerRelativeUrl':path}
        s={'sourceId':'edition-one','status':'retrieved','nativeUniqueId':native['UniqueId'],'canonicalUrl':'https://example.sharepoint.com'+path,'nativeVersionRef':'1.0 "1"','nativePin':native,'retrievedAtUtc':'2026-10-22T00:00:00Z','sha256':digest(self.raw),'binarySHA256':digest(self.raw),'text':self.raw.decode(),'lineMap':[{'sourceLine':1},{'sourceLine':2}],'extraction':'utf8-v1','rawFile':'edition-one.raw','authorityLabel':'captured-reference-unconfirmed','searchVisibility':'not-returned-by-this-query; indexing-unconfirmed'}
        (bundle/'sources.json').write_text(json.dumps([s]));(bundle/'run.json').write_text(json.dumps({'scope':'https://example.sharepoint.com/sites/ppg/evidence/','searchStatus':'no-indexed-matches'}))
        publication={'manifestSHA256':digest((self.output/'manifest.json').read_bytes()),'preparationId':m['preparationId'],'files':[{'name':e['name'],'pin':{'UniqueId':native['UniqueId'],'ETag':native['ETag']}}]}
        return bundle,publication
    def test_offline_evaluation_has_no_native_promotion_and_search_miss_is_explicit(self):
        bundle,p=self.bundle();r=evaluate(self.output,bundle,config(),p,live=False)
        self.assertTrue(r['deterministicChecksPassed']);self.assertFalse(r['sourcePreparationQualified']);self.assertFalse(r['searchDiscoveryObserved']);self.assertFalse(r['conversationalRetrievalQualified']);self.assertGreater(len(r['checks']),10)
    def test_failed_native_extraction_cannot_pass_integrity(self):
        bundle,p=self.bundle();(bundle/'sources.json').write_text(json.dumps([{'sourceId':'edition-one','status':'unsupported','searchVisibility':'not-returned-by-this-query; indexing-unconfirmed'}]));r=evaluate(self.output,bundle,config(),p,live=False);self.assertFalse(r['deterministicChecksPassed'])
    def test_prepared_copy_change_fails_roundtrip(self):
        bundle,p=self.bundle();m=json.loads((self.output/'manifest.json').read_text());(self.output/'sources'/m['sources'][0]['name']).write_bytes(b'changed');r=evaluate(self.output,bundle,config(),p,live=False);self.assertFalse(r['deterministicChecksPassed'])
    def metadata_copy(self,change='allowed'):
        original=io.BytesIO();native=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(docx())) as source,zipfile.ZipFile(original,'w') as a,zipfile.ZipFile(native,'w') as b:
            for name in source.namelist():
                raw=source.read(name);a.writestr(name,raw);b.writestr(name,raw.replace(b'12 months',b'6 months') if change=='body' else raw)
            schema='<m:contentTypeSchema xmlns:m="http://schemas.microsoft.com/office/2006/metadata/contentType" xmlns:a="http://schemas.microsoft.com/office/2006/metadata/properties/metaAttributes" a:versionID="'+('a'*32)+'"><field name="Title"/></m:contentTypeSchema>'
            a.writestr('customXml/item1.xml',schema)
            updated=schema.replace('a'*32,'b'*32)
            if change=='schema-field':updated=updated.replace('Title','PolicyText')
            b.writestr('customXml/item1.xml',updated)
            item='<d:datastoreItem xmlns:d="http://schemas.openxmlformats.org/officeDocument/2006/customXml" d:itemID="{11111111-1111-4111-8111-111111111111}"/>'
            a.writestr('customXml/itemProps1.xml',item);b.writestr('customXml/itemProps1.xml',item.replace('11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222'))
        return original.getvalue(),native.getvalue()
    def test_only_qualified_schema_attributes_accept_native_ingestion(self):
        a,b=self.metadata_copy();p=verify_ingestion(a,b,'source.docx','sharepoint-schema-attributes-v1')
        self.assertTrue(p['supportedTextAndLocatorsEqual']);self.assertTrue(p['otherPackagePartsByteExact']);self.assertNotEqual(p['originalSHA256'],p['nativeSHA256'])
        with self.assertRaises(EvidenceError):verify_ingestion(a,b,'source.docx')
    def test_body_and_other_schema_changes_are_refused(self):
        for change in ['body','schema-field']:
            with self.subTest(change=change):
                a,b=self.metadata_copy(change)
                with self.assertRaises(EvidenceError):verify_ingestion(a,b,'source.docx','sharepoint-schema-attributes-v1')


if __name__=='__main__':unittest.main()
