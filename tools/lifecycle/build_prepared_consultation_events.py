"""Local selected-case consultation recording against a verified prepared revision.

This composes within the existing event flow. It grants no readiness, approval,
publication or actor authority. Native qualification and ordinary-user UI proof
remain separate requirements; this module performs no network operations.
"""
import copy
from build_selected_event_routes import audit_actions


def _stable_history_rows(rows):
    """Keep complete native row identity except its per-response odata.id."""
    return 'if(equals(length('+rows+"),1),createArray(union(first("+rows+"),json('{\"odata.id\":null}'))),"+rows+')'


def build(kind, prepared_event_flow, event_list_uri, technical_role):
    if kind not in ('request', 'response'):
        raise ValueError('Choose request or response')
    if not isinstance(technical_role,str) or not technical_role.startswith('FICTIONAL ') or len(technical_role)>255:
        raise ValueError('Explicit existing fictional technical role required')
    out=copy.deepcopy(prepared_event_flow);props=out['properties'];props['state']='Stopped'
    d=props['definition'];a=d['actions']
    if 'Route_consultation_prepared_context' not in a:
        raise ValueError('Embed the reviewed prepared reader first')
    template=copy.deepcopy(a['Resolve_context']['actions']['Read_selected_case'])
    creators=[]
    def walk(x):
        if isinstance(x,dict):
            q=x.get('inputs',{}).get('parameters',{}) if isinstance(x.get('inputs'),dict) else {}
            if q.get('parameters/method')=='POST':
                creators.append(q.get('parameters/uri'));x['inputs']['retryPolicy']={'type':'none'}
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    walk(a)
    if creators != [event_list_uri] or not event_list_uri.endswith('/items'):
        raise ValueError('Retain the one existing ownership creator and its qualified event list')
    c="outputs('Selected_case_context')";r="outputs('Native_prepared_revision')";p=r+"?['preparedRevision']";scope=p+"?['scope']"
    def quote(x):return "'"+x.replace("'","''")+"'"
    def comp(value,prev=None):return {'type':'Compose','inputs':value,'runAfter':{prev:['Succeeded']} if prev else {}}
    def http(uri,prev=None,body=None):
        x=copy.deepcopy(template);x['runAfter']={prev:['Succeeded']} if prev else {};q=x['inputs']['parameters']
        q['parameters/uri']=uri;q['parameters/method']='POST' if body is not None else 'GET'
        q['parameters/headers']={'Accept':'application/json;odata=nometadata','Content-Type':'application/json;odata=nometadata'}
        q.pop('parameters/body',None)
        if body is not None:
            q['parameters/body']=body;x['inputs']['retryPolicy']={'type':'none'}
        return x
    def guard(checks,prev,yes,held_name,reason):
        return {'type':'If','expression':'@and('+','.join(checks)+')','runAfter':{prev:['Succeeded']} if prev else {},'actions':yes,'else':{'actions':{held_name:comp({'qualified':False,'consultationRecorded':False,'eventWriteCount':0,'progressionGranted':False,'reason':reason})}}}
    def eq(x,y):return 'equals('+x+','+y+')'
    def complete(name):return ["empty(body('"+name+"')?['odata.nextLink'])","empty(body('"+name+"')?['@odata.nextLink'])"]
    def query(field,value):return '@concat('+quote(event_list_uri+'?$filter='+field+' eq ')+",decodeUriComponent('%27'),"+value+",decodeUriComponent('%27'))"
    def stable_history(name):
        # SharePoint returns a fresh response-only odata.id UUID per read. Keep
        # actual Id/GUID/odata.etag and every payload field. Histories with zero
        # or multiple rows remain unchanged and retain the separate shape guards.
        rows="body('"+name+"')?['value']"
        return _stable_history_rows(rows)

    request_uid="concat('LC-CONSULT-REQ-',toLower("+p+"?['file']?['UniqueId']),'-v',"+p+"?['file']?['nativeVersion'])"
    role=quote(technical_role)
    base={'CaseUID':'@'+scope+"?['CaseUID']",'DocumentReference':'@'+scope+"?['DocumentReference']",'ReviewedVersionRef':'@'+scope+"?['ReviewedVersionRef']",'DocumentSHA256':'@'+scope+"?['DocumentSHA256']",'SubjectRole':technical_role,'EventKind':'Consultation','FictionalTest':True,'ActorName':'FICTIONAL technical operator; real reviewer authority unqualified','OccurredOn':'@utcNow()'}
    payload={**base,'Title':'FICTIONAL prepared-revision consultation request','EventUID':'@'+request_uid,'RecordState':'Pending response','ConditionsState':'None recorded','Summary':'FICTIONAL technical consultation on the verified prepared revision; no assignment or notification','ResponseSummary':None,'EvidenceReference':'@'+p+"?['qualificationReceipt']?['DocumentReference']",'NextAction':'Record an explicit response for this prepared revision; no readiness or approval is implied'}
    request_payload=copy.deepcopy(payload)
    field='text' if kind=='request' else 'text_5';mode='Consultation request' if kind=='request' else 'Consultation response'
    work={}
    if kind=='response':
        # Existing response wires remain stable; mode-specific consultation validation
        # precedes even its parent/history reads. Ownership validation is unchanged.
        def text(k):return "string(coalesce(triggerBody()?['"+k+"'],''))"
        checks=["startsWith("+text('text')+",'LC-CONSULT-RESP-')","lessOrEquals(length("+text('text')+"),80)","equals(uriComponent("+text('text')+'),'+text('text')+')',"contains(createArray('Responded','Unanswered','Declined','Conditional'),triggerBody()?['text_1'])"]
        for key in ('text','text_1','text_2','text_3','text_4'):
            checks.extend([eq("triggerBody()?['"+key+"']",text(key)),"not(empty(trim("+text(key)+')))',"lessOrEquals(length("+text(key)+'),'+('2000' if key=='text_4' else '255')+')'])
        work['Consultation_input_valid']=comp('@and('+','.join(checks)+')')
        work['Validate_consultation_response']={'type':'If','expression':"@equals(outputs('Consultation_input_valid'),true)",'runAfter':{'Consultation_input_valid':['Succeeded']},'actions':{},'else':{'actions':{'Refuse_consultation_input':{'type':'Terminate','runAfter':{},'inputs':{'runStatus':'Failed','runError':{'code':'InvalidConsultationInput','message':'Provide a bounded fictional response reference, supported outcome, finding, evidence and next action; no event attempted.'}}}}}}
        work['Read_consultation_request']=http(query('EventUID',request_uid),'Validate_consultation_response')
        work['Read_consultation_history']=http(query('ParentEventUID',request_uid),'Read_consultation_request')
        payload.update(Title="@concat('FICTIONAL consultation ',triggerBody()?['text_1'])",EventUID="@triggerBody()?['text']",ParentEventUID='@'+request_uid,
            RecordState="@if(equals(triggerBody()?['text_1'],'Unanswered'),'Pending response',if(equals(triggerBody()?['text_1'],'Declined'),'Declined','Responded'))",
            ConditionsState="@if(equals(triggerBody()?['text_1'],'Responded'),'None recorded','Open')",Summary="@triggerBody()?['text_2']",ResponseSummary="@triggerBody()?['text_2']",EvidenceReference="@triggerBody()?['text_3']",NextAction="@triggerBody()?['text_4']",ConditionsNotes="@if(greater(length(triggerBody()?['text_4']),255),triggerBody()?['text_2'],triggerBody()?['text_4'])")
    work['Consultation_payload']=comp(payload,'Read_consultation_history' if kind=='response' else None)
    eventquery=query('EventUID',"outputs('Consultation_payload')?['EventUID']")
    work['Find_consultation_event']=http(eventquery,'Consultation_payload')
    # Bracket the create/replay with native metadata reads. The prepared reader has
    # independently qualified receipt content/provenance and initial version pins.
    def file_uri(identifier):return "@concat('_api/web/GetFileById(',decodeUriComponent('%27'),"+identifier+",decodeUriComponent('%27'),')?$select=UniqueId,ETag')"
    reads={'case':template['inputs']['parameters']['parameters/uri'],
        'draft':file_uri(p+"?['file']?['UniqueId']"),'receipt':file_uri(p+"?['qualificationReceipt']?['UniqueId']"),
        'template':file_uri(p+"?['template']?['UniqueId']"),'source':file_uri(c+"?['sourcePins']?['UniqueId']"),'baseline':file_uri(c+"?['baselineUniqueId']")}
    def bracket(container,suffix,previous):
        for label,uri in reads.items():
            name='Consultation_'+label+'_'+suffix;container[name]=http(uri,previous);previous=name
        return previous
    previous=bracket(work,'before','Find_consultation_event')
    if kind=='response':
        parent_item="@concat("+quote(event_list_uri+'(')+",string(int(first(body('Read_consultation_request')?['value'])?['Id'])),')')"
        work['Consultation_parent_before']=http(parent_item,previous)
        work['Consultation_history_before']=http(query('ParentEventUID',request_uid),'Consultation_parent_before')
        previous='Consultation_history_before'

    def stable(suffix):
        result=[eq("outputs('Consultation_case_"+suffix+"')?['headers']?['ETag']",r+"?['currentCaseETag']")]
        for label,pin in [('draft',p+"?['file']"),('receipt',p+"?['qualificationReceipt']"),('template',p+"?['template']"),('source',c+"?['sourcePins']")]:
            result.extend(eq("body('Consultation_"+label+'_'+suffix+"')?['"+key+"']",pin+"?['"+key+"']") for key in ('UniqueId','ETag'))
        result.extend([eq("body('Consultation_baseline_"+suffix+"')?['UniqueId']",c+"?['baselineUniqueId']"),eq("body('Consultation_baseline_"+suffix+"')?['ETag']",c+"?['baselineETag']")])
        return result
    before=stable('before')+complete('Find_consultation_event')+["lessOrEquals(length(body('Find_consultation_event')?['value']),1)"]
    if kind=='response':
        parent="first(body('Read_consultation_request')?['value'])"
        before+=complete('Read_consultation_request')+complete('Read_consultation_history')+["equals(length(body('Read_consultation_request')?['value']),1)",eq(parent+"?['EventUID']",request_uid),eq(parent+"?['EventKind']","'Consultation'"),eq(parent+"?['RecordState']","'Pending response'"),eq(parent+"?['ConditionsState']","'None recorded'"),eq(parent+"?['SubjectRole']",role),eq(parent+"?['FictionalTest']",'true'),"empty("+parent+"?['ParentEventUID'])","empty("+parent+"?['SupersedesEventUID'])"]
        before += [eq(parent+"?['"+key+"']",scope+"?['"+key+"']") for key in ('CaseUID','DocumentReference','ReviewedVersionRef','DocumentSHA256')]
        before += [eq(parent+"?['"+key+"']",value[1:] if isinstance(value,str) and value.startswith('@') else ('null' if value is None else 'true' if value is True else quote(value))) for key,value in request_payload.items() if key!='OccurredOn']
        before += ["lessOrEquals(ticks("+parent+"?['OccurredOn']),ticks(utcNow()))","greaterOrEquals(ticks(outputs('Consultation_payload')?['OccurredOn']),ticks("+parent+"?['OccurredOn']))"]
        before += ["or(equals(length(body('Read_consultation_history')?['value']),0),and(equals(length(body('Read_consultation_history')?['value']),1),equals(first(body('Read_consultation_history')?['value'])?['EventUID'],triggerBody()?['text'])))"]
    if kind=='response':
        before += ["not(empty(outputs('Consultation_parent_before')?['headers']?['ETag']))",
                   "not(equals(outputs('Consultation_parent_before')?['headers']?['ETag'],'*'))"]
        before += [eq("body('Consultation_parent_before')?['"+key+"']",parent+"?['"+key+"']") for key in list(request_payload)+['Id','ParentEventUID','SupersedesEventUID']]
        before += complete('Consultation_history_before')+[eq(stable_history('Consultation_history_before'),stable_history('Read_consultation_history'))]
    apply={'Ensure_consultation_event':{'type':'If','expression':"@equals(length(body('Find_consultation_event')?['value']),0)",'runAfter':{},'actions':{'Create_consultation_event':http(event_list_uri,body="@string(outputs('Consultation_payload'))")},'else':{'actions':{}}}}
    apply['Read_consultation_event']=http(eventquery,'Ensure_consultation_event')
    exact=["equals(length(body('Read_consultation_event')?['value']),1)"]+complete('Read_consultation_event')
    exact += [eq("first(body('Read_consultation_event')?['value'])?['"+key+"']","outputs('Consultation_payload')?['"+key+"']") for key in payload if key!='OccurredOn']
    after={};last=bracket(after,'after',None)
    checks=stable('after')
    if kind=='response':
        after['Consultation_parent_after']=http(parent_item,last);last='Consultation_parent_after'
        checks+=[eq("outputs('Consultation_parent_after')?['headers']?['ETag']","outputs('Consultation_parent_before')?['headers']?['ETag']")]
        checks += [eq("body('Consultation_parent_after')?['"+key+"']","body('Consultation_parent_before')?['"+key+"']") for key in list(request_payload)+['Id','ParentEventUID','SupersedesEventUID']]
        after['Consultation_history_after']=http(query('ParentEventUID',request_uid),last);last='Consultation_history_after'
        checks+=complete(last)+["equals(length(body('Consultation_history_after')?['value']),1)",eq("first(body('Consultation_history_after')?['value'])?['EventUID']","outputs('Consultation_payload')?['EventUID']")]
    if kind=='response':
        checks += [eq(stable_history('Consultation_history_after'),stable_history('Read_consultation_event'))]
    after['Consultation_after_checks']=comp('@and('+','.join(checks)+')',last)
    after['Native_consultation_receipt']=comp({'qualified':"@equals(outputs('Consultation_after_checks'),true)",'consultationRecorded':True,'scope':'@'+scope,'eventUID':"@outputs('Consultation_payload')?['EventUID']",'createdCount':"@if(equals(length(body('Find_consultation_event')?['value']),0),1,0)",'progressionGranted':False,'contentReadinessGranted':False,'approvalGranted':False,'actorAuthorityQualified':False,'caseWrites':0,'sourceWrites':0,'notifications':0,'realPolicyEffects':False,'effectState':"@if(equals(outputs('Consultation_after_checks'),true),'retained-event-verified','retained-event-context-changed')"},'Consultation_after_checks')
    if kind=='response':
        from build_consultation_coverage import build_runtime
        reader=http(event_list_uri)
        coverage=build_runtime('Read_current_consultation_coverage',reader,[technical_role],
            qualified_reader=template,collection_uri=event_list_uri)
        final=bracket(coverage,'coverage','Consultation_coverage_Runtime_guard')
        fresh=stable('coverage')
        history="outputs('Consultation_coverage_Receipt')"
        coverage['Native_consultation_coverage_receipt']=comp({
            'technicalCoverageComplete':'@and(equals('+history+"?['coverageHistoryComplete'],true),"+','.join(fresh)+')',
            'nativeContextRevalidated':'@and('+','.join(fresh)+')',
            'preparedScope':'@'+scope,'requiredRoleResults':'@'+history+"?['requiredRoleResults']",
            'scopeRecordCount':'@'+history+"?['scopeRecordCount']",'writeCount':0,
            'progressionGranted':False,'contentReadinessAssessed':False,'policyApproved':False,
            'actorAuthorityQualified':False,'realPolicyEffects':False,
            'limits':'Technical consultation coverage only; human readiness and policy decisions remain separate.'},final)
        after['Check_current_consultation_coverage']={'type':'If',
            'expression':"@equals(outputs('Consultation_after_checks'),true)",
            'runAfter':{'Native_consultation_receipt':['Succeeded']},
            'actions':coverage,'else':{'actions':{}}}
    apply['Verify_consultation_event']=guard(exact,'Read_consultation_event',after,'Held_uncertain_consultation_event','Event readback differs or is incomplete; retain any event and reconcile before retry')
    # A readback mismatch cannot prove zero writes: override the ordinary hold.
    uncertain=apply['Verify_consultation_event']['else']['actions']['Held_uncertain_consultation_event']['inputs'];uncertain.update(consultationRecorded=None,eventWriteCount=None,effectState='unknown-reconcile-before-retry')
    # Native expressions have a finite size budget. Evaluate all conditions in
    # bounded, side-effect-free groups after the final history read; no additional
    # I/O or creator is inserted between these checks and the write guard.
    if len('@and('+','.join(before)+')')>7000:
        groups=[];group=[]
        for clause in before:
            if len('@and('+','.join(group+[clause])+')')>6000:
                if not group:raise ValueError('A single consultation condition exceeds the expression budget')
                groups.append(group);group=[]
            group.append(clause)
        if group:groups.append(group)
        before=[]
        for index,clauses in enumerate(groups):
            name='Consultation_before_checks_'+str(index)
            work[name]=comp('@and('+','.join(clauses)+')',previous);previous=name
            before.append("equals(outputs('"+name+"'),true)")
    work['Verify_consultation_before']=guard(before,previous,apply,'Held_stale_consultation_context','Prepared document, context or consultation history changed; no event attempted')
    valid=[eq("triggerBody()?['"+field+"']",quote(mode)),eq(c+"?['contextValid']",'true'),eq(r+"?['preparationQualified']",'true'),eq(r+"?['consultationOpenable']",'true'),eq(r+"?['originalSourceIsPreparedRevision']",'false'),eq(scope+"?['CaseUID']",c+"?['CaseUID']"),"not(equals("+scope+"?['DocumentReference'],"+c+"?['scope']?['DocumentReference']))"]
    a['Route_prepared_consultation_event']=guard(valid,'Route_consultation_prepared_context',work,'Held_unqualified_prepared_consultation','No verified same-case prepared revision is available; no consultation event attempted')
    # Suppress misleading holds during ownership operations; preparation failure is
    # reported by the reader itself and this receipt only concerns consultation.
    a['Route_prepared_consultation_event']['else']['actions']={}
    a['Held_consultation_runtime_error']=comp({'qualified':False,'consultationRecorded':None,'eventWriteCount':None,'effectState':'unknown-reconcile-before-retry','progressionGranted':False,'reason':'Inspect this native run and retained event before retry; do not overwrite or blindly resubmit'})
    a['Held_consultation_runtime_error']['runAfter']={'Route_prepared_consultation_event':['Failed','TimedOut']}
    audit_actions(d)
    return out
