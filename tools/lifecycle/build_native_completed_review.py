"""Compose runtime completed-review selection and guarded readback.

No authentication, tenant I/O or deployment occurs here. A selected closure is
untrusted evidence, not authority. Complete reviewed configuration connects native
historical proof, source/prepared revision and full scoped closure checks to the
canonical next-review writer. Local composition does not qualify native execution,
ordinary-user access or actor authority. Partial configurations explicitly hold.
No connector-specific historical-run client or caller-supplied qualification flag
is required or accepted.
"""
import copy
import re
import hashlib
from urllib.parse import urlsplit
from build_prepared_closure_check import calendar_date_expression


class NativeProducerRouteUnavailable(ValueError):
    """An unsupported producer-envelope route was supplied to the resolver."""


def _literal(value):
    return "'" + value.replace("'", "''") + "'"


def build_actions(reference, binding, producer_route=None):
    """Read a runtime-selected occurrence; hold before unqualified progression.

    ``reference`` is the retained initiation flow, not an uploaded receipt.
    ``binding`` contains only reviewed site/list/folder/source configuration.
    Historical producer clients and caller-injected action graphs are unsupported.
    Native qualification and writer integration remain open, explicitly.
    """
    if producer_route is not None:
        raise NativeProducerRouteUnavailable('Use authoritative inline revalidation; producer-route assertions are unsupported')
    allowed = {'qualificationOnly', 'siteUrl', 'closureFolder', 'caseListUri',
               'allowedSources', 'completedReferenceField', 'evidenceFolder', 'assuranceCollectionUri',
               'readinessCollectionUri', 'consultationCollectionUri', 'requiredFictionalRoles',
               'purposeReferences', 'artifactFolderRelative', 'caseEvidenceFieldType', 'templateFileUniqueId',
               'runtimeClosureTraceVersion', 'additionalPreparedArtifactFolder'}
    if not isinstance(binding, dict) or set(binding) - allowed:
        raise ValueError('Only reviewed completed-review configuration is accepted')
    if 'runtimeClosureTraceVersion' in binding and (type(binding['runtimeClosureTraceVersion']) is not int or binding['runtimeClosureTraceVersion']!=1):
        raise ValueError('Explicit supported runtime closure trace version required')
    # Reuse the existing reader configuration validation without consuming its
    # trusted-envelope graph. This does not confer native qualification.
    _reader_actions(binding, 'Unused_configuration_validation', 'Unused')
    refs = reference.get('properties', {}).get('connectionReferences', {})
    connection = refs.get('shared_sharepointonline', {})
    if (not connection.get('connectionName')
            or connection.get('id') != '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'):
        raise ValueError('Retain the existing SharePoint connection reference')
    collections = []
    for key in ('assuranceCollectionUri', 'readinessCollectionUri', 'consultationCollectionUri'):
        uri = binding.get(key, '')
        if not re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'\)/items", uri):
            raise ValueError('Complete authoritative collection required: ' + key)
        collections.append(uri)
    if len(set(collections + [binding['caseListUri']])) != 4:
        raise ValueError('Separate authoritative case and event collections required')
    graph = _linearize_refusing_pipeline(_candidate_actions(binding))
    observer_keys = {'evidenceFolder', 'requiredFictionalRoles', 'purposeReferences', 'artifactFolderRelative', 'caseEvidenceFieldType', 'templateFileUniqueId'}
    if observer_keys & set(binding):
        if not observer_keys <= set(binding):
            raise ValueError('Complete authoritative observer configuration required')
        site = urlsplit(binding['siteUrl'])
        owned = site.path.rstrip('/') + '/PPG Review Evidence/Templates'
        write_folder = binding['evidenceFolder']
        read_folder = binding['closureFolder']
        if (write_folder != owned or not (read_folder == owned or read_folder.startswith(owned + '/'))
                or any(char in read_folder for char in ("'", '..', '?', '#', '%', '\\'))
                or read_folder.endswith('/')):
            raise ValueError('Separate existing same-site closure-read and operator-evidence-write folders required')
        result = _attach_authoritative_observers(reference, binding, graph)
        if _source_review_requirements(binding) is not None:
            from build_selected_event_routes import audit_actions
            if audit_actions({'actions': result})['actionCount'] > 500:
                raise ValueError('Source-specific completed-review route exceeds native action limit')
        return result
    return graph


def _attach_authoritative_observers(reference, binding, graph):
    """Connect actual runtime origin/prepared/history readers, never JSON flags."""
    from build_operator_entry import namespace_actions, _flatten
    graph = copy.deepcopy(graph)
    graph.pop('Completed_observer_unavailable')
    context_action = 'Unused_runtime_comparison'
    origin = _reader_actions(binding, context_action, 'Unused')
    nodes = _flatten(origin)
    ctx = "outputs('" + context_action + "')"
    select = nodes['Completed_select']
    tail = ",equals(" + ctx + "?['qualified'],true),equals(" + ctx + "?['flowId'],'Unused'),not(empty(" + ctx + "?['runId'])))"
    if not select['expression'].endswith(tail):
        raise ValueError('Origin selection contract changed')
    select['expression'] = select['expression'][:-len(tail)] + ')'
    record = "outputs('Completed_record')"
    gate = nodes['Completed_validate_record']
    head = "@and(equals(" + record + ',' + ctx + "?['commit']),equals(body('Completed_commit_content')?['$content']," + ctx + "?['commitContentBase64']),"
    if not gate['expression'].startswith(head):
        raise ValueError('Origin comparison contract changed')
    gate['expression'] = '@and(' + gate['expression'][len(head):]
    # All replacements below target this generated guard only. No uploaded JSON
    # or human text is rewritten, and no native producer claim is introduced.
    gate['expression'] = gate['expression'].replace(ctx + "?['runId']", record + "?['runId']")
    gate['expression'] = gate['expression'].replace(ctx + "?['commitMetadata']", "body('Completed_candidate_after')")
    gate['expression'] = '@and(' + gate['expression'][1:] + ",equals(outputs('Completed_record'),outputs('Completed_candidate_record')),equals(body('Completed_commit_content')?['$content'],body('Completed_candidate_content')?['$content']))"
    nodes['Completed_context']['inputs'].pop('qualified')
    nodes['Completed_context']['inputs']['identityAndSourceConsistent'] = True
    namespaced = namespace_actions(origin, 'Origin_', literal_inputs=())
    namespaced['Origin_Completed_select']['runAfter'] = {'Completed_candidate': ['Succeeded']}
    graph.update(namespaced)
    def comp(value, after):
        return {'type': 'Compose', 'inputs': value, 'runAfter': {after: ['Succeeded']}}
    def fail(code):
        return {'type': 'Terminate', 'inputs': {'runStatus': 'Failed',
            'runError': {'code': code, 'message': 'Authoritative completed-review evidence is incomplete or changed; no new occurrence.'}}, 'runAfter': {}}
    def guard(checks, yes, code, after):
        return {'type': 'If', 'expression': '@and(' + ','.join(checks) + ')',
                'actions': yes, 'else': {'actions': {code: fail(code)}},
                'runAfter': {after: ['Succeeded']}}
    origin_context = "outputs('Origin_Completed_context')"
    graph['Completed_origin_ready'] = guard([
        'equals(' + origin_context + "?['identityAndSourceConsistent'],true)"],
        {'Completed_origin_passed': comp(True, None)}, 'Completed_origin_invalid', 'Origin_Completed_select')
    # comp(None) means an empty dependency at a new branch, not a bogus action.
    graph['Completed_origin_ready']['actions']['Completed_origin_passed']['runAfter'] = {}
    original_scope = {k: '@' + origin_context + "?['originalSource']?['" + source_key + "']" for k, source_key in
                      [('DocumentReference', 'DocumentReference'), ('ReviewedVersionRef', 'ReviewedVersionRef'), ('DocumentSHA256', 'sha256')]}
    original_scope['CaseUID'] = '@' + origin_context + "?['closedCase']?['CaseUID']"
    selected = {'contextValid': True, 'CaseUID': '@' + origin_context + "?['closedCase']?['CaseUID']",
        'caseETag': '@' + origin_context + "?['closedCaseETag']", 'scope': original_scope,
        'sourcePins': '@' + origin_context + "?['originalSourceMetadata']",
        'baselineUniqueId': '@' + origin_context + "?['sourceBaselineMetadata']?['UniqueId']",
        'baselineETag': '@' + origin_context + "?['sourceBaselineMetadata']?['ETag']"}
    graph['Selected_case_context'] = comp(selected, 'Completed_origin_ready')
    graph['Parse_baseline'] = comp("@outputs('Origin_Completed_baseline')", 'Selected_case_context')
    # Exact same-site, GET-only templates for the unchanged canonical readers.
    template = copy.deepcopy(graph['Completed_authoritative_case_after'])
    template['runAfter'] = {}
    origin_nodes = _flatten(namespaced)
    source_template = copy.deepcopy(origin_nodes['Origin_Completed_originalSource_before'])
    baseline_template = copy.deepcopy(origin_nodes['Origin_Completed_sourceBaseline_before'])
    context = {'properties': {'connectionReferences': copy.deepcopy(reference['properties']['connectionReferences']),
        'definition': {'actions': {'Resolve_context': {'type': 'Scope', 'runAfter': {}, 'actions': {
            'Read_selected_case': template,
            'Verify_baseline_boundary': {'type': 'If', 'expression': '@true', 'runAfter': {}, 'actions': {
                'Read_baseline_before': baseline_template,
                'Verify_request': {'type': 'If', 'expression': '@true', 'runAfter': {}, 'actions': {
                    'Read_source_before': source_template}, 'else': {'actions': {}}}}, 'else': {'actions': {}}}}}}}}}
    prepared = build_historical_prepared_reader(context, binding)
    prepared['Check_prepared_ownership']['runAfter'] = {'Parse_baseline': ['Succeeded']}
    graph.update(prepared)
    observer = build_runtime_closure_observer(context, binding)
    for action in observer.values():
        if not action.get('runAfter'):
            action['runAfter'] = {'Check_prepared_ownership': ['Succeeded']}
    graph.update(observer)
    observation = "outputs('Native_closure_observation')"
    checks = ['equals(' + observation + "?['" + key + "'],true)" for key in
              ('closureEvidenceConsistent', 'nextReviewDateProvenanceConsistent', 'nextOccurrencePrerequisitesConsistent')]
    # All candidate occurrence/source/date/issued assertions must agree with this
    # run's freshly recomputed canonical observer, never substitute for it.
    retained = "outputs('Completed_candidate_record')?['contract']?['observation']"
    for key in ('preparedScope', 'selectedEvents', 'issuedFile', 'nextReviewEvidenceFileUID', 'nextReviewDate', 'nextReviewRuleReference'):
        checks.append('equals(' + observation + "?['" + key + "']," + retained + "?['" + key + "'])")
    # Pin the selected occurrence's retained event records, including opaque
    # tokens and human fields. Unrelated occurrences may be appended without
    # invalidating this review; complete-current-history collision/supersession
    # and parent checks remain in the canonical observer.
    evidence = "outputs('Completed_candidate_record')?['afterProof']?['evidence']"
    # A held preparation/observer does not provide history arrays. Refuse before
    # querying them rather than converting missing observations into empty data.
    graph['Completed_require_observer'] = guard(checks[:3],
        {'Completed_observer_passed': {'type': 'Compose', 'inputs': True, 'runAfter': {}}},
        'Completed_observer_unavailable_now', 'Closure_check_chain')
    previous = 'Completed_require_observer'
    from build_prepared_closure_check import CHAIN
    for role in CHAIN:
        name = 'Completed_retained_' + role
        selected_uid = retained + "?['selectedEvents']?['" + role + "']"
        graph[name] = {'type': 'Query', 'inputs': {'from': '@' + evidence + "?['assurance']",
            'where': "@equals(item()?['EventUID']," + selected_uid + ')'},
            'runAfter': {previous: ['Succeeded']}}
        current = "body('Closure_selected_" + role + "')"
        saved = "body('" + name + "')"
        normalized = lambda value: 'union(' + value + ",json('{\"odata.id\":null}'))"
        checks.append('if(and(equals(length(' + current + '),1),equals(length(' + saved + '),1)),equals(' +
                      normalized('first(' + current + ')') + ',' + normalized('first(' + saved + ')') + '),false)')
        previous = name
    scope = "outputs('Native_prepared_revision')?['preparedRevision']?['scope']"
    for kind, current_action in [('readiness', 'Closure_Readiness_history_after'),
                                  ('consultation', 'Closure_Readiness_consultation_after')]:
        pair = []
        for side, values in [('retained', '@' + evidence + "?['" + kind + "']"),
                             ('current', "@body('" + current_action + "')?['value']")]:
            name = 'Completed_' + side + '_' + kind
            where = '@and(' + ','.join("equals(item()?['" + key + "']," + scope + "?['" + key + "'])" for key in
                ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')) + ')'
            graph[name] = {'type': 'Query', 'inputs': {'from': values, 'where': where}, 'runAfter': {previous: ['Succeeded']}}
            stable = name + '_stable'
            graph[stable] = {'type': 'Select', 'inputs': {'from': "@body('" + name + "')",
                'select': "@union(item(),json('{\"odata.id\":null}'))"}, 'runAfter': {name: ['Succeeded']}}
            previous = stable; pair.append(stable)
        checks.append("equals(body('" + pair[0] + "'),body('" + pair[1] + "'))")
    previous = _revalidate_histories(graph, binding, 'Completed_prewrite_history', previous)
    checks.append("equals(outputs('" + previous + "'),true)")
    graph['Completed_evidence_ready'] = guard(checks,
        build_runtime_next_writer(reference, binding),
        'Completed_evidence_invalid', previous)
    return graph


