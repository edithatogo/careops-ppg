"""Bounded independent proof producer; read-only CLI transport, local outputs only.

No upload/copy/event, login, connection, permission or flow mutation is implemented.
Stage after a separately reviewed actual copy. Finalize only after a separately
authorised create-only proof upload and reviewed storage-permission observation.
"""
import argparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit, parse_qs, unquote
from urllib.request import build_opener, HTTPRedirectHandler

from binary_publication import (SCOPE, complete, digest, metadata,
                                normalize_sharepoint_file, require, text, token, verify_downloads)

FRAME = frozenset(('case','originalSource','baseline','template','preparedReceipt','ownershipCommit',
                   'readinessHistory','consultationHistory','assuranceHistory'))
CASE_FIELDS = frozenset(('CaseUID','Title','linkedDocumentUIDs','sourceBaselineRef','accountableRole',
                        'proposedOutcome','nextAction','targetDate','caseStatus','evidenceDraftLink','OData__UIVersionString'))
CODES = ('committee','officer','coordinator','authorisation')
LABELS = ('Committee endorsement','Officer signoff','Coordinator check','Final authorisation')
COLLECTIONS = frozenset(('readinessHistory','consultationHistory','assuranceHistory'))


def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def normalized(value):
    if isinstance(value,dict):return {k:normalized(v) for k,v in value.items() if k!='odata.id'}
    if isinstance(value,list):return [normalized(v) for v in value]
    return value
def utc(value):
    require(text(value),'Missing native chronology')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    require(result.tzinfo is not None,'Naive chronology refused')
    return result
def row_identity(row):
    require(isinstance(row,dict) and type(row.get('Id')) is int and row['Id']>0 and text(row.get('GUID'))
            and token(row.get('odata.etag')),'Actual native row identity and opaque token required')
def scoped(row,scope):return all(row.get(k)==scope[k] for k in SCOPE)
def flatten(group):
    result={}
    for name,action in group.items():
        require(name not in result,'Ambiguous reviewed action name');result[name]=action
        for branch in (action.get('actions',{}),action.get('else',{}).get('actions',{})):
            child=flatten(branch);require(not result.keys()&child.keys(),'Ambiguous reviewed action name');result.update(child)
    return result


def validate_binding(b,definition):
    require(b.get('qualificationOnly') is True,'Fictional qualification only')
    require(text(b.get('readinessDateTimeZone')) and isinstance(b.get('readinessAssessmentDate'),str)
            and re.fullmatch(r'\d{4}-\d{2}-\d{2}',b['readinessAssessmentDate']) is not None,
            'Explicit reviewed DateOnly timezone and assessment date required')
    ZoneInfo(b['readinessDateTimeZone'])
    require(isinstance(b.get('scope'),dict) and all(text(b['scope'].get(k)) for k in SCOPE)
            and b['scope']['CaseUID'].startswith('LC-FICTIONAL-'),'Exact fictional prepared scope required')
    require(digest(definition)==b['copy']['definitionSHA256'],'Reviewed exact native copy definition required')
    require(re.fullmatch(r'[0-9a-fA-F-]{36}',b['copy']['flowName']) is not None
            and re.fullmatch(r'[A-Za-z0-9-]{1,100}',b['copy']['environment']) is not None
            and re.fullmatch(r'[A-Za-z0-9-]{1,100}',b['copy']['runId']) is not None,'Explicit safe flow/environment/run required')
    parsed=urlsplit(b['site']);require(parsed.scheme=='https' and parsed.netloc and not parsed.query
            and not parsed.fragment and not parsed.username and not parsed.password,'Canonical HTTPS site required')
    origin=parsed.scheme+'://'+parsed.netloc
    src=metadata(b['source']);dst=metadata(b['issued'])
    require(src['UniqueId']!=dst['UniqueId'] and src['DocumentReference']!=dst['DocumentReference'],'Separate source and issued object required')
    for pin in (src,dst):
        url=urlsplit(pin['DocumentReference']);require(url.scheme+'://'+url.netloc==origin and url.path.startswith(parsed.path+'/')
            and not url.query and not url.fragment and all(v not in url.path for v in ('..','%','\\')),'Bound same-site canonical file required')
    folder=b['qualificationFolder'];require(folder.startswith(parsed.path+'/')
            and all(x not in folder for x in ('..','%','\\','?','#')),'Reviewed isolated same-site folder required')
    issued_path=urlsplit(dst['DocumentReference']).path
    require(issued_path.rsplit('/',1)[0]==folder and issued_path.rsplit('/',1)[1].startswith('FICTIONAL-issued-')
            and issued_path.endswith('.docx'),'Exact isolated issued DOCX required')
    require(set(b['frame'])==FRAME,'Complete protected frame required')
    for name,entry in b['frame'].items():
        require(set(entry)=={'url','expected'} and entry['url'].startswith(b['site']+'/_api/'),'Literal reviewed same-site frame read required')
        if name in COLLECTIONS:
            require(re.fullmatch(re.escape(b['site'])+r"/_api/web/lists\(guid'[0-9a-fA-F-]{36}'\)/items",entry['url']) is not None,
                    'Complete literal history; filters, projections and pagination shortcuts refused')
            complete(entry['expected'])
    require(CASE_FIELDS<=b['frame']['case']['expected'].keys(),'Full human case fields required')
    require('?' not in b['frame']['case']['url'],'Case projection queries refused')
    actions=flatten(definition['actions']);writers={n:a for n,a in actions.items() if a.get('type')=='OpenApiConnection'
            and a['inputs']['parameters'].get('parameters/method')!='GET'}
    require(set(writers)=={'Copy_binary_absent_only','Create_binary_publication'},'Reviewed two-writer profile required')
    require(all(a['inputs'].get('retryPolicy')=={'type':'none'} for a in writers.values()),'No automatic writer retries')
    cp=writers['Copy_binary_absent_only']['inputs']['parameters']
    require('parameters/body' not in cp and 'bOverWrite=false' in cp['parameters/uri'],'Body-free absent-only copy required')
    return origin,actions


