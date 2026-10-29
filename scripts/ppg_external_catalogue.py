"""Library-backed external catalogue contract. Offline; no native mutation or auth."""
from __future__ import annotations

import argparse
import hashlib
import json
import copy
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 8 * 1024 * 1024
HOST = 'www.safetyandquality.gov.au'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def official_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.hostname != HOST or parsed.username
            or parsed.password or parsed.port not in (None, 443) or parsed.fragment
            or any(ord(c) < 32 for c in value)):
        raise ValueError('Official HTTPS source URL required')
    return value


def native_url(value, *, related=False, publication=None):
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.sharepoint.com')
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.fragment or any(ord(c) < 32 for c in value)):
        raise ValueError('Stable HTTPS SharePoint link required')
    if not related and parsed.query:
        raise ValueError('Stable original links cannot contain authentication/query parameters')
    if related:
        from urllib.parse import parse_qs
        query = parse_qs(parsed.query)
        if ('/Lists/' not in parsed.path or not parsed.path.endswith('.aspx')
                or query != {'FilterField1': ['PublicationKey'], 'FilterValue1': [publication]}):
            raise ValueError('Exact publication navigation link required')


def page_inventory(raw, url):
    """Keep link occurrences, including repeated URLs; never mint publication IDs."""
    official_url(url)
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError('Bounded HTML bytes required')
    text = raw.decode('utf-8-sig')
    if '\x00' in text:
        raise ValueError('NUL HTML refused')
    soup = BeautifulSoup(text, 'html.parser')
    main = soup.find('main')
    if main is None or not main.find(['h1', 'h2']):
        raise ValueError('Expected publisher main content required')
    entries, outside = [], []
    for i, link in enumerate(main.find_all('a', href=True)):
        target = urljoin(url, link['href'])
        u = urlsplit(target)
        if u.fragment or u.scheme != 'https' or u.hostname != HOST:
            outside.append(dict(occurrence=i, rawHref=link['href'], label=link.get_text(' ', strip=True),
                                reason='Outside selected same-origin publication-link scope'))
            continue
        official_url(target)
        label = link.get_text(' ', strip=True)
        if label:
            entries.append(dict(occurrence=i, url=target, rawHref=link['href'], label=label,
                                sourceURL=url, sourceSHA256=digest(raw)))
    return dict(sourceURL=url, sourceSHA256=digest(raw), occurrences=entries,
                outsideSelectedScope=outside,
                text=main.get_text(' ', strip=True))


