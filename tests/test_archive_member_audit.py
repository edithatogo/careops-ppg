"""Synthetic archives: exhaustive member identity without false WARC acceptance."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import warnings
from unittest.mock import patch
import zipfile
from ppg_archive_member_audit import audit, audit_warc
import io


class MemberAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'fictional.zip'

    def make(self, entries):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.path, 'w') as z:
                for name, raw in entries:
                    z.writestr(name, raw)

    def test_duplicate_names_distinct_bytes_and_occurrences_survive(self):
        self.make([('same.pdf', b'old'),('same.pdf', b'new'),('../no-extraction.pdf', b'old')])
        result = audit(self.path)
        self.assertEqual(result['memberCount'], 3)
        self.assertEqual(len({x['sha256'] for x in result['members']}), 2)
        self.assertEqual([x['ordinal'] for x in result['members']], [0,1,2])
        self.assertTrue(result['allZipMemberBytesVerified'])
        self.assertFalse((self.path.parent.parent/'no-extraction.pdf').exists())
        self.assertFalse(result['fullOriginalArchiveAcceptance'])

    def test_warc_is_accounted_but_not_mistaken_for_payload_coverage(self):
        self.make([('responses.warc.gz',b'fictional opaque WARC')])
        result = audit(self.path)
        self.assertTrue(result['warcPayloadAuditPending'])
        self.assertFalse(result['fullOriginalArchiveAcceptance'])

    def test_expected_archive_identity_and_limits_fail_closed(self):
        self.make([('large.pdf',b'123456')])
        with self.assertRaisesRegex(ValueError,'identity-mismatch'):
            audit(self.path,'0'*64)
        result = audit(self.path,hashlib.sha256(self.path.read_bytes()).hexdigest(),max_member_bytes=5)
        self.assertTrue(result['expectedIdentityMatched'])
        self.assertFalse(result['allZipMemberBytesVerified'])
        self.assertEqual(result['members'][0]['state'],'unverified-byte-limit')

    def test_corrupt_member_crc_is_an_unverified_entry(self):
        self.make([('document.pdf',b'ORIGINAL')])
        raw=bytearray(self.path.read_bytes())
        offset=30+struct.unpack_from('<H',raw,26)[0]+struct.unpack_from('<H',raw,28)[0]
        raw[offset] ^= 1
        self.path.write_bytes(raw)
        result=audit(self.path)
        self.assertFalse(result['allZipMemberBytesVerified'])
        self.assertEqual(result['members'][0]['state'],'unverified-read-error')

    def test_directory_and_symlink_are_accounted_without_following(self):
        link=zipfile.ZipInfo('link.pdf');link.create_system=3;link.external_attr=0o120777<<16
        self.make([('folder/',b''),(link,b'/not/a/real/path')])
        result=audit(self.path)
        self.assertEqual([x['state'] for x in result['members']],['directory','unverified-symlink'])
        self.assertFalse(result['allZipMemberBytesVerified'])

    def test_archive_change_during_member_read_cannot_produce_receipt(self):
        self.make([('a.pdf', b'old')])
        original = zipfile.ZipFile.open
        def changed(archive, member, *args, **kwargs):
            stream = original(archive, member, *args, **kwargs)
            with self.path.open('ab') as target:
                target.write(b'changed')
            return stream
        with patch.object(zipfile.ZipFile, 'open', changed):
            with self.assertRaisesRegex(ValueError, 'archive-changed-during-audit'):
                audit(self.path)

    def warc(self, payload=b'fictional response', digest=None, kind='response'):
        body=b'HTTP/1.1 200 Response\r\nContent-Type: application/pdf\r\n\r\n'+payload
        sha=digest or hashlib.sha256(payload).hexdigest()
        return (f'WARC/1.1\r\nWARC-Type: {kind}\r\nContent-Length: {len(body)}\r\nWARC-Payload-Digest: sha256:{sha}\r\n\r\n'.encode()+body+b'\r\n\r\n')

    def test_warc_payloads_are_digest_checked_and_duplicate_records_retained(self):
        raw=self.warc()+self.warc()
        out=audit_warc(io.BytesIO(raw))
        self.assertTrue(out['allRecordsAccounted'])
        self.assertEqual(out['recordCount'],2)
        self.assertEqual(out['records'][0]['payloadSHA256'],hashlib.sha256(b'fictional response').hexdigest())
        self.make([('capture.warc',raw)])
        result=audit(self.path)
        self.assertTrue(result['allZipMemberBytesVerified'])
        self.assertFalse(result['warcPayloadAuditPending'])
        self.assertFalse(result['fullOriginalArchiveAcceptance'])

    def test_warc_digest_unknown_record_and_truncation_never_pass(self):
        for raw in (self.warc(digest='0'*64),self.warc(kind='revisit')):
            self.assertFalse(audit_warc(io.BytesIO(raw))['allRecordsAccounted'])
        with self.assertRaisesRegex(ValueError,'truncated-warc-record'):
            audit_warc(io.BytesIO(self.warc()[:-10]))
        with self.assertRaisesRegex(ValueError,'warc-byte-limit-exceeded'):
            audit_warc(io.BytesIO(self.warc()),max_record_bytes=1)
