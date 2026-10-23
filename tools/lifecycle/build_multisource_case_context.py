"""Opt-in context lookup for reviewed fictional source profiles.

Pure composition. Other operations retain the original source restriction by
default; explicit pinned exceptions can prepare ownership projection or read-only
preparation checks for one additional profile. Native qualification is separate.
"""
import copy
import hashlib
import json
import re
from urllib.parse import urlsplit
from uuid import UUID

from build_operator_entry import _flatten, _literal, action_references
from build_selected_event_routes import audit_actions

PREFIX = 'SourceProfiles_'
REQ = "outputs('Parse_baseline')?['request']"
SELECTED = "outputs('SourceProfiles_selected')"
MATCH = (('DocumentUID','DocumentUID'),('DocumentReference','DocumentReference'),
         ('ReviewedVersionRef','ReviewedVersionRef'),('sha256','DocumentSHA256'))
PROJECTION_SOURCE_READS = ('Selected_Projection_before_source','Selected_Projection_after_source')


def _projection_source_uri():
    return ("@concat('_api/web/GetFileById(',decodeUriComponent('%27'),"
            "outputs('Selected_case_context')?['sourcePins']?['UniqueId'],"
            "decodeUriComponent('%27'),')?$select=UniqueId,ETag,Length')")


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate_sources(profiles, site):
    if not isinstance(profiles,list) or not profiles:
        raise ValueError('Nonempty reviewed source profiles required')
    validated=[];identities=set();scopes=set();target=urlsplit(site)
    for value in profiles:
        keys={'DocumentUID','DocumentReference','ReviewedVersionRef','UniqueId','ETag','content','sha256'}
        if not isinstance(value,dict) or not keys<=set(value) or any(not isinstance(value[k],str) or not value[k] for k in keys):
            raise ValueError('Complete immutable source profile required')
        profile={key:value[key] for key in keys}
        uid=str(UUID(profile['UniqueId']));uri=urlsplit(profile['DocumentReference'])
        if (not profile['DocumentUID'].startswith('FICTIONAL-') or not profile['ETag'].strip() or profile['ETag'].strip()=='*' or any(v.startswith('@') for v in profile.values())
                or uri.scheme!='https' or uri.netloc!=target.netloc or not uri.path.startswith(target.path.rstrip('/')+'/')
                or uri.username or uri.password or uri.query or uri.fragment
                or hashlib.sha256(profile['content'].encode()).hexdigest()!=profile['sha256']):
            raise ValueError('Reviewed same-site fictional source identity/content required')
        scope=tuple(profile[key] for key,_ in MATCH)
        if uid in identities or scope in scopes:
            raise ValueError('Source identities and request scopes must be unambiguous')
        identities.add(uid);scopes.add(scope);validated.append(profile)
    return validated


def match_expression():
    return '@and('+','.join("equals(item()?['"+key+"'],"+REQ+"?['"+request_key+"'])" for key,request_key in MATCH)+')'


def _operation_expression(seed, additional_projection=None, additional_preparation=None):
    checks = ["equals(triggerBody()?['text'],'Check context')",
              'equals('+SELECTED+"?['UniqueId'],"+_literal(seed['UniqueId'])+')']
    if additional_projection is not None:
        checks.append("and(equals(triggerBody()?['text'],'Project ownership'),equals("
                      +SELECTED+"?['UniqueId'],"+_literal(additional_projection)+'))')
    if additional_preparation is not None:
        checks.append("and(contains(createArray('Check preparation','Check readiness'),triggerBody()?['text']),equals("
                      +SELECTED+"?['UniqueId'],"+_literal(additional_preparation)+'))')
    return '@or('+','.join(checks)+')'


