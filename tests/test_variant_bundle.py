import copy
import hashlib
import io
import json
import unittest
import zipfile

from scripts.ppg_variant_bundle import build_variant_bundle


class VariantBundleTests(unittest.TestCase):
    def setUp(self):
        self.records, self.bodies = [], {}
        for index, content in enumerate((b'first retained text', b'second retained text')):
            body = io.BytesIO()
            with zipfile.ZipFile(body, 'w') as archive:
                archive.writestr('original.txt', content)
            raw = body.getvalue()
            sha = hashlib.sha256(raw).hexdigest()
            self.bodies[sha] = raw
            self.records.append({
                'documentUID': '11111111-1111-4111-8111-111111111111',
                'identityEvidence': {'existingReceipt': 'fictional-' + str(index)},
                'sourceEdition': '3.1', 'sha256': sha, 'bytes': len(raw),
                'sourcePath': '/fictional/source-' + str(index) + '.zip',
                'sourceCapsule': {'member': 'original.txt', 'memberBytes': len(content),
                                  'memberSHA256': hashlib.sha256(content).hexdigest()},
            })

    def test_all_distinct_bytes_and_provenance_survive_without_variant_selection(self):
        before = copy.deepcopy(self.records)
        result = build_variant_bundle(self.records, self.bodies)
        self.assertEqual(self.records, before)
        with zipfile.ZipFile(io.BytesIO(result['bytes'])) as archive:
            self.assertIsNone(archive.testzip())
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest, result['manifest'])
            self.assertEqual(len(archive.namelist()), 3)
            self.assertEqual(manifest['variantOrder'], 'unresolved')
            self.assertIsNone(manifest['canonicalVariant'])
            self.assertFalse(manifest['authorityAsserted'])
            self.assertFalse(manifest['newSourceCapture'])
            for record in manifest['sourceCaptures']:
                self.assertEqual(hashlib.sha256(archive.read(record['bundleMember'])).hexdigest(),
                                 record['sourceCapsule']['memberSHA256'])
                self.assertEqual(record['identityEvidence'], next(r['identityEvidence'] for r in before if r['sha256'] == record['sha256']))

    def test_reversed_input_does_not_create_a_different_revision(self):
        a = build_variant_bundle(self.records, self.bodies)
        b = build_variant_bundle(list(reversed(self.records)), self.bodies)
        self.assertEqual(a['bytes'], b['bytes'])
        self.assertEqual(hashlib.sha256(a['bytes']).hexdigest(), a['sha256'])

    def test_identity_edition_hash_member_and_missing_evidence_fail_closed(self):
        mutations = (
            lambda r: r.update(documentUID='22222222-2222-4222-8222-222222222222'),
            lambda r: r.update(documentUID='bad'),
            lambda r: r.update(identityEvidence=None),
            lambda r: r.update(sourceEdition='3.2'),
            lambda r: r.update(bytes=1),
            lambda r: r['sourceCapsule'].update(memberSHA256='a' * 64),
            lambda r: r['sourceCapsule'].update(member='../original.txt'),
        )
        for mutate in mutations:
            records = copy.deepcopy(self.records)
            mutate(records[0])
            with self.subTest(record=records[0]):
                with self.assertRaises(ValueError):
                    build_variant_bundle(records, self.bodies)
        with self.assertRaises(ValueError):
            build_variant_bundle(self.records, {})
        with self.assertRaises(ValueError):
            build_variant_bundle(self.records, {**self.bodies, 'unused': b'unused'})

    def test_singletons_and_repeated_identical_captures_are_not_fabricated_variants(self):
        with self.assertRaises(ValueError):
            build_variant_bundle(self.records[:1], self.bodies)
        with self.assertRaises(ValueError):
            build_variant_bundle([self.records[0], self.records[0]], self.bodies)

    def test_repeated_original_bytes_keep_every_occurrence_deterministically(self):
        records = copy.deepcopy(self.records)
        bodies = dict(self.bodies)
        extra = copy.deepcopy(records[0])
        with zipfile.ZipFile(io.BytesIO(bodies[extra['sha256']])) as capsule:
            content = capsule.read('original.txt')
        body = io.BytesIO()
        with zipfile.ZipFile(body, 'w') as capsule:
            capsule.writestr('another-name.txt', content)
        raw = body.getvalue()
        extra.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), sourcePath='/fictional/another.zip')
        extra['sourceCapsule']['member'] = 'another-name.txt'
        records.append(extra)
        bodies[extra['sha256']] = raw
        result = build_variant_bundle(records, bodies)
        self.assertEqual(result['bytes'], build_variant_bundle(list(reversed(records)), bodies)['bytes'])
        self.assertEqual(len(result['manifest']['sourceCaptures']), 3)
        with zipfile.ZipFile(io.BytesIO(result['bytes'])) as archive:
            self.assertEqual(len(archive.namelist()), 3)