def validate(bundle, known_frameworks=(), capture_root=None):
    if not {'date-time', 'uri'} <= FormatChecker.checkers.keys():
        raise RuntimeError('Hash-locked jsonschema format profile required')
    schema = json.loads((ROOT / 'config/external-publication.schema.json').read_text())
    # No remote schema retrieval: the checked-in schema has only local references.
    validator = Draft202012Validator(schema, format_checker=FormatChecker(), registry=Registry())
    validator.validate(bundle)
    records = bundle['records']
    index = {r['key']: r for r in records}
    if len(index) != len(records):
        raise ValueError('Duplicate external record identity')
    c = bundle['coverage']
    if c['collectionEntries'] != c['included'] + c['excluded'] + c['unresolved']:
        raise ValueError('Collection denominator does not reconcile')
    if c['fullCollectionComplete'] and c['unresolved']:
        raise ValueError('Unresolved collection cannot be complete')
    frameworks = set(known_frameworks)
    for r in records:
        if not set(r['frameworkKeys']) <= frameworks:
            raise ValueError('Unknown existing framework key')
        for a in r['assertions']:
            official_url(a['sourceURL'])
        data = r['data']
        if data.get('sourceURL'):
            official_url(data['sourceURL'])
        if data.get('nativeURL'):
            native_url(data['nativeURL'])
        if data.get('relatedRecordsURL'):
            native_url(data['relatedRecordsURL'], related=True, publication=r['publicationKey'])
        pub, edition = r['publicationKey'], r['editionKey']
        if r['kind'] == 'Publication' and (pub != r['key'] or edition is not None):
            raise ValueError('Publication identity must be edition-independent')
        if pub is not None and index.get(pub, {}).get('kind') != 'Publication':
            raise ValueError('Unknown publication endpoint')
        if r['kind'] == 'Edition':
            if not pub or edition != r['key']:
                raise ValueError('Edition must bind a publication and itself')
        elif edition is not None:
            e = index.get(edition)
            if not e or e['kind'] != 'Edition' or e['publicationKey'] != pub:
                raise ValueError('Cross-publication or unknown edition')
        if r['kind'] == 'Capture':
            data = r['data']
            if not pub or (not edition and data.get('editionResolution') != 'unverified'):
                raise ValueError('Capture requires a publication and explicit edition resolution')
            if (not isinstance(data.get('sha256'), str) or len(data['sha256']) != 64
                    or any(x not in '0123456789abcdef' for x in data['sha256'])
                    or type(data.get('bytes')) is not int or data['bytes'] <= 0):
                raise ValueError('Capture hash and size required')
            official_url(data['sourceURL'])
            if capture_root is not None:
                root = Path(capture_root).resolve()
                path = root / data['file']
                if (path.is_symlink() or not path.is_file() or root not in path.resolve().parents
                        or any(p.is_symlink() for p in path.parents if p != root and root in p.parents)):
                    raise ValueError('Capture must be a regular file inside the pinned root')
                if path.stat().st_size != data['bytes'] or data['bytes'] > 128 * 1024 * 1024:
                    raise ValueError('Capture original bytes differ or exceed bounds')
                raw = path.read_bytes()
                if len(raw) != data['bytes'] or digest(raw) != data['sha256']:
                    raise ValueError('Capture original bytes differ')
        if r['kind'] == 'Resolution':
            ref = index.get(r['data'].get('referenceKey'))
            if not ref or ref['kind'] != 'Reference':
                raise ValueError('Unknown reference occurrence')
            if r['data'].get('level') == 'publication' and edition is not None:
                raise ValueError('Publication-only resolution cannot select an edition')
        if r['data'].get('clinicalApplicabilityAccepted', False) is not False:
            raise ValueError('Source ingestion cannot accept clinical applicability')
    return dict(records=len(records), kinds={k: sum(r['kind'] == k for r in records)
                 for k in sorted({r['kind'] for r in records})}, coverage=c)


def payloads(bundle, known_frameworks=(), capture_root=None):
    validate(bundle, known_frameworks, capture_root)
    return [dict(Title=r['title'][:255], RecordKey=r['key'], RecordKind=r['kind'],
                 PublicationKey=r['publicationKey'], EditionKey=r['editionKey'],
                 Issuer=r['issuer'], SourceStatus=r['sourceStatus'], SourceRole=r['role'],
                 TrancheKey=bundle['tranche'], RecordJSON=canonical(r),
                 PayloadSHA256=digest(canonical(r).encode()), ReviewState='Proposed',
                 OfficialURL=r['data'].get('sourceURL') or r['assertions'][0]['sourceURL'],
                 EvidenceURL=r['data'].get('nativeURL'),
                 RelatedRecordsURL=r['data'].get('relatedRecordsURL'))
            for r in bundle['records']]


def snapshot(bundle, native_rows, capture_root, known_frameworks=()):
    """Bind native current-row readback and downloaded originals into one export."""
    expected = payloads(bundle, known_frameworks, capture_root)
    index = {r['RecordKey']: r for r in native_rows}
    if len(index) != len(native_rows) or len(index) != len(expected):
        raise ValueError('Native population count/key mismatch')
    for row in expected:
        actual = index.get(row['RecordKey'], {})
        if any(actual.get(k) != value for k, value in row.items()):
            raise ValueError('Native row drift; preserve edits before export')
    return dict(exportVersion=1, bundle=copy.deepcopy(bundle),
                nativeRecords=copy.deepcopy(native_rows),
                knownFrameworkKeys=list(known_frameworks))


