"""Additive native closure binding adapter; pure local composition, no I/O.

This first component resolves the canonical sixteen evidence reads from the
same execution's qualified case/prepared/closure observations. It emits no write
and cannot close a case or qualify publication authority. Journal/write/replay
composition is a separate boundary; arbitrary caller evidence is never accepted.
"""
import copy
import base64
import hashlib
import json
import re
from urllib.parse import urlsplit

from build_operator_entry import _flatten, _literal, action_references
from build_selected_event_routes import audit_actions


FILE_FIELDS = 'UniqueId,ETag,UIVersionLabel,Length'
PATH_FIELDS = FILE_FIELDS + ',ServerRelativeUrl'
HISTORIES = ('assurance', 'readiness', 'consultation')
FILES = ('source', 'draft', 'issued', 'proof', 'date', 'originalSource',
         'sourceBaseline', 'template', 'generationReceipt', 'ownershipCommit')
CONTENTS = {'sourceContent': 'source', 'issuedContent': 'issued', 'dateContent': 'date'}


def _check_expression_lengths(value):
    if isinstance(value,str):
        if (value.startswith('@') or '@{' in value) and len(value)>8192:
            raise ValueError('Native closure expression exceeds 8192 characters')
    elif isinstance(value,dict):
        for child in value.values():_check_expression_lengths(child)
    elif isinstance(value,list):
        for child in value:_check_expression_lengths(child)


def _check_entry_limits(definition):
    geometry=audit_actions(definition)
    if geometry['actionCount']>500:
        raise ValueError('Native closure entry exceeds 500 actions')
    _check_expression_lengths(definition)


