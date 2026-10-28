"""Assemble the existing publication flow locally; no deployment or native I/O.

Two explicit phases: body-free absent-only copy; separately verified binary-proof
receipt then one immutable event. Both re-read the producer's current purpose,
prepared/readiness/history frame. No saved eligibility receipt is trusted.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lifecycle'))
from build_selected_event_routes import audit_actions
from binary_publication import digest, require

CODES = ('committee', 'officer', 'coordinator', 'authorisation')
READERS = ('Resolve_context', 'Route_preparation_check', 'Route_readiness_check')


def build(purpose, target, binding, producer_evidence=None):
    source = purpose['properties']['definition']; old = target['properties']['definition']
    require(binding.get('qualificationOnly') is True and target['properties'].get('state') == 'Stopped', 'Stopped qualification target required')
    require(digest(source) == binding.get('approvedPurposeDefinitionSHA256')
            and digest(old) == binding.get('approvedTargetDefinitionSHA256'), 'Reviewed exact source/target definitions required')
    module = Path(__file__).resolve().parents[1] / 'lifecycle/build_prepared_purpose_events.py'
    require(hashlib.sha256(module.read_bytes()).hexdigest() == binding.get('approvedPurposeModuleSHA256'), 'Reviewed purpose producer source required')
    refs = target['properties']['connectionReferences']
    require(refs == purpose['properties']['connectionReferences'] and set(refs) == {'shared_sharepointonline'}, 'Unchanged qualified SharePoint-only references required')
    require(binding.get('eventUIDUnique') is True, 'Observed native EventUID uniqueness required')
    profile = binding['fictionalRouteProfile']; profile_hash = digest(profile)
    require(set(profile) == {'reference', 'version', 'FictionalTest', 'grantsRealAuthority'}
            and profile['FictionalTest'] is True and profile['grantsRealAuthority'] is False, 'Fictional-only exact route profile required')
    base_work = copy.deepcopy(source['actions']['Check_purpose_prerequisites']['actions'])
    profiles = base_work['Purpose_profile']['inputs']
    require(len(profiles) == 4 and tuple(r['code'] for r in profiles) == CODES, 'Exact four-purpose producer contract required')
    require(all(r['DecisionReference'] == profile['reference'] + '/' + profile['version'] + '/' + profile_hash + '/' + r['code']
                for r in profiles), 'Full route/version/profile hash/purpose binding required')
    before_guard = base_work.pop('Verify_purpose_before')
    a = {name: copy.deepcopy(source['actions'][name]) for name in READERS}
    a['Resolve_context']['runAfter'] = {'Validate_publication_input': ['Succeeded']}
    template = a['Resolve_context']['actions']['Read_selected_case']
    host = template['inputs']['host']; site = template['inputs']['parameters']['dataset']; parsed = urlsplit(site)
    origin = parsed.scheme + '://' + parsed.netloc
    require(parsed.scheme == 'https' and parsed.netloc, 'Existing HTTPS site required')
    folder = binding['qualificationFolder']
    require(isinstance(folder, str) and folder.startswith(parsed.path + '/')
            and all(x not in folder for x in ('..', '%', '?', '#', '\\')), 'Canonical isolated same-site folder required')
    assurance_uri = binding['assuranceCollectionUri']
    require(re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F-]{36}'\)/items", assurance_uri), 'Complete literal assurance collection required')
    require(base_work['Purpose_before_assurance']['inputs']['parameters']['parameters/uri'] == assurance_uri + '?$top=5000',
            'Retain exact producer full-history reader')

    def quote(v): return "'" + v.replace("'", "''") + "'"
    def eq(x,y): return 'equals('+x+','+y+')'
    def allof(checks): return 'and('+','.join(checks)+')'
    def present(x): return "not(empty(trim(string(coalesce("+x+",'')))))"
    def comp(v, prev=None): return {'type':'Compose','inputs':v,'runAfter':{prev:['Succeeded']} if prev else {}}
    def http(uri, prev=None, method='GET', body=None):
        v = copy.deepcopy(template); q = v['inputs']['parameters']
        q.update({'parameters/uri':uri,'parameters/method':method,'parameters/headers':{'Accept':'application/json;odata=minimalmetadata'}})
        q.pop('parameters/body',None);v['runAfter']={prev:['Succeeded']} if prev else {}
        if method=='POST':
            v['inputs']['retryPolicy']={'type':'none'}
            if body is not None:q['parameters/body']=body;q['parameters/headers']['Content-Type']='application/json;odata=nometadata'
        return v
    def complete(name):
        return ["empty(body('" + name + "')?['" + marker + "'])"
                for marker in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink')]
    def query(from_, where, prev): return {'type':'Query','inputs':{'from':from_,'where':'@'+where},'runAfter':{prev:['Succeeded']}}
    def stable(from_,prev): return {'type':'Select','inputs':{'from':from_,'select':"@union(item(),json('{\"odata.id\":null}'))"},'runAfter':{prev:['Succeeded']}}
    held={'qualified':False,'copyCreatedCount':0,'publicationCreatedCount':0,'caseWrites':0,'sourceWrites':0,
          'readinessWrites':0,'purposeWrites':0,'notifications':0,'realPolicyEffects':False,'actorAuthorityQualified':False}
    def stop(reason, prev=None, *, unknown=False):
        name='Held_'+reason
        return {'type':'If','expression':'@false','actions':{},'else':{'actions':{
            name:comp({**held,'copyCreatedCount':None if unknown else 0,'publicationCreatedCount':None if unknown else 0,
                       'reason':reason,'reconcileBeforeRetry':unknown}),
            'Stop_'+reason:{'type':'Terminate','runAfter':{name:['Succeeded']},'inputs':{'runStatus':'Succeeded'}}}},
            'runAfter':{prev:['Succeeded']} if prev else {}}
    def gate(name, checks, prev):
        v=stop(name,prev);v['expression']='@'+allof(checks);return v
    def bounded_gate(container,name,checks,prev):
        # No I/O between bounded evaluations and their final gate.
        chunks=[];chunk=[]
        for check in checks:
            if len('@'+allof(chunk+[check]))>6000:
                require(bool(chunk),'Single publication condition too long');chunks.append(chunk);chunk=[]
            chunk.append(check)
        if chunk:chunks.append(chunk)
        for i,chunk in enumerate(chunks):
            step=name+'_check_'+str(i);container[step]=comp('@'+allof(chunk),prev);prev=step
        container[name]=gate(name,[eq("outputs('"+name+'_check_'+str(i)+"')",'true') for i in range(len(chunks))],prev)
        return name
    def inspect_get(group):
        for value in group.values():
            require(value['type'] in ('If','Scope','Compose','OpenApiConnection','Query','Select','Terminate'), 'Unsupported prerequisite action')
            if value['type']=='OpenApiConnection':
                h=value['inputs']['host'];p=value['inputs']['parameters']
                require(h==host and p.get('dataset')==site and p.get('parameters/method')=='GET'
                        and 'parameters/body' not in p and not any(k.lower() in ('x-http-method','x-http-method-override') for k in p.get('parameters/headers',{})),
                        'Only exact same-connection GET prerequisites can be reused')
            inspect_get(value.get('actions',{}));inspect_get(value.get('else',{}).get('actions',{}))
    inspect_get(a);inspect_get(base_work)
    # Fixed selection from the producer's own immutable profile; no caller asserts approval.
    base_work['Select_purpose']['inputs']['where']="@equals(item()?['label'],'Final authorisation')"
    first=next(iter(base_work));base_work[first]['runAfter']={'Publication_uid':['Succeeded']}
    p="outputs('Native_prepared_revision')?['preparedRevision']";file=p+"?['file']";scope=p+"?['scope']"
    ready="outputs('Native_readiness_observation')"
    modes=['Prepare binary copy','Record publication']
    valid=["contains(createArray('Prepare binary copy','Record publication'),triggerBody()?['text'])"]
    for key in ('text','text_6'):
        value="triggerBody()?['"+key+"']";valid += [eq(value,"string(coalesce("+value+",''))"),present(value),'lessOrEquals(length(string('+value+')),128)']
    a={'Validate_publication_input':gate('invalid_input',valid,None),**a}
    prereq=[eq(ready+"?['readinessEvidenceConsistent']",'true'),eq(ready+"?['nativeContextRevalidated']",'true'),
            eq(ready+"?['technicalConsultationCoverageComplete']",'true'),eq("outputs('Native_prepared_revision')?['consultationOpenable']",'true')]
    a['Verify_runtime_prerequisites']=gate('unqualified_runtime_frame',prereq,'Route_readiness_check')
    a['Verify_runtime_prerequisites']['runAfter']={'Route_readiness_check':['Succeeded','Failed','TimedOut']}
    a['Publication_uid']=comp("@concat('LC04-PUBLICATION-',outputs('Parse_baseline')?['request']?['requestReference'],'-',toLower("+file+"?['UniqueId']),'-v',"+file+"?['nativeVersion'])",'Verify_runtime_prerequisites')
    # The producer intentionally rejects later-stage rows. Allow only this event's
    # deterministic identity through its scope filter, then validate that event fully.
    old_where=base_work['Purpose_before_scope']['inputs']['where']
    require(old_where.startswith('@and('),'Reviewed scope predicate shape required')
    base_work['Purpose_before_scope']['inputs']['where']='@and('+old_where[1:]+",not(equals(item()?['EventUID'],outputs('Publication_uid'))))"
    a.update(base_work)
    initial_checks=[before_guard['expression'][1:]]+["equals(length(body('Purpose_before_rows_"+code+"')),1)" for code in CODES]
    initial_checks += [eq("outputs('Purpose_before_valid_"+code+"')",'true') for code in CODES]
    initial_checks += [eq("uriComponent(string("+file+"?['nativeVersion']))",file+"?['nativeVersion']"),"lessOrEquals(length(outputs('Publication_uid')),255)"]
    a['Find_publication_before_copy']=query("@body('Purpose_before_assurance')?['value']","equals(item()?['EventUID'],outputs('Publication_uid'))",'Purpose_before_selected')
    a['Find_corrections_before_copy']=query("@body('Purpose_before_assurance')?['value']","equals(item()?['SupersedesEventUID'],outputs('Publication_uid'))",'Find_publication_before_copy')
    initial_checks += ["lessOrEquals(length(body('Find_publication_before_copy')),1)","equals(length(body('Find_corrections_before_copy')),0)",
        "or(equals(triggerBody()?['text'],'Record publication'),equals(length(body('Find_publication_before_copy')),0))"]
    # Existing publication is never a reason to recreate a missing target; only
    # the Record phase can validate that immutable event as an exact zero-write retry.
    last=bounded_gate(a,'Verify_all_retained_purposes',initial_checks,'Find_corrections_before_copy')
    a['Issued_path']=comp("@concat("+quote(folder+'/FICTIONAL-issued-')+",toLower("+file+"?['UniqueId']),'-v',"+file+"?['nativeVersion'],'.docx')",last)
    files_uri="_api/web/GetFolderByServerRelativePath(decodedurl="+quote(folder)+')/Files'
    a['Find_issued']=http("@concat("+quote(files_uri+"?$filter=Name eq '")+",last(split(outputs('Issued_path'),'/')),"+quote("'&$select=Name,UniqueId,ETag,UIVersionLabel,Length,ServerRelativeUrl")+')','Issued_path')
    a['Verify_target_cardinality']=gate('ambiguous_target',complete('Find_issued')+["lessOrEquals(length(body('Find_issued')?['value']),1)"],'Find_issued')
    source_uri="@concat('_api/web/GetFileById(',decodeUriComponent('%27'),"+file+"?['UniqueId'],decodeUriComponent('%27'),')/copyTo(strNewUrl=',decodeUriComponent('%27'),outputs('Issued_path'),decodeUriComponent('%27'),',bOverWrite=false)')"
    a['Copy_if_absent']={'type':'If','expression':"@and(equals(triggerBody()?['text'],'Prepare binary copy'),equals(length(body('Find_issued')?['value']),0))",'runAfter':{'Verify_target_cardinality':['Succeeded']},'actions':{'Copy_binary_absent_only':http(source_uri,method='POST')},'else':{'actions':{}}}
    issued_uri="@concat('_api/web/GetFileByServerRelativePath(decodedurl=',decodeUriComponent('%27'),outputs('Issued_path'),decodeUriComponent('%27'),')?$select=UniqueId,ETag,UIVersionLabel,Length,ServerRelativeUrl')"
    a['Read_issued']=http(issued_uri,'Copy_if_absent')
    issued="body('Read_issued')"
    target_checks=[present(issued+"?['UniqueId']"),present(issued+"?['ETag']"),"not(equals("+issued+"?['ETag'],'*'))",present(issued+"?['UIVersionLabel']"),
                   eq(issued+"?['ServerRelativeUrl']","outputs('Issued_path')"),'not('+eq(issued+"?['UniqueId']",file+"?['UniqueId']")+')',
                   eq('string('+issued+"?['Length'])",'string('+file+"?['Length'])")]
    a['Verify_issued_metadata']=gate('issued_metadata_mismatch',target_checks,'Read_issued')
    a['Verify_issued_metadata']['else']['actions']['Held_issued_metadata_mismatch']['inputs'].update(
        copyCreatedCount=None,reconcileBeforeRetry=True)

    constants={'Purpose_uid_'+code for code in CODES}|{'Purpose_profile','Select_purpose','Chosen_purpose'}
    frame={name:copy.deepcopy(action) for name,action in base_work.items() if name not in constants}
    def rename(value,names):
        if isinstance(value,dict):return {names.get(k,k):rename(v,names) for k,v in value.items()}
        if isinstance(value,list):return [rename(v,names) for v in value]
        if isinstance(value,str):
            for old,new in names.items():
                for function in ('body','outputs','actions'):
                    value=value.replace(function+"('"+old+"')",function+"('"+new+"')")
        return value
    def recheck(prefix,previous):
        names={name:prefix+'_'+name for name in frame};out=rename(frame,names);first_name=names[next(iter(frame))]
        out[first_name]['runAfter']={previous:['Succeeded']}
        # Include issued/proof metadata immediately before complete assurance history.
        history=names['Purpose_before_assurance'];prior=next(iter(out[history]['runAfter']))
        out[prefix+'_issued']=http(issued_uri,prior)
        extra=[eq("body('"+prefix+"_issued')?['"+k+"']",issued+"?['"+k+"']") for k in ('UniqueId','ETag','UIVersionLabel','Length','ServerRelativeUrl')]
        out[history]['runAfter']={prefix+'_issued':['Succeeded']}
        if prefix!='Copy_after':
            out[prefix+'_proof']=http("@concat('_api/web/GetFileById(',decodeUriComponent('%27'),body('Read_binary_proof_before')?['UniqueId'],decodeUriComponent('%27'),')?$select=UniqueId,ETag')",prefix+'_issued')
            out[history]['runAfter']={prefix+'_proof':['Succeeded']}
            extra += [eq("body('"+prefix+"_proof')?['"+k+"']","body('Read_binary_proof_before')?['"+k+"']") for k in ('UniqueId','ETag')]
        checks=rename(initial_checks,names)+extra
        return out,checks,names['Purpose_before_selected'],names['Purpose_before_assurance']

    # Copy phase always stops short of publication, including an already-existing target.
    cp,checks,last,_=recheck('Copy_after',None);cp[next(iter(cp))]['runAfter']={}
    bounded_gate(cp,'Verify_copy_frame',checks,last)
    cp['Verify_copy_frame']['else']['actions']['Held_Verify_copy_frame']['inputs'].update(
        copyCreatedCount=None,publicationCreatedCount=0,reconcileBeforeRetry=True)
    cp['Native_binary_copy_observation']=comp({**held,'copyCreatedCount':"@if(equals(length(body('Find_issued')?['value']),0),1,0)",
        'issued':'@'+issued,'preparedScope':'@'+scope,'purposeAuthorisation':"@first(body('Purpose_before_rows_authorisation'))",
        'binaryOutputQualified':False,'reason':'Download source and issued bytes independently; reconcile existing target or uncertain copy before any publication event',
        'runId':"@workflow()?['run']?['name']"},'Verify_copy_frame')
    a['Observe_copy_phase']={'type':'If','expression':"@equals(triggerBody()?['text'],'Prepare binary copy')",'actions':cp,'else':{'actions':{}},'runAfter':{'Verify_issued_metadata':['Succeeded']}}
    a['Stop_copy_phase']={'type':'If','expression':"@equals(triggerBody()?['text'],'Prepare binary copy')",'actions':{'Copy_phase_finished':{'type':'Terminate','inputs':{'runStatus':'Succeeded'},'runAfter':{}}},'else':{'actions':{}},'runAfter':{'Observe_copy_phase':['Succeeded']}}

    # A writable library JSON plus a matching hash assertion is not a trusted
    # producer. This concrete candidate keeps Record closed until the actual
    # independently produced proof and producer evidence have been reviewed/pinned.
    trusted=binding.get('reviewedBinaryProof')
    if trusted is not None:
        require(set(trusted)=={'receipt','content','producerEvidenceSHA256'},'Exact reviewed binary proof contract required')
        require(re.fullmatch('[0-9a-f]{64}',trusted['producerEvidenceSHA256']) is not None,
                'Independent producer/storage qualification evidence digest required')
        require(isinstance(producer_evidence,bytes)
                and hashlib.sha256(producer_evidence).hexdigest()==trusted['producerEvidenceSHA256'],
                'Actual separately reviewed producer evidence bytes required; a digest assertion alone is insufficient')
        evidence=json.loads(producer_evidence)
        require(evidence.get('kind')=='independent-binary-publication-producer-qualification-v1'
                and evidence.get('copyFlowName')==target.get('name') and bool(target.get('name'))
                and isinstance(evidence.get('copyRunId'),str) and bool(evidence['copyRunId'])
                and evidence.get('proofContentSHA256')==digest(trusted['content'])
                and evidence.get('proofReceipt')==trusted['receipt'],
                'Exact copy run, producer evidence and native proof receipt/content relation required')
        require(all(isinstance(trusted['receipt'].get(k),str) and trusted['receipt'][k].strip()
                    for k in ('UniqueId','ETag','DocumentReference')) and trusted['receipt']['ETag']!='*',
                'Actual immutable native proof receipt pins required')
        require(trusted['content'].get('kind')=='local-downloaded-binary-parity-v1'
                and isinstance(trusted['content'].get('downloadEvidence'),dict)
                and set(trusted['content']['downloadEvidence'])=={'source','issued','producer'},
                'Reviewed actual independent download and producer evidence required')
    a['Verify_record_producer_trust']=gate('unqualified_independent_binary_proof_producer',
        ['true' if trusted else 'false'],'Stop_copy_phase')
    a['Binary_proof_path']=comp("@concat("+quote(folder+'/PPG-binary-proof-')+",toLower("+issued+"?['UniqueId']),'-v',"+issued+"?['UIVersionLabel'],'.json')",'Verify_record_producer_trust')
    proof_uri="@concat('_api/web/GetFileByServerRelativePath(decodedurl=',decodeUriComponent('%27'),outputs('Binary_proof_path'),decodeUriComponent('%27'),')')"
    a['Read_binary_proof_before']=http(proof_uri[:-1]+",'?$select=UniqueId,ETag,Length,ServerRelativeUrl')",'Binary_proof_path')
    a['Verify_proof_metadata']=gate('missing_binary_proof',[present("body('Read_binary_proof_before')?['UniqueId']"),present("body('Read_binary_proof_before')?['ETag']"),"not(equals(body('Read_binary_proof_before')?['ETag'],'*'))","greater(int(body('Read_binary_proof_before')?['Length']),0)","lessOrEquals(int(body('Read_binary_proof_before')?['Length']),65536)"],'Read_binary_proof_before')
    a['Read_binary_proof_content']=http(proof_uri[:-1]+",'/$value')",'Verify_proof_metadata')
    a['Parse_binary_proof']=comp("@if(contains(body('Read_binary_proof_content'),'$content'),json(base64ToString(body('Read_binary_proof_content')?['$content'])),json(string(body('Read_binary_proof_content'))))",'Read_binary_proof_content')
    proof="outputs('Parse_binary_proof')"
    proof_checks=[eq(proof+"?['kind']","'local-downloaded-binary-parity-v1'"),eq(proof+"?['independentByteParity']",'true'),eq(proof+"?['publicationEventCreated']",'false')]
    proof_checks += [eq(proof+"?['scope']?['"+k+"']",scope+"?['"+k+"']") for k in ('CaseUID','DocumentReference','ReviewedVersionRef','DocumentSHA256')]
    for k in ('UniqueId','ETag','nativeVersion','Length','DocumentReference'):proof_checks.append(eq(proof+"?['source']?['"+k+"']",file+"?['"+k+"']"))
    for k,native in [('UniqueId','UniqueId'),('ETag','ETag'),('nativeVersion','UIVersionLabel')]:proof_checks.append(eq(proof+"?['issued']?['"+k+"']",issued+"?['"+native+"']"))
    proof_checks += [eq('string('+proof+"?['issued']?['Length'])",'string('+issued+"?['Length'])"),eq(proof+"?['issued']?['DocumentReference']","concat("+quote(origin)+",outputs('Issued_path'))"),eq(proof+"?['issued']?['SHA256']",scope+"?['DocumentSHA256']")]
    if trusted:
        for k in ('UniqueId','ETag'):proof_checks.append(eq("body('Read_binary_proof_before')?['"+k+"']",quote(trusted['receipt'][k])))
        proof_checks.append(eq("concat("+quote(origin)+",outputs('Binary_proof_path'))",quote(trusted['receipt']['DocumentReference'])))
        proof_checks.append(eq(proof,"json("+quote(json.dumps(trusted['content'],separators=(',',':')))+')'))
    last=bounded_gate(a,'Verify_binary_proof_relations',proof_checks,'Parse_binary_proof')
    final,checks,last,history=recheck('Before_event',last);a.update(final)
    # Exact unchanged whole purpose histories, excluding only this publication identity.
    for label,read in [('initial','Purpose_before_assurance'),('late',history)]:
        name='Publication_others_'+label;a[name]=query("@body('"+read+"')?['value']","not(equals(item()?['EventUID'],outputs('Publication_uid')))",last)
        a[name+'_stable']=stable("@body('"+name+"')",name);last=name+'_stable'
    checks += [eq("body('Publication_others_initial_stable')","body('Publication_others_late_stable')")]
    a['Find_existing_publication']=query("@body('"+history+"')?['value']","equals(item()?['EventUID'],outputs('Publication_uid'))",last)
    a['Find_publication_corrections']=query("@body('"+history+"')?['value']","equals(item()?['SupersedesEventUID'],outputs('Publication_uid'))",'Find_existing_publication')
    checks += ["lessOrEquals(length(body('Find_existing_publication')),1)","equals(length(body('Find_publication_corrections')),0)"]
    last=bounded_gate(a,'Verify_publication_frame_before',checks,'Find_publication_corrections')
    payload={key:'@'+scope+"?['"+key+"']" for key in ('CaseUID','DocumentReference','ReviewedVersionRef','DocumentSHA256')}
    payload.update(EventUID="@outputs('Publication_uid')",Title='FICTIONAL binary publication representation',Stage='Publication',RecordState='Recorded',ConditionsState='None recorded',FictionalTest=True,
        ParentEventUID="@first(body('Purpose_before_rows_authorisation'))?['EventUID']",SupersedesEventUID=None,
        ActorName='FICTIONAL technical publisher; real authority unqualified',Summary='FICTIONAL retained authorised bytes; no actual controlled publication or circulation',
        EvidenceReference='@concat('+quote(origin)+",outputs('Binary_proof_path'))",PublicationURL='@concat('+quote(origin)+",outputs('Issued_path'))",
        PublishedVersionRef="@concat('sharepoint:',"+issued+"?['UniqueId'],':',"+issued+"?['ETag'])",
        OccurredOn="@if(equals(length(body('Find_existing_publication')),1),first(body('Find_existing_publication'))?['OccurredOn'],formatDateTime(utcNow(),'yyyy-MM-ddTHH:mm:ssZ'))")
    a['Publication_payload']=comp(payload,last)
    row="first(body('Find_existing_publication'))"
    matches=[eq(row+"?['"+k+"']","outputs('Publication_payload')?['"+k+"']") for k in payload]
    matches += ["greater(int(coalesce("+row+"?['Id'],0)),0)",present(row+"?['GUID']"),present(row+"?['odata.etag']"),"not(equals("+row+"?['odata.etag'],'*'))"]
    checks=["if(equals(length(body('Find_existing_publication')),1),"+allof(matches)+',true)']
    checks += ['lessOrEquals(length(string(outputs(\'Publication_payload\')?[\''+k+"'])),255)" for k in ('EventUID','ActorName','Summary','EvidenceReference','PublicationURL','PublishedVersionRef')]
    last=bounded_gate(a,'Verify_publication_replay',checks,'Publication_payload')
    a['Ensure_publication']={'type':'If','expression':"@equals(length(body('Find_existing_publication')),0)",'runAfter':{last:['Succeeded']},
        'actions':{'Create_binary_publication':http(assurance_uri,method='POST',body="@string(outputs('Publication_payload'))")},'else':{'actions':{}}}
    after,checks,last,history=recheck('After_event','Ensure_publication');a.update(after)
    a['Read_retained_publication']=query("@body('"+history+"')?['value']","equals(item()?['EventUID'],outputs('Publication_uid'))",last)
    a['Read_retained_corrections']=query("@body('"+history+"')?['value']","equals(item()?['SupersedesEventUID'],outputs('Publication_uid'))",'Read_retained_publication')
    a['Publication_others_after']=query("@body('"+history+"')?['value']","not(equals(item()?['EventUID'],outputs('Publication_uid')))",'Read_retained_corrections')
    a['Publication_others_after_stable']=stable("@body('Publication_others_after')",'Publication_others_after')
    row="first(body('Read_retained_publication'))"
    checks += ["equals(length(body('Read_retained_publication')),1)","equals(length(body('Read_retained_corrections')),0)",eq("body('Publication_others_late_stable')","body('Publication_others_after_stable')")]
    checks += ["if(equals(length(body('Read_retained_publication')),1),"+allof([eq(row+"?['"+k+"']","outputs('Publication_payload')?['"+k+"']") for k in payload])+',false)']
    checks += ["if(equals(length(body('Read_retained_publication')),1),"+allof([
        "greater(int(coalesce("+row+"?['Id'],0)),0)",present(row+"?['GUID']"),present(row+"?['odata.etag']"),"not(equals("+row+"?['odata.etag'],'*'))",
        "lessOrEquals(ticks("+row+"?['OccurredOn']),ticks(utcNow()))",
        "greaterOrEquals(ticks("+row+"?['OccurredOn']),ticks(first(body('Purpose_before_rows_authorisation'))?['OccurredOn']))"])+',false)',
        "if(and(equals(length(body('Find_existing_publication')),1),equals(length(body('Read_retained_publication')),1)),equals(union(first(body('Find_existing_publication')),json('{\"odata.id\":null}')),union(first(body('Read_retained_publication')),json('{\"odata.id\":null}'))),true)"]
    # After any possible writer, a failed final check cannot honestly report zero effects.
    last=bounded_gate(a,'Verify_publication_after',checks,'Publication_others_after_stable')
    error=a['Verify_publication_after']['else']['actions']['Held_Verify_publication_after']['inputs'];error.update(copyCreatedCount=0,publicationCreatedCount=None,reconcileBeforeRetry=True)
    a['Native_binary_publication_receipt']=comp({'qualified':True,'preparedScope':'@'+scope,'originalSourceScope':'@'+p+"?['originalSourceScope']",
        'authorisation':"@first(body('Purpose_before_rows_authorisation'))",'issued':'@'+issued,'downloadedSHA256':'@'+proof+"?['issued']?['SHA256']",
        'publicationEvent':'@'+row,'copyCreatedCount':0,'publicationCreatedCount':"@if(equals(length(body('Find_existing_publication')),0),1,0)",
        'caseWrites':0,'sourceWrites':0,'readinessWrites':0,'purposeWrites':0,'notifications':0,'actualControlledPublication':False,'realPolicyEffects':False,
        'actorAuthorityQualified':False,'runId':"@workflow()?['run']?['name']"},last)
    a['Unknown_copy_effect']=comp({**held,'copyCreatedCount':None,'publicationCreatedCount':0,'reason':'Copy may exist; retain run/output and reconcile; no automatic resubmit','reconcileBeforeRetry':True})
    a['Unknown_copy_effect']['runAfter']={'Copy_if_absent':['Failed','TimedOut']}
    a['Unknown_copy_readback']=comp({**held,'copyCreatedCount':None,'publicationCreatedCount':0,
        'reason':'Issued metadata readback failed after possible copy; retain output and reconcile','reconcileBeforeRetry':True})
    a['Unknown_copy_readback']['runAfter']={'Verify_issued_metadata':['Failed','TimedOut','Skipped']}
    a['Unknown_publication_effect']=comp({**held,'copyCreatedCount':0,'publicationCreatedCount':None,'reason':'Event may exist; retain run/output and reconcile before retry','reconcileBeforeRetry':True})
    a['Unknown_publication_effect']['runAfter']={'Ensure_publication':['Failed','TimedOut']}
    a['Unknown_final_publication_evidence']=comp({**held,'copyCreatedCount':0,'publicationCreatedCount':None,'reason':'Final readback/frame failed; retain event and reconcile','reconcileBeforeRetry':True})
    a['Unknown_final_publication_evidence']['runAfter']={'Verify_publication_after':['Failed','TimedOut','Skipped']}
    out=copy.deepcopy(target);out['properties']['state']='Stopped';d=out['properties']['definition'];d['actions']=a
    fields={'text':{'type':'string','title':'Action','description':'Prepare binary copy or Record publication. FICTIONAL only.'},
            'text_6':copy.deepcopy(source['triggers']['manual']['inputs']['schema']['properties']['text_6'])}
    d['triggers']={'manual':{'type':'Request','kind':'Button','inputs':{'schema':{'type':'object','properties':fields,'required':list(fields)}},'runtimeConfiguration':{'concurrency':{'runs':1}}}}
    audit_actions(d)
    # The only copied native writers are our one body-free copy and one event append.
    writers=[]
    def scan(group):
        for name,v in group.items():
            if v.get('type')=='OpenApiConnection' and v['inputs']['parameters'].get('parameters/method')!='GET':writers.append(name)
            scan(v.get('actions',{}));scan(v.get('else',{}).get('actions',{}))
    scan(a);require(set(writers)=={'Copy_binary_absent_only','Create_binary_publication'},'Unexpected native writer')
    return out
