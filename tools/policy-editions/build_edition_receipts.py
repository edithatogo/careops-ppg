"""Build fixed fictional edition receipt qualification; no native I/O or policy writes."""
import argparse
import hashlib
import json
from pathlib import Path


def build(request, reference):
    if request.get('FictionalTest') is not True:
        raise ValueError('Fictional request required')
    site, folder = request['site'], request['qualificationFolder']
    if len(request['receipts']) != 2 or {x['request']['operation'] for x in request['receipts']} != {'replace', 'withdraw'}:
        raise ValueError('Two explicit fictional transition receipts required')
    if len(request.get('filePins', [])) < 4 or len(request.get('events', [])) < 4:
        raise ValueError('Both source/issued revisions and their decision/publication events required')
    by_id = {e['EventUID']: e for e in request['events']}
    if len(by_id) != len(request['events']):
        raise ValueError('Ambiguous event identity')
    for receipt in request['receipts']:
        body = receipt['request']
        decision = by_id.get(body.get('decisionEventUID'), {})
        if (decision.get('Stage') != 'Decision' or decision.get('RecordState') != 'Recorded'
                or decision.get('DecisionOutcome') != 'Approved (recorded)'
                or decision.get('ConditionsState') not in ('None recorded', 'Resolved')
                or decision.get('FictionalTest') is not True):
            raise ValueError('Actual frozen fictional decision required')
        purpose = json.loads(decision.get('NextAction', '{}'))
        if purpose.get('purpose') != body['operation'] or purpose.get('retainedSubject') != body.get('subjectScope'):
            raise ValueError('Exact predecessor/purpose contract required')
        if body['operation'] == 'replace':
            publication = by_id.get(body.get('publicationEventUID'), {})
            if (purpose.get('replacement') != body.get('replacementScope') or
                    publication.get('ParentEventUID') != decision['EventUID'] or
                    publication.get('Stage') != 'Publication' or
                    publication.get('RecordState') != 'Recorded' or
                    any(publication.get(k) != body['replacementScope'][k] for k in body['replacementScope'])):
                raise ValueError('Verified replacement publication required')
        elif purpose.get('issuedReference') != body.get('issuedReference'):
            raise ValueError('Exact withdrawn issued reference required')
    def lit(v):
        return 'true' if v is True else "'" + str(v).replace("'", "''") + "'"
    def http(uri, after=None, method='GET', body=None):
        params = {'dataset': site, 'parameters/method': method, 'parameters/uri': uri, 'parameters/headers': {'Accept': 'application/json;odata=nometadata', 'Content-Type': 'application/json;odata=nometadata'}}
        if body is not None:
            params['parameters/body'] = body
        return {'type': 'OpenApiConnection', 'inputs': {'host': {'apiId': '/providers/Microsoft.PowerApps/apis/shared_sharepointonline', 'connectionName': 'shared_sharepointonline', 'operationId': 'HttpRequest'}, 'parameters': params}, 'runAfter': after or {}}
    def comp(value, after=None):
        return {'type': 'Compose', 'inputs': value, 'runAfter': after or {}}
    def guard(expr, yes, code, after):
        return {'type': 'If', 'expression': expr, 'actions': yes, 'else': {'actions': {'Refuse_' + code: {'type': 'Terminate', 'inputs': {'runStatus': 'Failed', 'runError': {'code': code, 'message': 'Fictional edition receipt held; no policy effect'}}, 'runAfter': {}}}}, 'runAfter': after}
    def text(action):
        return "if(contains(body('" + action + "'),'$content'),base64ToString(body('" + action + "')?['$content']),string(body('" + action + "')))"
    a, checks, previous = {}, [], None
    for i, pin in enumerate(request['filePins']):
        if hashlib.sha256(pin['text'].encode()).hexdigest() != pin['sha256']:
            raise ValueError('Frozen bytes do not match SHA-256')
        if not pin['etag'] or pin['etag'] == '*':
            raise ValueError('Exact file version required')
        name = 'File_' + str(i)
        uri = "_api/web/GetFileById('" + pin['uid'] + "')"
        a[name] = http(uri + '?$select=UniqueId,ETag', {previous: ['Succeeded']} if previous else None)
        a[name + '_bytes'] = http(uri + '/$value', {name: ['Succeeded']})
        a[name + '_after'] = http(uri + '?$select=UniqueId,ETag', {name + '_bytes': ['Succeeded']})
        checks += ["equals(body('" + name + "')?['ETag']," + lit(pin['etag']) + ')', "equals(body('" + name + "_after')?['ETag']," + lit(pin['etag']) + ')', 'equals(' + text(name + '_bytes') + ',' + lit(pin['text']) + ')']
        previous = name + '_after'
    for i, event in enumerate(request['events']):
        name = 'Event_' + str(i)
        if event.get('FictionalTest') is not True:
            raise ValueError('Fictional events required')
        a[name] = http("_api/web/lists/getbytitle('PPG Assurance Events')/items?$filter=EventUID eq " + lit(event['EventUID']), {previous: ['Succeeded']} if previous else None)
        checks.append("equals(length(body('" + name + "')?['value']),1)")
        for k, v in event.items():
            checks.append("equals(first(body('" + name + "')?['value'])?['" + k + "']," + lit(v) + ')')
        superseders = name + '_superseders'
        a[superseders] = http("_api/web/lists/getbytitle('PPG Assurance Events')/items?$filter=SupersedesEventUID eq " + lit(event['EventUID']), {name: ['Succeeded']})
        checks += ["equals(length(body('" + superseders + "')?['value']),0)", "empty(body('" + superseders + "')?['odata.nextLink'])", "empty(body('" + superseders + "')?['@odata.nextLink'])"]
        previous = superseders
    writes, last = {}, None
    for i, receipt in enumerate(request['receipts']):
        name, body = receipt['name'], receipt['request']
        if not name.startswith('FICTIONAL-LC04-') or '/' in name or '..' in name or not name.endswith('.json') or body.get('FictionalTest') is not True or body.get('scope') != 'isolated-fictional-projection-only':
            raise ValueError('Isolated fictional target required')
        if body.get('historyRetained') is not True or not body.get('decisionEventUID'):
            raise ValueError('Preserved history and explicit decision required')
        label = 'Receipt_' + str(i)
        file = "_api/web/GetFileByServerRelativePath(decodedurl=" + lit(folder + '/' + name) + ')'
        writes[label + '_request'] = comp(body, {last: ['Succeeded']} if last else None)
        writes[label + '_find'] = http("_api/web/GetFolderByServerRelativePath(decodedurl=" + lit(folder) + ")/Files?$filter=Name eq " + lit(name), {label + '_request': ['Succeeded']})
        payload = {'request': '@outputs(\'' + label + '_request\')', 'runId': "@workflow()?['run']?['name']", 'recordedAtUtc': '@utcNow()', 'realPolicyEffects': False}
        create = {label + '_payload': comp(payload), label + '_create': http("_api/web/GetFolderByServerRelativePath(decodedurl=" + lit(folder) + ")/Files/add(overwrite=false,url=" + lit(name) + ')', {label + '_payload': ['Succeeded']}, 'POST', "@string(outputs('" + label + "_payload'))")}
        writes[label + '_ensure'] = {'type': 'If', 'expression': "@equals(length(body('" + label + "_find')?['value']),0)", 'actions': create, 'else': {'actions': {}}, 'runAfter': {label + '_find': ['Succeeded']}}
        writes[label + '_read'] = http(file + '/$value', {label + '_ensure': ['Succeeded']})
        writes[label + '_parsed'] = comp('@json(' + text(label + '_read') + ')', {label + '_read': ['Succeeded']})
        writes[label + '_verify'] = guard("@and(equals(string(outputs('" + label + "_parsed')?['request']),string(outputs('" + label + "_request'))),equals(outputs('" + label + "_parsed')?['realPolicyEffects'],false))", {}, 'ReceiptConflict' + str(i), {label + '_parsed': ['Succeeded']})
        last = label + '_verify'
    writes['Native_receipt'] = comp({'requestId': request['requestId'], 'scope': 'isolated-fictional-projection-only', 'runId': "@workflow()?['run']?['name']", 'createdCount': "@add(if(equals(length(body('Receipt_0_find')?['value']),0),1,0),if(equals(length(body('Receipt_1_find')?['value']),0),1,0))", 'caseWrites': 0, 'sourceWrites': 0, 'realPolicyEffects': False}, {last: ['Succeeded']})
    groups, group = [], []
    for clause in checks:
        if group and len('@and(' + ','.join(group + [clause]) + ')') > 6000:
            groups.append(group)
            group = []
        group.append(clause)
    if group:
        groups.append(group)
    gated = writes
    for index in reversed(range(len(groups))):
        gated = {'Frozen_evidence_guard_' + str(index): guard('@and(' + ','.join(groups[index]) + ')', gated, 'EvidenceChanged' + str(index), {})}
    first = next(iter(gated.values()))
    first['runAfter'] = {previous: ['Succeeded']}
    a.update(gated)
    definition = dict(reference['properties']['definition'])
    definition['actions'] = a
    definition['triggers'] = {'manual': {'type': 'Request', 'kind': 'Button', 'inputs': {'schema': {'type': 'object', 'properties': {}, 'required': []}}, 'runtimeConfiguration': {'concurrency': {'runs': 1}}}}
    return {'properties': {'displayName': 'PPG Lifecycle | FICTIONAL edition receipts qualification', 'definition': definition, 'connectionReferences': {'shared_sharepointonline': reference['properties']['connectionReferences']['shared_sharepointonline']}, 'state': 'Stopped'}}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for flag in ['request', 'reference-flow', 'output']:
        parser.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    result = build(json.loads(Path(args.request).read_text()), json.loads(Path(args.reference_flow).read_text()))
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
