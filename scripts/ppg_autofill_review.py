"""Version-bound reviewed metadata for the existing fictional Autofill pilot only."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config/autofill-suggestions.json'
RAW = ('SuggestedTopic', 'SuggestedPurpose', 'SuggestedDocumentKind')
REVIEWED = ('ReviewedTopic', 'ReviewedPurpose', 'ReviewedDocumentKind')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def plan(snapshot, current, values, actor, operation_id, config):
    """Pure guarded payload construction; only five reviewed fields may be written."""
    if snapshot.get('contractVersion') != config['reviewContractVersion']:
        raise ValueError('review_contract_changed')
    if snapshot.get('configSHA256') != fingerprint(config):
        raise ValueError('configuration_changed')
    if str(uuid.UUID(operation_id)) != operation_id:
        raise ValueError('canonical_operation_uuid_required')
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 120:
        raise ValueError('explicit_actor_required')
    if set(values) != set(REVIEWED):
        raise ValueError('reviewed_fields_only')
    for field, limit in [('ReviewedTopic', 120), ('ReviewedPurpose', 500)]:
        if not isinstance(values[field], str) or not values[field].strip() or len(values[field]) > limit:
            raise ValueError('invalid_reviewed_value:' + field)
    if values['ReviewedDocumentKind'] not in config['columns'][2]['choices']:
        raise ValueError('invalid_reviewed_kind')
    # An operation binds its entire request, not just a caller-controlled ID.
    request = {'snapshotSHA256': fingerprint(snapshot), 'values': values, 'actor': actor,
               'operationId': operation_id}
    request_hash = fingerprint(request)
    item = current['item']
    if current['target'] != snapshot['target']:
        raise ValueError('target_changed')
    if item.get('ReviewOperationId') == operation_id:
        try:
            prior = json.loads(item.get('ReviewProvenance') or '{}')
        except (TypeError, json.JSONDecodeError):
            raise ValueError('invalid_existing_provenance')
        if prior.get('requestSHA256') != request_hash or any(item.get(k) != v for k, v in values.items()):
            raise ValueError('operation_conflict')
        # Read-only retry after an uncertain response; never reapply a stale snapshot.
        return None
    if current['itemETag'] != snapshot['itemETag']:
        raise ValueError('stale_item')
    for key in ('source', 'rawSuggestions', 'processing'):
        if current[key] != snapshot[key]:
            raise ValueError('stale_' + key)
    if current['processing']['status'] != 'Finished':
        raise ValueError('processing_not_finished')
    provenance = {'contractVersion': config['reviewContractVersion'], **request,
                  'requestSHA256': request_hash, 'source': snapshot['source'],
                  'rawSuggestions': snapshot['rawSuggestions'],
                  'promptVersion': snapshot['promptVersion'],
                  'expectedItemETag': snapshot['itemETag'],
                  'recordedAtUtc': datetime.now(timezone.utc).isoformat(),
                  'scope': 'Fictional technical review record; no policy approval'}
    return {**values, 'ReviewOperationId': operation_id, 'ReviewProvenance': canonical(provenance)}


class Pilot:
    def __init__(self, binding):
        self.binding = binding
        site = binding['site'].rstrip('/')
        if binding.get('fictionalOnly') is not True or urlparse(site).scheme != 'https':
            raise ValueError('fictional_https_binding_required')
        self.site = site
        self.base = site + "/_api/web/lists(guid'" + str(uuid.UUID(binding['libraryId'])) + "')"
        settings = self.request(self.base + '?$select=Id,Title,EnableVersioning')
        if settings.get('Title') != 'PPG Autofill Fictional Pilot' or not settings.get('EnableVersioning'):
            raise ValueError('exact_versioned_fictional_pilot_required')

    def request(self, url, *, payload=None, etag=None, download=None):
        args = ['m365', 'request', '--url', url, '--method', 'get' if payload is None else 'post']
        if payload is not None:
            if not etag or etag == '*':
                raise ValueError('exact_etag_required')
            args += ['--content-type', 'application/json;odata=nometadata',
                     '--x-http-method', 'MERGE', '--if-match', etag, '--body', canonical(payload)]
        if download:
            args += ['--filePath', str(download)]
        else:
            args += ['--output', 'json']
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError('native_request_failed:' + r.stderr.strip())
        return json.loads(r.stdout) if r.stdout.strip() else None

    def ownership(self, config):
        fields = self.request(self.base + '/fields?$select=InternalName,TypeAsString,AutofillInfo')['value']
        by_name = {f['InternalName']: f for f in fields}
        for expected in config['columns']:
            field = by_name.get(expected['internalName'])
            info = field.get('AutofillInfo') if field else None
            info = json.loads(info) if isinstance(info, str) else info
            if not field or field['TypeAsString'] != expected['type'] or not info or info.get('LLM', {}).get('Prompt') != expected['prompt']:
                raise ValueError('raw_prompt_contract_changed:' + expected['internalName'])
        for expected in config['reviewedFields']:
            field = by_name.get(expected['internalName'])
            if not field or field['TypeAsString'] != expected['type'] or field.get('AutofillInfo'):
                raise ValueError('reviewed_field_not_separate:' + expected['internalName'])

    def capture(self, item_id, config):
        if type(item_id) is not int or item_id < 1:
            raise ValueError('positive_item_id_required')
        self.ownership(config)
        url = self.base + '/items(' + str(item_id) + ')?$expand=File'
        before = self.request(url)
        file = before['File']
        uid = str(uuid.UUID(file['UniqueId']))
        file_url = self.site + "/_api/web/GetFileById('" + uid + "')"
        meta = self.request(file_url + '?$select=UniqueId,ETag,UIVersionLabel,Length')
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / 'source'
            self.request(file_url + '/$value', download=dest)
            raw = dest.read_bytes()
        after = self.request(url)
        meta_after = self.request(file_url + '?$select=UniqueId,ETag,UIVersionLabel,Length')
        etag = before.get('odata.etag') or before.get('__metadata', {}).get('etag')
        after_etag = after.get('odata.etag') or after.get('__metadata', {}).get('etag')
        pins = ('UniqueId', 'ETag', 'UIVersionLabel', 'Length')
        if not etag or etag != after_etag or any(meta.get(k) != meta_after.get(k) for k in pins):
            raise ValueError('changed_during_capture')
        if int(meta['Length']) != len(raw):
            raise ValueError('source_size_mismatch')
        source = {'UniqueId': uid, 'version': meta['UIVersionLabel'], 'ETag': meta['ETag'],
                  'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        return {'contractVersion': config['reviewContractVersion'],
                'configSHA256': fingerprint(config), 'promptVersion': config['promptVersion'],
                'target': {'site': self.site, 'libraryId': self.binding['libraryId'], 'itemId': item_id},
                'itemETag': etag, 'source': source,
                'rawSuggestions': {k: after.get(k) for k in RAW},
                'processing': {'status': after.get('PrimeClassificationStatus'),
                               'classifiedAt': after.get('PrimeLastClassified')},
                'item': {k: after.get(k) for k in (*REVIEWED, 'ReviewOperationId', 'ReviewProvenance')}}

    def apply(self, snapshot, values, actor, operation_id, config):
        current = self.capture(snapshot['target']['itemId'], config)
        payload = plan(snapshot, current, values, actor, operation_id, config)
        if payload is None:
            return {'state': 'replayed', 'record': current}
        # Item and raw-processing edits change this ETag; a racing update returns 412.
        self.request(self.base + '/items(' + str(current['target']['itemId']) + ')',
                     payload=payload, etag=snapshot['itemETag'])
        readback = self.capture(snapshot['target']['itemId'], config)
        if any(readback['item'].get(k) != v for k, v in payload.items()):
            raise ValueError('apply_readback_mismatch')
        return {'state': 'applied', 'record': readback}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    snap = sub.add_parser('snapshot'); snap.add_argument('--item', type=int, required=True)
    apply = sub.add_parser('apply')
    apply.add_argument('--snapshot', type=Path, required=True)
    apply.add_argument('--values', type=Path, required=True)
    apply.add_argument('--actor', required=True)
    apply.add_argument('--operation-id', required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('output_exists_preserve_receipt')
    if not args.output.parent.is_dir():
        raise ValueError('existing_private_output_directory_required')
    config = json.loads(CONFIG.read_text())
    client = Pilot(json.loads(args.binding.read_text()))
    if args.command == 'snapshot':
        record = client.capture(args.item, config)
    else:
        record = client.apply(json.loads(args.snapshot.read_text()), json.loads(args.values.read_text()),
                              args.actor, args.operation_id, config)
    with args.output.open('x') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
