"""Bind an operator outcome pilot to an already qualified private case/source flow.

Does not deploy, authenticate, issue documents or write case/source records.
Bindings and generated definitions must remain outside Git.
"""
import argparse
import copy
import json
from pathlib import Path


def build(base):
    result = copy.deepcopy(base)
    props = result['properties']
    props['displayName'] = 'PPG Lifecycle | FICTIONAL operator decision outcomes'
    props['state'] = 'Stopped'
    definition = props['definition']
    fields = {
        'text': ('Event reference', 'Use a new LC03-OP- reference; reuse only for an identical retry.'),
        'text_1': ('Outcome', 'Rejected, Deferred, or Return for changes. Fictional pilot only.'),
        'text_2': ('Reason', 'Explain the decision and what remains unresolved.'),
        'text_3': ('Evidence reference', 'Reference the evidence supporting this fictional outcome.'),
        'text_4': ('Next action', 'Record what must happen next; this does not assign anyone.'),
    }
    definition['triggers']['manual']['inputs']['schema'] = {
        'type': 'object', 'properties': {
            key: {'title': title, 'type': 'string', 'x-ms-dynamically-added': True,
                  'description': description, 'x-ms-content-hint': 'TEXT'}
            for key, (title, description) in fields.items()
        }, 'required': list(fields),
    }
    actions = definition['actions']
    old = actions['Preflight']['actions']
    payload = copy.deepcopy(old['Payload_E4']['inputs'])
    if payload.get('FictionalTest') is not True or not payload.get('CaseUID', '').startswith('LC-FICTIONAL-'):
        raise ValueError('Only an explicitly fictional qualified case binding is supported')
    for key in ('ParentEventUID',):
        payload.pop(key, None)
    payload.update({
        'EventUID': "@triggerBody()?['text']",
        'Title': "@concat('FICTIONAL ',triggerBody()?['text_1'])",
        'DecisionOutcome': "@if(equals(triggerBody()?['text_1'],'Rejected'),'Rejected','Deferred')",
        'Summary': "@concat(triggerBody()?['text_1'],': ',triggerBody()?['text_2'])",
        'EvidenceReference': "@triggerBody()?['text_3']",
        'DecisionReference': "@triggerBody()?['text_3']",
        'NextAction': "@triggerBody()?['text_4']",
        'ConditionsState': 'Open',
        'ConditionsNotes': "@triggerBody()?['text_4']",
    })
    # Reuse the exact previously qualified connector operation and parameter shape.
    inner = {'Payload_E1': {'type': 'Compose', 'inputs': payload, 'runAfter': {}}}
    for name in ('Find_E1', 'Ensure_E1', 'Read_E1'):
        inner[name] = copy.deepcopy(old[name])
    base_uri = inner['Find_E1']['inputs']['parameters']['parameters/uri'].split('?$filter=')[0]
    query = "@concat('" + base_uri.replace("'", "''") + "?$filter=EventUID eq ',decodeUriComponent('%27'),triggerBody()?['text'],decodeUriComponent('%27'))"
    for name in ('Find_E1', 'Read_E1'):
        inner[name]['inputs']['parameters']['parameters/uri'] = query
    clauses = ["equals(length(body('Read_E1')?['value']),1)"]
    for key in payload:
        if key == 'OccurredOn':
            continue
        clauses.append("equals(first(body('Read_E1')?['value'])?['" + key + "'],outputs('Payload_E1')?['" + key + "'])")
    inner['Verify_E1'] = copy.deepcopy(old['Verify_E1'])
    inner['Verify_E1']['expression'] = '@and(' + ','.join(clauses) + ')'
    inner['Recheck_case'] = copy.deepcopy(old['Recheck_case'])
    inner['Recheck_case']['runAfter'] = {'Verify_E1': ['Succeeded']}
    inner['Recheck_source'] = copy.deepcopy(old['Recheck_source'])
    inner['Final_guard'] = copy.deepcopy(old['Final_guard'])
    inner['Final_guard']['actions']['Native_event_receipt']['inputs'] = {
        'eventUID': "@triggerBody()?['text']", 'disposition': "@triggerBody()?['text_1']",
        'createdCount': "@if(equals(length(body('Find_E1')?['value']),0),1,0)",
        'caseWriteCount': 0, 'sourceWriteCount': 0, 'publicationWriteCount': 0,
        'realPolicyEffects': False, 'actorAuthorityQualified': False,
        'nextAction': "@triggerBody()?['text_4']", 'runId': "@workflow()?['run']?['name']",
    }
    actions['Preflight']['actions'] = inner
    checks = ["startsWith(triggerBody()?['text'],'LC03-OP-')",
              "lessOrEquals(length(triggerBody()?['text']),80)",
              "not(contains(triggerBody()?['text'],decodeUriComponent('%27')))",
              "contains(createArray('Rejected','Deferred','Return for changes'),triggerBody()?['text_1'])"]
    checks += ["not(empty(trim(coalesce(triggerBody()?['" + key + "'],''))))" for key in fields]
    # Refuse malformed input before even reading case/source; event queries cannot inject quotes.
    definition['actions'] = {'Validate_operator_input': {
        'type': 'If', 'expression': '@and(' + ','.join(checks) + ')',
        'runAfter': {}, 'actions': actions,
        'else': {'actions': {'Refuse_input': {'type': 'Terminate', 'runAfter': {},
            'inputs': {'runStatus': 'Failed', 'runError': {'code': 'InvalidOperatorInput',
                       'message': 'Enter a supported fictional outcome, unique event reference, reason, evidence and next action.'}}}}},
    }}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('qualified_definition', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(json.loads(args.qualified_definition.read_text())), indent=2) + '\n')