def _revalidate_histories(group, binding, prefix, previous):
    """Bracket effects with complete same-run histories; no filtered shortcuts."""
    checks = []
    expected = {'assurance': 'Closure_assurance_stable_after',
                'readiness': 'Closure_Readiness_stable_after',
                'consultation': 'Closure_Readiness_consultation_stable_after'}
    for kind, snapshot in expected.items():
        name = prefix + '_' + kind
        group[name] = {'type': 'OpenApiConnection', 'inputs': {
            'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
                     'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
            'parameters': {'dataset': binding['siteUrl'], 'parameters/method': 'GET',
                           'parameters/uri': binding[kind + 'CollectionUri'],
                           'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata'}},
            'retryPolicy': {'type': 'none'}}, 'runAfter': {previous: ['Succeeded']}}
        stable = name + '_stable'
        group[stable] = {'type': 'Select', 'inputs': {'from': "@body('" + name + "')?['value']",
            'select': "@union(item(),json('{\"odata.id\":null}'))"}, 'runAfter': {name: ['Succeeded']}}
        checks += ["empty(body('" + name + "')?['" + key + "'])" for key in ('odata.nextLink', '@odata.nextLink', 'nextLink', '@nextLink')]
        checks.append("equals(body('" + stable + "'),body('" + snapshot + "'))")
        previous = stable
    name = prefix + '_consistent'
    group[name] = {'type': 'Compose', 'inputs': '@and(' + ','.join(checks) + ')', 'runAfter': {previous: ['Succeeded']}}
    return name


def _compile_writer_template(reference, binding):
    """Obtain canonical writer code using explicit compile-only placeholders.

    The canonical builder currently requires frozen occurrence values. This
    internal scaffold supplies its required shape, then only its code subtree is
    reused. Every occurrence/receipt/source binding in that subtree is replaced
    at explicit generated nodes before emission. Placeholder records are never
    runtime evidence, persisted inputs or qualification, and never leave here.
    """
    import base64
    import json
    from build_next_review_occurrence import build as canonical
    try:
        writer = reference['properties']['definition']['actions']['Validate_operator_input']['actions']['Source_guard']['actions']['Verify_request']['actions']['Ensure_case']['actions']['Create_case']
        target = writer['inputs']['parameters']
    except (KeyError, TypeError) as error:
        raise ValueError('Retained canonical initiation writer reference required') from error
    if (writer.get('type') != 'OpenApiConnection' or target.get('parameters/method') != 'POST'
            or target.get('dataset') != binding['siteUrl']
            or target.get('parameters/uri') != binding['caseListUri']):
        raise ValueError('Next review must retain the existing native case site/list target')
    source = copy.deepcopy(binding['allowedSources'][0])
    uid = lambda n: '00000000-0000-4000-8000-' + str(n).zfill(12)
    parent = {'Id': 1, 'CaseUID': 'LC-FICTIONAL-OP-COMPILER-PLACEHOLDER',
              'caseStatus': 'Review closed — FICTIONAL'}
    scope = {'CaseUID': parent['CaseUID'], 'DocumentReference': binding['siteUrl'] + '/COMPILER-PLACEHOLDER.docx',
             'ReviewedVersionRef': 'COMPILER-PLACEHOLDER', 'DocumentSHA256': 'a' * 64}
    date = {'FictionalTest': True, 'notOperational': True, 'policyAuthorityGranted': False,
            'scope': scope, 'reviewDate': '2099-01-01', 'ruleReference': 'fictional://COMPILER-PLACEHOLDER'}
    issued = {'UniqueId': uid(80), 'ETag': '"COMPILER-PLACEHOLDER-issued,1"'}
    observation = {'closureEvidenceConsistent': True, 'nextReviewDateProvenanceConsistent': True,
        'nextOccurrencePrerequisitesConsistent': True, 'preparedScope': scope, 'issuedFile': issued,
        'selectedEvents': {role: 'COMPILER-PLACEHOLDER-' + role for role in
            ('committee', 'officer', 'coordinator', 'authorisation', 'publication', 'implementation', 'verification')},
        'nextReviewEvidenceFileUID': uid(81), 'nextReviewDate': date['reviewDate'], 'nextReviewRuleReference': date['ruleReference']}
    contract = {'kind': 'fictional-prepared-closure-contract-v1', 'CaseUID': parent['CaseUID'],
                'initialCaseETag': '"COMPILER-PLACEHOLDER-before,1"', 'initialCaseStatus': 'Ownership accepted — FICTIONAL',
                'patch': {'caseStatus': 'Review closed — FICTIONAL'}, 'observation': observation}
    closed = {'kind': 'fictional-prepared-closure-commit-v1', 'contract': contract, 'realPolicyEffects': False,
              'beforeProof': {'kind': 'fictional-prepared-closure-before-v1', 'contract': contract,
                              'beforeCaseETag': contract['initialCaseETag'], 'beforeCase': {'caseStatus': contract['initialCaseStatus']}},
              'afterProof': {'kind': 'fictional-prepared-closure-after-v1', 'contract': contract,
                             'afterCase': {**parent, 'odata.id': None}, 'afterCaseETag': '"COMPILER-PLACEHOLDER-after,1"'}}
    def file(value, identifier):
        raw = json.dumps(value).encode()
        return {'record': value, 'contentBase64': base64.b64encode(raw).decode(),
                'SHA256': hashlib.sha256(raw).hexdigest(), 'metadata': {'UniqueId': identifier,
                'ETag': '"COMPILER-PLACEHOLDER-file,1"', 'UIVersionLabel': '1.0', 'Length': len(raw)}}
    config = {'qualificationOnly': True, 'canonicalInputs': {
        'text': 'LC02-OP-COMPILER-PLACEHOLDER', 'text_1': 'OCC-COMPILER-PLACEHOLDER',
        'text_2': 'FICTIONAL compile-only', 'text_3': 'FICTIONAL compile-only',
        'text_4': 'FICTIONAL Case9 next-occurrence test role'}, 'targetDateFieldType': 'Text',
        'completedReview': {'case': parent, 'preparedScope': scope, 'issuedFile': issued, 'originalSource': source},
        'completedCaseETag': closed['afterProof']['afterCaseETag'], 'completedCaseUri': binding['caseListUri'] + '(1)',
        'date': file(date, uid(81)), 'closureCommit': file(closed, uid(82)),
        'initiation': {'qualificationOnly': True, 'source': source, 'siteUrl': binding['siteUrl'],
                       'evidenceFolder': binding['evidenceFolder'], 'caseListUri': binding['caseListUri']}}
    shape = copy.deepcopy(reference)
    shape['properties']['definition']['actions']['Compiler_case_template'] = {
        'type': 'OpenApiConnection', 'inputs': {'parameters': {'dataset': binding['siteUrl'],
        'parameters/uri': binding['caseListUri'] + '(1)'}}}
    generated = canonical(shape, config)
    return generated['properties']['definition']['actions']['Validate_operator_input']['actions']['Next_validate_origin']['actions']


