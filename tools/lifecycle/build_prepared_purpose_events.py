"""Assemble one explicitly fictional prepared-purpose assertion in an existing flow.

Local generation only. No I/O, deployment, real delegation, approval or publication.
Each invocation selects one purpose; predecessors must already be retained.
"""
import copy
import re
from build_prepared_decision_outcome import digest
from build_selected_event_routes import audit_actions

PURPOSES = (
    ('Committee endorsement', 'committee', 'Endorsed (recorded)'),
    ('Officer signoff', 'officer', 'Endorsed (recorded)'),
    ('Coordinator check', 'coordinator', 'Endorsed (recorded)'),
    ('Final authorisation', 'authorisation', 'Approved (recorded)'),
)


def build(case_work, target, binding):
    source = case_work['properties']['definition']; old = target['properties']['definition']
    if (binding.get('qualificationOnly') is not True
            or digest(source) != binding.get('approvedCaseWorkDefinitionSHA256')
            or digest(old) != binding.get('approvedTargetDefinitionSHA256')
            or target['properties'].get('state') != 'Stopped'):
        raise ValueError('Exact reviewed prepared source and stopped target preimage required')
    if target['properties']['connectionReferences'] != case_work['properties']['connectionReferences']:
        raise ValueError('Preserve qualified connection references')
    uri = binding['assuranceCollectionUri']
    if not re.fullmatch(r"_api/web/lists\(guid'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}'\)/items", uri):
        raise ValueError('Complete fixed assurance collection required')
    if binding.get('eventUIDUnique') is not True or binding.get('observedFieldTypes') != {
            'ActorName': 'Text', 'Summary': 'Text', 'EvidenceReference': 'Text',
            'DecisionReference': 'Text', 'ConditionsNotes': 'Text', 'NextAction': 'Note'}:
        raise ValueError('Observed unique event and native Text/Note contract required')
    if binding.get('observedTextMaxLengths') != {k: 255 for k in
            ('EventUID', 'ActorName', 'Summary', 'EvidenceReference', 'DecisionReference', 'ConditionsNotes')}:
        raise ValueError('Observed native Text255 limits required')
    profile = binding['fictionalRouteProfile']; reference = profile.get('reference', '')
    if (set(profile) != {'reference', 'version', 'FictionalTest', 'grantsRealAuthority'}
            or profile.get('FictionalTest') is not True or profile.get('grantsRealAuthority') is not False
            or not isinstance(profile.get('version'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,16}', profile['version'])
            or not re.fullmatch(r'fictional://[A-Za-z0-9_./-]{1,160}', reference)
            or len(reference + '@' + profile['version']) > 180):
        raise ValueError('Explicit versioned fictional-only route profile required')
    asserted_profile = reference + '@' + profile['version']
    route_digest = digest(profile)
    def purpose_ref(code): return reference + '/' + profile['version'] + '/' + route_digest + '/' + code
    if any(len(purpose_ref(code)) > 255 for _, code, _ in PURPOSES):
        raise ValueError('Full route reference, version, SHA256 and purpose must fit native Text255')
    a = {k: copy.deepcopy(source['actions'][k]) for k in
         ('Resolve_context', 'Route_preparation_check', 'Route_readiness_check')}
    a['Resolve_context']['runAfter'] = {'Validate_purpose_input': ['Succeeded']}
    for name in ('Route_preparation_check', 'Route_readiness_check'):
        a[name]['expression'] = "@equals(outputs('Selected_case_context')?['contextValid'],true)"
    template = a['Resolve_context']['actions']['Read_selected_case']; base = template['inputs']
    def inspect(group):
        for v in group.values():
            if v.get('type') not in ('If', 'Scope', 'Compose', 'OpenApiConnection', 'Query', 'Select', 'Terminate'):
                raise ValueError('Unsupported prerequisite action')
            if v['type'] == 'Terminate' and v['inputs'].get('runStatus') != 'Failed':
                raise ValueError('Successful early termination is not a prerequisite')
            if v['type'] == 'OpenApiConnection':
                q = v['inputs']['parameters']; h = v['inputs']['host']
                if (h.get('apiId') != '/providers/Microsoft.PowerApps/apis/shared_sharepointonline'
                        or h.get('operationId') != 'HttpRequest'
                        or any(h.get(k) != base['host'].get(k) for k in ('apiId', 'operationId', 'connectionName'))
                        or q.get('dataset') != base['parameters']['dataset']
                        or q.get('parameters/method') != 'GET' or 'parameters/body' in q
                        or any(k.lower() in ('x-http-method', 'x-http-method-override') for k in q.get('parameters/headers', {}))):
                    raise ValueError('Only qualified same-connection GET prerequisites may be copied')
            inspect(v.get('actions', {})); inspect(v.get('else', {}).get('actions', {}))
    inspect(a)
    if old['triggers']['manual'].get('kind') != 'Button' or source['triggers']['manual'].get('kind') != 'Button':
        raise ValueError('Existing first-party Button route required')
    def quote(v): return "'" + v.replace("'", "''") + "'"
    def eq(x, y): return 'equals(' + x + ',' + y + ')'
    def both(checks): return 'and(' + ','.join(checks) + ')'
    def present(x): return "not(empty(trim(string(coalesce(" + x + ",'')))))"
    def comp(x, prev=None): return {'type': 'Compose', 'inputs': x, 'runAfter': {prev: ['Succeeded']} if prev else {}}
    def guard(checks, yes, no, prev=None):
        return {'type': 'If', 'expression': '@' + both(checks), 'actions': yes,
            'else': {'actions': no}, 'runAfter': {prev: ['Succeeded']} if prev else {}}
    def http(path, prev=None, body=None):
        v = copy.deepcopy(template); p = v['inputs']['parameters']
        # SharePoint defaults to 100 rows. Bound the full-history observation;
        # the retained guards still refuse every continuation link.
        if path == uri and body is None:
            path += '?$top=5000'
        p.update({'parameters/uri': path, 'parameters/method': 'GET' if body is None else 'POST',
                  'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata'}})
        v['runAfter'] = {prev: ['Succeeded']} if prev else {}
        if body is not None:
            p['parameters/body'] = body; p['parameters/headers']['Content-Type'] = 'application/json;odata=nometadata'
            v['inputs']['retryPolicy'] = {'type': 'none'}
        return v
    def query(from_, where, prev):
        return {'type': 'Query', 'inputs': {'from': from_, 'where': '@' + where}, 'runAfter': {prev: ['Succeeded']}}
    def complete(name):
        return ["empty(body('" + name + "')?['" + key + "'])"
                for key in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink')]
    def stable(container, name, read):
        container[name] = {'type': 'Select', 'inputs': {'from': "@body('" + read + "')?['value']",
            'select': "@union(item(),json('{\"odata.id\":null}'))"}, 'runAfter': {read: ['Succeeded']}}
    held = {'qualified': False, 'createdCount': 0, 'caseWrites': 0, 'sourceWrites': 0,
        'readinessWrites': 0, 'publicationWrites': 0, 'actorAuthorityQualified': False,
        'policyApproved': False, 'progressionGranted': False, 'contentReadinessGranted': False,
        'realPolicyEffects': False, 'reason': 'Explicit fictional purpose, current prepared readiness and complete nonconflicting predecessor history required; no purpose created.'}
    uncertain = {**held, 'createdCount': None, 'reason': 'A purpose event may exist but final evidence is unverified; retain run and reconcile before retry.'}
    prep = "outputs('Native_prepared_revision')"; revision = prep + "?['preparedRevision']"
    scope = revision + "?['scope']"; ctx = "outputs('Selected_case_context')"
    ready = "outputs('Native_readiness_observation')"; finding = "first(body('Readiness_scope'))"
    chosen = "outputs('Chosen_purpose')"
    work = {}; previous = None; profiles = []
    for index, (label, code, outcome) in enumerate(PURPOSES):
        name = 'Purpose_uid_' + code
        expression = "@concat('LC03-PURPOSE-',outputs('Parse_baseline')?['request']?['requestReference'],'-',toLower(" + revision + "?['file']?['UniqueId']),'-v'," + revision + "?['file']?['nativeVersion'],'-" + code + "')"
        work[name] = comp(expression, previous); previous = name
        profiles.append({'label': label, 'code': code, 'ordinal': index, 'outcome': outcome,
            'EventUID': '@outputs(\'' + name + '\')', 'ParentEventUID': None if index == 0 else '@outputs(\'Purpose_uid_' + PURPOSES[index - 1][1] + '\')',
            'DecisionReference': purpose_ref(code)})
    work['Purpose_profile'] = comp(profiles, previous)
    work['Select_purpose'] = query("@outputs('Purpose_profile')", "equals(item()?['label'],triggerBody()?['text'])", 'Purpose_profile')
    work['Chosen_purpose'] = comp("@first(body('Select_purpose'))", 'Select_purpose')
    reader = a['Route_readiness_check']['actions']['Check_prepared_readiness']['actions']
    def frame(container, suffix, prev):
        checks = []
        for label, read, initial in [('readiness', 'Readiness_history_after', 'Readiness_stable_after'),
                                     ('consultation', 'Readiness_consultation_after', 'Readiness_consultation_stable_after')]:
            name = 'Purpose_' + label + '_' + suffix
            container[name] = copy.deepcopy(reader[read]); container[name]['runAfter'] = {prev: ['Succeeded']}
            stable(container, name + '_stable', name); prev = name + '_stable'
            checks += complete(name) + [eq("body('" + prev + "')", "body('" + initial + "')")]
        for label in ('case', 'draft', 'receipt', 'template', 'source', 'baseline'):
            name = 'Purpose_' + label + '_' + suffix
            container[name] = copy.deepcopy(reader['Readiness_' + label + '_final']); container[name]['runAfter'] = {prev: ['Succeeded']}; prev = name
        checks += [eq("outputs('Purpose_case_" + suffix + "')?['headers']?['ETag']", prep + "?['currentCaseETag']"),
                   eq("body('Purpose_case_" + suffix + "')?['CaseUID']", scope + "?['CaseUID']"),
                   eq("body('Purpose_case_" + suffix + "')?['evidenceDraftLink']", scope + "?['DocumentReference']")]
        for label, pin in [('draft', revision + "?['file']"), ('receipt', revision + "?['qualificationReceipt']"),
                           ('template', revision + "?['template']"), ('source', ctx + "?['sourcePins']")]:
            checks += [eq("body('Purpose_" + label + '_' + suffix + "')?['" + k + "']", pin + "?['" + k + "']") for k in ('UniqueId', 'ETag')]
        checks += [eq("body('Purpose_baseline_" + suffix + "')?['UniqueId']", ctx + "?['baselineUniqueId']"),
                   eq("body('Purpose_baseline_" + suffix + "')?['ETag']", ctx + "?['baselineETag']")]
        return prev, checks

    def history(container, prefix, prev, *, require_selected=False):
        read = prefix + '_assurance'; container[read] = http(uri, prev)
        uid_values = ["outputs('Purpose_uid_" + code + "')" for _, code, _ in PURPOSES]
        canonical = 'createArray(' + ','.join(uid_values) + ')'
        scoped = prefix + '_scope'
        scope_checks = [eq("item()?['" + key + "']", scope + "?['" + key + "']") for key in
                        ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')]
        container[scoped] = query("@body('" + read + "')?['value']", both(scope_checks), read)
        problems = ["not(equals(item()?['FictionalTest'],true))", "not(equals(item()?['RecordState'],'Recorded'))",
            "not(contains(createArray('None recorded','Resolved'),item()?['ConditionsState']))",
            "not(empty(item()?['SupersedesEventUID']))",
            "not(equals(item()?['Stage'],'Decision'))",
            "not(contains(" + canonical + ",item()?['EventUID']))" ]
        container[prefix + '_problems'] = query("@body('" + scoped + "')", 'or(' + ','.join(problems) + ')', scoped)
        container[prefix + '_superseders'] = query("@body('" + read + "')?['value']",
            'contains(' + canonical + ",item()?['SupersedesEventUID'])", prefix + '_problems')
        last = prefix + '_superseders'; valid_names = []; row_names = []
        for index, (label, code, outcome) in enumerate(PURPOSES):
            rows = prefix + '_rows_' + code; valid = prefix + '_valid_' + code
            container[rows] = query("@body('" + read + "')?['value']", eq("item()?['EventUID']", uid_values[index]), last)
            item = "first(body('" + rows + "'))"
            checks = [eq(item + "?['" + key + "']", scope + "?['" + key + "']") for key in
                      ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')]
            checks += [eq(item + "?['Stage']", "'Decision'"), eq(item + "?['RecordState']", "'Recorded'"),
                eq(item + "?['DecisionOutcome']", quote(outcome)), eq(item + "?['DecisionReference']", quote(purpose_ref(code))),
                eq(item + "?['ReadinessEventUID']", ready + "?['selectedEventUID']"), eq(item + "?['FictionalTest']", 'true'),
                "contains(createArray('None recorded','Resolved')," + item + "?['ConditionsState'])", "empty(" + item + "?['SupersedesEventUID'])",
                eq(item + "?['ParentEventUID']", 'null' if index == 0 else uid_values[index - 1]),
                "greater(int(coalesce(" + item + "?['Id'],0)),0)", present(item + "?['GUID']"), present(item + "?['odata.etag']"),
                "not(equals(" + item + "?['odata.etag'],'*'))", "startsWith(string(" + item + "?['ActorName']),'FICTIONAL ')",
                "startsWith(string(" + item + "?['EvidenceReference']),'fictional://')",
                eq(item + "?['Summary']", "concat(" + quote('FICTIONAL ' + label + ': ') + ',' + item + "?['ConditionsNotes'])")]
            checks += [present(item + "?['" + key + "']") for key in ('ActorName', 'ConditionsNotes', 'NextAction', 'OccurredOn')]
            checks += ["lessOrEquals(length(string(" + item + "?['ConditionsNotes'])),180)",
                "lessOrEquals(ticks(" + item + "?['OccurredOn']),ticks(utcNow()))",
                "greaterOrEquals(ticks(" + item + "?['OccurredOn']),ticks(" + finding + "?['AssessedOn']))"]
            if index:
                parent = "first(body('" + row_names[-1] + "'))"
                checks += ["if(equals(length(body('" + row_names[-1] + "')),1),greaterOrEquals(ticks(" + item + "?['OccurredOn']),ticks(" + parent + "?['OccurredOn'])),false)"]
            container[valid] = comp("@if(equals(length(body('" + rows + "')),1)," + both(checks) + ',false)', rows)
            row_names.append(rows); valid_names.append(valid); last = valid
        checks = complete(read) + ["equals(length(body('" + prefix + "_problems')),0)", "equals(length(body('" + prefix + "_superseders')),0)"]
        for index, rows in enumerate(row_names):
            checks += ["lessOrEquals(length(body('" + rows + "')),1)",
                "if(equals(length(body('" + rows + "')),1),equals(outputs('" + valid_names[index] + "'),true),true)",
                "if(greater(int(" + chosen + "?['ordinal'])," + str(index) + "),equals(length(body('" + rows + "')),1),true)"]
            if require_selected:
                checks += ["if(equals(int(" + chosen + "?['ordinal'])," + str(index) + "),equals(length(body('" + rows + "')),1),true)"]
        name = prefix + '_history_consistent'; container[name] = comp('@' + both(checks), last)
        selected = prefix + '_selected'
        container[selected] = query("@body('" + read + "')?['value']", eq("item()?['EventUID']", chosen + "?['EventUID']"), name)
        return selected, name

    before_last, before_checks = frame(work, 'before', 'Chosen_purpose')
    before_last, history_name = history(work, 'Purpose_before', before_last)
    # Identity is deterministic for occurrence+physical prepared version+purpose.
    before_checks += [eq("outputs('" + history_name + "')", 'true'),
        "startsWith(string(" + chosen + "?['EventUID']),'LC03-PURPOSE-')",
        "lessOrEquals(length(string(" + chosen + "?['EventUID'])),255)",
        eq("uriComponent(string(" + chosen + "?['EventUID']))", chosen + "?['EventUID']")]
    event = {key: '@' + scope + "?['" + key + "']" for key in ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')}
    event.update({'EventUID': '@' + chosen + "?['EventUID']", 'Title': "@concat('FICTIONAL ',triggerBody()?['text'])",
        'Stage': 'Decision', 'RecordState': 'Recorded', 'DecisionOutcome': '@' + chosen + "?['outcome']",
        'DecisionReference': '@' + chosen + "?['DecisionReference']", 'ReadinessEventUID': '@' + ready + "?['selectedEventUID']",
        'ParentEventUID': '@' + chosen + "?['ParentEventUID']", 'SupersedesEventUID': None,
        'ActorName': "@triggerBody()?['text_1']", 'Summary': "@concat('FICTIONAL ',triggerBody()?['text'],': ',triggerBody()?['text_2'])",
        'ConditionsNotes': "@triggerBody()?['text_2']", 'EvidenceReference': "@triggerBody()?['text_3']",
        'NextAction': "@triggerBody()?['text_4']", 'ConditionsState': "@triggerBody()?['text_5']",
        'OccurredOn': '@utcNow()', 'FictionalTest': True})
    create = {'Purpose_payload': comp(event)}
    before_row = "first(body('Purpose_before_selected'))"
    def match(row):return [eq(row + "?['" + key + "']", "outputs('Purpose_payload')?['" + key + "']") for key in event if key != 'OccurredOn']
    refuse = {'Refuse_changed_purpose': {'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed',
        'runError': {'code': 'ChangedPurposeRequest', 'message': 'Retained purpose differs; preserve it and reconcile, never overwrite or create another identity.'}}}}
    create['Ensure_purpose'] = guard(["equals(length(body('Purpose_before_selected')),0)"],
        {'Create_purpose': http(uri, body="@string(outputs('Purpose_payload'))")},
        {'Verify_purpose_replay': guard(match(before_row), {'Purpose_replay_matched': comp(True)}, refuse)}, 'Purpose_payload')
    after_last, after_checks = frame(create, 'after', 'Ensure_purpose')
    after_last, after_history = history(create, 'Purpose_after', after_last, require_selected=True)
    after_row = "first(body('Purpose_after_selected'))"
    # Compare all untouched Assurance rows, not a filtered favorable subset.
    for suffix in ('before', 'after'):
        name = 'Purpose_other_' + suffix; read = 'Purpose_' + suffix + '_assurance'
        create[name] = query("@body('" + read + "')?['value']", 'not(' + eq("item()?['EventUID']", chosen + "?['EventUID']") + ')', after_last)
        create[name + '_stable'] = {'type': 'Select', 'inputs': {'from': "@body('" + name + "')",
            'select': "@union(item(),json('{\"odata.id\":null}'))"}, 'runAfter': {name: ['Succeeded']}}
        after_last = name + '_stable'
    after_checks += [eq("outputs('" + after_history + "')", 'true'), eq("body('Purpose_other_before_stable')", "body('Purpose_other_after_stable')")]
    after_checks += match(after_row) + ["if(equals(length(body('Purpose_before_selected')),1),equals(union(" + before_row + ",json('{\"odata.id\":null}')),union(" + after_row + ",json('{\"odata.id\":null}'))),true)"]
    receipt = {'qualified': True, 'EventUID': '@' + chosen + "?['EventUID']", 'purpose': '@' + chosen + "?['label']",
        'nativeEventId': '@' + after_row + "?['Id']", 'eventETag': '@' + after_row + "?['odata.etag']",
        'ParentEventUID': '@' + chosen + "?['ParentEventUID']", 'ReadinessEventUID': '@' + ready + "?['selectedEventUID']",
        'preparedScope': '@' + scope, 'originalSourceScope': '@' + revision + "?['originalSourceScope']",
        'fictionalRouteProfile': {'reference': reference, 'version': profile['version'], 'SHA256': route_digest},
        'retainedPurposeChain': {code: "@if(equals(length(body('Purpose_after_rows_" + code + "')),1),first(body('Purpose_after_rows_" + code + "')),null)" for _, code, _ in PURPOSES},
        'allFourPurposeAssertionsPresent': '@' + both(["equals(length(body('Purpose_after_rows_" + code + "')),1)" for _, code, _ in PURPOSES]),
        'createdCount': "@if(equals(length(body('Purpose_before_selected')),0),1,0)", 'retainedOccurredOn': '@' + after_row + "?['OccurredOn']",
        'caseWrites': 0, 'sourceWrites': 0, 'readinessWrites': 0, 'publicationWrites': 0,
        'actorAuthorityQualified': False, 'policyApproved': False, 'contentReadinessGranted': False,
        'progressionGranted': False, 'realPolicyEffects': False, 'runId': "@workflow()?['run']?['name']"}
    create['Verify_purpose_after'] = guard(after_checks, {'Native_purpose_receipt': comp(receipt)}, {'Held_purpose_after': comp(uncertain)}, after_last)
    create['Verify_purpose_after']['expression'] = "@if(equals(length(body('Purpose_after_selected')),1)," + both(after_checks) + ',false)'
    work['Verify_purpose_before'] = guard(before_checks, create, {'Held_purpose_history': comp(held)}, before_last)
    prereq = [eq(ready + "?['readinessEvidenceConsistent']", 'true'), eq(ready + "?['nativeContextRevalidated']", 'true'),
              eq(ready + "?['technicalConsultationCoverageComplete']", 'true')]
    a['Check_purpose_prerequisites'] = guard(prereq, work, {'Held_purpose_prerequisites': comp(held)})
    a['Check_purpose_prerequisites']['runAfter'] = {'Route_readiness_check': ['Succeeded', 'Failed', 'TimedOut']}
    a['Held_purpose_error'] = {'type': 'Compose', 'inputs': uncertain, 'runAfter': {'Check_purpose_prerequisites': ['Failed', 'TimedOut']}}
    labels = ','.join(quote(label) for label, _, _ in PURPOSES)
    checks = ["contains(createArray(" + labels + "),triggerBody()?['text'])", eq("triggerBody()?['text_7']", quote(asserted_profile)),
        "startsWith(string(triggerBody()?['text_1']),'FICTIONAL ')", "startsWith(string(triggerBody()?['text_3']),'fictional://')",
        "contains(createArray('None recorded','Resolved'),triggerBody()?['text_5'])"]
    for key, limit in [('text', 32), ('text_1', 200), ('text_2', 180), ('text_3', 255), ('text_4', 4000), ('text_5', 32), ('text_6', 128), ('text_7', 180)]:
        value = "triggerBody()?['" + key + "']"
        checks += [eq(value, 'string(coalesce(' + value + ",''))"), present(value), 'lessOrEquals(length(string(' + value + ')),' + str(limit) + ')']
    a = {'Validate_purpose_input': guard(checks, {'Purpose_input_valid': comp(True)},
        {'Refuse_purpose_input': {'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed',
            'runError': {'code': 'InvalidFictionalPurposeInput', 'message': 'Explicit bounded fictional purpose/actor/rationale/evidence/conditions and exact route profile required; no I/O attempted.'}}}}), **a}
    titles = {'text': 'Purpose', 'text_1': 'Fictional actor', 'text_2': 'Fictional rationale', 'text_3': 'Fictional evidence reference',
              'text_4': 'Next action', 'text_5': 'Conditions assertion', 'text_6': 'Case reference', 'text_7': 'Fictional route profile'}
    fields = {key: {'type': 'string', 'title': title, 'x-ms-dynamically-added': True, 'x-ms-content-hint': 'TEXT'} for key, title in titles.items()}
    fields['text']['description'] = 'Enter exactly one: ' + ' / '.join(label for label, _, _ in PURPOSES) + '. Recording only; no real authority.'
    fields['text_2']['description'] = 'Explicit technical rationale, at most 180 characters.'
    fields['text_4']['description'] = 'Full next action, at most 4000 characters; no assignment or notification.'
    fields['text_5']['description'] = 'Enter None recorded or Resolved. Other relevant adverse evidence still holds.'
    fields['text_6'] = copy.deepcopy(source['triggers']['manual']['inputs']['schema']['properties']['text_6'])
    fields['text_7']['description'] = 'Enter exactly ' + asserted_profile + '; explicitly fictional, no real delegation.'
    out = copy.deepcopy(target); out['properties']['state'] = 'Stopped'; d = out['properties']['definition']
    trigger = copy.deepcopy(old['triggers']['manual']); trigger['inputs']['schema'] = {'type': 'object', 'properties': fields, 'required': list(fields)}
    trigger['runtimeConfiguration'] = {'concurrency': {'runs': 1}}; d['triggers'] = {'manual': trigger}; d['actions'] = a
    audit_actions(d)
    return out
