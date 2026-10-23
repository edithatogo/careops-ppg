"""Preserve selected captures and compare source bytes; no network or record writes."""
from __future__ import annotations
import argparse
import base64
import hashlib
import html
import json
import os
import stat
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


MAX_CAPTURE_BYTES = 10 * 1024 * 1024
MAX_RECEIPT_BYTES = 1024 * 1024
FAILURE_FIELDS = {'sourceKey', 'canonicalUrl', 'capturedAtUtc', 'status'}


def capture_browser_receipt(config, bundle, output):
    """Import acquired browser bytes offline; never fetch or enable a schedule."""
    selected = validate_config(config)
    if not isinstance(bundle, dict) or bundle.get('kind') != 'browser-public-source-capture-v1':
        raise ValueError('qualified browser capture envelope required')
    results = bundle.get('results')
    if not isinstance(results, list) or len(results) != len(selected):
        raise ValueError('account for every selected source')
    observations, receipts, bodies, seen = [], [], [], set()
    for result in results:
        if not isinstance(result, dict):
            raise ValueError('browser source receipt required')
        key = result.get('sourceKey')
        if key not in selected or key in seen or result.get('canonicalUrl') != selected[key]['canonicalUrl']:
            raise ValueError('unknown, duplicate or redirected source')
        seen.add(key)
        observed = dict(sourceKey=key, capturedAtUtc=utc(result['capturedAtUtc']))
        status = result.get('status')
        if type(status) is int and status == 200:
            if result.get('finalUrl') != selected[key]['canonicalUrl']:
                raise ValueError('unexpected final source URL')
            encoded = result.get('base64')
            if not isinstance(encoded, str) or len(encoded) > 4*((MAX_CAPTURE_BYTES+2)//3):
                raise ValueError('browser body exceeds byte limit')
            data = base64.b64decode(encoded, validate=True)
            if (not 1 <= len(data) <= MAX_CAPTURE_BYTES or type(result.get('bytes')) is not int
                    or len(data) != result['bytes'] or hashlib.sha256(data).hexdigest() != result.get('sha256')):
                raise ValueError('browser body hash or size mismatch')
            headers = result.get('headers')
            if not isinstance(headers, dict):
                raise ValueError('browser response headers required')
            etag = headers.get('etag')
            if etag is not None and (not isinstance(etag, str) or not etag.strip() or '\r' in etag or '\n' in etag):
                raise ValueError('invalid ETag header')
            observed.update(status='captured', canonicalUrl=result['canonicalUrl'],
                sha256=result['sha256'], nativeVersionRef=None if etag is None else 'etag: '+etag,
                acquisitionRoute='BrowserOS neo same-origin public GET; imported raw-byte receipt')
            bodies.append((observed, data))
            receipts.append({k:v for k,v in result.items() if k != 'base64'})
        else:
            if set(result) - {'sourceKey','canonicalUrl','capturedAtUtc','status','error'}:
                raise ValueError('failed browser receipt must be body-free')
            observed['status'] = 'denied' if status in (401,403) else 'missing' if status == 404 else 'error'
            receipts.append({k:result[k] for k in FAILURE_FIELDS})
        observations.append(observed)
    receipt_bytes = (json.dumps(receipts,indent=2)+'\n').encode('utf-8')
    if len(receipt_bytes) > MAX_RECEIPT_BYTES:
        raise ValueError('browser receipt metadata exceeds byte limit')
    # All validation precedes destination creation. Keep exact originals; no
    # HTML normalisation or comparison-time trimming of opaque version tokens.
    with tempfile.TemporaryDirectory(prefix='ppg-browser-capture-') as temporary:
        for index,(observed,data) in enumerate(bodies):
            path = Path(temporary)/str(index)
            path.write_bytes(data)
            observed['file'] = str(path)
        snapshot = capture(config,observations,output)
    (Path(output)/'browser-receipts.json').write_bytes(receipt_bytes)
    return snapshot


def read_regular_bounded(path, limit):
    """Reject nonregular inputs before opening; bound the read even after growth."""
    path = Path(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('regular file required')
    flags = os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('regular file required')
        if info.st_size > limit:
            raise ValueError('file exceeds byte limit')
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError('file exceeds byte limit')
    return data


def read_json(path):
    return json.loads(read_regular_bounded(path, MAX_RECEIPT_BYTES).decode('utf-8'))


def utc(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError('UTC capture time required')
    return value


def validate_config(config):
    if not isinstance(config.get('familyId'), str) or not config['familyId'].strip():
        raise ValueError('explicit family identity required')
    sources = config.get('sources')
    if not isinstance(sources, list) or not 1 <= len(sources) <= 5:
        raise ValueError('select one to five sources')
    indexed = {}
    for source in sources:
        key, url = source['sourceKey'], urlsplit(source['canonicalUrl'])
        if not re.fullmatch(r'[a-z0-9-]{1,80}', key) or key in indexed:
            raise ValueError('unique explicit source key required')
        if url.scheme != 'https' or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError('canonical HTTPS URL required without credentials/query/fragment')
        indexed[key] = source
    return indexed


def capture(config, observations, output):
    selected = validate_config(config)
    if not isinstance(observations, list) or len(observations) != len(selected):
        raise ValueError('account for every selected source')
    seen, records, raw = set(), [], []
    for observed in observations:
        key = observed['sourceKey']
        if key not in selected or key in seen:
            raise ValueError('unknown or duplicate source')
        seen.add(key)
        status = observed['status']
        if status not in ('captured', 'denied', 'missing', 'unsupported', 'error'):
            raise ValueError('invalid observation status')
        record = dict(sourceKey=key, canonicalUrl=selected[key]['canonicalUrl'],
                      capturedAtUtc=utc(observed['capturedAtUtc']), status=status)
        if status == 'captured':
            if observed.get('canonicalUrl') != selected[key]['canonicalUrl']:
                raise ValueError('observed source URL mismatch')
            if not isinstance(observed.get('acquisitionRoute'), str) or not observed['acquisitionRoute'].strip():
                raise ValueError('qualified acquisition route receipt required')
            data = read_regular_bounded(observed['file'], MAX_CAPTURE_BYTES)
            if not data:
                raise ValueError('capture must contain one to10MiB')
            digest = hashlib.sha256(data).hexdigest()
            if observed.get('sha256') != digest:
                raise ValueError('capture hash mismatch')
            version = observed.get('nativeVersionRef')
            if version is not None and (not isinstance(version, str) or not version.strip()):
                raise ValueError('native version reference must be nonempty text or null')
            record.update(sha256=digest, size=len(data), rawFile=key+'.raw',
                          acquisitionRoute=observed['acquisitionRoute'],
                          nativeVersionRef=observed.get('nativeVersionRef'),
                          authority='captured-reference-current-unconfirmed')
            raw.append((record['rawFile'], data))
        elif set(observed) - (FAILURE_FIELDS - {'canonicalUrl'}):
            raise ValueError('failure observation must not retain denied/stale content metadata')
        records.append(record)
    snapshot = dict(schemaVersion=1, familyId=config['familyId'],
                    sources=sorted(records, key=lambda r:r['sourceKey']),
                    complete=all(r['status']=='captured' for r in records),
                    authorityDetermined=False, sourceWrites=False)
    receipt = (json.dumps(snapshot, indent=2)+'\n').encode('utf-8')
    if len(receipt) > MAX_RECEIPT_BYTES:
        raise ValueError('snapshot receipt exceeds byte limit')
    # Validate everything before creating the new destination. Existing snapshots stay intact.
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in raw:
        (output/name).write_bytes(data)
    (output/'snapshot.json').write_bytes(receipt)
    return snapshot


def _load_snapshot(directory):
    directory = Path(directory)
    receipt = read_regular_bounded(directory/'snapshot.json', MAX_RECEIPT_BYTES)
    snapshot = json.loads(receipt.decode('utf-8'))
    validate_config(snapshot)
    if snapshot.get('schemaVersion') != 1 or snapshot.get('authorityDetermined') is not False or snapshot.get('sourceWrites') is not False:
        raise ValueError('invalid snapshot contract')
    if snapshot.get('complete') is not all(r['status'] == 'captured' for r in snapshot['sources']):
        raise ValueError('invalid snapshot completeness')
    for record in snapshot['sources']:
        utc(record['capturedAtUtc'])
        if record['status'] == 'captured':
            if (not isinstance(record.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', record['sha256']) or
                type(record.get('size')) is not int or not 1 <= record['size'] <= MAX_CAPTURE_BYTES or
                record.get('rawFile') != record['sourceKey']+'.raw' or
                record.get('authority') != 'captured-reference-current-unconfirmed' or
                not isinstance(record.get('acquisitionRoute'), str) or not record['acquisitionRoute'].strip()):
                raise ValueError('invalid stored capture provenance')
            version = record.get('nativeVersionRef')
            if version is not None and (not isinstance(version, str) or not version.strip()):
                raise ValueError('invalid stored native version')
            # Derive filename from validated identity, never trust a manifest path.
            data = read_regular_bounded(directory/(record['sourceKey']+'.raw'), MAX_CAPTURE_BYTES)
            if not data or hashlib.sha256(data).hexdigest() != record['sha256'] or len(data) != record['size']:
                raise ValueError('stored capture integrity mismatch')
        elif record['status'] not in ('denied', 'missing', 'unsupported', 'error'):
            raise ValueError('invalid stored source status')
        elif set(record) - FAILURE_FIELDS:
            raise ValueError('failure snapshot must not retain denied/stale content metadata')
    return snapshot, {r['sourceKey']:r for r in snapshot['sources']}, hashlib.sha256(receipt).hexdigest()


def load_snapshot(directory):
    snapshot, sources, _ = _load_snapshot(directory)
    return snapshot, sources


def compare(baseline_dir, candidate_dir, links):
    before, old, before_receipt = _load_snapshot(baseline_dir)
    after, new, after_receipt = _load_snapshot(candidate_dir)
    if before['familyId'] != after['familyId'] or set(old) != set(new):
        raise ValueError('source scope changed; explicitly establish a new baseline')
    changes = []
    for key in sorted(old):
        a, b = old[key], new[key]
        if datetime.fromisoformat(b['capturedAtUtc'].replace('Z','+00:00')) < datetime.fromisoformat(a['capturedAtUtc'].replace('Z','+00:00')):
            raise ValueError('candidate capture predates baseline')
        if a['canonicalUrl'] != b['canonicalUrl']:
            raise ValueError('source binding changed')
        if a['status'] != 'captured':
            kind = 'baseline-unavailable'
        elif b['status'] != 'captured':
            kind = 'source-unavailable-exception'
        elif a['sha256'] != b['sha256']:
            kind = 'captured-bytes-changed'
        elif a.get('nativeVersionRef') != b.get('nativeVersionRef'):
            kind = 'version-reference-changed'
        else:
            kind = 'unchanged'
        changes.append(dict(sourceKey=key, canonicalUrl=a['canonicalUrl'],
                            beforeNativeVersionRef=a.get('nativeVersionRef'), afterNativeVersionRef=b.get('nativeVersionRef'), kind=kind, beforeStatus=a['status'], afterStatus=b['status'], beforeSHA256=a.get('sha256'), afterSHA256=b.get('sha256'), beforeCapturedAtUtc=a['capturedAtUtc'], afterCapturedAtUtc=b['capturedAtUtc']))
    affected = {r['sourceKey'] for r in changes if r['kind'] != 'unchanged'}
    cases, seen = [], set()
    for link in links:
        case, keys = link['CaseUID'], link['sourceKeys']
        if not isinstance(case,str) or not case or case in seen or not isinstance(keys,list) or not keys or any(k not in old for k in keys):
            raise ValueError('unique case and explicit known source links required')
        seen.add(case)
        cases.append(dict(CaseUID=case, potentiallyAffected=bool(set(keys)&affected)))
    return dict(schemaVersion=2, mode='manual-selected-source-surveillance', familyId=before['familyId'],
                caseCoverage='Explicit supplied links only; omitted cases are not assessed',
                baselineSnapshot=dict(receiptFile='snapshot.json', receiptSHA256=before_receipt),
                candidateSnapshot=dict(receiptFile='snapshot.json', receiptSHA256=after_receipt),
                caseLinksSHA256=hashlib.sha256(json.dumps(links, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest(),
                changes=changes, cases=cases, scope='Exact raw bytes/version references only; no semantic/currency determination.',
                baselinePromotionAllowed=all(r['kind'] not in ('baseline-unavailable','source-unavailable-exception') for r in changes),
                baselineAdvanced=False, sourceWrites=False, caseWrites=False, notificationsSent=False)


def render(report):
    """Readable report from accepted structured comparison; never execute source text."""
    esc = lambda value: html.escape('not supplied' if value is None else str(value), quote=True)
    rows = ''.join('<tr><td>'+esc(c['sourceKey'])+'<br><a href="'+esc(c['canonicalUrl'])+'">Source</a></td><td>'+esc(c['kind'])+
                   '<br>'+esc(c['beforeStatus'])+' → '+esc(c['afterStatus'])+'</td><td>'+esc(c['beforeCapturedAtUtc'])+'<br>'+esc(c['beforeNativeVersionRef'])+'<br>'+esc(c['beforeSHA256'])+
                   '</td><td>'+esc(c['afterCapturedAtUtc'])+'<br>'+esc(c['afterNativeVersionRef'])+'<br>'+esc(c['afterSHA256'])+'</td></tr>' for c in report['changes'])
    cases = ''.join('<li>'+esc(c['CaseUID'])+': '+('potentially affected' if c['potentiallyAffected'] else 'no captured change in supplied links')+'</li>' for c in report['cases'])
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Selected-source surveillance</title>'
            '<style>body{font:16px system-ui;max-width:1200px;margin:2rem auto;padding:1rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #aaa;padding:.5rem;text-align:left;overflow-wrap:anywhere}.notice{background:#fff4ce;padding:1rem}</style>'
            '<h1>Selected-source surveillance</h1><p class="notice">'+esc(report['scope'])+
            ' No authority decision, case update, baseline advance or notification.</p><p>Unavailable means an acquisition result for this attempt, not global denial or retirement. Omitted cases are unassessed.</p><p>Family: '+esc(report['familyId'])+
            '</p><table><thead><tr><th>Source</th><th>Signal</th><th>Before: capture / version / SHA256</th><th>After: capture / version / SHA256</th></tr></thead><tbody>'+rows+'</tbody></table>'
            '<h2>Explicit case links</h2><p>'+esc(report['caseCoverage'])+'</p><ul>'+cases+'</ul>'
            '<h2>Provenance</h2><p>Baseline snapshot receipt SHA256: '+esc(report['baselineSnapshot']['receiptSHA256'])+
            '<br>Candidate snapshot receipt SHA256: '+esc(report['candidateSnapshot']['receiptSHA256'])+
            '<br>Canonical case-link payload SHA256: '+esc(report['caseLinksSHA256'])+
            '</p><p>Use surveillance.json and the matching immutable snapshots for full accounting. '
            'Byte changes can be formatting or navigation; inspect retained sources before deciding what changed.</p></html>')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    c=commands.add_parser('capture');c.add_argument('--config',type=Path,required=True)
    acquisition=c.add_mutually_exclusive_group(required=True)
    acquisition.add_argument('--observations',type=Path)
    acquisition.add_argument('--browser-capture',type=Path)
    c.add_argument('--output',type=Path,required=True)
    d=commands.add_parser('compare');d.add_argument('--baseline',type=Path,required=True);d.add_argument('--candidate',type=Path,required=True);d.add_argument('--links',type=Path,required=True);d.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='capture':
        if args.browser_capture:
            limit=5*(4*((MAX_CAPTURE_BYTES+2)//3))+MAX_RECEIPT_BYTES
            bundle=json.loads(read_regular_bounded(args.browser_capture,limit).decode('utf-8'))
            capture_browser_receipt(read_json(args.config),bundle,args.output)
        else:
            capture(read_json(args.config),read_json(args.observations),args.output)
    else:
        report=compare(args.baseline,args.candidate,read_json(args.links))
        args.output.mkdir(parents=True,exist_ok=False)
        (args.output/'surveillance.json').write_text(json.dumps(report,indent=2)+'\n', encoding='utf-8')
        (args.output/'surveillance.html').write_text(render(report), encoding='utf-8')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
