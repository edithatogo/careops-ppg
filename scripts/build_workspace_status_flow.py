#!/usr/bin/env python3
"""Prepare a private native flow definition from the existing deployment binding.

Run from repository root. This does not deploy or alter the importer.
Writes only .local/workspace/status-flow-create.json.
"""
import json
from pathlib import Path


def build(binding, source_binding):
    site=binding['destination']['siteUrl'];from urllib.parse import urlparse
    root=urlparse(site).path;lib=root+'/PPG Review Evidence';status_id=binding['workspace']['statusListId']
    old=source_binding;refs={'shared_sharepointonline':old['refs']['shared_sharepointonline']}
    def http(uri,after=None,method='GET',body=None,headers=None):
     params={'dataset':site,'parameters/method':method,'parameters/uri':uri,'parameters/headers':headers or {'Accept':'application/json;odata=nometadata'}}
     if body is not None:params['parameters/body']=body
     return {'type':'OpenApiConnection','inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_sharepointonline','connectionName':'shared_sharepointonline','operationId':'HttpRequest'},'parameters':params},'runAfter':after or {}}
    def comp(value,after):return {'type':'Compose','inputs':value,'runAfter':after}
    def parse(a):return f"@if(contains(body('{a}'),'$content'),json(base64ToString(body('{a}')?['$content'])),json(string(body('{a}'))))"
    def getfile(name):return f"_api/web/GetFileByServerRelativePath(decodedurl='{lib}/{name}')/$value"
    a={}
    a['Read_source']=http(getfile('qw3-source-state.json'))
    a['Source']=comp(parse('Read_source'),{'Read_source':['Succeeded']})
    a['Read_checkpoint']=http(getfile('qw3-last-successful.json'),{'Source':['Succeeded']})
    a['Checkpoint']=comp(parse('Read_checkpoint'),{'Read_checkpoint':['Succeeded']})
    a['List_attempts']=http(f"_api/web/GetFolderByServerRelativePath(decodedurl='{lib}')/Files?$select=Name,TimeLastModified&$filter=startswith(Name,'qw3-run-')&$orderby=TimeLastModified desc&$top=1",{'Checkpoint':['Succeeded']})
    a['Read_attempt']=http(f"@concat('_api/web/GetFileByServerRelativePath(decodedurl=''{lib}/',first(body('List_attempts')?['value'])?['Name'],''')/$value')",{'List_attempts':['Succeeded']})
    a['Attempt']=comp(parse('Read_attempt'),{'Read_attempt':['Succeeded']})
    a['Changed']=comp("@not(equals(outputs('Source')?['sourceETag'],outputs('Checkpoint')?['centralSourceETag']))",{'Attempt':['Succeeded']})
    a['Recent_failure']=comp("@and(equals(outputs('Attempt')?['status'],'failed_partial_or_unverified'),greater(ticks(coalesce(outputs('Attempt')?['asOfUtc'],'1900-01-01T00:00:00Z')),ticks(outputs('Checkpoint')?['asOfUtc'])))",{'Changed':['Succeeded']})
    valid="and(not(empty(outputs('Source')?['sourceETag'])),not(empty(outputs('Checkpoint')?['centralSourceETag'])),equals(outputs('Checkpoint')?['status'],'completed'),or(equals(outputs('Attempt')?['status'],'completed'),equals(outputs('Attempt')?['status'],'running'),equals(outputs('Attempt')?['status'],'failed_partial_or_unverified')),not(empty(outputs('Attempt')?['asOfUtc'])),lessOrEquals(ticks(outputs('Attempt')?['asOfUtc']),ticks(utcNow())),greaterOrEquals(outputs('Checkpoint')?['readbackCount'],1),lessOrEquals(ticks(outputs('Source')?['checkedUtc']),ticks(utcNow())),lessOrEquals(ticks(outputs('Checkpoint')?['asOfUtc']),ticks(utcNow())))"
    health=f"@if(not({valid}),'unknown',if(outputs('Changed'),if(and(outputs('Recent_failure'),not(equals(outputs('Attempt')?['attemptedWrites'],0))),'failed','held'),if(outputs('Recent_failure'),'failed',if(greater(ticks(utcNow()),ticks(addMinutes(outputs('Source')?['checkedUtc'],90))),'unknown','healthy'))))"
    a['Health']=comp(health,{'Recent_failure':['Succeeded']})
    reason="@if(equals(outputs('Health'),'held'),'Source change detected—reconciliation held',if(equals(outputs('Health'),'failed'),'Latest reconciliation failed or remains unverified; last successful baseline retained',if(equals(outputs('Health'),'healthy'),'Latest observed source matches the last verified reconciliation','Evidence missing, inconsistent or source check overdue')))"
    a['Projection']=comp({'Title':'Source catalogue refresh','Health':"@outputs('Health')",'LatestCheck':"@outputs('Source')?['checkedUtc']",'LatestAttemptOutcome':"@outputs('Attempt')?['status']",'LastSuccessfulReconciliation':"@outputs('Checkpoint')?['asOfUtc']",'ObservedVersion':"@outputs('Source')?['sourceETag']",'CommittedVersion':"@outputs('Checkpoint')?['centralSourceETag']",'CommittedCount':"@outputs('Checkpoint')?['readbackCount']",'ProjectedAt':'@utcNow()','Reason':reason,'NextAction':"@if(equals(outputs('Health'),'healthy'),'None','Inspect source-sync evidence; resolve identity exceptions through the existing identity contract. Do not extend the ledger automatically.')",'EvidenceLink':f"@concat('{site}/PPG Review Evidence/',first(body('List_attempts')?['value'])?['Name'])"},{'Health':['Succeeded']})
    # Fixed adopted item ID is a private binding, not an upsert/create in each run.
    uri=f"_api/web/lists(guid'{status_id}')/items({binding['workspace']['statusItemId']})"
    headers={'Accept':'application/json;odata=nometadata','Content-Type':'application/json;odata=nometadata','IF-MATCH':'*','X-HTTP-Method':'MERGE'}
    a['Update_status']=http(uri,{'Projection':['Succeeded']},'POST',"@string(outputs('Projection'))",headers)
    unknown={'Title':'Source catalogue refresh','Health':'unknown','LatestCheck':None,'LatestAttemptOutcome':'Evidence read or validation failed','LastSuccessfulReconciliation':None,'ObservedVersion':None,'CommittedVersion':None,'CommittedCount':None,'ProjectedAt':'@utcNow()','Reason':'Evidence read, parse or consistency check failed; no healthy result inferred','NextAction':'Inspect projection flow and source-sync evidence','EvidenceLink':site+'/PPG Review Evidence/Forms/AllItems.aspx'}
    definition={'$schema':'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#','contentVersion':'1.0.0.0','parameters':{'$authentication':{'defaultValue':{},'type':'SecureObject'},'$connections':{'defaultValue':{},'type':'Object'}},'triggers':{'Every_15_minutes':{'type':'Recurrence','recurrence':{'frequency':'Minute','interval':15,'timeZone':'E. Australia Standard Time'},'runtimeConfiguration':{'concurrency':{'runs':1}}}},'actions':{'Project':{'type':'Scope','actions':a,'runAfter':{}},'Unknown_on_failure':http(uri,{'Project':['Failed','TimedOut']},'POST',json.dumps(unknown).replace('"@utcNow()"','"@{utcNow()}"'),headers)},'outputs':{}}
    request={'env':old['env'],'name':'PPG Workspace — quiet status projection','state':'Stopped','connectionRefs':refs,'definition':definition}
    return request


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, default=Path('.local/deployment.json'))
    parser.add_argument('--source-binding', type=Path, default=Path('.local/source-sync/native-scheduled-qualified-definition.json'))
    parser.add_argument('--output', type=Path, default=Path('.local/workspace/status-flow-create.json'))
    args = parser.parse_args()
    if '.local' not in args.output.parts:
        parser.error('Native flow definitions must remain under .local')
    result = build(json.loads(args.binding.read_text()), json.loads(args.source_binding.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('Prepared presentation-only flow; no native writes performed')
