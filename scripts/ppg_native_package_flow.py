"""Build the bounded M365 request-to-cover-and-existing-pack flow; no native I/O."""
import copy
import json
from uuid import UUID

FIELDS = ('PPGCoverTitle','PPGCoverCaseUID','PPGDocumentUID','PPGPolicyEdition',
          'PPGCoverRecordedOwner','PPGCoverReviewDate','PPGCoverOutputRevision')
PIN_FIELDS = ('UniqueId','ETag','Length','UIVersionLabel','ServerRelativeUrl')


def build_flow(existing, binding):
    """Own existing flow only. Bindings/actual outputs stay private, outside Git."""
    site=binding['site'];folder=binding['folder'];library=str(UUID(binding['libraryId']))
    if not site.startswith('https://') or not folder.startswith('/'):raise ValueError('native_binding_invalid')
    if any(v in folder for v in ("'",'..','?','#','\\')):raise ValueError('unsafe_output_folder')
    request_id=binding['requestItemId']
    if type(request_id) is not int or request_id<1:raise ValueError('request_item_invalid')
    p=existing['properties'];d=copy.deepcopy(p['definition']);a={}
    refs={k:copy.deepcopy(p['connectionReferences'][k]) for k in ['shared_sharepointonline','shared_excelonlinebusiness']}
    for ref in refs.values():ref['source']='Embedded'
    auth="@parameters('$authentication')"
    def lit(v):return "'"+str(v).replace("'","''")+"'"
    def dep(prev):return {} if prev is None else {prev:['Succeeded']}
    def http(method,uri,prev=None,body=None):
        params={'dataset':site,'parameters/method':method,'parameters/uri':uri,'parameters/headers':{'Accept':'application/json;odata=minimalmetadata'}}
        if body is not None:params['parameters/body']=body
        return {'type':'OpenApiConnection','runAfter':dep(prev),'inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_sharepointonline','connectionName':'shared_sharepointonline','operationId':'HttpRequest'},'parameters':params,'authentication':auth,'retryPolicy':{'type':'none'}}}
    def content(path,prev,infer=False):
        return {'type':'OpenApiConnection','runAfter':dep(prev),'inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_sharepointonline','connectionName':'shared_sharepointonline','operationId':'GetFileContentByPath'},'parameters':{'dataset':site,'path':path,'inferContentType':infer},'authentication':auth}}
    def check(expr,prev,code,message):return {'type':'If','runAfter':dep(prev),'expression':{'and':[{'equals':['@'+expr,True]}]},'actions':{},'else':{'actions':{'Refuse_'+code:{'type':'Terminate','runAfter':{},'inputs':{'runStatus':'Failed','runError':{'code':code,'message':message}}}}}}
    def compose(value,prev):return {'type':'Compose','runAfter':dep(prev),'inputs':value}
    def binary(action):return "body('"+action+"')?['$content']"
    def sp_path(expr):return "@substring("+expr+","+str(len(binding['sitePath']))+")"
    a['Request_ID']=compose("@int(if(empty(trim(string(coalesce(triggerBody()?['requestItemId'],'')))),'"+str(request_id)+"',triggerBody()?['requestItemId']))",None)
    item="@concat('_api/web/lists(guid''"+library+"'')/items(',string(outputs('Request_ID')),')')"
    selected="@concat('_api/web/lists(guid''"+library+"'')/items(',string(outputs('Request_ID')),')/File?$select="+','.join(PIN_FIELDS)+"')"
    a['Read_request_properties']=http('GET',item,'Request_ID');a['Read_request_pin']=http('GET',selected,'Read_request_properties')
    property_fields=('Id','GUID','Modified','OData__UIVersionString','odata.etag',*FIELDS)
    a['Request_property_pin']=compose({k:"@body('Read_request_properties')?['"+k+"']" for k in property_fields},'Read_request_pin')
    a['Read_request_config']=content(sp_path("body('Read_request_pin')?['ServerRelativeUrl']"),'Request_property_pin',True)
    a['Require_request_kind']=check("and(equals(body('Read_request_config')?['kind'],'PPG-native-package-request-v1'),startsWith(body('Read_request_pin')?['ServerRelativeUrl'],"+lit(folder+'/')+"))",'Read_request_config','REQUEST_KIND','Select a maintained PPG package request in its configured folder.')
    values={k:"@body('Read_request_properties')?['"+k+"']" for k in FIELDS}
    for k in ['PPGCoverRecordedOwner','PPGCoverReviewDate']:values[k]="@if(empty(trim(coalesce(body('Read_request_properties')?['"+k+"'],''))),'Unresolved',body('Read_request_properties')?['"+k+"'])"
    a['Accepted_values']=compose(values,'Require_request_kind');a['Revision']=compose("@coalesce(outputs('Accepted_values')?['PPGCoverOutputRevision'],'')",'Accepted_values')
    a['Revision_characters']={'type':'Query','runAfter':dep('Revision'),'inputs':{'from':"@range(0,length(outputs('Revision')))",'where':"@contains('abcdefghijklmnopqrstuvwxyz0123456789-',substring(outputs('Revision'),item(),1))"}}
    a['Require_safe_revision']=check("and(greater(length(outputs('Revision')),0),lessOrEquals(length(outputs('Revision')),40),equals(length(body('Revision_characters')),length(outputs('Revision'))),not(startsWith(outputs('Revision'),'-')))",'Revision_characters','REVISION','Enter a new lower-case revision with letters, numbers and hyphens (40 characters maximum).')
    a['Job_key']=compose("@concat('job-item',string(outputs('Request_ID')),'-',outputs('Revision'))",'Require_safe_revision')
    assets=[('compiled-template','compiled','compiledTemplateUniqueId'),('maintained-template','template','maintainedTemplateUniqueId'),('source-pack','source_pack','sourcePackUniqueId'),('source-job','source_job','sourceJobUniqueId'),('source-receipt','source_receipt','sourceReceiptUniqueId')]
    def pin_uri(field):return "@concat('_api/web/GetFileById(''',body('Read_request_config')?['"+field+"'],''')?$select="+','.join(PIN_FIELDS)+"')"
    prev='Job_key'
    for _,key,field in assets:a['Read_'+key+'_pin']=http('GET',pin_uri(field),prev);prev='Read_'+key+'_pin'
    a['Read_engine_pin']=http('GET',"_api/web/GetFileById('"+str(UUID(binding['enginePin']['UniqueId']))+"')?$select="+','.join(PIN_FIELDS),prev);prev='Read_engine_pin'
    engine="and("+','.join("equals(body('Read_engine_pin')?['"+k+"'],"+lit(binding['enginePin'][k])+")" for k in PIN_FIELDS)+")"
    a['Require_qualified_engine']=check(engine,prev,'ENGINE_CHANGED','The maintained packaging script changed; qualify the new script revision before use.');prev='Require_qualified_engine'
    for name,key,infer in [('Read_compiled','compiled',True),('Read_source_job','source_job',True),('Read_source_receipt','source_receipt',True),('Read_source_pack','source_pack',False),('Read_template','template',False)]:a[name]=content(sp_path("body('Read_"+key+"_pin')?['ServerRelativeUrl']"),prev,infer);prev=name
    pin_keys=[('request','Read_request_pin')]+[(role,'Read_'+key+'_pin') for role,key,_ in assets]+[('engine','Read_engine_pin')]
    def pin_array(suffix=''):
        return [{'role':role,**{k:"@body('"+name+suffix+"')?['"+k+"']" for k in PIN_FIELDS}} for role,name in pin_keys]
    a['Input_pins']=compose(pin_array(),prev)
    relative=folder[len(binding['sitePath']):]
    def output_path(ext):return "@concat("+lit(relative+'/')+",outputs('Job_key'),"+lit(ext)+")"
    def file_uri(ext,suffix='/$value'):return "@concat('_api/web/GetFileByServerRelativePath(decodedurl=''"+folder+"/',outputs('Job_key'),'"+ext+"'')"+suffix+"')"
    a['Read_claim']=content(output_path('.claim.json'),'Input_pins',False)
    a['Require_claim_readable']=check("or(equals(outputs('Read_claim')?['statusCode'],200),equals(outputs('Read_claim')?['statusCode'],404))",'Read_claim','CLAIM_READ','The existing job claim could not be read; no output will be replaced.');a['Require_claim_readable']['runAfter']={'Read_claim':['Succeeded','Failed']}
    request={'kind':'m365-cover-request-v1','generationRunId':"@workflow()?['run']?['name']",'requestItemId':"@outputs('Request_ID')",'createdAtUtc':"@formatDateTime(utcNow(),'yyyy-MM-ddTHH:mm:ssZ')",'existingClaimJson':"@if(equals(outputs('Read_claim')?['statusCode'],200),base64ToString(body('Read_claim')?['$content']),'')",'templateVersion':"@body('Read_request_config')?['templateVersion']",'template':"@body('Read_compiled')",'values':"@outputs('Accepted_values')",'sourceJobJson':"@body('Read_source_job')?['jobJson']",'sourceReceiptJson':"@string(body('Read_source_receipt'))",'sourcePin':"@body('Read_source_pack_pin')",'pinsJson':"@string(outputs('Input_pins'))"}
    a['Native_request']=compose(request,'Require_claim_readable')
    run=copy.deepcopy(binding['runScriptAction']);run['runAfter']=dep('Native_request');run['inputs']['authentication']=auth;run['inputs']['parameters']['scriptId']=binding['scriptGraphId'];run['inputs']['parameters']['ScriptParameters/jobJson']="@string(outputs('Native_request'))";run['inputs']['parameters']['ScriptParameters/membersJson']="@string(createArray(setProperty(setProperty(json('{}'),'path','existing-pack.zip'),'base64',body('Read_source_pack')?['$content']),setProperty(setProperty(json('{}'),'path','maintained-template.docx'),'base64',body('Read_template')?['$content'])))";a['Run_script_from_SharePoint_library']=run
    result="outputs('Run_script_from_SharePoint_library')?['body/result/"
    def recheck(label,prev):
        for role,name in pin_keys:
            key=name+'_'+label
            original=a[name];uri=original['inputs']['parameters']['parameters/uri']
            a[key]=http('GET',uri,prev);prev=key
        meta='Read_request_properties_'+label;a[meta]=http('GET',item,prev);prev=meta
        prop='Request_property_pin_'+label;a[prop]=compose({k:"@body('"+meta+"')?['"+k+"']" for k in property_fields},prev)
        pins='Input_pins_'+label;a[pins]=compose(pin_array('_'+label),prop)
        guard='Require_pins_'+label;a[guard]=check("and(equals(string(outputs('Input_pins')),string(outputs('"+pins+"'))),equals(string(outputs('Request_property_pin')),string(outputs('"+prop+"'))))",pins,'INPUT_CHANGED_'+label,'Input changed during generation. Keep the retained files and use a new revision.');return guard
    prev=recheck('before_write','Run_script_from_SharePoint_library')
    for name,ext in [('Read_existing_cover','.docx'),('Read_existing_pack','.zip')]:
        a[name]=content(output_path(ext),prev);a[name]['runAfter']={prev:['Succeeded','Failed']} if prev.startswith('Read_existing') else dep(prev);prev=name
    expr='and('+','.join("or(equals(outputs('"+name+"')?['statusCode'],404),and(equals(outputs('"+name+"')?['statusCode'],200),equals("+binary(name)+','+result+field+"'])))" for name,field in [('Read_existing_cover','coverBase64'),('Read_existing_pack','zipBase64')])+')'
    a['Require_unchanged_outputs']=check(expr,prev,'OUTPUT_EDITED','A saved cover/package differs or cannot be read. Preserve it and use a new revision.');a['Require_unchanged_outputs']['runAfter']={prev:['Succeeded','Failed']}
    missing="equals(outputs('Read_claim')?['statusCode'],404)";create_claim="@concat('_api/web/GetFolderByServerRelativePath(decodedurl=''"+folder+"'')/Files/AddUsingPath(decodedurl=''',outputs('Job_key'),'.claim.json'',overwrite=false)')"
    a['Ensure_claim']=http("@if("+missing+",'POST','GET')","@if("+missing+","+create_claim[1:]+","+file_uri('.claim.json')[1:]+")",'Require_unchanged_outputs',"@if("+missing+","+result+"claimJson'],'')")
    a['Read_saved_claim']=content(output_path('.claim.json'),'Ensure_claim')
    a['Require_saved_claim']=check("equals(body('Read_saved_claim')?['$content'],base64("+result+"claimJson']))",'Read_saved_claim','CLAIM_CHANGED','The saved job claim differs. Preserve retained files and reconcile this revision.')
    stage='PPG-native-stage-';stage_path=relative+"/"+stage+"@{workflow()?['run']?['name']}"
    def connector(op,params,prev):return {'type':'OpenApiConnection','runAfter':dep(prev),'inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_sharepointonline','connectionName':'shared_sharepointonline','operationId':op},'parameters':{'dataset':site,**params},'authentication':auth,'retryPolicy':{'type':'none'}}}
    prepare=connector('CreateNewFolder',{'table':library,'parameters/path':relative.strip('/')+'/'+stage+"@{workflow()?['run']?['name']}"},None)
    a['Prepare_stage']={'type':'If','runAfter':dep('Require_saved_claim'),'expression':{'or':[{'equals':["@outputs('Read_existing_cover')?['statusCode']",404]},{'equals':["@outputs('Read_existing_pack')?['statusCode']",404]}]},'actions':{'Create_stage':prepare},'else':{'actions':{}}}
    prev='Prepare_stage'
    for label,ext,field in [('cover','.docx','coverBase64'),('pack','.zip','zipBase64')]:
        create=connector('CreateFile',{'folderPath':stage_path,'name':"@concat(outputs('Job_key'),'"+ext+"')",'body':"@base64ToBinary("+result+field+"'])"},None)
        move=connector('MoveFileAsync',{'parameters/sourceFileId':"@body('Create_"+label+"')?['Id']",'parameters/destinationDataset':site,'parameters/destinationFolderPath':relative,'parameters/nameConflictBehavior':0},'Create_'+label)
        a['Ensure_'+label]={'type':'If','runAfter':dep(prev),'expression':{'and':[{'equals':["@outputs('Read_existing_"+label+"')?['statusCode']",404]}]},'actions':{'Create_'+label:create,'Move_'+label:move},'else':{'actions':{}}};prev='Ensure_'+label
    for label,ext in [('cover','.docx'),('pack','.zip')]:
        a['Read_saved_'+label]=content(output_path(ext),prev);prev='Read_saved_'+label
        a['Read_saved_'+label+'_pin']=http('GET',file_uri(ext,'?$select='+','.join(PIN_FIELDS)),prev);prev='Read_saved_'+label+'_pin'
    valid='and(equals('+binary('Read_saved_cover')+','+result+"coverBase64']),equals("+binary('Read_saved_pack')+','+result+"zipBase64']))"
    a['Require_saved_bytes']=check(valid,prev,'SAVED_BYTES','Saved cover or package differs from the generated bytes.');prev=recheck('before_receipt','Require_saved_bytes')
    record={'kind':'PPG-native-package-completion-v1','jobId':"@"+result+"jobId']",'outputRevision':"@"+result+"outputRevision']",'jobSHA256':"@"+result+"jobSHA256']",'requestSHA256':"@"+result+"requestSHA256']",'job':"@json("+result+"jobJson'])",'claim':"@json("+result+"claimJson'])",'cover':{'sha256':"@"+result+"coverSHA256']",'pin':"@body('Read_saved_cover_pin')"},'package':{'sha256':"@"+result+"packageSHA256']",'pin':"@body('Read_saved_pack_pin')"},'status':'DRAFT / HUMAN CHECK REQUIRED','selectionKind':'existing-frozen-package','caseCurrencyEstablished':False,'sourceWrites':False,'caseWrites':False,'sent':False,'policyApproved':False,'pdfStatus':'separate'}
    a['Expected_receipt']=compose(record,prev);a['Read_existing_receipt']=content(output_path('.receipt.json'),'Expected_receipt',False)
    no_receipt="equals(outputs('Read_existing_receipt')?['statusCode'],404)";same_receipt="and(equals(outputs('Read_existing_receipt')?['statusCode'],200),equals(body('Read_existing_receipt')?['$content'],base64(string(outputs('Expected_receipt')))))";create="@concat('_api/web/GetFolderByServerRelativePath(decodedurl=''"+folder+"'')/Files/AddUsingPath(decodedurl=''',outputs('Job_key'),'.receipt.json'',overwrite=false)')"
    a['Commit_or_reuse_receipt']=http("@if("+no_receipt+",'POST','GET')","@if("+no_receipt+','+create[1:]+',if('+same_receipt+','+file_uri('.receipt.json')[1:]+",'_api/PPG_RECEIPT_CHANGED'))",None,"@if("+no_receipt+",string(outputs('Expected_receipt')),'')");a['Commit_or_reuse_receipt']['runAfter']={'Read_existing_receipt':['Succeeded','Failed']}
    prev='Commit_or_reuse_receipt'
    for label,ext in [('cover','.docx'),('pack','.zip'),('receipt','.receipt.json'),('claim','.claim.json')]:a['Read_final_'+label]=content(output_path(ext),prev);prev='Read_final_'+label
    final="and(equals("+binary('Read_final_claim')+",base64("+result+"claimJson'])),equals("+binary('Read_final_cover')+','+result+"coverBase64']),equals("+binary('Read_final_pack')+','+result+"zipBase64']),equals("+binary('Read_final_receipt')+",base64(string(outputs('Expected_receipt')))))"
    a['Require_final_pair']=check(final,prev,'FINAL_PAIR','Post-commit output/receipt readback differs. Preserve the saved files.');a['Core_complete']=compose({'status':'COMPLETE / DRAFT','jobId':"@outputs('Job_key')",'cover':"@body('Read_saved_cover_pin')?['ServerRelativeUrl']",'package':"@body('Read_saved_pack_pin')?['ServerRelativeUrl']",'receipt':"@concat("+lit(folder+'/')+",outputs('Job_key'),'.receipt.json')"},'Require_final_pair')
    # Optional PDF is deliberately downstream of the committed, usable core pair.
    if binding.get('pdfConnection'):
        refs['shared_onedriveforbusiness']=copy.deepcopy(binding['pdfConnection'])
        refs['shared_onedriveforbusiness']['source']='Embedded'
        def od(op,params,prev):
            return {'type':'OpenApiConnection','runAfter':dep(prev),'inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness','connectionName':'shared_onedriveforbusiness','operationId':op},'parameters':params,'authentication':auth,'retryPolicy':{'type':'none'}}}
        pdf={};pdf['Read_PDF_receipt']=content(output_path('.pdf.receipt.json'),None)
        readable=http('GET',"@if(or(equals(outputs('Read_PDF_receipt')?['statusCode'],200),equals(outputs('Read_PDF_receipt')?['statusCode'],404)),'_api/web/currentuser?$select=Id','_api/PPG_PDF_RECEIPT_UNREADABLE')",None)
        readable['runAfter']={'Read_PDF_receipt':['Succeeded','Failed']};pdf['Require_PDF_receipt_readable']=readable
        fresh={};fresh['Create_conversion_copy']=od('CreateFile',{'folderPath':binding.get('pdfScratchFolder','/PPG-word-qualification'),'name':"@concat(outputs('Job_key'),'-',workflow()?['run']?['name'],'.docx')",'body':"@base64ToBinary("+result+"coverBase64'])"},None)
        fresh['Allow_conversion_availability']={'type':'Wait','runAfter':dep('Create_conversion_copy'),'inputs':{'interval':{'count':5,'unit':'Second'}}}
        fresh['Convert_cover']=od('ConvertFile',{'id':"@body('Create_conversion_copy')?['Id']",'type':'PDF'},'Allow_conversion_availability')
        fresh['Convert_cover']['inputs']['retryPolicy']={'type':'exponential','count':2,'interval':'PT5S','minimumInterval':'PT5S','maximumInterval':'PT15S'}
        pdf_folder=relative+"/PPG-PDF-@{workflow()?['run']?['name']}"
        fresh['Prepare_PDF_folder']=connector('CreateNewFolder',{'table':library,'parameters/path':pdf_folder.strip('/')},'Convert_cover')
        fresh['Save_PDF']=connector('CreateFile',{'folderPath':pdf_folder,'name':"@concat(outputs('Job_key'),'.pdf')",'body':"@body('Convert_cover')"},'Prepare_PDF_folder')
        pdf_path=pdf_folder+"/@{outputs('Job_key')}.pdf"
        fresh['Read_saved_PDF']=content(pdf_path,'Save_PDF')
        pdf_uri="@concat('_api/web/GetFileByServerRelativePath(decodedurl=''"+folder+"/PPG-PDF-',workflow()?['run']?['name'],'/',outputs('Job_key'),'.pdf'')?$select="+','.join(PIN_FIELDS)+"')"
        fresh['Read_saved_PDF_pin']=http('GET',pdf_uri,'Read_saved_PDF')
        fresh['Read_cover_for_PDF_commit']=content(output_path('.docx'),'Read_saved_PDF_pin')
        fresh['Require_PDF_saved_bytes']=http('GET',"@if(and(equals(body('Read_saved_PDF')?['$content'],body('Convert_cover')?['$content']),equals(body('Read_cover_for_PDF_commit')?['$content'],"+result+"coverBase64'])),'_api/web/currentuser?$select=Id','_api/PPG_PDF_BYTES_CHANGED')",'Read_cover_for_PDF_commit')
        pdf_record={'kind':'PPG-native-package-PDF-v1','jobId':"@outputs('Job_key')",'requestSHA256':"@"+result+"requestSHA256']",'coverSHA256':"@"+result+"coverSHA256']",'packageSHA256':"@"+result+"packageSHA256']",'pdfPin':{k:"@body('Read_saved_PDF_pin')?['"+k+"']" for k in PIN_FIELDS},'generationRunId':"@workflow()?['run']?['name']",'status':'DRAFT'}
        fresh['PDF_success_record']=compose(pdf_record,'Require_PDF_saved_bytes')
        receipt_create="@concat('_api/web/GetFolderByServerRelativePath(decodedurl=''"+folder+"'')/Files/AddUsingPath(decodedurl=''',outputs('Job_key'),'.pdf.receipt.json'',overwrite=false)')"
        fresh['Commit_PDF_receipt']=http('POST',receipt_create,'PDF_success_record',"@string(outputs('PDF_success_record'))")
        fresh['Read_committed_PDF_receipt']=content(output_path('.pdf.receipt.json'),'Commit_PDF_receipt')
        fresh['Require_PDF_receipt_bytes']=http('GET',"@if(equals(body('Read_committed_PDF_receipt')?['$content'],base64(string(outputs('PDF_success_record')))),'_api/web/currentuser?$select=Id','_api/PPG_PDF_RECEIPT_BYTES_CHANGED')",'Read_committed_PDF_receipt')
        reuse={};reuse['Existing_PDF_record']=compose("@json(base64ToString(body('Read_PDF_receipt')?['$content']))",None)
        pin="outputs('Existing_PDF_record')?['pdfPin']"
        reuse['Read_existing_PDF_pin']=http('GET',"@concat('_api/web/GetFileById(''',"+pin+"?['UniqueId'],''')?$select="+','.join(PIN_FIELDS)+"')",'Existing_PDF_record')
        matches=["equals(outputs('Existing_PDF_record')?['"+k+"'],"+result+field+"'])" for k,field in [('requestSHA256','requestSHA256'),('coverSHA256','coverSHA256'),('packageSHA256','packageSHA256')]]
        matches += ["equals(body('Read_existing_PDF_pin')?['"+k+"'],"+pin+"?['"+k+"'])" for k in PIN_FIELDS]
        reuse['Require_existing_PDF_unchanged']=http('GET',"@if(and("+','.join(matches)+"),'_api/web/currentuser?$select=Id','_api/PPG_PDF_EDITED_OR_INPUT_CHANGED')",'Read_existing_PDF_pin')
        pdf['Create_or_reuse_PDF']={'type':'If','runAfter':dep('Require_PDF_receipt_readable'),'expression':{'equals':["@outputs('Read_PDF_receipt')?['statusCode']",404]},'actions':fresh,'else':{'actions':reuse}}
        a['Optional_PDF']={'type':'Scope','runAfter':dep('Core_complete'),'actions':pdf}
        a['PDF_outcome']={'type':'Compose','runAfter':{'Optional_PDF':['Succeeded','Failed','TimedOut']},'inputs':{'coreStatus':'COMPLETE / DRAFT','pdfStatus':"@if(equals(actions('Optional_PDF')?['status'],'Succeeded'),'COMPLETE / DRAFT','FAILED — DOCX and package remain usable; inspect Optional_PDF and retry the same revision')",'runId':"@workflow()?['run']?['name']",'core':"@outputs('Core_complete')"}}
        failure_uri=receipt_create.replace("'.pdf.receipt.json'',overwrite=false)","'.pdf-failed-',workflow()?['run']?['name'],'.json'',overwrite=false)")
        a['Record_PDF_failure']={'type':'If','runAfter':dep('PDF_outcome'),'expression':{'not':{'equals':["@actions('Optional_PDF')?['status']",'Succeeded']}},'actions':{'Save_PDF_failure':http('POST',failure_uri,None,"@string(outputs('PDF_outcome'))")},'else':{'actions':{}}}
    if binding.get('fullReview'):
        # An explicit request kind selects the new version. Legacy requests keep
        # their original script, engine pin, input-pin order and job fingerprint.
        full=binding['fullReview'];full_id=str(UUID(full['enginePin']['UniqueId']))
        chosen="equals(body('Read_request_config')?['kind'],'PPG-native-full-review-request-v1')"
        if binding.get('caseIntake'):
            chosen="or("+chosen+",equals(body('Read_request_config')?['kind'],'PPG-native-case-intake-request-v1'))"
        legacy="equals(body('Read_request_config')?['kind'],'PPG-native-package-request-v1')"
        a['Require_request_kind']['expression']={'and':[{'equals':['@and(or('+chosen+','+legacy+'),startsWith(body(\'Read_request_pin\')?[\'ServerRelativeUrl\'],'+lit(folder+'/')+'))',True]}]}
        old_engine=a['Read_engine_pin']['inputs']['parameters']['parameters/uri']
        new_engine="_api/web/GetFileById('"+full_id+"')?$select="+','.join(PIN_FIELDS)
        engine_uri='@if('+chosen+','+lit(new_engine)+','+lit(old_engine)+')'
        engine_match='and('+','.join("equals(body('Read_engine_pin')?['"+k+"'],"+lit(full['enginePin'][k])+")" for k in PIN_FIELDS)+')'
        a['Require_qualified_engine']['expression']={'and':[{'equals':['@if('+chosen+','+engine_match+','+engine+')',True]}]}
        full_uri="@concat('_api/web/GetFileById(''',if("+chosen+",body('Read_request_config')?['fullDocumentInputUniqueId'],body('Read_request_config')?['compiledTemplateUniqueId']),''')?$select="+','.join(PIN_FIELDS)+"')"
        a['Read_full_input_pin']=http('GET',full_uri,'Read_template')
        a['Read_full_input']=content(sp_path("body('Read_full_input_pin')?['ServerRelativeUrl']"),'Read_full_input_pin',True)
        a['Input_pins']['runAfter']=dep('Read_full_input')
        for suffix in ['', '_before_write', '_before_receipt']:
            a['Read_engine_pin'+suffix]['inputs']['parameters']['parameters/uri']=engine_uri
            name='Input_pins'+suffix;old_pins=a[name]['inputs']
            extra={'role':'full-document-input',**{k:"@body('Read_full_input_pin"+suffix+"')?['"+k+"']" for k in PIN_FIELDS}}
            sets='Pin_sets'+suffix
            a[sets]=compose({'legacy':old_pins,'full':old_pins+[extra]},next(iter(a[name]['runAfter'])))
            a[name]['runAfter']=dep(sets);a[name]['inputs']='@if('+chosen+",outputs('"+sets+"')?['full'],outputs('"+sets+"')?['legacy'])"
            if suffix:
                previous='Read_request_properties'+suffix
                a['Read_full_input_pin'+suffix]=http('GET',full_uri,next(iter(a[previous]['runAfter'])))
                a[previous]['runAfter']=dep('Read_full_input_pin'+suffix)
        a['Native_request']['inputs']['kind']='@if('+chosen+",'m365-full-review-request-v1','m365-cover-request-v1')"
        # Revision is technical request metadata, so one library-property edit
        # advances a request without editing a second JSON copy. Preserve the
        # original serialized input when it already agrees (stable old replay).
        full_input="if(equals(body('Read_full_input')?['outputRevision'],outputs('Accepted_values')?['PPGCoverOutputRevision']),body('Read_full_input'),setProperty(body('Read_full_input'),'outputRevision',outputs('Accepted_values')?['PPGCoverOutputRevision']))"
        a['Native_request']['inputs']['fullDocumentInputJson']='@if('+chosen+',string('+full_input+"),'')"
        a['Native_request']['inputs']['sourceSelectionJson']='@if('+chosen+",coalesce(body('Read_source_job')?['selectionJson'],''),'')"
        # Static script IDs retain the connector's exact two-parameter schema.
        # A dynamic ID makes the service demand an untyped ScriptParameters
        # object and was rejected before save during native qualification.
        legacy_run=copy.deepcopy(a['Run_script_from_SharePoint_library']);legacy_run['runAfter']={}
        full_run=copy.deepcopy(legacy_run);full_run['inputs']['parameters']['scriptId']=full['scriptGraphId']
        a['Select_document_script']={'type':'If','runAfter':dep('Native_request'),'expression':{'equals':['@'+chosen,True]},'actions':{'Run_full_review_script':full_run},'else':{'actions':{'Run_existing_cover_script':legacy_run}}}
        a['Run_script_from_SharePoint_library']=compose('@if('+chosen+",outputs('Run_full_review_script'),outputs('Run_existing_cover_script'))",'Select_document_script')
        a['Expected_receipt']['inputs']['generationRoute']="@"+result+"generationRoute']"
        a['Expected_receipt']['inputs']['documentShape']='@if('+chosen+",'maintained-full-review-v1','fixed-cover-v1')"
        # Keep existing receipt bytes stable for legacy replay. New extra fields
        # belong only to the full route's completion record.
        full_record=copy.deepcopy(a['Expected_receipt']['inputs'])
        old_record=copy.deepcopy(full_record);old_record.pop('generationRoute');old_record.pop('documentShape')
        a['Receipt_shapes']=compose({'legacy':old_record,'full':full_record},next(iter(a['Expected_receipt']['runAfter'])))
        a['Expected_receipt']['runAfter']=dep('Receipt_shapes');a['Expected_receipt']['inputs']='@if('+chosen+",outputs('Receipt_shapes')?['full'],outputs('Receipt_shapes')?['legacy'])"
    if binding.get('caseIntake'):
        if not binding.get('fullReview'):raise ValueError('case_intake_requires_full_template_route')
        from ppg_native_case_intake import extend_case_intake
        extend_case_intake(a,binding,http,content,compose,check,sp_path,lit)
    if binding.get('savedBodyFinalisation'):
        if binding['savedBodyFinalisation'] is not True or binding.get('pdfConnection'):
            raise ValueError('saved_body_candidate_requires_explicit_profile_without_pdf')
        from ppg_saved_body_flow import extend_saved_body
        extend_saved_body(a,binding,http,content,compose,check,output_path,file_uri)
    # Save payloads omit authentication; the service supplies the connection
    # token expression. Never copy authentication material from a run or client.
    def omit_service_auth(group):
        for action in group.values():
            if action.get('type')=='OpenApiConnection':action['inputs'].pop('authentication',None)
            omit_service_auth(action.get('actions',{}));omit_service_auth(action.get('else',{}).get('actions',{}))
    omit_service_auth(a)
    d['actions']=a;d['triggers']={'manual':{'type':'Request','kind':'Button','inputs':{'schema':{'type':'object','properties':{'requestItemId':{'type':'string','title':'Package request ID (optional)','description':'Leave blank for the maintained PPG request.'}},'required':[]}},'runtimeConfiguration':{'concurrency':{'runs':1}}}}
    return {'properties':{'definition':d,'connectionReferences':refs,'displayName':'PPG | Generate cover and existing pack','state':'Stopped'}}