def _check_context_shape(definition):
    """Check the local emitted lookup shape; not native consumer qualification."""
    nodes=_flatten(definition['actions'])
    if PREFIX+'configured' not in nodes:return None
    site=nodes['Read_selected_case']['inputs']['parameters']['dataset']
    profiles=validate_sources(nodes[PREFIX+'configured']['inputs'],site)
    context=nodes['Selected_case_context']['inputs']
    if (nodes[PREFIX+'matches']['inputs']!={'from':"@outputs('SourceProfiles_configured')",'where':match_expression()}
            or nodes[PREFIX+'selected']['inputs']!="@first(body('SourceProfiles_matches'))"
            or nodes[PREFIX+'verify']['expression']!="@equals(length(body('SourceProfiles_matches')),1)"
            or nodes['Read_source_before']['runAfter']!={PREFIX+'verify':['Succeeded']}
            or nodes[PREFIX+'configured']['runAfter']!={}
            or nodes[PREFIX+'matches']['runAfter']!={PREFIX+'configured':['Succeeded']}
            or nodes[PREFIX+'verify']['runAfter']!={PREFIX+'matches':['Succeeded']}):
        raise ValueError('Reviewed source lookup contract changed')
    for key in ('DocumentUID','UniqueId','ETag'):
        if context['sourcePins'].get(key)!='@'+SELECTED+"?['"+key+"']":
            raise ValueError('Source context must use the verified selected profile')
    for key,source_key in [('DocumentReference','DocumentReference'),('ReviewedVersionRef','ReviewedVersionRef'),('DocumentSHA256','sha256')]:
        if context['scope'].get(key)!='@'+SELECTED+"?['"+source_key+"']":
            raise ValueError('Case scope must use the verified selected profile')
    if context.get('limits',{}).get('profiledReadOnlyContext') is not True:
        raise ValueError('Explicit context-only eligibility contract required')
    branch=nodes['Verify_request']['actions']
    verify=branch[PREFIX+'verify']
    selected=verify['actions'][PREFIX+'selected']
    operation=verify['actions'][PREFIX+'operation']
    additional=context.get('limits',{}).get('additionalOwnershipProjectionSource')
    preparation=context.get('limits',{}).get('additionalPreparationContextSource')
    folders=context.get('limits',{}).get('additionalPreparationArtifactFolders')
    roles=context.get('limits',{}).get('additionalPreparationReadinessRoles')
    if additional is not None and (not isinstance(additional,str)
            or additional not in {p['UniqueId'] for p in profiles}):
        raise ValueError('Additional projection source must be an existing reviewed profile')
    if preparation is not None and (not isinstance(preparation,str)
            or preparation not in {p['UniqueId'] for p in profiles}):
        raise ValueError('Additional preparation source must be an existing reviewed profile')
    seeds=[p for p in profiles if operation['expression']==_operation_expression(p,additional,preparation)]
    if (len(seeds)!=1 or selected.get('runAfter')!={}
            or operation.get('runAfter')!={PREFIX+'selected':['Succeeded']}
            or operation['actions']!={PREFIX+'allowed':{'type':'Compose','inputs':True,'runAfter':{}}}):
        raise ValueError('Source-specific operation restriction changed')
    if additional is not None and additional==seeds[0]['UniqueId']:
        raise ValueError('Additional projection source must differ from the original source')
    if preparation is not None:
        if preparation==seeds[0]['UniqueId']:
            raise ValueError('Additional preparation source must differ from the original source')
        _check_preparation_readers(nodes,site,_projection_source_uri())
    if folders is not None:
        if preparation is None:
            raise ValueError('Prepared artifact folders require the reviewed additional source')
        _check_preparation_folders(nodes,site,preparation,folders)
    if roles is not None:
        if preparation is None:
            raise ValueError('Readiness role binding requires the reviewed additional source')
        expected=_preparation_role_graph(nodes,preparation,roles)
        if nodes['Ready_consultation_Runtime_guard']!=expected['Ready_consultation_Runtime_guard']:
            raise ValueError('Reviewed source-specific readiness role guards changed')
    if additional is not None:
        for name in PROJECTION_SOURCE_READS:
            if name in nodes:
                params=nodes[name].get('inputs',{}).get('parameters',{})
                if (nodes[name].get('type')!='OpenApiConnection'
                        or params.get('parameters/method')!='GET' or params.get('dataset')!=site
                        or params.get('parameters/uri')!=_projection_source_uri()):
                    raise ValueError('Projection source reads must follow the verified selected context')
    for container,name in [(verify,PREFIX+'refused'),(operation,PREFIX+'operation_refused')]:
        refused=container['else']['actions'][name]
        if refused.get('type')!='Terminate' or refused.get('inputs',{}).get('runStatus')!='Failed':
            raise ValueError('Unqualified source/operation must terminate before later routes')
    from build_selected_case_context import build as canonical_context
    table='00000000-0000-4000-8000-000000000001'
    probe={'properties':{'definition':{'triggers':{'manual':{'kind':'ApiConnection',
        'inputs':{'operationId':'GetItemHybridTriggerSchema','parameters':{'dataset':site,'table':table}}}}},
        'connectionReferences':{'shared_sharepointonline':{}}}}
    canonical=canonical_context(probe,{'qualificationOnly':True,'siteUrl':site,
        'caseListUri':"_api/web/lists(guid'"+table+"')/items",'evidenceFolder':'/fictional','source':seeds[0]})
    expected=_flatten(canonical['properties']['definition']['actions'])['Verify_source_and_case']['expression']
    final=branch['Verify_source_and_case']
    if final['expression']!=_selected_final_guard(expected,seeds[0],site):
        raise ValueError('Exact source-content and native case/baseline frame guards required')
    if (final.get('runAfter')!={'Recheck_baseline':['Succeeded']}
            or 'Selected_case_context' not in final['actions']):
        raise ValueError('Context must follow final native checks')
    for name,suffix,previous in [('Read_source_before','?$select=UniqueId,ETag,Length,ServerRelativeUrl',PREFIX+'verify'),
            ('Read_source_content','/$value','Read_source_before'),
            ('Read_source_after','?$select=UniqueId,ETag,Length,ServerRelativeUrl','Read_source_content')]:
        action=branch[name];params=action['inputs']['parameters'];host=action['inputs']['host']
        expected="@concat('_api/web/GetFileById(',decodeUriComponent('%27'),"+SELECTED+"?['UniqueId'],decodeUriComponent('%27'),"+_literal(')'+suffix)+')'
        if (action.get('type')!='OpenApiConnection' or params.get('dataset')!=site
                or params.get('parameters/method')!='GET' or params.get('parameters/uri')!=expected
                or 'parameters/body' in params or params.get('parameters/headers') not in (None,{}, {'Accept':'application/json;odata=nometadata'})
                or host.get('operationId')!='HttpRequest' or host.get('connectionName')!='shared_sharepointonline'
                or action.get('runAfter')!={previous:['Succeeded']}):
            raise ValueError('Reviewed selected-source read contract changed')
    return profiles