def build_binding_reads(context, binding, historical_frame_action=None):
    """Return GET-only authoritative binding/snapshot actions for initial closure.

    Required preceding actions are the existing manual context, ownership and
    prepared reader, plus the canonical closure observer. The adapter verifies
    their current native case/file identities again and keeps full fresh response
    values for the later canonical writer. It does not accept a retained receipt
    as a substitute for those same-execution observations.
    """
    definition = context['properties']['definition']
    nodes = _flatten(definition['actions'])
    template = nodes['Read_selected_case']
    site = template['inputs']['parameters']['dataset']
    parts = urlsplit(site)
    if (parts.scheme != 'https' or not parts.netloc or parts.username or parts.password
            or parts.query or parts.fragment or site != binding.get('siteUrl')):
        raise ValueError('Exact existing HTTPS case-work site required')
    collection = binding.get('caseListUri', '')
    pattern = r"_api/web/lists\(guid'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'\)/items"
    if not re.fullmatch(pattern, collection):
        raise ValueError('Exact existing case collection required')
    expected_prefix = "@concat('" + collection.replace("'", "''") + "('"
    if (template['inputs']['parameters'].get('parameters/method') != 'GET'
            or not template['inputs']['parameters']['parameters/uri'].startswith(expected_prefix)):
        raise ValueError('Server-resolved case reader must match the case collection')
    for kind in HISTORIES:
        if not re.fullmatch(pattern, binding.get(kind + 'CollectionUri', '')):
            raise ValueError('Complete native history collection required: ' + kind)
    if len({binding[kind + 'CollectionUri'] for kind in HISTORIES}) != 3:
        raise ValueError('Distinct assurance/readiness/consultation histories required')
    folder = binding.get('proofFolder', '')
    if (not folder.startswith(parts.path.rstrip('/') + '/')
            or any(char in folder for char in ("'", '..', '%', '?', '#', '\\'))):
        raise ValueError('Existing same-site proof folder required')
    ownership_pairs = (
        ('Preparation_Verified_preparation_ownership', 'Preparation_Read_projection_commit_after'),
        ('SelectedPreparation_Verified_preparation_ownership', 'SelectedPreparation_Read_projection_commit_after'))
    for verified, metadata in ownership_pairs:
        if (verified not in nodes or metadata not in nodes
                or nodes[verified].get('inputs', {}).get('ownershipProjectionVerified') is not True
                or nodes[metadata].get('inputs', {}).get('parameters', {}).get('parameters/method') != 'GET'):
            raise ValueError('Existing same-execution ownership reader required: ' + verified)
    origin = parts.scheme + '://' + parts.netloc
    selected = "outputs('Selected_case_context')"
    prepared = "outputs('Native_prepared_revision')?['preparedRevision']"
    observed = "outputs('Native_closure_observation')"
    own = "outputs('ClosureEntry_ownership_metadata')"
    if historical_frame_action is not None and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',historical_frame_action):
        raise ValueError('Literal historical frame action required')
    historical="outputs('"+historical_frame_action+"')" if historical_frame_action else None
    historical_ready="equals("+historical+"?['historicalContinuityConsistent'],true)" if historical else None
    uid = {
        'source': prepared + "?['file']?['UniqueId']",
        'draft': prepared + "?['file']?['UniqueId']",
        'issued': observed + "?['issuedFile']?['UniqueId']",
        'proof': "body('ClosureEntry_proof_locator')?['UniqueId']",
        'date': observed + "?['nextReviewEvidenceFileUID']",
        'originalSource': selected + "?['sourcePins']?['UniqueId']",
        'sourceBaseline': selected + "?['baselineUniqueId']",
        'template': prepared + "?['template']?['UniqueId']",
        'generationReceipt': prepared + "?['qualificationReceipt']?['UniqueId']",
        'ownershipCommit': own + "?['UniqueId']"}
    def equal(left, right): return 'equals(' + left + ',' + right + ')'
    def both(checks): return '@and(' + ','.join(checks) + ')'
    def comp(value, previous=None):
        return {'type': 'Compose', 'inputs': value,
                'runAfter': {previous: ['Succeeded']} if previous else {}}
    def http(uri, previous=None):
        action = copy.deepcopy(template)
        params = action['inputs']['parameters']
        params.update({'parameters/uri': uri, 'parameters/method': 'GET',
                       'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata'}})
        params.pop('parameters/body', None)
        action['inputs']['retryPolicy'] = {'type': 'none'}
        action['runAfter'] = {previous: ['Succeeded']} if previous else {}
        return action
    def hold(reason):
        return comp({'bindingsConsistent': False, 'closureWriteReady': False,
                     'caseWriteCount': 0, 'closurePerformed': False,
                     'realPolicyEffects': False, 'reason': reason})
    hold_number = 0
    def gate(checks, yes, reason, previous=None):
        nonlocal hold_number
        hold_number += 1
        return {'type': 'If', 'expression': both(checks), 'actions': yes,
                'else': {'actions': {'ClosureEntry_held_' + str(hold_number): hold(reason)}},
                'runAfter': {previous: ['Succeeded']} if previous else {}}
    def guid(value):
        value = 'string(coalesce(' + value + ",''))"
        stripped = value
        for char in '0123456789abcdefABCDEF-':
            stripped = 'replace(' + stripped + ',' + _literal(char) + ",'')"
        checks = [equal(stripped, "''"), equal("length(replace(" + value + ",'-',''))", '32')]
        checks += [equal('substring(' + value + ',' + str(i) + ',1)', "'-'") for i in (8,13,18,23)]
        return 'if(equals(length(' + value + '),36),and(' + ','.join(checks) + '),false)'
    case_uri = "@concat(" + _literal(collection + '(') + ',string(int(' + selected + "?['nativeItemId'])),')')"
    statuses = ["equals(actions('" + pair[0] + "')?['status'],'Succeeded')" for pair in ownership_pairs]
    metadata = "@if(" + statuses[0] + ",body('" + ownership_pairs[0][1] + "'),if(" + statuses[1] + ",body('" + ownership_pairs[1][1] + "'),json('null')))"
    if historical:
        metadata='@if('+historical_ready+','+historical+"?['ownershipMetadata'],"+metadata[1:]+')'
    scope = prepared + "?['scope']"
    proof_url = "first(body('Closure_selected_publication'))?['EvidenceReference']"
    initial = [equal(selected + "?['contextValid']", 'true'),
        equal("outputs('Native_prepared_revision')?['preparationQualified']", 'true'),
        equal("outputs('Native_prepared_revision')?['originalSourceIsPreparedRevision']", 'false'),
        equal(scope + "?['CaseUID']", selected + "?['CaseUID']"),
        equal(observed + "?['preparedScope']", scope),
        'greater(int(coalesce(' + selected + "?['nativeItemId'],0)),0)",
        'or(' + ','.join(statuses) + ')', 'not(and(' + ','.join(statuses) + '))',
        "if(equals(length(body('Closure_selected_publication')),1),startsWith(string(" + proof_url + '),' + _literal(origin + folder.rstrip('/') + '/') + '),false)']
    initial += [equal(observed + "?['" + key + "']", 'true') for key in
                ('closureEvidenceConsistent', 'nextReviewDateProvenanceConsistent', 'nextOccurrencePrerequisitesConsistent')]
    initial += [equal(observed + "?['" + key + "']", 'false') for key in
                ('closurePerformed', 'nextOccurrenceCreated', 'actorAuthorityQualified', 'realPolicyEffects')]
    initial.append("if(equals(length(body('Closure_selected_publication')),1),equals("+
        "first(body('Closure_selected_publication'))?['EventUID'],"+observed+"?['selectedEvents']?['publication']),false)")
    if historical:
        initial=[('or('+historical_ready+','+check+')') if check in ('or('+','.join(statuses)+')','not(and('+','.join(statuses)+'))') else check for check in initial]
    proof_checks = ['endsWith(string(' + proof_url + "),'.json')"]
    proof_checks += ['not(contains(string(' + proof_url + '),' + _literal(char) + '))' for char in ("'", '..', '%', '?', '#', '\\')]
    proof_path = 'substring(' + proof_url + ',' + str(len(origin)) + ')'
    proof_uri = "@concat('_api/web/GetFileByServerRelativePath(decodedurl=',decodeUriComponent('%27')," + proof_path + ",decodeUriComponent('%27'),')?$select=" + PATH_FIELDS + "')"
    work = {'ClosureEntry_ownership_metadata': comp(metadata),
        'ClosureEntry_case': http(case_uri, 'ClosureEntry_ownership_metadata')}
    case = "body('ClosureEntry_case')"
    token = "outputs('ClosureEntry_case')?['headers']?['ETag']"
    case_checks = [equal(case + "?['CaseUID']", selected + "?['CaseUID']"),
        equal(case + "?['Id']", selected + "?['nativeItemId']"),
        equal(case + "?['caseStatus']", "'Ownership accepted — FICTIONAL'"),
        'not(empty(' + token + '))', 'not(equals(' + token + ",'*'))",
        equal(token, selected + "?['caseETag']"),
        equal(token, "outputs('Native_prepared_revision')?['currentCaseETag']")]
    if historical:
        initial_status="equals("+case+"?['caseStatus'],'Ownership accepted — FICTIONAL')"
        case_checks=[('if('+historical_ready+",equals("+case+"?['caseStatus'],'Review closed — FICTIONAL'),"+check+')') if check==initial_status else check for check in case_checks]
    route = {'ClosureEntry_proof_locator': http(proof_uri)}
    identifiers = [equal("body('ClosureEntry_proof_locator')?['ServerRelativeUrl']", proof_path)]
    reads, snapshot = {}, {}
    previous = None
    for key in HISTORIES + FILES + tuple(CONTENTS):
        name = 'ClosureEntry_read_' + key
        if key in HISTORIES:
            uri = binding[key + 'CollectionUri']; collection_read = True
        else:
            target = CONTENTS.get(key, key)
            suffix = '/$value' if key in CONTENTS else '?$select=' + (PATH_FIELDS if key in ('source','issued','proof','date') else FILE_FIELDS)
            uri = '@concat(' + _literal("_api/web/GetFileById('") + ',' + uid[target] + ',' + _literal("')" + suffix) + ')'
            collection_read = False
        reads[key] = {'uri': uri, 'collection': collection_read}
        route[name] = http(uri, previous); previous = name
        if collection_read:
            stable = name + '_stable'
            route[stable] = {'type': 'Select', 'inputs': {'from': "@body('" + name + "')?['value']",
                'select': "@union(item(),json('{\"odata.id\":null}'))"}, 'runAfter': {name: ['Succeeded']}}
            previous = stable; snapshot[key] = "@body('" + stable + "')"
        elif key in ('sourceContent','issuedContent'):
            snapshot[key] = {'$content': "@body('" + name + "')?['$content']"}
        elif key == 'dateContent':
            snapshot[key] = "@if(contains(body('" + name + "'),'$content'),json(base64ToString(body('" + name + "')?['$content'])),json(string(body('" + name + "'))))"
        else:
            snapshot[key] = "@union(body('" + name + "'),json('{\"odata.id\":null}'))"
    route['ClosureEntry_snapshot'] = comp(snapshot, previous)
    pin_tokens = {
        'source': prepared + "?['file']?['ETag']", 'draft': prepared + "?['file']?['ETag']",
        'issued': observed + "?['issuedFile']?['ETag']",
        'proof': "body('ClosureEntry_proof_locator')?['ETag']",
        'date': "body('Closure_final_date')?['ETag']",
        'originalSource': selected + "?['sourcePins']?['ETag']",
        'sourceBaseline': selected + "?['baselineETag']",
        'template': prepared + "?['template']?['ETag']",
        'generationReceipt': prepared + "?['qualificationReceipt']?['ETag']",
        'ownershipCommit': own + "?['ETag']"}
    closing_checks = []
    previous = 'ClosureEntry_snapshot'
    for kind in HISTORIES + FILES:
        first = 'ClosureEntry_read_' + kind
        last = 'ClosureEntry_check_' + kind
        route[last] = http(reads[kind]['uri'], previous); previous = last
        if kind in HISTORIES:
            stable = last + '_stable'
            route[stable] = {'type': 'Select', 'inputs': {'from': "@body('" + last + "')?['value']",
                'select': "@union(item(),json('{\"odata.id\":null}'))"}, 'runAfter': {last: ['Succeeded']}}
            previous = stable
            closing_checks += ["empty(body('" + name + "')?['" + key + "'])" for name in (first, last)
                               for key in ('nextLink', 'odata.nextLink', '@odata.nextLink', '@nextLink')]
            closing_checks.append(equal("setProperty(body('" + first + "'),'value',body('" + first + "_stable'))",
                                        "setProperty(body('" + last + "'),'value',body('" + stable + "'))"))
        else:
            row = "body('" + first + "')"
            closing_checks += [equal(row + "?['UniqueId']", uid[kind]),
                               equal(row + "?['ETag']", pin_tokens[kind]),
                               'not(empty(' + row + "?['ETag']))", 'not(equals(' + row + "?['ETag'],'*'))",
                               equal("union(" + row + ",json('{\"odata.id\":null}'))",
                                     "union(body('" + last + "'),json('{\"odata.id\":null}'))")]
    route['ClosureEntry_case_after'] = http(case_uri, previous)
    closing_checks += [equal("outputs('ClosureEntry_case_after')?['headers']?['ETag']", token),
        equal("union(body('ClosureEntry_case_after'),json('{\"odata.id\":null}'))",
              "union(" + case + ",json('{\"odata.id\":null}'))"),
        equal("body('ClosureEntry_read_source')?['UIVersionLabel']", prepared + "?['file']?['nativeVersion']"),
        equal("int(body('ClosureEntry_read_source')?['Length'])", 'int(' + prepared + "?['file']?['Length'])"),
        equal("concat(" + _literal(origin) + ",body('ClosureEntry_read_source')?['ServerRelativeUrl'])", scope + "?['DocumentReference']"),
        equal("concat(" + _literal(origin) + ",body('ClosureEntry_read_issued')?['ServerRelativeUrl'])",
              "first(body('Closure_selected_publication'))?['PublicationURL']"),
        "not(empty(body('ClosureEntry_read_sourceContent')?['$content']))",
        equal("body('ClosureEntry_read_sourceContent')?['$content']", "body('ClosureEntry_read_issuedContent')?['$content']"),
        equal("int(body('ClosureEntry_read_source')?['Length'])", "int(body('ClosureEntry_read_issued')?['Length'])"),
        equal("outputs('ClosureEntry_snapshot')?['dateContent']", "outputs('Closure_date_record')")]
    closing_checks += [equal(observed+"?['nextReviewDate']", "outputs('Closure_date_record')?['reviewDate']"),
                       equal(observed+"?['nextReviewRuleReference']", "outputs('Closure_date_record')?['ruleReference']")]
    for kind in ('source', 'issued'):
        content = "body('ClosureEntry_read_" + kind + "Content')?['$content']"
        padding = "if(endsWith(" + content + ",'=='),2,if(endsWith(" + content + ",'='),1,0))"
        byte_length = 'sub(div(mul(length(' + content + '),3),4),' + padding + ')'
        closing_checks += [equal('mod(length(' + content + '),4)', '0'),
                           equal(byte_length, "int(body('ClosureEntry_read_" + kind + "')?['Length'])")]
    # A binding is a set of fresh read locations and observations, not write
    # authority. The next component must revalidate them around journal/write.
    binding_result = comp({'bindingsCollected': True,
        'closureWriteReady': False, 'case': '@' + case, 'caseETag': '@' + token,
        'caseItemUri': case_uri, 'observation': '@' + observed,
        'evidenceReads': reads, 'evidence': "@outputs('ClosureEntry_snapshot')",
        'historyWrappers': {kind: "@setProperty(body('ClosureEntry_check_" + kind + "'),'value',body('ClosureEntry_check_" + kind + "_stable'))" for kind in HISTORIES},
        'caseWriteCount': 0, 'closurePerformed': False, 'realPolicyEffects': False})
    # Keep individual expressions bounded even when complete opaque metadata and
    # all sixteen current reads are carried through to the canonical writer.
    validations = []
    previous = 'ClosureEntry_case_after'
    for index in range(0, len(closing_checks), 10):
        name = 'ClosureEntry_frame_' + str(index // 10)
        route[name] = comp(both(closing_checks[index:index + 10]), previous)
        validations.append(equal("outputs('" + name + "')", 'true')); previous = name
    route['ClosureEntry_frame_valid'] = gate(validations,
        {'ClosureEntry_binding_result': binding_result},
        'Case, evidence token/content or complete history changed; no closure write', previous)
    # Validate every file identity before using it in a native URI. Split the
    # GUID checks into separate actions to stay below native expression limits.
    # Read specifications evaluate to data, never executable caller expressions.
    locator = route.pop('ClosureEntry_proof_locator')
    proof_work = {'ClosureEntry_proof_locator': locator}
    previous = 'ClosureEntry_proof_locator'
    for kind, value in uid.items():
        name = 'ClosureEntry_key_' + kind
        proof_work[name] = comp('@' + guid(value), previous)
        identifiers.append(equal("outputs('" + name + "')", 'true'))
        previous = name
    proof_work['ClosureEntry_file_keys'] = gate(identifiers, route, 'Invalid authoritative evidence identity', previous)
    work['ClosureEntry_case_verified'] = gate(case_checks,
        {'ClosureEntry_proof_path': gate(proof_checks, proof_work, 'Unsafe recorded publication proof path')},
        'Current full case identity, status or opaque token changed', 'ClosureEntry_case')
    result = {'ClosureEntry_initial': gate(initial, work, 'Fresh prepared/closure/ownership context required')}
    audit_actions({'actions': result})
    return result


def _compile_transition_template(context, binding):
    """Compile canonical code only; no scaffold value may enter emitted data."""
    from build_prepared_closure_transition import build_actions
    marker = 'COMPILER_CLOSURE_ONLY'
    guid = lambda n: 'ffffffff-ffff-4fff-8fff-' + format(n, '012x')
    data = b'COMPILER_CLOSURE_ONLY; never a runtime evidence record'
    reads, evidence = {}, {}
    for index, key in enumerate(HISTORIES + FILES, 1):
        collection = key in HISTORIES
        reads[key] = {'uri': binding[key+'CollectionUri'] if collection else
            "_api/web/GetFileById('" + guid(index) + "')", 'collection': collection}
        evidence[key] = [] if collection else {'UniqueId':guid(index), 'ETag':marker,
                                               'UIVersionLabel':'1.0', 'Length':len(data)}
    for key, target in CONTENTS.items():
        reads[key] = {'uri':reads[target]['uri']+'/$value', 'collection':False}
        evidence[key] = {'$content':base64.b64encode(data).decode()} if key!='dateContent' else {'reviewDate':'2099-01-01'}
    observation = {'closureEvidenceConsistent':True,'nextReviewDateProvenanceConsistent':True,
        'nextOccurrencePrerequisitesConsistent':True,
        'preparedScope':{'CaseUID':'LC-FICTIONAL-OP-'+marker, 'DocumentSHA256':hashlib.sha256(data).hexdigest()},
        'issuedFile':{key:evidence['issued'][key] for key in ('UniqueId','ETag')},
        'selectedEvents':{role:marker+'_'+role for role in
            ('committee','officer','coordinator','authorisation','publication','implementation','verification')},
        'nextReviewDate':'2099-01-01','nextReviewRuleReference':'fictional://'+marker,
        'nextReviewEvidenceFileUID':evidence['date']['UniqueId']}
    folder = binding.get('journalFolder', '')
    if (not folder.startswith(urlsplit(binding['siteUrl']).path.rstrip('/')+'/')
            or any(char in folder for char in ("'", '..', '%', '?', '#', '\\'))):
        raise ValueError('Existing same-site closure journal folder required')
    config = {'qualificationOnly':True,'requestReference':'LC04-'+marker,
        'expectedCaseUID':observation['preparedScope']['CaseUID'], 'expectedCaseETag':marker,
        'expectedCaseStatus':'Ownership accepted — FICTIONAL',
        'caseItemUri':binding['caseListUri']+'(2147483647)',
        'folderUri':"_api/web/GetFolderByServerRelativePath(decodedurl='"+folder+"')",
        'expectedObservation':observation,'evidenceReads':reads,'expectedEvidence':evidence}
    return build_actions(context, config), config


def build_initial_transition(context, binding, historical_frame_action=None):
    """Bind the canonical first-write graph to checked runtime observations.

    No native I/O occurs. The journal, conditional MERGE, after-proof and commit
    code comes from the unchanged canonical builder. Its replay/recovery code is
    preserved, but a separately verified historical entry must still supply the
    original initial contract before those paths are operationally reachable.
    This component deliberately requires the current initial binding collector.
    """
    field = binding.get('closureReferenceField')
    schema = context['properties']['definition']['triggers']['manual']['inputs']['schema']
    if (not isinstance(field,str) or not re.fullmatch(r'text_[0-9]+',field)
            or schema.get('properties',{}).get(field,{}).get('type')!='string'):
        raise ValueError('Existing explicit string closure-request field required')
    graph, config = _compile_transition_template(context, binding)
    nodes = _flatten(graph)
    result = "outputs('ClosureEntry_binding_result')"
    contract = "outputs('ClosureEntry_write_contract')"
    request = "string(coalesce(triggerBody()?['"+field+"'],''))"
    checks = ["startsWith("+request+",'LC04-')",'greater(length('+request+'),5)',
        'lessOrEquals(length('+request+'),80)', 'equals(trim('+request+'),'+request+')',
        'equals(uriComponent('+request+'),'+request+')',"not(contains("+request+",'..'))",
        'equals('+result+"?['bindingsCollected'],true)", 'equals('+result+"?['closureWriteReady'],false)"]
    checks += ['not(contains('+request+','+_literal(char)+'))' for char in ("'",'!','*','~','(',')')]
    payload = {'kind':'fictional-prepared-closure-contract-v1', 'requestReference':'@'+request,
        'runtimeTraceVersion':1,
        'CaseUID':'@'+result+"?['case']?['CaseUID']", 'caseItemUri':'@'+result+"?['caseItemUri']",
        'initialCaseETag':'@'+result+"?['caseETag']", 'initialCaseStatus':'@'+result+"?['case']?['caseStatus']",
        'observation':'@'+result+"?['observation']", 'evidenceReads':'@'+result+"?['evidenceReads']",
        'historyWrappers':'@'+result+"?['historyWrappers']",
        'patch':{'caseStatus':'Review closed — FICTIONAL'}, 'realPolicyEffects':False}
    entry = {'ClosureEntry_validate_write': {'type':'If', 'expression':'@and('+','.join(checks)+')',
        'runAfter':{'ClosureEntry_initial':['Succeeded']},
        'actions':{'ClosureEntry_write_contract':{'type':'Compose','inputs':payload,'runAfter':{}}},
        'else':{'actions':{'ClosureEntry_refuse_write':{'type':'Terminate','runAfter':{},
            'inputs':{'runStatus':'Failed','runError':{'code':'ClosureBindingUnavailable',
                'message':'A safe closure request and this execution\'s current authoritative binding frame are required. No closure write attempted; retain existing evidence.'}}}}}}}
    if historical_frame_action is not None:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',historical_frame_action) or type(binding.get('runtimeClosureTraceVersion')) is not int or binding['runtimeClosureTraceVersion']!=1:
            raise ValueError('Explicit version-one historical frame action required')
        history="outputs('"+historical_frame_action+"')";ready="equals("+history+"?['historicalContinuityConsistent'],true)"
        branch=entry['ClosureEntry_validate_write']['actions']
        branch['ClosureEntry_fresh_contract']=branch.pop('ClosureEntry_write_contract')
        branch['ClosureEntry_write_contract']={'type':'Compose','runAfter':{'ClosureEntry_fresh_contract':['Succeeded']},
            'inputs':'@if('+ready+','+history+"?['originalContract'],outputs('ClosureEntry_fresh_contract'))"}
        extra="if("+ready+",and(equals("+result+"?['evidenceReads'],"+history+"?['originalContract']?['evidenceReads']),equals("+result+"?['caseItemUri'],"+history+"?['originalContract']?['caseItemUri'])),true)"
        gate=entry['ClosureEntry_validate_write'];gate['expression']='@and('+gate['expression'][1:]+','+extra+')'
    nodes['Cycle_contract']['inputs']='@'+contract
    nodes['Cycle_contract']['runAfter']={'ClosureEntry_validate_write':['Succeeded']}
    nodes['Cycle_expected_evidence']['inputs']=('@if('+ready+','+history+"?['afterProof']?['evidence'],"+result+"?['evidence'])") if historical_frame_action else '@'+result+"?['evidence']"
    for prefix in ('Cycle_current','Cycle_prewrite','Cycle_after'):
        for key in HISTORIES + FILES + tuple(CONTENTS):
            nodes[prefix+'_'+key]['inputs']['parameters']['parameters/uri']='@'+contract+"?['evidenceReads']?['"+key+"']?['uri']"
    for name in ('Cycle_case','Cycle_case_prewrite','Cycle_case_after','Cycle_apply_closure'):
        nodes[name]['inputs']['parameters']['parameters/uri']='@'+contract+"?['caseItemUri']"
    folder = config['folderUri']; ref = config['requestReference']
    # Only generated HTTP URI leaves are transformed. Raw proofs, contracts and
    # human text are never searched/replaced or interpreted as expressions.
    for node in nodes.values():
        if node.get('type')!='OpenApiConnection': continue
        params=node['inputs']['parameters'];uri=params['parameters/uri']
        if ref not in uri: continue
        matched=False
        for kind in ('before','after','commit'):
            suffix='-'+kind+'.json'
            forms=[(folder+"/Files?$filter=Name eq 'LC04-closure-"+ref+suffix+"'",folder+"/Files?$filter=Name eq 'LC04-closure-",suffix+"'"),
                   (folder+"/Files('LC04-closure-"+ref+suffix+"')/$value",folder+"/Files('LC04-closure-",suffix+"')/$value"),
                   (folder+"/Files/add(url='LC04-closure-"+ref+suffix+"',overwrite=false)",folder+"/Files/add(url='LC04-closure-",suffix+"',overwrite=false)")]
            for expected,start,end in forms:
                if uri==expected:
                    params['parameters/uri']='@concat('+_literal(start)+','+contract+"?['requestReference'],"+_literal(end)+')'
                    matched=True;break
            if matched:break
        if not matched:raise ValueError('Canonical closure journal URI changed')
    expected_uid=_literal(config['expectedCaseUID'])
    expr=nodes['Cycle_reads_valid']['inputs']
    if expr.count(expected_uid)!=1:raise ValueError('Canonical closure identity guard changed')
    nodes['Cycle_reads_valid']['inputs']=expr.replace(expected_uid,contract+"?['CaseUID']")
    expr=nodes['Cycle_validate_initial']['expression']
    for key,target in [('expectedCaseETag','initialCaseETag'),('expectedCaseStatus','initialCaseStatus')]:
        literal=_literal(config[key])
        if expr.count(literal)!=1:raise ValueError('Canonical closure initial guard changed')
        expr=expr.replace(literal,contract+"?['"+target+"']")
    nodes['Cycle_validate_initial']['expression']=expr
    # Keep the canonical committer runId unchanged. Origin and committer are
    # separate versioned facts when recovery commits proofs from an earlier run.
    for prefix,before in [('First_','Cycle_first_stored_before'),('Recovery_','Cycle_before_record')]:
        commit=nodes[prefix+'Cycle_commit_payload']['inputs']
        commit.update(runtimeTraceVersion=1,originRunId="@outputs('"+before+"')?['runId']",
                      committedByRun="@workflow()?['run']?['name']")
    recovery=nodes['Cycle_verify_recovery']
    recovery['expression']="@and("+recovery['expression'][1:]+",not(empty(outputs('Cycle_before_record')?['runId'])),equals(outputs('Cycle_before_record')?['runId'],outputs('Cycle_after_record')?['runId']))"
    # Preserve complete history wrappers as well as the canonical row snapshots
    # across collection, the prewrite check and the after-write observation.
    for name,prefix in [('Cycle_reads_valid','Cycle_current'),('Cycle_verify_prewrite','Cycle_prewrite'),('Cycle_verify_after','Cycle_after')]:
        node=nodes[name];field_name='inputs' if name=='Cycle_reads_valid' else 'expression'
        checks=[]
        for kind in HISTORIES:
            current="setProperty(body('"+prefix+'_'+kind+"'),'value',body('"+prefix+'_'+kind+"_stable'))"
            checks.append('equals('+current+','+contract+"?['historyWrappers']?['"+kind+"'])")
        node[field_name]='@and('+node[field_name][1:]+','+','.join(checks)+')'
    read_holds=nodes['Cycle_hold_reads']['actions']
    if len(read_holds)!=1 or next(iter(read_holds.values()))['type']!='Compose':
        raise ValueError('Canonical read-hold receipt changed')
    next(iter(read_holds.values()))['inputs']['historyWrappersMatch']='@and('+','.join(
        "equals(setProperty(body('Cycle_current_"+kind+"'),'value',body('Cycle_current_"+kind+"_stable')),"+contract+"?['historyWrappers']?['"+kind+"'])" for kind in HISTORIES)+')'
    encoded=json.dumps(graph)
    if 'COMPILER_CLOSURE_ONLY' in encoded or 'ffffffff-ffff-4fff-8fff-' in encoded or '(2147483647)' in encoded:
        raise ValueError('Compile-only closure scaffold survived runtime adaptation')
    entry.update(graph)
    combined={**build_binding_reads(context,binding,historical_frame_action),**entry}
    audit_actions({'actions':combined})
    return entry


def build_initial_entry(case_work, binding):
    """Prepare a separate stopped closure-operation candidate, never deploy it.

    Reuse the existing context/preparation stage exactly; omit its unrelated
    writers and fixed closure routes. This is a candidate shape for an explicitly
    assigned native target, not permission to replace the case-work flow. A
    historical replay/recovery entry still requires its own verified adaptation.
    """
    from build_native_completed_review import build_current_closure_observer
    if case_work['properties'].get('state')!='Stopped':
        raise ValueError('Retained stopped case-work reference required')
    source=case_work['properties']['definition']
    required={'Resolve_context','Route_preparation_check'}
    if not required <= source['actions'].keys():
        raise ValueError('Existing context/preparation entrypoints required')
    references=case_work['properties']['connectionReferences']
    if set(references)!={'shared_sharepointonline'}:
        raise ValueError('Existing SharePoint-only connection required')
    out={'properties':{'displayName':'PPG Lifecycle | FICTIONAL closure operation', 'state':'Stopped',
                      'connectionReferences':copy.deepcopy(references),'definition':copy.deepcopy(source)}}
    definition=out['properties']['definition'];trigger=definition['triggers']['manual']
    schema=trigger['inputs']['schema']
    if (trigger.get('kind')!='Button' or set(schema['properties'])!={'text','text_6'}
            or set(schema['required'])!={'text','text_6'}):
        raise ValueError('Existing two-field manual case-work form required')
    fields=(binding.get('closureReferenceField'),binding.get('dateEvidenceField'))
    if (len(set(fields))!=2 or any(not isinstance(x,str) or not re.fullmatch(r'text_[0-9]+',x)
                                 or x in schema['properties'] for x in fields)):
        raise ValueError('Distinct available closure-request and date-evidence fields required')
    for field,title in zip(fields,('Closure request reference','Next review evidence file identity')):
        schema['properties'][field]={'type':'string','title':title,'x-ms-dynamically-added':True,'x-ms-content-hint':'TEXT'}
    schema['required']+=list(fields)
    schema['properties']['text']['description']='Enter Close review. Fictional qualification only; no publication or authority granted.'
    trigger['runtimeConfiguration']={'concurrency':{'runs':1}}
    actions={name:copy.deepcopy(action) for name,action in source['actions'].items()
             if name in required or name in ('Held_case_context_error','Hold_unverified_case_context')}
    actions['Validate_closure_operation']={'type':'If','runAfter':{},
        'expression':"@equals(triggerBody()?['text'],'Close review')",
        # The If itself gates Resolve_context. No output consumes a success
        # marker; keep this branch empty to conserve the native action limit.
        'actions':{},
        'else':{'actions':{'Closure_operation_refused':{'type':'Terminate','runAfter':{},
            'inputs':{'runStatus':'Failed','runError':{'code':'UnsupportedClosureOperation',
                'message':'Choose Close review on the intended fictional case. No other stage is invoked.'}}}}}}
    actions['Resolve_context']['runAfter']={'Validate_closure_operation':['Succeeded']}
    actions['Route_preparation_check']['expression']="@and(equals(triggerBody()?['text'],'Close review'),equals(outputs('Selected_case_context')?['contextValid'],true))"
    actions['Route_preparation_check']['runAfter']={'Resolve_context':['Succeeded']}
    definition['actions']=actions
    selection=build_current_closure_observer(out,binding)
    selection['CurrentClosure_validate']['runAfter']={'Route_preparation_check':['Succeeded']}
    actions.update(selection)
    collector=build_binding_reads(out,binding)
    collector['ClosureEntry_initial']['runAfter']={'CurrentClosure_observe':['Succeeded']}
    actions.update(collector)
    actions.update(build_initial_transition(out,binding))
    _check_entry_limits(definition)
    unresolved=action_references(actions)-_flatten(actions).keys()
    if unresolved:
        raise ValueError('Unresolved closure entry prerequisites: '+','.join(sorted(unresolved)))
    return out


def build_historical_frame(context, binding):
    """Read versioned original journals and bind them to the current native case.

    GET-only prerequisite, not replay success or permission to commit. Missing
    after-proof or commit is represented explicitly; only a matching durable
    before/after pair may be offered to separately checked receipt-only recovery.
    No URI or initial token from journal JSON is executed or rebased.
    """
    if type(binding.get('runtimeClosureTraceVersion')) is not int or binding['runtimeClosureTraceVersion']!=1:
        raise ValueError('Explicit version-one historical trace consumer required')
    # Reuse the existing source/target validation without emitting its collector.
    build_binding_reads(context,binding)
    template=_flatten(context['properties']['definition']['actions'])['Read_selected_case']
    folder=binding.get('journalFolder','');site=binding['siteUrl'];collection=binding['caseListUri']
    if not folder.startswith(urlsplit(site).path.rstrip('/')+'/') or any(c in folder for c in ("'",'..','%','?','#','\\')):
        raise ValueError('Existing same-site historical journal folder required')
    field=binding.get('closureReferenceField');date_field=binding.get('dateEvidenceField')
    fields=context['properties']['definition']['triggers']['manual']['inputs']['schema']['properties']
    if any(not isinstance(f,str) or not re.fullmatch(r'text_[0-9]+',f) or fields.get(f,{}).get('type')!='string' for f in (field,date_field)):
        raise ValueError('Existing closure and date lookup fields required')
    request="string(coalesce(triggerBody()?['"+field+"'],''))"
    selected="outputs('Selected_case_context')"
    def eq(a,b):return 'equals('+a+','+b+')'
    def allof(parts):return '@and('+','.join(parts)+')'
    def comp(data,previous=None):return {'type':'Compose','inputs':data,'runAfter':{previous:['Succeeded']} if previous else {}}
    def get(uri,previous=None):
        out=copy.deepcopy(template);p=out['inputs']['parameters'];p.update({'parameters/uri':uri,'parameters/method':'GET','parameters/headers':{'Accept':'application/json;odata=minimalmetadata'}});p.pop('parameters/body',None)
        out['inputs']['retryPolicy']={'type':'none'};out['runAfter']={previous:['Succeeded']} if previous else {};return out
    def parse(name):return "@if(contains(body('"+name+"'),'$content'),json(base64ToString(body('"+name+"')?['$content'])),json(string(body('"+name+"'))))"
    def stable(v):return 'union('+v+",json('{\"odata.id\":null}'))"
    def protected(v):return 'union('+v+",json('{\"odata.id\":null,\"odata.etag\":null,\"Modified\":null,\"EditorId\":null,\"OData__UIVersionString\":null,\"caseStatus\":null}'))"
    def held(reason):return comp({'historicalContinuityConsistent':False,'closurePerformed':False,'caseWriteCount':None,'reconcileBeforeRetry':True,'realPolicyEffects':False,'reason':reason})
    initial=[eq(selected+"?['contextValid']",'true'),"startsWith("+request+",'LC04-')",'greater(length('+request+'),5)','lessOrEquals(length('+request+'),80)',
        eq('trim('+request+')',request),eq('uriComponent('+request+')',request),"not(contains("+request+",'..'))",
        eq("body('Read_selected_case')?['caseStatus']","'Review closed — FICTIONAL'")]
    initial+=['not(contains('+request+','+_literal(c)+'))' for c in ("'",'!','*','~','(',')')]
    root="_api/web/GetFolderByServerRelativePath(decodedurl='"+folder+"')/Files"
    work={};previous=None
    names={}
    for kind in ('before','after','commit'):
        name='ClosureHistory_find_'+kind;names[kind]="concat('LC04-closure-',"+request+",'-"+kind+".json')"
        uri='@concat('+_literal(root+"?$filter=Name eq '")+','+names[kind]+','+_literal("'&$select=UniqueId,ETag,UIVersionLabel,Length,Name")+')'
        work[name]=get(uri,previous);previous=name
    complete=[]
    for kind in names:
        source="body('ClosureHistory_find_"+kind+"')"
        complete+=['empty('+source+"?['"+key+"'])" for key in ('nextLink','odata.nextLink','@odata.nextLink','@nextLink')]
        complete.append(('lessOrEquals' if kind=='commit' else 'equals')+'(length('+source+"?['value']),1)")
    reads={};last=None;metadata_checks=[]
    for kind in names:
        found="first(body('ClosureHistory_find_"+kind+"')?['value'])"
        # File identity is a native SP.File GUID from the exact name query. Still
        # validate/escape it before using it in a new path, never use file JSON.
        uid="string(coalesce("+found+"?['UniqueId'],''))";stripped=uid
        for c in '0123456789abcdefABCDEF-':stripped='replace('+stripped+','+_literal(c)+",'')"
        valid=[eq('length('+uid+')','36'),eq(stripped,"''"),eq("length(replace("+uid+",'-',''))",'32')]
        valid+=['if(equals(length('+uid+'),36),equals(substring('+uid+','+str(i)+",1),'-'),false)" for i in (8,13,18,23)]
        valid+=[eq(found+"?['Name']",names[kind]),"not(empty("+found+"?['ETag']))","not(equals("+found+"?['ETag'],'*'))",
                'greater(int('+found+"?['Length']),0)",'lessOrEquals(int('+found+"?['Length']),4194304)"]
        check='ClosureHistory_key_'+kind
        work[check]=comp('@if(equals(length(body(\'ClosureHistory_find_'+kind+"\')?['value']),1),and("+','.join(valid)+'),'+('true' if kind=='commit' else 'false')+')',previous);previous=check
        complete.append(eq("outputs('"+check+"')",'true'))
        prefix='ClosureHistory_'+kind
        uri='@concat('+_literal("_api/web/GetFileById('")+','+found+"?['UniqueId'],"+_literal("')")+')'
        group={prefix+'_before':get(uri[:-1]+','+_literal('?$select=UniqueId,ETag,UIVersionLabel,Length,Name')+')'),
            prefix+'_content':get(uri[:-1]+",'/$value')",prefix+'_before'),
            prefix+'_after':get(uri[:-1]+','+_literal('?$select=UniqueId,ETag,UIVersionLabel,Length,Name')+')',prefix+'_content'),
            prefix+'_record':comp(parse(prefix+'_content'),prefix+'_after')}
        if kind=='commit':
            reads['ClosureHistory_optional_commit']={'type':'If','expression':"@equals(length(body('ClosureHistory_find_commit')?['value']),1)",'runAfter':{last:['Succeeded']},'actions':group,'else':{'actions':{}}}
            last='ClosureHistory_optional_commit'
        else:
            group[prefix+'_before']['runAfter']={last:['Succeeded']} if last else {};reads.update(group);last=prefix+'_record'
        checks=[eq(stable("body('"+prefix+"_before')"),stable("body('"+prefix+"_after')"))]
        checks += [eq("body('"+prefix+"_after')?['"+key+"']",found+"?['"+key+"']") for key in ('UniqueId','ETag','UIVersionLabel','Length','Name')]
        metadata_checks.append('if(equals(length(body(\'ClosureHistory_find_'+kind+"\')?['value']),1),and("+','.join(checks)+'),'+('true' if kind=='commit' else 'false')+')')
    case_uri='@concat('+_literal(collection+'(')+',string(int('+selected+"?['nativeItemId'])),')')"
    reads['ClosureHistory_current_case']=get(case_uri,last)
    before="outputs('ClosureHistory_before_record')";after="outputs('ClosureHistory_after_record')";commit="outputs('ClosureHistory_commit_record')"
    contract=before+"?['contract']";current="body('ClosureHistory_current_case')";token="outputs('ClosureHistory_current_case')?['headers']?['ETag']"
    checks=metadata_checks+[
        eq(before+"?['kind']","'fictional-prepared-closure-before-v1'"),eq(after+"?['kind']","'fictional-prepared-closure-after-v1'"),
        eq(contract+"?['kind']","'fictional-prepared-closure-contract-v1'"),eq(contract+"?['runtimeTraceVersion']",'1'),eq('string('+contract+"?['runtimeTraceVersion'])","'1'"),
        eq(after+"?['contract']",contract),eq(contract+"?['requestReference']",request),eq(contract+"?['CaseUID']",selected+"?['CaseUID']"),
        eq(contract+"?['caseItemUri']",case_uri[1:]),eq(contract+"?['patch']","json('{\"caseStatus\":\"Review closed — FICTIONAL\"}')"),
        eq(before+"?['beforeCaseETag']",contract+"?['initialCaseETag']"),"not(empty("+contract+"?['initialCaseETag']))","not(equals("+contract+"?['initialCaseETag'],'*'))",
        eq(contract+"?['initialCaseStatus']","'Ownership accepted — FICTIONAL'"),eq(before+"?['beforeCase']?['caseStatus']",contract+"?['initialCaseStatus']"),
        eq(after+"?['afterCase']?['caseStatus']","'Review closed — FICTIONAL'"),eq(current+"?['CaseUID']",selected+"?['CaseUID']"),eq(current+"?['Id']",selected+"?['nativeItemId']"),
        eq(token,selected+"?['caseETag']"),"not(empty("+token+"))","not(equals("+token+",'*'))",eq(after+"?['afterCaseETag']",token),
        'not(equals('+before+"?['beforeCaseETag'],"+after+"?['afterCaseETag']))",
        eq(stable(after+"?['afterCase']"),stable(current)),eq(protected(before+"?['beforeCase']"),protected(after+"?['afterCase']")),
        eq(before+"?['evidence']",after+"?['evidence']"),"not(empty("+before+"?['runId']))",eq(before+"?['runId']",after+"?['runId']"),
        eq(before+"?['evidence']?['originalSource']?['UniqueId']",selected+"?['sourcePins']?['UniqueId']"),eq(before+"?['evidence']?['originalSource']?['ETag']",selected+"?['sourcePins']?['ETag']"),
        eq(before+"?['evidence']?['sourceBaseline']?['UniqueId']",selected+"?['baselineUniqueId']"),eq(before+"?['evidence']?['sourceBaseline']?['ETag']",selected+"?['baselineETag']"),
        eq(contract+"?['observation']?['preparedScope']?['CaseUID']",selected+"?['CaseUID']"),
        eq(contract+"?['observation']?['preparedScope']?['DocumentReference']","decodeUriComponent(string("+current+"?['evidenceDraftLink']))"),
        eq(contract+"?['observation']?['nextReviewEvidenceFileUID']","string(coalesce(triggerBody()?['"+date_field+"'],''))")]
    committed=[eq(commit+"?['kind']","'fictional-prepared-closure-commit-v1'"),eq(commit+"?['contract']",contract),eq(commit+"?['beforeProof']",before),eq(commit+"?['afterProof']",after),
        eq(commit+"?['runtimeTraceVersion']",'1'),eq('string('+commit+"?['runtimeTraceVersion'])","'1'"),eq(commit+"?['originRunId']",before+"?['runId']"),
        "not(empty("+commit+"?['runId']))",eq(commit+"?['committedByRun']",commit+"?['runId']")]
    checks.append("if(equals(length(body('ClosureHistory_find_commit')?['value']),1),and("+','.join(committed)+'),true)')
    # The ownership artifact is independently read and related to this case and
    # original source. A GUID copied into a journal is not ownership evidence.
    owner_meta=before+"?['evidence']?['ownershipCommit']"
    owner_uid='string(coalesce('+owner_meta+"?['UniqueId'],''))";owner_stripped=owner_uid
    for c in '0123456789abcdefABCDEF-':owner_stripped='replace('+owner_stripped+','+_literal(c)+",'')"
    owner_keys=[eq('length('+owner_uid+')','36'),eq(owner_stripped,"''"),eq("length(replace("+owner_uid+",'-',''))",'32')]
    owner_keys+=['if(equals(length('+owner_uid+'),36),equals(substring('+owner_uid+','+str(i)+",1),'-'),false)" for i in (8,13,18,23)]
    owner_uri='@concat('+_literal("_api/web/GetFileById('")+','+owner_meta+"?['UniqueId'],"+_literal("')")+')'
    owner_reads={'ClosureHistory_owner_before':get(owner_uri[:-1]+','+_literal('?$select='+FILE_FIELDS)+')'),
        'ClosureHistory_owner_content':get(owner_uri[:-1]+",'/$value')",'ClosureHistory_owner_before'),
        'ClosureHistory_owner_after':get(owner_uri[:-1]+','+_literal('?$select='+FILE_FIELDS)+')','ClosureHistory_owner_content'),
        'ClosureHistory_owner_record':comp(parse('ClosureHistory_owner_content'),'ClosureHistory_owner_after')}
    owner="outputs('ClosureHistory_owner_record')"
    checks += [eq(stable("body('ClosureHistory_owner_before')"),stable("body('ClosureHistory_owner_after')")),
               "not(empty(body('ClosureHistory_owner_after')?['ETag']))","not(equals(body('ClosureHistory_owner_after')?['ETag'],'*'))",
               eq(owner+"?['kind']","'fictional-ownership-projection-commit-v1'"),eq(owner+"?['CaseUID']",selected+"?['CaseUID']")]
    checks += [eq("body('ClosureHistory_owner_after')?['"+key+"']",owner_meta+"?['"+key+"']") for key in ('UniqueId','ETag','UIVersionLabel','Length')]
    checks += [eq(owner+"?['context']?['"+key+"']",selected+"?['"+key+"']") for key in ('baselineReference','baselineUniqueId','baselineETag')]
    checks += [eq(owner+"?['context']?['scope']?['"+key+"']",selected+"?['scope']?['"+key+"']") for key in ('CaseUID','DocumentReference','ReviewedVersionRef','DocumentSHA256')]
    from build_prepared_revision_check import CASE_INPUT_FIELDS
    checks += [eq(owner+"?['afterCase']?['"+key+"']",before+"?['beforeCase']?['"+key+"']") for key in CASE_INPUT_FIELDS]
    previous='ClosureHistory_owner_record';flags=[]
    for index in range(0,len(checks),6):
        name='ClosureHistory_check_'+str(index//6);owner_reads[name]=comp(allof(checks[index:index+6]),previous);previous=name;flags.append(eq("outputs('"+name+"')",'true'))
    frame={'historicalContinuityConsistent':True,'nativeObserverQualified':False,
        'originalContract':'@'+contract,'beforeCase':'@'+before+"?['beforeCase']",'afterCase':'@'+after+"?['afterCase']",'currentCase':'@'+current,
        'beforeProof':'@'+before,'afterProof':'@'+after,'currentCaseETag':'@'+token,'ownershipMetadata':"@body('ClosureHistory_owner_after')",
        'mode':"@if(equals(length(body('ClosureHistory_find_commit')?['value']),1),'committed-replay','after-proof-recovery')",
        'commit':"@if(equals(length(body('ClosureHistory_find_commit')?['value']),1),"+commit+",json('null'))",
        'freshEvidenceRevalidationRequired':True,'caseWriteCount':0,'closurePerformed':False,'realPolicyEffects':False}
    owner_reads['ClosureHistory_verified']={'type':'If','expression':allof(flags),'runAfter':{previous:['Succeeded']},'actions':{'ClosureHistory_frame':comp(frame)},'else':{'actions':{'ClosureHistory_changed':held('Original request, proofs, source or current protected case differ; retain and reconcile')}}}
    diagnostic=owner_reads['ClosureHistory_verified']['else']['actions']['ClosureHistory_changed']['inputs']
    diagnostic.update(requestMatches='@'+eq(contract+"?['requestReference']",request),
        caseScopeMatches='@'+eq(contract+"?['CaseUID']",selected+"?['CaseUID']"),
        currentHumanContentMatches='@'+eq(stable(after+"?['afterCase']"),stable(current)),
        initialTokenPreserved='@'+eq(before+"?['beforeCaseETag']",contract+"?['initialCaseETag']"),
        sourceBaselineMatches='@'+eq(before+"?['evidence']?['sourceBaseline']?['UniqueId']",selected+"?['baselineUniqueId']"),
        proofOriginMatches='@'+eq(before+"?['runId']",after+"?['runId']"),
        commitTraceMatches="@if(equals(length(body('ClosureHistory_find_commit')?['value']),1),and("+','.join(committed)+'),true)')
    reads['ClosureHistory_owner_key']= {'type':'If','expression':allof(owner_keys),'runAfter':{'ClosureHistory_current_case':['Succeeded']},
        'actions':owner_reads,'else':{'actions':{'ClosureHistory_owner_missing':held('Missing or unsafe retained ownership artifact identity')}}}
    work['ClosureHistory_pair']={'type':'If','expression':allof(complete),'runAfter':{list(work)[-1]:['Succeeded']},'actions':reads,
        'else':{'actions':{'ClosureHistory_incomplete':held('Missing/ambiguous before/after pair or invalid commit metadata; no successful replay and no repeated case mutation')}}}
    out={'ClosureHistory_entry':{'type':'If','expression':allof(initial),'runAfter':{},'actions':work,'else':{'actions':{'ClosureHistory_unavailable':held('Safe original closure reference and resolved closed case required')}}}}
    audit_actions({'actions':out})
    return out


def build_entry_with_history(case_work,binding):
    """Compose initial closure plus version-one closed-case re-entry locally.

    Shared consumers always receive freshly resolved artifacts and observations.
    Only independently read journals can supply the original historical contract;
    the canonical replay/recovery gates still compare the entire fresh frame.
    """
    from build_native_completed_review import build_historical_prepared_reader
    from build_operator_entry import namespace_actions
    if type(binding.get('runtimeClosureTraceVersion')) is not int or binding['runtimeClosureTraceVersion']!=1:
        raise ValueError('Explicit version-one complete closure entry required')
    out=build_initial_entry(case_work,binding);actions=out['properties']['definition']['actions']
    prep=actions['Route_preparation_check']['actions']
    if 'Native_prepared_revision' in action_references(prep):
        raise ValueError('Preparation producer gained an internal receipt dependency')
    def rename_receipt(group):
        for name,node in list(group.items()):
            if name=='Native_prepared_revision':group['ClosureEntry_initial_prepared']=group.pop(name);return True
            for child in (node.get('actions',{}),node.get('else',{}).get('actions',{})):
                if rename_receipt(child):return True
        return False
    if not rename_receipt(prep):raise ValueError('Existing preparation producer receipt required')
    current=actions['Route_preparation_check'];current['expression']="@and("+current['expression'][1:]+",equals(body('Read_selected_case')?['caseStatus'],'Ownership accepted — FICTIONAL'))"
    history=build_historical_frame(out,binding)
    history['ClosureHistory_entry']['runAfter']={'Resolve_context':['Succeeded']}
    # An open case follows the existing initial path; absence of a historical
    # frame there is not an uncertain historical effect.
    history['ClosureHistory_entry']['else']={'actions':{}}
    actions.update(history)
    historical_context=copy.deepcopy(out)
    historical_context['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']['inputs']['parameters']['parameters/headers']={'Accept':'application/json;odata=minimalmetadata'}
    historical_prepared=namespace_actions(build_historical_prepared_reader(historical_context,binding,'ClosureHistory_frame'),'HP_')
    actions['ClosureHistory_preparation']={'type':'If','runAfter':{'ClosureHistory_entry':['Succeeded']},
        'expression':"@equals(outputs('ClosureHistory_frame')?['historicalContinuityConsistent'],true)",
        'actions':historical_prepared,'else':{'actions':{}}}
    actions['Native_prepared_revision']={'type':'Compose',
        'runAfter':{'Route_preparation_check':['Succeeded'],'ClosureHistory_preparation':['Succeeded']},
        'inputs':"@if(equals(outputs('ClosureHistory_frame')?['historicalContinuityConsistent'],true),outputs('HP_Native_prepared_revision'),outputs('ClosureEntry_initial_prepared'))"}
    actions['CurrentClosure_validate']['runAfter']={'Native_prepared_revision':['Succeeded']}
    collector=build_binding_reads(out,binding,'ClosureHistory_frame')
    collector['ClosureEntry_initial']['runAfter']={'CurrentClosure_observe':['Succeeded']}
    actions.update(collector)
    actions.update(build_initial_transition(out,binding,'ClosureHistory_frame'))
    _check_entry_limits(out['properties']['definition'])
    unresolved=action_references(actions)-_flatten(actions).keys()
    if unresolved:raise ValueError('Unresolved historical entry prerequisites: '+','.join(sorted(unresolved)))
    return out
