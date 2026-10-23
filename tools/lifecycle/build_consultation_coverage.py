"""Emit read-only native consultation coverage actions; no deployment or native I/O.

The caller must first verify the prepared artifact, its separate native file
identity, provenance, current version and case ownership. Scope literals come from
that qualified binding, never operator input. This graph cannot qualify a draft,
actor authority, content readiness or permission to progress.
"""
import copy
import re
from urllib.parse import unquote

SCOPE_KEYS = ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')


def build(read_name, read_action, prepared_scope, original_scope, required_roles,
          *, qualified_reader, collection_uri, prefix='Consultation_coverage'):
    for scope in (prepared_scope, original_scope):
        if not isinstance(scope, dict) or any(not isinstance(scope.get(k), str) or not scope[k].strip() for k in SCOPE_KEYS):
            raise ValueError('Explicit complete prepared and original scopes required')
        if not re.fullmatch(r'[a-fA-F0-9]{64}', scope['DocumentSHA256']):
            raise ValueError('Exact document digest required')
    if (prepared_scope['CaseUID'] != original_scope['CaseUID']
            or not prepared_scope['CaseUID'].startswith('LC-FICTIONAL-OP-')
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', prepared_scope['CaseUID'])
            or prepared_scope['DocumentReference'] == original_scope['DocumentReference']):
        raise ValueError('Separate prepared artifact for the same fictional occurrence required')
    if (not isinstance(required_roles, list) or not required_roles
            or any(not isinstance(role, str) or not role.startswith('FICTIONAL ') or len(role) > 255 for role in required_roles)
            or len(set(required_roles)) != len(required_roles)):
        raise ValueError('Explicit unique required fictional roles required; no empty-plan pass')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,23}', prefix) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}', read_name):
        raise ValueError('Safe native action names required')
    inputs = read_action.get('inputs', {})
    params = inputs.get('parameters', {})
    host = inputs.get('host', {})
    uri = params.get('parameters/uri', '')
    reference_inputs = qualified_reader.get('inputs', {})
    reference_host = reference_inputs.get('host', {})
    reference_dataset = reference_inputs.get('parameters', {}).get('dataset')
    def decoded(value):
        for _ in range(4):
            next_value = unquote(value)
            if next_value == value:
                return value
            value = next_value
        raise ValueError('Excessively encoded collection URI')
    if not isinstance(uri, str) or not isinstance(collection_uri, str):
        raise ValueError('Literal qualified collection URI required')
    base = decoded(collection_uri)
    path, separator, query = decoded(uri).partition('?')
    allowed_filter = "$filter=CaseUID eq '" + prepared_scope['CaseUID'] + "'"
    if (read_action.get('type') != 'OpenApiConnection'
            or host.get('apiId') != '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
            or host.get('operationId') != 'HttpRequest'
            or not reference_host.get('connectionName')
            or any(host.get(k) != reference_host.get(k) for k in ('apiId', 'operationId', 'connectionName'))
            or not reference_dataset or params.get('dataset') != reference_dataset
            or params.get('parameters/method') != 'GET'
            or 'parameters/body' in params
            or any(k.lower() in ('x-http-method', 'x-http-method-override') for k in params.get('parameters/headers', {}))
            or read_action.get('runtimeConfiguration', {}).get('paginationPolicy') is not None
            or not base.startswith('_api/web/lists') or '?' in base or not base.endswith('/items')
            or path != base or (separator and query != allowed_filter)):
        raise ValueError('Qualified untruncated GET collection reader required')

    def lit(value):
        return "'" + value.replace("'", "''") + "'"
    def conjunction(clauses):
        return 'and(' + ','.join(clauses) + ')'
    def step(suffix):
        return prefix + '_' + suffix
    def compose(value, previous):
        return {'type': 'Compose', 'inputs': value, 'runAfter': {previous: ['Succeeded']}}
    def query(source, expression, previous):
        return {'type': 'Query', 'inputs': {'from': source, 'where': '@' + expression},
                'runAfter': {previous: ['Succeeded']}}
    def text_present(expression):
        return 'not(empty(trim(string(coalesce(' + expression + ",'')))))"

    actions = {read_name: copy.deepcopy(read_action)}
    scope_name, ids_name, problems_name = (step(s) for s in ('Scope', 'Ids', 'Problems'))
    scoped = "@body('" + scope_name + "')"
    scope_checks = ["equals(item()?['" + k + "']," + lit(prepared_scope[k]) + ')' for k in SCOPE_KEYS]
    scope_checks += ["equals(item()?['EventKind'],'Consultation')"]
    actions[scope_name] = query("@body('" + read_name + "')?['value']", conjunction(scope_checks), read_name)
    actions[ids_name] = {'type': 'Select', 'inputs': {'from': scoped, 'select': {'EventUID': "@item()?['EventUID']"}},
                         'runAfter': {scope_name: ['Succeeded']}}
    problems = ["not(equals(item()?['FictionalTest'],true))",
        "not(contains(createArray(" + ','.join(lit(r) for r in required_roles) + "),item()?['SubjectRole']))",
        "not(empty(item()?['SupersedesEventUID']))",
        "not(contains(createArray('Pending response','Responded'),item()?['RecordState']))",
        "not(contains(createArray('None recorded','Resolved'),item()?['ConditionsState']))",
        "not(" + text_present("item()?['EventUID']") + ')']
    actions[problems_name] = query(scoped, 'or(' + ','.join(problems) + ')', ids_name)
    previous = problems_name
    complete_actions, role_results = [], []
    for index, role in enumerate(required_roles):
        rows, requests, responses, complete = (step('R' + str(index) + '_' + s) for s in ('Rows', 'Requests', 'Responses', 'Complete'))
        actions[rows] = query(scoped, "equals(item()?['SubjectRole']," + lit(role) + ')', previous)
        actions[requests] = query("@body('" + rows + "')", "and(equals(item()?['RecordState'],'Pending response'),empty(item()?['ParentEventUID']))", rows)
        actions[responses] = query("@body('" + rows + "')", "not(equals(item()?['RecordState'],'Pending response'))", requests)
        req, resp = "first(body('" + requests + "'))", "first(body('" + responses + "'))"
        checks = ["equals(" + resp + "?['RecordState'],'Responded')",
            "equals(" + resp + "?['ParentEventUID']," + req + "?['EventUID'])",
            "not(equals(" + resp + "?['EventUID']," + req + "?['EventUID']))"]
        for item in (req, resp):
            checks += ["equals(" + item + "?['FictionalTest'],true)",
                "empty(" + item + "?['SupersedesEventUID'])",
                "contains(createArray('None recorded','Resolved')," + item + "?['ConditionsState'])"]
            checks += [text_present(item + "?['" + key + "']") for key in
                       ('EventUID', 'ActorName', 'OccurredOn', 'Summary', 'EvidenceReference', 'NextAction')]
        checks += [text_present(resp + "?['ResponseSummary']")]
        dates_present = conjunction([text_present(req + "?['OccurredOn']"), text_present(resp + "?['OccurredOn']")])
        checks += ['if(' + dates_present + ',and(greaterOrEquals(ticks(' + resp + "?['OccurredOn']),ticks(" + req + "?['OccurredOn'])),lessOrEquals(ticks(" + resp + "?['OccurredOn']),ticks(utcNow()))),false)"]
        shape = conjunction(["equals(length(body('" + rows + "')),2)",
            "equals(length(body('" + requests + "')),1)", "equals(length(body('" + responses + "')),1)"])
        actions[complete] = compose('@if(' + shape + ',' + conjunction(checks) + ',false)', responses)
        complete_actions.append(complete)
        role_results.append({'SubjectRole': role, 'complete': "@outputs('" + complete + "')",
            'requestCount': "@length(body('" + requests + "'))", 'responseCount': "@length(body('" + responses + "'))"})
        previous = complete

    # A next link means unobserved conflicting evidence could still exist.
    final_checks = ["empty(body('" + read_name + "')?['odata.nextLink'])",
        "empty(body('" + read_name + "')?['@odata.nextLink'])",
        "equals(length(body('" + problems_name + "')),0)",
        "equals(length(body('" + ids_name + "')),length(union(body('" + ids_name + "'),body('" + ids_name + "'))))"]
    final_checks += ["equals(outputs('" + name + "'),true)" for name in complete_actions]
    actions[step('Receipt')] = compose({'technicalCoverageComplete': '@' + conjunction(final_checks),
        'preparedScope': {k: prepared_scope[k] for k in SCOPE_KEYS}, 'requiredRoleResults': role_results,
        'scopeRecordCount': "@length(body('" + scope_name + "'))",
        'problemRecordCount': "@length(body('" + problems_name + "'))",
        'writeCount': 0, 'progressionGranted': False, 'actorAuthorityQualified': False,
        'contentReadinessAssessed': False, 'policyApproved': False,
        'limits': 'Caller must revalidate actual prepared artifact and complete history; corrections and parallel response histories are held.'}, previous)
    return actions


