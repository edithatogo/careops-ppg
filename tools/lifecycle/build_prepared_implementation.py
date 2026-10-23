"""Compose fictional implementation recording from a reviewed publication graph.

Local only. The publication graph's prepared/readiness/purpose/proof checks remain
prerequisites, including its held producer gate until actual proof is qualified.
No copy, publication, case, permission or notification writer is retained.
"""
import copy
import hashlib
import json

from build_selected_event_routes import audit_actions


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build(publication, target, binding):
    source = publication['properties']['definition']
    if (binding.get('qualificationOnly') is not True
            or target['properties'].get('state') != 'Stopped'
            or digest(source) != binding.get('approvedPublicationDefinitionSHA256')
            or digest(target['properties']['definition']) != binding.get('approvedTargetDefinitionSHA256')):
        raise ValueError('Exact reviewed publication graph and stopped target required')
    refs = target['properties']['connectionReferences']
    if refs != publication['properties']['connectionReferences'] or set(refs) != {'shared_sharepointonline'}:
        raise ValueError('Existing matching SharePoint-only references required')
    note = binding.get('implementationActionsNoteField')
    if note is not None:
        if (not isinstance(note, dict)
                or note.get('InternalName') != 'ImplementationActionsNote'
                or note.get('TypeAsString') != 'Note'
                or note.get('RichText') is not False
                or note.get('AppendOnly') is not False
                or note.get('ReadOnlyField') is not False
                or binding.get('approvedImplementationActionsNoteFieldSHA256') != digest(note)):
            raise ValueError('Reviewed writable plain implementation-actions Note contract required')
    elif binding.get('approvedImplementationActionsNoteFieldSHA256') is not None:
        raise ValueError('Implementation-actions Note pin requires its observed field contract')
    actions_limit = 2000 if note is not None else 255
    original = source['actions']
    required = ['Verify_record_producer_trust', 'Verify_publication_replay',
                'Find_existing_publication', 'Read_binary_proof_before', 'Before_event_issued']
    if any(name not in original for name in required):
        raise ValueError('Complete reviewed prepared binary publication contract required')

    def rewrite(value, replacements):
        if isinstance(value, dict):
            return {rewrite(k, replacements): rewrite(v, replacements) for k, v in value.items()}
        if isinstance(value, list):
            return [rewrite(v, replacements) for v in value]
        if isinstance(value, str):
            for old, new in replacements.items():
                value = value.replace(old, new)
        return value

    # Reuse the source's existing Record checks, never invoke its writers.
    actions = {}
    omitted = {'Copy_if_absent', 'Observe_copy_phase', 'Stop_copy_phase'}
    for name, action in original.items():
        if name not in omitted:
            actions[name] = rewrite(copy.deepcopy(action), {"triggerBody()?['text']": "'Record publication'"})
        if name == 'Verify_publication_replay':
            break
    else:
        raise ValueError('Publication prerequisite boundary missing')
    actions['Read_issued']['runAfter'] = {'Verify_target_cardinality': ['Succeeded']}
    actions['Verify_record_producer_trust']['runAfter'] = {'Verify_issued_metadata': ['Succeeded']}
    # Existing target must already exist; this consumer never repairs/copies it.
    actions['Verify_target_cardinality']['expression'] = (
        '@and(' + actions['Verify_target_cardinality']['expression'][1:]
        + ",equals(length(body('Find_issued')?['value']),1))")

    def both(checks):
        return 'and(' + ','.join(checks) + ')'
    def eq(a, b):
        return 'equals(' + a + ',' + b + ')'
    def comp(value, previous=None):
        return {'type': 'Compose', 'inputs': value,
                'runAfter': {previous: ['Succeeded']} if previous else {}}
    held = {'qualified': False, 'implementationCreatedCount': 0,
            'caseWrites': 0, 'sourceWrites': 0, 'publicationWrites': 0,
            'readinessWrites': 0, 'issuedFileWrites': 0, 'notifications': 0,
            'realPolicyEffects': False, 'implementationCompletionGranted': False,
            'actorAuthorityQualified': False, 'progressionGranted': False}
    def gate(name, checks, previous=None, unknown=False):
        return {'type': 'If', 'expression': '@' + both(checks), 'actions': {},
                'else': {'actions': {
                    'Held_' + name: comp({**held, 'reason': name,
                        'implementationCreatedCount': None if unknown else 0,
                        'reconcileBeforeRetry': unknown}),
                    'Stop_' + name: {'type': 'Terminate', 'inputs': {'runStatus': 'Succeeded'},
                                    'runAfter': {'Held_' + name: ['Succeeded']}}}},
                'runAfter': {previous: ['Succeeded']} if previous else {}}
    checks = ["equals(triggerBody()?['text'],'Record implementation')"]
    for key, limit in [('text_1', 80), ('text_2', actions_limit), ('text_3', 255), ('text_4', 2000)]:
        value = "triggerBody()?['" + key + "']"
        checks += [eq(value, 'string(coalesce(' + value + ",''))"),
                   "not(empty(trim(string(" + value + '))))',
                   'lessOrEquals(length(string(' + value + ')),' + str(limit) + ')']
    checks += ["startsWith(triggerBody()?['text_1'],'LC04-IMPL-PREPARED-')",
               "equals(uriComponent(triggerBody()?['text_1']),triggerBody()?['text_1'])",
               "startsWith(triggerBody()?['text_2'],'FICTIONAL')",
               "startsWith(triggerBody()?['text_3'],'fictional://')",
               "startsWith(triggerBody()?['text_4'],'FICTIONAL')"]
    actions = {'Validate_implementation_input': gate('invalid_implementation_input', checks),
               'Implementation_uid': comp("@triggerBody()?['text_1']", 'Validate_implementation_input'),
               **actions}
    actions['Validate_publication_input']['runAfter'] = {'Implementation_uid': ['Succeeded']}
    # Exclude only this implementation identity from the producer's four-purpose
    # classifier; global identity/payload/correction checks below still apply.
    for name, action in actions.items():
        if name.endswith('Purpose_before_scope'):
            action['inputs']['where'] = '@and(' + action['inputs']['where'][1:] + ",not(equals(item()?['EventUID'],outputs('Implementation_uid'))))"

    def query(name, history, predicate, previous):
        actions[name] = {'type': 'Query', 'inputs': {'from': "@body('" + history + "')?['value']",
            'where': '@' + predicate}, 'runAfter': {previous: ['Succeeded']}}
    history = 'Before_event_Purpose_before_assurance'
    query('Find_implementation', history, "equals(item()?['EventUID'],outputs('Implementation_uid'))", 'Verify_publication_replay')
    query('Find_implementation_corrections', history, "equals(item()?['SupersedesEventUID'],outputs('Implementation_uid'))", 'Find_implementation')
    publication_row = "first(body('Find_existing_publication'))"
    pub_checks = ["lessOrEquals(ticks(" + publication_row + "?['OccurredOn']),ticks(utcNow()))",
                  "greaterOrEquals(ticks(" + publication_row + "?['OccurredOn']),ticks(first(body('Purpose_before_rows_authorisation'))?['OccurredOn']))"]
    actions['Verify_implementation_parent'] = gate('implementation_parent', [
        "if(equals(length(body('Find_existing_publication')),1)," + both(pub_checks) + ',false)',
        "lessOrEquals(length(body('Find_implementation')),1)",
        "equals(length(body('Find_implementation_corrections')),0)"], 'Find_implementation_corrections')
    scope = "outputs('Native_prepared_revision')?['preparedRevision']?['scope']"
    payload = {k: '@' + scope + "?['" + k + "']" for k in
               ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')}
    payload.update(EventUID="@outputs('Implementation_uid')", Title='FICTIONAL prepared implementation record',
        Stage='Implementation', RecordState='Recorded', FictionalTest=True,
        ConditionsState='None recorded', ConditionsNotes='FICTIONAL technical fixture; no real policy rollout is asserted.',
        ParentEventUID="@outputs('Publication_uid')", SupersedesEventUID=None,
        ReadinessEventUID="@outputs('Native_readiness_observation')?['selectedEventUID']",
        ActorName='FICTIONAL technical implementation actor; real authority unqualified',
        Summary='FICTIONAL implementation recording only; no clinical rollout or effectiveness claim',
        ImplementationActions="@triggerBody()?['text_2']", EvidenceReference="@triggerBody()?['text_3']",
        NextAction="@triggerBody()?['text_4']",
        PublicationURL='@' + publication_row + "?['PublicationURL']",
        PublishedVersionRef='@' + publication_row + "?['PublishedVersionRef']",
        OccurredOn="@if(equals(length(body('Find_implementation')),1),first(body('Find_implementation'))?['OccurredOn'],formatDateTime(utcNow(),'yyyy-MM-ddTHH:mm:ssZ'))")
    if note is not None:
        # Preserve full text in the observed Note column. The legacy Text255
        # field remains a summary; long input is never silently truncated.
        payload['ImplementationActionsNote'] = "@triggerBody()?['text_2']"
        payload['ImplementationActions'] = (
            "@if(lessOrEquals(length(triggerBody()?['text_2']),255),"
            "triggerBody()?['text_2'],"
            "'FICTIONAL detailed implementation actions retained in the full action note.')")
    actions['Implementation_payload'] = comp(payload, 'Verify_implementation_parent')
    def matches(row):
        return [eq(row + "?['" + k + "']", "outputs('Implementation_payload')?['" + k + "']") for k in payload]
    def identity(row):
        return ["greater(int(coalesce(" + row + "?['Id'],0)),0)",
                "not(empty(" + row + "?['GUID']))", "not(empty(" + row + "?['odata.etag']))",
                "not(equals(" + row + "?['odata.etag'],'*'))",
                "lessOrEquals(ticks(" + row + "?['OccurredOn']),ticks(utcNow()))",
                "greaterOrEquals(ticks(" + row + "?['OccurredOn']),ticks(" + publication_row + "?['OccurredOn']))"]
    old_row = "first(body('Find_implementation'))"
    actions['Verify_implementation_replay'] = gate('implementation_replay', [
        "if(equals(length(body('Find_implementation')),1)," + both(matches(old_row) + identity(old_row)) + ',true)'],
        'Implementation_payload')
    template = copy.deepcopy(actions['Before_event_Purpose_before_assurance'])
    create = copy.deepcopy(template); create['runAfter'] = {}
    create['inputs']['parameters'].update({'parameters/method': 'POST',
        'parameters/body': "@string(outputs('Implementation_payload'))",
        'parameters/headers': {'Accept': 'application/json;odata=minimalmetadata', 'Content-Type': 'application/json;odata=nometadata'}})
    create['inputs']['retryPolicy'] = {'type': 'none'}
    actions['Ensure_implementation'] = {'type': 'If',
        'expression': "@equals(length(body('Find_implementation')),0)",
        'actions': {'Create_implementation': create}, 'else': {'actions': {}},
        'runAfter': {'Verify_implementation_replay': ['Succeeded']}}

    # Re-run the publication producer's complete native frame after the append.
    after = {k: copy.deepcopy(v) for k, v in actions.items() if k.startswith('Before_event_')}
    after = rewrite(after, {'Before_event_': 'Implementation_after_'})
    after[next(iter(after))]['runAfter'] = {'Ensure_implementation': ['Succeeded']}
    actions.update(after)
    previous = 'Implementation_after_Purpose_before_selected'
    for name, action in original.items():
        if name.startswith('Verify_publication_frame_before_check_'):
            next_name = name.replace('Verify_publication_frame_before', 'Implementation_after_frame')
            actions[next_name] = rewrite(copy.deepcopy(action), {
                'Before_event_': 'Implementation_after_',
                "triggerBody()?['text']": "'Record publication'"})
            actions[next_name]['runAfter'] = {previous: ['Succeeded']}; previous = next_name
    frame_checks = [eq("outputs('" + name + "')", 'true') for name in actions if name.startswith('Implementation_after_frame_check_')]
    after_history = 'Implementation_after_Purpose_before_assurance'
    query('Read_implementation', after_history, "equals(item()?['EventUID'],outputs('Implementation_uid'))", previous)
    query('Read_implementation_corrections', after_history, "equals(item()?['SupersedesEventUID'],outputs('Implementation_uid'))", 'Read_implementation')
    previous = 'Read_implementation_corrections'
    for label, read in [('before', history), ('after', after_history)]:
        name = 'Implementation_others_' + label
        query(name, read, "not(equals(item()?['EventUID'],outputs('Implementation_uid')))", previous)
        actions[name + '_stable'] = {'type': 'Select', 'inputs': {'from': "@body('" + name + "')",
            'select': "@union(item(),json('{\"odata.id\":null}'))"}, 'runAfter': {name: ['Succeeded']}}
        previous = name + '_stable'
    row = "first(body('Read_implementation'))"
    final_checks = frame_checks + [
        "empty(body('" + after_history + "')?['nextLink'])", "empty(body('" + after_history + "')?['@nextLink'])",
        "empty(body('" + after_history + "')?['odata.nextLink'])", "empty(body('" + after_history + "')?['@odata.nextLink'])",
        "equals(length(body('Read_implementation_corrections')),0)",
        eq("body('Implementation_others_before_stable')", "body('Implementation_others_after_stable')"),
        "if(equals(length(body('Read_implementation')),1)," + both(matches(row) + identity(row)) + ',false)',
        "if(and(equals(length(body('Find_implementation')),1),equals(length(body('Read_implementation')),1)),equals(union(" + old_row + ",json('{\"odata.id\":null}')),union(" + row + ",json('{\"odata.id\":null}'))),true)"]
    actions['Verify_implementation_after'] = gate('implementation_after', final_checks, previous, unknown=True)
    actions['Native_implementation_receipt'] = comp({**held, 'qualified': True,
        'implementationCreatedCount': "@if(equals(length(body('Find_implementation')),0),1,0)",
        'preparedScope': '@' + scope, 'publication': '@' + publication_row,
        'implementation': '@' + row, 'issued': "@body('Read_issued')",
        'runId': "@workflow()?['run']?['name']"}, 'Verify_implementation_after')
    actions['Unknown_implementation_effect'] = comp({**held, 'implementationCreatedCount': None,
        'reconcileBeforeRetry': True, 'reason': 'Creation or final readback is uncertain; retain run and reconcile before retry.'})
    actions['Unknown_implementation_effect']['runAfter'] = {'Verify_implementation_after': ['Failed', 'TimedOut', 'Skipped']}
    # Reused post-copy holds now describe a read-only prerequisite, not a copy.
    actions['Verify_issued_metadata']['else']['actions']['Held_issued_metadata_mismatch']['inputs'].update(
        copyCreatedCount=0, implementationCreatedCount=0)
    out = copy.deepcopy(target); out['properties']['state'] = 'Stopped'
    out['properties']['definition']['actions'] = actions
    fields = {'text': {'type': 'string', 'title': 'Action'},
              'text_1': {'type': 'string', 'title': 'Implementation reference'},
              'text_2': {'type': 'string', 'title': 'Fictional implementation actions'},
              'text_3': {'type': 'string', 'title': 'Fictional evidence reference'},
              'text_4': {'type': 'string', 'title': 'Fictional next action'},
              'text_6': copy.deepcopy(source['triggers']['manual']['inputs']['schema']['properties']['text_6'])}
    fields['text_2'].update(maxLength=actions_limit,
        description=('Full implementation actions, up to 2000 characters; retained without shortening.'
                     if note is not None else
                     'Brief implementation summary, up to 255 characters; link detailed evidence separately.'))
    out['properties']['definition']['triggers'] = {'manual': {'type': 'Request', 'kind': 'Button',
        'inputs': {'schema': {'type': 'object', 'properties': fields, 'required': list(fields)}},
        'runtimeConfiguration': {'concurrency': {'runs': 1}}}}
    audit_actions(out['properties']['definition'])
    return out