def _check_preparation_readers(nodes, site, source_uri):
    """The two exposed preparation operations must remain GET-only."""
    for name in ('Route_preparation_check','Route_readiness_check'):
        branch=nodes[name]
        for action in _flatten({name:branch}).values():
            if action.get('type') not in ('If','Compose','Query','Select','OpenApiConnection'):
                raise ValueError('Reviewed read-only preparation routes required')
            if action.get('type')=='OpenApiConnection':
                params=action.get('inputs',{}).get('parameters',{})
                host=action.get('inputs',{}).get('host',{})
                if (params.get('dataset')!=site or params.get('parameters/method')!='GET'
                        or 'parameters/body' in params or host.get('operationId')!='HttpRequest'
                        or host.get('connectionName')!='shared_sharepointonline'
                        or host.get('apiId')!='/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
                        or any(k.lower() in ('x-http-method','x-http-method-override')
                               for k in params.get('parameters/headers',{}))):
                    raise ValueError('Reviewed read-only preparation routes required')
    reader=nodes['Read_prepared_source_final']
    if reader['inputs']['parameters'].get('parameters/uri')!=source_uri:
        raise ValueError('Preparation source read must follow the reviewed selected context')


def _preparation_folder_fragments(site, source_uid, folders, *, by_document_reference=False):
    if (not isinstance(folders,dict)
            or set(folders) not in ({'originalFolder','additionalFolder','selectionGuardSHA256','receiptLookupSHA256'},
                                   {'originalFolder','additionalFolder','selectionGuardSHA256','receiptLookupSHA256','receiptReferenceSHA256'})
            or any(not isinstance(folders[k],str) or not re.fullmatch('[0-9a-f]{64}',folders[k])
                   for k in ('selectionGuardSHA256','receiptLookupSHA256')+
                   (('receiptReferenceSHA256',) if 'receiptReferenceSHA256' in folders else ()))):
        raise ValueError('Exact reviewed preparation-folder binding required')
    parsed=urlsplit(site);origin=parsed.scheme+'://'+parsed.netloc
    old,new=folders['originalFolder'],folders['additionalFolder']
    for folder in (old,new):
        if (not isinstance(folder,str) or not folder.startswith(parsed.path.rstrip('/')+'/')
                or folder.endswith('/') or any(c in folder for c in ("'",'..','?','#','%','\\','//'))
                or any(ord(c)<32 for c in folder)):
            raise ValueError('Exact same-site preparation folders required')
    if old==new:raise ValueError('Additional artifact folder must differ from the original')
    old_prefix=_literal(origin+old+'/');new_prefix=_literal(origin+new+'/')
    condition=("startsWith(outputs('Prepared_document_reference'),"+new_prefix+')' if by_document_reference else
               'equals('+SELECTED+"?['UniqueId'],"+_literal(source_uid)+')')
    old_lookup=_literal("_api/web/GetFolderByServerRelativePath(decodedurl='"+old+"')/Files?$filter=Name eq '")
    new_lookup=_literal("_api/web/GetFolderByServerRelativePath(decodedurl='"+new+"')/Files?$filter=Name eq '")
    return ((old_prefix,'if('+condition+','+new_prefix+','+old_prefix+')'),
            (old_lookup,'if('+condition+','+new_lookup+','+old_lookup+')'))