def validate_domain(frame,b,authorisation):
    """Recheck actual complete history; no qualified boolean or latest-date choice."""
    scope=b['scope'];now=datetime.now(timezone.utc);case=frame['case']
    require(case['CaseUID']==scope['CaseUID'] and case['evidenceDraftLink']==scope['DocumentReference'], 'Case/source selection changed')
    histories={k:complete(frame[k]) for k in COLLECTIONS}
    ready=[r for r in histories['readinessHistory'] if scoped(r,scope)]
    require(len(ready)==1,'Unique exact-revision readiness finding required');finding=ready[0];row_identity(finding)
    require(finding.get('Finding')=='Ready for decision' and finding.get('FictionalTest') is True
            and finding.get('ConditionsState') in ('None recorded','Resolved') and not finding.get('SupersedesEventUID')
            and all(text(finding.get(k)) for k in ('EventUID','AssessorName','FindingSummary','EvidenceReference','AssessedOn')),
            'Evidenced current fictional readiness required')
    require(len([r for r in histories['readinessHistory'] if r.get('EventUID')==finding['EventUID']])==1
            and not any(r.get('SupersedesEventUID')==finding['EventUID'] for r in histories['readinessHistory']), 'Readiness identity/correction conflict')
    # AssessedOn is a measured SharePoint DateOnly field, not an assessment instant.
    # Preserve its reviewed local date and use actual native Created for recording order.
    zone=ZoneInfo(b['readinessDateTimeZone'])
    assessment=utc(finding['AssessedOn']).astimezone(zone)
    readiness_recorded=utc(finding.get('Created'))
    require(assessment.time().isoformat()=='00:00:00'
            and assessment.date().isoformat()==b['readinessAssessmentDate']
            and assessment.date()<=now.astimezone(zone).date()
            and assessment.date()<=readiness_recorded.astimezone(zone).date()
            and readiness_recorded<=now,'Reviewed local assessment date or native recording time inconsistent')
    profile=b['fictionalRouteProfile'];require(set(profile)=={'reference','version','FictionalTest','grantsRealAuthority'}
            and profile['FictionalTest'] is True and profile['grantsRealAuthority'] is False,'Reviewed fictional profile required')
    uid_prefix='LC03-PURPOSE-'+b['requestReference']+'-'+b['source']['UniqueId'].lower()+'-v'+b['source']['nativeVersion']+'-'
    selected=[];assurance=histories['assuranceHistory']
    for index,code in enumerate(CODES):
        uid=uid_prefix+code;matches=[r for r in assurance if r.get('EventUID')==uid];require(len(matches)==1,'Missing or ambiguous retained purpose')
        r=matches[0];row_identity(r)
        require(scoped(r,scope) and r.get('FictionalTest') is True and r.get('Stage')=='Decision' and r.get('RecordState')=='Recorded'
                and r.get('ConditionsState') in ('None recorded','Resolved') and not r.get('SupersedesEventUID')
                and r.get('DecisionOutcome')==('Approved (recorded)' if index==3 else 'Endorsed (recorded)')
                and r.get('ReadinessEventUID')==finding['EventUID'] and r.get('ParentEventUID')==(selected[-1]['EventUID'] if selected else None)
                and r.get('DecisionReference')==profile['reference']+'/'+profile['version']+'/'+digest(profile)+'/'+code,
                'Purpose scope/profile/parent/readiness relation changed')
        require(all(text(r.get(k)) for k in ('ActorName','Summary','EvidenceReference','ConditionsNotes','NextAction'))
                and r['Summary']=='FICTIONAL '+LABELS[index]+': '+r['ConditionsNotes'] and len(r['ConditionsNotes'])<=180
                and r['ActorName'].startswith('FICTIONAL ') and r['EvidenceReference'].startswith('fictional://')
                and utc(r.get('OccurredOn'))<=utc(r.get('Created'))<=now
                and utc(r['OccurredOn'])>=(utc(selected[-1]['OccurredOn']) if selected else readiness_recorded)
                and utc(r['Created'])>=(utc(selected[-1]['Created']) if selected else readiness_recorded),
                'Purpose evidence or chronology changed')
        selected.append(r)
    uids={r['EventUID'] for r in selected}
    require(normalized(authorisation)==normalized(selected[-1]),'Copy receipt final authorisation differs from retained row')
    require(not any(r.get('SupersedesEventUID') in uids for r in assurance),'Purpose superseded')
    require(all(r.get('EventUID') in uids for r in assurance if scoped(r,scope)),'Adverse/competing/later exact-scope assurance requires reconciliation')
    roles=b['requiredFictionalRoles'];require(isinstance(roles,list) and bool(roles) and len(set(roles))==len(roles)
            and all(text(r) and r.startswith('FICTIONAL ') for r in roles),'Reviewed existing fictional role plan required')
    consultation=[r for r in histories['consultationHistory'] if scoped(r,scope)]
    require(all(r.get('SubjectRole') in roles and r.get('EventKind')=='Consultation' for r in consultation),'Unknown consultation role/kind')
    selected_consult=[]
    for role in roles:
        rs=[r for r in consultation if r['SubjectRole']==role];requests=[r for r in rs if not r.get('ParentEventUID')]
        require(len(rs)==2 and len(requests)==1,'Unique consultation request/response required')
        req=requests[0];resp=next(r for r in rs if r is not req)
        for r in (req,resp):row_identity(r);require(r.get('FictionalTest') is True and not r.get('SupersedesEventUID'),'Consultation correction/real scope refused')
        require(req.get('RecordState')=='Pending response' and req.get('ConditionsState')=='None recorded'
                and resp.get('ParentEventUID')==req.get('EventUID') and resp.get('RecordState')=='Responded'
                and resp.get('ConditionsState') in ('None recorded','Resolved')
                and all(text(resp.get(k)) for k in ('Summary','EvidenceReference','NextAction'))
                and utc(req.get('OccurredOn'))<=utc(resp.get('OccurredOn'))<=readiness_recorded
                and utc(req.get('OccurredOn'))<=utc(req.get('Created'))<=utc(resp.get('Created'))<=readiness_recorded
                and utc(resp['OccurredOn'])<=utc(resp['Created'])
                and utc(resp['OccurredOn']).astimezone(zone).date()<=assessment.date(),
                'Consultation unresolved or native recording/date chronology inconsistent')
        selected_consult.extend((req,resp))
    ids={r['EventUID'] for r in selected_consult}
    require(all(len([r for r in histories['consultationHistory'] if r.get('EventUID')==uid])==1 for uid in ids)
            and not any(r.get('SupersedesEventUID') in ids for r in histories['consultationHistory']),'Consultation identity/correction conflict')


