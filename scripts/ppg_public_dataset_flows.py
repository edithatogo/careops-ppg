"""Standard-connector public JSON captures, separated from policy review leads."""
from ppg_source_update_flows import reference, recurrence, SP
from urllib.parse import urlsplit
import re

OD='/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness'


def build(binding, sources, *, manual=False):
    if not sources or not re.fullmatch(r'[a-f0-9-]{36}',binding['listId']):
        raise ValueError('Sources and exact staging list required')
    refs={'shared_onedriveforbusiness':reference(binding['onedrive'],OD),'shared_sharepointonline':reference(binding['sharepoint'],SP)}
    actions={};previous=None;keys=set()
    def action(op,params,after,api=OD,connection='shared_onedriveforbusiness'):
        return {'type':'OpenApiConnection','runAfter':after,'inputs':{'host':{'apiId':api,'connectionName':connection,'operationId':op},'parameters':params,'retryPolicy':{'type':'none'}}}
    for source in sources:
        key=source['key'];u=urlsplit(source['url'])
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,80}',key) or key in keys or u.scheme!='https' or u.username or u.password or u.fragment:
            raise ValueError('Unique source key and public HTTPS URL required')
        keys.add(key);n=key.replace('-','_');path=n+'_path';download=n+'_download';read=n+'_read';parsed=n+'_json';complete=n+'_complete';persist=n+'_persist'
        actions[path]={'type':'Compose','runAfter':{previous:['Succeeded']} if previous else {},'inputs':"@concat('/PPG-dataset-"+key+"-',workflow()?['run']?['name'],'.json')"}
        actions[download]=action('CopyFile',{'source':source['url'],'destination':"@outputs('"+path+"')",'overwrite':False},{path:['Succeeded']})
        metadata=n+'_metadata';poll=n+'_poll';ready=n+'_ready'
        completed="and(equals(actions('"+metadata+"')?['status'],'Succeeded'),greater(coalesce(body('"+metadata+"')?['Size'],0),0))"
        error="and(not(equals(actions('"+metadata+"')?['status'],'Succeeded')),not(equals(outputs('"+metadata+"')?['statusCode'],404)))"
        actions[poll]={'type':'Until','runAfter':{download:['Succeeded']},'expression':'@or('+completed+','+error+')','limit':{'count':12,'timeout':'PT2M'},'actions':{
            n+'_delay':{'type':'Wait','runAfter':{},'inputs':{'interval':{'count':5,'unit':'Second'}}},
            metadata:action('GetFileMetadataByPath',{'path':"@outputs('"+path+"')"},{n+'_delay':['Succeeded']}),
            n+'_observe':{'type':'Compose','runAfter':{metadata:['Succeeded','Failed','TimedOut']},'inputs':"@actions('"+metadata+"')?['status']"}}}
        actions[ready]={'type':'ParseJson','runAfter':{poll:['Succeeded']},'inputs':{'content':{'ready':'@'+completed},'schema':{'type':'object','required':['ready'],'properties':{'ready':{'type':'boolean','enum':[True]}}}}}
        actions[read]=action('GetFileContentByPath',{'path':"@outputs('"+path+"')",'inferContentType':False},{ready:['Succeeded']})
        actions[parsed]={'type':'Compose','runAfter':{read:['Succeeded']},'inputs':"@json(base64ToString(body('"+read+"')?['$content']))"}
        actions[complete]={'type':'ParseJson','runAfter':{parsed:['Succeeded']},'inputs':{'content':{'complete':"@and(equals(outputs('"+parsed+"')?['success'],true),not(equals(outputs('"+parsed+"')?['result']?['records'],null)),equals(length(outputs('"+parsed+"')?['result']?['records']),outputs('"+parsed+"')?['result']?['total']))"},'schema':{'type':'object','required':['complete'],'properties':{'complete':{'type':'boolean','enum':[True]}}}}}
        payload=n+'_payload';actions[payload]={'type':'Compose','runAfter':{complete:['Succeeded']},'inputs':{'Title':source['name'],'SourceKey':"@concat('"+key+":',workflow()?['run']?['name'])",'ObservedAt':'@utcNow()','CapturePath':"@outputs('"+path+"')",'RecordCount':"@length(outputs('"+parsed+"')?['result']?['records'])",'SourceLink':source['url'],'ProcessingState':'Captured'}}
        actions[persist]=action('HttpRequest',{'dataset':binding['site'],'parameters/method':'POST','parameters/uri':"_api/web/lists(guid'"+binding['listId']+"')/items",'parameters/headers':{'Accept':'application/json;odata=nometadata','Content-Type':'application/json;odata=nometadata'},'parameters/body':"@string(outputs('"+payload+"'))"},{payload:['Succeeded']},SP,'shared_sharepointonline');previous=persist
    failure={'Title':'Public dataset collection failed','SourceKey':"@concat('failure:',workflow()?['run']?['name'])",'ObservedAt':'@utcNow()','ProcessingState':'Failed','SourceLink':sources[0]['url']}
    actions={'Collect_datasets':{'type':'Scope','runAfter':{},'actions':actions},
             'Failure_payload':{'type':'Compose','runAfter':{'Collect_datasets':['Failed','TimedOut']},'inputs':failure},
             'Record_failure':action('HttpRequest',{'dataset':binding['site'],'parameters/method':'POST','parameters/uri':"_api/web/lists(guid'"+binding['listId']+"')/items",'parameters/headers':{'Accept':'application/json;odata=nometadata','Content-Type':'application/json;odata=nometadata'},'parameters/body':"@string(outputs('Failure_payload'))"},{'Failure_payload':['Succeeded']},SP,'shared_sharepointonline'),
             'Fail_collection':{'type':'Terminate','runAfter':{'Record_failure':['Succeeded']},'inputs':{'runStatus':'Failed','runError':{'code':'DatasetCaptureFailed','message':'See staging failure record and native action history; no checkpoint advanced.'}}}}
    trigger={'type':'Request','kind':'Button','inputs':{'schema':{'type':'object','properties':{}}},'runtimeConfiguration':{'concurrency':{'runs':1}}} if manual else recurrence()
    return {'properties':{'displayName':'PPG | Source updates | Public datasets | Captures | API','state':'Stopped','flowFailureAlertSubscribed':False,'connectionReferences':refs,'definition':{'$schema':'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#','contentVersion':'1.0.0.0','parameters':{'$authentication':{'type':'SecureObject','defaultValue':{}},'$connections':{'type':'Object','defaultValue':{}}},'triggers':{'manual' if manual else 'Scheduled_collection':trigger},'actions':actions,'outputs':{}}}}
