#!/usr/bin/env python3
"""Inventory existing workspace artefacts and exercise copied fictional recovery.

No native writes, credential export, live restoration or solution inclusion.
"""
import argparse
import hashlib
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

from ppg_workspace import validate
from ppg_source_paths import forbidden_path

ROOT = Path(__file__).resolve().parents[1]
OUTSIDE_SOLUTION = {'page','list','library','template','guide','receipts','archive','view','downloadable-tool','example-package','index','manual-tool','fictional-example','operator-guide','optional-local-manual-tool','frozen-report','technical-evidence','control-file','native-script','metric-dictionary','frozen-technical-projection','field-contract','optional-read-only-maintenance-tool','maintained-template','fictional-input','input-contract','native-view','manual-tool-and-fixtures','file'}
SECTIONS = {'local-tools','navigation','sharepoint-records','source-sync','scheduled-reports','native-pilots','archive'}


def safe_path(root, value, private=False):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value or any(ord(c)<32 for c in value):
        raise ValueError('Unsafe inventory path')
    if not private and forbidden_path(value): raise ValueError('Publication-private source path refused')
    if any(p.lower() in {'.git','.venv','node_modules','private','outputs'} for p in path.parts):
        raise ValueError('Private/non-source inventory path')
    if ('.local' in [p.lower() for p in path.parts]) != private or (private and path.parts[0]!='.local'):
        raise ValueError('Source and private receipt storage must stay separate')
    candidate = root / value
    if not candidate.resolve().is_relative_to(root.resolve()): raise ValueError('Inventory path escapes root')
    for item in [candidate,*candidate.parents]:
        if item == root: break
        if item.is_symlink(): raise ValueError('Symlink inventory path refused')
    return candidate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_exported_references(workflow, expected):
    """Verify solution-export declarations, not runtime connection access.

    Service readback can retain logical names while the saved export omits them.
    Check the actual exported representation before accepting a release candidate.
    """
    if (not isinstance(expected, dict) or not expected
            or any(not isinstance(v, str) or not v.strip() for v in expected.values())):
        raise ValueError('Expected logical reference names required')
    properties = workflow.get('properties') if isinstance(workflow, dict) else None
    references = properties.get('connectionReferences') if isinstance(properties, dict) else None
    if not isinstance(references, dict) or set(references) != set(expected):
        raise ValueError('Exported reference set mismatch')
    for key, logical_name in expected.items():
        reference = references[key]
        connection = reference.get('connection') if isinstance(reference, dict) else None
        if (not isinstance(connection, dict)
                or connection.get('connectionReferenceLogicalName') != logical_name):
            raise ValueError('Exported logical reference missing or changed')
    return True