class Capture:
    def __init__(self,path):
        self.path=Path(path);self.path.mkdir(parents=False,exist_ok=False);self.hashes={}
    def write(self,name,raw):
        require(Path(name).name==name,'Local evidence basename required')
        with (self.path/name).open('xb') as f:f.write(raw)
        self.hashes[name]=sha(raw)
    def json(self,name,value):self.write(name,canonical(value))
    def hold(self,error):self.json('held.json',{'qualified':False,'nativeWrites':0,'reason':str(error),'preservedFiles':self.hashes})


def read_history(t,url,c=None,prefix='history'):
    """Follow only actual same-collection continuations, preserving every page.

    The reviewed initial URL stays unfiltered and unprojected. No caller-supplied
    cursor, inferred offset or favorable first page becomes a complete history.
    Binding preparation may use this same read-only helper for its expected frame.
    """
    base=urlsplit(url)
    require(base.scheme=='https' and base.netloc and not base.username and not base.password
            and not base.query and not base.fragment
            and re.fullmatch(r"(?:/[^?#]*)?/_api/web/lists\(guid'[0-9a-fA-F-]{36}'\)/items",base.path),
            'Literal unfiltered HTTPS history collection required')
    pages=[];rows=[];seen=set();next_url=url
    markers=('nextLink','@nextLink','odata.nextLink','@odata.nextLink')
    while next_url:
        require(next_url not in seen and len(pages)<50,'Cyclic or excessive history continuation')
        seen.add(next_url)
        page=t.get_json(next_url)
        require(isinstance(page,dict) and isinstance(page.get('value'),list),'Missing native history page')
        pages.append(page)
        if c is not None:c.json(prefix+'-page'+str(len(pages))+'.json',page)
        rows.extend(page['value'])
        require(len(rows)<=5000,'History exceeds reviewed proof bound')
        for row in page['value']:row_identity(row)
        require(len({row['Id'] for row in rows})==len(rows)
                and len({row['GUID'].lower() for row in rows})==len(rows),'Duplicate history identity across pages')
        supplied=[page[k] for k in markers if page.get(k)]
        require(all(isinstance(link,str) for link in supplied),'Native history continuation must be a URL')
        links=set(supplied)
        require(len(links)<=1,'Conflicting history continuations')
        next_url=next(iter(links),None)
        if next_url:
            require(isinstance(next_url,str),'Native history continuation must be a URL')
            target=urlsplit(next_url);query=parse_qs(target.query,keep_blank_values=True)
            require(target.scheme==base.scheme and target.netloc==base.netloc
                    and not target.username and not target.password and not target.fragment
                    and unquote(target.path).lower()==base.path.lower()
                    and set(query)<= {'$skiptoken','$top'}
                    and len(query.get('$skiptoken',[]))==1 and text(query['$skiptoken'][0])
                    and ('$top' not in query or len(query['$top'])==1
                         and query['$top'][0].isdigit() and 0<int(query['$top'][0])<=5000),
                    'Only actual same-collection opaque history continuation permitted')
    if len(pages)==1:
        complete(pages[0])
        return pages[0]
    result={k:v for k,v in pages[0].items() if k not in markers}
    result['value']=rows
    complete(result)
    return result


