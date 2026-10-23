"""Build a read-only on-demand standards check using the qualified Standard pair."""
import copy

SLOTS=('frameworks','requirements','mappings','crosswalks','relationships','catalogue')


def build(bindings):
    refs=copy.deepcopy(bindings['connectionReferences'])
    if set(refs)!={'shared_sharepointonline','shared_excelonlinebusiness'} or any(r.get('source')!='Embedded' for r in refs.values()):
        raise ValueError('Only existing qualified embedded Standard connections allowed')
    registers=bindings['registers']
    if set(registers)!=set(SLOTS):raise ValueError('All five registers and catalogue required')
    parameters=copy.deepcopy(bindings['scriptParameters'])
    if set(parameters)!={'source','drive','file','scriptSource','scriptDrive','scriptId'}:raise ValueError('Exact workbook/script bindings required')
    actions={};previous=None
    def read(name,slot):
        nonlocal previous
        actions[name]={'type':'OpenApiConnection','runAfter':{previous:['Succeeded']} if previous else {},'inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_sharepointonline','connectionName':'shared_sharepointonline','operationId':'HttpRequest'},'parameters':{'dataset':bindings['site'],'parameters/method':'GET','parameters/uri':"_api/web/lists(guid'"+registers[slot]+"')/items?$top=5000",'parameters/headers':{'Accept':'application/json;odata=nometadata'}}}}
        previous=name
    for slot in SLOTS:read('Read_'+slot,slot)
    actions['Validation_request']={'type':'Compose','runAfter':{previous:['Succeeded']},'inputs':{'kind':'ppg-standards-context-v1','native':{slot:"@body('Read_"+slot+"')" for slot in SLOTS},'documentUID':"@triggerBody()?['documentUID']",'documentVersion':"@triggerBody()?['documentVersion']"}}
    parameters['ScriptParameters/requestJson']="@string(outputs('Validation_request'))"
    actions['Run_standards_check']={'type':'OpenApiConnection','runAfter':{'Validation_request':['Succeeded']},'inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_excelonlinebusiness','connectionName':'shared_excelonlinebusiness','operationId':'RunScriptProdV2'},'parameters':parameters}}
    actions['Parsed_context']={'type':'Compose','runAfter':{'Run_standards_check':['Succeeded']},'inputs':"@json(body('Run_standards_check')?['result'])"};previous='Parsed_context'
    for slot in SLOTS:read('Recheck_'+slot,slot)
    condition='@and('+','.join("equals(body('Read_"+slot+"'),body('Recheck_"+slot+"'))" for slot in SLOTS)+')'
    actions['Source_snapshot_stable']={'type':'If','runAfter':{previous:['Succeeded']},'expression':condition,'actions':{'Report_context':{'type':'Compose','runAfter':{},'inputs':{'context':"@outputs('Parsed_context')",'scriptSHA256':bindings['scriptSHA256'],'contractSHA256':bindings['contractSHA256'],'nativeWrites':0,'notificationsEnabled':False}}},'else':{'actions':{'Hold_changed_source':{'type':'Terminate','runAfter':{},'inputs':{'runStatus':'Failed','runError':{'code':'StandardsSourceChanged','message':'Standards or catalogue changed during validation. No record changed; inspect and run a fresh check.'}}}}}}
    schema={'type':'object','properties':{k:{'type':'string','title':t,'x-ms-dynamically-added':True,'x-ms-content-hint':'TEXT'} for k,t in [('documentUID','Document UID'),('documentVersion','Document version')]},'required':['documentUID','documentVersion']}
    definition={'$schema':'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#','contentVersion':'1.0.0.0','parameters':{'$authentication':{'type':'SecureObject','defaultValue':{}},'$connections':{'type':'Object','defaultValue':{}}},'triggers':{'manual':{'type':'Request','kind':'Button','inputs':{'schema':schema}}},'actions':actions,'outputs':{}}
    return {'properties':{'displayName':'PPG | On-demand standards and relationship check','state':'Stopped','definition':definition,'connectionReferences':refs}}
