"""Pure adapter from a reviewed selected-case flow to observed manual Button entry.

A case reference is an untrusted lookup key, never caller-supplied native identity,
version, role or provenance. No deployment, authentication or native I/O occurs here.
"""
import copy
import hashlib
import json
import uuid
from build_selected_event_routes import audit_actions


def definition_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def build(flow, observed_button_flow, binding):
    source=flow['properties']['definition'];button=observed_button_flow['properties']['definition']['triggers']['manual']
    if (binding.get('qualificationOnly') is not True
        or definition_digest(source)!=binding.get('approvedDefinitionSHA256')
        or definition_digest(button)!=binding.get('approvedButtonTriggerSHA256')):
        raise ValueError('Exact reviewed flow and currently observed Button trigger required')
    if button.get('type')!='Request' or button.get('kind')!='Button':
        raise ValueError('Use the observed first-party manual Button trigger')
    if set(source['triggers'])!={'manual'}:
        raise ValueError('One existing trigger required')
    old=source['triggers']['manual'];inputs=old['inputs']
    if old.get('kind')!='ApiConnection' or inputs.get('operationId')!='GetItemHybridTriggerSchema':
        raise ValueError('Adapt the reviewed selected-item entry only once')
    refs=flow['properties']['connectionReferences'];observed_refs=observed_button_flow['properties']['connectionReferences']
    if (set(refs)!={'shared_sharepointonline'}
        or refs['shared_sharepointonline']['connectionName']!=observed_refs['shared_sharepointonline']['connectionName']):
        raise ValueError('Preserve the qualified SharePoint connection')
    table=inputs['parameters']['table'];uuid.UUID(table)
    site=inputs['parameters']['dataset'];collection="_api/web/lists(guid'"+table+"')/items"
    def quote(value):return "'"+value.replace("'","''")+"'"
    context=source['actions']['Resolve_context']['actions'];reader=context['Read_selected_case']
    parameters=reader['inputs']['parameters'];host=reader['inputs']['host']
    if (reader.get('type')!='OpenApiConnection'
        or host.get('apiId')!='/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
        or host.get('operationId')!='HttpRequest'
        or parameters.get('dataset')!=site or parameters.get('parameters/method')!='GET'
        or host.get('connectionName')!='shared_sharepointonline'
        or 'parameters/body' in parameters
        or any(k.lower() in ('x-http-method','x-http-method-override') for k in parameters.get('parameters/headers',{}))
        or not parameters['parameters/uri'].startswith('@concat('+quote(collection+'('))
        or reader.get('runAfter')):
        raise ValueError('Exact fixed-site/list native case reader required')
    out=copy.deepcopy(flow);props=out['properties'];props['state']='Stopped';d=props['definition']
    schema=old['inputs']['schema'];row=schema.get('properties',schema)['rows']['items']
    fields=copy.deepcopy(row.get('properties',{}))
    if 'text_6' in fields or any(value.get('type')!='string' for value in fields.values()):
        raise ValueError('Preserve existing text fields; text_6 must be available')
    for field in fields.values():
        choices=field.pop('enum',None)
        if choices:field['description']=field.get('description','')+' Enter exactly: '+' / '.join(choices)+'.'
    fields['text_6']={'type':'string','title':'Case reference',
        'description':'Existing LC-FICTIONAL-OP- case reference. A lookup key only; no authority, role or document version is supplied by this field.',
        'x-ms-dynamically-added':True,'x-ms-content-hint':'TEXT'}
    trigger=copy.deepcopy(button);trigger['inputs']['schema']={'type':'object','properties':fields,'required':list(dict.fromkeys(row.get('required',[])+['text_6']))}
    trigger['runtimeConfiguration']={'concurrency':{'runs':1}};d['triggers']['manual']=trigger
    entity="triggerBody()?['entity']?['ID']";resolved="outputs('Resolved_case_item_id')"
    def convert(value):
        if isinstance(value,dict):return {('resolvedCaseItemId' if k=='selectedTriggerItemId' else k):convert(v) for k,v in value.items()}
        if isinstance(value,list):return [convert(v) for v in value]
        if isinstance(value,str):return value.replace(entity,resolved).replace("?['selectedTriggerItemId']","?['resolvedCaseItemId']")
        return value
    reserved={'Case_reference_value','Validate_case_reference','Case_reference_valid','Refuse_case_reference',
        'Find_case_reference','Verify_case_reference','Resolved_case_item_id','Refuse_case_lookup',
        'Verify_case_reference_identity','Case_reference_identity_verified','Refuse_case_reference_drift'}
    names=set()
    def collect(value):
        if isinstance(value,dict):
            if isinstance(value.get('actions'),dict):names.update(value['actions'])
            for child in value.values():collect(child)
        elif isinstance(value,list):
            for child in value:collect(child)
    names.update(d['actions']);collect(d['actions'])
    if reserved & names:raise ValueError('Manual-entry action namespace collision')
    d['actions']=convert(d['actions']);context=d['actions']['Resolve_context']['actions']
    if any(pattern in json.dumps(d) for pattern in ("triggerBody()?['entity']","triggerBody()['entity']",
        "triggerOutputs()?['body/rows']","triggerOutputs()['body/rows']",
        "triggerOutputs()?['body/entity/ID']","triggerOutputs()['body/entity/ID']")):
        raise ValueError('Unreviewed caller-entity reference remains')
    def comp(value,previous=None):return {'type':'Compose','inputs':value,'runAfter':{previous:['Succeeded']} if previous else {}}
    def refuse(code,message):return {'type':'Terminate','runAfter':{},'inputs':{'runStatus':'Failed','runError':{'code':code,'message':message}}}
    value="outputs('Case_reference_value')"
    syntax=["equals(triggerBody()?['text_6'],"+value+')',"startsWith("+value+",'LC-FICTIONAL-OP-')",
        "greater(length("+value+"),16)","lessOrEquals(length("+value+"),128)",
        "equals(uriComponent("+value+'),'+value+')']
    syntax += ['not(contains('+value+','+quote(char)+'))' for char in ('.','~','!','*',"'",'(',')')]
    context['Case_reference_value']=comp("@string(coalesce(triggerBody()?['text_6'],''))")
    context['Validate_case_reference']={'type':'If','expression':'@and('+','.join(syntax)+')',
        'runAfter':{'Case_reference_value':['Succeeded']},'actions':{'Case_reference_valid':comp(True)},
        'else':{'actions':{'Refuse_case_reference':refuse('InvalidCaseReference','Enter one bounded fictional case reference using letters, digits, hyphens or underscores. No lookup or write attempted.')}}}
    lookup=copy.deepcopy(reader);lookup['runAfter']={'Validate_case_reference':['Succeeded']}
    lookup['inputs']['parameters']['parameters/uri']='@concat('+quote(collection+'?$filter=CaseUID eq ')+",decodeUriComponent('%27'),"+value+",decodeUriComponent('%27'),"+quote('&$select=Id,CaseUID')+')'
    lookup['inputs']['parameters'].pop('parameters/body',None)
    lookup['inputs']['parameters']['parameters/headers']={'Accept':'application/json;odata=nometadata'}
    context['Find_case_reference']=lookup
    item="first(body('Find_case_reference')?['value'])"
    checks=["empty(body('Find_case_reference')?['odata.nextLink'])","empty(body('Find_case_reference')?['@odata.nextLink'])",
        "equals("+item+"?['CaseUID'],"+value+')',"greater(int(coalesce("+item+"?['Id'],0)),0)",
        "lessOrEquals(int(coalesce("+item+"?['Id'],0)),2147483647)"]
    context['Verify_case_reference']={'type':'If','expression':"@if(equals(length(body('Find_case_reference')?['value']),1),and("+','.join(checks)+'),false)',
        'runAfter':{'Find_case_reference':['Succeeded']},'actions':{'Resolved_case_item_id':comp('@int('+item+"?['Id'])")},
        'else':{'actions':{'Refuse_case_lookup':refuse('UnresolvedCaseReference','A unique complete exact case match with a positive native ID is required. No broader or latest-record fallback; no write attempted.')}}}
    context['Read_selected_case']['runAfter']={'Verify_case_reference':['Succeeded']}
    context['Verify_case_reference_identity']={'type':'If',
        'expression':"@and(equals(body('Read_selected_case')?['CaseUID'],"+value+"),equals(body('Read_selected_case')?['Id'],"+resolved+'))',
        'runAfter':{'Read_selected_case':['Succeeded']},'actions':{'Case_reference_identity_verified':comp(True)},
        'else':{'actions':{'Refuse_case_reference_drift':refuse('CaseReferenceChangedBeforeEvidence','Case identity changed between lookup and full read; no baseline/source reads or writes.')}}}
    boundary=context['Verify_baseline_boundary']
    boundary['runAfter']={'Verify_case_reference_identity':['Succeeded']}
    final=boundary['actions']['Verify_request']['actions']['Verify_source_and_case']['actions']['Selected_case_context']['inputs']
    final.pop('selectedTriggerItemId',None)
    final.update(contextOrigin='manual_case_reference_lookup',caseReference='@'+value,resolvedCaseItemId='@'+resolved)
    final.setdefault('limits',{}).update(selectedRowProvenanceClaimed=False,ordinaryUserAccessQualified=False)
    audit_actions(d)
    return out
