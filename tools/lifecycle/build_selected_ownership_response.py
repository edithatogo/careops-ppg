"""Build an event-only fictional response using authenticated selected context.

The operator supplies a response, never case/source pins or an offer identity.
Case projection and real responsibility/actor authority are separate.
"""
import argparse
import copy
import json
from pathlib import Path
from build_selected_ownership_offer import build as build_offer


def build(context, target, binding, probe_only=False):
    result = build_offer(context, target, binding)
    props = result['properties']
    props['displayName'] = 'PPG Lifecycle | FICTIONAL selected ownership response'
    definition = props['definition']
    fields = {
        'text': ('Response reference', 'Unique LC02-OP-RESP- reference; identical retry only.'),
        'text_1': ('Response', 'Accepted or Declined. Fictional recording; no case update or real assignment.'),
        'text_2': ('Reason', 'Explain the explicit fictional response.'),
        'text_3': ('Evidence reference', 'Retained evidence supporting this fictional response.'),
        'text_4': ('Next action', 'What remains to do; no assignment or notification follows.'),
    }
    schema = definition['triggers']['manual']['inputs']['schema']
    row = schema.get('properties', schema)['rows']['items']
    row['properties'] = {k: {'title': title, 'description': description, 'type': 'string',
        'x-ms-dynamically-added': True, 'x-ms-content-hint': 'TEXT'} for k, (title, description) in fields.items()}
    row['required'] = list(fields)
    definition['triggers']['manual']['inputs']['schema'] = {'type': 'object', 'properties': {'rows': {'type': 'array', 'items': row}}}
    def input_text(key):
        return "string(coalesce(triggerBody()?['" + key + "'],''))"
    clauses = ["startsWith(" + input_text('text') + ",'LC02-OP-RESP-')",
        "not(contains(" + input_text('text') + ",decodeUriComponent('%27')))",
        "lessOrEquals(length(" + input_text('text') + '),80)',
        "contains(createArray('Accepted','Declined'),triggerBody()?['text_1'])"]
    clauses += ["equals(triggerBody()?['" + k + "']," + input_text(k) + ')' for k in fields]
    clauses += ["not(empty(trim(coalesce(triggerBody()?['" + k + "'],''))))" for k in fields]
    clauses += ["lessOrEquals(length(" + input_text(k) + '),255)' for k in ('text_2', 'text_3')]
    clauses += ["lessOrEquals(length(" + input_text('text_4') + '),2000)']
    definition['actions']['Validate_response_input'] = {
        'type': 'If', 'expression': '@and(' + ','.join(clauses) + ')', 'runAfter': {},
        'actions': {'Input_valid': {'type': 'Compose', 'inputs': True, 'runAfter': {}}},
        'else': {'actions': {'Refuse_response_input': {'type': 'Terminate', 'runAfter': {},
            'inputs': {'runStatus': 'Failed', 'runError': {'code': 'InvalidOwnershipResponse',
                'message': 'Enter an explicit fictional Accepted or Declined response with unique reference, reason, evidence and next action.'}}}}}}
    definition['actions']['Resolve_context']['runAfter'] = {'Validate_response_input': ['Succeeded']}
    if probe_only:
        # Qualify the actual selected-item input envelope without any connector write.
        definition['actions'] = {
            'Observe_native_response_input': {'type': 'Compose', 'runAfter': {}, 'inputs': {
                'selectedId': "@triggerBody()?['entity']?['ID']",
                'values': {k: "@triggerBody()?['" + k + "']" for k in fields},
                'writeCount': 0, 'qualificationOnly': True}}}
        props['displayName'] += ' — input qualification'
        return result
    success = definition['actions']['Resolve_context']['actions']['Verify_baseline_boundary']['actions']['Verify_request']['actions']['Verify_source_and_case']['actions']
    base = binding['eventListUri']
    request = "outputs('Parse_baseline')?['request']"
    context_ref = "outputs('Selected_case_context')"
    parent = "first(body('Read_current_offer')?['value'])"
    def read(uri, previous):
        action = copy.deepcopy(success['Find_offer'])
        action['inputs']['parameters']['parameters/uri'] = uri
        action['runAfter'] = {previous: ['Succeeded']}
        return action
    prefix = "@concat('" + base.replace("'", "''")
    parent_query = prefix + "?$filter=EventUID eq ',decodeUriComponent('%27'),'LC02-OP-OFFER-'," + request + "?['requestReference'],decodeUriComponent('%27'))"
    history_query = prefix + "?$filter=ParentEventUID eq ',decodeUriComponent('%27'),'LC02-OP-OFFER-'," + request + "?['requestReference'],decodeUriComponent('%27'))"
    parent_item = prefix + "(',string(" + parent + "?['Id']),')')"
    success['Read_current_offer'] = read(parent_query, 'Selected_case_context')
    success['Read_response_history'] = read(history_query, 'Read_current_offer')
    success['Offer_payload']['runAfter'] = {'Read_response_history': ['Succeeded']}
    payload = success['Offer_payload']['inputs']
    payload.update({'Title': "@concat('FICTIONAL ownership ',triggerBody()?['text_1'])",
        'EventUID': "@triggerBody()?['text']", 'RecordState': "@triggerBody()?['text_1']",
        'ActorName': 'FICTIONAL operator response; real identity/authority not qualified',
        'ParentEventUID': '@' + parent + "?['EventUID']",
        'EvidenceReference': "@triggerBody()?['text_3']", 'Summary': "@triggerBody()?['text_2']",
        'NextAction': "@triggerBody()?['text_4']",
        'ConditionsState': "@if(equals(triggerBody()?['text_1'],'Accepted'),'None recorded','Open')",
        # ConditionsNotes is a 255-character Text field; NextAction is Note.
        # Preserve older short-input payloads for exact retry compatibility.
        'ConditionsNotes': "@if(greater(length(triggerBody()?['text_4']),255),triggerBody()?['text_2'],triggerBody()?['text_4'])"})
    success['Response_parent_before'] = read(parent_item, 'Offer_baseline_before')
    guard = success['Verify_offer_before']
    guard['runAfter'] = {'Response_parent_before': ['Succeeded']}
    initial_stage_clauses = [
        "equals(body('Read_selected_case')?['caseStatus'],'Initiated — FICTIONAL')",
        "equals(body('Read_selected_case')?['accountableRole'],concat('UNACCEPTED — proposed fictional role: '," + request + "?['proposedRole']))",
    ]
    initial_stage = 'and(' + ','.join(initial_stage_clauses) + ')'
    # A later case stage must not turn an immutable retry into another write.
    # Only the full matching retained row can bypass the initial-stage clauses;
    # every context, parent, history and fresh-token check still applies.
    replay_matches = ["equals(first(body('Find_offer')?['value'])?['" + k + "'],outputs('Offer_payload')?['" + k + "'])"
                      for k in payload if k != 'OccurredOn']
    exact_replay = "if(equals(length(body('Find_offer')?['value']),1),and(" + ','.join(replay_matches) + '),false)'
    success['Response_exact_replay'] = {'type': 'Compose', 'inputs': '@' + exact_replay,
        'runAfter': {'Response_parent_before': ['Succeeded']}}
    guard['runAfter'] = {'Response_exact_replay': ['Succeeded']}
    stage_and_tokens = guard['expression'][1:]
    for clause in initial_stage_clauses:
        if stage_and_tokens.count(clause) != 1:
            raise ValueError('Reviewed initial ownership-stage contract changed')
        stage_and_tokens = stage_and_tokens.replace(clause, 'or(' + clause + ",equals(outputs('Response_exact_replay'),true))")
    checks = [stage_and_tokens, "equals(length(body('Read_current_offer')?['value']),1)",
        "equals(" + parent + "?['EventUID'],concat('LC02-OP-OFFER-'," + request + "?['requestReference']))",
        "equals(" + parent + "?['RecordState'],'Proposed')",
        "equals(" + parent + "?['EventKind'],'Ownership handoff')",
        "equals(" + parent + "?['FictionalTest'],true)",
        "equals(" + parent + "?['SubjectRole']," + request + "?['proposedRole'])",
        "equals(" + parent + "?['FromRole'],'FICTIONAL initiating role')",
        "if(equals(length(body('Read_response_history')?['value']),0),true,and(equals(length(body('Read_response_history')?['value']),1),equals(first(body('Read_response_history')?['value'])?['EventUID'],triggerBody()?['text'])))",
        "not(empty(outputs('Response_parent_before')?['headers']?['ETag']))",
        "not(equals(outputs('Response_parent_before')?['headers']?['ETag'],'*'))"]
    # A favorable first page cannot establish a unique offer or empty history.
    # Preserve current no-write holds instead of selecting from partial results.
    checks += ["empty(body('" + name + "')?['" + marker + "'])"
               for name in ('Read_current_offer', 'Read_response_history')
               for marker in ('nextLink', '@nextLink', 'odata.nextLink', '@odata.nextLink', '__next')]
    keys = ['CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256']
    checks += ["equals(" + parent + "?['" + k + "']," + context_ref + "?['scope']?['" + k + "'])" for k in keys]
    checks += ["equals(body('Response_parent_before')?['" + k + "']," + parent + "?['" + k + "'])" for k in keys + ['Id', 'EventUID', 'RecordState', 'EventKind', 'SubjectRole', 'FromRole', 'FictionalTest']]
    guard['expression'] = '@and(' + ','.join(checks) + ')'
    for hold in guard['else']['actions'].values():
        hold['inputs']['reason'] = 'Selected offer, role, response history, case stage or document context does not match; no response write'
    apply = guard['actions']
    verify = apply['Verify_offer']
    verify['expression'] = '@and(equals(length(body(\'Read_offer\')?[\'value\']),1),' + ','.join(
        "equals(first(body('Read_offer')?['value'])?['" + k + "'],outputs('Offer_payload')?['" + k + "'])" for k in payload if k != 'OccurredOn') + ')'
    after = verify['actions']
    after['Response_parent_after'] = read(parent_item, 'Offer_baseline_after')
    final = after['Verify_offer_after']
    final['runAfter'] = {'Response_parent_after': ['Succeeded']}
    final['expression'] = '@and(' + final['expression'][1:] + ",equals(outputs('Response_parent_before')?['headers']?['ETag'],outputs('Response_parent_after')?['headers']?['ETag']))"
    receipt = final['actions']['Native_offer_receipt']['inputs']
    receipt.update({'ParentEventUID': '@' + parent + "?['EventUID']", 'response': "@triggerBody()?['text_1']",
        'ownershipResponseRecorded': True, 'ownershipAccepted': False,
        'acceptanceAssertionRecorded': "@equals(triggerBody()?['text_1'],'Accepted')", 'caseOwnershipUpdated': False,
        'caseAtInitialOwnershipStage': '@' + initial_stage,
        'historicalReplay': '@and(not(' + initial_stage + "),equals(outputs('Response_exact_replay'),true))",
        'progressionGranted': False})
    # Preserve tested uncertainty semantics, naming the effect as a response.
    return json.loads(json.dumps(result).replace('offerRecorded', 'responseRecorded'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('context', 'target', 'binding', 'output'):
        parser.add_argument('--' + key, required=True, type=Path)
    parser.add_argument('--probe-only', action='store_true')
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(json.loads(args.context.read_text()), json.loads(args.target.read_text()),
        json.loads(args.binding.read_text()), args.probe_only), indent=2) + '\n')
