"""Build a stopped, event-only fictional consultation outcome form.

Reuse a qualified consultation/readiness definition. Private bindings stay private;
the emitted flow does not assign, send, or update cases, sources or readiness.
"""
import argparse
import copy
import json
from pathlib import Path


def build(base, expected_case_etag):
    if not isinstance(expected_case_etag, str) or not expected_case_etag.strip() or expected_case_etag == '*':
        raise ValueError('Exact qualified case ETag required')
    result = copy.deepcopy(base)
    props = result['properties']
    props['displayName'] = 'PPG Lifecycle | FICTIONAL consultation outcomes'
    props['state'] = 'Stopped'
    definition = props['definition']
    actions = definition['actions']
    preflight = actions['Preflight']
    old = preflight['actions']
    payload = copy.deepcopy(old['Payload_E1']['inputs'])
    if payload.get('FictionalTest') is not True or not payload.get('CaseUID', '').startswith('LC-FICTIONAL-'):
        raise ValueError('Explicit fictional scope required')
    fields = {
        'text': ('Event reference', 'Unique LC-CONSULT-OP- reference. Reuse only for identical retry.'),
        'text_1': ('Outcome', 'Unanswered, Declined, or Conditional. Fictional recording only.'),
        'text_2': ('Finding', 'Describe the response or absence of a response and outstanding work.'),
        'text_3': ('Evidence reference', 'Retained evidence for this fictional assertion.'),
        'text_4': ('Next action', 'What remains to do. This does not assign or notify anyone.'),
    }
    definition['triggers']['manual']['inputs']['schema'] = {
        'type': 'object', 'properties': {key: {
            'title': title, 'description': description, 'type': 'string',
            'x-ms-dynamically-added': True, 'x-ms-content-hint': 'TEXT'
        } for key, (title, description) in fields.items()}, 'required': list(fields)
    }
    payload.update({
        'EventUID': "@triggerBody()?['text']",
        'Title': "@concat('FICTIONAL consultation ',triggerBody()?['text_1'])",
        'RecordState': "@if(equals(triggerBody()?['text_1'],'Unanswered'),'Pending response',if(equals(triggerBody()?['text_1'],'Declined'),'Declined','Responded'))",
        'ActorName': 'Technical qualification — fictional consultation assertion',
        'OccurredOn': '@utcNow()', 'Summary': "@triggerBody()?['text_2']",
        'ResponseSummary': "@triggerBody()?['text_2']",
        'EvidenceReference': "@triggerBody()?['text_3']", 'ConditionsState': 'Open',
        'ConditionsNotes': "@if(greater(length(triggerBody()?['text_4']),255),triggerBody()?['text_2'],triggerBody()?['text_4'])",
        'NextAction': "@triggerBody()?['text_4']",
    })
    inner = {'Payload_E1': {'type': 'Compose', 'inputs': payload, 'runAfter': {}}}
    for name in ('Find_E1', 'Ensure_E1', 'Read_E1', 'Verify_E1', 'Recheck_case', 'Recheck_source', 'Final_guard'):
        inner[name] = copy.deepcopy(old[name])
    uri = inner['Find_E1']['inputs']['parameters']['parameters/uri'].split('?$filter=')[0]
    query = "@concat('" + uri.replace("'", "''") + "?$filter=EventUID eq ',decodeUriComponent('%27'),triggerBody()?['text'],decodeUriComponent('%27'))"
    for name in ('Find_E1', 'Read_E1'):
        inner[name]['inputs']['parameters']['parameters/uri'] = query
    checks = ["equals(length(body('Read_E1')?['value']),1)"]
    checks.extend("equals(first(body('Read_E1')?['value'])?['" + k + "'],outputs('Payload_E1')?['" + k + "'])" for k in payload if k != 'OccurredOn')
    inner['Verify_E1']['expression'] = '@and(' + ','.join(checks) + ')'
    inner['Recheck_case']['runAfter'] = {'Verify_E1': ['Succeeded']}
    # A missing or adverse response cannot satisfy consultation. This is evaluated
    # from the actual saved native row, not inferred from successful creation.
    satisfied = "@and(equals(first(body('Read_E1')?['value'])?['RecordState'],'Responded'),contains(createArray('None recorded','Resolved'),first(body('Read_E1')?['value'])?['ConditionsState']))"
    receipt = inner['Final_guard']['actions']['Native_event_receipt']
    receipt['inputs'] = {
        'eventUID': "@triggerBody()?['text']", 'outcome': "@triggerBody()?['text_1']",
        'consultationSatisfied': satisfied, 'progressionGranted': False,
        'createdCount': "@if(equals(length(body('Find_E1')?['value']),0),1,0)",
        'caseWriteCount': 0, 'sourceWriteCount': 0, 'readinessWriteCount': 0,
        'realPolicyEffects': False, 'actorAuthorityQualified': False,
        'runId': "@workflow()?['run']?['name']",
    }
    preflight['actions'] = inner
    # Replace only the exact qualified case token in preflight and final recheck.
    marker = "equals(outputs('Read_case')?['headers']?['ETag'],"
    expression = preflight['expression']
    start = expression.index(marker) + len(marker)
    end = expression.index(')', start)
    old_literal = expression[start:end]
    new_literal = "'" + expected_case_etag.replace("'", "''") + "'"
    for container in (preflight, inner['Final_guard']):
        container['expression'] = container['expression'].replace(old_literal, new_literal)
    def input_text(key):
        return "string(coalesce(triggerBody()?['" + key + "'],''))"
    validations = ["startsWith(" + input_text('text') + ",'LC-CONSULT-OP-')",
                   "lessOrEquals(length(" + input_text('text') + '),80)',
                   "not(contains(" + input_text('text') + ",decodeUriComponent('%27')))",
                   "contains(createArray('Unanswered','Declined','Conditional'),triggerBody()?['text_1'])"]
    validations.extend("equals(triggerBody()?['" + k + "']," + input_text(k) + ')' for k in fields)
    validations.extend("not(empty(trim(coalesce(triggerBody()?['" + k + "'],''))))" for k in fields)
    validations.extend("lessOrEquals(length(" + input_text(k) + '),255)' for k in ('text_2', 'text_3'))
    validations.append("lessOrEquals(length(" + input_text('text_4') + '),2000)')
    definition['actions'] = {'Validate_operator_input': {
        'type': 'If', 'expression': '@and(' + ','.join(validations) + ')',
        'runAfter': {}, 'actions': actions, 'else': {'actions': {'Refuse_input': {
            'type': 'Terminate', 'runAfter': {}, 'inputs': {'runStatus': 'Failed',
                'runError': {'code': 'InvalidConsultationInput', 'message': 'Enter a supported fictional outcome, unique reference, finding, evidence and next action.'}}
        }}}
    }}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('qualified_definition', 'case_handoff', 'output'):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(json.loads(args.qualified_definition.read_text()),
        json.loads(args.case_handoff.read_text())['caseETag']), indent=2) + '\n')