def read_frame(b,t,c,prefix):
    frame={}
    for name in sorted(FRAME):
        url=b['frame'][name]['url']
        actual=read_history(t,url,c,prefix+'-'+name) if name in COLLECTIONS else t.get_json(url)
        c.json(prefix+'-'+name+'.json',actual)
        if name in COLLECTIONS:
            for row in complete(actual):row_identity(row)
        require(normalized(actual)==normalized(b['frame'][name]['expected']),'Protected frame changed: '+name)
        frame[name]=actual
    return frame


def publication_action_ineligibility(definition,rows,run_id,name):
    """Narrow proof of nonexecution; omitted action is never called Skipped.

    Only an observed Skipped ancestor or an exact terminal sibling runAfter
    barrier qualifies an omission. No branch-expression, termination, inferred
    predecessor status, or eligible/mixed dependency extrapolation is used.
    """
    observed={r['name']:r for r in rows}
    require(len(observed)==len(rows) and all(r.get('runName')==run_id for r in rows),
            'Ambiguous or foreign-run action inventory')
    nodes={}
    def visit(group,ancestors=()):
        for key,action in group.items():
            require(key not in nodes,'Ambiguous reviewed action name')
            nodes[key]=(action,ancestors,group)
            visit(action.get('actions',{}),ancestors+(key,))
            visit(action.get('else',{}).get('actions',{}),ancestors+(key,))
    visit(definition['actions'])
    require(name in nodes,'Publication action missing from reviewed definition')
    def status(key):return observed.get(key,{}).get('properties',{}).get('status')
    def consistent_subtree(key):
        return all(status(child)=='Skipped' for child,(_,parents,_) in nodes.items()
                   if child in observed and (child==key or key in parents))
    if name in observed:
        require(status(name)=='Skipped','Publication action executed, running or ambiguous')
        return {'action':name,'classification':'explicit-skipped','observedStatus':'Skipped'}
    action,ancestors,_=nodes[name]
    for parent in reversed(ancestors):
        if status(parent)=='Skipped':
            require(consistent_subtree(parent),'Mixed observations under Skipped ancestor')
            return {'action':name,'classification':'omitted-ineligible','basis':'observed-skipped-ancestor','barrier':parent}
    terminal={'Succeeded','Failed','TimedOut','Skipped','Cancelled'}
    for candidate in (name,*reversed(ancestors)):
        if candidate in observed:continue
        node,_,siblings=nodes[candidate];dependencies=node.get('runAfter',{})
        if not dependencies:continue
        require(isinstance(dependencies,dict),'Malformed reviewed runAfter')
        exact=[]
        for dep,allowed in dependencies.items():
            require(dep in siblings and isinstance(allowed,list) and bool(allowed)
                    and set(allowed)<=terminal,'Unreviewed dependency/status boundary')
            exact.append((dep,status(dep),allowed))
        # Deliberately refuse missing, active, eligible or mixed barriers.
        if all(value in terminal and value not in allowed for _,value,allowed in exact):
            require(consistent_subtree(candidate),'Mixed observations under blocked dependency')
            return {'action':name,'classification':'omitted-ineligible','basis':'exact-terminal-runAfter-barrier',
                    'barrier':candidate,'dependencies':[{'action':dep,'observedStatus':value,'allowedStatuses':allowed}
                                                        for dep,value,allowed in exact]}
    raise ValueError('Publication action inventory gap held: no observed Skipped ancestor or exact terminal runAfter barrier')


