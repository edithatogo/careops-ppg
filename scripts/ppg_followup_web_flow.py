"""Build the bounded manual follow-up/history + send-free digest flow."""
import copy
from scripts.ppg_role_web_flow import script_package

SLOTS=('requests','contexts','events','digests','ownership','cases')

def build(bindings):
    refs=copy.deepcopy(bindings['connectionReferences'])
    if set(refs)!={'shared_sharepointonline','shared_excelonlinebusiness'} or any(x.get('source')!='Embedded' for x in refs.values()):
        raise ValueError('Use the existing qualified Standard connector pair')
    if set(bindings['registers'])!=set(SLOTS):raise ValueError('All six exact registers required')
    parameters=copy.deepcopy(bindings['scriptParameters'])
    if set(parameters)!={'source','drive','file','scriptSource','scriptDrive','scriptId'}:raise ValueError('Dedicated workbook and script required')
    if set(bindings['maps'])!={'requests','contexts','events','digests'}:raise ValueError('Exact four-register field maps required')
    actions={}
    def http(uri,method='GET',body=None):
        params={'dataset':bindings['site'],'parameters/method':method,'parameters/uri':uri,'parameters/headers':{'Accept':'application/json;odata=nometadata'}}
        if body is not None:params.update({'parameters/body':body});params['parameters/headers']['Content-Type']='application/json;odata=nometadata'
        return {'type':'OpenApiConnection','inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_sharepointonline','connectionName':'shared_sharepointonline','operationId':'HttpRequest'},'parameters':params,'retryPolicy':{'type':'none'}},'runAfter':{}}
    def reads(prefix,after):
        previous=after
        for slot in SLOTS:
            suffix='?$top=5000&$orderby=Id asc'
            if slot=='requests':suffix+='&$select=*,Author/Title,Editor/Title&$expand=Author,Editor'
            name=prefix+slot;actions[name]=http("_api/web/lists(guid'"+bindings['registers'][slot]+"')/items"+suffix)
            actions[name]['runAfter']={previous:['Succeeded']} if previous else {};previous=name
        return previous
    def script(name,compose,after,inputs):
        actions[compose]={'type':'Compose','inputs':inputs,'runAfter':{after:['Succeeded']}}
        p=copy.deepcopy(parameters);p['ScriptParameters/requestJson']="@string(outputs('"+compose+"'))"
        actions[name]={'type':'OpenApiConnection','runAfter':{compose:['Succeeded']},'inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_excelonlinebusiness','connectionName':'shared_excelonlinebusiness','operationId':'RunScriptProdV2'},'parameters':p,'retryPolicy':{'type':'none'}}}
    previous=reads('Read_',None)
    common={'requestId':"@triggerBody()?['requestId']",'maps':bindings['maps']}
    script('Plan_followup','Plan_request',previous,dict(common,native={k:"@body('Read_"+k+"')" for k in SLOTS}))
    actions['Parsed_plan']={'type':'Compose','runAfter':{'Plan_followup':['Succeeded']},'inputs':"@json(body('Plan_followup')?['result'])"}
    uri="@concat('_api/web/lists(guid''',if(equals(items('Persist_rows')?['target'],'events'),'"+bindings['registers']['events']+"','"+bindings['registers']['digests']+"'),''')/items')"
    write=http(uri,'POST',"@string(items('Persist_rows')?['payload'])")
    actions['Persist_rows']={'type':'Foreach','foreach':"@outputs('Parsed_plan')?['writes']",'runAfter':{'Parsed_plan':['Succeeded']},'runtimeConfiguration':{'concurrency':{'repetitions':1}},'actions':{'Only_missing':{'type':'If','expression':"@equals(items('Persist_rows')?['create'],true)",'runAfter':{},'actions':{'Create_row':write},'else':{'actions':{}}}}}
    previous=reads('Verify_','Persist_rows')
    verify=dict(common,phase='verify',originalPlan="@outputs('Parsed_plan')",native={k:"@body('Verify_"+k+"')" for k in SLOTS})
    script('Verify_saved_rows','Verification_request',previous,verify)
    actions['Verified_plan']={'type':'Compose','runAfter':{'Verify_saved_rows':['Succeeded']},'inputs':"@json(body('Verify_saved_rows')?['result'])"}
    create=http("_api/web/lists(guid'"+bindings['registers']['digests']+"')/items",'POST',"@string(outputs('Parsed_plan')?['completion']?['payload'])")
    actions['Commit_completion']={'type':'If','expression':"@equals(outputs('Parsed_plan')?['completion']?['create'],true)",'runAfter':{'Verified_plan':['Succeeded']},'actions':{'Create_completion_marker':create},'else':{'actions':{}}}
    actions['Read_completed_digest']=http("_api/web/lists(guid'"+bindings['registers']['digests']+"')/items?$top=5000&$orderby=Id asc")
    actions['Read_completed_digest']['runAfter']={'Commit_completion':['Succeeded']}
    final=copy.deepcopy(verify);final['verifyCompletion']=True;final['native']['digests']="@body('Read_completed_digest')"
    script('Verify_completion','Completion_request','Read_completed_digest',final)
    actions['Report_followup']={'type':'Compose','runAfter':{'Verify_completion':['Succeeded']},'inputs':{'result':"@json(body('Verify_completion')?['result'])?['report']",'runKey':"@outputs('Parsed_plan')?['runKey']",'historyUrl':bindings['historyUrl'],'digestUrl':"@concat('"+bindings['digestUrl']+"?FilterField1="+bindings['maps']['digests']['RunKey']+"&FilterValue1=',uriComponent(outputs('Parsed_plan')?['runKey']))",'notificationsEnabled':False,'deliveryEligible':False,'scriptSHA256':bindings['scriptSHA256']}}
    schema={'type':'object','properties':{'requestId':{'type':'string','title':'Follow-up request item ID','description':'Create the request in the web List first. Enter its numeric item ID.','x-ms-dynamically-added':True,'x-ms-content-hint':'TEXT'}},'required':['requestId']}
    definition={'$schema':'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#','contentVersion':bindings.get('contentVersion','1.0.0.0'),'parameters':{'$authentication':{'type':'SecureObject','defaultValue':{}},'$connections':{'type':'Object','defaultValue':{}}},'triggers':{'manual':{'type':'Request','kind':'Button','inputs':{'schema':schema},'runtimeConfiguration':{'concurrency':{'runs':1}}}},'actions':actions,'outputs':{}}
    return {'properties':{'displayName':'PPG | On-demand follow-up and digest preview','state':'Stopped','definition':definition,'connectionReferences':refs}}
