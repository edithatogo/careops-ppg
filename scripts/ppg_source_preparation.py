"""Prepare immutable evidence copies and evaluate deterministic source/citation fidelity."""
from __future__ import annotations
import argparse
import copy
import io
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import xml.etree.ElementTree as ET
import zipfile
from uuid import UUID
from urllib.parse import urlsplit
from ppg_evidence_cli import (Client, EvidenceError, MAX_BYTES, LABELS, config_checked,
                              digest, endpoint, extract, excerpts, pin, require,
                              root_json, validate, write, META)


def read_file(path, limit=MAX_BYTES):
    require(stat.S_ISREG(Path(path).lstat().st_mode), 'regular_input_required')
    fd=os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'regular_input_required')
        chunks=[];size=0
        while True:
            b=os.read(fd,min(65536,limit-size+1))
            if not b:
                break
            size+=len(b);require(size<=limit,'input_size_limit');chunks.append(b)
        return b''.join(chunks)
    finally:
        os.close(fd)


def verify_ingestion(original, native, name, policy='exact-bytes'):
    proof={'kind':'exact-bytes','originalSHA256':digest(original),'nativeSHA256':digest(native),'changedParts':[]}
    if original==native:
        return proof
    require(policy=='sharepoint-schema-attributes-v1' and Path(name).suffix.lower()=='.docx', 'native_byte_change_not_qualified')
    allowed={'customXml/item1.xml','customXml/itemProps1.xml'}
    meta='{http://schemas.microsoft.com/office/2006/metadata/properties/metaAttributes}'
    store='{http://schemas.openxmlformats.org/officeDocument/2006/customXml}'
    attributes={meta+'versionID',meta+'fieldsID',meta+'indexed',store+'itemID'}
    changes=[]
    try:
        with zipfile.ZipFile(io.BytesIO(original)) as a,zipfile.ZipFile(io.BytesIO(native)) as b:
            require(set(a.namelist())==set(b.namelist()) and len(a.namelist())==len(set(a.namelist())) and
                    len(b.namelist())==len(set(b.namelist())) and len(a.namelist())<=500 and
                    all(sum(x.file_size for x in z.infolist())<=20_000_000 for z in (a,b)),'native_docx_membership_changed')
            require(a.testzip() is None and b.testzip() is None,'native_docx_crc_failed')
            for part in sorted(a.namelist()):
                aa,bb=a.read(part),b.read(part)
                if aa==bb:
                    continue
                require(part in allowed,'native_docx_nonmetadata_part_changed')
                require(len(aa)<=MAX_BYTES and len(bb)<=MAX_BYTES and all(not re.search(br'<!\s*(DOCTYPE|ENTITY)',x,re.I) for x in (aa,bb)), 'native_metadata_xml_unsupported')
                decoded=[x.decode('utf-8-sig') for x in (aa,bb)]
                require(all('\x00' not in x and not re.search(r'<!\s*(DOCTYPE|ENTITY)',x,re.I) for x in decoded),'native_metadata_xml_unsupported')
                x,y=[ET.fromstring(x) for x in decoded]
                root='{http://schemas.microsoft.com/office/2006/metadata/contentType}contentTypeSchema' if part.endswith('/item1.xml') else store+'datastoreItem'
                require(x.tag==y.tag==root,'native_metadata_root_changed')
                left,right=list(x.iter()),list(y.iter());require(len(left)==len(right),'native_metadata_structure_changed')
                attrs=[]
                for n,(old,new) in enumerate(zip(left,right)):
                    require(old.tag==new.tag and old.text==new.text and old.tail==new.tail and len(old)==len(new), 'native_metadata_content_changed')
                    for attr in sorted(set(old.attrib)|set(new.attrib)):
                        if old.get(attr)==new.get(attr):
                            continue
                        require(attr in attributes,'native_metadata_attribute_not_qualified')
                        if part.endswith('/itemProps1.xml'):
                            require(n==0 and attr==store+'itemID' and all(UUID(v.strip('{}')).int!=0 for v in (old.get(attr,''),new.get(attr,''))), 'native_store_id_change_invalid')
                        elif attr in {meta+'versionID',meta+'fieldsID'}:
                            require(all(re.fullmatch(r'[a-fA-F0-9]{32}',v or '') for v in (old.get(attr),new.get(attr))), 'native_schema_id_change_invalid')
                        else:
                            require(attr==meta+'indexed' and all(v in {None,'true','false'} for v in (old.get(attr),new.get(attr))), 'native_schema_attribute_change_invalid')
                        attrs.append({'element':n,'attribute':attr,'beforeSHA256':digest((old.get(attr) or '').encode()),'afterSHA256':digest((new.get(attr) or '').encode())})
                changes.append({'part':part,'attributes':attrs})
    except (zipfile.BadZipFile,ET.ParseError,ValueError):
        raise EvidenceError('native_ingestion_not_qualified') from None
    before=extract(original,name);after=extract(native,name)
    require(before[:3]==after[:3], 'native_supported_text_changed')
    return proof|{'kind':policy,'changedParts':changes,'supportedTextAndLocatorsEqual':True,'otherPackagePartsByteExact':True}


