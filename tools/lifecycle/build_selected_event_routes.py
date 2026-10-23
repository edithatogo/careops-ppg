"""Compose explicit event operations in the two existing selected-case flows.

No deployment or native I/O. Ownership remains available alongside an explicit
unbound consultation hold. A prepared binding cannot be accepted until its native
consumer is implemented and qualified; no source or partial draft is substituted.
"""
import argparse
import copy
import json
from pathlib import Path
from build_selected_ownership_offer import build as build_offer
from build_selected_ownership_response import build as build_response


def audit_actions(definition):
    names, maximum = set(), 0
    def visit(siblings, depth):
        nonlocal maximum
        for name, action in siblings.items():
            if name in names:
                raise ValueError('Ambiguous native action name: ' + name)
            names.add(name)
            maximum = max(maximum, depth)
            if not set(action.get('runAfter', {})).issubset(siblings):
                raise ValueError('runAfter must reference a sibling action: ' + name)
            if isinstance(action.get('actions'), dict):
                visit(action['actions'], depth + 1)
            if isinstance(action.get('else', {}).get('actions'), dict):
                visit(action['else']['actions'], depth + 1)
            for case in action.get('cases', {}).values():
                visit(case.get('actions', {}), depth + 1)
            if isinstance(action.get('default', {}).get('actions'), dict):
                visit(action['default']['actions'], depth + 1)
    visit(definition['actions'], 1)
    if maximum > 8:
        raise ValueError('Native action nesting exceeds the qualified limit')
    return {'maximumActionDepth': maximum, 'actionCount': len(names),
            'siblingDependenciesVerified': True}


def _compose(value, previous=None):
    return {'type': 'Compose', 'inputs': value,
            'runAfter': {previous: ['Succeeded']} if previous else {}}


def _flatten_after_check(work):
    """Keep after-proof truthfulness without another nested conditional level."""
    after = work['Verify_offer_before']['actions']['Verify_offer']['actions']
    final = after.pop('Verify_offer_after')
    if final['type'] != 'If' or set(final['actions']) != {'Native_offer_receipt'}:
        raise ValueError('Reviewed final event proof changed; review composition')
    after['Event_after_checks'] = {'type': 'Compose', 'inputs': final['expression'],
                                   'runAfter': copy.deepcopy(final['runAfter'])}
    receipt = copy.deepcopy(final['actions']['Native_offer_receipt'])
    receipt['runAfter'] = {'Event_after_checks': ['Succeeded']}
    receipt['inputs'].update({
        'qualified': "@equals(outputs('Event_after_checks'),true)",
        'effectState': "@if(equals(outputs('Event_after_checks'),true),'verified-retained-event','retained-event-context-changed')",
        'reason': "@if(equals(outputs('Event_after_checks'),true),json('null'),'The event is retained but its case, source, request or parent changed; reconcile before progressing')",
        'progressionGranted': False,
    })
    after['Native_offer_receipt'] = receipt
    return receipt['inputs']


def _offer_replay(work):
    request = "outputs('Parse_baseline')?['request']"
    clauses = ["equals(body('Read_selected_case')?['caseStatus'],'Initiated — FICTIONAL')",
        "equals(body('Read_selected_case')?['accountableRole'],concat('UNACCEPTED — proposed fictional role: '," + request + "?['proposedRole']))"]
    payload = work['Offer_payload']['inputs']
    comparisons = ["equals(first(body('Find_offer')?['value'])?['" + k + "'],outputs('Offer_payload')?['" + k + "'])"
                   for k in payload if k != 'OccurredOn']
    work['Offer_exact_replay'] = _compose("@if(equals(length(body('Find_offer')?['value']),1),and(" + ','.join(comparisons) + '),false)', 'Offer_baseline_before')
    guard = work['Verify_offer_before']
    guard['runAfter'] = {'Offer_exact_replay': ['Succeeded']}
    expression = guard['expression']
    for clause in clauses:
        if expression.count(clause) != 1:
            raise ValueError('Reviewed initial ownership-stage contract changed')
        expression = expression.replace(clause, 'or(' + clause + ",equals(outputs('Offer_exact_replay'),true))")
    guard['expression'] = expression
    return 'and(' + ','.join(clauses) + ')'