def inventory(root=ROOT):
    manifest_path = safe_path(root,'config/workspace-manifest.json')
    original = manifest_path.read_bytes(); manifest = json.loads(original); validate(manifest)
    management = manifest.get('management',[])
    policies = {row['capabilityKey']:row for row in management}
    capabilities = {row['key']:row for row in manifest['capabilities']}
    if len(policies)!=len(management) or set(policies)!=set(capabilities):
        raise ValueError('Missing/duplicate capability management coverage')
    runbook = safe_path(root,'docs/artefact-inventory-recovery.md').read_text()
    tracked = subprocess.run(['git','ls-files','-z'],cwd=root,capture_output=True,check=True,timeout=30).stdout.decode().split('\0')
    hashes, coverage = {}, {}
    for key, policy in policies.items():
        if policy['recoverySection'] not in SECTIONS or ('## '+policy['recoverySection'].replace('-',' ').title()).lower() not in runbook.lower():
            raise ValueError('Missing recovery section')
        paths = set()
        for name in policy['sourcePaths']:
            path=safe_path(root,name)
            if not path.exists(): raise ValueError('Missing declared source: '+name)
            names = [name] if path.is_file() else [n for n in tracked if n.startswith(name.rstrip('/')+'/')]
            if not names: raise ValueError('Empty declared source directory')
            for item in names:
                file=safe_path(root,item)
                if not file.is_file() or file.stat().st_size>5*1024*1024: raise ValueError('Unsupported source entry')
                paths.add(item)
                hashes[item]=sha(file)
        if not paths: raise ValueError('No declared source coverage')
        receipts=[]
        for name in policy['receiptRoots']:
            path=safe_path(root,name,private=True)
            if not path.is_dir():
                receipts.append({'root':name,'status':'missing','sampledFiles':[]});continue
            # Bounded presence/hash inventory, never semantic acceptance of receipts.
            candidates=list(itertools.islice(path.rglob('*.json'),201)); sampled=[]
            for file in sorted(candidates[:200]):
                relative=file.relative_to(root).as_posix(); safe_path(root,relative,private=True)
                if file.is_file() and file.stat().st_size<=5*1024*1024:
                    sampled.append({'path':relative,'sha256':sha(file)})
            receipts.append({'root':name,'status':'present-unverified','sampleLimit':200,'truncated':len(candidates)>200,'sampledFiles':sampled})
        coverage[key]={'sourceFiles':sorted(paths),'receiptScope':'bounded-presence/hash sample' if policy['receiptRoots'] else 'no private receipt roots declared','localReceipts':receipts}
    artefacts=[]
    for artefact in manifest['artefacts']:
        key=artefact['capabilityKey']; policy=policies[key]; cap=capabilities[key]
        # Unknown future kinds must not silently become outside-solution resources.
        eligible=artefact['type'] not in OUTSIDE_SOLUTION
        artefacts.append({'key':artefact['key'],'kind':artefact['type'],'capabilityKey':key,
                          'maintainerLane':policy['maintainerLane'],'businessRoleAsRecorded':cap['responsibleRole'],
                          'environmentAlias':policy['environmentAlias'],'privateNativeIdentityRef':artefact['resourceRef'],
                          'nativeIdentityStatus':'requires private binding/readback reconciliation' if artefact['location']=='hosted' else 'not-applicable',
                          'sourceScope':'capability-shared source; not a native deployed-definition hash',
                          'sourceFiles':coverage[key]['sourceFiles'],'dependencyCapabilities':cap['dependencies'],
                          'connectionDependencies':policy['connectionDependencies'],'deploymentMethod':policy['deploymentMethod'],
                          'runtimeState':policy['runtimeState'],'solutionMembership':'unknown' if eligible else 'not-applicable',
                          'solutionEvidenceAtUtc':None,'recovery':'docs/artefact-inventory-recovery.md#'+policy['recoverySection']})
    if manifest_path.read_bytes()!=original or any(sha(safe_path(root,name))!=value for name,value in hashes.items()):
        raise ValueError('Source changed during inventory; capture again')
    return {'schemaVersion':1,'capturedAtUtc':datetime.now(timezone.utc).isoformat(),
            'scope':'local manifest/source/receipt presence; no native state or solution readback',
            'manifestSHA256':hashlib.sha256(original).hexdigest(),'capabilityCount':len(capabilities),
            'artefactCount':len(artefacts),'sourceSHA256':hashes,'coverage':coverage,'artefacts':artefacts,
            'unknownSolutionMembershipCount':sum(a['solutionMembership']=='unknown' for a in artefacts),
            'nativeWrites':0,'acceptedDeploymentOrRecovery':False}


