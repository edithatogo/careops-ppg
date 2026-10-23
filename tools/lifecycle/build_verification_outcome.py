"""Build an event-only native fictional failed/inconclusive verification form.

Consumes an existing qualified decision definition and selected native fictional
implementation. Emits a stopped definition; never deploys or changes case/source.
"""
import argparse
import json
from pathlib import Path
from build_decision_outcome import build as build_outcome


def build(base, parent):
    if parent.get('FictionalTest') is not True or parent.get('Stage') != 'Implementation' or parent.get('RecordState') != 'Recorded':
        raise ValueError('Recorded fictional implementation parent required')
    result = build_outcome(base)
    props = result['properties']
    props['displayName'] = 'PPG Lifecycle | FICTIONAL operator verification outcomes'
    definition = props['definition']
    fields = definition['triggers']['manual']['inputs']['schema']['properties']
    fields['text']['description'] = 'Use a new LC04-VERIFY-OP- reference; reuse only for an identical retry.'
    fields['text_1']['description'] = 'Failed or Inconclusive. This pilot cannot record completed verification.'
    fields['text_2']['title'] = 'Method and finding'
    fields['text_2']['description'] = 'Describe the verification method, observed finding and what remains unresolved.'
    wrapper = definition['actions']['Validate_operator_input']
    wrapper['expression'] = wrapper['expression'].replace('LC03-OP-', 'LC04-VERIFY-OP-').replace("createArray('Rejected','Deferred','Return for changes')", "createArray('Failed','Inconclusive')")
    wrapper['else']['actions']['Refuse_input']['inputs']['runError']['message'] = 'Enter Failed or Inconclusive, a unique fictional event reference, method/finding, evidence and next action.'
    actions = wrapper['actions']
    inner = actions['Preflight']['actions']
    payload = inner['Payload_E1']['inputs']
    scope_keys = ('CaseUID', 'DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')
    if any(payload.get(k) != parent.get(k) for k in scope_keys):
        raise ValueError('Implementation parent must match guarded source scope')
    payload.pop('ReadinessEventUID', None)
    payload.pop('DecisionReference', None)
    payload.update({
        'Title': "@concat('FICTIONAL verification ',triggerBody()?['text_1'])",
        'Stage': 'Verification', 'DecisionOutcome': 'Unknown',
        'VerificationResult': "@triggerBody()?['text_1']",
        'VerificationMethod': "@triggerBody()?['text_2']",
        'ParentEventUID': parent['EventUID'],
    })
    read = json.loads(json.dumps(actions['Read_case']))
    read['inputs']['parameters']['parameters/uri'] = "_api/web/lists/getbytitle('PPG Assurance Events')/items?$filter=EventUID eq '" + parent['EventUID'].replace("'", "''") + "'"
    read['runAfter'] = {'Read_readiness': ['Succeeded']}
    actions['Read_implementation'] = read
    conditions = [actions['Preflight']['expression'][1:], "equals(length(body('Read_implementation')?['value']),1)"]
    for key in scope_keys + ('EventUID', 'Stage', 'RecordState', 'FictionalTest'):
        value = parent[key]
        literal = 'true' if value is True else "'" + str(value).replace("'", "''") + "'"
        conditions.append("equals(first(body('Read_implementation')?['value'])?['" + key + "']," + literal + ")")
    actions['Preflight']['expression'] = '@and(' + ','.join(conditions) + ')'
    actions['Preflight']['runAfter'] = {'Read_implementation': ['Succeeded']}
    clauses = ["equals(length(body('Read_E1')?['value']),1)"]
    for key in payload:
        if key != 'OccurredOn':
            clauses.append("equals(first(body('Read_E1')?['value'])?['" + key + "'],outputs('Payload_E1')?['" + key + "'])")
    inner['Verify_E1']['expression'] = '@and(' + ','.join(clauses) + ')'
    receipt = inner['Final_guard']['actions']['Native_event_receipt']['inputs']
    receipt.update({'stage': 'Verification', 'implementationEventUID': parent['EventUID'], 'completionGranted': False})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('qualified_definition', 'implementation_readback', 'output'):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    parent = json.loads(args.implementation_readback.read_text())['body']['value'][0]
    args.output.write_text(json.dumps(build(json.loads(args.qualified_definition.read_text()), parent), indent=2) + '\n')