def build_runtime_next_writer(reference, binding):
    """Reuse canonical intent/create/readback/recovery/receipt code dynamically.

    This is a local fictional candidate, not a deployed or accepted route. The
    caller must gate it with this execution's complete authoritative observer.
    Original initiation and canonical next-review builders remain untouched.
    """
    from build_operator_entry import _flatten, namespace_actions
    import json
    graph = _compile_writer_template(reference, binding)
    nodes = _flatten(graph)
    ctx = "outputs('Origin_Completed_context')"; source = ctx + "?['originalSource']"
    case = ctx + "?['closedCase']"; commitmeta = "body('Completed_candidate_after')"
    date_meta = ctx + "?['dateMetadata']"
    request = nodes['Request']['inputs']
    for key, source_key in [('DocumentUID', 'DocumentUID'), ('DocumentReference', 'DocumentReference'),
                            ('ReviewedVersionRef', 'ReviewedVersionRef'), ('DocumentSHA256', 'sha256')]:
        request[key] = '@' + source + "?['" + source_key + "']"
    request['completedReview'] = {'CaseUID': '@' + case + "?['CaseUID']", 'closedCaseETag': '@' + ctx + "?['closedCaseETag']",
        'closureCommit': {'metadata': '@' + commitmeta},
        'preparedScope': "@outputs('Native_closure_observation')?['preparedScope']",
        'issuedFile': "@outputs('Native_closure_observation')?['issuedFile']",
        'dateEvidence': {'metadata': '@' + date_meta},
        'reviewDate': "@outputs('Next_date_record')?['reviewDate']", 'ruleReference': "@outputs('Next_date_record')?['ruleReference']",
        'originalSourceAdoptedFromIssuedRevision': False, 'realPolicyEffects': False}
    def by_id(value, suffix):
        return '@concat(' + _literal("_api/web/GetFileById('") + ',' + value + ',' + _literal("')" + suffix) + ')'
    for name, suffix in [('Read_source_before', '?$select=UniqueId,ETag'), ('Read_source_content', '/$value'),
                         ('Read_source_after', '?$select=UniqueId,ETag'), ('Recheck_source', '?$select=UniqueId,ETag')]:
        nodes[name]['inputs']['parameters']['parameters/uri'] = by_id(source + "?['UniqueId']", suffix)
    source_text = "if(contains(body('Read_source_content'),'$content'),base64ToString(body('Read_source_content')?['$content']),string(body('Read_source_content')))"
    nodes['Source_guard']['expression'] = "@and(equals(body('Read_source_before')?['ETag']," + source + "?['ETag']),equals(body('Read_source_after')?['ETag']," + source + "?['ETag']),equals(" + source_text + ',' + source + "?['content']))"
    payload = nodes['Case_payload']['inputs']
    payload['linkedDocumentUIDs'] = '@string(createArray(' + source + "?['DocumentUID']))"
    payload['evidenceDraftLink'] = '@' + source + "?['DocumentReference']"
    folder = "_api/web/GetFolderByServerRelativePath(decodedurl='" + binding['evidenceFolder'] + "')"
    key = "trim(triggerBody()?['text'])"
    # Exactly the seven generated intent/receipt path nodes; no raw proof or
    # human string is scanned/replaced. Request names are already runtime-native.
    paths = {
        'Next_find_intent': ('LC02-next-case-intent-', '.json', 'find'),
        'Next_create_intent': ('LC02-next-case-intent-', '.json', 'create'),
        'Next_read_intent': ('LC02-next-case-intent-', '.json', 'read'),
        'Next_reconcile_intent_read': ('LC02-next-case-intent-', '.json', 'read'),
        'Next_find_receipt': ('LC02-next-review-receipt-', '.json', 'find'),
        'Next_create_receipt': ('LC02-next-review-receipt-', '.json', 'create'),
        'Next_read_receipt': ('LC02-next-review-receipt-', '.json', 'read')}
    for name, (prefix, suffix, mode) in paths.items():
        filename = 'concat(' + _literal(prefix) + ',' + key + ',' + _literal(suffix) + ')'
        before, after = {'find': (folder + "/Files?$filter=Name eq '", "'"),
                         'create': (folder + "/Files/add(url='", "',overwrite=false)"),
                         'read': (folder + "/Files('", "')/$value")}[mode]
        nodes[name]['inputs']['parameters']['parameters/uri'] = '@concat(' + _literal(before) + ',' + filename + ',' + _literal(after) + ')'
    nodes['Next_parent_final']['inputs']['parameters']['parameters/uri'] = '@concat(' + _literal(binding['caseListUri'] + '(') + ',string(' + case + "?['Id']),')')"
    for name, metadata in [('date', date_meta), ('commit', commitmeta)]:
        nodes['Next_' + name + '_final']['inputs']['parameters']['parameters/uri'] = by_id(metadata + "?['UniqueId']", '?$select=UniqueId,ETag,UIVersionLabel,Length')
    nodes['Next_receipt_payload']['inputs']['closureCommitUniqueId'] = '@' + commitmeta + "?['UniqueId']"
    receipt = nodes['Native_initiation_receipt']['inputs']
    receipt['completedCaseUID'] = '@' + case + "?['CaseUID']"
    receipt['closureCommitUniqueId'] = '@' + commitmeta + "?['UniqueId']"
    final = nodes['Final_source_guard']
    before = final['expression']
    original_etag = _literal(binding['allowedSources'][0]['ETag'])
    if before.count(original_etag) != 1 or before.count(_literal('"COMPILER-PLACEHOLDER-after,1"')) != 1:
        raise ValueError('Canonical late source/parent guard changed')
    final['expression'] = before.replace(original_etag, source + "?['ETag']").replace(_literal('"COMPILER-PLACEHOLDER-after,1"'), ctx + "?['closedCaseETag']")
    # Event histories are mutable until access qualification proves otherwise.
    # Revalidate immediately before the durable receipt and once after saving it;
    # drift can never produce a qualified completion, even after partial effects.
    checked = nodes['Verify_case']['actions']
    before_history = _revalidate_histories(checked, binding, 'Next_history_before_receipt', 'Next_case_before_stable')
    final['runAfter'] = {before_history: ['Succeeded']}
    final['expression'] = '@and(' + final['expression'][1:] + ",equals(outputs('" + before_history + "'),true))"
    error = final['else']['actions']['Refuse_source_drift']['inputs']['runError']
    error['code'] = 'NextReviewEvidenceChangedAfterInitiation'
    error['message'] = 'Source, completed review, case or event evidence changed; preserve partial results and reconcile before retry.'
    final_actions = final['actions']
    after_history = _revalidate_histories(final_actions, binding, 'Next_history_after_receipt', 'Next_case_after_stable')
    result = nodes['Native_initiation_receipt']
    previous_qualified = result['inputs']['qualified'][1:]
    qualified = 'and(' + previous_qualified + ",equals(outputs('" + after_history + "'),true))"
    final_actions['Next_completion_verified'] = {'type': 'Compose', 'inputs': '@' + qualified,
        'runAfter': {after_history: ['Succeeded']}}
    qualified = "outputs('Next_completion_verified')"
    result['inputs']['qualified'] = '@' + qualified
    for key in ('caseCreatedCount', 'requestCreatedCount'):
        result['inputs'][key] = '@if(' + qualified + ',' + result['inputs'][key][1:] + ',null)'
    result['inputs']['recoveredExistingCase'] = '@and(' + qualified + ',' + result['inputs']['recoveredExistingCase'][1:] + ')'
    result['inputs']['reconcileBeforeRetry'] = '@not(' + qualified + ')'
    result['inputs']['eventHistoryStableThroughReceipt'] = "@equals(outputs('" + after_history + "'),true)"
    result['runAfter'] = {'Next_completion_verified': ['Succeeded']}
    final_actions['Next_require_verified_completion'] = {
        'type': 'If', 'expression': "@equals(outputs('Native_initiation_receipt')?['qualified'],true)",
        'actions': {'Next_completed': {'type': 'Compose', 'inputs': {
            'nextOccurrenceRecorded': True, 'ownershipAccepted': False, 'realPolicyEffects': False}, 'runAfter': {}}},
        'else': {'actions': {'Next_post_receipt_hold': {'type': 'Terminate',
            'inputs': {'runStatus': 'Failed', 'runError': {'code': 'NextReviewEvidenceChangedAfterReceipt',
                'message': 'Retain the request, intent, case and receipt. Completion is unqualified; reconcile changed evidence before retry. No rollback or automatic resubmit.'}}, 'runAfter': {}}}},
        'runAfter': {'Native_initiation_receipt': ['Succeeded']}}
    # These are dynamic same-execution observations, not compiled proof records.
    def metadata_read(value, after):
        action = copy.deepcopy(nodes['Read_source_before'])
        action['inputs']['parameters']['parameters/uri'] = by_id(value + "?['UniqueId']", '?$select=UniqueId,ETag,UIVersionLabel,Length')
        action['runAfter'] = {after: ['Succeeded']}
        return action
    prerequisite = {
        'Next_expected_case': {'type': 'Compose', 'inputs': '@' + case, 'runAfter': {}},
        'Next_date_record': {'type': 'Compose', 'inputs': '@' + ctx + "?['date']", 'runAfter': {'Next_expected_case': ['Succeeded']}},
        'Next_date_before': metadata_read(date_meta, 'Next_date_record'),
        'Next_commit_before': metadata_read(commitmeta, 'Next_date_before')}
    frame_checks = ["not(equals(concat('LC-FICTIONAL-OP-',trim(triggerBody()?['text_1']))," + case + "?['CaseUID']))"]
    for name, metadata in [('date', date_meta), ('commit', commitmeta)]:
        for key in ['UniqueId', 'ETag', 'UIVersionLabel', 'Length']:
            left = "body('Next_" + name + "_before')?['" + key + "']"
            right = metadata + "?['" + key + "']"
            frame_checks.append('equals(' + ('int(' + left + ')' if key == 'Length' else left) + ',' + ('int(' + right + ')' if key == 'Length' else right) + ')')
    prerequisite['Next_write_frame_current'] = {'type': 'If', 'expression': '@and(' + ','.join(frame_checks) + ')',
        'actions': {'Next_write_frame_passed': {'type': 'Compose', 'inputs': True, 'runAfter': {}}},
        'else': {'actions': {'Next_write_frame_changed': {'type': 'Terminate', 'inputs': {'runStatus': 'Failed',
                    'runError': {'code': 'NextReviewOriginChanged', 'message': 'Completed review changed or occurrence identity was reused; no new writes.'}}, 'runAfter': {}}}},
        'runAfter': {'Next_commit_before': ['Succeeded']}}
    for action in graph.values():
        if not action.get('runAfter'):
            action['runAfter'] = {'Next_write_frame_current': ['Succeeded']}
    prerequisite.update(graph)
    emitted = namespace_actions(prerequisite, 'NextOccurrence_', literal_inputs=())
    # Compile-only occurrence/receipt pins must never survive in executable data.
    encoded = json.dumps(emitted)
    if 'COMPILER-PLACEHOLDER' in encoded or 'Case9' in encoded:
        raise ValueError('Unreplaced compile-only writer binding')
    return emitted