def _bind_preparation_receipt_reference(nodes, folders, fragments):
    receipt=nodes['Native_prepared_revision']['inputs']['preparedRevision']['qualificationReceipt']
    original=receipt['DocumentReference'];old,new=fragments[0]
    if original.count(old)!=1:
        raise ValueError('Exact original receipt reference folder required')
    folders['receiptReferenceSHA256']=digest(original)
    receipt['DocumentReference']=original.replace(old,new)


def _check_preparation_folders(nodes, site, source_uid, folders, *, by_document_reference=False):
    fragments=_preparation_folder_fragments(site,source_uid,folders,by_document_reference=by_document_reference)
    for name,key,field,pair in (
            ('Verify_prepared_selection','selectionGuardSHA256','expression',fragments[0]),
            ('Find_prepared_receipt','receiptLookupSHA256','parameters/uri',fragments[1])):
        value=nodes[name][field] if field=='expression' else nodes[name]['inputs']['parameters'][field]
        old,new=pair
        if value.count(new)!=1 or digest(value.replace(new,old))!=folders[key]:
            raise ValueError('Prepared folder selection/receipt guards changed')
    if 'receiptReferenceSHA256' in folders:
        value=nodes['Native_prepared_revision']['inputs']['preparedRevision']['qualificationReceipt']['DocumentReference']
        old,new=fragments[0]
        if value.count(new)!=1 or digest(value.replace(new,old))!=folders['receiptReferenceSHA256']:
            raise ValueError('Prepared receipt reference changed')


