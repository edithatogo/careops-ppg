"""Small source-update collectors. Bindings stay private; definitions start stopped."""
import json
import re
from urllib.parse import urlsplit

SP='/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
RSS='/providers/Microsoft.PowerApps/apis/shared_rss'
MAIL='/providers/Microsoft.PowerApps/apis/shared_office365'
FEED='https://www.safetyandquality.gov.au/rss.xml'


CONFIG_VERSION='1.1.0'


def quoted(value):
    """Quote a trusted configuration string as a workflow expression literal."""
    return "'" + value.replace("'", "''") + "'"


def source_config(channel, source=None):
    if source is None and channel=='sharepoint':raise ValueError('Explicit internal source configuration required')
    if source is None:
        source={'key':'acsqhc-rss' if channel=='rss' else 'acsqhc-newsletter',
                'publisher':'ACSQHC','name':'Updates' if channel=='rss' else 'Newsletters',
                'fallbackUrl':FEED if channel=='rss' else 'https://www.safetyandquality.gov.au/news-and-media/newsletters',
                'linkDomains':['www.safetyandquality.gov.au'],'feedUrl':FEED}
    source=dict(source)
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',source.get('key','')) or len(source['key'])>120:
        raise ValueError('Stable source catalogue key required')
    for field in ('publisher','name'):
        if not isinstance(source.get(field),str) or not source[field].strip() or len(source[field])>80 or any(c in source[field] for c in '\r\n|'):
            raise ValueError('Simple publisher and channel names required')
    for field in (('fallbackUrl','feedUrl') if channel=='rss' else ('fallbackUrl',)):
        u=urlsplit(source.get(field,''))
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.fragment:
            raise ValueError('Public HTTPS source URL required')
    if source['key']=='acsqhc-rss' and (channel!='rss' or source['feedUrl']!=FEED):
        raise ValueError('Legacy namespace belongs only to the Commission feed')
    domains=source.get('linkDomains',[])
    if channel=='newsletter' and (not domains or any(not isinstance(d,str) or not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*',d) for d in domains)):
        raise ValueError('Explicit publisher link hosts required')
    return source


def reference(value, api):
    if (not isinstance(value,dict) or value.get('id')!=api or value.get('source')!='Embedded'
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',value.get('connectionName',''))):
        raise ValueError('Exact existing connector binding required')
    return {k:value[k] for k in ('id','source','connectionName')}


def recurrence():
    return {'type':'Recurrence','recurrence':{'frequency':'Day','interval':1,'timeZone':'E. Australia Standard Time','schedule':{'hours':[7],'minutes':[0]}},'runtimeConfiguration':{'concurrency':{'runs':1}}}


def build(channel, binding, *, manual=False, pending_sender=False, source=None):
    if channel not in ('rss','newsletter','sharepoint','meteor'):raise ValueError('Unknown source channel')
    if pending_sender and channel!='newsletter':raise ValueError('Pending sender mode is newsletter-only')
    config=source_config(channel,source) if channel!='meteor' else None
    # Preserve the existing Commission RSS namespace and fingerprint for zero-create upgrades.
    channel_key='rss' if config and config['key']=='acsqhc-rss' else (channel+':'+config['key'] if config else channel)
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
            actions['Read_feed']={'type':'OpenApiConnection','runAfter':{},'inputs':{'host':{'apiId':RSS,'connectionName':'shared_rss','operationId':'ListFeedItems'},'parameters':{'feedUrl':config['feedUrl']},'retryPolicy':{'type':'none'}}}
            collection="@body('Read_feed')";after={'Read_feed':['Succeeded']}
            source_id="@if(empty(item()?['id']),coalesce(item()?['primaryLink'],''),item()?['id'])";title="@coalesce(item()?['title'],'Untitled source update')";link="@if(empty(item()?['primaryLink']),"+quoted("https://www.safetyandquality.gov.au/news-and-media/latest-news" if config["key"]=="acsqhc-rss" else config["fallbackUrl"])+",item()?['primaryLink'])";date="@item()?['publishDate']"
        elif channel=='newsletter':
            refs['shared_office365']=reference(binding['outlook'],MAIL)
            if not isinstance(binding.get('folderId'),str) or not binding['folderId']:raise ValueError('Exact newsletter folder required')
            senders=binding.get('senders')
            if not isinstance(senders,list)or (not senders and not pending_sender) or any(not re.fullmatch(r'[^\s@;]+@[^\s@;]+\.[^\s@;]+',s)for s in senders):raise ValueError('Verified exact newsletter senders required')
            collection='@createArray(triggerBody())';after={}
            if manual:
                message_id=binding.get('messageId')
                if not isinstance(message_id,str) or not message_id:raise ValueError('Exact existing message required for manual newsletter qualification')
                from urllib.parse import quote
                actions['Read_existing_message']={'type':'OpenApiConnection','runAfter':{},'inputs':{'host':{'apiId':MAIL,'connectionName':'shared_office365','operationId':'HttpRequest'},'parameters':{'Uri':'https://graph.microsoft.com/v1.0/me/messages/'+quote(message_id,safe='')+'?$select=id,internetMessageId,subject,receivedDateTime,webLink,body,from','Method':'GET'},'retryPolicy':{'type':'none'}}}
                collection="@createArray(body('Read_existing_message'))";after={'Read_existing_message':['Succeeded']}
            source_id="@if(empty(item()?['internetMessageId']),coalesce(item()?['id'],''),item()?['internetMessageId'])";title="@coalesce(item()?['subject'],'Untitled newsletter')";link="@if(empty(item()?['webLink']),"+quoted(config["fallbackUrl"])+",item()?['webLink'])";date=None
        else:
            source_site=binding.get('sourceSite','');su=urlsplit(source_site)
            if su.scheme!='https' or su.hostname!=u.hostname or su.query or su.fragment or su.username:
                raise ValueError('Exact same-tenant source site required')
            source_list=binding.get('sourceListId','')
            if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}',source_list):
                raise ValueError('Exact source list required')
            selector=binding.get('sourceTitle')
            if not isinstance(selector,str) or not selector.strip():raise ValueError('Bounded source title selector required')
            from urllib.parse import quote
            source_uri="_api/web/lists(guid'"+source_list+"')/items?$select=Id,GUID,Title,Modified,OData__UIVersionString&$filter="+quote("Title eq '"+selector.replace("'","''")+"'",safe='')+"&$top=5000"
            actions['Read_source']=http('GET',source_uri)
            actions['Read_source']['inputs']['parameters']['dataset']=source_site
            actions['Require_complete_source']={'type':'ParseJson','runAfter':{'Read_source':['Succeeded']},'inputs':{'content':{'complete':"@and(empty(body('Read_source')?['odata.nextLink']),empty(body('Read_source')?['@odata.nextLink']))"},'schema':{'type':'object','required':['complete'],'properties':{'complete':{'type':'boolean','enum':[True]}}}}}
            collection="@body('Read_source')?['value']";after={'Require_complete_source':['Succeeded']}
            source_id="@coalesce(item()?['GUID'],'')";title="@item()?['Title']";date=None
            link="@concat("+quoted(config['fallbackUrl'])+",'?ID=',string(item()?['Id']))"
        base="_api/web/lists(guid'"+list_id+"')/items"
        observation={'sourceId':source_id,'title':title,'link':link,'publishedAt':date}
        if channel=='rss':observation['sourceObservation']="@item()"
        if channel=='sharepoint':
            observation.update(sourceKey=config['key'],sourceModifiedAt="@item()?['Modified']",sourceVersion="@item()?['OData__UIVersionString']")
        if channel=='newsletter':
            observation['publisherLinks']="@body('Publisher_links')"
            observation['receivedAt']="@item()?['receivedDateTime']"
            observation['sourceKey']=config['key']
        work={'Observation':{'type':'Compose','runAfter':{},'inputs':observation},'Source_id':{'type':'Compose','runAfter':{'Observation':['Succeeded']},'inputs':source_id}}
        if channel=='newsletter':
            work['Email_link_fragments']={'type':'Query','runAfter':{},'inputs':{'from':"@skip(split(replace(string(coalesce(item()?['body']?['content'],item()?['body'],'')),decodeUriComponent('%27'),'\"'),'href=\"'),1)",'where':"@or("+','.join("startsWith(toLower(item()),"+quoted('https://'+d+'/')+")" for d in config['linkDomains'])+",false)"}}
            body_field="item()?['body']?['content']" if manual else "item()?['body']"
            work['Email_link_fragments']['inputs']['from']=work['Email_link_fragments']['inputs']['from'].replace("item()?['body']?['content'],item()?['body']",body_field)
            work['Publisher_links']={'type':'Select','runAfter':{'Email_link_fragments':['Succeeded']},'inputs':{'from':"@body('Email_link_fragments')",'select':{'url':"@replace(first(split(item(),'\"')),'&amp;','&')"}}}
            work['Observation']['runAfter']={'Publisher_links':['Succeeded']}
        uri="@concat('"+base.replace("'", "''")+"?$select=Id,Fingerprint&$filter=ChannelKey%20eq%20%27"+channel_key+"%27%20and%20SourceKey%20eq%20%27',uriComponent(replace(outputs('Source_id'),'''','''''')),'%27&$top=5000')"
        read=http('GET',uri)
        fingerprint="@string(outputs('Observation'))"
        write=http('POST',base,{'Title':"@take(string(outputs('Observation')?['title']),255)",'ChannelKey':channel_key,'SourceKey':"@outputs('Source_id')",'Fingerprint':fingerprint,'ObservedAt':'@utcNow()','SourceLink':"@outputs('Observation')?['link']",'ProcessingState':'Proposed','ObservationJSON':fingerprint})
        lead_payload=write['inputs']['parameters']['parameters/body']
        write['inputs']['parameters']['parameters/body']="@string(outputs('Lead_payload'))"
        write['runAfter']={'Lead_payload':['Succeeded']}
        ready={'Read_existing':read,'Match_existing':{'type':'Query','runAfter':{'Read_existing':['Succeeded']},'inputs':{'from':"@body('Read_existing')?['value']",'where':"@equals(item()?['Fingerprint'],string(outputs('Observation')))"}},'Require_complete_query':{'type':'ParseJson','runAfter':{'Match_existing':['Succeeded']},'inputs':{'content':{'complete':"@and(empty(body('Read_existing')?['odata.nextLink']),empty(body('Read_existing')?['@odata.nextLink']))"},'schema':{'type':'object','required':['complete'],'properties':{'complete':{'type':'boolean','enum':[True]}}}}},'Create_if_changed':{'type':'If','runAfter':{'Require_complete_query':['Succeeded']},'expression':"@empty(body('Match_existing'))",'actions':{'Lead_payload':{'type':'Compose','runAfter':{},'inputs':lead_payload},'Persist_lead':write},'else':{'actions':{}}}}
        work['Require_identity']={'type':'ParseJson','runAfter':{'Source_id':['Succeeded']},'inputs':{'content':{'id':"@outputs('Source_id')"},'schema':{'type':'object','required':['id'],'properties':{'id':{'type':'string','minLength':1,'maxLength':255}}}}}
        ready['Read_existing']['runAfter']={'Require_identity':['Succeeded']}
        work.update(ready)
        if channel=='newsletter':
            # Sender qualification occurs in the connector trigger; subject qualification
            # excludes replies/forwards and unrelated messages from the same publisher.
            subject=binding.get('subjectContains')
            if not isinstance(subject,str) or not subject.strip():
                if source is not None and not pending_sender:raise ValueError('Verified newsletter subject selector required')
                subject=''
            actions['Original_issues']={'type':'Query','runAfter':after,'inputs':{'from':collection,'where':"@and(contains(toLower(coalesce(item()?['subject'],'')),"+quoted(subject.lower())+"),not(or(startsWith(toLower(trim(coalesce(item()?['subject'],''))),'re:'),startsWith(toLower(trim(coalesce(item()?['subject'],''))),'fw:'),startsWith(toLower(trim(coalesce(item()?['subject'],''))),'fwd:'))))"}}
            if manual:
                original=actions['Original_issues']['inputs']['where'][1:]
                sender_conditions=','.join("equals(toLower(coalesce(item()?['from']?['emailAddress']?['address'],'')),"+quoted(s.lower())+")" for s in binding['senders'])
                actions['Original_issues']['inputs']['where']='@and('+original+',or('+sender_conditions+',false))'
            collection="@body('Original_issues')";after={'Original_issues':['Succeeded']}
        actions['Collect']={'type':'Foreach','foreach':collection,'runAfter':after,'runtimeConfiguration':{'concurrency':{'repetitions':1}},'actions':work}
        collection_actions=actions
        failure=http('POST',base,{'Title':'Source collection failed','ChannelKey':channel_key,'SourceKey':"@workflow()?['run']?['name']",'Fingerprint':"@workflow()?['run']?['name']",'ObservedAt':'@utcNow()','SourceLink':config['fallbackUrl'],'ProcessingState':'Failed','ObservationJSON':json.dumps({'kind':'source-update-failure','reason':'Inspect the owned flow run; no protected body is copied into this record.'})},after={'Collect_source':['Failed','TimedOut']})
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
    return {'properties':{'displayName':('PPG | Source updates | '+config['publisher']+' | '+config['name']+' | '+{'rss':'RSS','newsletter':'Newsletter','sharepoint':'SharePoint'}[channel]) if config else 'PPG | Source updates | METEOR | Indicators | API','state':'Stopped','flowFailureAlertSubscribed':False,'connectionReferences':refs,'definition':{'$schema':'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#','contentVersion':'1.1.0.0','parameters':{'$authentication':{'type':'SecureObject','defaultValue':{}},'$connections':{'type':'Object','defaultValue':{}}},'triggers':{'manual' if manual else 'Newsletter_arrival' if channel=='newsletter' else 'Scheduled_collection':trigger},'actions':actions,'outputs':{}}}}


def deployment_manifest(flow, *, source_commit, source=None):
    """Private binding manifest; this is preparation, never deployment evidence."""
    import hashlib
    if not re.fullmatch(r'[a-f0-9]{40}',source_commit):raise ValueError('Exact source commit required')
    digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'schemaVersion':1,'configVersion':CONFIG_VERSION,'sourceCommit':source_commit,
            'sourceKey':source['key'] if source else None,
            'definitionSHA256':digest(flow['properties']['definition']),
            'connectionReferencesSHA256':digest(flow['properties']['connectionReferences']),
            'sourceConfigurationSHA256':digest(source),'nativeReadbackVerified':False,
            'runtimeVerified':False,'requestedState':'Stopped'}


def main():
    import argparse,os
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--channel',choices=['rss','newsletter','sharepoint','meteor'],required=True)
    p.add_argument('--binding',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    group=p.add_mutually_exclusive_group()
    group.add_argument('--source',type=Path,help='One reusable source configuration JSON')
    group.add_argument('--source-key',help='Key in the reusable source profile catalogue')
    p.add_argument('--catalogue',type=Path,default=Path(__file__).resolve().parents[1]/'config/source-update-channels.json')
    p.add_argument('--manifest',type=Path,help='Private preparation manifest (requires --source-commit)')
    p.add_argument('--source-commit')
    p.add_argument('--manual',action='store_true')
    p.add_argument('--prepare-newsletter',action='store_true')
    a=p.parse_args()
    source=json.loads(a.source.read_text()) if a.source else None
    if a.source_key:
        matches=[r for r in json.loads(a.catalogue.read_text()).get(a.channel,[]) if r['key']==a.source_key]
        if len(matches)!=1:p.error('Source key must identify exactly one profile for the channel')
        source=matches[0]
    result=build(a.channel,json.loads(a.binding.read_text()),manual=a.manual,pending_sender=a.prepare_newsletter,source=source)
    manifest=deployment_manifest(result,source_commit=a.source_commit or '',source=source) if a.manifest else None
    if a.output.exists() or (a.manifest and a.manifest.exists()):p.error('Output already exists; preserve prior preparation')
    for target,value in [(a.output,result)]+([(a.manifest,manifest)] if a.manifest else []):
        with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w')as f:
            f.write(json.dumps(value,indent=2)+'\n')

if __name__=='__main__':main()