def _linearize_refusing_pipeline(group):
    """Hoist only positive branches whose negative branch terminates execution.

    This retains all guards and dependencies while leaving depth for the real
    prepared/closure observers. A failed guard terminates before the hoisted
    children; a failed read prevents its dependent gate. Other branch shapes are
    deliberately unsupported, rather than assumed safe to flatten.
    """
    result = {}
    def append(siblings, parent=None):
        for name, action in siblings.items():
            if name in result:
                raise ValueError('Duplicate pipeline action: ' + name)
            value = copy.deepcopy(action)
            if not value.get('runAfter') and parent:
                value['runAfter'] = {parent: ['Succeeded']}
            if value.get('type') == 'If':
                no = value.get('else', {}).get('actions', {})
                if not no or any(a.get('type') != 'Terminate' for a in no.values()):
                    raise ValueError('Only execution-terminating refusal branches can be linearized')
                positive = value['actions']
                marker = name + '_passed'
                value['actions'] = {marker: {'type': 'Compose', 'inputs': True, 'runAfter': {}}}
                result[name] = value
                append(positive, name)
            else:
                result[name] = value
    append(group)
    return result


def _candidate_actions(binding):
    """Untrusted selection -> complete native snapshots -> explicit hold.

    A coherent forged commit can reach the observer boundary, but cannot become
    qualified or reach any writer. The boundary is intentionally executable and
    visible rather than a misleading success/qualified result.
    """
    def comp(value, after=None):
        return {'type': 'Compose', 'inputs': value,
                'runAfter': {after: ['Succeeded']} if after else {}}
    def get(uri, after=None):
        return {'type': 'OpenApiConnection', 'inputs': {
            'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
                     'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
            'parameters': {'dataset': binding['siteUrl'], 'parameters/method': 'GET',
                           'parameters/uri': uri,
                           'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata'}},
            'retryPolicy': {'type': 'none'}},
            'runAfter': {after: ['Succeeded']} if after else {}}
    def fail(code):
        return {'type': 'Terminate', 'inputs': {'runStatus': 'Failed',
            'runError': {'code': code, 'message': 'Completed review is not qualified for progression; no writes performed.'}}, 'runAfter': {}}
    def guard(checks, actions, code, after=None):
        return {'type': 'If', 'expression': '@and(' + ','.join(checks) + ')',
                'actions': actions, 'else': {'actions': {code: fail(code)}},
                'runAfter': {after: ['Succeeded']} if after else {}}
    field = binding.get('completedReferenceField', 'text_6')
    ref = "trim(coalesce(triggerBody()?['" + field + "'],''))"
    safe = ["startsWith(" + ref + ",'LC04-')", 'greater(length(' + ref + '),5)',
            'lessOrEquals(length(' + ref + '),80)', 'equals(encodeUriComponent(' + ref + '),' + ref + ')',
            "not(contains(" + ref + ",'..'))", "not(contains(" + ref + ",decodeUriComponent('%27')))" ]
    folder = "_api/web/GetFolderByServerRelativePath(decodedurl='" + binding['closureFolder'] + "')/Files('LC04-closure-"
    uri = '@concat(' + _literal(folder) + ",outputs('Completed_reference')," + _literal("-commit.json')") + ')'
    a = {'Completed_reference': comp('@' + ref)}
    metadata = uri[:-1] + ',' + _literal('?$select=UniqueId,ETag,UIVersionLabel,Length') + ')'
    a['Completed_candidate_before'] = get(metadata, 'Completed_reference')
    a['Completed_candidate_content'] = get(uri[:-1] + ",'/$value')", 'Completed_candidate_before')
    a['Completed_candidate_after'] = get(metadata, 'Completed_candidate_content')
    a['Completed_candidate_record'] = comp("@if(contains(body('Completed_candidate_content'),'$content'),json(base64ToString(body('Completed_candidate_content')?['$content'])),json(string(body('Completed_candidate_content'))))", 'Completed_candidate_after')
    r = "outputs('Completed_candidate_record')"; c = r + "?['contract']"; parent = r + "?['afterProof']?['afterCase']"
    stable = ["equals(body('Completed_candidate_before'),body('Completed_candidate_after'))",
        "not(empty(body('Completed_candidate_after')?['ETag']))", "not(equals(body('Completed_candidate_after')?['ETag'],'*'))",
        "equals(" + r + "?['kind'],'fictional-prepared-closure-commit-v1')",
        "equals(" + r + "?['realPolicyEffects'],false)",
        "equals(" + c + "?['requestReference'],outputs('Completed_reference'))",
        "equals(" + c + "?['CaseUID']," + parent + "?['CaseUID'])",
        "startsWith(" + parent + "?['CaseUID'],'LC-FICTIONAL-OP-')",
        "equals(" + parent + "?['caseStatus'],'Review closed — FICTIONAL')",
        'greater(int(coalesce(' + parent + "?['Id'],0)),0)",
        "equals(" + c + "?['caseItemUri'],concat(" + _literal(binding['caseListUri'] + '(') + ',string(' + parent + "?['Id']),')'))"]
    reads = {}; previous = None
    caseuri = '@concat(' + _literal(binding['caseListUri'] + '(') + ',string(' + parent + "?['Id']),')')"
    reads['Completed_authoritative_case_before'] = get(caseuri)
    previous = 'Completed_authoritative_case_before'
    checks = []
    for side in ('before', 'after'):
        for label in ('assurance', 'readiness', 'consultation'):
            name = 'Completed_authoritative_' + label + '_' + side
            reads[name] = get(binding[label + 'CollectionUri'], previous)
            stable_name = name + '_stable'
            reads[stable_name] = {'type': 'Select', 'inputs': {'from': "@body('" + name + "')?['value']",
                'select': "@union(item(),json('{\"odata.id\":null}'))"}, 'runAfter': {name: ['Succeeded']}}
            previous = stable_name
            checks += ["empty(body('" + name + "')?['" + key + "'])" for key in ('odata.nextLink', '@odata.nextLink', 'nextLink', '@nextLink')]
    reads['Completed_authoritative_case_after'] = get(caseuri, previous)
    previous = 'Completed_authoritative_case_after'
    checks += ["equals(union(body('Completed_authoritative_case_before'),json('{\"odata.id\":null}')),union(body('Completed_authoritative_case_after'),json('{\"odata.id\":null}')))",
               "equals(outputs('Completed_authoritative_case_before')?['headers']?['ETag'],outputs('Completed_authoritative_case_after')?['headers']?['ETag'])",
               "not(empty(outputs('Completed_authoritative_case_after')?['headers']?['ETag']))",
               "not(equals(outputs('Completed_authoritative_case_after')?['headers']?['ETag'],'*'))",
               "equals(body('Completed_authoritative_case_after')?['CaseUID']," + c + "?['CaseUID'])",
               "equals(body('Completed_authoritative_case_after')?['caseStatus'],'Review closed — FICTIONAL')"]
    for label in ('assurance', 'readiness', 'consultation'):
        # Replace only the row array on comparison copies. Preserve every
        # response-wrapper key, including unknown future fields and next links.
        # setProperty returns an updated object (Microsoft WDL reference); the
        # raw native body and its retained receipt are never modified.
        before = 'Completed_authoritative_' + label + '_before'
        after = 'Completed_authoritative_' + label + '_after'
        checks.append("equals(setProperty(body('" + before + "'),'value',body('" + before + "_stable')),setProperty(body('" + after + "'),'value',body('" + after + "_stable')))")
    boundary = {'Completed_candidate': comp({'qualified': False, 'candidateOnly': True,
        'record': '@' + r, 'commitMetadata': "@body('Completed_candidate_after')",
        'currentCase': "@body('Completed_authoritative_case_after')",
        'currentCaseETag': "@outputs('Completed_authoritative_case_after')?['headers']?['ETag']",
        'domainWrites': 0, 'realPolicyEffects': False, 'actorAuthorityQualified': False}),
        'Completed_observer_unavailable': fail('AuthoritativeClosureObserverNotIntegrated')}
    boundary['Completed_observer_unavailable']['runAfter'] = {'Completed_candidate': ['Succeeded']}
    continuity = _historical_continuity_actions(binding)
    # This stage verifies retained transition provenance, but does not alone
    # qualify current stage evidence, actor authority or a new occurrence.
    leaf = continuity['Completed_verify_historical_continuity']['actions']
    leaf.update(boundary)
    leaf['Completed_candidate']['runAfter'] = {'Completed_historical_continuity': ['Succeeded']}
    reads['Completed_authoritative_stable'] = guard(checks, continuity, 'Completed_history_or_case_changed', previous)
    a['Completed_candidate_shape'] = guard(stable, reads, 'Completed_candidate_invalid', 'Completed_candidate_record')
    return {'Completed_selection': guard(safe, a, 'Completed_selection_invalid')}