def exercise_recovery(output, root=ROOT):
    """Fixed fictional export/recover shape only; cannot target a native object."""
    source=safe_path(root,'templates/recovery')
    manifest_path=safe_path(source,'fictional-record.json'); original_manifest=manifest_path.read_bytes(); manifest=json.loads(original_manifest)
    if (manifest.get('fictionalOnly') is not True
            or not all(isinstance(manifest.get(k),str) and manifest[k].startswith('FICTIONAL-') for k in ['caseUID','documentUID'])
            or not str(manifest.get('sourceRef','')).startswith('fictional://')
            or [v.get('version') for v in manifest.get('draftVersions',[])]!=['fixture-v1','fixture-v2']):
        raise ValueError('Fixed fictional fixture identities and versions required')
    originals={}
    for entry in [*manifest['draftVersions'],manifest['reference']]:
        path=safe_path(source,entry['source'])
        if sha(path)!=entry['sha256']: raise ValueError('Fixture source hash mismatch')
        originals[entry['source']]=path.read_bytes()
    output.mkdir(parents=True,exist_ok=False)
    for directory in ['original','export','recovered']:(output/directory).mkdir()
    for name,content in originals.items():(output/'export'/name).write_bytes(content)
    (output/'export'/'fictional-record.json').write_bytes(original_manifest)
    exported_manifest=(output/'export'/'fictional-record.json').read_bytes()
    if exported_manifest!=original_manifest: raise ValueError('Exported record differs')
    manifest=json.loads(exported_manifest)
    def write_record(directory,version,edited=False):
        draft=(output/'export'/version['source']).read_bytes()
        if edited: draft+=b'\nFICTIONAL human edit retained on the current copy.\n'
        (directory/'draft.txt').write_bytes(draft)
        reference=(output/'export'/manifest['reference']['source']).read_bytes()
        (directory/'reference.txt').write_bytes(reference)
        record={'caseUID':manifest['caseUID'],'documentUID':manifest['documentUID'],'sourceRef':manifest['sourceRef'],
                'version':version['version'],'draftLink':'draft.txt','draftSHA256':hashlib.sha256(draft).hexdigest(),
                'referenceLink':'reference.txt','referenceSHA256':hashlib.sha256(reference).hexdigest(),'fictionalOnly':True}
        (directory/'record.json').write_text(json.dumps(record,indent=2))
    write_record(output/'original',manifest['draftVersions'][-1],edited=True)
    pins={p.name:sha(p) for p in (output/'original').iterdir()}
    # Recover an older version from the exported copy into a distinct new target.
    write_record(output/'recovered',manifest['draftVersions'][0])
    record=json.loads((output/'recovered/record.json').read_text())
    for key in ['caseUID','documentUID','sourceRef']:
        if record[key]!=manifest[key]: raise ValueError('Recovered identity mismatch')
    for link,digest in [('draftLink','draftSHA256'),('referenceLink','referenceSHA256')]:
        if sha(safe_path(output/'recovered',record[link]))!=record[digest]: raise ValueError('Recovered link/hash mismatch')
    if record['draftSHA256']!=manifest['draftVersions'][0]['sha256']: raise ValueError('Recovered version differs')
    if pins!={p.name:sha(p) for p in (output/'original').iterdir()} or manifest_path.read_bytes()!=original_manifest:
        raise ValueError('Original copy changed')
    if any((source/name).read_bytes()!=content for name,content in originals.items()): raise ValueError('Source fixture changed')
    receipt={'schemaVersion':1,'scope':'copied fictional local export only','recoveredVersion':record['version'],
             'identityHashAndLinksVerified':True,'editedOriginalPreserved':True,'sourceFixturesPreserved':True,
             'nativeRestorePerformed':False,'nativeWrites':0}
    (output/'recovery-receipt.json').write_text(json.dumps(receipt,indent=2));return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--exercise-recovery',action='store_true')
    parser.add_argument('--workspace',type=Path,help='Reviewed workspace root containing its own manifest and source; never inferred from this toolkit')
    args=parser.parse_args()
    if args.exercise_recovery:
        result=exercise_recovery(args.output);print(json.dumps(result));return
    if args.workspace is None: raise ValueError('Explicit reviewed workspace root required')
    result=inventory(args.workspace)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'inventory.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ['artefactCount','capabilityCount','unknownSolutionMembershipCount','nativeWrites']}))


if __name__=='__main__':main()