def _preparation_role_graph(nodes, source_uid, binding):
    """Select two explicit role plans within the existing unrolled coverage shape."""
    from build_consultation_coverage import build_runtime
    if (not isinstance(binding,dict)
            or set(binding)!={'originalRoles','additionalRoles','originalCoverageSHA256'}
            or not isinstance(binding['originalRoles'],list) or not isinstance(binding['additionalRoles'],list)
            or len(binding['originalRoles'])!=len(binding['additionalRoles'])):
        raise ValueError('Equal-cardinality explicit readiness role plans required; qualify a different shape separately')
    reader=nodes['Readiness_consultation_before'];uri=reader['inputs']['parameters']['parameters/uri']
    def canonical(roles):
        return build_runtime('Readiness_consultation_before',reader,roles,
            qualified_reader=nodes['Read_selected_case'],collection_uri=uri,prefix='Ready_consultation')
    old=canonical(binding['originalRoles']);new=canonical(binding['additionalRoles'])
    if digest(old)!=binding['originalCoverageSHA256']:
        raise ValueError('Original complete readiness coverage graph changed')
    original=_flatten(old);changed=_flatten(new)
    condition='equals('+SELECTED+"?['UniqueId'],"+_literal(source_uid)+')'
    replacements=[('Ready_consultation_Problems','where')]
    replacements += [('Ready_consultation_R'+str(i)+'_Rows','where')for i in range(len(binding['originalRoles']))]
    selected=copy.deepcopy(old);updated=_flatten(selected)
    for name,key in replacements:
        before=original[name]['inputs'][key];after=changed[name]['inputs'][key]
        if not before.startswith('@') or not after.startswith('@'):
            raise ValueError('Canonical readiness role query expression required')
        updated[name]['inputs'][key]='@if('+condition+','+after[1:]+','+before[1:]+')'
        changed[name]['inputs'][key]=before
    for index,(before,after) in enumerate(zip(binding['originalRoles'],binding['additionalRoles'])):
        updated['Ready_consultation_Receipt']['inputs']['requiredRoleResults'][index]['SubjectRole']='@if('+condition+','+_literal(after)+','+_literal(before)+')'
        changed['Ready_consultation_Receipt']['inputs']['requiredRoleResults'][index]['SubjectRole']=before
    if new!=old:
        raise ValueError('Role binding must preserve every other coverage action, condition and reader')
    return selected