def _historical_continuity_actions(binding):
    """Verify native retained proofs and exact protected-case continuity.

    A closure JSON's embedded before/after snapshots must equal the separately
    retained native before/after files. Both complete case snapshots survive.
    Only server-managed transition fields and the explicitly owned status field
    are masked on comparison copies; unknown and human fields remain protected.
    This is provenance consistency, not evidence authenticity or native acceptance.
    """
    def compose(value, after=None):
        return {'type': 'Compose', 'inputs': value,
                'runAfter': {after: ['Succeeded']} if after else {}}
    def get(uri, after=None):
        return {'type': 'OpenApiConnection', 'inputs': {
            'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
                     'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
            'parameters': {'dataset': binding['siteUrl'], 'parameters/method': 'GET',
                           'parameters/uri': uri,
                           'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata'}},
            'retryPolicy': {'type': 'none'}},
            'runAfter': {after: ['Succeeded']} if after else {}}
    a = {}; last = None
    folder = "_api/web/GetFolderByServerRelativePath(decodedurl='" + binding['closureFolder'] + "')/Files('LC04-closure-"
    for kind in ('before', 'after'):
        base = '@concat(' + _literal(folder) + ",outputs('Completed_reference')," + _literal('-' + kind + ".json')") + ')'
        prefix = 'Completed_proof_' + kind
        metadata = base[:-1] + ',' + _literal('?$select=UniqueId,ETag,UIVersionLabel,Length') + ')'
        a[prefix + '_metadata_before'] = get(metadata, last)
        a[prefix + '_content'] = get(base[:-1] + ", '/$value')", prefix + '_metadata_before')
        a[prefix + '_metadata_after'] = get(metadata, prefix + '_content')
        a[prefix] = compose("@if(contains(body('" + prefix + "_content'),'$content'),json(base64ToString(body('" + prefix + "_content')?['$content'])),json(string(body('" + prefix + "_content'))))", prefix + '_metadata_after')
        last = prefix
    record = "outputs('Completed_candidate_record')"; before = "outputs('Completed_proof_before')"; after = "outputs('Completed_proof_after')"
    contract = record + "?['contract']"; current = "body('Completed_authoritative_case_after')"
    def eq(left, right): return 'equals(' + left + ',' + right + ')'
    def clean(value): return 'union(' + value + ",json('{\"odata.id\":null}'))"
    def protected(value):
        return 'union(' + value + ",json('{\"odata.id\":null,\"odata.etag\":null,\"Modified\":null,\"EditorId\":null,\"OData__UIVersionString\":null,\"caseStatus\":null}'))"
    trace_version=binding.get('runtimeClosureTraceVersion')
    if trace_version is not None and (type(trace_version) is not int or trace_version!=1):
        raise ValueError('Explicit supported runtime closure trace version required')
    checks = [eq(before, record + "?['beforeProof']"), eq(after, record + "?['afterProof']"),
        eq(before + "?['evidence']", after + "?['evidence']"),
        eq(before + "?['kind']", "'fictional-prepared-closure-before-v1'"),
        eq(after + "?['kind']", "'fictional-prepared-closure-after-v1'"),
        eq(before + "?['contract']", contract), eq(after + "?['contract']", contract),
        eq(contract + "?['kind']", "'fictional-prepared-closure-contract-v1'"),
        eq(contract + "?['patch']", "json('{\"caseStatus\":\"Review closed — FICTIONAL\"}')"),
        eq(before + "?['beforeCaseETag']", contract + "?['initialCaseETag']"),
        eq(before + "?['beforeCase']?['caseStatus']", contract + "?['initialCaseStatus']"),
        eq(contract + "?['initialCaseStatus']", "'Ownership accepted — FICTIONAL'"),
        eq(clean(after + "?['afterCase']"), clean(current)),
        eq(after + "?['afterCaseETag']", "outputs('Completed_authoritative_case_after')?['headers']?['ETag']"),
        eq(protected(before + "?['beforeCase']"), protected(after + "?['afterCase']")),
        "not(equals(" + before + "?['beforeCaseETag']," + after + "?['afterCaseETag']))",
        "not(empty(" + record + "?['runId']))",
        eq(before + "?['runId']", record + "?['runId']"), eq(after + "?['runId']", record + "?['runId']")]
    if trace_version==1:
        # Opt-in only: legacy emitted code and runId meaning remain unchanged.
        # The discriminator selects trace semantics, never proof authenticity.
        # WDL evaluates both or branches. A runtime version is numeric, so
        # testing legacy absence with empty() throws even for a valid v1 trace.
        legacy_trace=checks[-2:]+[eq(record+"?['runtimeTraceVersion']",'null'),eq(contract+"?['runtimeTraceVersion']",'null')]
        runtime_trace=[
            eq(record+"?['runtimeTraceVersion']",'1'),eq('string('+record+"?['runtimeTraceVersion'])","'1'"),
            eq(contract+"?['runtimeTraceVersion']",'1'),eq('string('+contract+"?['runtimeTraceVersion'])","'1'"),
            "not(empty("+before+"?['runId']))",eq(before+"?['runId']",after+"?['runId']"),
            eq(record+"?['originRunId']",before+"?['runId']"),
            eq(record+"?['committedByRun']",record+"?['runId']")]
        checks=checks[:-2]+['or(and('+','.join(legacy_trace)+'),and('+','.join(runtime_trace)+'))']
    for kind in ('before', 'after'):
        prefix = 'Completed_proof_' + kind
        checks += [eq("body('" + prefix + "_metadata_before')", "body('" + prefix + "_metadata_after')"),
            "not(empty(body('" + prefix + "_metadata_after')?['ETag']))",
            "not(equals(body('" + prefix + "_metadata_after')?['ETag'],'*'))"]
    output = {'historicalContinuityConsistent': True, 'nativeObserverQualified': False,
              'beforeCase': '@' + before + "?['beforeCase']", 'afterCase': '@' + after + "?['afterCase']",
              'currentCase': '@' + current, 'domainWrites': 0, 'realPolicyEffects': False}
    a['Completed_verify_historical_continuity'] = {'type': 'If', 'expression': '@and(' + ','.join(checks) + ')',
        'actions': {'Completed_historical_continuity': compose(output)},
        'else': {'actions': {'Completed_changed_historical_proof': {'type': 'Terminate',
            'inputs': {'runStatus': 'Failed', 'runError': {'code': 'HistoricalClosureContinuityChanged',
                       'message': 'Retained proof or protected case fields changed; no progression.'}}, 'runAfter': {}}}},
        'runAfter': {last: ['Succeeded']}}
    return a


def build_historical_prepared_reader(context, binding, continuity_action='Completed_historical_continuity'):
    """Reuse the canonical prepared reader after verified closure continuity.

    Current-case and artifact/source/template checks are preserved. The original
    preparation receipt's status is compared to the actual retained before-case
    status, never discarded or relabelled as current. Complete before/after case
    continuity must already have succeeded in this same execution.
    """
    from build_prepared_revision_check import build_actions as prepared_reader
    from build_operator_entry import _flatten
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',continuity_action):
        raise ValueError('Literal historical continuity action required')
    continuity = "outputs('"+continuity_action+"')"
    graph = prepared_reader(context, binding, continuity)
    nodes = _flatten(graph)
    gate = nodes['Check_prepared_ownership']
    expected_gate = "@and(equals(" + continuity + "?['ownershipProjectionVerified'],true))"
    if gate['expression'] != expected_gate:
        raise ValueError('Canonical preparation ownership prerequisite changed')
    gate['expression'] = "@and(equals(" + continuity + "?['historicalContinuityConsistent'],true),equals(" + continuity + "?['nativeObserverQualified'],false))"
    verify = nodes['Verify_prepared_revision']
    old = "equals(outputs('Parse_prepared_receipt')?['caseSnapshot']?['snapshot']?['caseStatus'],body('Read_prepared_case')?['caseStatus'])"
    if verify['expression'].count(old) != 1:
        raise ValueError('Canonical original preparation status check changed')
    new = "equals(outputs('Parse_prepared_receipt')?['caseSnapshot']?['snapshot']?['caseStatus']," + continuity + "?['beforeCase']?['caseStatus'])"
    verify['expression'] = verify['expression'].replace(old, new)
    # Pin the complete current case to the separately verified after/current
    # closure snapshot; do not ignore unknown human fields or change the receipt.
    verify['expression'] = '@and(' + verify['expression'][1:] + ",equals(union(body('Read_prepared_case'),json('{\"odata.id\":null}')),union(" + continuity + "?['currentCase'],json('{\"odata.id\":null}'))),equals(union(body('Read_prepared_case_final'),json('{\"odata.id\":null}')),union(" + continuity + "?['currentCase'],json('{\"odata.id\":null}'))))"
    return graph