def prepare(job_file, input_directory, output, pdf_tool=None):
    raw=read_file(job_file,1_000_000);job=json.loads(raw)
    require(job.get('schemaVersion')==1 and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',job.get('preparationId','')),
            'invalid_preparation_identity')
    sources=job.get('sources');require(isinstance(sources,list) and 0<len(sources)<=5,'select_one_to_five_sources')
    root=Path(input_directory).resolve(strict=True);output=Path(output).absolute()
    require(root.is_dir() and not output.exists() and root!=output and root not in output.parents and output not in root.parents,
            'new_disjoint_output_required')
    ids=set()
    for s in sources:
        require(isinstance(s,dict) and isinstance(s.get('sourceId'),str) and
                re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',s['sourceId']) and s['sourceId'] not in ids,'invalid_source_identity')
        ids.add(s['sourceId'])
        require(s.get('authorityLabel') in LABELS and
                all(isinstance(s.get(k),str) and s[k].strip() for k in
                    ('originalReference','originalVersionRef','sourceEdition','evaluationNeedle')) and
                all(re.fullmatch(r'[a-f0-9]{64}',s.get(k,'')) for k in ('sha256','expectedTextSHA256')),
                'source_provenance_or_expectation_missing')
        require(s.get('ingestionPolicy','exact-bytes') in {'exact-bytes','sharepoint-schema-attributes-v1'},'unsupported_ingestion_policy')
    output.mkdir(mode=0o700);(output/'sources').mkdir(mode=0o700);(output/'extracted').mkdir(mode=0o700)
    try:
        prepared=[]
        for s in sources:
            relative=Path(s['file'])
            require(not relative.is_absolute() and '..' not in relative.parts,'unsafe_input_path')
            source=(root/relative).resolve(strict=True)
            require(root in source.parents,'source_outside_input_root')
            original=read_file(source);require(digest(original)==s['sha256'],'original_source_hash_mismatch')
            text,locators,method,warnings=extract(original,source.name,pdf_tool)
            require(digest(text.encode())==s['expectedTextSHA256'],'source_extraction_expectation_mismatch')
            require(s['evaluationNeedle'].casefold() in text.casefold(),'evaluation_needle_not_found')
            name=job['preparationId']+'-'+s['sourceId']+source.suffix.lower()
            target=output/'sources'/name
            with target.open('xb') as f:
                f.write(original)
            target.chmod(0o600)
            require(read_file(target)==original,'prepared_copy_changed')
            write(output/'extracted'/(s['sourceId']+'.json'),{'text':text,'lineMap':locators,'extraction':method,'warnings':warnings})
            prepared.append({k:v for k,v in s.items() if k!='file'}|{'name':name,'originalFileName':source.name,'bytes':len(original),'extraction':method,
                             'extractionWarnings':warnings})
        manifest={'schemaVersion':1,'kind':'cli-assistant-source-preparation-v1','preparationId':job['preparationId'],
                  'jobSHA256':digest(raw),'preparedAtUtc':datetime.now(timezone.utc).isoformat(),
                  'sources':prepared,'status':'EVIDENCE PREPARATION ONLY / AUTHORITY UNCONFIRMED',
                  'originalSourceWrites':False,'wordBodyGenerationPerformed':False,'conversationalRetrievalQualified':False}
        write(output/'manifest.json',manifest)
        return {'preparationId':job['preparationId'],'preparedSources':len(prepared),'originalSourceWrites':False,
                'wordBodyGenerationPerformed':False,'paidAIRuntimeUsed':False}
    except Exception as error:
        write(output/'failure.json',{'status':'NOT PREPARED','reason':str(error) if isinstance(error,EvidenceError) else 'preparation_failed',
                                    'manifestCommitted':False,'originalSourceWrites':False})
        raise


def evaluate(preparation, bundle, config, publication, client=None, live=True):
    config=config_checked(config);preparation=Path(preparation);bundle=Path(bundle)
    manifest_raw=read_file(preparation/'manifest.json');manifest=json.loads(manifest_raw)
    require(manifest.get('kind')=='cli-assistant-source-preparation-v1','invalid_preparation_manifest')
    run=json.loads(read_file(bundle/'run.json'));require(run['scope']==config['prefix'],'bundle_scope_mismatch')
    sources=json.loads(read_file(bundle/'sources.json',12_000_000));indexed={s['sourceId']:s for s in sources}
    expected=manifest['sources'];checks=[]
    add=lambda name,ok:checks.append({'check':name,'passed':bool(ok)})
    add('exact_selected_source_membership',len(indexed)==len(sources) and set(indexed)=={s['sourceId'] for s in expected})
    add('search_visibility_check_performed',run['searchStatus'] in {'results','no-indexed-matches'} and all('searchVisibility' in s for s in sources))
    add('publication_manifest_identity',publication.get('manifestSHA256')==digest(manifest_raw) and publication.get('preparationId')==manifest['preparationId'])
    native_receipt=False
    if live:
        client=client or Client(config)
        try:
            receipt_name=manifest['preparationId']+'.sources.json'
            api,_=endpoint(config,config['folder']+'/'+receipt_name)
            before=pin(root_json(client.get(api+'?$select='+META)))
            remote=client.get(api+'/$value',binary=True)
            after=pin(root_json(client.get(api+'?$select='+META)))
            receipt=json.loads(remote)
            native_receipt=(before==after and digest(remote)==publication.get('receiptSHA256') and
                            receipt.get('manifestSHA256')==digest(manifest_raw) and receipt.get('preparedManifest')==manifest)
            receipt_pin=publication['files'][-1]['pin']
            native_receipt=native_receipt and all(before[k]==str(receipt_pin[k]) for k in ('UniqueId','ETag','Length','ServerRelativeUrl'))
        except (EvidenceError,KeyError,ValueError):
            native_receipt=False
        add('native_manifest_readback_and_stable_pin',native_receipt)
    citations=0
    for e in expected:
        sid=e['sourceId'];s=indexed.get(sid,{})
        require(isinstance(e['name'],str) and Path(e['name']).name==e['name'] and e['name'].startswith(manifest['preparationId']+'-'), 'invalid_prepared_member_path')
        if s.get('status')=='retrieved':
            require(isinstance(s.get('rawFile'),str) and Path(s['rawFile']).name==s['rawFile'], 'invalid_retrieved_member_path')
        raw_path=preparation/'sources'/e['name']
        integrity=next((x for x in publication.get('sourceIntegrity',[]) if x['sourceId']==sid),{})
        native_hash=integrity.get('proof',{}).get('nativeSHA256',e['sha256'])
        equivalent=False
        if s.get('status')=='retrieved':
            try:
                proof=verify_ingestion(read_file(raw_path),read_file(bundle/s['rawFile']),e['name'],e.get('ingestionPolicy','exact-bytes'))
                equivalent=(proof==integrity.get('proof',proof) and proof['originalSHA256']==e['sha256'])
            except EvidenceError:
                equivalent=False
        add(sid+':prepared_bytes_or_qualified_schema_ingestion',equivalent)
        good=(s.get('status')=='retrieved' and s.get('binarySHA256')==native_hash and
              s.get('sha256')==e['expectedTextSHA256'] and s.get('authorityLabel')==e['authorityLabel'] and
              s.get('extraction')==e['extraction'])
        add(sid+':native_source_integrity',good)
        if not good:
            continue
        expected_path=config['folder']+'/'+e['name']
        published=next((f for f in publication.get('files',[]) if f['name']==e['name']),{})
        add(sid+':native_destination_identity',urlsplit(s['canonicalUrl']).path==expected_path and
            published.get('pin',{}).get('UniqueId')==s['nativeUniqueId'] and
            published.get('pin',{}).get('ETag')==s['nativePin']['ETag'])
        answer=excerpts([s],e['evaluationNeedle'],0)
        positive=validate(answer,[s],config['prefix'],bundle,config,client if live else None)
        add(sid+':positive_exact_citation',positive['mechanicallyValid'] and len(answer['claims'])>0)
        citations+=positive['citationsChecked']
        for key,value in [('quote','FICTIONAL ALTERED QUOTE'),('nativeVersionRef','wrong-edition'),
                          ('binarySHA256','0'*64),('nativeUniqueId','22222222-2222-4222-8222-222222222222')]:
            altered=copy.deepcopy(answer);altered['claims'][0]['citations'][0][key]=value
            add(sid+':reject_changed_'+key,not validate(altered,[s],config['prefix'],bundle,config)['mechanicallyValid'])
        changed=copy.deepcopy(s);changed['text']+='\nALTERED SOURCE'
        add(sid+':reject_changed_source_text',not validate(answer,[changed],config['prefix'],bundle,config)['mechanicallyValid'])
        for state in ('denied','missing','unsupported','changed-during-read'):
            unavailable={'sourceId':sid,'status':state}
            unknown=excerpts([unavailable],e['evaluationNeedle'],0)
            add(sid+':unknown_for_'+state,unknown['status']=='unknown' and not unknown['claims'] and
                validate(unknown,[unavailable],config['prefix'],bundle,config)['mechanicallyValid'])
        add(sid+':no_actions_or_authority_claims',answer['actionsPerformed']==[] and answer['policyApproved'] is False and
            all(c['assertsCurrentAuthority'] is False for c in answer['claims']))
    passed=all(c['passed'] for c in checks)
    visibility=[{'sourceId':s['sourceId'],'status':s['status'],'visibility':s.get('searchVisibility')} for s in sources]
    return {'schemaVersion':1,'preparationId':manifest['preparationId'],'deterministicChecksPassed':passed,
            'sourcePreparationQualified':passed and live and native_receipt,'checks':checks,'citationsChecked':citations,
            'searchVisibility':visibility,'searchDiscoveryObserved':bool(sources) and all(s.get('searchVisibility')=='returned-by-this-query' for s in sources),
            'indexingBoundary':'A bounded query miss is indexing-unconfirmed; no recrawl or absence inference.',
            'liveVersionChecks':live,'conversationalRetrievalQualified':False,'semanticReviewPerformed':False,
            'paidAIRuntimeUsed':False,'originalSourceWrites':False,'evaluationSharePointWrites':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--job',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--pdf-tool',type=Path)
    v=sub.add_parser('verify-ingestion');v.add_argument('--original',type=Path,required=True);v.add_argument('--native',type=Path,required=True);v.add_argument('--name',required=True);v.add_argument('--policy',required=True)
    e=sub.add_parser('evaluate');e.add_argument('--preparation',type=Path,required=True);e.add_argument('--bundle',type=Path,required=True);e.add_argument('--config',type=Path,required=True);e.add_argument('--publication',type=Path,required=True);e.add_argument('--output',type=Path,required=True);e.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    try:
        if args.command=='prepare':
            report=prepare(args.job,args.input,args.output,args.pdf_tool)
        elif args.command=='verify-ingestion':
            print(json.dumps(verify_ingestion(read_file(args.original),read_file(args.native),args.name,args.policy)))
            return 0
        else:
            report=evaluate(args.preparation,args.bundle,json.loads(args.config.read_text()),json.loads(args.publication.read_text()),live=not args.offline)
            write(args.output,report)
        print(json.dumps(report if args.command=='prepare' else {k:report[k] for k in ('deterministicChecksPassed','sourcePreparationQualified','citationsChecked','searchDiscoveryObserved','conversationalRetrievalQualified')}))
        return 1 if report.get('deterministicChecksPassed') is False else 0
    except (EvidenceError,OSError,ValueError,KeyError,TypeError):
        print(json.dumps({'status':'failed','reason':'Source preparation/evaluation failed; preserve partial evidence and original files.'}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