def inspect_copy(b,definition,t,c):
    before=t.flow(b);c.json('copy-flow-before.json',before)
    require(before.get('name')==b['copy']['flowName'] and digest(before['properties']['definition'])==digest(definition),'Current flow differs from reviewed native definition')
    run=t.run(b);c.json('copy-run.json',run)
    require(run.get('name')==b['copy']['runId'] and run['properties'].get('status')=='Succeeded'
            and text(run['properties'].get('endTime')) and not run['properties'].get('isAborted'), 'Copy run is not terminal successful')
    inventory=t.actions(b);c.json('copy-action-inventory.json',inventory)
    rows=complete(inventory);c.json('copy-actions.json',rows);by_name={r['name']:r for r in rows}
    require(len(by_name)==len(rows) and all(r.get('runName')==b['copy']['runId'] for r in rows),'Incomplete or ambiguous copy action history')
    for name in ('Copy_binary_absent_only','Native_binary_copy_observation'):
        require(by_name.get(name,{}).get('properties',{}).get('status')=='Succeeded','Actual successful copy action/receipt required')
    classifications=[publication_action_ineligibility(definition,rows,b['copy']['runId'],name)
                     for name in ('Create_binary_publication','Native_binary_publication_receipt')]
    c.json('publication-action-ineligibility.json',classifications)
    inputs=t.action_content(by_name['Copy_binary_absent_only'],'inputs');c.json('copy-actual-inputs.json',inputs)
    params=inputs.get('parameters',inputs);source=b['source'];target_path=urlsplit(b['issued']['DocumentReference']).path
    expected="_api/web/GetFileById('"+source['UniqueId']+"')/copyTo(strNewUrl='"+target_path.replace("'","''")+"',bOverWrite=false)"
    require(params.get('dataset')==b['site'] and params.get('parameters/method')=='POST'
            and params.get('parameters/uri')==expected and 'parameters/body' not in params
            and not any(k.lower() in ('x-http-method','x-http-method-override') for k in params.get('parameters/headers',{})),
            'Run-specific body-free absent-only copy input differs')
    receipt=t.action_content(by_name['Native_binary_copy_observation'],'outputs');c.json('copy-terminal-receipt.json',receipt)
    require(receipt.get('runId')==b['copy']['runId'] and receipt.get('preparedScope')==b['scope']
            and receipt.get('copyCreatedCount')==1 and receipt.get('binaryOutputQualified') is False
            and all(receipt.get(k)==0 for k in ('publicationCreatedCount','caseWrites','sourceWrites','readinessWrites','purposeWrites','notifications'))
            and receipt.get('realPolicyEffects') is False,'Exact terminal copy receipt required; flags alone are insufficient')
    origin=urlsplit(b['site']).scheme+'://'+urlsplit(b['site']).netloc
    require(normalize_sharepoint_file(receipt['issued'],origin)==metadata(b['issued']),'Copy receipt issued pins differ')
    return receipt