def build_current_closure_observer(context, binding):
    """Resolve current selection keys, then run the existing GET-only observer.

    This is local composition only. The caller must first run its canonical
    context/prepared reader and expose a string date-evidence lookup field in
    its manual form. The field supplies a file identity, never a date or pass
    flag. Neither a selected key nor this observer writes a closure commit.
    """
    from build_operator_entry import _flatten
    from build_prepared_closure_check import CHAIN, SCOPE
    field = binding.get('dateEvidenceField')
    schema = context['properties']['definition']['triggers']['manual']['inputs']['schema']
    if (not isinstance(field, str) or not re.fullmatch(r'text_[0-9]+', field)
            or schema.get('properties', {}).get(field, {}).get('type') != 'string'):
        raise ValueError('Existing explicit string date-evidence lookup field required')
    uri = binding.get('assuranceCollectionUri', '')
    if not re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F-]{36}'\)/items", uri):
        raise ValueError('Complete literal assurance history collection required')
    purposes = binding.get('purposeReferences', {})
    if set(purposes) != set(CHAIN[:4]) or any(not isinstance(v, str) or not v.startswith('fictional://') for v in purposes.values()):
        raise ValueError('Explicit fictional decision-purpose route required')
    template = context['properties']['definition']['actions']['Resolve_context']['actions']['Read_selected_case']
    if template['inputs']['parameters'].get('parameters/method') != 'GET':
        raise ValueError('Qualified read-only case context required')
    value = "string(coalesce(triggerBody()?['" + field + "'],''))"
    stripped = value
    for char in '0123456789abcdefABCDEF-':
        stripped = 'replace(' + stripped + ',' + _literal(char) + ",'')"
    guid_checks = ["equals(" + stripped + ",'')", "equals(length(replace(" + value + ",'-','')),32)"]
    guid_checks += ["equals(substring(" + value + ',' + str(index) + ",1),'-')" for index in (8, 13, 18, 23)]
    prepared = "outputs('Native_prepared_revision')"
    scope = prepared + "?['preparedRevision']?['scope']"
    checks = ["if(equals(length(" + value + '),36),and(' + ','.join(guid_checks) + '),false)',
              "equals(outputs('Selected_case_context')?['contextValid'],true)",
              'equals(' + prepared + "?['preparationQualified'],true)",
              'equals(' + prepared + "?['originalSourceIsPreparedRevision'],false)",
              'equals(' + scope + "?['CaseUID'],outputs('Selected_case_context')?['CaseUID'])"]
    def comp(payload, previous=None):
        return {'type': 'Compose', 'inputs': payload,
                'runAfter': {previous: ['Succeeded']} if previous else {}}
    def held(reason):
        return comp({'selectionConsistent': False, 'writeCount': 0,
                     'closurePerformed': False, 'realPolicyEffects': False, 'reason': reason})
    history = copy.deepcopy(template)
    history['inputs']['parameters'].update({'parameters/uri': uri, 'parameters/method': 'GET',
        'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata'}})
    history['inputs']['parameters'].pop('parameters/body', None)
    history['inputs']['retryPolicy'] = {'type': 'none'}
    history['runAfter'] = {}
    work = {'CurrentClosure_history': history,
        'CurrentClosure_scoped': {'type': 'Query', 'inputs': {
            'from': "@body('CurrentClosure_history')?['value']",
            'where': '@and(' + ','.join("equals(item()?['" + key + "']," + scope + "?['" + key + "'])" for key in SCOPE) + ')'},
            'runAfter': {'CurrentClosure_history': ['Succeeded']}}}
    previous = 'CurrentClosure_scoped'
    selected = {}
    for index, role in enumerate(CHAIN):
        name = 'CurrentClosure_select_' + role
        clauses = ["equals(item()?['Stage']," + _literal('Decision' if index < 4 else role.title()) + ')']
        if index < 4:
            clauses.append("equals(item()?['DecisionReference']," + _literal(purposes[role]) + ')')
        work[name] = {'type': 'Query', 'inputs': {'from': "@body('CurrentClosure_scoped')",
            'where': '@' + ('and(' + ','.join(clauses) + ')' if len(clauses) > 1 else clauses[0])},
            'runAfter': {previous: ['Succeeded']}}
        selected[role] = "first(body('" + name + "'))"
        previous = name
    unique = ["empty(body('CurrentClosure_history')?['" + key + "'])" for key in ('nextLink', 'odata.nextLink', '@odata.nextLink', '@nextLink')]
    unique += ["equals(length(body('CurrentClosure_scoped')),7)"]
    unique += ["equals(length(body('CurrentClosure_select_" + role + "')),1)" for role in CHAIN]
    parents = ["empty(" + selected[CHAIN[0]] + "?['ParentEventUID'])"]
    parents += ['equals(' + selected[role] + "?['ParentEventUID']," + selected[CHAIN[index - 1]] + "?['EventUID'])" for index, role in enumerate(CHAIN) if index]
    for role in CHAIN:
        parents.append('not(empty(' + selected[role] + "?['EventUID']))")
    work['CurrentClosure_unique'] = {'type': 'If', 'expression': '@and(' + ','.join(unique) + ')',
        'runAfter': {previous: ['Succeeded']}, 'actions': {
            'CurrentClosure_parents': {'type': 'If', 'expression': '@and(' + ','.join(parents) + ')',
                'runAfter': {}, 'actions': {'Current_closure_selection': comp({
                    'selectionConsistent': True, 'selectedEvents': {role: '@' + row + "?['EventUID']" for role, row in selected.items()},
                    'nextReviewEvidenceFileUID': '@' + value,
                    'lookupKeysOnly': True, 'writeCount': 0, 'closurePerformed': False,
                    'realPolicyEffects': False})},
                'else': {'actions': {'CurrentClosure_parent_hold': held('Missing or mismatched ordered parent chain')}}}},
        'else': {'actions': {'CurrentClosure_selection_hold': held('Missing, duplicate, extra or incomplete scoped history')}}}
    observer = build_runtime_closure_observer(context, binding, 'Current_closure_selection')
    graph = {'CurrentClosure_validate': {'type': 'If', 'expression': '@and(' + ','.join(checks) + ')',
        'runAfter': {}, 'actions': work,
        'else': {'actions': {'CurrentClosure_input_hold': held('Current prepared context and safe date-evidence identity required')}}},
        'CurrentClosure_observe': {'type': 'If',
            'expression': "@equals(outputs('Current_closure_selection')?['selectionConsistent'],true)",
            'runAfter': {'CurrentClosure_validate': ['Succeeded']}, 'actions': observer,
            'else': {'actions': {'CurrentClosure_observer_hold': held('No current unique selection; canonical observer was not run')}}}}
    if any(action['inputs']['parameters']['parameters/method'] != 'GET'
           for action in _flatten(graph).values() if action.get('type') == 'OpenApiConnection'):
        raise ValueError('Current closure observer must remain GET-only')
    return graph


def _source_review_requirements(binding):
    """Optional reviewed source routes; never consume a closure's route claims."""
    profiles = binding.get('allowedSources', [])
    if not any(isinstance(profile, dict) and 'reviewRequirements' in profile for profile in profiles):
        return None
    routes = []; seen = set(); purposes = {'committee', 'officer', 'coordinator', 'authorisation'}
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError('Every eligible source needs reviewed requirements')
        uid = profile.get('UniqueId', '')
        if not isinstance(uid, str) or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', uid):
            raise ValueError('Reviewed route requires an exact source file identity')
        if uid.lower() in seen:
            raise ValueError('Reviewed routes require unique source identities')
        seen.add(uid.lower())
        route = profile.get('reviewRequirements')
        if not isinstance(route, dict) or set(route) != {'requiredFictionalRoles', 'purposeReferences'}:
            raise ValueError('Every eligible source needs complete reviewed role and purpose requirements')
        roles = route['requiredFictionalRoles']; refs = route['purposeReferences']
        if (not isinstance(roles, list) or not roles
                or any(not isinstance(role, str) or not role.startswith('FICTIONAL ') or len(role) > 255 for role in roles)
                or len(set(roles)) != len(roles)):
            raise ValueError('Explicit unique required fictional roles required per source')
        if (not isinstance(refs, dict) or set(refs) != purposes
                or any(not isinstance(ref, str) or not ref.startswith('fictional://') or len(ref) > 255 for ref in refs.values())):
            raise ValueError('Four explicit fictional purpose references required per source')
        routes.append((uid.lower(), copy.deepcopy(route)))
    return routes


def _apply_source_review_requirements(nodes, routes, roles, purposes):
    """Adapt only generated coverage and purpose checks; no new writer or reader."""
    import json
    source = "toLower(string(coalesce(outputs('Selected_case_context')?['sourcePins']?['UniqueId'],'')))"
    def choose(value):
        expression = 'null'
        for uid, route in reversed(routes):
            expression = 'if(equals(' + source + ',' + _literal(uid) + '),' + value(route) + ',' + expression + ')'
        return expression
    required = choose(lambda route: 'createArray(' + ','.join(_literal(role) for role in route['requiredFictionalRoles']) + ')')
    known = 'or(false,' + ','.join('equals(' + source + ',' + _literal(uid) + ')' for uid, _ in routes) + ')'
    guard = nodes['Closure_Ready_consultation_Runtime_guard']
    guard['expression'] = '@and(' + guard['expression'][1:] + ',' + known + ')'
    problems = nodes['Closure_Ready_consultation_Problems']['inputs']
    old = 'createArray(' + ','.join(_literal(role) for role in roles) + ')'
    if problems['where'].count(old) != 1:
        raise ValueError('Canonical consultation role membership changed')
    problems['where'] = problems['where'].replace(old, required)
    result_nodes = {}
    for index, role in enumerate(roles):
        name = 'Closure_Ready_consultation_R' + str(index)
        complete = nodes[name + '_Complete']
        # Roles absent from this source's reviewed route are not requirements;
        # unexpected actual rows still fail the source-specific Problems query.
        complete['inputs'] = '@if(contains(' + required + ',' + _literal(role) + '),' + complete['inputs'][1:] + ',true)'
        record = "json(" + _literal(json.dumps({'SubjectRole': role}, separators=(',', ':'))) + ')'
        for key, value in [('complete', "outputs('" + name + "_Complete')"),
                           ('requestCount', "length(body('" + name + "_Requests'))"),
                           ('responseCount', "length(body('" + name + "_Responses'))")]:
            record = 'setProperty(' + record + ',' + _literal(key) + ',' + value + ')'
        result_nodes[role] = record
    nodes['Closure_Ready_consultation_Receipt']['inputs']['requiredRoleResults'] = '@' + choose(
        lambda route: 'createArray(' + ','.join(result_nodes[role] for role in route['requiredFictionalRoles']) + ')')
    for role, reference in purposes.items():
        node = nodes['Closure_selected_' + role + '_valid']
        old = "equals(first(body('Closure_selected_" + role + "'))?['DecisionReference']," + _literal(reference) + ')'
        if node['inputs'].count(old) != 1:
            raise ValueError('Canonical configured purpose comparison changed')
        new = "equals(first(body('Closure_selected_" + role + "'))?['DecisionReference']," + choose(
            lambda route: _literal(route['purposeReferences'][role])) + ')'
        node['inputs'] = node['inputs'].replace(old, new)
    # These are native expression limits, not an additional adoption gate.
    def bounded(value):
        if isinstance(value, str) and value.startswith('@') and len(value) > 8192:
            raise ValueError('Source-specific review expression exceeds native length limit')
        if isinstance(value, dict):
            for child in value.values(): bounded(child)
        elif isinstance(value, list):
            for child in value: bounded(child)
    bounded(nodes)


