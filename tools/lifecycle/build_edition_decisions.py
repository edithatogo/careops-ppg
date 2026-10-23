"""Emit a stopped, event-only fictional replacement/withdrawal decision flow.

Reuses a qualified new-revision assessment definition. Private scope/source/event
bindings are explicit. No deployment or native effects occur in this builder.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def build(base, request):
    if request.get('FictionalTest') is not True:
        raise ValueError('Fictional request required')
    new_scope, old_scope = request['replacementScope'], request['retainedScope']
    if not new_scope['CaseUID'].startswith('LC-FICTIONAL-') or new_scope['CaseUID'] != old_scope['CaseUID']:
        raise ValueError('Same fictional case required')
    if new_scope == old_scope:
        raise ValueError('Distinct revisions required')
    if hashlib.sha256(request['retainedText'].encode()).hexdigest() != old_scope['DocumentSHA256']:
        raise ValueError('Retained text/hash mismatch')
    result = copy.deepcopy(base)
    props = result['properties']
    props['displayName'] = 'PPG Lifecycle | FICTIONAL edition purpose decisions'
    props['state'] = 'Stopped'
    actions = props['definition']['actions']
    old_inner = actions['Preflight']['actions']
    if any(old_inner['Payload_E4']['inputs'].get(k) != v for k, v in new_scope.items()):
        raise ValueError('Qualified source guard must match new revision')
    def q(s):
        return str(s).replace("'", "''")
    def read(uri, previous):
        action = copy.deepcopy(actions['Read_case'])
        action['inputs']['parameters']['parameters/uri'] = uri
        action['runAfter'] = {previous: ['Succeeded']}
        return action
    actions['Read_selected_consultation'] = read("_api/web/lists/getbytitle('PPG Consultation and Handoff Events')/items?$filter=EventUID eq '" + q(request['consultationUID']) + "'", 'Read_source_after')
    actions['Read_selected_readiness'] = read("_api/web/lists/getbytitle('PPG Readiness Events')/items?$filter=EventUID eq '" + q(request['readinessUID']) + "'", 'Read_selected_consultation')
    retained_uri = "_api/web/GetFileById('" + request['retainedSource']['UniqueId'] + "')"
    actions['Read_retained_before'] = read(retained_uri + '?$select=ETag', 'Read_selected_readiness')
    actions['Read_retained_content'] = read(retained_uri + '/$value', 'Read_retained_before')
    actions['Read_retained_after'] = read(retained_uri + '?$select=ETag', 'Read_retained_content')
    conditions = [actions['Preflight']['expression'][1:]]
    for name, field, expected in [('Read_selected_consultation', 'RecordState', 'Responded'), ('Read_selected_readiness', 'Finding', 'Ready for decision')]:
        conditions.append("equals(length(body('" + name + "')?['value']),1)")
        for key, val in new_scope.items():
            conditions.append("equals(first(body('" + name + "')?['value'])?['" + key + "'],'" + q(val) + "')")
        conditions += ["equals(first(body('" + name + "')?['value'])?['" + field + "'],'" + expected + "')", "equals(first(body('" + name + "')?['value'])?['FictionalTest'],true)", "equals(first(body('" + name + "')?['value'])?['ConditionsState'],'None recorded')"]
    for name in ('Read_retained_before', 'Read_retained_after'):
        conditions.append("equals(body('" + name + "')?['ETag'],'" + q(request['retainedSource']['ETag']) + "')")
    content = "if(contains(body('Read_retained_content'),'$content'),base64ToString(body('Read_retained_content')?['$content']),string(body('Read_retained_content')))"
    conditions.append("equals(" + content + ",'" + q(request['retainedText']) + "')")
    preflight = actions['Preflight']
    preflight['expression'] = '@and(' + ','.join(conditions) + ')'
    preflight['runAfter'] = {'Read_retained_after': ['Succeeded']}
    inner = {}
    events = request['events']
    if len(events) != 2:
        raise ValueError('Distinct replacement and withdrawal records required')
    for index, (payload, purpose, scope) in enumerate(zip(events, ['replace', 'withdraw'], [new_scope, old_scope]), 1):
        if payload.get('FictionalTest') is not True or any(payload.get(k) != v for k, v in scope.items()):
            raise ValueError('Purpose decision scope mismatch')
        evidence = json.loads(payload['NextAction'])
        expected_subject = {k: old_scope[k] for k in ('DocumentReference', 'ReviewedVersionRef', 'DocumentSHA256')}
        if evidence['purpose'] != purpose or evidence['retainedSubject'] != expected_subject:
            raise ValueError('Explicit structured purpose and predecessor required')
        if purpose == 'replace':
            if payload['ReadinessEventUID'] != request['readinessUID'] or evidence['replacement'] != {k: new_scope[k] for k in expected_subject}:
                raise ValueError('Fresh readiness and replacement pins required')
        elif payload.get('ReadinessEventUID'):
            raise ValueError('Original approval/readiness must not stand in for withdrawal purpose')
        if payload['Stage'] != 'Decision' or payload['RecordState'] != 'Recorded' or payload['DecisionOutcome'] != 'Approved (recorded)':
            raise ValueError('Explicit fictional decision required')
        name = 'E' + str(index)
        inner['Payload_' + name] = copy.deepcopy(old_inner['Payload_' + name])
        inner['Payload_' + name]['inputs'] = payload
        for prefix in ('Find_', 'Ensure_', 'Read_', 'Verify_'):
            inner[prefix + name] = copy.deepcopy(old_inner[prefix + name])
        listuri = "_api/web/lists/getbytitle('PPG Assurance Events')/items"
        inner['Ensure_' + name]['actions']['Create_' + name]['inputs']['parameters']['parameters/uri'] = listuri
        for prefix in ('Find_', 'Read_'):
            inner[prefix + name]['inputs']['parameters']['parameters/uri'] = listuri + "?$filter=EventUID eq '" + q(payload['EventUID']) + "'"
        clauses = ["equals(length(body('Read_" + name + "')?['value']),1)"]
        for key, val in payload.items():
            if val != '@utcNow()':
                clauses.append("equals(first(body('Read_" + name + "')?['value'])?['" + key + "'],outputs('Payload_" + name + "')?['" + key + "'])")
        inner['Verify_' + name]['expression'] = '@and(' + ','.join(clauses) + ')'
    inner['Recheck_case'] = copy.deepcopy(old_inner['Recheck_case'])
    inner['Recheck_case']['runAfter'] = {'Verify_E2': ['Succeeded']}
    inner['Recheck_source'] = copy.deepcopy(old_inner['Recheck_source'])
    inner['Recheck_retained'] = read(retained_uri + '?$select=ETag', 'Recheck_source')
    final = copy.deepcopy(old_inner['Final_guard'])
    final['runAfter'] = {'Recheck_retained': ['Succeeded']}
    final['expression'] = '@and(' + final['expression'][1:] + ",equals(body('Recheck_retained')?['ETag'],body('Read_retained_after')?['ETag']))"
    final['actions']['Native_event_receipt']['inputs'] = {
        'requestId': request['requestId'], 'replacementScope': new_scope, 'retainedScope': old_scope,
        'eventUIDs': [x['EventUID'] for x in events], 'freshReadinessUID': request['readinessUID'],
        'createdCount': "@add(if(equals(length(body('Find_E1')?['value']),0),1,0),if(equals(length(body('Find_E2')?['value']),0),1,0))",
        'runId': "@workflow()?['run']?['name']", 'caseWrites': 0, 'sourceWrites': 0,
        'issuedFileWrites': 0, 'realPolicyEffects': False, 'actorAuthorityQualified': False,
    }
    inner['Final_guard'] = final
    preflight['actions'] = inner
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('qualified_definition', 'request', 'output'):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(json.loads(args.qualified_definition.read_text()), json.loads(args.request.read_text())), indent=2) + '\n')
