"""GET-only readiness evidence observation for a same-execution prepared revision.

No assessment, selection by latest date, native writes or progression authority.
Multiple scoped findings/corrections deliberately hold pending explicit resolution.
"""
import copy
import re
from build_consultation_coverage import build_runtime

SCOPE_KEYS = ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')


def build_actions(context, binding):
    template = context['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']
    inputs = template.get('inputs', {}); params = inputs.get('parameters', {}); host = inputs.get('host', {})
    if (template.get('type') != 'OpenApiConnection' or params.get('parameters/method') != 'GET'
            or host.get('apiId') != '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
            or host.get('operationId') != 'HttpRequest' or not host.get('connectionName')
            or not params.get('dataset') or 'parameters/body' in params
            or any(k.lower() in ('x-http-method', 'x-http-method-override') for k in params.get('parameters/headers', {}))):
        raise ValueError('Qualified same-site GET-only case reader required')
    readiness_uri = binding['readinessCollectionUri']; consultation_uri = binding['consultationCollectionUri']
    # Native list GUIDs are privately bound. No query can hide history or fields.
    if not isinstance(readiness_uri, str) or not re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'\)/items", readiness_uri):
        raise ValueError('Complete literal privately bound readiness collection required')
    if readiness_uri == consultation_uri:
        raise ValueError('Separate readiness and consultation collections required')

    def http(uri, previous=None):
        action = copy.deepcopy(template)
        action['inputs']['parameters']['parameters/uri'] = uri
        if uri in (readiness_uri, consultation_uri):
            action['inputs']['parameters']['parameters/headers'] = {'Accept': 'application/json;odata=minimalmetadata'}
        action['runAfter'] = {previous: ['Succeeded']} if previous else {}
        return action
    def comp(value, previous=None):
        return {'type': 'Compose', 'inputs': value, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def query(source, where, previous):
        return {'type': 'Query', 'inputs': {'from': source, 'where': '@' + where}, 'runAfter': {previous: ['Succeeded']}}
    def eq(a, b): return 'equals(' + a + ',' + b + ')'
    def allof(checks): return 'and(' + ','.join(checks) + ')'
    def present(value): return "not(empty(trim(string(coalesce(" + value + ",'')))))"
    def complete(name):
        return ["empty(body('" + name + "')?['odata.nextLink'])", "empty(body('" + name + "')?['@odata.nextLink'])"]
    def stable(name, previous):
        return {'type': 'Select', 'inputs': {'from': "@body('" + name + "')?['value']",
            'select': "@union(item(),json('{\"odata.id\":null}'))"}, 'runAfter': {previous: ['Succeeded']}}

    prepared = "outputs('Native_prepared_revision')"; revision = prepared + "?['preparedRevision']"
    scope = revision + "?['scope']"; ctx = "outputs('Selected_case_context')"
    coverage_reader = http(consultation_uri)
    graph = build_runtime('Readiness_consultation_before', coverage_reader, binding['requiredFictionalRoles'],
        qualified_reader=template, collection_uri=consultation_uri, prefix='Ready_consultation')
    coverage = "outputs('Ready_consultation_Receipt')"
    graph['Readiness_history_before'] = http(readiness_uri, 'Ready_consultation_Runtime_guard')
    graph['Readiness_scope'] = query("@body('Readiness_history_before')?['value']",
        allof([eq("item()?['" + k + "']", scope + "?['" + k + "']") for k in SCOPE_KEYS]), 'Readiness_history_before')
    selected = "first(body('Readiness_scope'))"
    singleton = "equals(length(body('Readiness_scope')),1)"
    # Search the complete history, including cross-version corrections and identity collisions.
    graph['Readiness_identity_rows'] = query("@body('Readiness_history_before')?['value']",
        'if(' + singleton + ',' + eq("item()?['EventUID']", selected + "?['EventUID']") + ',false)', 'Readiness_scope')
    graph['Readiness_superseders'] = query("@body('Readiness_history_before')?['value']",
        'if(' + singleton + ',' + eq("item()?['SupersedesEventUID']", selected + "?['EventUID']") + ',false)', 'Readiness_identity_rows')
    checks = [eq(selected + "?['Finding']", "'Ready for decision'"), eq(selected + "?['FictionalTest']", 'true'),
        "contains(createArray('None recorded','Resolved')," + selected + "?['ConditionsState'])",
        "empty(" + selected + "?['SupersedesEventUID'])", "equals(length(body('Readiness_identity_rows')),1)",
        "equals(length(body('Readiness_superseders')),0)"]
    checks += ["greater(int(coalesce(" + selected + "?['Id'],0)),0)",
        present(selected + "?['GUID']"), present(selected + "?['odata.etag']"),
        "not(equals(" + selected + "?['odata.etag'],'*'))"]
    checks += [present(selected + "?['" + k + "']") for k in
               ('EventUID', 'AssessorName', 'AssessedOn', 'FindingSummary', 'EvidenceReference')]
    checks += ["if(" + present(selected + "?['AssessedOn']") + ',lessOrEquals(ticks(' + selected + "?['AssessedOn']),ticks(utcNow())),false)"]
    graph['Readiness_finding_consistent'] = comp('@if(' + singleton + ',' + allof(checks) + ',false)', 'Readiness_superseders')
    graph['Readiness_stable_before'] = stable('Readiness_history_before', 'Readiness_finding_consistent')
    graph['Readiness_consultation_stable_before'] = stable('Readiness_consultation_before', 'Readiness_stable_before')
    graph['Readiness_history_after'] = http(readiness_uri, 'Readiness_consultation_stable_before')
    graph['Readiness_stable_after'] = stable('Readiness_history_after', 'Readiness_history_after')
    graph['Readiness_consultation_after'] = http(consultation_uri, 'Readiness_stable_after')
    graph['Readiness_consultation_stable_after'] = stable('Readiness_consultation_after', 'Readiness_consultation_after')

    def file_uri(identifier):
        return "@concat('_api/web/GetFileById(',decodeUriComponent('%27')," + identifier + ",decodeUriComponent('%27'),')?$select=UniqueId,ETag')"
    case_uri = params['parameters/uri'].replace('?$select=Id,CaseUID,linkedDocumentUIDs,sourceBaselineRef,accountableRole,caseStatus', '')
    reads = {'case': case_uri, 'draft': file_uri(revision + "?['file']?['UniqueId']"),
        'receipt': file_uri(revision + "?['qualificationReceipt']?['UniqueId']"),
        'template': file_uri(revision + "?['template']?['UniqueId']"),
        'source': file_uri(ctx + "?['sourcePins']?['UniqueId']"), 'baseline': file_uri(ctx + "?['baselineUniqueId']")}
    last = 'Readiness_consultation_stable_after'
    for label, uri in reads.items():
        name = 'Readiness_' + label + '_final'; graph[name] = http(uri, last); last = name
    current = [eq("outputs('Readiness_case_final')?['headers']?['ETag']", prepared + "?['currentCaseETag']"),
        eq("body('Readiness_case_final')?['CaseUID']", scope + "?['CaseUID']"),
        eq("body('Readiness_case_final')?['evidenceDraftLink']", scope + "?['DocumentReference']")]
    for label, pin in [('draft', revision + "?['file']"), ('receipt', revision + "?['qualificationReceipt']"),
                       ('template', revision + "?['template']"), ('source', ctx + "?['sourcePins']")]:
        current += [eq("body('Readiness_" + label + "_final')?['" + k + "']", pin + "?['" + k + "']") for k in ('UniqueId', 'ETag')]
    current += [eq("body('Readiness_baseline_final')?['UniqueId']", ctx + "?['baselineUniqueId']"),
                eq("body('Readiness_baseline_final')?['ETag']", ctx + "?['baselineETag']")]
    history = complete('Readiness_history_before') + complete('Readiness_history_after')
    history += complete('Readiness_consultation_before') + complete('Readiness_consultation_after')
    history += [eq("body('Readiness_stable_before')", "body('Readiness_stable_after')"),
                eq("body('Readiness_consultation_stable_before')", "body('Readiness_consultation_stable_after')")]
    graph['Readiness_context_current'] = comp('@' + allof(current + history), last)
    graph['Native_readiness_observation'] = comp({
        'readinessEvidenceConsistent': '@' + allof(["equals(outputs('Readiness_context_current'),true)",
            "equals(outputs('Readiness_finding_consistent'),true)", eq(coverage + "?['coverageHistoryComplete']", 'true')]),
        'technicalConsultationCoverageComplete': '@' + eq(coverage + "?['coverageHistoryComplete']", 'true'),
        'nativeContextRevalidated': "@equals(outputs('Readiness_context_current'),true)",
        'preparedScope': '@' + scope,
        'scopedFindingCount': "@length(body('Readiness_scope'))",
        'selectedEventUID': '@if(' + singleton + ',' + selected + "?['EventUID'],null)",
        'recordedFindingConsistent': "@equals(outputs('Readiness_finding_consistent'),true)",
        'writeCount': 0, 'contentReadinessGranted': False, 'actorAuthorityQualified': False,
        'progressionGranted': False, 'policyApproved': False, 'ordinaryUserAccessQualified': False,
        'realPolicyEffects': False,
        'runId': "@workflow()?['run']?['name']", 'asOfUtc': '@utcNow()',
        'reason': "@if(not(equals(outputs('Readiness_context_current'),true)),'Native context or complete history changed; hold',if(not(equals(" + coverage + "?['coverageHistoryComplete'],true)),'Required fictional consultation coverage is incomplete; hold',if(not(equals(outputs('Readiness_finding_consistent'),true)),'One complete unique unsuperseded exact-version Ready for decision finding is required; hold','Recorded fictional evidence is consistent; no readiness assessment, authority or progression granted')))",
        'limits': 'Read-only fictional evidence consistency, not a content assessment. Missing, multiple, adverse, incomplete, superseded or changed histories hold; no latest-date choice or Not applicable bypass. Snapshot only; revalidate before a later action.'
    }, 'Readiness_context_current')
    guard = [eq(prepared + "?['preparationQualified']", 'true'), eq(prepared + "?['preparedArtifactQualified']", 'true'),
             eq(prepared + "?['originalSourceIsPreparedRevision']", 'false'), eq(ctx + "?['contextValid']", 'true'),
             eq(scope + "?['CaseUID']", ctx + "?['CaseUID']")]
    held = {'readinessEvidenceConsistent': False, 'writeCount': 0, 'contentReadinessGranted': False,
        'progressionGranted': False, 'policyApproved': False,
        'reason': 'No qualified prepared revision or complete stable evidence; readiness not established.'}
    return {'Check_prepared_readiness': {'type': 'If', 'expression': '@' + allof(guard), 'runAfter': {},
        'actions': graph, 'else': {'actions': {'Held_unprepared_readiness': comp(held)}}},
        'Held_readiness_error': {'type': 'Compose', 'inputs': held,
            'runAfter': {'Check_prepared_readiness': ['Failed', 'TimedOut', 'Skipped']}}}
