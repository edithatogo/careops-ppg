"""Add create-only native observation receipts to the qualified acquisition graph.

Uses the existing Standard SharePoint receipt/readback pattern. No native I/O.
The catalogue remains authoritative; this builder never promotes a record.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from urllib.parse import urlsplit
from uuid import UUID

from scripts.ppg_integrated_acquisition import build as build_integrated, _native_projection

API = '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
SLOT = 'shared_sharepointonline'
PINS = ('UniqueId', 'ETag', 'Length', 'UIVersionLabel', 'ServerRelativeUrl')
OD_FIELDS = ('Id', 'ETag', 'Size', 'IsFolder')
RUN_CHARACTERS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-'


def _text(value, maximum=2048):
    if (not isinstance(value, str) or not value or len(value) > maximum
            or value.startswith('@') or '@{' in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('Bounded literal binding required')
    return value


def _uuid(value):
    if str(UUID(value)) != value or not UUID(value).int:
        raise ValueError('Canonical nonzero UUID required')
    return value


def _pin(value):
    if not isinstance(value, dict) or set(value) != set(PINS):
        raise ValueError('Exact qualified native pin required')
    for k in PINS:
        _text(value[k])
    _uuid(value['UniqueId'])
    if not value['Length'].isdigit() or value['ETag'] == '*':
        raise ValueError('Stable native byte length/ETag required')


def _binding(value):
    required = {'site', 'folder', 'connectionReference', 'replayKey', 'binding',
                'retainedOriginalURL', 'originalPin', 'sourceMetadata', 'sourceFile',
                'records', 'claimName', 'claimJSON', 'claimPin', 'resumeRunIdDefault'}
    required |= {'scriptPath','scriptMetadata'}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('Exact qualified observation binding required')
    b = copy.deepcopy(value)
    site = urlsplit(_text(b['site']))
    if (site.scheme != 'https' or not site.hostname or not site.hostname.endswith('.sharepoint.com')
            or site.username or site.password or site.port not in (None, 443)
            or site.query or site.fragment or b['site'].endswith('/')
            or not site.path.startswith(('/sites/', '/teams/'))):
        raise ValueError('Exact existing SharePoint site required')
    folder = _text(b['folder'], 500)
    if (not folder.startswith(site.path + '/') or folder.endswith('/')
            or any(c in folder for c in ("'", '%', '?', '#', '\\'))
            or any(part in ('.', '..', '') for part in folder.split('/')[1:])):
        raise ValueError('Owned existing receipt folder required')
    ref = b['connectionReference']
    if (not isinstance(ref, dict) or set(ref) != {'id', 'connectionName', 'source'}
            or ref['id'] != API or ref['source'] != 'Embedded'
            or not re.fullmatch('[A-Za-z0-9_-]{1,160}', _text(ref['connectionName'], 160))):
        raise ValueError('Existing embedded SharePoint reference required')
    if not isinstance(b['replayKey'], str) or not re.fullmatch('[0-9a-f]{64}', b['replayKey']):
        raise ValueError('Qualified capture replay key required')
    if b['claimName'] != 'source-replay-' + b['replayKey'] + '.json':
        raise ValueError('Existing capture claim name differs')
    _pin(b['originalPin']); _pin(b['claimPin'])
    if b['claimPin']['ServerRelativeUrl'] != folder + '/' + b['claimName']:
        raise ValueError('Existing claim outside assigned namespace')
    _text(b['claimJSON'], 1024 * 1024)
    claim = json.loads(b['claimJSON'])
    if (claim.get('kind') != 'ppg-source-capture-replay-claim-v1'
            or claim.get('replayKey') != b['replayKey'] or claim.get('binding') != b['binding']
            or claim.get('existingRetainedOriginalURL') != b['retainedOriginalURL']
            or claim.get('fullAcquisitionQualified') is not False
            or claim.get('publicationPromotionPerformed') is not False):
        raise ValueError('Qualified capture claim body differs')
    binding = b['binding']
    if not isinstance(binding, dict) or set(binding) != {'publicationKey','editionKey','captureKey','requestedSourceURL','sha256'}:
        raise ValueError('Exact capture endpoints required')
    for k in ('publicationKey','editionKey','captureKey'):
        if not re.fullmatch('[a-z0-9][a-z0-9:._-]{0,199}', _text(binding[k], 200)):
            raise ValueError('Literal catalogue endpoints required')
    if not isinstance(binding['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', binding['sha256']):
        raise ValueError('Qualified source digest required')
    canonical = lambda obj: json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    if (hashlib.sha256(canonical(binding).encode()).hexdigest() != b['replayKey']
            or canonical(claim) != b['claimJSON'] or len(b['claimJSON'].encode()) != int(b['claimPin']['Length'])):
        raise ValueError('Capture claim canonical bytes or replay key differs')
    original = urlsplit(_text(b['retainedOriginalURL']))
    if (original.scheme != site.scheme or original.netloc != site.netloc or original.query
            or original.fragment or original.username or original.password
            or not b['originalPin']['ServerRelativeUrl'].startswith(site.path + '/')):
        raise ValueError('Existing original outside selected site')
    from urllib.parse import unquote
    if unquote(original.path) != b['originalPin']['ServerRelativeUrl']:
        raise ValueError('Retained original link/pin differs')
    meta = b['sourceMetadata']
    if (not isinstance(meta, dict) or set(meta) != set(OD_FIELDS)
            or type(meta['Size']) is not int or meta['Size'] < 1 or meta['IsFolder'] is not False
            or not isinstance(meta['ETag'], str) or meta['ETag'] == '*'):
        raise ValueError('Qualified source metadata required')
    _text(meta['Id']); _text(meta['ETag'])
    sf = b['sourceFile']
    if (not isinstance(sf, dict) or set(sf) != {'uniqueId','nativeVersion','etag','url','bytes'}
            or sf['etag'] != meta['ETag'] or type(sf['bytes']) is not int
            or sf['bytes'] != meta['Size'] or b['originalPin']['Length'] != str(meta['Size'])):
        raise ValueError('Qualified source occurrence pin differs')
    _uuid(sf['uniqueId']); _text(sf['nativeVersion']); _text(sf['url'])
    source = urlsplit(sf['url'])
    if (source.scheme != 'https' or not source.hostname or not source.hostname.endswith('.sharepoint.com')
            or source.username or source.password or source.query or source.fragment):
        raise ValueError('Stable native source file URL required')
    records = b['records']
    if not isinstance(records, list) or len(records) != 3:
        raise ValueError('Exactly three consumer-selected native records required')
    expected = {binding[k] for k in ('publicationKey','editionKey','captureKey')}
    if {r.get('key') for r in records if isinstance(r, dict)} != expected:
        raise ValueError('Consumer-selected endpoints differ')
    if set(claim.get('selectedRecordSHA256',{})) != expected:
        raise ValueError('Capture claim record endpoints differ')
    for row in records:
        if set(row) != {'key','listId','itemId','recordJSON','payloadSHA256','reviewState'}:
            raise ValueError('Exact current record preimage required')
        _uuid(row['listId'])
        if type(row['itemId']) is not int or row['itemId'] < 1:
            raise ValueError('Current native item ID required')
        _text(row['recordJSON'], 256*1024); _text(row['reviewState'])
        actual = hashlib.sha256(row['recordJSON'].encode()).hexdigest()
        if actual != row['payloadSHA256'] or claim['selectedRecordSHA256'].get(row['key']) != actual:
            raise ValueError('Current record bytes differ from selected claim')
    resume = b['resumeRunIdDefault']
    if not isinstance(resume, str) or len(resume) > 80 or any(c not in RUN_CHARACTERS for c in resume):
        raise ValueError('Bounded explicit resume run ID required')
    script_path=_text(b['scriptPath'],500)
    script=b['scriptMetadata']
    if (not script_path.startswith('/') or any(c in script_path for c in ('\\','%',"'",'?','#'))
            or any(part in ('','.','..') for part in script_path.split('/')[1:])
            or not script_path.endswith('.osts')
            or not isinstance(script,dict) or set(script)!={'ETag','Size','IsFolder','Name'}
            or type(script['Size']) is not int or not 0<script['Size']<=1024*1024
            or script['IsFolder'] is not False or script['Name']!=script_path.rsplit('/',1)[-1]
            or not isinstance(script['ETag'],str) or script['ETag']=='*'):
        raise ValueError('Exact qualified script path/metadata required')
    _text(script['ETag'])
    return b


def build(profile, runtime, persistence):
    b = _binding(persistence)
    if (b['binding']['sha256'] != profile['expectedSHA256']
            or b['binding']['requestedSourceURL'] != profile['sourceURL']
            or b['sourceMetadata']['Size'] != profile['expectedBytes']):
        raise ValueError('Capture selection and acquisition profile differ')
    flow = build_integrated(profile, runtime)
    p = flow['properties']; p['connectionReferences'][SLOT] = b['connectionReference']
    trigger = p['definition']['triggers']['manual']['inputs']['schema']
    trigger['properties']['resumeRunId'] = {'type':'string','title':'Resume existing observation run (optional)',
        'maxLength':80,'pattern':'^[A-Za-z0-9-]*$','x-ms-dynamically-added':True,'x-ms-content-hint':'TEXT'}
    actions = p['definition']['actions']['Select_fixed_source']['actions']['Require_ready']['actions']['Require_expected_metadata']['actions']['Require_stable_metadata']['actions']['Require_integrated_integrity']['actions']
    stable=p['definition']['actions']['Select_fixed_source']['actions']['Require_ready']['actions']['Require_expected_metadata']['actions']['Require_stable_metadata']['actions']
    site = b['site']; site_path = urlsplit(site).path
    relative = b['folder'][len(site_path):]
    def lit(text):return "'" + str(text).replace("'", "''") + "'"
    def after(prev):return {prev:['Succeeded']} if prev else {}
    def compose(value, prev):return {'type':'Compose','runAfter':after(prev),'inputs':value}
    def http(method, uri, prev, body=None):
        params={'dataset':site,'parameters/method':method,'parameters/uri':uri,
                'parameters/headers':{'Accept':'application/json;odata=nometadata'}}
        if body is not None:params['parameters/body']=body
        return {'type':'OpenApiConnection','runAfter':after(prev),'inputs':{
            'host':{'apiId':API,'connectionName':SLOT,'operationId':'HttpRequest'},
            'parameters':params,'retryPolicy':{'type':'none'}}}
    def content(path, prev):
        return {'type':'OpenApiConnection','runAfter':after(prev),'inputs':{
            'host':{'apiId':API,'connectionName':SLOT,'operationId':'GetFileContentByPath'},
            'parameters':{'dataset':site,'path':path,'inferContentType':False},'retryPolicy':{'type':'none'}}}
    def check(expression, prev, name):
        return {'type':'If','runAfter':after(prev),'expression':'@'+expression,'actions':{},
            'else':{'actions':{'Hold_'+name:{'type':'Terminate','runAfter':{},'inputs':{
                'runStatus':'Failed','runError':{'code':name,'message':'Preserve native evidence. Reconcile the held source or saved receipt before a fresh invocation.'}}}}}}
    def pin_uri(pin):return "_api/web/GetFileById('"+pin['UniqueId']+"')?$select="+','.join(PINS)
    def pin_checks(action, expected):return ["equals(string(body('"+action+"')?['"+k+"']),"+lit(expected[k])+")" for k in PINS]
    def engine(action,prev):
        operation={'type':'OpenApiConnection','runAfter':after(prev),'inputs':{
            'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness','connectionName':'shared_onedriveforbusiness','operationId':'GetFileMetadataByPath'},
            'parameters':{'path':b['scriptPath']},'retryPolicy':{'type':'none'}}}
        tests=[]
        for k,value in b['scriptMetadata'].items():
            literal=lit(value) if isinstance(value,str) else json.dumps(value)
            tests.append("equals(body('"+action+"')?['"+k+"'],"+literal+")")
        return operation,tests
    operation,engine_checks=engine('Read_engine_before_hash','Hash_request')
    stable['Read_engine_before_hash']=operation
    stable['Require_engine_before_hash']=check('and('+','.join(engine_checks)+')','Read_engine_before_hash','Engine_changed_before_hash')
    stable['Run_hash']['runAfter']=after('Require_engine_before_hash')
    def context(label, prev):
        conditions=[]
        for index,row in enumerate(b['records']):
            name='Read_record_'+label+'_'+str(index)
            actions[name]=http('GET',"_api/web/lists(guid'"+row['listId']+"')/items("+str(row['itemId'])+")?$select=RecordKey,RecordJSON,PayloadSHA256,ReviewState",prev);prev=name
            for field,key in [('RecordKey','key'),('RecordJSON','recordJSON'),('PayloadSHA256','payloadSHA256'),('ReviewState','reviewState')]:
                conditions.append("equals(body('"+name+"')?['"+field+"'],"+lit(row[key])+")")
        name='Read_original_'+label;actions[name]=http('GET',pin_uri(b['originalPin']),prev);prev=name
        conditions+=pin_checks(name,b['originalPin'])
        name='Read_claim_pin_'+label;actions[name]=http('GET',pin_uri(b['claimPin']),prev);prev=name
        conditions+=pin_checks(name,b['claimPin'])
        name='Read_stage_'+label
        stage=profile['stagingRoot']+'/'+profile['qualificationId']+'.captured'
        actions[name]={'type':'OpenApiConnection','runAfter':after(prev),'inputs':{
            'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness','connectionName':'shared_onedriveforbusiness','operationId':'GetFileMetadataByPath'},
            'parameters':{'path':stage},'retryPolicy':{'type':'none'}}};prev=name
        for k in OD_FIELDS:
            value=b['sourceMetadata'][k]
            literal=lit(value) if isinstance(value,str) else json.dumps(value)
            conditions.append("equals(body('"+name+"')?['"+k+"'],"+literal+")")
        name='Read_engine_'+label
        operation,tests=engine(name,prev);actions[name]=operation;prev=name;conditions+=tests
        name='Require_context_'+label;actions[name]=check('and('+','.join(conditions)+')',prev,'Context_'+label)
        return name

    actions['Observation_resume_input']=compose("@coalesce(triggerBody()?['resumeRunId'],"+lit(b['resumeRunIdDefault'])+")",'Report_integrated_candidate')
    actions['Observation_resume_characters']={'type':'Query','runAfter':after('Observation_resume_input'),'inputs':{
        'from':"@range(0,length(outputs('Observation_resume_input')))",
        'where':"@contains('"+RUN_CHARACTERS+"',substring(outputs('Observation_resume_input'),item(),1))"}}
    actions['Require_safe_resume']=check("and(lessOrEquals(length(outputs('Observation_resume_input')),80),equals(length(body('Observation_resume_characters')),length(outputs('Observation_resume_input'))))",'Observation_resume_characters','Unsafe_resume')
    actions['Observation_origin_run']=compose("@if(empty(outputs('Observation_resume_input')),workflow()?['run']?['name'],outputs('Observation_resume_input'))",'Require_safe_resume')
    actions['Observation_filename']=compose("@concat('source-native-run-',outputs('Observation_origin_run'),'.json')",'Observation_origin_run')
    path="@concat("+lit(relative+'/')+",outputs('Observation_filename'))"
    uri="@concat('_api/web/GetFolderByServerRelativePath(decodedurl=''"+b['folder']+"'')/Files/AddUsingPath(decodedurl=''',outputs('Observation_filename'),''',overwrite=false)')"
    read_uri="@concat('_api/web/GetFileByServerRelativePath(decodedurl=''"+b['folder']+"/',outputs('Observation_filename'),''')?$select="+','.join(PINS)+"')"
    prev=context('initial','Observation_filename')
    actions['Read_capture_claim']=content(relative+'/'+b['claimName'],prev)
    actions['Require_capture_claim']=check("equals(body('Read_capture_claim')?['$content'],base64("+lit(b['claimJSON'])+"))",'Read_capture_claim','Capture_claim_changed')
    actions['Read_observation_before']=http('GET',read_uri,'Require_capture_claim')
    readable="or(equals(outputs('Read_observation_before')?['statusCode'],200),and(equals(outputs('Read_observation_before')?['statusCode'],404),empty(outputs('Observation_resume_input'))))"
    actions['Require_observation_readable']=check(readable,None,'Observation_unreadable_or_missing_resume')
    actions['Require_observation_readable']['runAfter']={'Read_observation_before':['Succeeded','Failed','TimedOut']}
    actions['Read_existing_observation']={'type':'If','runAfter':after('Require_observation_readable'),
        'expression':"@equals(outputs('Read_observation_before')?['statusCode'],200)",
        'actions':{'Read_existing_observation_content':content(path,None)},'else':{'actions':{}}}
    observed="@if(equals(outputs('Read_observation_before')?['statusCode'],200),json(base64ToString(body('Read_existing_observation_content')?['$content']))?['observedAtUtc'],utcNow())"
    record={'kind':'ppg-native-acquisition-observation-v1','binding':b['binding'],'replayKey':b['replayKey'],
            'workflowId':"@workflow()?['name']",'originRunId':"@outputs('Observation_origin_run')",'observedAtUtc':observed,
            'sourceFile':b['sourceFile'],'retainedOriginalURL':b['retainedOriginalURL'],'retainedOriginalPin':b['originalPin'],
            'selectedRecordSHA256':json.loads(b['claimJSON'])['selectedRecordSHA256'],
            'hashResult':"@outputs('Hash_result')",'scriptPackageSHA256':runtime['scriptPackageSHA256'],
            'runtimeSourceSHA256':runtime['runtimeSourceSHA256'],'captureClaimPin':b['claimPin'],
            'finalSourceURL':None,'redirectsVerified':False,'cataloguePromotionPerformed':False,
            'checkpointAdvanced':False,'fullAcquisitionQualified':False,'clinicalApplicabilityAccepted':False}
    actions['Expected_observation']=compose(record,'Read_existing_observation')
    match="and(not(empty(outputs('Expected_observation')?['observedAtUtc'])),or(equals(outputs('Read_observation_before')?['statusCode'],404),and(equals(body('Read_existing_observation_content')?['$content'],base64(string(outputs('Expected_observation')))),equals(body('Read_observation_before')?['UIVersionLabel'],'1.0'))))"
    actions['Require_existing_observation_exact']=check(match,'Expected_observation','Observation_edited')
    prev=context('before_write','Require_existing_observation_exact')
    actions['Create_observation_if_missing']={'type':'If','runAfter':after(prev),
        'expression':"@equals(outputs('Read_observation_before')?['statusCode'],404)",
        'actions':{'Create_observation':http('POST',uri,None,"@string(outputs('Expected_observation'))")},'else':{'actions':{}}}
    actions['Read_saved_observation_pin']=http('GET',read_uri,'Create_observation_if_missing')
    actions['Read_saved_observation_content']=content(path,'Read_saved_observation_pin')
    actions['Read_saved_observation_after']=http('GET',read_uri,'Read_saved_observation_content')
    prev=context('final','Read_saved_observation_after')
    encoded="base64(string(outputs('Expected_observation')))"
    byte_length="sub(div(mul(length("+encoded+"),3),4),if(endsWith("+encoded+",'=='),2,if(endsWith("+encoded+",'='),1,0)))"
    checks=["equals(body('Read_saved_observation_content')?['$content'],base64(string(outputs('Expected_observation'))))",
            "equals(body('Read_saved_observation_after')?['UIVersionLabel'],'1.0')",
            "equals(body('Read_saved_observation_after')?['ServerRelativeUrl'],concat("+lit(b['folder']+'/')+",outputs('Observation_filename')))",
            "equals(int(body('Read_saved_observation_after')?['Length']),"+byte_length+")"]
    checks += ["equals(body('Read_saved_observation_pin')?['"+k+"'],body('Read_saved_observation_after')?['"+k+"'])" for k in PINS]
    checks += ["or(equals(outputs('Read_observation_before')?['statusCode'],404),equals(body('Read_observation_before')?['"+k+"'],body('Read_saved_observation_after')?['"+k+"']))" for k in PINS]
    actions['Require_saved_observation']=check('and('+','.join(checks)+')',prev,'Saved_observation_changed')
    actions['Report_persisted_observation']=compose({'kind':'ppg-native-acquisition-persistence-result-v1',
        'currentRunId':"@workflow()?['run']?['name']",'originRunId':"@outputs('Observation_origin_run')",
        'receiptPin':"@body('Read_saved_observation_after')",'captureKey':b['binding']['captureKey'],
        'replayKey':b['replayKey'],'created':"@equals(outputs('Read_observation_before')?['statusCode'],404)",
        'resumed':"@not(empty(outputs('Observation_resume_input')))",'producerObservationPersisted':True,
        'catalogueRowsChanged':0,'originalCapturesCreated':0,'checkpointAdvanced':False,
        'associationCommitVerified':False,'fullAcquisitionQualified':False,'clinicalApplicabilityAccepted':False},'Require_saved_observation')
    return flow


def validate(flow, profile, runtime, persistence):
    """Exact owned graph only; generic SharePoint REST execution is not authorised."""
    try:
        if _native_projection(flow) != _native_projection(build(profile,runtime,persistence)):
            return ['cloud-observation-definition-or-bindings-differ']
        if flow['properties'].get('state') != 'Stopped' or flow['properties'].get('flowFailureAlertSubscribed') is not False:
            return ['stopped-with-owner-alerts-off-required']
    except (KeyError,TypeError,ValueError,AttributeError):
        return ['invalid-cloud-observation-definition-or-binding']
    return []