def with_readonly_preparation_source(profile, source_uid, approved_definition_sha256,
                                     *, artifact_folder_relative=None, required_fictional_roles=None):
    """Prepare selected-source preparation/readiness reads, adding no writer.

    This adds one reviewed existing source to the two existing read-only modes.
    It preserves ownership restrictions, templates and all evidence guards.
    Optional explicit folder and fictional-role bindings preserve the original
    source's plan. Role plans retain the existing unrolled coverage cardinality;
    a changed cardinality requires a separately qualified graph shape.
    Native first/replay qualification remains separate.
    """
    definition=profile['properties']['definition']
    if digest(definition)!=approved_definition_sha256:
        raise ValueError('Exact reviewed case-work definition required')
    profiles=_check_context_shape(definition)
    if profiles is None:
        raise ValueError('Existing reviewed eligible-source context required')
    nodes=_flatten(definition['actions']);limits=nodes['Selected_case_context']['inputs']['limits']
    if 'additionalPreparationContextSource' in limits:
        raise ValueError('Review an existing preparation exception before replacing it')
    additional=limits.get('additionalOwnershipProjectionSource')
    seeds=[p for p in profiles if nodes[PREFIX+'operation']['expression']==_operation_expression(p,additional)]
    if len(seeds)!=1 or source_uid==seeds[0]['UniqueId'] or source_uid not in {p['UniqueId'] for p in profiles}:
        raise ValueError('Exact existing additional reviewed source identity required')
    site=nodes['Read_selected_case']['inputs']['parameters']['dataset']
    original_uri="_api/web/GetFileById('"+seeds[0]['UniqueId']+"')?$select=UniqueId,ETag,Length"
    _check_preparation_readers(nodes,site,original_uri)
    out=copy.deepcopy(profile);out['properties']['state']='Stopped'
    updated=_flatten(out['properties']['definition']['actions'])
    updated[PREFIX+'operation']['expression']=_operation_expression(seeds[0],additional,source_uid)
    updated['Selected_case_context']['inputs']['limits']['additionalPreparationContextSource']=source_uid
    updated['Read_prepared_source_final']['inputs']['parameters']['parameters/uri']=_projection_source_uri()
    if artifact_folder_relative is not None:
        selection=updated['Verify_prepared_selection']['expression']
        lookup=updated['Find_prepared_receipt']['inputs']['parameters']['parameters/uri']
        matches=re.findall(r"startsWith\(outputs\('Prepared_document_reference'\),('(?:[^']|'')*')\)",selection)
        if len(matches)!=1:raise ValueError('Original literal prepared-folder guard required')
        original_prefix=matches[0][1:-1].replace("''", "'");parsed=urlsplit(site)
        origin=parsed.scheme+'://'+parsed.netloc
        if not original_prefix.startswith(origin) or not original_prefix.endswith('/'):
            raise ValueError('Original same-site prepared-folder guard required')
        folders={'originalFolder':original_prefix[len(origin):-1],
                 'additionalFolder':artifact_folder_relative,
                 'selectionGuardSHA256':digest(selection),'receiptLookupSHA256':digest(lookup)}
        fragments=_preparation_folder_fragments(site,source_uid,folders)
        for value,(old,new) in zip((selection,lookup),fragments):
            if value.count(old)!=1:raise ValueError('Original paired preparation-folder literals required')
        updated['Verify_prepared_selection']['expression']=selection.replace(*fragments[0])
        updated['Find_prepared_receipt']['inputs']['parameters']['parameters/uri']=lookup.replace(*fragments[1])
        _bind_preparation_receipt_reference(updated,folders,fragments)
        updated['Selected_case_context']['inputs']['limits']['additionalPreparationArtifactFolders']=folders
    if required_fictional_roles is not None:
        original_roles=[row['SubjectRole']for row in updated['Ready_consultation_Receipt']['inputs']['requiredRoleResults']]
        binding={'originalRoles':original_roles,'additionalRoles':copy.deepcopy(required_fictional_roles),
                 'originalCoverageSHA256':digest({'Ready_consultation_Runtime_guard':updated['Ready_consultation_Runtime_guard']})}
        role_graph=_preparation_role_graph(updated,source_uid,binding)
        updated['Ready_consultation_Runtime_guard'].clear()
        updated['Ready_consultation_Runtime_guard'].update(role_graph['Ready_consultation_Runtime_guard'])
        updated['Selected_case_context']['inputs']['limits']['additionalPreparationReadinessRoles']=binding
    _check_context_shape(out['properties']['definition'])
    return out


