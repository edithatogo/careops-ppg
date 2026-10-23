#!/usr/bin/env python3
"""Read-only ZIP member accounting. WARC payload qualification remains explicit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile
import zlib


def digest(stream, limit):
    result = hashlib.sha256()
    count = 0
    while chunk := stream.read(min(1024 * 1024, limit - count + 1)):
        count += len(chunk)
        if count > limit:
            raise ValueError('byte-limit-exceeded')
        result.update(chunk)
    return result.hexdigest(), count


def audit_warc(stream, max_record_bytes=1024**3, max_total_bytes=8*1024**3):
    """Account stored WARC records; verify SHA256 of captured HTTP payload bytes.

    No network decoding, replay, header export or current-authority assertion.
    Unknown record types/digests remain unqualified, never silently skipped.
    """
    records = []
    total = 0
    while True:
        version = stream.readline(65537)
        total += len(version)
        if total > max_total_bytes:
            raise ValueError('warc-byte-limit-exceeded')
        if not version:
            break
        if not version.strip():
            continue
        if version.rstrip() not in (b'WARC/1.0', b'WARC/1.1'):
            raise ValueError('unsupported-warc-record-boundary')
        headers = {}
        header_bytes = len(version)
        while True:
            line = stream.readline(65537)
            total += len(line); header_bytes += len(line)
            if not line or header_bytes > 65536:
                raise ValueError('invalid-warc-headers')
            if not line.strip():
                break
            key, separator, value = line.decode('latin1').partition(':')
            key = key.lower().strip()
            if not separator or key in headers:
                raise ValueError('ambiguous-warc-header')
            headers[key] = value.strip()
        length = int(headers['content-length'])
        if length < 0 or length > max_record_bytes or total + length > max_total_bytes:
            raise ValueError('warc-byte-limit-exceeded')
        body = stream.read(length)
        total += len(body)
        if len(body) != length:
            raise ValueError('truncated-warc-record')
        kind = headers.get('warc-type')
        row = {'ordinal': len(records), 'kind': kind,
               'recordSHA256': hashlib.sha256(body).hexdigest(), 'recordBytes': length,
               'target': headers.get('warc-target-uri'), 'capturedAt': headers.get('warc-date')}
        records.append(row)
        if kind in ('warcinfo', 'request', 'metadata'):
            row['state'] = 'accounted-control-record'
            continue
        if kind == 'response':
            head, separator, payload = body.partition(b'\r\n\r\n')
            if not separator or not head.startswith(b'HTTP/') or len(head) > 65536:
                raise ValueError('unsupported-warc-http-envelope')
            status = head.split(b' ', 2)[1]
            if len(status) != 3 or not status.isdigit():
                raise ValueError('invalid-warc-http-status')
            row['httpStatus'] = int(status)
        elif kind == 'resource':
            payload = body
        else:
            row['state'] = 'unverified-record-type'
            continue
        sha = hashlib.sha256(payload).hexdigest()
        row.update(payloadSHA256=sha, payloadBytes=len(payload),
                   state='payload-digest-verified' if headers.get('warc-payload-digest', '').lower() == 'sha256:'+sha
                   else 'unverified-payload-digest')
    return {'recordCount': len(records), 'records': records,
            'allRecordsAccounted': bool(records) and all(x['state'] in ('accounted-control-record','payload-digest-verified') for x in records)}


def audit(path, expected_sha256=None, max_member_bytes=1024**3, max_total_bytes=8*1024**3):
    """Never extract. Preserve duplicate names by ordinal; fail closed on unknowns."""
    path = Path(path)
    if max_member_bytes <= 0 or max_total_bytes <= 0:
        raise ValueError('positive-byte-limits-required')
    with path.open('rb') as stream:
        archive_sha, archive_bytes = digest(stream, max_total_bytes)
    if expected_sha256 is not None and archive_sha != expected_sha256:
        raise ValueError('archive-identity-mismatch')
    members = []
    total = 0
    with zipfile.ZipFile(path) as archive:
        for ordinal, info in enumerate(archive.infolist()):
            row = {'ordinal': ordinal, 'member': info.filename, 'declaredBytes': info.file_size,
                   'crc32': f'{info.CRC:08x}', 'directory': info.is_dir()}
            members.append(row)
            if info.is_dir():
                row['state'] = 'directory' if info.file_size == 0 else 'unverified-directory-payload'
                continue
            if stat.S_ISLNK(info.external_attr >> 16):
                row['state'] = 'unverified-symlink'
                continue
            if info.file_size > max_member_bytes or total + info.file_size > max_total_bytes:
                row['state'] = 'unverified-byte-limit'
                continue
            total += info.file_size
            try:
                with archive.open(info) as stream:
                    sha, count = digest(stream, max_member_bytes)
                if count != info.file_size:
                    raise ValueError('member-size-mismatch')
                row.update(sha256=sha, bytes=count, state='bytes-and-crc-verified')
                if info.filename.lower().endswith(('.warc', '.warc.gz')):
                    with archive.open(info) as stream:
                        if info.filename.lower().endswith('.gz'):
                            import gzip
                            with gzip.GzipFile(fileobj=stream) as decoded:
                                row['warcPayloads'] = audit_warc(decoded, max_member_bytes, max_total_bytes)
                        else:
                            row['warcPayloads'] = audit_warc(stream, max_member_bytes, max_total_bytes)
            except (OSError, KeyError, ValueError, RuntimeError, NotImplementedError, EOFError, zlib.error, zipfile.BadZipFile) as error:
                row['state'] = 'unverified-read-error'
                row['errorType'] = type(error).__name__
    with path.open('rb') as stream:
        final_sha, final_bytes = digest(stream, max_total_bytes)
    if (final_sha, final_bytes) != (archive_sha, archive_bytes):
        raise ValueError('archive-changed-during-audit')
    verified = all(x['state'] in ('directory', 'bytes-and-crc-verified') for x in members)
    warc_pending = any(x['member'].lower().endswith(('.warc','.warc.gz')) and
                       not isinstance(x.get('warcPayloads'), dict) or
                       isinstance(x.get('warcPayloads'), dict) and not x['warcPayloads']['allRecordsAccounted']
                       for x in members)
    return {'schemaVersion': 1, 'archiveName': path.name, 'archiveSHA256': archive_sha,
            'archiveBytes': archive_bytes, 'expectedIdentityMatched': expected_sha256 is not None,
            'memberCount': len(members), 'members': members,
            'allZipMemberBytesVerified': verified, 'warcPayloadAuditPending': warc_pending,
            'fullOriginalArchiveAcceptance': False, 'nativeWrites': 0,
            'remaining': ['Compare original provenance and retained/native hashes; qualify exclusions and all distinct document payloads',
                          *(['Inspect every WARC response/payload and encoding'] if warc_pending else [])]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('output', type=Path, help='New private JSON receipt; never overwrites')
    parser.add_argument('--expected-sha256')
    parser.add_argument('--max-member-bytes', type=int, default=1024**3)
    parser.add_argument('--max-total-bytes', type=int, default=8*1024**3)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists')
    result = audit(args.archive, args.expected_sha256, args.max_member_bytes, args.max_total_bytes)
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('memberCount','allZipMemberBytesVerified','warcPayloadAuditPending','fullOriginalArchiveAcceptance','nativeWrites')}))
    return 0 if result['allZipMemberBytesVerified'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
