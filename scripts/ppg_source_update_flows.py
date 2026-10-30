# Copyright 2026 PPG Workbench contributors
# SPDX-License-Identifier: Apache-2.0
"""Small source-update collectors. Bindings stay private; definitions start stopped."""
import json
import re
from urllib.parse import urlsplit

SP='/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
RSS='/providers/Microsoft.PowerApps/apis/shared_rss'
MAIL='/providers/Microsoft.PowerApps/apis/shared_office365'
FEED='https://www.safetyandquality.gov.au/rss.xml'


def reference(value, api):
    if (not isinstance(value,dict) or value.get('id')!=api or value.get('source')!='Embedded'
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',value.get('connectionName',''))):
        raise ValueError('Exact existing connector binding required')
    return {k:value[k] for k in ('id','source','connectionName')}


def recurrence():
    return {'type':'Recurrence','recurrence':{'frequency':'Day','interval':1,'timeZone':'E. Australia Standard Time','schedule':{'hours':[7],'minutes':[0]}},'runtimeConfiguration':{'concurrency':{'runs':1}}}


def build(channel, binding, *, manual=False, pending_sender=False):
    if channel not in ('rss','newsletter','meteor'):raise ValueError('Unknown source channel')
    if pending_sender and channel!='newsletter':raise ValueError('Pending sender mode is newsletter-only')
    refs={};actions={}
    if channel=='meteor':
        ids=binding.get('indicatorIds')
        if not isinstance(ids,list) or not ids or any(not re.fullmatch(r'[0-9]{6,9}',str(i))for i in ids):raise ValueError('Explicit indicator identifiers required')
        actions={'Access_dependencies':{'type':'Terminate','runAfter':{},'inputs':{'runStatus':'Failed','runError':{'code':'MeteorAccessPending','message':'API approval, secure HMAC signing, supported connection and licensing must be qualified before replacing this stop.'}}},'Selected_endpoints':{'type':'Compose','runAfter':{'Access_dependencies':['Succeeded']},'inputs':{'search':'https://meteor-api.aihw.gov.au/api/v1.0/Indicators','items':['https://meteor-api.aihw.gov.au/api/v1.0/Indicators/'+str(i)for i in ids],'nativeAccessQualified':False}}}
    else:
        site=binding['site'];u=urlsplit(site)
        if u.scheme!='https' or not u.hostname or not u.hostname.endswith('.sharepoint.com') or u.query or u.fragment or u.username:raise ValueError('Exact SharePoint site required')
        list_id=binding['listId']
        if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}',list_id):raise ValueError('Exact lead list required')
        refs['shared_sharepointonline']=reference(binding['sharepoint'],SP)
        def http(method,uri,body=None,after=None):
            params={'dataset':site,'parameters/method':method,'parameters/uri':uri,'parameters/headers':{'Accept':'application/json;odata=nometadata','Content-Type':'application/json;odata=nometadata'}}
            if body is not None:params['parameters/body']=body
            return {'type':'OpenApiConnection','runAfter':after or {},'inputs':{'host':{'apiId':SP,'connectionName':'shared_sharepointonline','operationId':'HttpRequest'},'parameters':params,'retryPolicy':{'type':'none'}}}
        if channel=='rss':
            refs['shared_rss']=reference(binding['rss'],RSS)
            actions['Read_feed']={'type':'OpenApiConnection','runAfter':{},'inputs':{'host':{'apiId':RSS,'connectionName':'shared_rss','operationId':'ListFeedItems'},'parameters':{'feedUrl':FEED},'retryPolicy':{'type':'none'}}}
            collection="@body('Read_feed')";after={'Read_feed':['Succeeded']}
            source_id="@coalesce(item()?['id'],item()?['primaryLink'],'')";title="@coalesce(item()?['title'],'Untitled source update')";link="@coalesce(item()?['primaryLink'],'https://www.safetyandquality.gov.au/news-and-media/latest-news')";date="@item()?['publishDate']"
        else:
            refs['shared_office365']=reference(binding['outlook'],MAIL)
            if not isinstance(binding.get('folderId'),str) or not binding['folderId']:raise ValueError('Exact newsletter folder required')
            senders=binding.get('senders')
            if not isinstance(senders,list)or (not senders and not pending_sender) or any(not re.fullmatch(r'[^\s@;]+@[^\s@;]+\.[^\s@;]+',s)for s in senders):raise ValueError('Verified exact newsletter senders required')
            collection='@createArray(triggerBody())';after={}
            source_id="@coalesce(item()?['internetMessageId'],item()?['id'],'')";title="@coalesce(item()?['subject'],'Untitled newsletter')";link="@coalesce(item()?['webLink'],'https://www.safetyandquality.gov.au/news-and-media/newsletters')";date="@item()?['receivedDateTime']"
        base="_api/web/lists(guid'"+list_id+"')/items"
        observation={'sourceId':source_id,'title':title,'link':link,'publishedAt':date}
        if channel=='rss':observation['sourceObservation']="@item()"
        if channel=='newsletter':observation['publisherLinks']="@body('Publisher_links')"
        work={'Observation':{'type':'Compose','runAfter':{},'inputs':observation},'Source_id':{'type':'Compose','runAfter':{'Observation':['Succeeded']},'inputs':source_id}}
        if channel=='newsletter':
            work['Email_link_fragments']={'type':'Query','runAfter':{},'inputs':{'from':"@skip(split(replace(string(coalesce(item()?['body'],'')),decodeUriComponent('%27'),'\"'),'href=\"'),1)",'where':"@startsWith(item(),'https://www.safetyandquality.gov.au/')"}}
            work['Publisher_links']={'type':'Select','runAfter':{'Email_link_fragments':['Succeeded']},'inputs':{'from':"@body('Email_link_fragments')",'select':{'url':"@replace(first(split(item(),'\"')),'&amp;','&')"}}}
            work['Observation']['runAfter']={'Publisher_links':['Succeeded']}
        uri="@concat('"+base.replace("'", "''")+"?$select=Id,Fingerprint&$filter=ChannelKey%20eq%20%27"+channel+"%27%20and%20SourceKey%20eq%20%27',uriComponent(replace(outputs('Source_id'),'''','''''')),'%27&$top=5000')"
        read=http('GET',uri)
        fingerprint="@string(outputs('Observation'))"
        write=http('POST',base,{'Title':"@take(string(outputs('Observation')?['title']),255)",'ChannelKey':channel,'SourceKey':"@outputs('Source_id')",'Fingerprint':fingerprint,'ObservedAt':'@utcNow()','SourceLink':"@outputs('Observation')?['link']",'ProcessingState':'Proposed','ObservationJSON':fingerprint})
        lead_payload=write['inputs']['parameters']['parameters/body']
        write['inputs']['parameters']['parameters/body']="@string(outputs('Lead_payload'))"
        write['runAfter']={'Lead_payload':['Succeeded']}
        ready={'Read_existing':read,'Match_existing':{'type':'Query','runAfter':{'Read_existing':['Succeeded']},'inputs':{'from':"@body('Read_existing')?['value']",'where':"@equals(item()?['Fingerprint'],string(outputs('Observation')))"}},'Require_complete_query':{'type':'ParseJson','runAfter':{'Match_existing':['Succeeded']},'inputs':{'content':{'complete':"@and(empty(body('Read_existing')?['odata.nextLink']),empty(body('Read_existing')?['@odata.nextLink']))"},'schema':{'type':'object','required':['complete'],'properties':{'complete':{'type':'boolean','enum':[True]}}}}},'Create_if_changed':{'type':'If','runAfter':{'Require_complete_query':['Succeeded']},'expression':"@empty(body('Match_existing'))",'actions':{'Lead_payload':{'type':'Compose','runAfter':{},'inputs':lead_payload},'Persist_lead':write},'else':{'actions':{}}}}
        work['Require_identity']={'type':'ParseJson','runAfter':{'Source_id':['Succeeded']},'inputs':{'content':{'id':"@outputs('Source_id')"},'schema':{'type':'object','required':['id'],'properties':{'id':{'type':'string','minLength':1,'maxLength':255}}}}}
        ready['Read_existing']['runAfter']={'Require_identity':['Succeeded']}
        work.update(ready)
        actions['Collect']={'type':'Foreach','foreach':collection,'runAfter':after,'runtimeConfiguration':{'concurrency':{'repetitions':1}},'actions':work}
        collection_actions=actions
        failure=http('POST',base,{'Title':'Source collection failed','ChannelKey':channel,'SourceKey':"@workflow()?['run']?['name']",'Fingerprint':"@workflow()?['run']?['name']",'ObservedAt':'@utcNow()','SourceLink':FEED if channel=='rss' else 'https://www.safetyandquality.gov.au/news-and-media/newsletters','ProcessingState':'Failed','ObservationJSON':json.dumps({'kind':'source-update-failure','reason':'Inspect the owned flow run; no protected body is copied into this record.'})},after={'Collect_source':['Failed','TimedOut']})
        failure_payload=failure['inputs']['parameters']['parameters/body']
        failure['inputs']['parameters']['parameters/body']="@string(outputs('Failure_payload'))"
        failure['runAfter']={'Failure_payload':['Succeeded']}
        actions={'Failure_payload':{'type':'Compose','runAfter':{'Collect_source':['Failed','TimedOut']},'inputs':failure_payload},'Collect_source':{'type':'Scope','runAfter':{},'actions':collection_actions},'Record_failure':failure,'Fail_collection':{'type':'Terminate','runAfter':{'Record_failure':['Succeeded']},'inputs':{'runStatus':'Failed','runError':{'code':'SourceCollectionFailed','message':'Source collection failed; see its review-lead error record and run history.'}}}}
    trigger=recurrence()
    if manual:trigger={'type':'Request','kind':'Button','inputs':{'schema':{'type':'object','properties':{}}},'runtimeConfiguration':{'concurrency':{'runs':1}}}
    elif channel=='newsletter':trigger={'type':'OpenApiConnectionNotification','inputs':{'host':{'apiId':MAIL,'connectionName':'shared_office365','operationId':'OnNewEmailV3'},'parameters':{'folderPath':binding['folderId'],'from':';'.join(binding['senders']),'includeAttachments':False}},'splitOn':"@triggerOutputs()?['body/value']",'runtimeConfiguration':{'concurrency':{'runs':1}}}
    if pending_sender:refs.pop('shared_sharepointonline',None)
    if pending_sender:actions={'Verified_sender_required':{'type':'Terminate','runAfter':{},'inputs':{'runStatus':'Failed','runError':{'code':'NewsletterSenderUnverified','message':'No subscribed newsletter message was found. Verify its exact sender before replacing this guard and enabling collection.'}}}}
    if channel=='newsletter' and not binding.get('senders'):trigger['inputs']['parameters'].pop('from',None)
    return {'properties':{'displayName':'PPG | Source updates | '+channel,'state':'Stopped','flowFailureAlertSubscribed':False,'connectionReferences':refs,'definition':{'$schema':'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#','contentVersion':'1.0.0.0','parameters':{'$authentication':{'type':'SecureObject','defaultValue':{}},'$connections':{'type':'Object','defaultValue':{}}},'triggers':{'manual' if manual else 'Newsletter_arrival' if channel=='newsletter' else 'Scheduled_collection':trigger},'actions':actions,'outputs':{}}}}


def main():
    import argparse,os
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--channel',choices=['rss','newsletter','meteor'],required=True);p.add_argument('--binding',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--manual',action='store_true');p.add_argument('--prepare-newsletter',action='store_true');a=p.parse_args()
    result=build(a.channel,json.loads(a.binding.read_text()),manual=a.manual,pending_sender=a.prepare_newsletter)
    with os.fdopen(os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w')as f:f.write(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