def build_runtime_closure_observer(context, binding, selection_action=None):
    """Reuse the canonical observer with runtime lookup keys, locally only.

    The caller must supply independently verified historical prepared context as
    Native_prepared_revision and Selected_case_context in the same execution.
    This helper neither manufactures those outputs nor grants native acceptance.
    Only explicitly generated selection/query/date nodes are transformed; proof
    records, human text, and other expression literals are never globally edited.
    """
    from build_prepared_closure_check import build_actions as closure_observer, CHAIN
    from build_operator_entry import _flatten
    selections = {role: 'RUNTIME_LOOKUP_' + role for role in CHAIN}
    purposes = {role: 'fictional://runtime-purpose/' + role for role in CHAIN[:4]}
    date_uid = '00000000-0000-4000-8000-000000000099'
    config = {key: binding[key] for key in ('assuranceCollectionUri', 'readinessCollectionUri',
                                           'consultationCollectionUri', 'requiredFictionalRoles')}
    routes = _source_review_requirements(binding)
    if routes is not None:
        config['requiredFictionalRoles'] = list(dict.fromkeys(
            role for _, route in routes for role in route['requiredFictionalRoles']))
    config.update(selectedEvents=selections, purposeReferences=purposes,
                  nextReviewEvidenceFileUID=date_uid)
    graph = closure_observer(context, config)
    nodes = _flatten(graph)
    if selection_action is not None and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', selection_action):
        raise ValueError('Literal selection action name required')
    candidate = ("outputs('" + selection_action + "')" if selection_action is not None else
                 "outputs('Completed_candidate_record')?['contract']?['observation']")
    # Exact generated node contracts make upstream changes explicit failures.
    for role in CHAIN:
        value = candidate + "?['selectedEvents']?['" + role + "']"
        selected = nodes['Closure_selected_' + role]['inputs']
        before = selected['where']
        needle = _literal(selections[role])
        if before.count(needle) != 1:
            raise ValueError('Canonical selected-event expression changed')
        selected['where'] = before.replace(needle, value)
        superseder = nodes['Closure_superseders_' + role]['inputs']
        if superseder['where'].count(needle) != 1:
            raise ValueError('Canonical superseder expression changed')
        superseder['where'] = superseder['where'].replace(needle, value)
        if role != CHAIN[0]:
            parent = CHAIN[CHAIN.index(role) - 1]
            expr = nodes['Closure_selected_' + role + '_valid']['inputs']
            needle = _literal(selections[parent])
            if expr.count(needle) != 1:
                raise ValueError('Canonical selected-parent expression changed')
            nodes['Closure_selected_' + role + '_valid']['inputs'] = expr.replace(
                needle, candidate + "?['selectedEvents']?['" + parent + "']")
        if role in purposes:
            expr = nodes['Closure_selected_' + role + '_valid']['inputs']
            needle = _literal(purposes[role])
            if expr.count(needle) != 1:
                raise ValueError('Canonical decision-purpose expression changed')
            # Purpose is a configured route requirement, never a candidate's
            # claim to authority. Same route applies to every eligible occurrence.
            required = binding.get('purposeReferences', {}).get(role)
            if not isinstance(required, str) or not required.startswith('fictional://'):
                raise ValueError('Explicit fictional route purpose required: ' + role)
            nodes['Closure_selected_' + role + '_valid']['inputs'] = expr.replace(needle, _literal(required))
    identifier = candidate + "?['nextReviewEvidenceFileUID']"
    for name in ('Closure_date_before', 'Closure_date_content', 'Closure_date_after', 'Closure_final_date'):
        node = nodes[name]['inputs']['parameters']
        uri = node['parameters/uri']
        prefix = "_api/web/GetFileById('" + date_uid + "')"
        if not uri.startswith(prefix):
            raise ValueError('Canonical date lookup expression changed')
        node['parameters/uri'] = '@concat(' + _literal("_api/web/GetFileById('") + ',' + identifier + ',' + _literal("')" + uri[len(prefix):]) + ')'
    date_expr = nodes['Closure_date_consistent']['inputs']
    if date_expr.count(_literal(date_uid)) != 1:
        raise ValueError('Canonical date-identity expression changed')
    nodes['Closure_date_consistent']['inputs'] = date_expr.replace(_literal(date_uid), identifier)
    if routes is not None:
        _apply_source_review_requirements(nodes, routes, config['requiredFictionalRoles'], binding['purposeReferences'])
    observation = nodes['Native_closure_observation']['inputs']
    observation['selectedEvents'] = '@' + candidate + "?['selectedEvents']"
    observation['nextReviewEvidenceFileUID'] = '@' + identifier
    return graph