def with_ownership_projection_source(profile, source_uid, approved_definition_sha256):
    """Prepare one explicit ownership-projection exception; no native approval.

    Preserve every source/frame/response/conditional-write guard and all other
    operation restrictions. Deployment and actual first/replay qualification
    remain separate. This function adds no writer, connection or source profile.
    """
    definition=profile['properties']['definition']
    if digest(definition)!=approved_definition_sha256:
        raise ValueError('Exact reviewed case-work definition required')
    profiles=_check_context_shape(definition)
    if profiles is None:
        raise ValueError('Existing reviewed eligible-source context required')
    nodes=_flatten(definition['actions'])
    limits=nodes['Selected_case_context']['inputs']['limits']
    if 'additionalOwnershipProjectionSource' in limits:
        raise ValueError('Review an existing projection exception before replacing it')
    matches=[p for p in profiles if p['UniqueId']==source_uid]
    if len(matches)!=1:
        raise ValueError('Exact existing reviewed source identity required')
    operation=nodes[PREFIX+'operation']['expression']
    preparation=limits.get('additionalPreparationContextSource')
    seeds=[p for p in profiles if operation==_operation_expression(p,None,preparation)]
    if len(seeds)!=1 or seeds[0]['UniqueId']==source_uid:
        raise ValueError('An additional source with the original restriction required')
    out=copy.deepcopy(profile);out['properties']['state']='Stopped'
    updated=_flatten(out['properties']['definition']['actions'])
    updated[PREFIX+'operation']['expression']=_operation_expression(seeds[0],source_uid,preparation)
    updated['Selected_case_context']['inputs']['limits']['additionalOwnershipProjectionSource']=source_uid
    site=updated['Read_selected_case']['inputs']['parameters']['dataset']
    original_uri="_api/web/GetFileById('"+seeds[0]['UniqueId']+"')?$select=UniqueId,ETag,Length"
    for name in PROJECTION_SOURCE_READS:
        if name in updated:
            node=updated[name];params=node.get('inputs',{}).get('parameters',{})
            if (node.get('type')!='OpenApiConnection' or params.get('dataset')!=site
                    or params.get('parameters/method')!='GET'
                    or params.get('parameters/uri') not in (original_uri,_projection_source_uri())):
                raise ValueError('Exact reviewed projection metadata reader required')
            params['parameters/uri']=_projection_source_uri()
    _check_context_shape(out['properties']['definition'])
    return out


def _selected_final_guard(expression, seed, site):
    origin=urlsplit(site).scheme+'://'+urlsplit(site).netloc
    for name in ('Read_source_before','Read_source_after'):
        for key in ('ETag','UniqueId'):
            old="equals(body('"+name+"')?['"+key+"'],"+_literal(seed[key])+')'
            new="equals(body('"+name+"')?['"+key+"'],"+SELECTED+"?['"+key+"'])"
            if expression.count(old)!=1:raise ValueError('Original source metadata guard changed')
            expression=expression.replace(old,new)
        expression='@and('+expression[1:]+",equals(concat("+_literal(origin)+",body('"+name+"')?['ServerRelativeUrl']),"+SELECTED+"?['DocumentReference']))"
    decoded="if(contains(body('Read_source_content'),'$content'),base64ToString(body('Read_source_content')?['$content']),string(body('Read_source_content')))"
    old='equals('+decoded+','+_literal(seed['content'])+')'
    if expression.count(old)!=1:raise ValueError('Original exact source-content guard changed')
    expression=expression.replace(old,'equals('+decoded+','+SELECTED+"?['content'])")
    return expression


