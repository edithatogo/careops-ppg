"""Build the standard-connector, on-demand web guide reconciliation flow.

Private target bindings are injected at deployment. No clinical content in Git.
"""
import copy


def build(site, source_list, context_list, guide_list, reference):
    def api(uri, method='GET', body=None, after=None):
        params={'dataset':site,'parameters/method':method,'parameters/uri':uri,
                'parameters/headers':{'Accept':'application/json;odata=nometadata'}}
        if body is not None:
            params['parameters/headers']['Content-Type']='application/json;odata=nometadata'
            params['parameters/body']=body
        return dict(type='OpenApiConnection',inputs={'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_sharepointonline','connectionName':'shared_sharepointonline','operationId':'HttpRequest'},'parameters':params,'retryPolicy':{'type':'none'}},runAfter=after or {})
    def dep(name):return {name:['Succeeded']}
    def stop(message):return dict(type='Terminate',inputs={'runStatus':'Failed','runError':{'code':'ReconciliationHeld','message':message}},runAfter={})
    def condition(expression, yes, no, after=None):return dict(type='If',expression=expression,actions=yes,else_={'actions':no},runAfter=after or {})
    def iff(expression,yes,no,after=None):
        a=condition(expression,yes,no,after);a['else']=a.pop('else_');return a
    def compose(value,after=None):return dict(type='Compose',inputs=value,runAfter=after or {})
    lists=lambda x:"_api/web/lists(guid'"+x+"')/items"
    fields={key:{'type':'string','title':title,'x-ms-dynamically-added':True,'x-ms-content-hint':'TEXT'} for key,title in {
        'mode':'Capture or Reconcile','sourceId':'Procedure section item ID (Capture)',
        'contextKey':'New review snapshot name (Capture)','contextId':'Review context item ID (Reconcile)',
        'guideRevision':'New guide revision (Reconcile)','guideText':'Complete reconciled guide text (Reconcile)',
        'rationale':'Reason and reconciliation notes (Reconcile)'}.items()}
    fields['mode']['enum']=['Capture','Reconcile']
    trigger={'type':'Request','kind':'Button','inputs':{'schema':{'type':'object','properties':fields,'required':['mode']}},'runtimeConfiguration':{'concurrency':{'runs':1}}}
    read_context=api("@concat('"+lists(context_list).replace("'","''")+"(', string(int(triggerBody()?['contextId'])), ')')")
    actions={'Initialise_anchor':{'type':'InitializeVariable','inputs':{'variables':[{'name':'AnchorId','type':'integer','value':0}]},'runAfter':{}},
       'Resolve_mode':iff("@equals(triggerBody()?['mode'],'Capture')",
          {'Set_capture_anchor':{'type':'SetVariable','inputs':{'name':'AnchorId','value':"@int(triggerBody()?['sourceId'])"},'runAfter':{}}},
          {'Read_context':read_context,'Set_context_anchor':{'type':'SetVariable','inputs':{'name':'AnchorId','value':"@int(body('Read_context')?['SourceAnchorId'])"},'runAfter':dep('Read_context')}},dep('Initialise_anchor'))}
    actions['Read_anchor']=api("@concat('"+lists(source_list).replace("'","''")+"(', string(variables('AnchorId')), ')')",after=dep('Resolve_mode'))
    actions['Read_sections']=api(lists(source_list)+'?$top=5000&$orderby=Id asc',after=dep('Read_anchor'))
    actions['Filter_sections']={'type':'Query','inputs':{'from':"@body('Read_sections')?['value']",'where':"@and(equals(item()?['DocumentUID'],body('Read_anchor')?['DocumentUID']),equals(item()?['ProposalRevision'],body('Read_anchor')?['ProposalRevision']))"},'runAfter':dep('Read_sections')}
    actions['Snapshot']={'type':'Select','inputs':{'from':"@body('Filter_sections')",'select':{k:v for k,v in {
        'Id':"@item()?['Id']",'SectionKey':"@item()?['SectionKey']",'SectionId':"@item()?['SectionId']",'Title':"@item()?['Title']",'Text':"@item()?['ProposedText']",'Definition':"@item()?['SectionJSON']",'ModuleKind':"@item()?['ModuleKind']",'TemplateHeading':"@item()?['TemplateHeading']",'Version':"@coalesce(item()?['OData__UIVersionString'],item()?['_UIVersionString'])"}.items()}},'runAfter':dep('Filter_sections')}
    actions['Review_lines']={'type':'Select','inputs':{'from':"@body('Snapshot')",'select':"@concat(item()?['Title'],' [',string(item()?['Version']),']',decodeUriComponent('%0A'),item()?['Text'])"},'runAfter':dep('Snapshot')}
    capture={'Read_existing_contexts':api(lists(context_list)+'?$top=5000'),
      'Match_context':{'type':'Query','inputs':{'from':"@body('Read_existing_contexts')?['value']",'where':"@equals(item()?['ContextKey'],triggerBody()?['contextKey'])"},'runAfter':dep('Read_existing_contexts')}}
    context_payload={'Title':"@triggerBody()?['contextKey']",'ContextKey':"@triggerBody()?['contextKey']",'SourceAnchorId':"@variables('AnchorId')",'DocumentUID':"@body('Read_anchor')?['DocumentUID']",'ProposalRevision':"@body('Read_anchor')?['ProposalRevision']",'SnapshotJSON':"@string(body('Snapshot'))",'SourceReviewText':"@join(body('Review_lines'),decodeUriComponent('%0A%0A'))"}
    capture['Create_or_reuse_context']=iff("@equals(length(body('Match_context')),0)",{'Create_context':api(lists(context_list),'POST',context_payload)}, {'Check_existing_context':iff("@and(equals(length(body('Match_context')),1),equals(first(body('Match_context'))?['SnapshotJSON'],string(body('Snapshot'))))",{'Context_reused':compose('Existing matching context retained')},{'Hold_context':stop('Context key already exists with different evidence; choose a new snapshot name')})},dep('Match_context'))
    reconcile={'Guide_key':compose("@concat(string(body('Read_context')?['Id']),':',triggerBody()?['guideRevision'])"),
      'Read_existing_guides':api(lists(guide_list)+'?$top=5000',after=dep('Guide_key')),
      'Match_guide':{'type':'Query','inputs':{'from':"@body('Read_existing_guides')?['value']",'where':"@equals(item()?['GuideKey'],outputs('Guide_key'))"},'runAfter':dep('Read_existing_guides')}}
    payload={'Title':"@concat('UNAPPROVED ',triggerBody()?['guideRevision'])",'GuideKey':"@outputs('Guide_key')",'ContextId':"@body('Read_context')?['Id']",'GuideRevision':"@triggerBody()?['guideRevision']",'GuideText':"@triggerBody()?['guideText']",'Rationale':"@triggerBody()?['rationale']",'DocumentUID':"@body('Read_anchor')?['DocumentUID']",'ProposalRevision':"@body('Read_anchor')?['ProposalRevision']",'SnapshotJSON':"@string(body('Snapshot'))"}
    reconcile['Create_or_reuse_guide']=iff("@equals(length(body('Match_guide')),0)",{'Create_guide':api(lists(guide_list),'POST',payload)}, {'Verify_existing_guide':iff("@and(equals(length(body('Match_guide')),1),equals(first(body('Match_guide'))?['GuideText'],triggerBody()?['guideText']),equals(first(body('Match_guide'))?['Rationale'],triggerBody()?['rationale']),equals(first(body('Match_guide'))?['SnapshotJSON'],string(body('Snapshot'))))",{'Guide_reused':compose('Matching guide revision retained; no write')},{'Hold_guide':stop('Guide revision exists with different content; preserve edits and choose a new revision')})},dep('Match_guide'))
    capture_guard="@and(not(empty(trim(coalesce(triggerBody()?['contextKey'],'')))),lessOrEquals(length(triggerBody()?['contextKey']),100))"
    reconcile_guard="@and(equals(triggerBody()?['mode'],'Reconcile'),equals(body('Read_context')?['DocumentUID'],body('Read_anchor')?['DocumentUID']),equals(body('Read_context')?['ProposalRevision'],body('Read_anchor')?['ProposalRevision']),equals(body('Read_context')?['SnapshotJSON'],string(body('Snapshot'))),not(empty(trim(coalesce(triggerBody()?['guideRevision'],'')))),lessOrEquals(length(triggerBody()?['guideRevision']),100),not(empty(trim(coalesce(triggerBody()?['guideText'],'')))),not(empty(trim(coalesce(triggerBody()?['rationale'],'')))))"
    actions['Validate_snapshot']=iff("@and(not(empty(body('Snapshot'))),less(length(body('Read_sections')?['value']),5000),empty(body('Read_sections')?['odata.nextLink']),empty(body('Read_sections')?['@odata.nextLink']),lessOrEquals(length(string(body('Snapshot'))),60000))",{'Choose_operation':iff("@equals(triggerBody()?['mode'],'Capture')",{'Validate_capture':iff(capture_guard,capture,{'Hold_capture':stop('Snapshot name required, maximum 100 characters')})},{'Validate_reconciliation':iff(reconcile_guard,reconcile,{'Hold_reconciliation':stop('Source changed or guide revision/text/rationale missing; capture a fresh review snapshot')})})},{'Hold_snapshot':stop('Missing/partial/oversized source snapshot; no output created')},dep('Review_lines'))
    # Guard potentially truncated duplicate inventories too; fail before any write.
    for branch,read,write in [(capture,'Read_existing_contexts','Create_or_reuse_context'),(reconcile,'Read_existing_guides','Create_or_reuse_guide')]:
        original=branch[write];branch[write]=iff("@and(less(length(body('"+read+"')?['value']),5000),empty(body('"+read+"')?['odata.nextLink']),empty(body('"+read+"')?['@odata.nextLink']))",{'Safe_'+write:dict(original,runAfter={})},{'Hold_'+write:stop('Partial existing-output inventory')},original['runAfter'])
    definition={'$schema':'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#','contentVersion':'1.0.0.0','parameters':{'$authentication':{'type':'SecureObject','defaultValue':{}},'$connections':{'type':'Object','defaultValue':{}}},'triggers':{'manual':trigger},'actions':actions,'outputs':{}}
    return {'properties':{'displayName':'PPG | Web guide reconciliation','state':'Stopped','definition':definition,'connectionReferences':{'shared_sharepointonline':copy.deepcopy(reference)}}}