def stage(b,definition,t,output,expected_binding_sha):
    require(digest(b)==expected_binding_sha,'Reviewed producer binding changed')
    origin,_=validate_binding(b,definition);c=Capture(output)
    try:
        c.json('binding.json',b);c.json('reviewed-copy-definition.json',definition)
        code={'driverSHA256':sha(Path(__file__).read_bytes()),
              'binaryVerifierSHA256':sha(Path(__file__).with_name('binary_publication.py').read_bytes())}
        c.json('producer-code-provenance.json',code)
        receipt=inspect_copy(b,definition,t,c);before=read_frame(b,t,c,'before');validate_domain(before,b,receipt['purposeAuthorisation'])
        source_before=t.file_metadata(b['site'],b['source']['DocumentReference']);issued_before=t.file_metadata(b['site'],b['issued']['DocumentReference'])
        c.json('source-before.json',source_before);c.json('issued-before.json',issued_before)
        require(normalize_sharepoint_file(source_before,origin)==metadata(b['source'])
                and normalize_sharepoint_file(issued_before,origin)==metadata(b['issued']),'Pinned source/issued metadata changed')
        source=t.download(b['site'],b['source']['DocumentReference']);c.write('source.docx',source)
        issued=t.download(b['site'],b['issued']['DocumentReference']);c.write('issued.docx',issued)
        source_after=t.file_metadata(b['site'],b['source']['DocumentReference']);issued_after=t.file_metadata(b['site'],b['issued']['DocumentReference'])
        c.json('source-after.json',source_after);c.json('issued-after.json',issued_after)
        proof=verify_downloads(b['scope'],normalize_sharepoint_file(source_before,origin),normalize_sharepoint_file(source_after,origin),
                               normalize_sharepoint_file(issued_before,origin),normalize_sharepoint_file(issued_after,origin),source,issued)
        after=read_frame(b,t,c,'after');validate_domain(after,b,receipt['purposeAuthorisation'])
        require(normalized(before)==normalized(after),'Protected frame changed across downloads')
        flow_after=t.flow(b);c.json('copy-flow-after.json',flow_after)
        require(flow_after.get('name')==b['copy']['flowName'] and digest(flow_after['properties']['definition'])==digest(definition),'Copy definition changed during producer reads')
        proof['downloadEvidence']={
            'source':{'SHA256':sha(source),'Length':len(source),'metadataBefore':normalize_sharepoint_file(source_before,origin),'metadataAfter':normalize_sharepoint_file(source_after,origin)},
            'issued':{'SHA256':sha(issued),'Length':len(issued),'metadataBefore':normalize_sharepoint_file(issued_before,origin),'metadataAfter':normalize_sharepoint_file(issued_after,origin)},
            'producer':{'kind':'existing-m365-cli-read-only-binary-verifier','copyFlowName':b['copy']['flowName'],'copyRunId':b['copy']['runId'],
                        **code,
                        'reviewedDefinitionSHA256':digest(definition),'actualCopyInputsSHA256':c.hashes['copy-actual-inputs.json'],
                        'terminalCopyReceiptSHA256':c.hashes['copy-terminal-receipt.json'],'protectedFrameSHA256':digest(normalized(after))}}
        c.json('binary-proof.json',proof)
        manifest={'kind':'staged-independent-binary-publication-proof-v1','bindingSHA256':digest(b),'proofContentSHA256':digest(proof),
                  'files':dict(c.hashes),'nativeWrites':0,'nativeProofStorageVerified':False,'publicationBindingProduced':False,
                  'limit':'Current definition bracket and run-specific copy inputs retained; immutable executed-definition version/protection still requires native review.'}
        c.json('stage-manifest.json',manifest)
        return {'stageManifestSHA256':c.hashes['stage-manifest.json'],'proofContentSHA256':digest(proof),'nativeWrites':0,'nativeProofStorageVerified':False}
    except Exception as error:
        c.hold(error);raise


