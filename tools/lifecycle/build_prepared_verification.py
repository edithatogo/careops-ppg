"""Compose event-only fictional verification from a reviewed implementation graph.

Local builder only. Requires an explicit retained parent, preserves all upstream
proof gates, and never deploys, implements, publishes, closes or sets review dates.
"""
import copy
import re
from build_prepared_implementation import digest
from build_selected_event_routes import audit_actions


def rewrite(value, replacements):
    if isinstance(value, dict):
        return {rewrite(k, replacements): rewrite(v, replacements) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite(v, replacements) for v in value]
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
    return value


def build(implementation, target, binding):
    source = implementation['properties']['definition']
    if (binding.get('qualificationOnly') is not True
            or target['properties'].get('state') != 'Stopped'
            or digest(source) != binding.get('approvedImplementationDefinitionSHA256')
            or digest(target['properties']['definition']) != binding.get('approvedTargetDefinitionSHA256')):
        raise ValueError('Reviewed implementation definition and stopped target required')
    refs = implementation['properties']['connectionReferences']
    if target['properties']['connectionReferences'] != refs or set(refs) != {'shared_sharepointonline'}:
        raise ValueError('Matching existing SharePoint references required')
    parent = copy.deepcopy(binding['retainedImplementation'])
    full_actions = 'ImplementationActionsNote' in source['actions']['Implementation_payload']['inputs']
    if full_actions and (not isinstance(parent.get('ImplementationActionsNote'), str)
                         or not parent['ImplementationActionsNote'].startswith('FICTIONAL')
                         or len(parent['ImplementationActionsNote']) > 2000):
        raise ValueError('Complete retained full implementation action note required')
    for key in ['EventUID', 'CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256',
                'ParentEventUID', 'ReadinessEventUID', 'PublicationURL', 'PublishedVersionRef',
                'ImplementationActions', 'EvidenceReference', 'NextAction', 'OccurredOn', 'GUID', 'odata.etag']:
        if not isinstance(parent.get(key), str) or not parent[key].strip():
            raise ValueError('Complete retained implementation required: ' + key)
    if (parent.get('FictionalTest') is not True or parent.get('Stage') != 'Implementation'
            or parent.get('RecordState') != 'Recorded' or parent.get('ConditionsState') != 'None recorded'
            or parent.get('SupersedesEventUID') not in (None, '')
            or type(parent.get('Id')) is not int or parent['Id'] <= 0 or parent['odata.etag'] == '*'
            or not re.fullmatch(r'LC04-IMPL-PREPARED-[A-Za-z0-9_-]+', parent['EventUID'])
            or any(not parent[k].startswith('FICTIONAL') for k in ['ImplementationActions', 'NextAction'])
            or not parent['EvidenceReference'].startswith('fictional://')):
        raise ValueError('Exact recorded fictional implementation without open conditions required')
    def literal(value):
        return "'" + value.replace("'", "''") + "'"
    frozen = {'text': 'Record implementation', 'text_1': parent['EventUID'],
              'text_2': parent['ImplementationActionsNote'] if full_actions else parent['ImplementationActions'], 'text_3': parent['EvidenceReference'],
              'text_4': parent['NextAction']}
    actions = rewrite(copy.deepcopy(source['actions']),
                      {"triggerBody()?['" + key + "']": literal(value) for key, value in frozen.items()})
    for name in ['Implementation_uid', 'Ensure_implementation', 'Native_implementation_receipt',
                 'Unknown_implementation_effect', 'Verify_implementation_after']:
        if name not in actions:
            raise ValueError('Complete reviewed implementation contract required')
    actions.pop('Unknown_implementation_effect')
    actions['Native_implementation_receipt']['inputs']['implementationCreatedCount'] = 0
    # A missing parent is a hold, never an invitation to create it.
    actions['Ensure_implementation'] = {'type': 'Compose', 'inputs': 'Read-only retained parent check',
        'runAfter': {'Verify_retained_implementation': ['Succeeded']}}
    held = {'qualified': False, 'verificationCreatedCount': 0, 'implementationWrites': 0,
            'caseWrites': 0, 'sourceWrites': 0, 'issuedFileWrites': 0, 'publicationWrites': 0,
            'notifications': 0, 'realPolicyEffects': False, 'actorAuthorityQualified': False,
            'completionGranted': False, 'progressionGranted': False}
    def compose(value, previous=None):
        return {'type': 'Compose', 'inputs': value, 'runAfter': {previous: ['Succeeded']} if previous else {}}
    def gate(name, checks, previous, unknown=False):
        return {'type': 'If', 'expression': '@and(' + ','.join(checks) + ')', 'actions': {},
                'else': {'actions': {'Held_' + name: compose({**held, 'reason': name,
                    'verificationCreatedCount': None if unknown else 0, 'reconcileBeforeRetry': unknown}),
                    'Stop_' + name: {'type': 'Terminate', 'inputs': {'runStatus': 'Succeeded'},
                                    'runAfter': {'Held_' + name: ['Succeeded']}}}},
                'runAfter': {previous: ['Succeeded']} if previous else {}}
    stable_parent = {**parent, 'odata.id': None}
    actions['Retained_implementation'] = compose(stable_parent, 'Verify_implementation_replay')
    actions['Verify_retained_implementation'] = gate('retained_implementation', [
        "if(equals(length(body('Find_implementation')),1),equals(union(first(body('Find_implementation')),json('{\"odata.id\":null}')),outputs('Retained_implementation')),false)"], 'Retained_implementation')
    checks = ["equals(triggerBody()?['text'],'Record verification')",
              "contains(createArray('Verified (recorded)','Failed','Inconclusive'),triggerBody()?['text_2'])"]
    for key, limit in [('text_1', 80), ('text_3', 255), ('text_4', 255), ('text_5', 2000)]:
        v = "triggerBody()?['" + key + "']"
        checks += ['equals(' + v + ',string(coalesce(' + v + ",'')))",
                   'not(empty(trim(string(' + v + '))))', 'lessOrEquals(length(string(' + v + ')),' + str(limit) + ')']
    checks += ["startsWith(triggerBody()?['text_1'],'LC04-VERIFY-PREPARED-')",
               "equals(uriComponent(triggerBody()?['text_1']),triggerBody()?['text_1'])",
               "startsWith(triggerBody()?['text_3'],'FICTIONAL')",
               "startsWith(triggerBody()?['text_4'],'https://')",
               "startsWith(triggerBody()?['text_5'],'FICTIONAL')",
               'not(equals(triggerBody()?[\'text_1\'],outputs(\'Retained_parent_uid\')))']
    head = {'Retained_parent_uid': compose(parent['EventUID']),
            'Validate_verification_input': gate('invalid_verification_input', checks, 'Retained_parent_uid'),
            'Verification_uid': compose("@triggerBody()?['text_1']", 'Validate_verification_input')}
    actions['Validate_implementation_input']['runAfter'] = {'Verification_uid': ['Succeeded']}
    # The sole new identity is independently checked globally below. Exclude only
    # it from the four-purpose classifier, preserving every other history guard.
    for name, action in actions.items():
        if name.endswith('Purpose_before_scope'):
            action['inputs']['where'] = '@and(' + action['inputs']['where'][1:] + ",not(equals(item()?['EventUID'],outputs('Verification_uid'))))"
    actions = {**head, **actions}
    history = 'Implementation_after_Purpose_before_assurance'
    def query(name, history_name, predicate, previous, dest=actions):
        dest[name] = {'type': 'Query', 'inputs': {'from': "@body('" + history_name + "')?['value']", 'where': '@' + predicate},
                      'runAfter': {previous: ['Succeeded']}}
    query('Find_verification', history, "equals(item()?['EventUID'],outputs('Verification_uid'))", 'Native_implementation_receipt')
    query('Find_verification_corrections', history, "equals(item()?['SupersedesEventUID'],outputs('Verification_uid'))", 'Find_verification')
    actions['Verify_verification_identity'] = gate('verification_identity', [
        "lessOrEquals(length(body('Find_verification')),1)", "equals(length(body('Find_verification_corrections')),0)",
        "not(empty(outputs('Native_implementation_receipt')?['publication']?['EvidenceReference']))",
        "equals(triggerBody()?['text_4'],outputs('Native_implementation_receipt')?['publication']?['EvidenceReference'])"], 'Find_verification_corrections')
    payload = {k: parent[k] for k in ['CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256',
                                    'ReadinessEventUID', 'PublicationURL', 'PublishedVersionRef']}
    payload.update(EventUID="@outputs('Verification_uid')", Title='FICTIONAL prepared verification record',
        Stage='Verification', RecordState='Recorded', FictionalTest=True,
        ConditionsState="@if(equals(triggerBody()?['text_2'],'Verified (recorded)'),'None recorded','Open')",
        ConditionsNotes="@if(equals(triggerBody()?['text_2'],'Verified (recorded)'),'FICTIONAL technical finding; no real effectiveness or closure asserted.',triggerBody()?['text_3'])",
        ParentEventUID=parent['EventUID'], SupersedesEventUID=None, DecisionOutcome='Unknown',
        ActorName='FICTIONAL technical verification actor; real authority unqualified',
        Summary='FICTIONAL verification recording only', VerificationResult="@triggerBody()?['text_2']",
        VerificationMethod="@triggerBody()?['text_3']", EvidenceReference="@triggerBody()?['text_4']",
        NextAction="@triggerBody()?['text_5']",
        OccurredOn="@if(equals(length(body('Find_verification')),1),first(body('Find_verification'))?['OccurredOn'],formatDateTime(utcNow(),'yyyy-MM-ddTHH:mm:ssZ'))")
    actions['Verification_payload'] = compose(payload, 'Verify_verification_identity')
    def matches(row):
        return ["equals(" + row + "?['" + k + "'],outputs('Verification_payload')?['" + k + "'])" for k in payload] + [
            'greater(int(coalesce(' + row + "?['Id'],0)),0)", 'not(empty(' + row + "?['GUID']))",
            'not(empty(' + row + "?['odata.etag']))", 'not(equals(' + row + "?['odata.etag'],'*'))",
            'lessOrEquals(ticks(' + row + "?['OccurredOn']),ticks(utcNow()))",
            'greaterOrEquals(ticks(' + row + "?['OccurredOn']),ticks(outputs('Retained_implementation')?['OccurredOn']))"]
    old = "first(body('Find_verification'))"
    actions['Verify_verification_replay'] = gate('verification_replay', [
        "if(equals(length(body('Find_verification')),1),and(" + ','.join(matches(old)) + '),true)'], 'Verification_payload')
    create = copy.deepcopy(actions['Before_event_Purpose_before_assurance'])
    create['runAfter'] = {}; create['inputs']['retryPolicy'] = {'type': 'none'}
    create['inputs']['parameters'].update({'parameters/method': 'POST', 'parameters/body': "@string(outputs('Verification_payload'))",
        'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata', 'Content-Type': 'application/json;odata=nometadata'}})
    actions['Ensure_verification'] = {'type': 'If', 'expression': "@equals(length(body('Find_verification')),0)",
        'actions': {'Create_verification': create}, 'else': {'actions': {}}, 'runAfter': {'Verify_verification_replay': ['Succeeded']}}
    # Preserve the complete initial qualification graph, then repeat its existing
    # full native after-frame contract. Repeating the entire initial graph would
    # exceed the native action limit for the actual retained implementation.
    # The fresh frame compares all source/case/readiness/consultation/purpose and
    # issued/proof pins against those already qualified before this append.
    pre = {k: v for k, v in actions.items() if k.startswith('Implementation_after_')}
    frame_checks = [k for k in pre if k.startswith('Implementation_after_frame_check_')]
    entries = [k for k, v in pre.items() if 'Ensure_implementation' in v.get('runAfter', {})]
    if len(entries) != 1 or not frame_checks:
        raise ValueError('Complete implementation after-frame contract required')
    # Include nested action names, not just top-level dependencies.
    def names(nodes):
        found = []
        for k, v in nodes.items():
            found.append(k)
            found += names(v.get('actions', {})); found += names(v.get('else', {}).get('actions', {}))
        return found
    replacements = {name: 'Verification_after_' + name for name in sorted(names(pre), key=len, reverse=True)}
    # Rename native dependencies and action-reference expressions only. Human
    # text and retained payload values must never be rewritten as action names.
    pattern = re.compile(r"\b(body|outputs|actions|result)\('([^']+)'\)")
    def rename(v):
        if isinstance(v, dict):
            return {replacements.get(k, k): rename(x) for k, x in v.items()}
        if isinstance(v, list):
            return [rename(x) for x in v]
        if isinstance(v, str) and v.startswith('@'):
            return pattern.sub(lambda m: m[1] + "('" + replacements.get(m[2], m[2]) + "')", v)
        return v
    after = rename(copy.deepcopy(pre))
    after['Verification_after_' + entries[0]]['runAfter'] = {'Ensure_verification': ['Succeeded']}
    # Whole-object equality requires the same route and projection. The reused
    # implementation frame's proof GET selects only identity/token, whereas the
    # initial publication proof GET also selects length and path.
    proof_after = 'Verification_after_Implementation_after_proof'
    if proof_after not in after or 'Read_binary_proof_before' not in actions:
        raise ValueError('Exact proof metadata request pair required')
    proof_dependency = after[proof_after]['runAfter']
    after[proof_after] = copy.deepcopy(actions['Read_binary_proof_before'])
    after[proof_after]['runAfter'] = proof_dependency
    actions.update(after)
    final_history = 'Verification_after_' + history
    query('Read_verification', final_history, "equals(item()?['EventUID'],outputs('Verification_uid'))", 'Verification_after_' + frame_checks[-1])
    query('Read_verification_corrections', final_history, "equals(item()?['SupersedesEventUID'],outputs('Verification_uid'))", 'Read_verification')
    query('Verification_parent_after', final_history,
          "equals(item()?['EventUID'],outputs('Retained_parent_uid'))", 'Read_verification_corrections')
    query('Verification_parent_corrections_after', final_history,
          "equals(item()?['SupersedesEventUID'],outputs('Retained_parent_uid'))", 'Verification_parent_after')
    previous = 'Verification_parent_corrections_after'
    for label, hist in [('before', history), ('after', final_history)]:
        name = 'Verification_others_' + label
        query(name, hist, "not(equals(item()?['EventUID'],outputs('Verification_uid')))", previous)
        actions[name + '_stable'] = {'type': 'Select', 'inputs': {'from': "@body('" + name + "')",
            'select': "@union(item(),json('{\"odata.id\":null}'))"}, 'runAfter': {name: ['Succeeded']}}
        previous = name + '_stable'
    row = "first(body('Read_verification'))"
    # Pin the same full observed file/case metadata across the verification
    # write, even if both independent frame evaluations could otherwise pass.
    frame_equality = []
    pairs = [('Read_issued', 'Implementation_after_issued'),
             ('Read_binary_proof_before', 'Implementation_after_proof')]
    pairs += [('Before_event_Purpose_' + kind + '_before',
               'Implementation_after_Purpose_' + kind + '_before')
              for kind in ['draft', 'receipt', 'template', 'source', 'baseline', 'case']]
    for before_name, after_name in pairs:
        after_name = 'Verification_after_' + after_name
        if before_name not in actions or after_name not in actions:
            raise ValueError('Complete retained metadata frame required: ' + before_name)
        frame_equality.append("equals(union(body('" + before_name + "'),json('{\"odata.id\":null}')),union(body('" + after_name + "'),json('{\"odata.id\":null}')))")
    frame_equality += ["equals(outputs('Verification_after_" + name + "'),true)" for name in frame_checks]
    frame_equality += [
        "equals(length(body('Verification_parent_corrections_after')),0)",
        "if(equals(length(body('Verification_parent_after')),1),equals(union(first(body('Verification_parent_after')),json('{\"odata.id\":null}')),outputs('Retained_implementation')),false)"]
    actions['Verify_verification_after'] = gate('verification_after', frame_equality + [
        "empty(body('" + final_history + "')?['nextLink'])", "empty(body('" + final_history + "')?['@nextLink'])",
        "empty(body('" + final_history + "')?['odata.nextLink'])", "empty(body('" + final_history + "')?['@odata.nextLink'])",
        "equals(length(body('Read_verification_corrections')),0)",
        "equals(body('Verification_others_before_stable'),body('Verification_others_after_stable'))",
        "if(equals(length(body('Read_verification')),1),and(" + ','.join(matches(row)) + '),false)',
        "if(and(equals(length(body('Find_verification')),1),equals(length(body('Read_verification')),1)),equals(union(" + old + ",json('{\"odata.id\":null}')),union(" + row + ",json('{\"odata.id\":null}'))),true)"], previous, unknown=True)
    actions['Native_verification_receipt'] = compose({**held, 'qualified': True,
        'verificationCreatedCount': "@if(equals(length(body('Find_verification')),0),1,0)",
        'implementation': "@outputs('Retained_implementation')", 'verification': '@' + row,
        'runId': "@workflow()?['run']?['name']"}, 'Verify_verification_after')
    actions['Unknown_verification_effect'] = compose({**held, 'verificationCreatedCount': None,
        'reconcileBeforeRetry': True, 'reason': 'Retain run and reconcile uncertain write/readback before retry.'})
    actions['Unknown_verification_effect']['runAfter'] = {'Verify_verification_after': ['Failed', 'TimedOut', 'Skipped']}
    out = copy.deepcopy(target); out['properties']['state'] = 'Stopped'; out['properties']['definition']['actions'] = actions
    fields = {key: {'type': 'string', 'title': title} for key, title in [
        ('text', 'Action'), ('text_1', 'Verification reference'), ('text_2', 'Fictional verification result'),
        ('text_3', 'Fictional method and finding (maximum 255 characters)'), ('text_4', 'Technical proof reference'),
        ('text_5', 'Fictional next action')]}
    fields['text_6'] = copy.deepcopy(source['triggers']['manual']['inputs']['schema']['properties']['text_6'])
    out['properties']['definition']['triggers'] = {'manual': {'type': 'Request', 'kind': 'Button',
        'inputs': {'schema': {'type': 'object', 'properties': fields, 'required': list(fields)}},
        'runtimeConfiguration': {'concurrency': {'runs': 1}}}}
    audit = audit_actions(out['properties']['definition'])
    def all_actions(nodes):
        for name, action in nodes.items():
            yield name, action
            yield from all_actions(action.get('actions', {}))
            yield from all_actions(action.get('else', {}).get('actions', {}))
            for case in action.get('cases', {}).values():
                yield from all_actions(case.get('actions', {}))
            yield from all_actions(action.get('default', {}).get('actions', {}))
    flat = dict(all_actions(actions))
    writers = {name for name, action in flat.items()
               if action['type'] == 'OpenApiConnection'
               and action['inputs']['parameters']['parameters/method'] != 'GET'}
    if writers != {'Create_verification'}:
        raise ValueError('Only the reviewed verification event writer is permitted')
    if (audit['actionCount'] > 500 or any(len(name) > 80 for name in flat)
            or any(len(action.get('expression', '')) > 8192 for action in flat.values())):
        raise ValueError('Composed native definition exceeds qualified limits')
    return out
