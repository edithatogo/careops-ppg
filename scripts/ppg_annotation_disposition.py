"""Prepare an explicit annotation disposition for an exact native ETag; never write."""
import argparse
import json
import uuid
from pathlib import Path
from scripts.ppg_annotation_adapter import annotations_from_export

STATES = {'Triaged', 'Deferred', 'Accepted', 'Rejected', 'Incorporated', 'Superseded'}


def prepare(export, item_id, target, rationale, operation_id, incorporated_version=None, summary=None):
    operation_id = str(uuid.UUID(operation_id))
    if target not in STATES or not isinstance(rationale, str) or not rationale.strip():
        raise ValueError('Disposition needs a known target and explicit rationale')
    if target == 'Incorporated' and (not isinstance(incorporated_version, str) or not incorporated_version.strip()):
        raise ValueError('Incorporation needs an explicit document version')
    if target != 'Incorporated' and incorporated_version is not None:
        raise ValueError('Only incorporation accepts an incorporated version')
    fields = export['binding']
    if summary is not None and 'DispositionSummary' not in fields:
        raise ValueError('Summary field is not qualified in this export')
    web_summary = summary if summary is not None else rationale
    if 'DispositionSummary' in fields and (not isinstance(web_summary, str) or not web_summary.strip() or len(web_summary) > 255):
        raise ValueError('Provide an explicit disposition summary of 1 to 255 characters')
    annotations = annotations_from_export(export)
    matches = [r for r in export['annotationItems']['value'] if r['Id'] == item_id]
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous annotation item')
    item = matches[0]
    annotation = next(r for r in annotations if r['annotationId'] == export['listId']+':'+str(item_id))
    marker = 'Annotation disposition operation '+operation_id
    contents = dict(target=target, rationale=rationale, incorporatedVersion=incorporated_version)
    if summary is not None:
        contents['summary'] = summary
    note = marker+'\n'+json.dumps(contents, sort_keys=True, ensure_ascii=False)
    prior = [v for v in annotation['versionHistory'] if marker in (v['rationale'] or '')]
    if prior:
        if any(v['rationale'] != note for v in prior):
            raise ValueError('Operation identity reused with a different disposition')
        # A later human edit must survive replay; never restore the earlier state.
        return dict(action='already_recorded', operationId=operation_id, itemId=item_id,
                    currentStatus=annotation['status'], nativeWriteRequired=False)
    etag = item.get('@odata.etag') or item.get('odata.etag') or item.get('__metadata', {}).get('etag')
    if not isinstance(etag, str) or not etag or etag == '*':
        raise ValueError('Exact item ETag required')
    fields = export['binding']
    changes = {fields['ReviewState']: target, fields['DecisionRationale']: note}
    if 'DispositionSummary' in fields:
        changes[fields['DispositionSummary']] = web_summary
    if target == 'Incorporated':
        changes[fields['IncorporatedVersion']] = incorporated_version
    return dict(action='conditional_update', operationId=operation_id,
                listId=export['listId'], itemId=item_id, ifMatch=etag,
                expectedDocumentUID=annotation['documentUID'],
                expectedDocumentVersion=annotation['documentVersion'],
                expectedSectionId=annotation['sectionId'], changes=changes,
                nativeWriteRequired=True, clinicalApproval=False, notificationsEnabled=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--item-id', type=int, required=True)
    p.add_argument('--target', choices=sorted(STATES), required=True)
    p.add_argument('--rationale', required=True)
    p.add_argument('--operation-id', required=True)
    p.add_argument('--incorporated-version')
    p.add_argument('--summary', help='Explicit short web disposition summary; detailed rationale is preserved')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = prepare(json.loads(args.input.read_text()), args.item_id, args.target,
                     args.rationale, args.operation_id, args.incorporated_version, args.summary)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(action=result['action'], nativeWrites=0)))
