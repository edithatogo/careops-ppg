"""Bounded release source integrity, private hydration and preservation checks."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts.ppg_release_source import verify, materialise


class ReleaseSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'; self.source.mkdir()
        self.private = self.root / '.local'; self.private.mkdir()
        self.settings = self.private / 'bindings.json'
        self.output = self.private / 'recovered'
        self.token = '__PPG_BINDING_00001__'
        self.raw = b'<Root>__PPG_BINDING_00001__</Root>\r\n'
        (self.source / 'member.xml.in').write_bytes(self.raw)
        self.manifest = {'schemaVersion': 1, 'releaseId': 'fictional-1', 'solutionVersion': '0.1.0.0',
            'files': [{'template': 'member.xml.in', 'target': 'member.xml',
                       'sha256': hashlib.sha256(self.raw).hexdigest()}],
            'bindings': {self.token: {'kind': 'fictional', 'private': True}}}
        self.save()
        self.settings.write_text(json.dumps({'schemaVersion': 1, 'releaseId': 'fictional-1',
                                            'values': {self.token: 'fictional'}}))

    def save(self):
        (self.source / 'release.json').write_text(json.dumps(self.manifest))

    def test_exact_bytes_crlf_and_input_preservation(self):
        before = self.settings.read_bytes()
        result = materialise(self.source, self.settings, self.output)
        self.assertEqual((self.output / 'member.xml').read_bytes(), b'<Root>fictional</Root>\r\n')
        self.assertEqual((self.source / 'member.xml.in').read_bytes(), self.raw)
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertFalse(result['deploymentOrRuntimeAccepted'])
        self.assertEqual(result['nativeWrites'], 0)

    def test_changed_source_and_extra_file_refused(self):
        (self.source / 'member.xml.in').write_bytes(self.raw + b' ')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): verify(self.source)
        (self.source / 'member.xml.in').write_bytes(self.raw)
        (self.source / 'unexpected.txt').write_text('fictional')
        with self.assertRaisesRegex(ValueError, 'Unexpected'): verify(self.source)

    def test_missing_wrong_release_and_extra_bindings_refused_before_output(self):
        for value in [{'schemaVersion': 1, 'releaseId': 'other', 'values': {self.token: 'x'}},
                      {'schemaVersion': 1, 'releaseId': 'fictional-1', 'values': {}},
                      {'schemaVersion': 1, 'releaseId': 'fictional-1', 'values': {self.token: 'x', 'extra': 'x'}}]:
            self.settings.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'incomplete'): materialise(self.source, self.settings, self.output)
            self.assertFalse(self.output.exists())

    def test_existing_output_and_nonprivate_bindings_never_overwritten(self):
        self.output.mkdir(); original = self.output / 'human-edit'; original.write_text('retain')
        with self.assertRaisesRegex(ValueError, 'new private'): materialise(self.source, self.settings, self.output)
        self.assertEqual(original.read_text(), 'retain')
        public = self.root / 'public.json'; public.write_bytes(self.settings.read_bytes())
        with self.assertRaisesRegex(ValueError, 'stay under'): materialise(self.source, public, self.private / 'other')

    def test_symlink_and_traversal_refused(self):
        original = self.source / 'member.xml.in'; original.unlink(); original.symlink_to(self.settings)
        with self.assertRaisesRegex(ValueError, 'unsafe'): verify(self.source)
        original.unlink(); original.write_bytes(self.raw)
        self.manifest['files'][0]['target'] = '../outside.xml'; self.save()
        with self.assertRaisesRegex(ValueError, 'Unsafe'): materialise(self.source, self.settings, self.output)
        self.assertFalse(self.output.exists())

    def test_private_path_binding_and_collisions_refused(self):
        self.manifest['files'][0]['target'] = self.token; self.save()
        value = json.loads(self.settings.read_text()); value['values'][self.token] = '../outside.xml'
        self.settings.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Unsafe'): materialise(self.source, self.settings, self.output)
        self.assertFalse(self.output.exists())
        value['values'][self.token] = 'member.xml'; self.settings.write_text(json.dumps(value))
        self.manifest['files'].append(dict(self.manifest['files'][0], template='second.xml.in', target='MEMBER.xml'))
        (self.source / 'second.xml.in').write_bytes(self.raw); self.save()
        with self.assertRaisesRegex(ValueError, 'collide'): materialise(self.source, self.settings, self.output)
        self.assertFalse(self.output.exists())

    def test_binding_declarations_cannot_embed_private_values(self):
        self.manifest['bindings'][self.token]['value'] = 'private'; self.save()
        with self.assertRaisesRegex(ValueError, 'declaration'): verify(self.source)

    def test_managed_flag_only_changes_selected_private_build(self):
        raw = b'<ImportExportXml>\r\n<Managed>0</Managed>\r\n</ImportExportXml>\r\n'
        (self.source / 'member.xml.in').write_bytes(raw)
        self.manifest['files'][0].update(target='Other/Solution.xml', sha256=hashlib.sha256(raw).hexdigest())
        self.manifest['bindings'] = {}; self.save()
        v = json.loads(self.settings.read_text()); v['values'] = {}; self.settings.write_text(json.dumps(v))
        materialise(self.source, self.settings, self.output, package_type='Managed')
        self.assertEqual((self.output / 'Other/Solution.xml').read_bytes(), raw.replace(b'>0<', b'>1<'))
        self.assertEqual((self.source / 'member.xml.in').read_bytes(), raw)

    def test_email_capable_definition_refused_before_output(self):
        raw = b'{"actions":{"send":{"type":"Http","inputs":{"uri":"https://example.invalid/sendMail"}}}}'
        (self.source / 'member.xml.in').write_bytes(raw)
        self.manifest['files'][0].update(target='Workflows/fictional.json', sha256=hashlib.sha256(raw).hexdigest())
        self.manifest['bindings'] = {}; self.save()
        v = json.loads(self.settings.read_text()); v['values'] = {}; self.settings.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError, 'Email-capable'):
            materialise(self.source, self.settings, self.output)
        self.assertFalse(self.output.exists())

    def test_git_clean_checkout_preserves_template_bytes(self):
        import subprocess
        repo = self.root / 'git-source'; repo.mkdir()
        source = repo / 'solutions/ExamplePPGWorkbench/v0.1.0.0'; source.mkdir(parents=True)
        (repo / '.gitattributes').write_bytes((Path(__file__).resolve().parents[1] / '.gitattributes').read_bytes())
        (source / 'member.xml.in').write_bytes(self.raw)
        (source / 'release.json').write_text(json.dumps(self.manifest))
        def git(*args): return subprocess.check_output(['git', *args], cwd=repo, stderr=subprocess.DEVNULL)
        git('init', '-q'); git('add', '.gitattributes', 'solutions')
        git('-c', 'core.hooksPath=/dev/null', '-c', 'user.name=Fictional',
            '-c', 'user.email=fictional@example.invalid', 'commit', '-qm', 'fixture')
        clone = self.root / 'clean-clone'
        subprocess.run(['git', 'clone', '-q', str(repo), str(clone)], check=True, capture_output=True)
        recovered = clone / 'solutions/ExamplePPGWorkbench/v0.1.0.0'
        self.assertEqual((recovered / 'member.xml.in').read_bytes(), self.raw)
        materialise(recovered, self.settings, self.output)
        self.assertEqual((self.output / 'member.xml').read_bytes(), b'<Root>fictional</Root>\r\n')

    def test_existing_cli_receipt_preserved_without_creating_output(self):
        import subprocess
        import sys
        receipt = self.output.parent / (self.output.name + '-receipt.json')
        receipt.write_text('retained prior evidence')
        script = Path(__file__).resolve().parents[1] / 'scripts/ppg_release_source.py'
        result = subprocess.run([sys.executable, str(script), '--source', str(self.source),
                                 '--bindings', str(self.settings), '--output', str(self.output)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(receipt.read_text(), 'retained prior evidence')
        self.assertFalse(self.output.exists())

    def test_invalid_graph_refused_before_any_output(self):
        (self.source/'member.xml.in').unlink()
        raw = json.dumps({'properties':{'definition':{'triggers':{'manual':{'type':'Request'}},'actions':{'one':{'type':'Compose','inputs':self.token,'runAfter':{'absent':['Succeeded']}}}},'connectionReferences':{}}}).encode()
        (self.source/'flow.json.in').write_bytes(raw)
        self.manifest['files']=[{'template':'flow.json.in','target':'Workflows/Fictional-00000000-0000-4000-8000-000000000001.json','sha256':hashlib.sha256(raw).hexdigest()}]
        self.save()
        with self.assertRaisesRegex(ValueError,'Invalid workflow structure'):
            materialise(self.source,self.settings,self.output)
        self.assertFalse(self.output.exists())

    def test_duplicate_binding_key_is_refused(self):
        self.settings.write_text('{"schemaVersion":1,"schemaVersion":1}')
        with self.assertRaisesRegex(ValueError,'duplicate_json_key'):
            materialise(self.source,self.settings,self.output)
        self.assertFalse(self.output.exists())

    def test_sealed_external_script_is_verified_but_not_hydrated(self):
        raw=b'function main() { return "fictional"; }\n'
        script=self.source/'script.ts'; script.write_bytes(raw)
        self.manifest['externalDependencies']=[{'path':'script.ts','role':'office-script','sha256':hashlib.sha256(raw).hexdigest()}]
        self.save()
        self.assertEqual(verify(self.source),self.manifest)
        result=materialise(self.source,self.settings,self.output)
        self.assertEqual(set(result['files']),{'member.xml'})
        self.assertFalse((self.output/'script.ts').exists())
        self.assertEqual(script.read_bytes(),raw)
        self.assertTrue(any(c['check']=='external_dependency_hash' and c['outcome']=='pass' for c in result['assurance']['checks']))

    def test_external_sources_fail_before_output_on_missing_drift_or_collision(self):
        raw=b'fictional script'
        script=self.source/'script.ts'; script.write_bytes(raw)
        entry={'path':'script.ts','role':'office-script','sha256':hashlib.sha256(raw).hexdigest()}
        for records in [[dict(entry,sha256='0'*64)],[dict(entry,path='missing.ts')],[entry,entry],
                        [dict(entry,path='member.xml.in')],[dict(entry,path='release.json')],
                        [dict(entry,path='../outside.ts')],[entry,dict(entry,path='SCRIPT.ts')]]:
            with self.subTest(records=records):
                self.manifest['externalDependencies']=records; self.save()
                with self.assertRaises(ValueError):materialise(self.source,self.settings,self.output)
                self.assertFalse(self.output.exists())
