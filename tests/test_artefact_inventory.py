"""Inventory provenance, privacy boundaries and copied-fixture recovery."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import ppg_artefact_inventory as module
from ppg_artefact_inventory import inventory, exercise_recovery
from ppg_workspace import validate


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.outer=Path(self.temp.name);self.root=self.outer/'repo';self.root.mkdir()
        subprocess.run(['git','init','-q'],cwd=self.root,check=True,capture_output=True)
        (self.root/'config').mkdir();(self.root/'docs').mkdir()
        (self.root/'docs/artefact-inventory-recovery.md').write_text('## Local Tools\nRecover into a new target only.\n')
        (self.root/'source.txt').write_text('Fictional source only.\n')
        self.manifest={'schemaVersion':1,'principles':['explicit-authority'],
          'capabilities':[dict(key='fixture',purpose='Fictional',lifecycle='pilot',executionMode='local-manual',responsibleRole='Existing owner',resources=['fixture-artifact'],dependencies=[],acceptanceCriteria=['No original changes'])],
          'artefacts':[dict(key='fixture-artifact',capabilityKey='fixture',type='file',resourceRef='fixtureRef',location='local-only',provenanceRef='fictional',contentStatus='fictional')],
          'surfaces':[], 'statusPolicy':copy.deepcopy(json.loads((ROOT/'config/workspace.example.json').read_text())['statusPolicy']),
          'management':[dict(capabilityKey='fixture',maintainerLane='Existing writer',environmentAlias='local',sourcePaths=['source.txt'],deploymentMethod='Local copy',recoverySection='local-tools',receiptRoots=['.local/receipts'],runtimeState='unknown',connectionDependencies=[])]}
        self.save()

    def save(self):
        (self.root/'config/workspace-manifest.json').write_text(json.dumps(self.manifest))

    def test_source_hashes_owner_recovery_and_membership_scope(self):
        original=(self.root/'source.txt').read_bytes();r=inventory(self.root)
        self.assertEqual(r['sourceSHA256']['source.txt'],hashlib.sha256(original).hexdigest())
        self.assertEqual(r['artefactCount'],1)
        self.assertEqual(r['artefacts'][0]['solutionMembership'],'not-applicable')
        self.assertEqual(r['coverage']['fixture']['localReceipts'][0]['status'],'missing')
        self.assertFalse(r['acceptedDeploymentOrRecovery'])
        self.assertEqual(r['nativeWrites'],0)
        self.assertEqual((self.root/'source.txt').read_bytes(),original)
        for kind in ['native-flow','future-unclassified-component']:
            self.manifest['artefacts'][0]['type']=kind;self.save()
            r=inventory(self.root)
            self.assertEqual(r['unknownSolutionMembershipCount'],1)
            self.assertIsNone(r['artefacts'][0]['solutionEvidenceAtUtc'])

    def test_old_hosted_manifest_valid_but_not_implicitly_managed(self):
        self.manifest.pop('management');self.save()
        self.assertTrue(validate(self.manifest))
        with self.assertRaises(ValueError):inventory(self.root)

    def test_missing_duplicate_sources_and_runbook_sections_refused(self):
        base=copy.deepcopy(self.manifest)
        for mutate in [lambda m:m['management'].append(m['management'][0]),
                       lambda m:m['management'][0].update(sourcePaths=['missing.txt']),
                       lambda m:m['management'][0].update(recoverySection='missing'),
                       lambda m:m['management'][0].update(sourcePaths=['.local/receipt.json']),
                       lambda m:m['management'][0].update(sourcePaths=['.env']),
                       lambda m:m['management'][0].update(sourcePaths=['credentials.pem'])]:
            self.manifest=copy.deepcopy(base);mutate(self.manifest);self.save()
            with self.assertRaises(ValueError):inventory(self.root)

    def test_symlink_source_and_traversal_receipts_refused(self):
        (self.outer/'outside.txt').write_text('Fictional outside root')
        (self.root/'source.txt').unlink();(self.root/'source.txt').symlink_to(self.outer/'outside.txt')
        with self.assertRaises(ValueError):inventory(self.root)
        (self.root/'source.txt').unlink();(self.root/'source.txt').write_text('Fictional')
        self.manifest['management'][0]['receiptRoots']=['../outside'];self.save()
        with self.assertRaises(ValueError):inventory(self.root)

    def test_receipt_sampling_is_bounded_hash_only_and_explicit(self):
        directory=self.root/'.local/receipts';directory.mkdir(parents=True)
        for i in range(202):(directory/f'{i:03}.json').write_text('{"privateNote":"FICTIONAL do not export contents"}')
        result=inventory(self.root);receipt=result['coverage']['fixture']['localReceipts'][0]
        self.assertTrue(receipt['truncated']);self.assertEqual(len(receipt['sampledFiles']),200)
        self.assertEqual(receipt['status'],'present-unverified')
        self.assertNotIn('privateNote',json.dumps(result))

    def test_directory_sources_exclude_untracked_generated_files(self):
        folder=self.root/'src';folder.mkdir()
        (folder/'source.txt').write_text('Fictional tracked source')
        (folder/'generated.txt').write_text('Fictional ignored build')
        subprocess.run(['git','add','src/source.txt'],cwd=self.root,check=True,capture_output=True)
        self.manifest['management'][0]['sourcePaths']=['src'];self.save()
        result=inventory(self.root)
        self.assertEqual(set(result['sourceSHA256']),{'src/source.txt'})

    def test_source_change_during_inventory_is_not_accepted(self):
        original=module.sha; changed=False
        def changing(path):
            nonlocal changed
            value=original(path)
            if path.name=='source.txt' and not changed:
                changed=True;path.write_text('Fictional concurrent update')
            return value
        with patch.object(module,'sha',side_effect=changing):
            with self.assertRaisesRegex(ValueError,'Source changed'):inventory(self.root)

    def fixture_root(self):
        shutil.copytree(ROOT/'templates/recovery',self.root/'templates/recovery')
        return self.root

    def test_copied_recovery_reads_export_and_preserves_edited_original(self):
        root=self.fixture_root();output=self.root/'.local/exercise'
        r=exercise_recovery(output,root)
        self.assertTrue(r['identityHashAndLinksVerified']);self.assertTrue(r['editedOriginalPreserved'])
        self.assertFalse(r['nativeRestorePerformed'])
        before=(output/'original/draft.txt').read_bytes()
        self.assertIn(b'FICTIONAL human edit',before)
        self.assertNotEqual(before,(output/'recovered/draft.txt').read_bytes())
        self.assertEqual(json.loads((output/'recovered/record.json').read_text())['version'],'fixture-v1')
        with self.assertRaises(FileExistsError):exercise_recovery(output,root)
        self.assertEqual((output/'original/draft.txt').read_bytes(),before)

    def test_bad_fixture_hash_identity_and_escaping_paths_stop_before_output(self):
        root=self.fixture_root();file=root/'templates/recovery/fictional-record.json';base=json.loads(file.read_text())
        for mutate in [lambda m:m.update(fictionalOnly=False),
                       lambda m:m.update(caseUID='operational-case'),
                       lambda m:m.update(sourceRef='https://example.invalid/operational'),
                       lambda m:m['draftVersions'][0].update(version='fixture-v2'),
                       lambda m:m['draftVersions'][0].update(sha256='wrong'),
                       lambda m:m['draftVersions'][0].update(source='../outside.txt')]:
            value=copy.deepcopy(base);mutate(value);file.write_text(json.dumps(value))
            output=root/'.local/not-created'
            with self.assertRaises(ValueError):exercise_recovery(output,root)
            self.assertFalse(output.exists())


class ExportReferenceTests(unittest.TestCase):
    def test_saved_export_requires_declared_logical_names(self):
        expected = {'shared_example': 'fictional_existing_reference'}
        export = {'properties': {'connectionReferences': {'shared_example': {
            'runtimeSource': 'embedded',
            'connection': {'connectionReferenceLogicalName': expected['shared_example']}}}}}
        self.assertTrue(module.verify_exported_references(export, expected))
        for connection in [{}, None, {'connectionReferenceLogicalName': 'different'}]:
            changed = copy.deepcopy(export)
            changed['properties']['connectionReferences']['shared_example']['connection'] = connection
            with self.assertRaises(ValueError):
                module.verify_exported_references(changed, expected)

    def test_runtime_metadata_and_partial_sets_are_not_export_proof(self):
        expected = {'shared_example': 'fictional_existing_reference'}
        for value in [None, {}, {'properties': {'connectionReferences': {}}},
                      {'properties': {'connectionReferences': {'shared_example': {
                          'connectionReferenceLogicalName': expected['shared_example']}}}}]:
            with self.assertRaises(ValueError):
                module.verify_exported_references(value, expected)
        with self.assertRaises(ValueError):
            module.verify_exported_references({}, {})


if __name__=='__main__':unittest.main()
