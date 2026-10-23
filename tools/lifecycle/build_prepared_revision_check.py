"""GET-only prepared-artifact reader for the existing case evidence link.

Selection is a same-site DOCX URL. All identity/version/hash assertions come from
its version-keyed native qualification receipt, not operator-entered pins.
"""
import copy
from urllib.parse import urlsplit

CASE_INPUT_FIELDS = ('Id', 'CaseUID', 'Title', 'linkedDocumentUIDs', 'sourceBaselineRef',
    'accountableRole', 'caseStatus', 'proposedOutcome', 'nextAction', 'targetDate', 'Created', 'GUID', 'AuthorId')


def build_actions(context, binding, ownership_context):
    original = context['properties']['definition']['actions']['Resolve_context']['actions']
    template = original['Read_selected_case']
    dataset = template['inputs']['parameters']['dataset']; parts = urlsplit(dataset)
    origin = parts.scheme + '://' + parts.netloc
    folder = binding['artifactFolderRelative']
    if not folder.startswith(parts.path + '/') or "'" in folder or '..' in folder:
        raise ValueError('Approved same-site evidence folder required')
    if binding.get('caseEvidenceFieldType') != 'Note':
        raise ValueError('This qualified case field is plain-text Note, not a URL object')
    template_uid = binding['templateFileUniqueId']
    import uuid
    uuid.UUID(template_uid)
    c = "outputs('Selected_case_context')"; req = "outputs('Parse_baseline')?['request']"
    receipt = "outputs('Parse_prepared_receipt')"; file = "body('Read_prepared_file_before')"
    selected = "first(body('Find_prepared_receipt')?['value'])"
    def quote(s): return "'" + s.replace("'", "''") + "'"
    def http(uri, previous=None):
        result = copy.deepcopy(template); result['inputs']['parameters']['parameters/uri'] = uri
        result['runAfter'] = {previous:['Succeeded']} if previous else {}
        return result
    def comp(value, previous=None):
        return {'type':'Compose','inputs':value,'runAfter':{previous:['Succeeded']} if previous else {}}
    def hold(reason):
        return comp({'preparationQualified':False,'consultationOpenable':False,'writeCount':0,
            'realPolicyEffects':False,'reason':reason,'originalSourceIsPreparedRevision':False})
    def guard(checks, yes, no, previous=None):
        return {'type':'If','expression':'@and('+','.join(checks)+')','actions':yes,
            'else':{'actions':no},'runAfter':{previous:['Succeeded']} if previous else {}}
    def eq(a,b): return 'equals('+a+','+b+')'
    a = {}
    read_case = copy.deepcopy(template)
    read_case['inputs']['parameters']['parameters/uri'] = read_case['inputs']['parameters']['parameters/uri'].replace('?$select=Id,CaseUID,linkedDocumentUIDs,sourceBaselineRef,accountableRole,caseStatus','')
    read_case['runAfter'] = {}
    a['Read_prepared_case'] = read_case
    a['Prepared_document_reference'] = comp("@decodeUriComponent(string(body('Read_prepared_case')?['evidenceDraftLink']))", 'Read_prepared_case')
    ref = "outputs('Prepared_document_reference')"
    valid_url = [eq("outputs('Read_prepared_case')?['headers']?['ETag']",c+"?['caseETag']"),
        eq("body('Read_prepared_case')?['CaseUID']",c+"?['CaseUID']"),
        "startsWith("+ref+','+quote(origin+folder+'/')+')', "endsWith(toLower("+ref+"),'.docx')"]
    valid_url += ["not(contains("+ref+','+quote(bad)+'))' for bad in ("'", '..', '?', '#', '%')]
    fileuri = "@concat('_api/web/GetFileByServerRelativePath(decodedurl=',decodeUriComponent('%27'),substring("+ref+','+str(len(origin))+"),decodeUriComponent('%27'),')?$select=UniqueId,ETag,UIVersionLabel,Length,ServerRelativeUrl')"
    file_actions = {'Read_prepared_file_before':http(fileuri)}
    file_checks = ["not(empty("+file+"?['UniqueId']))","not(empty("+file+"?['ETag']))","not(equals("+file+"?['ETag'],'*'))",
        "not(empty("+file+"?['UIVersionLabel']))",eq("concat("+quote(origin)+','+file+"?['ServerRelativeUrl'])",ref),
        eq("uriComponent(string("+file+"?['UIVersionLabel']))","string("+file+"?['UIVersionLabel'])")]
    receipt_name = "concat('PPG-prepared-',toLower("+file+"?['UniqueId']),'-v',"+file+"?['UIVersionLabel'],'.json')"
    receipt_folder = "_api/web/GetFolderByServerRelativePath(decodedurl='"+folder+"')"
    finding = {'Find_prepared_receipt':http('@concat('+quote(receipt_folder+"/Files?$filter=Name eq '")+','+receipt_name+','+quote("'&$select=Name,UniqueId,ETag")+')')}
    item = "@concat('_api/web/GetFileById(',decodeUriComponent('%27'),"+selected+"?['UniqueId'],decodeUriComponent('%27'),')')"
    def by_id(suffix): return item[:-1]+','+quote(suffix)+')'
    work = {'Read_prepared_receipt_before':http(by_id('?$select=UniqueId,ETag'))}
    work['Read_prepared_receipt_content'] = http(by_id('/$value'),'Read_prepared_receipt_before')
    work['Parse_prepared_receipt'] = comp("@if(contains(body('Read_prepared_receipt_content'),'$content'),json(base64ToString(body('Read_prepared_receipt_content')?['$content'])),json(string(body('Read_prepared_receipt_content'))))",'Read_prepared_receipt_content')
    template_uri = "_api/web/GetFileById('"+template_uid+"')?$select=UniqueId,ETag,UIVersionLabel,Length"
    work['Read_prepared_template_before'] = http(template_uri,'Parse_prepared_receipt')
    previous = 'Read_prepared_template_before'
    # Four short expressions validate a complete SHA-256 alphabet without a large
    # nested expression; the hash itself remains the independently checked receipt.
    for index, chars in enumerate(('0123','4567','89ab','cdef')):
        expression = receipt+"?['file']?['SHA256']" if index==0 else "outputs('Prepared_sha_"+str(index-1)+"')"
        for char in chars: expression='replace('+expression+','+quote(char)+",'')"
        name='Prepared_sha_'+str(index);work[name]=comp('@'+expression,previous);previous=name
    for family, value in [('template', receipt+"?['templateSHA256']"), ('input', receipt+"?['inputSHA256']")]:
        for index, chars in enumerate(('0123','4567','89ab','cdef')):
            expression = value if index==0 else "outputs('Prepared_"+family+"_sha_"+str(index-1)+"')"
            for char in chars: expression='replace('+expression+','+quote(char)+",'')"
            name='Prepared_'+family+'_sha_'+str(index);work[name]=comp('@'+expression,previous);previous=name
    work['Read_prepared_file_after'] = http(fileuri,previous)
    work['Read_prepared_receipt_after'] = http(by_id('?$select=UniqueId,ETag'),'Read_prepared_file_after')
    work['Read_prepared_template_after'] = http(template_uri,'Read_prepared_receipt_after')
    final_case=copy.deepcopy(read_case);final_case['runAfter']={'Read_prepared_template_after':['Succeeded']};work['Read_prepared_case_final']=final_case
    request_actions=original['Verify_baseline_boundary']['actions']['Verify_request']['actions']
    source_uri=request_actions['Read_source_before']['inputs']['parameters']['parameters/uri']
    baseline_uri=original['Verify_baseline_boundary']['actions']['Read_baseline_before']['inputs']['parameters']['parameters/uri']
    work['Read_prepared_source_final']=http(source_uri,'Read_prepared_case_final')
    work['Read_prepared_baseline_final']=http(baseline_uri,'Read_prepared_source_final')
    checks=[eq(receipt+"?['kind']","'ppg-prepared-revision-qualification-v1'"),eq(receipt+"?['schemaVersion']",'1'),
        eq(receipt+"?['CaseUID']",c+"?['CaseUID']"),eq(receipt+"?['occurrenceReference']",req+"?['occurrenceReference']"),
        eq(receipt+"?['documentKind']","'fictional-review-draft'"),eq(receipt+"?['generationRoute']","'local-manual-fallback'"),
        eq(receipt+"?['nativeGenerationQualified']",'false'),eq(receipt+"?['preparedArtifactQualified']",'true'),
        "not(empty("+receipt+"?['jobId']))","greater(int("+receipt+"?['outputRevision']),0)",
        eq("length(string("+receipt+"?['file']?['SHA256']))",'64'),"empty(outputs('Prepared_sha_3'))",
        eq(receipt+"?['file']?['DocumentReference']",ref),eq(receipt+"?['file']?['UniqueId']",file+"?['UniqueId']"),
        eq(receipt+"?['file']?['ETag']",file+"?['ETag']"),eq(receipt+"?['file']?['nativeVersion']",file+"?['UIVersionLabel']"),
        eq("int("+receipt+"?['file']?['Length'])","int("+file+"?['Length'])"),
        eq("outputs('Read_prepared_case_final')?['headers']?['ETag']","outputs('Read_prepared_case')?['headers']?['ETag']"),
        eq("body('Read_prepared_case_final')?['evidenceDraftLink']","body('Read_prepared_case')?['evidenceDraftLink']")]
    checks += [eq(receipt+"?['originalSourceScope']?['"+k+"']",c+"?['scope']?['"+k+"']") for k in ('CaseUID','DocumentReference','ReviewedVersionRef','DocumentSHA256')]
    checks += [eq(receipt+"?['caseSnapshot']?['snapshot']?['"+k+"']","body('Read_prepared_case')?['"+k+"']") for k in CASE_INPUT_FIELDS]
    checks += [eq(receipt+"?['checks']?['"+k+"']",'true') for k in ('inputBinding','template','contentControls','wordWebRender','nativeEditReadback','retryPreservation','originalsPreserved')]
    for name, before in [('Read_prepared_file_after','Read_prepared_file_before'),('Read_prepared_receipt_after','Read_prepared_receipt_before'),('Read_prepared_template_after','Read_prepared_template_before')]:
        checks += [eq("body('"+name+"')?['"+k+"']","body('"+before+"')?['"+k+"']") for k in ('UniqueId','ETag')]
    checks += [eq("body('Read_prepared_receipt_before')?['UniqueId']",selected+"?['UniqueId']"),eq("body('Read_prepared_receipt_before')?['ETag']",selected+"?['ETag']")]
    checks += [eq(receipt+"?['template']?['"+k+"']","body('Read_prepared_template_before')?['"+k+"']") for k in ('UniqueId','ETag','UIVersionLabel')]
    checks += [eq("body('Read_prepared_template_before')?['UniqueId']",quote(template_uid)),eq("body('Read_prepared_template_after')?['UniqueId']",quote(template_uid)),
        "not(empty(body('Read_prepared_template_before')?['ETag']))","not(equals(body('Read_prepared_template_before')?['ETag'],'*'))",
        "not(empty(body('Read_prepared_template_before')?['UIVersionLabel']))",
        "not(empty("+receipt+"?['template']?['ETag']))","not(equals("+receipt+"?['template']?['ETag'],'*'))",
        "not(empty("+receipt+"?['template']?['UIVersionLabel']))",
        eq("length(string("+receipt+"?['templateSHA256']))",'64'),"empty(outputs('Prepared_template_sha_3'))",
        eq("length(string("+receipt+"?['inputSHA256']))",'64'),"empty(outputs('Prepared_input_sha_3'))"]
    checks += [eq(receipt+"?['template']?['SHA256']",receipt+"?['templateSHA256']"),eq(receipt+"?['qualificationEvidence']?['preservation']?['output']",receipt+"?['file']?['SHA256']")]
    checks += [eq("body('Read_prepared_source_final')?['"+k+"']",c+"?['sourcePins']?['"+k+"']") for k in ('UniqueId','ETag')]
    checks += [eq("body('Read_prepared_baseline_final')?['UniqueId']",c+"?['baselineUniqueId']"),eq("body('Read_prepared_baseline_final')?['ETag']",c+"?['baselineETag']")]
    draft_scope={'CaseUID':'@'+c+"?['CaseUID']",'DocumentReference':'@'+ref,
        'ReviewedVersionRef':"@concat('sharepoint:',"+file+"?['UniqueId'],':',"+file+"?['ETag'])",'DocumentSHA256':'@'+receipt+"?['file']?['SHA256']"}
    prepared={'CaseUID':'@'+c+"?['CaseUID']",'occurrenceReference':'@'+req+"?['occurrenceReference']",'requestReference':'@'+req+"?['requestReference']",'documentKind':'fictional-review-draft',
        'originalSourceScope':'@'+c+"?['scope']",'scope':draft_scope,'jobId':'@'+receipt+"?['jobId']",'outputRevision':'@'+receipt+"?['outputRevision']",'generationRoute':'local-manual-fallback','nativeGenerationQualified':False,
        'file':'@'+receipt+"?['file']",'template':'@'+receipt+"?['template']",'generatedOutput':'@'+receipt+"?['generatedOutput']",
        'qualificationReceipt':{'UniqueId':"@body('Read_prepared_receipt_after')?['UniqueId']",'ETag':"@body('Read_prepared_receipt_after')?['ETag']",'DocumentReference':'@concat('+quote(origin+folder+'/')+','+receipt_name+')'}}
    ready={'preparationQualified':True,'preparedArtifactQualified':True,'consultationOpenable':True,'writeCount':0,'preparedRevision':prepared,'originalSourceIsPreparedRevision':False,
        'contentReadinessGranted':False,'approvalGranted':False,'publishingAllowed':False,'ordinaryUserAccessQualified':False,'currentCaseETag':"@outputs('Read_prepared_case_final')?['headers']?['ETag']",'realPolicyEffects':False}
    work['Verify_prepared_revision'] = guard(checks,{'Native_prepared_revision':comp(ready)},{'Held_changed_prepared_revision':hold('Prepared file, qualification receipt or case/source/template frame is missing, stale or mismatched; no consultation progression')},'Read_prepared_baseline_final')
    finding['Verify_unique_prepared_receipt'] = guard([eq("length(body('Find_prepared_receipt')?['value'])",'1'),"empty(body('Find_prepared_receipt')?['odata.nextLink'])","empty(body('Find_prepared_receipt')?['@odata.nextLink'])","not(empty("+selected+"?['ETag']))","not(equals("+selected+"?['ETag'],'*'))"],work,{'Held_missing_prepared_receipt':hold('No unique complete qualification receipt exists for the selected native file version; no latest-version or cross-case fallback')},'Find_prepared_receipt')
    file_actions['Verify_prepared_file_identity'] = guard(file_checks,finding,{'Held_invalid_prepared_metadata':hold('Prepared file identity/version could not be verified')},'Read_prepared_file_before')
    a['Verify_prepared_selection'] = guard(valid_url,file_actions,{'Held_no_selected_prepared_draft':hold('Select a qualified same-site DOCX in the existing case evidence link; the original source is not a prepared draft')},'Prepared_document_reference')
    result = {'Check_prepared_ownership':guard([eq(ownership_context+"?['ownershipProjectionVerified']",'true')],a,{'Held_unverified_prepared_ownership':hold('Current ownership/source context is unverified; no prepared-artifact progression')})}
    if 'additionalPreparedArtifactFolder' in binding:
        # Reuse the already-qualified paired folder/receipt-reference transform.
        # Historical callers retain their own independently verified source and
        # case continuity gates; no static-source assertion is manufactured here.
        from build_operator_entry import _flatten
        from build_multisource_case_context import (digest, _preparation_folder_fragments,
            _bind_preparation_receipt_reference, _check_preparation_folders)
        nodes = _flatten(result)
        selection = nodes['Verify_prepared_selection']['expression']
        lookup = nodes['Find_prepared_receipt']['inputs']['parameters']['parameters/uri']
        folders = {'originalFolder': folder,
                   'additionalFolder': binding['additionalPreparedArtifactFolder'],
                   'selectionGuardSHA256': digest(selection), 'receiptLookupSHA256': digest(lookup)}
        fragments = _preparation_folder_fragments(dataset, None, folders, by_document_reference=True)
        if any(value.count(old) != 1 for value, (old, _) in zip((selection, lookup), fragments)):
            raise ValueError('Exact paired original preparation-folder guards required')
        nodes['Verify_prepared_selection']['expression'] = selection.replace(*fragments[0])
        nodes['Find_prepared_receipt']['inputs']['parameters']['parameters/uri'] = lookup.replace(*fragments[1])
        _bind_preparation_receipt_reference(nodes, folders, fragments)
        _check_preparation_folders(nodes, dataset, None, folders, by_document_reference=True)
    return result