def _reader_actions(binding, context_action, producer_flow_id):
    """SharePoint-side WDL, exercised offline with explicitly synthetic adapters.

    Internal composition primitive, not an alternative unqualified public entry.
    It emits no history API or mutation and cannot qualify an adapter.
    """
    if binding.get('qualificationOnly') is not True:
        raise ValueError('Explicit fictional qualification scope required')
    site = binding.get('siteUrl', '')
    folder = binding.get('closureFolder', '')
    casebase = binding.get('caseListUri', '')
    if (not site.startswith('https://') or not folder.startswith('/')
            or any(c in folder for c in ["'", '..', '?', '#', '%'])
            or not re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F-]{36}'\)/items", casebase)):
        raise ValueError('Qualified site/folder/case-list binding required')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', context_action):
        raise ValueError('Literal independently qualified context action required')
    source_profiles = binding.get('allowedSources', [])
    if not isinstance(source_profiles, list) or not source_profiles:
        raise ValueError('Explicit immutable fictional source eligibility profiles required')
    seen_sources = set()
    for profile in source_profiles:
        if not isinstance(profile, dict):
            raise ValueError('Source eligibility profiles must be objects')
        required = ('DocumentUID', 'UniqueId', 'ETag', 'DocumentReference',
                    'ReviewedVersionRef', 'content', 'sha256')
        if any(not isinstance(profile.get(k), str) or not profile[k].strip()
               for k in required):
            raise ValueError('Complete immutable source identity, version and content required')
        uri = urlsplit(profile['DocumentReference'])
        if (not profile['DocumentUID'].startswith('FICTIONAL-')
                or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', profile['UniqueId'])
                or profile['ETag'] == '*'
                or uri.scheme != 'https' or not uri.netloc or uri.username or uri.password
                or uri.query or uri.fragment
                or hashlib.sha256(profile['content'].encode()).hexdigest() != profile['sha256']):
            raise ValueError('Explicit immutable fictional source eligibility profiles required')
        source_key = profile['UniqueId'].lower()
        if source_key in seen_sources:
            raise ValueError('Source eligibility profiles must have unique file identities')
        seen_sources.add(source_key)
    field = binding.get('completedReferenceField', 'text_6')
    if not re.fullmatch(r'text(?:_[0-9]+)?', field):
        raise ValueError('Existing manual-form field required')
    ctx = "outputs('" + context_action + "')"
    ref = "trim(coalesce(triggerBody()?['" + field + "'],''))"
    names = lambda label: 'Completed_' + label
    def compose(value, previous=None):
        return {'type': 'Compose', 'inputs': value,
                'runAfter': {previous: ['Succeeded']} if previous else {}}
    def http(uri, previous, accept='application/json;odata=minimalmetadata'):
        return {'type': 'OpenApiConnection', 'inputs': {
            'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline',
                     'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'},
            'parameters': {'dataset': site, 'parameters/method': 'GET',
                           'parameters/uri': uri, 'parameters/headers': {'Accept': accept}},
            'retryPolicy': {'type': 'none'}}, 'runAfter': {previous: ['Succeeded']}}
    def clean(value): return 'union(' + value + ",json('{\"odata.id\":null}'))"
    def equal(a, b): return 'equals(' + a + ',' + b + ')'
    def conjunction(checks): return '@and(' + ','.join(checks) + ')'
    def gate(checks, yes, hold):
        return {'type': 'If', 'expression': conjunction(checks), 'actions': yes,
                'else': {'actions': {hold: compose({'qualified': False,
                    'reason': hold, 'domainWrites': 0, 'realPolicyEffects': False})}}, 'runAfter': {}}
    def parse(name):
        return "@if(contains(body('"+name+"'),'$content'),json(base64ToString(body('"+name+"')?['$content'])),json(string(body('"+name+"'))))"
    prefix = 'LC04-'
    # Validate before constructing any selected file path. URI encoding blocks
    # quotes, slashes, percent escapes and other query/path injection characters.
    selected = ["startsWith("+ref+",'"+prefix+"')", 'greater(length('+ref+'),'+str(len(prefix))+')',
                'lessOrEquals(length('+ref+'),80)', 'equals(encodeUriComponent('+ref+'),'+ref+')',
                "not(contains("+ref+",'..'))", "not(contains("+ref+",decodeUriComponent('%27')))",
                equal(ctx+"?['qualified']", 'true'), equal(ctx+"?['flowId']", _literal(producer_flow_id)),
                "not(empty("+ctx+"?['runId']))"]
    a = {names('reference'): compose('@'+ref)}
    filename = "concat('LC04-closure-',outputs('Completed_reference'),'-commit.json')"
    base = "_api/web/GetFolderByServerRelativePath(decodedurl='"+folder+"')/Files"
    def commit_uri(suffix):
        return '@concat('+_literal(base+"('")+','+filename+','+_literal("')"+suffix)+')'
    a[names('commit_before')] = http(commit_uri('?$select=UniqueId,ETag,UIVersionLabel,Length'), names('reference'))
    a[names('commit_content')] = http(commit_uri('/$value'), names('commit_before'))
    a[names('commit_after')] = http(commit_uri('?$select=UniqueId,ETag,UIVersionLabel,Length'), names('commit_content'))
    a[names('record')] = compose(parse(names('commit_content')), names('commit_after'))
    record = "outputs('Completed_record')"; contract = record+"?['contract']"
    checks = [equal(record, ctx+"?['commit']"),
              equal("body('Completed_commit_content')?['$content']", ctx+"?['commitContentBase64']"),
              equal(record+"?['kind']", "'fictional-prepared-closure-commit-v1'"),
              equal(record+"?['realPolicyEffects']", 'false'),
              equal(contract+"?['requestReference']", "outputs('Completed_reference')"),
              equal(record+"?['runId']", ctx+"?['runId']"),
              equal(record+"?['beforeProof']?['runId']", ctx+"?['runId']"),
              equal(record+"?['afterProof']?['runId']", ctx+"?['runId']"),
              equal(record+"?['beforeProof']?['contract']", contract),
              equal(record+"?['afterProof']?['contract']", contract)]
    for name in ['Completed_commit_before', 'Completed_commit_after']:
        checks += [equal(('int(body(\''+name+'\')?[\'Length\'])') if k=='Length' else "body('"+name+"')?['"+k+"']",
                         'int('+ctx+"?['commitMetadata']?['Length'])" if k=='Length' else ctx+"?['commitMetadata']?['"+k+"']")
                   for k in ['UniqueId','ETag','UIVersionLabel','Length']]
    # Actual retained layout: afterProof.evidence, NOT contract.expectedEvidence.
    evidence = record+"?['afterProof']?['evidence']"
    parent = record+"?['afterProof']?['afterCase']"
    token = record+"?['afterProof']?['afterCaseETag']"
    observation = contract+"?['observation']"
    checks += [equal(contract+"?['kind']", "'fictional-prepared-closure-contract-v1'"),
               equal(record+"?['beforeProof']?['kind']", "'fictional-prepared-closure-before-v1'"),
               equal(record+"?['afterProof']?['kind']", "'fictional-prepared-closure-after-v1'"),
               equal(parent+"?['caseStatus']", "'Review closed — FICTIONAL'"),
               "startsWith("+parent+"?['CaseUID'],'LC-FICTIONAL-OP-')",
               equal(contract+"?['CaseUID']", parent+"?['CaseUID']"),
               "not(empty("+parent+"?['GUID']))",
               "not(empty("+parent+"?['Created']))",
               'greater(int('+parent+"?['Id']),0)",
               equal(contract+"?['caseItemUri']", 'concat('+_literal(casebase+'(')+',string('+parent+"?['Id']),')')"),
               "not(empty("+token+"))", "not(equals("+token+",'*'))",
               equal(record+"?['beforeProof']?['beforeCaseETag']", contract+"?['initialCaseETag']"),
               equal(record+"?['beforeProof']?['beforeCase']?['caseStatus']", contract+"?['initialCaseStatus']")]
    for key in ['closureEvidenceConsistent','nextReviewDateProvenanceConsistent','nextOccurrencePrerequisitesConsistent']:
        checks.append(equal(observation+"?['"+key+"']", 'true'))
    for key in ['originalSource','sourceBaseline','date']:
        value=evidence+"?['"+key+"']?['UniqueId']";stripped=value
        for char in '0123456789abcdefABCDEF-':stripped='replace('+stripped+','+_literal(char)+",'')"
        checks += ['equals(length('+value+'),36)',"equals("+stripped+",'')"]
    current = {'Completed_record_verified': compose(True)}
    def file_route(key, suffix):
        return '@concat('+_literal("_api/web/GetFileById('")+','+evidence+"?['"+key+"']?['UniqueId'],"+_literal("')"+suffix)+')'
    previous='Completed_record_verified'
    for key in ['originalSource','sourceBaseline','date']:
        before='Completed_'+key+'_before';content='Completed_'+key+'_content';after='Completed_'+key+'_after'
        current[before]=http(file_route(key,'?$select=UniqueId,ETag,UIVersionLabel,Length,ServerRelativeUrl'),previous)
        current[content]=http(file_route(key,'/$value'),before)
        current[after]=http(current[before]['inputs']['parameters']['parameters/uri'],content);previous=after
    current['Completed_baseline']=compose(parse('Completed_sourceBaseline_content'),previous)
    current['Completed_date']=compose(parse('Completed_date_content'),'Completed_baseline')
    current['Completed_allowed_sources']=compose(copy.deepcopy(source_profiles),'Completed_date')
    baseline="outputs('Completed_baseline')?['request']"
    profile_checks=[equal("item()?['UniqueId']",evidence+"?['originalSource']?['UniqueId']"),equal("item()?['ETag']",evidence+"?['originalSource']?['ETag']")]
    for key,baseline_key in [('DocumentUID','DocumentUID'),('DocumentReference','DocumentReference'),('ReviewedVersionRef','ReviewedVersionRef'),('sha256','DocumentSHA256')]:
        profile_checks.append(equal("item()?['"+key+"']",baseline+"?['"+baseline_key+"']"))
    current['Completed_source_profiles']={'type':'Query','inputs':{'from':"@outputs('Completed_allowed_sources')",'where':conjunction(profile_checks)},'runAfter':{'Completed_allowed_sources':['Succeeded']}}
    case_uri='@concat('+_literal(casebase+'(')+',string('+parent+"?['Id']),')')"
    current['Completed_case_before']=http(case_uri,'Completed_source_profiles')
    listbase=casebase.rsplit('/items',1)[0]
    current['Completed_unique_field']=http(listbase+"/fields/getbyinternalnameortitle('CaseUID')?$select=InternalName,TypeAsString,MaxLength,EnforceUniqueValues",'Completed_case_before')
    current['Completed_date_field']=http(listbase+"/fields/getbyinternalnameortitle('targetDate')?$select=InternalName,TypeAsString,MaxLength",'Completed_unique_field')
    current['Completed_case_after']=http(case_uri,'Completed_date_field')
    final_checks=[equal(baseline+"?['CaseUID']",parent+"?['CaseUID']"),
                  equal("outputs('Completed_baseline')?['kind']","'fictional-operator-initiation-request'"),
                  equal(baseline+"?['qualificationOnly']",'true'),
                  equal(baseline+"?['realPolicyEffects']",'false'),
                  equal(clean("body('Completed_case_before')"),clean(parent)),equal(clean("body('Completed_case_after')"),clean(parent)),
                  equal("outputs('Completed_case_before')?['headers']?['ETag']",token),equal("outputs('Completed_case_after')?['headers']?['ETag']",token),
                  equal("length(body('Completed_source_profiles'))",'1'),equal("body('Completed_unique_field')?['InternalName']","'CaseUID'"),
                  equal("body('Completed_unique_field')?['EnforceUniqueValues']",'true'),equal("body('Completed_unique_field')?['TypeAsString']","'Text'"),
                  equal("body('Completed_date_field')?['InternalName']","'targetDate'"),equal("body('Completed_date_field')?['TypeAsString']","'Text'"),
                  "greaterOrEquals(int(body('Completed_date_field')?['MaxLength']),10)"]
    for key in ['originalSource','sourceBaseline','date']:
        for side in ['before','after']:
            action='Completed_'+key+'_'+side
            for field_name in ['UniqueId','ETag','UIVersionLabel','Length']:
                left="body('"+action+"')?['"+field_name+"']";right=evidence+"?['"+key+"']?['"+field_name+"']"
                final_checks.append(equal('int('+left+')' if field_name=='Length' else left,'int('+right+')' if field_name=='Length' else right))
    origin=urlsplit(site).scheme+'://'+urlsplit(site).netloc
    final_checks.append(equal(parent+"?['sourceBaselineRef']",'concat('+_literal(origin)+",body('Completed_sourceBaseline_after')?['ServerRelativeUrl'])"))
    date="outputs('Completed_date')"
    # Keep the final full-frame gate within the native expression-size limit.
    # This same-execution predicate is a dependency, never a caller assertion.
    current['Completed_calendar_date_valid'] = compose(
        '@' + calendar_date_expression(date+"?['reviewDate']"), 'Completed_case_after')
    final_checks += [equal(date,evidence+"?['dateContent']"),equal(date+"?['FictionalTest']",'true'),equal(date+"?['notOperational']",'true'),
                    equal(date+"?['policyAuthorityGranted']",'false'),equal(date+"?['scope']",observation+"?['preparedScope']"),
                    equal(date+"?['scope']?['CaseUID']",parent+"?['CaseUID']"),equal(date+"?['reviewDate']",observation+"?['nextReviewDate']"),
                    equal("outputs('Completed_calendar_date_valid')", 'true'),
                    equal(date+"?['ruleReference']",observation+"?['nextReviewRuleReference']"),"startsWith("+date+"?['ruleReference'],'fictional://')",
                    equal(evidence+"?['date']?['UniqueId']",observation+"?['nextReviewEvidenceFileUID']")]
    source_text="if(contains(body('Completed_originalSource_content'),'$content'),base64ToString(body('Completed_originalSource_content')?['$content']),string(body('Completed_originalSource_content')))"
    final_checks.append("if(equals(length(body('Completed_source_profiles')),1),and(equals("+source_text+",first(body('Completed_source_profiles'))?['content']),equals(concat("+_literal(origin)+",body('Completed_originalSource_after')?['ServerRelativeUrl']),first(body('Completed_source_profiles'))?['DocumentReference'])),false)")
    output={'qualified':True,'closureReference':"@outputs('Completed_reference')",'commit':'@'+record,'commitMetadata':"@body('Completed_commit_after')",
            'closedCase':'@'+parent,'closedCaseETag':'@'+token,'originalSource':"@first(body('Completed_source_profiles'))",'date':'@'+date,
            'originalSourceMetadata':'@'+evidence+"?['originalSource']",'sourceBaselineMetadata':'@'+evidence+"?['sourceBaseline']",'dateMetadata':'@'+evidence+"?['date']",
            'domainWrites':0,'realPolicyEffects':False,'ownershipAccepted':False}
    current['Completed_validate_current']=gate(final_checks,{'Completed_context':compose(output)},'Completed_hold_current_drift')
    current['Completed_validate_current']['runAfter']={'Completed_calendar_date_valid':['Succeeded']}
    a['Completed_validate_record']=gate(checks,current,'Completed_hold_unverified_record')
    a['Completed_validate_record']['runAfter']={'Completed_record':['Succeeded']}
    return {'Completed_select':gate(selected,a,'Completed_hold_unqualified_selection')}
