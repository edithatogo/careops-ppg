"""Offline PPG migration reconciliation. Never authorises cutover or writes a tenant."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

KEYS={'catalogue':'DocumentUID','cases':'CaseUID','readiness':'EventUID',
      'assurance':'EventUID','consultation':'EventUID','evidence':'NativeFileUniqueId'}


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def identity(value):
    if not isinstance(value,str):
        raise ValueError('identity must be an existing UUID string')
    parsed = UUID(value)
    if parsed.int == 0:
        raise ValueError('identity must not be the nil UUID')
    return str(parsed)


def load_export(raw):
    def unique_object(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate JSON key: '+key)
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique_object)


def populated_reference(value):
    # Only null, absent and empty text represent an unrecorded optional lookup.
    return value is not None and value != ''


def validate_history(rows,fields):
    dependencies={uid:set() for uid in rows}
    dependents={uid:set() for uid in rows}
    for uid,row in rows.items():
        for field in fields:
            if populated_reference(row.get(field)):
                parent=identity(row[field])
                dependencies[uid].add(parent)
                dependents[parent].add(uid)
    ready=[uid for uid,parents in dependencies.items() if not parents]
    visited=0
    while ready:
        parent=ready.pop();visited+=1
        for child in dependents[parent]:
            dependencies[child].remove(parent)
            if not dependencies[child]:ready.append(child)
    if visited != len(rows):raise ValueError('cyclic event history')


def validate(bundle):
    if type(bundle.get('schemaVersion')) is not int or bundle['schemaVersion'] != 1 or set(bundle.get('datasets',{})) != set(KEYS):
        raise ValueError('complete six-dataset normalized export required')
    if not isinstance(bundle.get('identityExceptions'),list):
        raise ValueError('explicit identity exception array required')
    indexed={}
    for dataset,key in KEYS.items():
        rows=bundle['datasets'][dataset]
        if not isinstance(rows,list):raise ValueError('dataset must be an array')
        indexed[dataset]={}
        for row in rows:
            uid=identity(row[key])
            if uid in indexed[dataset]:raise ValueError('duplicate persistent identity: '+dataset)
            canonical(row)
            indexed[dataset][uid]=row
    for row in indexed['cases'].values():
        links=row.get('linkedDocumentUIDs')
        if isinstance(links,str):links=load_export(links)
        if not isinstance(links,list) or not links:raise ValueError('explicit case document links required')
        if len({identity(uid) for uid in links}) != len(links):raise ValueError('duplicate case document link')
        if any(identity(uid) not in indexed['catalogue'] for uid in links):
            raise ValueError('orphan case document link')
    for dataset in ('readiness','assurance','consultation'):
        for row in indexed[dataset].values():
            if identity(row['CaseUID']) not in indexed['cases']:raise ValueError('orphan event case link')
            refs={'SupersedesEventUID':dataset}
            if dataset in ('assurance','consultation'):refs['ParentEventUID']=dataset
            if dataset == 'assurance':refs['ReadinessEventUID']='readiness'
            for field,related_dataset in refs.items():
                if not populated_reference(row.get(field)):continue
                uid=identity(row[field]);related=indexed[related_dataset].get(uid)
                if related is None:raise ValueError('orphan event reference: '+field)
                if related_dataset == dataset and uid == identity(row['EventUID']):
                    raise ValueError('self event reference: '+field)
                if identity(related['CaseUID']) != identity(row['CaseUID']):
                    raise ValueError('cross-case event reference: '+field)
        validate_history(indexed[dataset],('SupersedesEventUID',) if dataset == 'readiness' else ('ParentEventUID','SupersedesEventUID'))
    for row in indexed['evidence'].values():
        if populated_reference(row.get('PPGDocumentUID')) and identity(row['PPGDocumentUID']) not in indexed['catalogue']:
            raise ValueError('orphan evidence document link')
    return indexed


def reconcile(source,target):
    left,right=validate(source),validate(target)
    differences=[];counts={}
    for dataset in KEYS:
        a,b=left[dataset],right[dataset]
        counts[dataset]=dict(source=len(a),target=len(b))
        for uid in sorted(set(a)|set(b)):
            if uid not in a or uid not in b:
                differences.append(dict(dataset=dataset,identity=uid,kind='extra-target' if uid not in a else 'missing-target'))
                continue
            fields=[key for key in sorted(set(a[uid])|set(b[uid]))
                    if (key in a[uid]) != (key in b[uid]) or canonical(a[uid].get(key)) != canonical(b[uid].get(key))]
            if fields:differences.append(dict(dataset=dataset,identity=uid,kind='field-mismatch',fields=fields))
    exceptions=bool(source['identityExceptions'] or target['identityExceptions'])
    return dict(structurallyReconciled=not differences and not exceptions,counts=counts,
                differences=differences,identityExceptionsPresent=exceptions,
                sourceBundleSHA256=hashlib.sha256(canonical(source).encode()).hexdigest(),
                targetBundleSHA256=hashlib.sha256(canonical(target).encode()).hexdigest(),
                scope='Supplied normalized values and explicit relationships only; no native export/ACL/history proof.',
                nativeImportPerformed=False,securityParityVerified=False,historyParityVerified=False,
                sourceWrites=False,targetWrites=False,cutoverAuthorised=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--target',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();raw_source=args.source.read_bytes();raw_target=args.target.read_bytes()
    report=reconcile(load_export(raw_source),load_export(raw_target))
    report['sourceFileSHA256']=hashlib.sha256(raw_source).hexdigest();report['targetFileSHA256']=hashlib.sha256(raw_target).hexdigest()
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'reconciliation.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if report['structurallyReconciled'] else 1


if __name__=='__main__':raise SystemExit(main())
