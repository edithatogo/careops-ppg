"""Bind an existing fictional publisher to exact native folder/receipt admission.

Offline assembly only. Standard SharePoint GETs add no access or publication
permission. Copy preparation requires a folder; recording also requires its
separately qualified issued-proof receipt. Original content/producer guards stay.
"""
import copy
from uuid import UUID
from urllib.parse import urlsplit
from build_prepared_decision_outcome import digest
from build_operator_entry import _flatten
from build_selected_event_routes import audit_actions


def build(profile, binding):
    definition = profile['properties']['definition']
    if (binding.get('qualificationOnly') is not True
            or binding.get('approvedDefinitionSHA256') != digest(definition)
            or profile['properties'].get('state') != 'Stopped'
            or set(profile['properties']['connectionReferences']) != {'shared_sharepointonline'}):
        raise ValueError('Exact reviewed stopped fictional publisher required')
    required = {'qualificationOnly','approvedDefinitionSHA256','requestedFolder','expectedFolder',
                'requestedReceipt','expectedReceipt'}
    if set(binding) != required:
        raise ValueError('Exact folder and issued-receipt admission contract required')
    nodes = _flatten(definition['actions'])
    if any(n.startswith('PA_') for n in nodes):
        raise ValueError('Admission already bound')
    for n in ['Validate_publication_input','Issued_path','Find_issued',
              'Copy_binary_absent_only','Create_binary_publication']:
        if n not in nodes:
            raise ValueError('Reviewed two-phase publication shape required')
    template = nodes['Read_selected_case']
    params = template.get('inputs',{}).get('parameters',{})
    host = template.get('inputs',{}).get('host',{})
    site = urlsplit(params.get('dataset',''))
    if (template.get('type') != 'OpenApiConnection' or params.get('parameters/method') != 'GET'
            or 'parameters/body' in params or site.scheme != 'https' or not site.netloc
            or host.get('apiId') != '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
            or host.get('operationId') != 'HttpRequest'
            or not host.get('connectionName')
            or any(k.lower() in ('x-http-method','x-http-method-override','authorization')
                   for k in params.get('parameters/headers',{}))):
        raise ValueError('Qualified same-site GET-only reader required')
    def path(value):
        if (not isinstance(value,str) or not value.startswith(site.path+'/')
                or any(x in value for x in ('..','%','?','#','\\'))):
            raise ValueError('Canonical same-site native path required')
        return value
    def quote(value): return "'"+value.replace("'","''")+"'"
    requested = path(binding['requestedFolder'])
    folder = binding['expectedFolder']; receipt = binding['expectedReceipt']
    if not isinstance(folder,dict) or set(folder) != {'UniqueId','ServerRelativeUrl'}:
        raise ValueError('Independently observed native folder/receipt pins required')
    if receipt is None:
        if binding['requestedReceipt'] is not None:
            raise ValueError('Unqualified receipt cannot have an asserted native path')
    elif not isinstance(receipt,dict) or set(receipt) != {'UniqueId','ETag','ServerRelativeUrl'}:
        raise ValueError('Independently observed native receipt pins required')
    for value in [folder]+([receipt] if receipt is not None else []):
        if not isinstance(value['UniqueId'],str) or str(UUID(value['UniqueId'])) != value['UniqueId'].lower():
            raise ValueError('Native UUID required')
        path(value['ServerRelativeUrl'])
    if receipt is not None:
        path(binding['requestedReceipt'])
        if not isinstance(receipt['ETag'],str) or receipt['ETag'].strip() in ('','*'):
            raise ValueError('Exact issued-receipt ETag required')
    if not nodes['Issued_path']['inputs'].startswith('@concat('+quote(requested+'/FICTIONAL-issued-')+','):
        raise ValueError('Requested folder must bind the actual copy path')
    folder_uri='_api/web/GetFolderByServerRelativePath(decodedurl='+quote(requested)+')'
    if (folder_uri+'/Files').replace("'","''") not in nodes['Find_issued']['inputs']['parameters']['parameters/uri']:
        raise ValueError('Actual issued lookup must use the same destination')
    roots=definition['actions']
    def successful_input_path(name, visiting):
        if name == 'Validate_publication_input': return True
        if name in visiting or name not in roots: return False
        # Failed/timed-out verification may deliberately reach a fail-closed
        # diagnostic. Skipped admission must never release native work.
        return any(statuses and set(statuses) <= {'Succeeded','Failed','TimedOut'}
                   and successful_input_path(parent, visiting | {name})
                   for parent,statuses in roots[name].get('runAfter',{}).items())
    def has_native_io(node):
        return (node.get('type') == 'OpenApiConnection'
                or any(has_native_io(v) for v in node.get('actions',{}).values())
                or any(has_native_io(v) for v in node.get('else',{}).get('actions',{}).values())
                or any(has_native_io(v) for case in node.get('cases',{}).values()
                       for v in case.get('actions',{}).values())
                or any(has_native_io(v) for v in node.get('default',{}).get('actions',{}).values()))
    if any(has_native_io(node) and not successful_input_path(name,set()) for name,node in roots.items()):
        raise ValueError('Input validation must dominate every original native operation')
    out=copy.deepcopy(profile); a=out['properties']['definition']['actions']
    # Move every original direct consumer behind admission. Existing constant
    # checkpoint roots can precede input validation; no original writer changes.
    consumers=0
    for n,v in a.items():
        deps=v.get('runAfter',{})
        if 'Validate_publication_input' in deps:
            if deps['Validate_publication_input'] != ['Succeeded']:
                raise ValueError('Single-success input validation dependency required')
            deps['PA_Check_receipt']=deps.pop('Validate_publication_input');consumers+=1
    if not consumers: raise ValueError('Input validation must dominate publication')
    def read(uri,previous):
        action=copy.deepcopy(template);action['runAfter']={previous:['Succeeded']} if previous else {}
        action['inputs']['parameters'].update({'parameters/uri':uri,
            'parameters/headers':{'Accept':'application/json;odata=minimalmetadata'}})
        action['inputs']['retryPolicy']={'type':'none'}
        return action
    def compose(value,previous=None):
        return {'type':'Compose','inputs':value,'runAfter':{previous:['Succeeded']} if previous else {}}
    def halt(label):
        held='PA_Held_'+label
        return {held:compose({'qualified':False,'reason':label,'copyCreatedCount':0,
            'publicationCreatedCount':0,'progressionGranted':False,'realPolicyEffects':False}),
            'PA_Stop_'+label:{'type':'Terminate','inputs':{'runStatus':'Succeeded'},
                'runAfter':{held:['Succeeded']}}}
    def checks(name,expected):
        result=["equals(toLower(string(body('"+name+"')?['UniqueId'])),"+quote(expected['UniqueId'].lower())+')',
                "equals(body('"+name+"')?['ServerRelativeUrl'],"+quote(expected['ServerRelativeUrl'])+')']
        if 'ETag' in expected:result.append("equals(body('"+name+"')?['ETag'],"+quote(expected['ETag'])+')')
        else:result.append("equals(body('"+name+"')?['Exists'],true)")
        return '@and('+','.join(result)+')'
    a['PA_Read_destination']=read(folder_uri+'?$select=UniqueId,ServerRelativeUrl,Exists','Validate_publication_input')
    a['PA_Verify_destination']={'type':'If','expression':checks('PA_Read_destination',folder),
        'runAfter':{'PA_Read_destination':['Succeeded']},
        'actions':{'PA_Destination_admitted':compose({'qualified':True,'grantsAuthority':False})},
        'else':{'actions':halt('wrong_destination')}}
    a['PA_Destination_read_failure']={'type':'Scope','runAfter':{'PA_Read_destination':['Failed','TimedOut']},
        'actions':halt('destination_read_unqualified')}
    receipt_actions=halt('issued_receipt_not_qualified')
    if receipt is not None:
        r=read('_api/web/GetFileByServerRelativePath(decodedurl='+quote(binding['requestedReceipt'])+
            ')?$select=UniqueId,ETag,ServerRelativeUrl',None)
        verify={'type':'If','expression':checks('PA_Read_receipt',receipt),
        'runAfter':{'PA_Read_receipt':['Succeeded']},
        'actions':{'PA_Receipt_admitted':compose({'qualified':True,'grantsAuthority':False})},
        'else':{'actions':halt('receipt_changed')}}
        failure={'type':'If','expression':"@equals(outputs('PA_Read_receipt')?['statusCode'],404)",
        'runAfter':{'PA_Read_receipt':['Failed','TimedOut']},
        'actions':halt('missing_issued_receipt'),'else':{'actions':halt('receipt_read_unqualified')}}
        receipt_actions={'PA_Read_receipt':r,'PA_Verify_receipt':verify,'PA_Receipt_read_failure':failure}
    a['PA_Check_receipt']={'type':'If','expression':"@equals(triggerBody()?['text'],'Record publication')",
        'runAfter':{'PA_Verify_destination':['Succeeded']},
        'actions':receipt_actions,
        'else':{'actions':{'PA_Copy_receipt_not_required':compose({'receiptRequired':False,'publicationAllowed':False})}}}
    audit_actions(out['properties']['definition'])
    return out
