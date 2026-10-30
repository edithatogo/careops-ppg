"""Add serial, conditional, batched current-row refresh to captured API datasets."""
from copy import deepcopy
import json
import re

SP='/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
def q(value): return "'"+value.replace("'","''")+"'"
def expr(value): return '@'+value

def extend(flow, binding, contracts):
    out=deepcopy(flow);d=out['properties']['definition'];original=d['actions']['Collect_datasets']['actions'];groups={};initial=[];previous=None
    site=binding['site']
    for contract in contracts:
        key=contract['key'];n=key.replace('-','_');list_id=binding['rowLists'][key]
        if not re.fullmatch('[a-f0-9-]{36}',list_id): raise ValueError('Exact row list required')
        base="_api/web/lists(guid'"+list_id+"')/items";a={k:deepcopy(v) for k,v in original.items() if k.startswith(n+'_')};a[n+'_path']['runAfter']={}
        prefix=n+'_sync_';name=lambda x:prefix+x
        def add(label,typ,inputs,after,**extra):
            a[name(label)]={'type':typ,'runAfter':{name(after):['Succeeded']} if after else {n+'_persist':['Succeeded']},'inputs':inputs,**extra}
        def http(method,uri,body=None,headers=None):
            p={'dataset':site,'parameters/method':method,'parameters/uri':uri,'parameters/headers':{'Accept':'application/json;odata=nometadata',**(headers or {})}}
            if body is not None:p['parameters/body']=body
            return {'type':'OpenApiConnection','inputs':{'host':{'apiId':SP,'connectionName':'shared_sharepointonline','operationId':'HttpRequest'},'parameters':p,'retryPolicy':{'type':'none'}},'runAfter':{}}
        a[name('validate_source')] = {'type':'ParseJson','runAfter':{n+'_persist':['Succeeded']},'inputs':{'content':expr("outputs("+q(n+'_json')+")?['result']?['records']"),'schema':{'type':'array','items':{'type':'object','required':[f['source'] for f in contract['fields']],'properties':{'FacilityCode':{'type':'string','minLength':1}}}}}}
        invalid='or('+','.join("or(empty(string(item()?["+q(f)+"])),contains(string(item()?["+q(f)+"]),':'))" for f in contract['keyFields'])+')'
        if len(contract['keyFields'])==1:invalid=invalid[3:-1]
        a[name('invalid_keys')]={'type':'Query','runAfter':{name('validate_source'):['Succeeded']},'inputs':{'from':expr("outputs("+q(n+'_json')+")?['result']?['records']"),'where':expr(invalid)}}
        a[name('valid_keys')]={'type':'ParseJson','runAfter':{name('invalid_keys'):['Succeeded']},'inputs':{'content':{'valid':expr("empty(body("+q(name('invalid_keys'))+"))")},'schema':{'type':'object','required':['valid'],'properties':{'valid':{'enum':[True]}}}}}
        rows_var=name('rows');next_var=name('next')
        initial.extend([{'name':rows_var,'type':'array','value':[]},{'name':next_var,'type':'string','value':base+'?$top=2000&$orderby=ID asc'}])
        read=http('GET',expr("variables("+q(next_var)+")"));read['inputs']['parameters']['parameters/headers']['Accept']='application/json;odata=minimalmetadata'
        merge={'type':'Compose','runAfter':{name('page'):['Succeeded']},'inputs':expr("union(variables("+q(rows_var)+"),body("+q(name('page'))+")?['value'])")}
        a[name('pages')]={'type':'Until','runAfter':{name('valid_keys'):['Succeeded']},'expression':expr("empty(variables("+q(next_var)+"))"),'limit':{'count':100,'timeout':'PT10M'},'actions':{name('page'):read,name('merge'):merge,name('keep'):{'type':'SetVariable','runAfter':{name('merge'):['Succeeded']},'inputs':{'name':rows_var,'value':expr("outputs("+q(name('merge'))+")")}},name('advance'):{'type':'SetVariable','runAfter':{name('keep'):['Succeeded']},'inputs':{'name':next_var,'value':expr("replace(coalesce(body("+q(name('page'))+")?['odata.nextLink'],body("+q(name('page'))+")?['@odata.nextLink'],''),"+q(site+'/')+",'')")}}}}
        add('complete_read','ParseJson',{'content':{'complete':expr("empty(variables("+q(next_var)+"))")},'schema':{'type':'object','properties':{'complete':{'enum':[True]}},'required':['complete']}},'pages')
        add('unknown_rows','Query',{'from':expr("variables("+q(rows_var)+")"),'where':expr("or(not(startsWith(coalesce(item()?['SourceKey'],''),"+q(key+':')+")),equals(item()?['SourceKey'],"+q(key+':')+"),empty(string(item()?['ID'])))")},'complete_read')
        add('known_rows','ParseJson',{'content':{'valid':expr("empty(body("+q(name('unknown_rows'))+"))")},'schema':{'type':'object','required':['valid'],'properties':{'valid':{'enum':[True]}}}},'unknown_rows')
        add('index_parts','Select',{'from':expr("variables("+q(rows_var)+")"),'select':expr("concat('\"',item()?['SourceKey'],'\":',string(item()))")},'known_rows')
        add('index','Compose',expr("json(concat('{',join(body("+q(name('index_parts'))+"),','),'}'))"),'index_parts')
        keyexpr="concat("+q(key+':')+","+",':',".join("string(item()?["+q(f)+"])" for f in contract['keyFields'])+")"
        payload={f['name']:expr("item()?["+q(f['source'])+"]") for f in contract['fields']}
        payload.update({'SourceKey':expr(keyexpr),'SourcePresent':True,'Title':expr("coalesce(item()?['FacilityName'],"+keyexpr+")"),'CapturePath':expr("outputs("+q(n+'_path')+")"),'SourceLink':expr("outputs("+q(n+'_payload')+")?['SourceLink']"),'ObservedAt':expr("outputs("+q(n+'_payload')+")?['ObservedAt']"),'Attribution':binding['attribution']})
        add('desired','Select',{'from':expr("outputs("+q(n+'_json')+")?['result']?['records']"),'select':payload},'index')
        add('keys','Select',{'from':expr("body("+q(name('desired'))+")"),'select':"@item()?['SourceKey']"},'desired')
        add('unique','ParseJson',{'content':{'valid':expr("equals(length(body("+q(name('keys'))+")),length(union(body("+q(name('keys'))+"),body("+q(name('keys'))+"))))")},'schema':{'type':'object','properties':{'valid':{'enum':[True]}},'required':['valid']}},'keys')
        old="outputs("+q(name('index'))+")?[item()?['SourceKey']]"
        equal='and('+','.join("equals("+old+"?["+q(f)+"],item()?["+q(f)+"])" for f in [x['name'] for x in contract['fields']]+['SourcePresent'])+')'
        add('changes','Query',{'from':expr("body("+q(name('desired'))+")"),'where':expr('not('+equal+')')},'unique')
        add('absent','Query',{'from':expr("variables("+q(rows_var)+")"),'where':expr("and(not(contains(body("+q(name('keys'))+"),item()?['SourceKey'])),not(equals(item()?['SourcePresent'],false)))")},'changes')
        add('removals','Select',{'from':expr("body("+q(name('absent'))+")"),'select':{'SourceKey':"@item()?['SourceKey']",'SourcePresent':False}},'absent')
        add('writes','Compose',expr("union(body("+q(name('changes'))+"),body("+q(name('removals'))+"))"),'removals')
        cr="decodeUriComponent('%0D%0A')";boundary='batch_'+n;change='change_'+n
        parts=[q('--'+boundary),cr,q('Content-Type: multipart/mixed; boundary='+change),cr,cr,q('--'+change),cr,q('Content-Type: application/http'),cr,q('Content-Transfer-Encoding: binary'),cr,cr,"if(equals("+old+",null),'POST ','MERGE ')",q(site+'/'+base),"if(equals("+old+",null),'',concat('(',string("+old+"?['ID']),')'))",q(' HTTP/1.1'),cr,q('Content-Type: application/json;odata=nometadata'),cr,"if(equals("+old+",null),'',concat('IF-MATCH: ',"+old+"?['odata.etag'],"+cr+"))",cr,'string(item())',cr,q('--'+change+'--'),cr]
        operation='concat('+','.join(parts)+')'
        add('requests','Select',{'from':expr("outputs("+q(name('writes'))+")"),'select':expr(operation)},'writes')
        loop=name('batches');chunk=name('chunk');send=name('send');validate=name('validate_batch')
        bodyexpr="concat(join(outputs("+q(chunk)+"),''),'--"+boundary+"--',"+cr+")"
        request=http('POST','_api/$batch',expr(bodyexpr),{'Content-Type':'multipart/mixed; boundary='+boundary});request['runAfter']={chunk:['Succeeded']}
        # The outer HTTP status alone does not prove the child writes succeeded.
        result="base64ToString(body("+q(send)+")?['$content'])"
        good="equals(add(sub(length(split("+result+",'HTTP/1.1 201')),1),sub(length(split("+result+",'HTTP/1.1 204')),1)),length(outputs("+q(chunk)+")))"
        a[loop]={'type':'Foreach','runAfter':{name('requests'):['Succeeded']},'foreach':expr("range(0,div(add(length(body("+q(name('requests'))+")),19),20))"),'runtimeConfiguration':{'concurrency':{'repetitions':1}},'actions':{chunk:{'type':'Compose','runAfter':{},'inputs':expr("take(skip(body("+q(name('requests'))+"),mul(items("+q(loop)+"),20)),20)")},send:request,validate:{'type':'ParseJson','runAfter':{send:['Succeeded']},'inputs':{'content':{'complete':expr(good)},'schema':{'type':'object','properties':{'complete':{'enum':[True]}},'required':['complete']}}}}}
        # Re-read persisted rows before the durable synchronisation checkpoint.
        add('reset_rows','SetVariable',{'name':rows_var,'value':[]},'batches')
        add('reset_next','SetVariable',{'name':next_var,'value':base+'?$top=2000&$orderby=ID asc'},'reset_rows')
        reread=json.dumps(a[name('pages')])
        for label in ('page','merge','keep','advance'):
            reread=reread.replace(name(label),name('readback_'+label))
        a[name('readback_pages')]=json.loads(reread)
        a[name('readback_pages')]['runAfter']={name('reset_next'):['Succeeded']}
        add('readback_parts','Select',{'from':expr("variables("+q(rows_var)+")"),'select':expr("concat('\"',item()?['SourceKey'],'\":',string(item()))")},'readback_pages')
        add('readback_index','Compose',expr("json(concat('{',join(body("+q(name('readback_parts'))+"),','),'}'))"),'readback_parts')
        persisted="outputs("+q(name('readback_index'))+")?[item()?['SourceKey']]"
        # Unchanged rows retain old provenance; compare provenance only on writes.
        mismatch='not('+equal.replace(old,persisted)+')'
        add('readback_mismatch','Query',{'from':expr("body("+q(name('desired'))+")"),'where':expr(mismatch)},'readback_index')
        changed_equal='and('+','.join("equals("+persisted+"?["+q(f)+"],item()?["+q(f)+"])" for f in ('Title','CapturePath','SourceLink','Attribution'))+",equals(formatDateTime("+persisted+"?['ObservedAt'],'yyyy-MM-ddTHH:mm:ss'),formatDateTime(item()?['ObservedAt'],'yyyy-MM-ddTHH:mm:ss')))"
        add('readback_provenance','Query',{'from':expr("body("+q(name('changes'))+")"),'where':expr('not('+changed_equal+')')},'readback_mismatch')
        add('readback_absent','Query',{'from':expr("body("+q(name('removals'))+")"),'where':expr("not(equals("+persisted+"?['SourcePresent'],false))")},'readback_provenance')
        valid='and(empty(variables('+q(next_var)+')),'+','.join('empty(body('+q(name(label))+'))' for label in ('readback_mismatch','readback_provenance','readback_absent'))+')'
        add('verified','ParseJson',{'content':{'valid':expr(valid)},'schema':{'type':'object','required':['valid'],'properties':{'valid':{'enum':[True]}}}},'readback_absent')
        done=http('POST',expr("concat("+q("_api/web/lists(guid'"+binding['listId']+"')/items(")+",string(body("+q(n+'_persist')+")?['Id']),')')"),'{"ProcessingState":"Synchronised"}',{'Content-Type':'application/json;odata=nometadata','X-HTTP-Method':'MERGE','IF-MATCH':'*'});done['runAfter']={name('verified'):['Succeeded']};a[name('done')]=done
        group=n+'_dataset';groups[group]={'type':'Scope','runAfter':{previous:['Succeeded','Failed','TimedOut','Skipped']} if previous else {},'actions':a};previous=group
    d['actions']['Initialise_row_reads']={'type':'InitializeVariable','runAfter':{},'inputs':{'variables':initial}}
    d['actions']['Collect_datasets']['actions']=groups;d['actions']['Collect_datasets']['runAfter']={'Initialise_row_reads':['Succeeded']};d['contentVersion']='1.3.0.0'
    return out