def finalize(stage_dir,storage,t,output,expected_manifest_sha):
    p=Path(stage_dir);raw=(p/'stage-manifest.json').read_bytes();require(sha(raw)==expected_manifest_sha,'Reviewed stage manifest changed')
    manifest=json.loads(raw)
    for name,value in manifest['files'].items():
        require(Path(name).name==name and sha((p/name).read_bytes())==value,'Staged evidence changed: '+name)
    b=json.loads((p/'binding.json').read_bytes());definition=json.loads((p/'reviewed-copy-definition.json').read_bytes());origin,_=validate_binding(b,definition)
    proof=json.loads((p/'binary-proof.json').read_bytes());require(digest(proof)==manifest['proofContentSHA256'],'Staged proof changed')
    expected_path=b['qualificationFolder']+'/PPG-binary-proof-'+b['issued']['UniqueId'].lower()+'-v'+b['issued']['nativeVersion']+'.json'
    require(storage.get('DocumentReference')==origin+expected_path and all(text(storage.get(k)) for k in ('UniqueId','ETag'))
            and storage['ETag']!='*' and isinstance(storage.get('expectedPermissions'),dict),'Exact actual create-only proof storage pins and reviewed permissions required')
    c=Capture(output)
    try:
        frame_before=read_frame(b,t,c,'storage-before');receipt=json.loads((p/'copy-terminal-receipt.json').read_bytes());validate_domain(frame_before,b,receipt['purposeAuthorisation'])
        permissions_before=t.permissions(b['site'],storage['DocumentReference']);c.json('storage-permissions-before.json',permissions_before)
        require(normalized(permissions_before)==normalized(storage['expectedPermissions']),'Proof storage permissions changed or unreviewed')
        before=t.file_metadata(b['site'],storage['DocumentReference']);c.json('storage-file-before.json',before)
        pin=normalize_sharepoint_file(before,origin)
        require(all(pin[k]==storage[k] for k in ('UniqueId','ETag','DocumentReference')),'Proof storage identity/token changed')
        actual=t.download(b['site'],storage['DocumentReference']);c.write('native-binary-proof.json',actual)
        require(actual==(p/'binary-proof.json').read_bytes(),'Stored proof bytes differ; never overwrite or repin')
        after=t.file_metadata(b['site'],storage['DocumentReference']);c.json('storage-file-after.json',after)
        require(normalize_sharepoint_file(after,origin)==pin and len(actual)==pin['Length'],'Proof changed during readback')
        for label in ('source','issued'):
            observed=t.file_metadata(b['site'],b[label]['DocumentReference']);c.json('storage-final-'+label+'.json',observed)
            require(normalize_sharepoint_file(observed,origin)==metadata(b[label]),'Source/issued changed since measured downloads')
        frame_after=read_frame(b,t,c,'storage-after');validate_domain(frame_after,b,receipt['purposeAuthorisation'])
        require(normalized(frame_before)==normalized(frame_after),'Protected frame changed during proof storage verification')
        permissions_after=t.permissions(b['site'],storage['DocumentReference']);c.json('storage-permissions-after.json',permissions_after)
        require(normalized(permissions_after)==normalized(permissions_before),'Proof permissions changed during readback')
        proof_pin={'UniqueId':pin['UniqueId'],'ETag':pin['ETag'],'DocumentReference':pin['DocumentReference']}
        evidence={'kind':'independent-binary-publication-producer-qualification-v1','copyFlowName':b['copy']['flowName'],
            'copyRunId':b['copy']['runId'],'proofContentSHA256':digest(proof),'proofReceipt':proof_pin,
            'stageManifestSHA256':expected_manifest_sha,'producerDefinitionSHA256':digest(definition),
            'producerFiles':dict(c.hashes),'scope':b['scope'],'nativeWrites':0,
            'storageProtection':'Reviewed existing permissions and exact create-only receipt/token/content brackets; no access change or atomic transaction claimed',
            'executionDefinitionLimit':manifest['limit']}
        evidence_bytes=canonical(evidence);c.write('producer-evidence.json',evidence_bytes)
        reviewed={'receipt':proof_pin,'content':proof,'producerEvidenceSHA256':sha(evidence_bytes)}
        c.json('reviewed-binary-proof-binding.json',reviewed)
        return {'reviewedBinaryProof':reviewed,'producerEvidenceSHA256':sha(evidence_bytes),'nativeWrites':0}
    except Exception as error:
        c.hold(error);raise


