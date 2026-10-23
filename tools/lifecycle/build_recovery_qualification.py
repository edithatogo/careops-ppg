"""Build a standard-SharePoint LC02 qualification profile; no native I/O.

Legacy bindings retain their exact fixed fixture and after-proof fault behavior.
For a new isolated fixture, bind isolatedFixture=true, referenceFlowName and
approvedReferenceDefinitionSHA256 to a stopped serial reference. Control/journal/
proof/commit filenames use the new requestId, preserving historical artifacts.
preproof_fault stops after Conditional_case_write and before any after observation
or proof. Recompose the same isolated binding without that fault for native replay;
a changed case token skips mutation and missing after-proof remains a hold.
The existing read-only classifier can reconcile actual retained LC02 evidence;
this builder grants no automatic recovery or permission to resubmit.
"""
import argparse,json,hashlib,re
from pathlib import Path

def build(expected,reference,source_text,inject_failure,binding,*,preproof_fault=False):
    isolated=binding.get('isolatedFixture') is True
    if preproof_fault and (not isolated or inject_failure):
        raise ValueError('Pre-proof stop requires one isolated fixture and no second fault point')
    if isolated:
        pin=hashlib.sha256(json.dumps(reference['properties']['definition'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        trigger=reference['properties']['definition'].get('triggers',{}).get('manual',{})
        if (reference['properties'].get('state')!='Stopped'
            or trigger.get('type')!='Request' or trigger.get('kind')!='Button'
            or trigger.get('runtimeConfiguration',{}).get('concurrency',{}).get('runs')!=1
            or not isinstance(inject_failure,bool) or not isinstance(preproof_fault,bool)
            or not binding.get('referenceFlowName') or reference.get('name')!=binding['referenceFlowName']
            or pin!=binding.get('approvedReferenceDefinitionSHA256')
            or not re.fullmatch(r'LC-FICTIONAL-[A-Za-z0-9_-]{1,100}',str(expected.get('CaseUID','')))
            or not re.fullmatch(r'LC02-RECOVERY-[A-Za-z0-9_-]{1,60}',str(expected.get('requestId','')))
            or expected.get('CaseUID')=='LC-FICTIONAL-20261017-01'
            or expected.get('requestId')=='LC02-RECOVERY-20261018-01'
            or not isinstance(expected.get('before'),dict)
            or expected['before'].get('CaseUID')!=expected['CaseUID']
            or 'nextAction' not in expected['before']
            or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',str(expected.get('sourceUniqueId','')))
            or not isinstance(expected.get('sourceETag'),str) or expected['sourceETag'] in ('','*')
            or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',key) for key in expected['before'])
            or not isinstance(expected.get('desiredNextAction'),str)
            or not expected['desiredNextAction'].startswith('FICTIONAL')
            or expected['desiredNextAction']==expected['before'].get('nextAction')
            or hashlib.sha256(source_text.encode()).hexdigest()!=expected.get('sourceSHA256')):
            raise ValueError('Exact stopped reference and distinct, fully bound fictional fixture required')

    if (binding.get('qualificationOnly') is not True
        or expected != binding.get('expectedRequest')
        or (not isolated and expected.get('CaseUID')!='LC-FICTIONAL-20261017-01')
        or (not isolated and expected.get('requestId')!='LC02-RECOVERY-20261018-01')
        or expected.get('caseItemId')!=binding.get('caseItemId')
        or expected.get('sourceUniqueId')!=binding.get('sourceUniqueId')
        or expected.get('expectedCaseETag') in (None,'','*')):
        raise ValueError('Only the explicitly bound fictional qualification contract is supported')
    from urllib.parse import urlsplit
    site=reference['properties']['definition']['actions']['Read_case']['inputs']['parameters']['dataset']
    if urlsplit(site).scheme!='https' or not urlsplit(site).hostname.endswith('.sharepoint.com'):
        raise ValueError('Expected an already qualified SharePoint reference flow')
    if site!=binding.get('siteUrl'):
        raise ValueError('Reference site differs from the private qualification binding')
    folder=urlsplit(site).path+'/PPG Review Evidence/Templates'
    caseuri=binding['caseUri']
    reference_case=reference['properties']['definition']['actions']['Read_case']['inputs']['parameters']['parameters/uri']
    matches_reference=(caseuri==reference_case)
    if isolated:
        matches_reference=(caseuri.rsplit('/items(',1)[0]==reference_case.rsplit('/items(',1)[0]
            and re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F-]{36}'\)/items\([1-9][0-9]*\)",caseuri) is not None)
    if (not matches_reference or not caseuri.endswith('/items('+str(binding['caseItemId'])+')')):
        raise ValueError('Reference case differs from the private qualification binding')
    fields=list(expected['before'])
    headers={'Accept':'application/json;odata=nometadata','Content-Type':'application/json;odata=nometadata'}
    def http(uri,after=None,method='GET',body=None,extra=None):
        params={'dataset':site,'parameters/method':method,'parameters/uri':uri,'parameters/headers':dict(headers,**(extra or {}))}
        if body is not None:params['parameters/body']=body
        result={'type':'OpenApiConnection','inputs':{'host':{'apiId':'/providers/Microsoft.PowerApps/apis/shared_sharepointonline','connectionName':'shared_sharepointonline','operationId':'HttpRequest'},'parameters':params},'runAfter':after or {}}
        if isolated and method!='GET':result['inputs']['retryPolicy']={'type':'none'}
        return result
    def comp(v,after=None):return {'type':'Compose','inputs':v,'runAfter':after or {}}
    def iff(expr,yes,no,after=None):return {'type':'If','expression':expr,'actions':yes,'else':{'actions':no},'runAfter':after or {}}
    def fail(code):return {'type':'Terminate','inputs':{'runStatus':'Failed','runError':{'code':code,'message':'Fictional LC02 qualification held; inspect retained native evidence'}},'runAfter':{}}
    def fileuri(name):return f"_api/web/GetFileByServerRelativePath(decodedurl='{folder}/{name}')/$value"
    def listfile(name):return f"_api/web/GetFolderByServerRelativePath(decodedurl='{folder}')/Files?$filter=Name eq '{name}'&$select=Name"
    def writefile(name,body,after):return http(f"_api/web/GetFolderByServerRelativePath(decodedurl='{folder}')/Files/add(overwrite=false,url='{name}')",after,'POST',body)
    def parse(name):return f"@if(contains(body('{name}'),'$content'),json(base64ToString(body('{name}')?['$content'])),json(string(body('{name}'))))"
    def project(action):return {k:f"@body('{action}')?['{k}']" for k in fields}
    def etag(action):return f"outputs('{action}')?['headers']?['ETag']"
    prefix=expected['requestId'] if isolated else 'LC02-recovery'
    journal=prefix+'-prepared.json';proof=prefix+'-after-proof.json';commit=prefix+'-committed.json'
    a={'Expected_request':comp(expected),'Read_control':http(fileuri(prefix+'-control.json'),{'Expected_request':['Succeeded']}),'Request':comp(parse('Read_control'),{'Read_control':['Succeeded']})}
    x={'Read_source':http(f"_api/web/GetFileById('{expected['sourceUniqueId']}')/$value"),'Read_source_pin':http(f"_api/web/GetFileById('{expected['sourceUniqueId']}')?$select=ETag,UniqueId",{'Read_source':['Succeeded']}),'Read_case':http(caseuri,{'Read_source_pin':['Succeeded']}),'Observed_before':comp(project('Read_case'),{'Read_case':['Succeeded']})}
    source="if(contains(body('Read_source'),'$content'),base64ToString(body('Read_source')?['$content']),string(body('Read_source')))"
    guard="@and(equals(body('Read_source_pin')?['ETag'],outputs('Expected_request')?['sourceETag']),equals("+source+",'"+source_text.replace("'","''")+"'),equals(body('Read_case')?['CaseUID'],outputs('Request')?['CaseUID']))"
    work={'Find_commit':http(listfile(commit))}
    replay={'Read_commit':http(fileuri(commit)),'Committed':comp(parse('Read_commit'),{'Read_commit':['Succeeded']})}
    replay['Verify_committed']=iff("@and(equals(string(outputs('Committed')?['request']),string(outputs('Request'))),equals(outputs('Committed')?['afterProof']?['caseETag'],"+etag('Read_case')+"),equals(string(outputs('Committed')?['afterProof']?['case']),string(outputs('Observed_before'))))",{'Native_replay_result':comp("@outputs('Committed')")},{'Refuse_changed_replay':fail('ChangedReplay')},{'Committed':['Succeeded']})
    pending={'Find_journal':http(listfile(journal))}
    prepared={'kind':'prepared-fictional-transition','request':"@outputs('Request')",'before':"@outputs('Observed_before')",'beforeETag':'@'+etag('Read_case'),'preparedByRun':"@workflow()?['run']?['name']",'preparedAtUtc':'@utcNow()'}
    # A new journal may only be written against the complete expected before state.
    beforeexpr="@and(equals("+etag('Read_case')+",outputs('Expected_request')?['expectedCaseETag']),equals(string(outputs('Observed_before')),string(outputs('Expected_request')?['before'])))"
    pending['Ensure_journal']=iff("@equals(length(body('Find_journal')?['value']),0)",{'Verify_new_journal_scope':iff(beforeexpr,{'Prepared':comp(prepared),'Write_journal':writefile(journal,"@string(outputs('Prepared'))",{'Prepared':['Succeeded']})},{'Refuse_initial_stale':fail('StaleBeforeJournal')})},{},{'Find_journal':['Succeeded']})
    pending['Read_journal']=http(fileuri(journal),{'Ensure_journal':['Succeeded']});pending['Journal']=comp(parse('Read_journal'),{'Read_journal':['Succeeded']})
    mutate={'Conditional_case_write':http(caseuri,method='POST',body=json.dumps({'nextAction':expected['desiredNextAction']}),extra={'IF-MATCH':expected['expectedCaseETag'],'X-HTTP-Method':'MERGE'}),'Read_after_write':http(caseuri,{'Conditional_case_write':['Succeeded']}),'After_projection':comp(project('Read_after_write'),{'Read_after_write':['Succeeded']})}
    if preproof_fault:
        mutate['Preproof_intentional_stop']=fail('InjectedAfterCaseWriteBeforeAfterProof')
        mutate['Preproof_intentional_stop']['runAfter']={'Conditional_case_write':['Succeeded']}
        mutate['Read_after_write']['runAfter']={'Preproof_intentional_stop':['Succeeded']}
    desired=dict(expected['before'],nextAction=expected['desiredNextAction'])
    proofbody={'kind':'native-after-proof','request':"@outputs('Request')",'case':"@outputs('After_projection')",'caseETag':'@'+etag('Read_after_write'),'writeRunId':"@workflow()?['run']?['name']",'observedAtUtc':'@utcNow()','realPolicyEffects':False}
    mutate['Verify_after_write']=iff("@and(equals(string(outputs('After_projection')),string(json('"+json.dumps(desired,separators=(',',':')).replace("'","''")+"'))),not(equals("+etag('Read_after_write')+",outputs('Journal')?['beforeETag'])))",{'After_proof_to_store':comp(proofbody),'Write_after_proof':writefile(proof,"@string(outputs('After_proof_to_store'))",{'After_proof_to_store':['Succeeded']}),'Fault_probe':iff('@'+str(inject_failure).lower(),{'Intentional_failure':fail('InjectedAfterWriteBeforeCommit')},{},{'Write_after_proof':['Succeeded']})},{'Refuse_after_mismatch':fail('AfterWriteMismatch')},{'After_projection':['Succeeded']})
    recover={'Mutate_only_before':iff(beforeexpr,mutate,{}),'Read_after_proof':http(fileuri(proof),{'Mutate_only_before':['Succeeded']}),'After_proof':comp(parse('Read_after_proof'),{'Read_after_proof':['Succeeded']}),'Read_recovery_case':http(caseuri,{'After_proof':['Succeeded']}),'Recovery_projection':comp(project('Read_recovery_case'),{'Read_recovery_case':['Succeeded']})}
    result={'kind':'committed-fictional-transition','request':"@outputs('Request')",'afterProof':"@outputs('After_proof')",'originalWriteRunId':"@outputs('After_proof')?['writeRunId']",'committedByRun':"@workflow()?['run']?['name']",'caseWritesThisRun':"@if(equals("+etag('Read_case')+",outputs('Journal')?['beforeETag']),1,0)",'committedAtUtc':'@utcNow()','realPolicyEffects':False,'actorAuthorityQualified':False}
    recover['Verify_recovery']=iff("@and(equals(string(outputs('After_proof')?['request']),string(outputs('Request'))),equals(outputs('After_proof')?['caseETag'],"+etag('Read_recovery_case')+"),equals(string(outputs('After_proof')?['case']),string(outputs('Recovery_projection'))))",{'Result':comp(result),'Commit_receipt':writefile(commit,"@string(outputs('Result'))",{'Result':['Succeeded']}),'Native_result':comp("@outputs('Result')",{'Commit_receipt':['Succeeded']})},{'Refuse_recovery_drift':fail('RecoveryStateChanged')},{'Recovery_projection':['Succeeded']})
    jguard="@and(equals(string(outputs('Journal')?['request']),string(outputs('Request'))),equals(outputs('Journal')?['beforeETag'],outputs('Expected_request')?['expectedCaseETag']),equals(string(outputs('Journal')?['before']),string(outputs('Expected_request')?['before'])))"
    pending['Journal_guard']=iff(jguard,recover,{'Refuse_journal':fail('JournalConflict')},{'Journal':['Succeeded']})
    work['Committed_or_pending']=iff("@equals(length(body('Find_commit')?['value']),1)",replay,pending,{'Find_commit':['Succeeded']})
    x['Source_guard']=iff(guard,work,{'Refuse_source':fail('SourceChanged')},{'Observed_before':['Succeeded']})
    a['Request_guard']=iff("@equals(string(outputs('Request')),string(outputs('Expected_request')))",x,{'Refuse_changed_request':fail('ChangedRequestIdentity')},{'Request':['Succeeded']})
    definition=dict(reference['properties']['definition']);definition['actions']=a
    # Retain the existing manually invoked serial trigger, never add recurrence.
    assert list(definition['triggers'])==['manual']
    refs={'shared_sharepointonline':reference['properties']['connectionReferences']['shared_sharepointonline']}
    result={'properties':{'displayName':'PPG Lifecycle | FICTIONAL request recovery qualification','definition':definition,'connectionReferences':refs}}
    if isolated:
        from build_selected_event_routes import audit_actions
        result['properties']['state']='Stopped'
        geometry=audit_actions(definition)
        if geometry['actionCount']>500:raise ValueError('Isolated recovery profile exceeds native action limit')
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--request',required=True);ap.add_argument('--binding',required=True);ap.add_argument('--reference-flow',required=True);ap.add_argument('--source-text',required=True);ap.add_argument('--output',required=True);ap.add_argument('--inject-failure',action='store_true');ap.add_argument('--preproof-fault',action='store_true');args=ap.parse_args()
    binding_data=json.loads(Path(args.binding).read_text())
    source_data=(Path(args.source_text).read_bytes().decode('utf-8') if binding_data.get('isolatedFixture') is True else Path(args.source_text).read_text())
    result=build(json.loads(Path(args.request).read_text()),json.loads(Path(args.reference_flow).read_text()),source_data,args.inject_failure,binding_data,preproof_fault=args.preproof_fault)
    if binding_data.get('isolatedFixture') is True:
        with Path(args.output).open('x') as output:output.write(json.dumps(result,indent=2)+'\n')
    else:Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
