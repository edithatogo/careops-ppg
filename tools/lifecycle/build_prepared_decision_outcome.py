"""Local-only assembly of the existing fictional adverse-decision recording flow.

Copies only reviewed GET prerequisites, never case projection writers. Native
bindings stay private; this module performs no I/O, deployment or assessment.
"""
import copy
import hashlib
import json
import re
from build_selected_event_routes import audit_actions


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build(case_work, target, binding):
    source = case_work['properties']['definition']; old = target['properties']['definition']
    if (binding.get('qualificationOnly') is not True
            or digest(source) != binding.get('approvedCaseWorkDefinitionSHA256')
            or digest(old) != binding.get('approvedTargetDefinitionSHA256')):
        raise ValueError('Exact reviewed prerequisite and existing target definitions required')
    if case_work['properties']['connectionReferences'] != target['properties']['connectionReferences']:
        raise ValueError('Preserve the qualified connection references')
    if target['properties'].get('state') != 'Stopped':
        raise ValueError('Preserve an idle stopped target preimage before assembly')
    uri = binding['assuranceCollectionUri']
    if not isinstance(uri, str) or not re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'\)/items", uri):
        raise ValueError('Complete privately bound assurance collection required')
    if binding.get('eventUIDUnique') is not True:
        raise ValueError('Observed native unique EventUID contract required')
    expected_types = {'ConditionsNotes': 'Text', 'NextAction': 'Note', 'Summary': 'Text',
                      'EvidenceReference': 'Text', 'DecisionReference': 'Text'}
    if binding.get('observedFieldTypes') != expected_types:
        raise ValueError('Explicit observed native Text/Note contract required')
    if binding.get('observedTextMaxLengths') != {key: 255 for key in
            ('Title', 'Summary', 'ConditionsNotes', 'EvidenceReference', 'DecisionReference')}:
        raise ValueError('Observed native Text255 limits required')
    actions = {name: copy.deepcopy(source['actions'][name]) for name in
               ('Resolve_context', 'Route_preparation_check', 'Route_readiness_check')}
    actions['Resolve_context']['runAfter'] = {}
    for name in ('Route_preparation_check', 'Route_readiness_check'):
        actions[name]['expression'] = "@equals(outputs('Selected_case_context')?['contextValid'],true)"
    # Inspect actual executable shapes and qualified resource descriptors recursively.
    template = actions['Resolve_context']['actions']['Read_selected_case']
    qualified = template['inputs']; dataset = qualified['parameters']['dataset']; host = qualified['host']
    def inspect(group):
        for action in group.values():
            if action.get('type') not in ('If', 'Scope', 'Compose', 'Query', 'Select', 'Terminate', 'OpenApiConnection'):
                raise ValueError('Unsupported prerequisite action')
            if action['type'] == 'Terminate' and action['inputs'].get('runStatus') != 'Failed':
                raise ValueError('Prerequisite cannot terminate successfully before evidence')
            if action['type'] == 'OpenApiConnection':
                inputs = action['inputs']; p = inputs['parameters']; h = inputs['host']
                if (h.get('apiId') != '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
                        or h.get('operationId') != 'HttpRequest'
                        or any(h.get(k) != host.get(k) for k in ('apiId', 'operationId', 'connectionName'))
                        or p.get('dataset') != dataset or p.get('parameters/method') != 'GET'
                        or 'parameters/body' in p
                        or any(k.lower() in ('x-http-method', 'x-http-method-override') for k in p.get('parameters/headers', {}))):
                    raise ValueError('Prerequisites must contain only same-connection SharePoint GETs')
            inspect(action.get('actions', {})); inspect(action.get('else', {}).get('actions', {}))
    inspect(actions)
    if old['triggers']['manual'].get('kind') != 'Button' or source['triggers']['manual'].get('kind') != 'Button':
        raise ValueError('Use the qualified existing first-party Button entry')
    fields = copy.deepcopy(old['triggers']['manual']['inputs']['schema']['properties'])
    if set(fields) != {'text', 'text_1', 'text_2', 'text_3', 'text_4'} or any(x.get('type') != 'string' for x in fields.values()):
        raise ValueError('Preserve the existing five-string decision form contract')
    fields['text_6'] = copy.deepcopy(source['triggers']['manual']['inputs']['schema']['properties']['text_6'])
    fields['text_2']['description'] = 'Fictional reason, 1–200 characters; retained in Summary and bounded ConditionsNotes.'
    fields['text_3']['description'] = 'Supporting fictional evidence reference, 1–255 characters.'
    fields['text_4']['description'] = 'Full next action, 1–4000 characters; retained in the native Note field, no assignment.'
    trigger = copy.deepcopy(old['triggers']['manual'])
    trigger['inputs']['schema'] = {'type': 'object', 'properties': fields, 'required': list(fields)}
    trigger['runtimeConfiguration'] = {'concurrency': {'runs': 1}}

    def comp(value, previous=None):
        return {'type': 'Compose', 'inputs': value, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def http(path, previous=None, *, method='GET', body=None):
        action = copy.deepcopy(template); p = action['inputs']['parameters']
        p.update({'parameters/uri': path, 'parameters/method': method,
                  'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata'}})
        action['runAfter'] = {previous: ['Succeeded']} if previous else {}
        if method != 'GET':
            p['parameters/body'] = body; p['parameters/headers']['Content-Type'] = 'application/json;odata=nometadata'
            action['inputs']['retryPolicy'] = {'type': 'none'}
        return action
    def guard(checks, yes, no, previous=None):
        return {'type': 'If', 'expression': '@and(' + ','.join(checks) + ')',
            'actions': yes, 'else': {'actions': no}, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def eq(a, b): return 'equals(' + a + ',' + b + ')'
    def complete(name):
        return ["empty(body('" + name + "')?['odata.nextLink'])", "empty(body('" + name + "')?['@odata.nextLink'])"]
    def stable(container, name, read):
        container[name] = {'type': 'Select', 'inputs': {'from': "@body('" + read + "')?['value']",
            'select': "@union(item(),json('{\"odata.id\":null}'))"}, 'runAfter': {read: ['Succeeded']}}
    def present(value): return "not(empty(trim(string(coalesce(" + value + ",'')))))"
    held = {'qualified': False, 'createdCount': 0, 'caseWrites': 0, 'sourceWrites': 0,
        'readinessWrites': 0, 'publicationWrites': 0, 'actorAuthorityQualified': False,
        'progressionGranted': False, 'policyApproved': False, 'contentReadinessGranted': False, 'realPolicyEffects': False,
        'reason': 'Current exact prepared readiness and complete stable evidence are required; no decision recorded.'}
    ready = "outputs('Native_readiness_observation')"; prepared = "outputs('Native_prepared_revision')"
    revision = prepared + "?['preparedRevision']"; scope = revision + "?['scope']"
    ctx = "outputs('Selected_case_context')"; finding = "first(body('Readiness_scope'))"
    work = {}
    payload = {'Title': "@concat('FICTIONAL ',triggerBody()?['text_1'])", 'EventUID': "@triggerBody()?['text']",
        **{key: '@' + scope + "?['" + key + "']" for key in ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')},
        'Stage': 'Decision', 'RecordState': 'Recorded', 'ConditionsState': 'Open',
        'DecisionOutcome': "@if(equals(triggerBody()?['text_1'],'Rejected'),'Rejected','Deferred')",
        'ActorName': 'FICTIONAL technical operator; real delegated authority not qualified',
        'OccurredOn': '@utcNow()', 'Summary': "@concat(triggerBody()?['text_1'],': ',triggerBody()?['text_2'])",
        'EvidenceReference': "@triggerBody()?['text_3']", 'DecisionReference': "@triggerBody()?['text_3']",
        'ReadinessEventUID': '@' + finding + "?['EventUID']", 'FictionalTest': True,
        'ParentEventUID': None, 'SupersedesEventUID': None,
        'ConditionsNotes': "@triggerBody()?['text_2']", 'NextAction': "@triggerBody()?['text_4']"}
    work['Decision_payload'] = comp(payload)
    work['Read_assurance_before'] = http(uri, 'Decision_payload')
    work['Find_decision_before'] = {'type': 'Query', 'inputs': {'from': "@body('Read_assurance_before')?['value']",
        'where': "@equals(item()?['EventUID'],triggerBody()?['text'])"}, 'runAfter': {'Read_assurance_before': ['Succeeded']}}

    # Copy only final read descriptors from the reviewed readiness observer; its
    # complete snapshots are fresh prerequisites, not persistent authorisation.
    readiness = actions['Route_readiness_check']['actions']['Check_prepared_readiness']['actions']
    def frame(container, suffix, previous):
        for label, original_name in [('readiness', 'Readiness_history_after'), ('consultation', 'Readiness_consultation_after')]:
            name = 'Decision_' + label + '_' + suffix
            container[name] = copy.deepcopy(readiness[original_name]); container[name]['runAfter'] = {previous: ['Succeeded']} if previous else {}
            stable_name = name + '_stable'; stable(container, stable_name, name); previous = stable_name
        for label in ('case', 'draft', 'receipt', 'template', 'source', 'baseline'):
            name = 'Decision_' + label + '_' + suffix
            container[name] = copy.deepcopy(readiness['Readiness_' + label + '_final'])
            container[name]['runAfter'] = {previous: ['Succeeded']}; previous = name
        checks = []
        for label, base in [('readiness', 'Readiness_stable_after'), ('consultation', 'Readiness_consultation_stable_after')]:
            name = 'Decision_' + label + '_' + suffix
            checks += complete(name) + [eq("body('" + name + "_stable')", "body('" + base + "')")]
        checks += [eq("outputs('Decision_case_" + suffix + "')?['headers']?['ETag']", prepared + "?['currentCaseETag']"),
                   eq("body('Decision_case_" + suffix + "')?['CaseUID']", scope + "?['CaseUID']"),
                   eq("body('Decision_case_" + suffix + "')?['evidenceDraftLink']", scope + "?['DocumentReference']")]
        for label, pin in [('draft', revision + "?['file']"), ('receipt', revision + "?['qualificationReceipt']"),
                           ('template', revision + "?['template']"), ('source', ctx + "?['sourcePins']")]:
            checks += [eq("body('Decision_" + label + '_' + suffix + "')?['" + k + "']", pin + "?['" + k + "']") for k in ('UniqueId', 'ETag')]
        checks += [eq("body('Decision_baseline_" + suffix + "')?['UniqueId']", ctx + "?['baselineUniqueId']"),
                   eq("body('Decision_baseline_" + suffix + "')?['ETag']", ctx + "?['baselineETag']")]
        return previous, checks
    last, before = frame(work, 'before', 'Find_decision_before')
    before += complete('Read_assurance_before') + ["lessOrEquals(length(body('Find_decision_before')),1)"]
    saved = "first(body('Find_decision_after'))"
    def matching(row):
        return [eq(row + "?['" + key + "']", "outputs('Decision_payload')?['" + key + "']") for key in payload if key != 'OccurredOn']
    existing = "first(body('Find_decision_before'))"
    refusal = {'Refuse_changed_decision': {'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed',
        'runError': {'code': 'ChangedDecisionRequest', 'message': 'Retained decision differs; preserve original event and do not overwrite or create.'}}}}
    ensure = {'Ensure_decision': guard(["equals(length(body('Find_decision_before')),0)"],
        {'Create_decision': http(uri, method='POST', body="@string(outputs('Decision_payload'))")},
        {'Verify_decision_replay': guard(matching(existing), {'Decision_replay_matched': comp(True)}, refusal)})}
    ensure['Read_assurance_after'] = http(uri, 'Ensure_decision')
    ensure['Find_decision_after'] = {'type': 'Query', 'inputs': {'from': "@body('Read_assurance_after')?['value']",
        'where': "@equals(item()?['EventUID'],triggerBody()?['text'])"}, 'runAfter': {'Read_assurance_after': ['Succeeded']}}
    last_after, after = frame(ensure, 'after', 'Find_decision_after')
    after += complete('Read_assurance_after') + ["equals(length(body('Find_decision_after')),1)"] + matching(saved)
    after += [present(saved + "?['odata.etag']"), present(saved + "?['GUID']"), "greater(int(coalesce(" + saved + "?['Id'],0)),0)",
              present(saved + "?['OccurredOn']"), "lessOrEquals(ticks(" + saved + "?['OccurredOn']),ticks(utcNow()))",
              "if(equals(length(body('Find_decision_before')),1),equals(" + existing + "?['OccurredOn']," + saved + "?['OccurredOn']),true)"]
    after += ["if(equals(length(body('Find_decision_before')),1),equals(union(" + existing + ",json('{\"odata.id\":null}')),union(" + saved + ",json('{\"odata.id\":null}'))),true)"]
    result = {'qualified': True, 'EventUID': "@triggerBody()?['text']", 'nativeEventId': '@' + saved + "?['Id']",
        'scope': '@' + scope, 'originalSourceScope': '@' + revision + "?['originalSourceScope']",
        'ReadinessEventUID': '@' + finding + "?['EventUID']", 'readinessEventETag': '@' + finding + "?['odata.etag']",
        'disposition': "@triggerBody()?['text_1']", 'retainedOccurredOn': '@' + saved + "?['OccurredOn']",
        'createdCount': "@if(equals(length(body('Find_decision_before')),0),1,0)",
        'caseWrites': 0, 'sourceWrites': 0, 'readinessWrites': 0, 'publicationWrites': 0,
        'actorAuthorityQualified': False, 'progressionGranted': False, 'policyApproved': False,
        'contentReadinessGranted': False,
        'realPolicyEffects': False, 'runId': "@workflow()?['run']?['name']"}
    uncertain = {**held, 'createdCount': None, 'reason': 'A decision event may exist but its final frame is unverified; inspect native run and retained event before retry.'}
    ensure['Verify_decision_after'] = guard(after, {'Native_prepared_decision_receipt': comp(result)},
        {'Held_decision_after': comp(uncertain)}, last_after)
    ensure['Verify_decision_after']['expression'] = "@if(equals(length(body('Find_decision_after')),1),and(" + ','.join(after) + '),false)'
    work['Verify_decision_before'] = guard(before, ensure, {'Held_decision_before': comp(held)}, last)
    work['Held_decision_error'] = {'type': 'Compose', 'inputs': uncertain,
        'runAfter': {'Verify_decision_before': ['Failed', 'TimedOut']}}
    prerequisites = [eq(ready + "?['readinessEvidenceConsistent']", 'true'), eq(ready + "?['nativeContextRevalidated']", 'true'),
        eq(ready + "?['technicalConsultationCoverageComplete']", 'true'), eq(ready + "?['selectedEventUID']", finding + "?['EventUID']")]
    # Avoid dereferencing an empty selection until the existing consistency guard passes.
    prerequisites[-1] = "if(equals(" + ready + "?['readinessEvidenceConsistent'],true)," + prerequisites[-1] + ',false)'
    actions['Check_decision_prerequisites'] = guard(prerequisites, work, {'Held_decision_prerequisites': comp(held)})
    actions['Check_decision_prerequisites']['runAfter'] = {'Route_readiness_check': ['Succeeded', 'Failed', 'TimedOut']}
    checks = ["contains(createArray('Rejected','Deferred','Return for changes'),triggerBody()?['text_1'])",
              "startsWith(string(triggerBody()?['text']),'LC03-OP-')", "equals(uriComponent(string(triggerBody()?['text'])),triggerBody()?['text'])"]
    checks += ["not(contains(string(triggerBody()?['text']),decodeUriComponent('" + char + "')))" for char in
               ('%2E', '%7E', '%21', '%2A', '%27', '%28', '%29')]
    for key, maximum in [('text', 80), ('text_1', 32), ('text_2', 200), ('text_3', 255), ('text_4', 4000), ('text_6', 128)]:
        value = "triggerBody()?['" + key + "']"
        checks += [eq(value, 'string(coalesce(' + value + ",''))"), present(value), 'lessOrEquals(length(string(' + value + ')),' + str(maximum) + ')']
    out = copy.deepcopy(target); out['properties']['state'] = 'Stopped'
    d = out['properties']['definition']; d['triggers'] = {'manual': trigger}
    actions['Resolve_context']['runAfter'] = {'Validate_operator_input': ['Succeeded']}
    d['actions'] = {'Validate_operator_input': guard(checks, {'Decision_input_valid': comp(True)},
        {'Refuse_decision_input': {'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed', 'runError': {
            'code': 'InvalidPreparedDecisionInput', 'message': 'Only bounded fictional Rejected, Deferred or Return for changes inputs are supported; no reads or creates attempted.'}}}}), **actions}
    audit_actions(d)
    return out
