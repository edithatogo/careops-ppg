"""Retain unordered same-edition source variants without choosing a winner.

The result is a derived ZIP representation, never another source capture or an
identity/edition decision. Originals stay separately retained. Native publication
and per-source pin/metadata checks belong to the existing qualified writer.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import zipfile
from uuid import UUID

MAX_CAPSULE_BYTES = 32 * 1024 * 1024
MAX_ORIGINAL_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_BYTES = 256 * 1024 * 1024


def build_variant_bundle(records, capsule_bytes):
    """Return deterministic bytes and a manifest for one evidenced edition set."""
    if (not isinstance(records, list) or not 2 <= len(records) <= 500
            or not isinstance(capsule_bytes, dict)
            or any(not isinstance(r, dict) or not isinstance(r.get('sha256'), str) for r in records)):
        raise ValueError('require_two_or_more_captured_variants')
    identities, editions, sources, originals = set(), set(), {}, {}
    retained = []
    for record in sorted(records, key=lambda row: row['sha256']):
        try:
            uid = UUID(record['documentUID'])
            if not uid.int or not record['identityEvidence']:
                raise ValueError()
            edition = record['sourceEdition']
            if not isinstance(edition, str) or not re.fullmatch(r'\d+(?:\.\d+)*', edition):
                raise ValueError()
            sha = record['sha256']
            if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{64}', sha):
                raise ValueError()
            if sha in sources or not isinstance(record['sourcePath'], str) or not record['sourcePath']:
                raise ValueError()
            raw = capsule_bytes[sha]
            if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_CAPSULE_BYTES or len(raw) != record['bytes'] or hashlib.sha256(raw).hexdigest() != sha:
                raise ValueError()
            member = record['sourceCapsule']
            name = member['member']
            if not isinstance(name, str) or not name or '/' in name or '\\' in name or '\x00' in name or name in {'.', '..'}:
                raise ValueError()
            with zipfile.ZipFile(io.BytesIO(raw)) as capsule:
                if (not isinstance(member['memberBytes'], int)
                        or not 0 < member['memberBytes'] <= MAX_ORIGINAL_BYTES
                        or capsule.getinfo(name).file_size != member['memberBytes']
                        or sum(info.file_size for info in capsule.infolist()) > MAX_ORIGINAL_BYTES + 2 * 1024 * 1024):
                    raise ValueError()
                if capsule.testzip() is not None or len(capsule.namelist()) != len(set(capsule.namelist())):
                    raise ValueError()
                content = capsule.read(name)
            original_sha = hashlib.sha256(content).hexdigest()
            if original_sha != member['memberSHA256'] or len(content) != member['memberBytes']:
                raise ValueError()
        except (KeyError, TypeError, ValueError, AttributeError, zipfile.BadZipFile) as exc:
            raise ValueError('unverified_variant_capture') from exc
        identities.add(str(uid))
        editions.add(edition)
        sources[sha] = True
        # Repeated byte occurrences retain their provenance, with one raw member.
        archive_name = 'variants/' + original_sha + '/' + name
        prior = originals.get(original_sha)
        if prior is None:
            originals[original_sha] = (archive_name, content)
        else:
            archive_name = prior[0]
        retained.append({**copy.deepcopy(record), 'bundleMember': archive_name})
    if len(identities) != 1 or len(editions) != 1:
        raise ValueError('one_established_identity_and_exact_printed_edition_required')
    if len(originals) < 2:
        raise ValueError('no_distinct_original_variants')
    if set(capsule_bytes) != set(sources):
        raise ValueError('unaccounted_capsule_bytes')
    if sum(len(content) for _, content in originals.values()) > MAX_BUNDLE_BYTES:
        raise ValueError('variant_bundle_oversize')
    manifest = {
        'schemaVersion': 1, 'representation': 'unordered-source-variant-set',
        'documentUID': next(iter(identities)), 'sourceEdition': next(iter(editions)),
        'sourceCaptures': sorted(retained, key=lambda row: row['sha256']),
        'variantOrder': 'unresolved', 'canonicalVariant': None,
        'authorityAsserted': False, 'newSourceCapture': False,
        'originalsMustRemainSeparatelyRetained': True,
        'storageOrder': 'SHA256 only; not source chronology or preference',
        'zipTimestamp': 'format normalization only; not a source or native timestamp',
    }
    output = io.BytesIO()
    entries = [('manifest.json', (json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + '\n').encode())]
    if sum(len(content) for _, content in originals.values()) + len(entries[0][1]) > MAX_BUNDLE_BYTES:
        raise ValueError('variant_bundle_oversize')
    entries += [originals[sha] for sha in sorted(originals)]
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, content in entries:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3  # Stable ZIP headers on Unix and Windows.
            info.external_attr = 0o100600 << 16
            archive.writestr(info, content)
    raw = output.getvalue()
    return {'bytes': raw, 'sha256': hashlib.sha256(raw).hexdigest(), 'manifest': manifest}