def build(kind, context, target, binding):
    if kind not in ('request', 'response'):
        raise ValueError('Choose request or response routing')
    if binding.get('preparedRevision') is not None:
        raise ValueError('Prepared consultation consumer must be qualified before binding a revision')
    role = binding.get('technicalConsultationRole', '')
    if not isinstance(role, str) or not role.startswith('FICTIONAL ') or len(role) > 255:
        raise ValueError('Explicit existing fictional technical role required')
    out = (build_offer if kind == 'request' else build_response)(context, target, binding)
    props, definition = out['properties'], out['properties']['definition']
    props['displayName'] = ('PPG Lifecycle | FICTIONAL offers and consultation requests'
                            if kind == 'request' else 'PPG Lifecycle | FICTIONAL selected responses')
    field = 'text' if kind == 'request' else 'text_5'
    ownership = 'Ownership offer' if kind == 'request' else 'Ownership response'
    consultation = 'Consultation request' if kind == 'request' else 'Consultation response'
    trigger = definition['triggers']['manual']
    old_schema = trigger['inputs']['schema']
    row = copy.deepcopy(old_schema.get('properties', old_schema)['rows']['items'])
    row.setdefault('properties', {})[field] = {
        'type': 'string', 'title': 'Action', 'enum': [ownership, consultation],
        'description': 'Choose the action for this selected case. Consultation stays closed until a prepared draft is verified.',
        'x-ms-dynamically-added': True, 'x-ms-content-hint': 'TEXT',
    }
    # Native forms cannot express mode-specific required fields. Ownership response
    # keeps its existing runtime validation; an unbound consultation check needs no
    # invented response content to return an honest missing-prerequisite hold.
    row['required'] = [field]
    trigger['inputs']['schema'] = {'type': 'object', 'properties': {'rows': {'type': 'array', 'items': row}}}
    actions = definition['actions']
    mode = "triggerBody()?['" + field + "']"
    held = {'qualified': False, 'eventWriteCount': 0, 'caseWrites': 0,
            'sourceWrites': 0, 'requestWrites': 0, 'notifications': 0,
            'progressionGranted': False, 'realPolicyEffects': False}
    actions['Validate_event_operation'] = {
        'type': 'If', 'expression': "@contains(createArray('" + ownership + "','" + consultation + "')," + mode + ')',
        'runAfter': {}, 'actions': {'Event_operation_valid': _compose(True)},
        'else': {'actions': {
            'Held_unsupported_event_operation': _compose({**held,
                'reason': 'Choose one of the supported actions; no event was attempted'}),
            'Stop_unsupported_event_operation': {'type': 'Terminate',
                'inputs': {'runStatus': 'Succeeded'},
                'runAfter': {'Held_unsupported_event_operation': ['Succeeded']}},
        }},
    }
    if kind == 'response':
        validate = actions['Validate_response_input']
        validate['expression'] = "@if(equals(" + mode + ",'" + ownership + "')," + validate['expression'][1:] + ',true)'
        validate['runAfter'] = {'Validate_event_operation': ['Succeeded']}
        response_fields={
            'text':('Response reference','Unique reference: LC02-OP-RESP- for ownership; LC-CONSULT-RESP- for consultation. Maximum 80 characters. Reuse only for an identical retry.'),
            'text_1':('Response / outcome','Ownership: Accepted or Declined. Consultation: Responded, Unanswered, Declined or Conditional. Responded does not mean policy approval.'),
            'text_2':('Reason / finding','Describe the response or outstanding work factually. Maximum 255 characters; retain unresolved conditions.'),
            'text_3':('Evidence reference','Retained evidence supporting this response. Maximum 255 characters; do not invent missing evidence.'),
            'text_4':('Next action','Describe the remaining step, including unresolved conditions. Maximum 2000 characters. No assignment or notification follows.'),
        }
        for key,(title,description) in response_fields.items():
            row['properties'][key]['title']=title
            row['properties'][key]['description']=description+' Required for either response action.'
    else:
        actions['Resolve_context']['runAfter'] = {'Validate_event_operation': ['Succeeded']}

    success = actions['Resolve_context']['actions']['Verify_baseline_boundary']['actions']['Verify_request']['actions']['Verify_source_and_case']['actions']
    context_action = success['Selected_case_context']
    work = {k: v for k, v in success.items() if k != 'Selected_case_context'}
    if kind == 'request':
        work['Offer_payload']['runAfter'] = {}
    else:
        work['Read_current_offer']['runAfter'] = {}
    initial_stage = _offer_replay(work) if kind == 'request' else None
    receipt = _flatten_after_check(work)
    if kind == 'request':
        receipt.update({'caseAtInitialOwnershipStage': '@' + initial_stage,
            'existingProposalReturned': "@equals(length(body('Find_offer')?['value']),1)",
            'historicalReplay': '@and(not(' + initial_stage + "),equals(outputs('Offer_exact_replay'),true))"})
    success.clear()
    success['Selected_case_context'] = context_action
    success['Route_ownership_event'] = {'type': 'If', 'expression': "@equals(" + mode + ",'" + ownership + "')",
        'runAfter': {'Selected_case_context': ['Succeeded']}, 'actions': work, 'else': {'actions': {}}}
    success['Route_unbound_consultation'] = {'type': 'If', 'expression': "@equals(" + mode + ",'" + consultation + "')",
        'runAfter': {'Selected_case_context': ['Succeeded']}, 'actions': {
            'Held_unbound_consultation': _compose({**held, 'consultationRecorded': False,
                'CaseUID': "@outputs('Selected_case_context')?['CaseUID']",
                'originalSourceScope': "@outputs('Selected_case_context')?['scope']",
                'originalSourceIsPreparedRevision': False, 'preparedRevision': None,
                'technicalRole': role,
                'reason': 'Finish and verify the prepared draft before recording consultation; the original source is not the prepared draft'})
        }, 'else': {'actions': {}}}
    def disable_mutation_retries(value):
        if isinstance(value,dict):
            inputs=value.get('inputs',{})
            if isinstance(inputs,dict) and inputs.get('parameters',{}).get('parameters/method')=='POST':
                inputs['retryPolicy']={'type':'none'}
            for child in value.values():disable_mutation_retries(child)
        elif isinstance(value,list):
            for child in value:disable_mutation_retries(child)
    disable_mutation_retries(actions)
    audit_actions(definition)
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=['request', 'response'], required=True)
    for key in ('context', 'target', 'binding', 'output'):
        parser.add_argument('--' + key, required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(args.kind, json.loads(args.context.read_text()),
        json.loads(args.target.read_text()), json.loads(args.binding.read_text())), indent=2) + '\n')