def with_eligible_sources(profile, profiles, approved_definition_sha256):
    source=profile['properties']['definition']
    if digest(source)!=approved_definition_sha256:
        raise ValueError('Exact reviewed case-work definition required')
    nodes=_flatten(source['actions']);context=nodes['Selected_case_context']['inputs']
    trigger=source['triggers'].get('manual',{});schema=trigger.get('inputs',{}).get('schema',{})
    if (trigger.get('type')!='Request' or trigger.get('kind')!='Button'
            or set(schema.get('properties',{}))!={'text','text_6'}
            or context.get('contextOrigin')!='manual_case_reference_lookup'
            or context.get('limits',{}).get('selectedRowProvenanceClaimed') is not False
            or any(name.startswith(PREFIX) for name in nodes)):
        raise ValueError('Unmodified server-resolved two-field case-work entry required')
    site=nodes['Read_selected_case']['inputs']['parameters']['dataset'];profiles=validate_sources(profiles,site)
    seeds=[p for p in profiles if all(context['sourcePins'].get(k)==p[k] for k in ('DocumentUID','UniqueId','ETag'))
           and all(context['scope'].get(k)==p[s] for k,s in [('DocumentReference','DocumentReference'),('ReviewedVersionRef','ReviewedVersionRef'),('DocumentSHA256','sha256')])]
    if len(seeds)!=1:raise ValueError('Retain the original configured source exactly')
    seed=seeds[0];out=copy.deepcopy(profile);out['properties']['state']='Stopped'
    definition=out['properties']['definition'];nodes=_flatten(definition['actions'])
    branch=nodes['Verify_request']['actions']
    request_guard=nodes['Verify_request']
    for key,request_key in MATCH:
        clause='equals('+REQ+"?['"+request_key+"'],"+_literal(seed[key])+')'
        if request_guard['expression'].count(clause)!=1:raise ValueError('Original request-source guard changed')
        request_guard['expression']=request_guard['expression'].replace(clause,'true')
    old="createArray("+_literal(seed['DocumentUID'])+")"
    if request_guard['expression'].count(old)!=1:raise ValueError('Original linked-document guard changed')
    request_guard['expression']=request_guard['expression'].replace(old,"createArray("+REQ+"?['DocumentUID'])")
    def compose(value,previous=None):return {'type':'Compose','inputs':value,'runAfter':{previous:['Succeeded']} if previous else {}}
    branch[PREFIX+'configured']=compose(profiles)
    branch[PREFIX+'matches']={'type':'Query','inputs':{'from':"@outputs('SourceProfiles_configured')",'where':match_expression()},'runAfter':{PREFIX+'configured':['Succeeded']}}
    allowed=_operation_expression(seed)
    def refused(code):return {'type':'Terminate','runAfter':{},'inputs':{'runStatus':'Failed','runError':{'code':code,'message':'No eligible reviewed source or operation. No source read or later writer entered.'}}}
    branch[PREFIX+'verify']={'type':'If','expression':"@equals(length(body('SourceProfiles_matches')),1)",
        'runAfter':{PREFIX+'matches':['Succeeded']},'actions':{PREFIX+'selected':compose("@first(body('SourceProfiles_matches'))"),
            PREFIX+'operation':{'type':'If','expression':allowed,'runAfter':{PREFIX+'selected':['Succeeded']},
                'actions':{PREFIX+'allowed':compose(True)},'else':{'actions':{PREFIX+'operation_refused':refused('SourceOperationNotQualified')}}}},
        'else':{'actions':{PREFIX+'refused':refused('SourceEligibilityUnresolved')}}}
    final=nodes['Verify_source_and_case'];origin=urlsplit(site).scheme+'://'+urlsplit(site).netloc
    for name,suffix in [('Read_source_before','?$select=UniqueId,ETag,Length,ServerRelativeUrl'),('Read_source_content','/$value'),('Read_source_after','?$select=UniqueId,ETag,Length,ServerRelativeUrl')]:
        action=nodes[name];params=action['inputs']['parameters']
        if params.get('parameters/method')!='GET' or params.get('dataset')!=site:raise ValueError('Same-site source GET contract required')
        params['parameters/uri']="@concat('_api/web/GetFileById(',decodeUriComponent('%27'),"+SELECTED+"?['UniqueId'],decodeUriComponent('%27'),"+_literal(')'+suffix)+')'
    nodes['Read_source_before']['runAfter']={PREFIX+'verify':['Succeeded']}
    final['expression']=_selected_final_guard(final['expression'],seed,site)
    result=nodes['Selected_case_context']['inputs']
    for key in ('DocumentUID','UniqueId','ETag'):result['sourcePins'][key]='@'+SELECTED+"?['"+key+"']"
    for key,source_key in [('DocumentReference','DocumentReference'),('ReviewedVersionRef','ReviewedVersionRef'),('DocumentSHA256','sha256')]:result['scope'][key]='@'+SELECTED+"?['"+source_key+"']"
    result['limits'].update(fixedQualifiedSourceProfile=False,profiledReadOnlyContext=True,
        otherOperationsRetainOriginalSource=True)
    geometry=audit_actions(definition)
    if geometry['actionCount']>500:raise ValueError('Eligible-source context exceeds native action limit')
    if action_references(definition['actions'])-_flatten(definition['actions']).keys():raise ValueError('Unresolved eligible-source context reference')
    _check_context_shape(definition)
    return out
