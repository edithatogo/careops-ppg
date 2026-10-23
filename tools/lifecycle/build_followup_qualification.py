"""Build a stopped native fictional implementation/verification qualification.

Consumes private qualified definition and exact publication/file bindings. No I/O
other than local input/output; no deployment, source/case mutation or publication.
"""
import argparse
import copy
import json
from pathlib import Path


def build(base, request):
    if request.get('FictionalTest') is not True:
        raise ValueError('Fictional binding required')
    result = copy.deepcopy(base)
    props = result['properties']
    props['displayName'] = 'PPG Lifecycle | FICTIONAL implementation and verification'
    props['state'] = 'Stopped'
    definition = props['definition']
    actions = definition['actions']
    scope = request['scope']
    if not scope['CaseUID'].startswith('LC-FICTIONAL-'):
        raise ValueError('Fictional case required')
    publication = request['publication']
    issued = request['issued']
    if publication['FictionalTest'] is not True or any(publication[k] != v for k, v in scope.items()):
        raise ValueError('Publication scope mismatch')
    if publication['Stage'] != 'Publication' or publication['RecordState'] != 'Recorded':
        raise ValueError('Recorded publication required')
    template = actions['Read_case']
    def read(uri, after):
        action = copy.deepcopy(template)
        action['inputs']['parameters']['parameters/uri'] = uri
        action['runAfter'] = {after: ['Succeeded']}
        return action
    def quote(value):
        return str(value).replace("'", "''")
    listuri = "_api/web/lists/getbytitle('PPG Assurance Events')/items"
    actions['Read_publication'] = read(listuri + "?$filter=EventUID eq '" + quote(publication['EventUID']) + "'", 'Read_readiness')
    fileuri = "_api/web/GetFileById('" + issued['UniqueId'] + "')"
    actions['Read_issued_before'] = read(fileuri + '?$select=UniqueId,ETag,Length', 'Read_publication')
    actions['Read_issued_content'] = read(fileuri + '/$value', 'Read_issued_before')
    actions['Read_issued_after'] = read(fileuri + '?$select=UniqueId,ETag,Length', 'Read_issued_content')
    preflight = actions['Preflight']
    conditions = [preflight['expression'][1:], "equals(length(body('Read_publication')?['value']),1)"]
    for key in list(scope) + ['EventUID', 'Stage', 'RecordState', 'ConditionsState', 'ParentEventUID', 'PublicationURL', 'PublishedVersionRef', 'FictionalTest']:
        val = publication[key]
        literal = 'true' if val is True else "'" + quote(val) + "'"
        conditions.append("equals(first(body('Read_publication')?['value'])?['" + key + "']," + literal + ")")
    for action in ('Read_issued_before', 'Read_issued_after'):
        conditions.append("equals(body('" + action + "')?['ETag'],'" + quote(issued['ETag']) + "')")
    decoded = "if(contains(body('Read_issued_content'),'$content'),base64ToString(body('Read_issued_content')?['$content']),string(body('Read_issued_content')))"
    conditions.append("equals(" + decoded + ",'" + quote(request['exactText']) + "')")
    preflight['expression'] = '@and(' + ','.join(conditions) + ')'
    preflight['runAfter'] = {'Read_issued_after': ['Succeeded']}
    old = preflight['actions']
    qualified_scope = old['Payload_E4']['inputs']
    if any(qualified_scope.get(key) != value for key, value in scope.items()):
        raise ValueError('Request scope must match the qualified source guards')
    inner = {}
    previous = None
    for index, payload in enumerate(request['events'], 1):
        name = 'E' + str(index)
        if payload.get('FictionalTest') is not True or any(payload[k] != v for k, v in scope.items()):
            raise ValueError('Event scope mismatch')
        if index == 1 and (payload['Stage'] != 'Implementation' or payload['ParentEventUID'] != publication['EventUID']):
            raise ValueError('Implementation must reference selected publication')
        if index == 2 and (payload['Stage'] != 'Verification' or payload['ParentEventUID'] != request['events'][0]['EventUID']):
            raise ValueError('Verification must reference selected implementation')
        inner['Payload_' + name] = {'type': 'Compose', 'inputs': payload, 'runAfter': {previous: ['Succeeded']} if previous else {}}
        for prefix in ('Find_', 'Ensure_', 'Read_', 'Verify_'):
            inner[prefix + name] = copy.deepcopy(old[prefix + name])
        for prefix in ('Find_', 'Read_'):
            inner[prefix + name]['inputs']['parameters']['parameters/uri'] = listuri + "?$filter=EventUID eq '" + quote(payload['EventUID']) + "'"
        clauses = ["equals(length(body('Read_" + name + "')?['value']),1)"]
        for key in payload:
            if key != 'OccurredOn':
                clauses.append("equals(first(body('Read_" + name + "')?['value'])?['" + key + "'],outputs('Payload_" + name + "')?['" + key + "'])")
        inner['Verify_' + name]['expression'] = '@and(' + ','.join(clauses) + ')'
        previous = 'Verify_' + name
    if len(request['events']) != 2:
        raise ValueError('Exactly two follow-up stages required')
    inner['Recheck_case'] = copy.deepcopy(old['Recheck_case'])
    inner['Recheck_case']['runAfter'] = {previous: ['Succeeded']}
    inner['Recheck_source'] = copy.deepcopy(old['Recheck_source'])
    inner['Recheck_issued'] = read(fileuri + '?$select=ETag', 'Recheck_source')
    final = copy.deepcopy(old['Final_guard'])
    final['runAfter'] = {'Recheck_issued': ['Succeeded']}
    final['expression'] = '@and(' + final['expression'][1:] + ",equals(body('Recheck_issued')?['ETag'],body('Read_issued_after')?['ETag']))"
    final['actions']['Native_event_receipt']['inputs'] = {
        'requestId': request['requestId'], 'scope': scope,
        'eventUIDs': [x['EventUID'] for x in request['events']],
        'createdCount': "@add(if(equals(length(body('Find_E1')?['value']),0),1,0),if(equals(length(body('Find_E2')?['value']),0),1,0))",
        'runId': "@workflow()?['run']?['name']", 'asOfUtc': '@utcNow()',
        'caseWrites': 0, 'sourceWrites': 0, 'issuedFileWrites': 0,
        'realPolicyEffects': False, 'ordinaryUserAccessQualified': False,
    }
    inner['Final_guard'] = final
    preflight['actions'] = inner
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('qualified_definition', 'request', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(json.loads(args.qualified_definition.read_text()), json.loads(args.request.read_text())), indent=2) + '\n')