class M365ReadOnly:
    """Only existing GET/download commands. Never invoked by import or tests."""
    def command(self,args):
        r=subprocess.run(['m365',*args],capture_output=True,timeout=60)
        require(r.returncode==0,'Read-only CLI operation failed; reconcile existing authentication/target, do not automatically retry')
        return r.stdout
    def get_json(self,url):
        require(urlsplit(url).scheme=='https','HTTPS native read required')
        # CLI stdout presentation can add escapes to multiline expression strings.
        # Parse the actual streamed response file; never normalize expression text.
        with tempfile.TemporaryDirectory(prefix='ppg-proof-json-') as folder:
            output=Path(folder)/'response.json'
            self.command(['request','--url',url,'--method','get','--filePath',str(output),'--output','json'])
            return json.loads(output.read_bytes())
    def base(self,b):
        return 'https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/'+b['copy']['environment']+'/flows/'+b['copy']['flowName']
    def flow(self,b):return self.get_json(self.base(b)+'?api-version=2016-11-01')
    def run(self,b):return self.get_json(self.base(b)+'/runs/'+b['copy']['runId']+'?api-version=2016-11-01')
    def actions(self,b):
        prefix=self.base(b)+'/runs/'+b['copy']['runId']+'/actions?'
        # Bound the first page as well as subsequent native continuations.
        url=prefix+'api-version=2016-11-01&$top=100';pages=[];rows=[];seen=set()
        while url:
            require(url.startswith(prefix) and url not in seen and len(pages)<10,'Unexpected, cyclic or excessive action continuation')
            seen.add(url);page=self.get_json(url)
            require(isinstance(page,dict) and isinstance(page.get('value'),list),'Missing native action page')
            pages.append(page);rows.extend(page['value'])
            links={page[k] for k in ('nextLink','@nextLink','odata.nextLink','@odata.nextLink') if page.get(k)}
            require(len(links)<=1,'Conflicting native action continuations')
            url=next(iter(links),None)
        return {'value':rows,'nativePages':pages,'complete':True}
    def action_content(self,action,kind):
        link=action['properties'][kind+'Link']['uri'];url=urlsplit(link)
        require(url.scheme=='https' and not url.username and not url.password
                and any((url.hostname or '').endswith(s) for s in ('.logic.azure.com','.flow.microsoft.com','.azure-apihub.net','.flow-apim.net',
                                                                  '.environment.api.powerplatformusercontent.com', '.environment.api.powerplatform.com')),
                'Only actual returned Microsoft action-content links are permitted')
        if (url.hostname or '').endswith('.environment.api.powerplatform.com'):
            require(kind in ('inputs', 'outputs') and not url.fragment
                    and re.fullmatch(r'/powerautomate/automations/direct/workflows/[A-Za-z0-9-]{1,100}/runs/[A-Za-z0-9-]{1,100}/actions/[A-Za-z0-9_-]{1,100}/contents/Action' + kind.title(), url.path)
                    and all(parse_qs(url.query).get(k) for k in ('sig', 'se', 'sp', 'sv')),
                    'Exact signed native action-content route required')
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):
                raise ValueError('Action-content redirect refused')
        with build_opener(NoRedirect()).open(link,timeout=30) as response:raw=response.read(4*1024*1024+1)
        require(len(raw)<=4*1024*1024,'Action content too large');return json.loads(raw)
    def file_metadata(self,site,reference):
        path=self.file_path(site,reference).replace("'","''")
        return self.get_json(site+"/_api/web/GetFileByServerRelativePath(decodedurl='"+path+"')?$select=UniqueId,ETag,UIVersionLabel,Length,ServerRelativeUrl")
    def file_path(self,site,reference):
        base=urlsplit(site);url=urlsplit(reference)
        require(base.scheme==url.scheme=='https' and base.netloc==url.netloc and not url.username and not url.password
                and url.path.startswith(base.path+'/') and not url.query and not url.fragment
                and all(x not in url.path for x in ('..','%','\\')),'Exact same-site canonical file required')
        return url.path
    def download(self,site,reference):
        with tempfile.TemporaryDirectory(prefix='ppg-proof-read-') as folder:
            output=Path(folder)/'download.bin'
            self.command(['spo','file','get','--webUrl',site,'--url',self.file_path(site,reference),'--asFile','--path',str(output),'--output','json'])
            return output.read_bytes()
    def permissions(self,site,reference):
        return json.loads(self.command(['spo','file','get','--webUrl',site,'--url',self.file_path(site,reference),'--withPermissions','--output','json']))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Read-only proof driver; no uploads or native mutations')
    parser.add_argument('phase',choices=('stage','finalize'));parser.add_argument('--execute-read-only',action='store_true',required=True)
    parser.add_argument('--binding');parser.add_argument('--reviewed-definition');parser.add_argument('--expected-binding-sha256')
    parser.add_argument('--stage-dir');parser.add_argument('--storage-binding');parser.add_argument('--expected-manifest-sha256')
    parser.add_argument('--output',required=True);args=parser.parse_args();transport=M365ReadOnly()
    if args.phase=='stage':
        result=stage(json.loads(Path(args.binding).read_bytes()),json.loads(Path(args.reviewed_definition).read_bytes()),transport,args.output,args.expected_binding_sha256)
    else:result=finalize(args.stage_dir,json.loads(Path(args.storage_binding).read_bytes()),transport,args.output,args.expected_manifest_sha256)
    print(json.dumps({k:v for k,v in result.items() if k!='reviewedBinaryProof'}))