def reconstruct(export, downloaded_root, bindings=None):
    """Verify downloaded bytes before rebinding into an isolated recovery target.

    Native item IDs/times remain provenance in the export, not fabricated history.
    No old source/edition assertion or human state is changed.
    """
    if export.get('exportVersion') != 1:
        raise ValueError('Unknown export contract')
    original = export['bundle']
    snapshot(original, export['nativeRecords'], downloaded_root, export['knownFrameworkKeys'])
    result = copy.deepcopy(original)
    if bindings is not None:
        for key in ['folderURL', 'listURL']:
            parsed = urlsplit(bindings[key])
            if (parsed.scheme != 'https' or not parsed.hostname.endswith('.sharepoint.com')
                    or parsed.username or parsed.password or parsed.query or parsed.fragment):
                raise ValueError('Explicit isolated SharePoint recovery bindings required')
        for r in result['records']:
            data = r['data']
            if data.get('nativeURL'):
                data['originNativeURL'] = data['nativeURL']
                data['nativeURL'] = bindings['folderURL'].rstrip('/') + '/ECR-' + data['file']
            if r['publicationKey']:
                data['relatedRecordsURL'] = (bindings['listURL'] + '?FilterField1=PublicationKey&FilterValue1='
                    + r['publicationKey'].replace(':', '%3A'))
    validate(result, export['knownFrameworkKeys'], downloaded_root)
    return result


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['validate', 'payloads', 'inventory', 'compare', 'snapshot', 'reconstruct'])
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--frameworks', type=Path)
    p.add_argument('--capture-root', type=Path)
    p.add_argument('--url')
    p.add_argument('--previous', type=Path)
    p.add_argument('--native-rows', type=Path)
    p.add_argument('--bindings', type=Path)
    a = p.parse_args()
    if a.command == 'inventory':
        result = page_inventory(a.input.read_bytes(), a.url)
    elif a.command == 'snapshot':
        result = snapshot(json.loads(a.input.read_text()), json.loads(a.native_rows.read_text()),
                          a.capture_root, json.loads(a.frameworks.read_text()))
    elif a.command == 'reconstruct':
        result = reconstruct(json.loads(a.input.read_text()), a.capture_root,
                             json.loads(a.bindings.read_text()) if a.bindings else None)
    elif a.command == 'compare':
        old = json.loads(a.previous.read_text())
        new = json.loads(a.input.read_text())
        result = changes(old, new)
    else:
        frameworks = json.loads(a.frameworks.read_text()) if a.frameworks else []
        b = json.loads(a.input.read_text())
        result = (validate(b, frameworks, a.capture_root) if a.command == 'validate'
                  else payloads(b, frameworks, a.capture_root))
    write_new(a.output, result)


def changes(old, new):
    """No missing observation or changed bytes automatically withdraws an edition."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ValueError('Keyed observation snapshots required')
    if any(v is not None and not isinstance(v, dict) for v in [*old.values(), *new.values()]):
        raise ValueError('Observation entries must be objects or explicit missing values')
    def facts(value):
        # Capture clocks and HTTP metadata are not publication changes by themselves.
        return {k: v for k, v in value.items()
                if k not in {'observedAt', 'observedAtUtc', 'at', 'lastVerifiedAt', 'headers', 'httpHeaders'}}
    results = []
    for key in sorted(old.keys() | new.keys()):
        previous, current = old.get(key), new.get(key)
        state = ('not_observed' if current is None else 'retrieval_failed_baseline_held'
                 if current.get('error') else 'new_candidate' if previous is None
                 else 'unchanged' if facts(previous) == facts(current) else 'changed_review_required')
        results.append(dict(key=key, state=state, baselinePromoted=False,
                            applicabilityAccepted=False))
    return results


if __name__ == '__main__':
    main()
