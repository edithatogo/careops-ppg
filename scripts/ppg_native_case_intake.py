"""Optional read-only catalogue-case intake in the existing package flow."""
import copy
from uuid import UUID

PIN_FIELDS=('UniqueId','ETag','Length','UIVersionLabel','ServerRelativeUrl')
CASE_FIELDS=('Id','CaseUID','Title','linkedDocumentUIDs','sourceBaselineRef','evidenceDraftLink',
             'odata.etag','OData__UIVersionString','caseStatus','proposedOutcome','accountableRole','nextAction')
ROW_FIELDS=('Id','DocumentUID','sourceDocumentId','sourceSnapshotRef','rawSourceRecordRef','odata.etag')


def extend_case_intake(a,b,http,content,compose,check,sp_path,lit):
    cfg=b['caseIntake'];pin=cfg['enginePin'];UUID(pin['UniqueId'])
    case_list=str(UUID(cfg['reviewQueueListId']));catalogue=str(UUID(cfg['catalogueListId']))
    chosen="equals(body('Read_request_config')?['kind'],'PPG-native-case-intake-request-v1')"
    def dep(name):return {name:['Succeeded']} if name else {}
    def project(name,keys):return {k:"@body('"+name+"')?['"+k+"']" for k in keys}
    case_uri="@concat('_api/web/lists(guid''"+case_list+"'')/items(',string(int(body('Read_request_config')?['caseItemId'])),')')"
    rows_uri="_api/web/lists(guid'"+catalogue+"')/items?$select="+','.join(k for k in ROW_FIELDS if k!='odata.etag')+"&$orderby=Id&$top=5000"
    def branch(suffix,initial=False):
        g={};c='Intake_case'+suffix;r='Intake_catalogue'+suffix;f='Intake_rows'+suffix;n='Intake_normal_rows'+suffix
        g[c]=http('GET',case_uri)
        g[r]=http('GET',rows_uri,c)
        g[f]={'type':'Query','runAfter':dep(r),'inputs':{'from':"@body('"+r+"')?['value']",'where':"@contains(json(body('"+c+"')?['linkedDocumentUIDs']),item()?['DocumentUID'])"}}
        g[n]={'type':'Select','runAfter':dep(f),'inputs':{'from':"@body('"+f+"')",'select':{k:"@item()?['"+k+"']" for k in ROW_FIELDS}}}
        guard='Intake_bound'+suffix
        expr="and(equals(body('"+c+"')?['CaseUID'],body('Read_request_config')?['expectedCaseUID']),empty(coalesce(body('"+r+"')?['odata.nextLink'],body('"+r+"')?['@odata.nextLink'],body('"+r+"')?['nextLink'])),startsWith(body('"+c+"')?['sourceBaselineRef'],"+lit(b['site']+'/')+"),startsWith(body('"+c+"')?['evidenceDraftLink'],"+lit(b['site']+'/')+"))"
        g[guard]=check(expr,n,'INTAKE_SCOPE'+suffix,'Select an exact supported case/source scope; catalogue continuation is not accepted.')
        prev=guard
        if cfg.get('events'):
            events={};ep=None
            for kind in ('assurance','consultation','readiness'):
                event_list=str(UUID(cfg['events'][kind]));name='Intake_events_'+kind+suffix
                uid="replace(body('"+c+"')?['CaseUID'],'''','''''')"
                uri="@concat('_api/web/lists(guid''"+event_list+"'')/items?$filter=CaseUID eq ''',"+uid+",'''&$top=5000')"
                events[name]=http('GET',uri,ep);ep=name
            name='Intake_own_events'+suffix
            g[name]={'type':'If','runAfter':dep(prev),'expression':{'equals':["@body('Read_request_config')?['selectionMode']",'fictional-initiated-source']},'actions':events,'else':{'actions':{}}};prev=name
        for role,key in [('baseline','sourceBaselineRef'),('draft','evidenceDraftLink')]:
            name='Intake_'+role+'_pin'+suffix
            # URL is constrained to this exact site before the read. Escape its
            # decoded apostrophes as OData string literals, never as expressions.
            if initial:
                path="replace(decodeUriComponent(uriPath(body('"+c+"')?['"+key+"'])),'"+"'"*3+",'"+"'"*5+")"
                uri="@concat('_api/web/GetFileByServerRelativePath(decodedurl=''',"+path+",''')?$select="+','.join(PIN_FIELDS)+"')"
            else:
                uri="@concat('_api/web/GetFileById(''',body('Intake_"+role+"_pin')?['UniqueId'],''')?$select="+','.join(PIN_FIELDS)+"')"
            g[name]=http('GET',uri,prev);prev=name
        size='Intake_sizes'+suffix
        g[size]=check("and(lessOrEquals(int(body('Intake_baseline_pin"+suffix+"')?['Length']),3000000),lessOrEquals(int(body('Intake_draft_pin"+suffix+"')?['Length']),3000000))",prev,'INTAKE_SIZE'+suffix,'Selected sources exceed the bounded route.');prev=size
        state={'case':project(c,CASE_FIELDS),'catalogue':"@body('"+n+"')",'baselinePin':project('Intake_baseline_pin'+suffix,PIN_FIELDS),'draftPin':project('Intake_draft_pin'+suffix,PIN_FIELDS)}
        if cfg.get('events'):
            state['eventSets']={kind:"@body('Intake_events_"+kind+suffix+"')"for kind in ('assurance','consultation','readiness')}
        g['Intake_state'+suffix]=compose(state,prev);prev='Intake_state'+suffix
        if initial:
            for role in ('baseline','draft'):
                name='Intake_read_'+role
                g[name]=content(sp_path("body('Intake_"+role+"_pin')?['ServerRelativeUrl']"),prev);prev=name
        else:
            g['Intake_unchanged'+suffix]=check("equals(string(outputs('Intake_state')),string(outputs('Intake_state"+suffix+"')))",prev,'INTAKE_CHANGED'+suffix,'Case, catalogue or selected file changed; use a new revision.')
        return g
    first='Read_case_intake'
    a[first]={'type':'If','runAfter':dep('Read_full_input'),'expression':{'equals':['@'+chosen,True]},'actions':branch('',True),'else':{'actions':{}}}
    a['Pin_sets']['runAfter']=dep(first)
    for suffix in ('','_before_write','_before_receipt'):
        # Old paths and their pin arrays remain byte-identical unless this new
        # explicit request kind is selected.
        if suffix:
            prev=next(iter(a['Pin_sets'+suffix]['runAfter']))
            name='Recheck_case_intake'+suffix
            a[name]={'type':'If','runAfter':dep(prev),'expression':{'equals':['@'+chosen,True]},'actions':branch(suffix),'else':{'actions':{}}}
            a['Pin_sets'+suffix]['runAfter']=dep(name)
        name='Input_pins'+suffix;old=a[name]['inputs'];sets='Intake_pin_sets'+suffix
        extras=[{'role':'selected-'+role,**project('Intake_'+role+'_pin'+suffix,PIN_FIELDS)}for role in ('baseline','draft')]
        # Select the old array first so default/full fingerprints do not change.
        a[sets]=compose({'original':old,'extra':extras},next(iter(a[name]['runAfter'])))
        a[name]['runAfter']=dep(sets)
        a[name]['inputs']='@if('+chosen+",union(outputs('"+sets+"')?['original'],outputs('"+sets+"')?['extra']),outputs('"+sets+"')?['original'])"
        uri=a['Read_engine_pin'+suffix]['inputs']['parameters']['parameters/uri']
        a['Read_engine_pin'+suffix]['inputs']['parameters']['parameters/uri']='@if('+chosen+','+lit("_api/web/GetFileById('"+pin['UniqueId']+"')?$select="+','.join(PIN_FIELDS))+','+uri[1:]+')'
    expr=a['Require_qualified_engine']['expression']['and'][0]['equals'][0]
    match='and('+','.join("equals(body('Read_engine_pin')?['"+k+"'],"+lit(pin[k])+")"for k in PIN_FIELDS)+')'
    a['Require_qualified_engine']['expression']['and'][0]['equals'][0]='@if('+chosen+','+match+','+expr[1:]+')'
    req=a['Native_request']['inputs'];req['kind']='@if('+chosen+",'m365-case-intake-request-v1',"+req['kind'][1:]+')'
    req['intake']={'site':b['site'],'mode':"@body('Read_request_config')?['selectionMode']",'expectedCaseUID':"@body('Read_request_config')?['expectedCaseUID']",'case':"@outputs('Intake_state')?['case']",'catalogue':"@outputs('Intake_state')?['catalogue']",'baselinePin':"@outputs('Intake_state')?['baselinePin']",'draftPin':"@outputs('Intake_state')?['draftPin']",'historicalSelection':"@body('Read_full_input')",'eventSets':"@outputs('Intake_state')?['eventSets']"}
    # New script gets a static connector ID. Existing scripts remain untouched.
    old=copy.deepcopy(a['Select_document_script']['actions']['Run_full_review_script'])
    new=copy.deepcopy(old);new['inputs']['parameters']['scriptId']=cfg['scriptGraphId']
    native_members="@string(createArray(setProperty(setProperty(json('{}'),'path','existing-pack.zip'),'base64',body('Intake_read_baseline')?['$content']),setProperty(setProperty(json('{}'),'path','maintained-template.docx'),'base64',body('Read_template')?['$content']),setProperty(setProperty(json('{}'),'path','evidence/selected-draft.docx'),'base64',body('Intake_read_draft')?['$content'])))"
    new['inputs']['parameters']['ScriptParameters/membersJson']=native_members
    # Keep the old action name for the full branch's result lookup.
    a['Select_document_script']['actions']={'Select_intake_script':{'type':'If','runAfter':{},'expression':{'equals':['@'+chosen,True]},'actions':{'Run_case_intake_script':new},'else':{'actions':{'Run_full_review_existing':old}}},'Run_full_review_script':compose('@if('+chosen+",outputs('Run_case_intake_script'),outputs('Run_full_review_existing'))",'Select_intake_script')}
