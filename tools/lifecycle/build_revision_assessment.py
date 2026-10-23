"""Bind four native fictional consultation/readiness events to a new revision.

Reuses qualified connector shapes, emits a stopped flow, and never deploys or
changes source/case records. Exact bindings and output definitions remain private.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def build(base, request):
    scope = request['scope']
    if request.get('FictionalTest') is not True or not scope['CaseUID'].startswith('LC-FICTIONAL-'):
        raise ValueError('Explicit fictional scope required')
    if hashlib.sha256(request['exactText'].encode()).hexdigest() != scope['DocumentSHA256']:
        raise ValueError('New revision text/hash mismatch')
    if len(request['events']) != 4:
        raise ValueError('Separate pending/response and pending/finding records required')
    result = copy.deepcopy(base)
    props = result['properties']
    props['displayName'] = 'PPG Lifecycle | FICTIONAL new revision assessment'
    props['state'] = 'Stopped'
    actions = props['definition']['actions']
    def quote(s):
        return str(s).replace("'", "''")
    source = request['source']
    uri = "_api/web/GetFileById('" + source['UniqueId'] + "')"
    for name in ('Read_source_before', 'Read_source_after'):
        actions[name]['inputs']['parameters']['parameters/uri'] = uri + '?$select=UniqueId,ETag,Length'
    actions['Read_source_content']['inputs']['parameters']['parameters/uri'] = uri + '/$value'
    checks = [
        "equals(body('Read_case')?['CaseUID'],'" + quote(scope['CaseUID']) + "')",
        "equals(body('Read_case')?['sourceBaselineRef'],'" + quote(request['occurrence']) + "')",
        "equals(body('Read_case')?['accountableRole'],'" + quote(request['acceptedRole']) + "')",
        "equals(outputs('Read_case')?['headers']?['ETag'],'" + quote(request['caseETag']) + "')",
    ]
    for name in ('Read_source_before', 'Read_source_after'):
        checks.append("equals(body('" + name + "')?['ETag'],'" + quote(source['ETag']) + "')")
    content = "if(contains(body('Read_source_content'),'$content'),base64ToString(body('Read_source_content')?['$content']),string(body('Read_source_content')))"
    checks.append("equals(" + content + ",'" + quote(request['exactText']) + "')")
    preflight = actions['Preflight']
    preflight['expression'] = '@and(' + ','.join(checks) + ')'
    inner = preflight['actions']
    for index, event in enumerate(request['events'], 1):
        payload = event['body']
        if payload.get('FictionalTest') is not True or any(payload.get(k) != v for k, v in scope.items()):
            raise ValueError('Event must use new revision scope')
        expected_list = 'PPG Consultation and Handoff Events' if index <= 2 else 'PPG Readiness Events'
        if event['listTitle'] != expected_list:
            raise ValueError('Unexpected event list')
        if index in (2, 4) and payload.get('SupersedesEventUID') != request['events'][index - 2]['body']['EventUID']:
            raise ValueError('Findings must reference their own new pending record')
        name = 'E' + str(index)
        inner['Payload_' + name]['inputs'] = payload
        listuri = "_api/web/lists/getbytitle('" + expected_list + "')/items"
        for prefix in ('Find_', 'Read_'):
            inner[prefix + name]['inputs']['parameters']['parameters/uri'] = listuri + "?$filter=EventUID eq '" + quote(payload['EventUID']) + "'"
        clauses = ["equals(length(body('Read_" + name + "')?['value']),1)"]
        for key, val in payload.items():
            if val != '@utcNow()':
                clauses.append("equals(first(body('Read_" + name + "')?['value'])?['" + key + "'],outputs('Payload_" + name + "')?['" + key + "'])")
        inner['Verify_' + name]['expression'] = '@and(' + ','.join(clauses) + ')'
    inner['Recheck_source']['inputs']['parameters']['parameters/uri'] = uri + '?$select=ETag'
    receipt = inner['Final_guard']['actions']['Native_event_receipt']['inputs']
    receipt.update({'requestId': request['requestId'], 'scope': scope,
                    'eventUIDs': [x['body']['EventUID'] for x in request['events']],
                    'newRevisionAssessment': True, 'previousReadinessInherited': False})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('qualified_definition', 'request', 'output'):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(json.loads(args.qualified_definition.read_text()), json.loads(args.request.read_text())), indent=2) + '\n')