def build_runtime(read_name, read_action, required_roles, *, qualified_reader,
                  collection_uri, prefix='Consultation_coverage'):
    """Read-only runtime coverage for the same execution's prepared-reader output.

    Reuse the strict collection-reader contract above. A complete collection is
    required; arbitrary runtime filters cannot hide adverse records. The caller
    must bracket this snapshot with fresh native context/artifact checks before
    using coverage in any later readiness recording operation.
    """
    case='LC-FICTIONAL-OP-RUNTIME-COVERAGE'
    prepared={'CaseUID':case,'DocumentReference':'fictional://runtime-prepared-document',
              'ReviewedVersionRef':'fictional-runtime-prepared-version','DocumentSHA256':'f'*64}
    original={'CaseUID':case,'DocumentReference':'fictional://runtime-original-document',
              'ReviewedVersionRef':'fictional-runtime-original-version','DocumentSHA256':'e'*64}
    graph=build(read_name,read_action,prepared,original,required_roles,
                qualified_reader=qualified_reader,collection_uri=collection_uri,prefix=prefix)
    # Restrict runtime composition to an unfiltered complete collection. A fixed
    # fixture CaseUID filter accepted by build() cannot represent all selections.
    if '?' in unquote(read_action['inputs']['parameters']['parameters/uri']):
        raise ValueError('Runtime coverage requires the complete literal collection')
    output="outputs('Native_prepared_revision')"
    revision=output+"?['preparedRevision']";scope=revision+"?['scope']"
    replacements={value:scope+"?['"+key+"']" for key,value in prepared.items()}
    def convert(value):
        if isinstance(value,dict):return {key:convert(child) for key,child in value.items()}
        if isinstance(value,list):return [convert(child) for child in value]
        if not isinstance(value,str):return value
        if value in replacements:return '@'+replacements[value]
        for literal,expression in replacements.items():
            value=value.replace("'"+literal+"'",expression)
        return value
    graph=convert(graph)
    # This is an event-history result only. A later fresh native bracket must
    # establish whether the snapshot is usable for the current revision.
    result=graph[prefix+'_Receipt']['inputs']
    result['coverageHistoryComplete']=result.pop('technicalCoverageComplete')
    result['nativeContextRevalidated']=False
    result['limits']='Read-only prepared-scope history assessment; revalidate native draft/receipt/template/case/source after this read before consuming it.'
    checks=["equals("+output+"?['preparationQualified'],true)",
            "equals("+output+"?['consultationOpenable'],true)",
            "equals("+output+"?['originalSourceIsPreparedRevision'],false)",
            "equals("+scope+"?['CaseUID'],outputs('Selected_case_context')?['CaseUID'])",
            "not(equals("+scope+"?['DocumentReference'],"+revision+"?['originalSourceScope']?['DocumentReference']))"]
    return {prefix+'_Runtime_guard':{'type':'If','expression':'@and('+','.join(checks)+')',
        'runAfter':{},'actions':graph,'else':{'actions':{prefix+'_Held':{'type':'Compose','runAfter':{},
        'inputs':{'coverageHistoryComplete':False,'nativeContextRevalidated':False,'writeCount':0,
                  'progressionGranted':False,'reason':'No qualified separate prepared revision exists in this execution; no history read attempted'}}}}}}
