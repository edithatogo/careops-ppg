"""Opt-in candidate graph for saved-byte finalisation; no deployment/native I/O."""
import copy


def extend_saved_body(a, binding, http, content, compose, check, output_path, file_uri):
    """Use only in a separately qualified profile/revision; defaults stay intact."""
    profile = binding.get('caseIntake') or binding.get('fullReview') or binding
    script_id = profile['scriptGraphId']
    kind = ('PPG-native-case-intake-request-v1' if binding.get('caseIntake') else
            'PPG-native-full-review-request-v1' if binding.get('fullReview') else
            'PPG-native-package-request-v1')
    prior = a['Require_request_kind']['expression']['and'][0]['equals'][0]
    a['Require_request_kind']['expression']['and'][0]['equals'][0] = (
        "@and(" + prior[1:] + ",equals(body('Read_request_config')?['kind'],'" + kind + "'))")
    safe = a['Require_safe_revision']['expression']['and'][0]['equals'][0]
    a['Require_safe_revision']['expression']['and'][0]['equals'][0] = (
        "@and(" + safe[1:] + ",startsWith(outputs('Revision'),'saved-'))")
    a['Native_request']['inputs']['includeFinalisationMembers'] = True
    generated = "outputs('Run_script_from_SharePoint_library')?['body/result/"
    final = "outputs('Finalise_saved_body')?['body/result/"
    claim_path = output_path('.saved-body.claim.json')
    a['Read_saved_body_claim'] = content(claim_path, 'Read_existing_pack')
    a['Read_saved_body_claim']['runAfter'] = {'Read_existing_pack':['Succeeded','Failed']}
    # A saved cover without the immutable finalisation claim is uncertain.
    # Preserve it for explicit native reconciliation; never silently adopt it.
    safe_outputs = ("or(and(equals(outputs('Read_existing_cover')?['statusCode'],404),"
        "equals(outputs('Read_existing_pack')?['statusCode'],404),"
        "equals(outputs('Read_saved_body_claim')?['statusCode'],404)),"
        "and(equals(outputs('Read_existing_cover')?['statusCode'],200),"
        "equals(outputs('Read_claim')?['statusCode'],200),"
        "equals(outputs('Read_saved_body_claim')?['statusCode'],200),"
        "or(equals(outputs('Read_existing_pack')?['statusCode'],200),"
        "equals(outputs('Read_existing_pack')?['statusCode'],404))))")
    a['Require_unchanged_outputs'] = check(safe_outputs, 'Read_saved_body_claim',
        'SAVED_BODY_UNCERTAIN', 'Preserve uncertain saved output; reconcile the exact original run before retry.')
    a['Require_unchanged_outputs']['runAfter'] = {'Read_saved_body_claim':['Succeeded','Failed']}
    a['Read_body_pin_before'] = http('GET',file_uri('.docx','?$select=UniqueId,ETag,Length,UIVersionLabel,ServerRelativeUrl'),'Ensure_cover')
    a['Read_body_bytes'] = content(output_path('.docx'),'Read_body_pin_before')
    a['Read_body_pin_after'] = http('GET',file_uri('.docx','?$select=UniqueId,ETag,Length,UIVersionLabel,ServerRelativeUrl'),'Read_body_bytes')
    request = {'kind':'m365-saved-body-package-v1',
        'generatedJobJson':'@'+generated+"jobJson']",'generatedClaimJson':'@'+generated+"claimJson']",
        'documentPath':"@json("+generated+"jobJson'])?['coverSnapshot']?['path']",
        'savedPinBefore':"@body('Read_body_pin_before')",'savedPinAfter':"@body('Read_body_pin_after')",
        'savedBodyBase64':"@body('Read_body_bytes')?['$content']",
        'existingSavedClaimJson':"@if(equals(outputs('Read_saved_body_claim')?['statusCode'],200),base64ToString(body('Read_saved_body_claim')?['$content']),'')"}
    a['Saved_body_request'] = compose(request,'Read_body_pin_after')
    run = copy.deepcopy(binding['runScriptAction'])
    run['runAfter'] = {'Saved_body_request':['Succeeded']}
    run['inputs']['parameters'].update({'scriptId':script_id,
        'ScriptParameters/jobJson':"@string(outputs('Saved_body_request'))",
        'ScriptParameters/membersJson':'@'+generated+"finalisationMembersJson']"})
    run['inputs']['retryPolicy'] = {'type':'none'}
    a['Finalise_saved_body'] = run
    missing = "equals(outputs('Read_saved_body_claim')?['statusCode'],404)"
    uri = file_uri('.saved-body.claim.json')[1:]
    folder = binding['folder']
    create = ("concat('_api/web/GetFolderByServerRelativePath(decodedurl=''" + folder
              + "'')/Files/AddUsingPath(decodedurl=''',outputs('Job_key'),'.saved-body.claim.json'',overwrite=false)')")
    a['Commit_saved_body_claim'] = http("@if("+missing+",'POST','GET')",
        '@if('+missing+','+create+','+uri+')','Finalise_saved_body',
        "@if("+missing+','+final+"claimJson'],'')")
    a['Read_committed_saved_body_claim'] = content(claim_path,'Commit_saved_body_claim')
    a['Require_saved_body_claim'] = check("equals(body('Read_committed_saved_body_claim')?['$content'],base64("+final+"claimJson']))",
        'Read_committed_saved_body_claim','SAVED_CLAIM_CHANGED','Preserve changed saved-body claim.')
    a['Require_saved_pack_unchanged'] = check("or(equals(outputs('Read_existing_pack')?['statusCode'],404),and(equals(outputs('Read_existing_pack')?['statusCode'],200),equals(body('Read_existing_pack')?['$content'],"+final+"zipBase64'])))",
        'Require_saved_body_claim','SAVED_PACKAGE_EDITED','Preserve edited saved-body package.')
    a['Ensure_pack']['runAfter'] = {'Require_saved_pack_unchanged':['Succeeded']}
    # Only downstream consumers switch to final bytes. Generated v1 claim and
    # original cover creation retain their original meaning and exact bytes.
    def replace(value):
        if isinstance(value,str): return value.replace(generated,final)
        if isinstance(value,list): return [replace(x) for x in value]
        if isinstance(value,dict): return {k:replace(v) for k,v in value.items()}
        return value
    for name in ['Ensure_pack','Require_saved_bytes','Expected_receipt','Receipt_shapes','Require_final_pair']:
        if name in a: a[name] = replace(a[name])
    fields = ['UniqueId','ETag','Length','UIVersionLabel','ServerRelativeUrl']
    def pin_equal(reader):
        return ','.join("equals(body('"+reader+"')?['"+key+"'],body('Read_body_pin_after')?['"+key+"'])" for key in fields)
    previous = a['Require_saved_bytes']['expression']['and'][0]['equals'][0]
    a['Require_saved_bytes']['expression']['and'][0]['equals'][0] = (
        '@and('+previous[1:]+','+pin_equal('Read_saved_cover_pin')+')')
    a['Read_final_saved_body_claim'] = content(claim_path,'Read_final_claim')
    a['Read_final_body_pin'] = http('GET',file_uri('.docx','?$select='+','.join(fields)),
        'Read_final_saved_body_claim')
    expression = ("and(equals(body('Read_final_claim')?['$content'],base64("+generated+"claimJson'])),"
        "equals(body('Read_final_saved_body_claim')?['$content'],base64("+final+"claimJson'])),"
        "equals(body('Read_final_cover')?['$content'],"+final+"coverBase64']),"
        "equals(body('Read_final_pack')?['$content'],"+final+"zipBase64']),"
        "equals(body('Read_final_receipt')?['$content'],base64(string(outputs('Expected_receipt')))),"
        +pin_equal('Read_final_body_pin')+")")
    a['Require_final_pair'] = check(expression,'Read_final_body_pin','FINAL_PAIR',
        'Post-commit bytes/claims differ; preserve all outputs.')
